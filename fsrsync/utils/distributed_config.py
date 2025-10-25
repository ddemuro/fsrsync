"""
Distributed Configuration Management for FSRsync

Provides cluster-wide configuration with:
- Configuration versioning
- Atomic updates across cluster
- Rollback support
- Configuration validation
- Version control
- Change history tracking
- Multi-environment support

## Configuration Environments

DEVELOPMENT: Development environment
STAGING: Staging environment
PRODUCTION: Production environment
TESTING: Testing environment
"""

import time
import logging
import json
from typing import Dict, List, Optional, Any, Set, Tuple
from dataclasses import dataclass, field
from enum import Enum


class ConfigEnvironment(Enum):
    """Configuration environment"""
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    TESTING = "testing"


class ConfigStatus(Enum):
    """Configuration status"""
    DRAFT = "draft"
    PROPOSED = "proposed"
    APPLIED = "applied"
    ROLLED_BACK = "rolled_back"
    FAILED = "failed"


@dataclass
class ConfigVersion:
    """Configuration version"""
    version_id: int
    environment: ConfigEnvironment
    config_data: Dict[str, Any] = field(default_factory=dict)
    status: ConfigStatus = ConfigStatus.DRAFT
    created_by: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    applied_at: Optional[float] = None
    rolled_back_at: Optional[float] = None
    applied_nodes: Set[str] = field(default_factory=set)
    failed_nodes: Set[str] = field(default_factory=set)
    change_description: str = ""
    validation_errors: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_fully_applied(self) -> bool:
        """Check if applied to all nodes"""
        return len(self.failed_nodes) == 0 and len(self.applied_nodes) > 0


@dataclass
class ConfigChange:
    """Configuration change record"""
    change_id: str
    from_version: int
    to_version: int
    timestamp: float = field(default_factory=time.time)
    changes: Dict[str, Tuple[Any, Any]] = field(default_factory=dict)  # key: (old, new)
    applied: bool = False
    applied_at: Optional[float] = None


class DistributedConfigManager:
    """
    Distributed configuration manager for FSRsync.

    Manages cluster-wide configuration with atomic updates,
    versioning, and rollback support.
    """

    def __init__(self, logger_instance=None):
        """
        Initialize distributed config manager.

        Args:
            logger_instance: Logger instance
        """
        self.logger = logger_instance or logging.getLogger(__name__)

        # Configuration storage
        self.configs: Dict[str, Dict[int, ConfigVersion]] = {
            env.value: {} for env in ConfigEnvironment
        }

        # Current active versions per environment
        self.active_versions: Dict[str, int] = {
            env.value: 0 for env in ConfigEnvironment
        }

        # Configuration change history
        self.change_history: Dict[str, List[ConfigChange]] = {
            env.value: [] for env in ConfigEnvironment
        }

        # Default configuration
        self.default_config: Dict[str, Any] = {
            'sync_enabled': True,
            'max_peers': 100,
            'max_concurrent_transfers': 50,
            'bandwidth_limit_mbps': 100,
            'health_check_interval': 30,
            'heartbeat_interval': 5,
            'log_level': 'INFO',
            'enable_compression': True,
            'enable_encryption': True,
            'conflict_resolution': 'timestamp',
            'retention_days': 30
        }

        # Configuration schemas for validation
        self.schemas: Dict[str, Dict[str, str]] = {}
        self._initialize_schemas()

        # Pending changes
        self.pending_changes: Dict[str, List[str]] = {
            env.value: [] for env in ConfigEnvironment
        }

        # Node acknowledgments
        self.node_acks: Dict[str, Dict[str, Set[str]]] = {}

        self.logger.info("DistributedConfigManager initialized")

    def _initialize_schemas(self) -> None:
        """Initialize configuration schemas"""
        self.schemas = {
            'sync_enabled': 'bool',
            'max_peers': 'int',
            'max_concurrent_transfers': 'int',
            'bandwidth_limit_mbps': 'int',
            'health_check_interval': 'int',
            'heartbeat_interval': 'int',
            'log_level': 'str',
            'enable_compression': 'bool',
            'enable_encryption': 'bool',
            'conflict_resolution': 'str',
            'retention_days': 'int'
        }

    def create_config(self, environment: str, config_data: Dict[str, Any],
                     description: str = "",
                     created_by: Optional[str] = None) -> Optional[int]:
        """
        Create new configuration version.

        Args:
            environment: Target environment
            config_data: Configuration data
            description: Change description
            created_by: User creating the config

        Returns:
            Version ID if created successfully
        """
        try:
            env = ConfigEnvironment(environment.lower())
            env_key = env.value

            # Validate configuration
            validation_errors = self._validate_config(config_data)
            if validation_errors:
                self.logger.warning(
                    f"Configuration validation failed: {validation_errors}"
                )

            # Get next version number
            next_version = max(
                self.configs[env_key].keys(),
                default=0
            ) + 1

            version = ConfigVersion(
                version_id=next_version,
                environment=env,
                config_data=config_data,
                created_by=created_by,
                change_description=description,
                validation_errors=validation_errors
            )

            self.configs[env_key][next_version] = version

            self.logger.info(
                f"Created config version {next_version} for "
                f"environment {environment}"
            )

            return next_version

        except Exception as e:
            self.logger.error(f"Error creating config: {e}")
            return None

    def apply_config(self, environment: str, version_id: int,
                    nodes: Optional[Set[str]] = None) -> bool:
        """
        Apply configuration version to cluster.

        Args:
            environment: Target environment
            version_id: Configuration version to apply
            nodes: Optional set of nodes to apply to

        Returns:
            True if application initiated
        """
        try:
            env = ConfigEnvironment(environment.lower())
            env_key = env.value

            if version_id not in self.configs[env_key]:
                self.logger.error(f"Configuration version {version_id} not found")
                return False

            version = self.configs[env_key][version_id]

            # Check if can apply
            if version.status not in [ConfigStatus.DRAFT, ConfigStatus.PROPOSED]:
                self.logger.warning(
                    f"Cannot apply config in status {version.status.value}"
                )
                return False

            version.status = ConfigStatus.PROPOSED

            # Track which nodes need to apply
            if nodes:
                version.applied_nodes.clear()
                version.failed_nodes.clear()

            self.pending_changes[env_key].append(f"v{version_id}")

            self.logger.info(
                f"Initiated application of config version {version_id} "
                f"for environment {environment}"
            )

            return True

        except Exception as e:
            self.logger.error(f"Error applying config: {e}")
            return False

    def confirm_config_application(self, environment: str, version_id: int,
                                  node_id: str, success: bool = True,
                                  error: Optional[str] = None) -> bool:
        """
        Confirm configuration application on a node.

        Args:
            environment: Target environment
            version_id: Configuration version
            node_id: Node applying the config
            success: Whether application succeeded
            error: Error message if failed

        Returns:
            True if confirmed
        """
        try:
            env = ConfigEnvironment(environment.lower())
            env_key = env.value

            if version_id not in self.configs[env_key]:
                return False

            version = self.configs[env_key][version_id]

            if success:
                version.applied_nodes.add(node_id)
                version.failed_nodes.discard(node_id)
            else:
                version.failed_nodes.add(node_id)
                version.applied_nodes.discard(node_id)

            # Check if fully applied
            if version.is_fully_applied:
                version.status = ConfigStatus.APPLIED
                version.applied_at = time.time()
                self.active_versions[env_key] = version_id

                self.logger.info(
                    f"Configuration version {version_id} fully applied "
                    f"for environment {environment}"
                )

            return True

        except Exception as e:
            self.logger.error(f"Error confirming config application: {e}")
            return False

    def rollback_config(self, environment: str, version_id: int) -> bool:
        """
        Rollback to previous configuration version.

        Args:
            environment: Target environment
            version_id: Version to rollback to

        Returns:
            True if rollback initiated
        """
        try:
            env = ConfigEnvironment(environment.lower())
            env_key = env.value

            if version_id not in self.configs[env_key]:
                self.logger.error(f"Configuration version {version_id} not found")
                return False

            version = self.configs[env_key][version_id]

            if version.status != ConfigStatus.APPLIED:
                self.logger.warning(
                    f"Can only rollback applied configs, "
                    f"this is {version.status.value}"
                )
                return False

            version.status = ConfigStatus.ROLLED_BACK
            version.rolled_back_at = time.time()

            # Set previous version as active
            versions = sorted(
                [v for v in self.configs[env_key].keys() if v < version_id],
                reverse=True
            )

            if versions:
                self.active_versions[env_key] = versions[0]

            self.logger.warning(
                f"Rolled back configuration for environment {environment} "
                f"from version {version_id}"
            )

            return True

        except Exception as e:
            self.logger.error(f"Error rolling back config: {e}")
            return False

    def get_config(self, environment: str,
                  version_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """
        Get configuration.

        Args:
            environment: Target environment
            version_id: Specific version, or None for active version

        Returns:
            Configuration data
        """
        try:
            env = ConfigEnvironment(environment.lower())
            env_key = env.value

            if version_id is None:
                version_id = self.active_versions[env_key]

            if version_id == 0:
                return self.default_config.copy()

            if version_id not in self.configs[env_key]:
                return None

            return self.configs[env_key][version_id].config_data.copy()

        except Exception as e:
            self.logger.error(f"Error getting config: {e}")
            return None

    def get_config_diff(self, environment: str, version_from: int,
                       version_to: int) -> Dict[str, Tuple[Any, Any]]:
        """
        Get differences between two configuration versions.

        Args:
            environment: Target environment
            version_from: Source version
            version_to: Target version

        Returns:
            Dictionary of changes {key: (old_value, new_value)}
        """
        try:
            env = ConfigEnvironment(environment.lower())
            env_key = env.value

            config_from = self.get_config(environment, version_from)
            config_to = self.get_config(environment, version_to)

            if not config_from or not config_to:
                return {}

            diff = {}

            all_keys = set(config_from.keys()) | set(config_to.keys())

            for key in all_keys:
                old_val = config_from.get(key)
                new_val = config_to.get(key)

                if old_val != new_val:
                    diff[key] = (old_val, new_val)

            return diff

        except Exception as e:
            self.logger.error(f"Error getting config diff: {e}")
            return {}

    def _validate_config(self, config_data: Dict[str, Any]) -> List[str]:
        """
        Validate configuration data.

        Args:
            config_data: Configuration to validate

        Returns:
            List of validation errors (empty if valid)
        """
        errors = []

        try:
            for key, value in config_data.items():
                if key not in self.schemas:
                    errors.append(f"Unknown configuration key: {key}")
                    continue

                expected_type = self.schemas[key]

                if expected_type == 'bool' and not isinstance(value, bool):
                    errors.append(
                        f"Configuration '{key}' must be boolean, "
                        f"got {type(value).__name__}"
                    )

                elif expected_type == 'int' and not isinstance(value, int):
                    errors.append(
                        f"Configuration '{key}' must be integer, "
                        f"got {type(value).__name__}"
                    )

                elif expected_type == 'str' and not isinstance(value, str):
                    errors.append(
                        f"Configuration '{key}' must be string, "
                        f"got {type(value).__name__}"
                    )

                # Value range validation
                if key == 'max_peers' and value > 10000:
                    errors.append("max_peers cannot exceed 10000")

                if key == 'bandwidth_limit_mbps' and value < 0:
                    errors.append("bandwidth_limit_mbps cannot be negative")

        except Exception as e:
            errors.append(f"Validation error: {str(e)}")

        return errors

    def get_config_history(self, environment: str) -> List[ConfigVersion]:
        """
        Get configuration version history.

        Args:
            environment: Target environment

        Returns:
            List of configuration versions in order
        """
        try:
            env = ConfigEnvironment(environment.lower())
            env_key = env.value

            versions = sorted(
                self.configs[env_key].values(),
                key=lambda v: v.version_id
            )

            return versions

        except Exception as e:
            self.logger.error(f"Error getting config history: {e}")
            return []

    def get_config_status(self, environment: str) -> Dict[str, Any]:
        """Get configuration status summary"""
        try:
            env = ConfigEnvironment(environment.lower())
            env_key = env.value

            active_version_id = self.active_versions[env_key]
            active_version = None

            if active_version_id > 0 and active_version_id in self.configs[env_key]:
                active_version = self.configs[env_key][active_version_id]

            return {
                'environment': env_key,
                'active_version': active_version_id,
                'total_versions': len(self.configs[env_key]),
                'pending_changes': len(self.pending_changes[env_key]),
                'active_config_status': active_version.status.value if active_version else 'none',
                'active_config_created_at': active_version.created_at if active_version else None,
                'active_config_applied_nodes': len(active_version.applied_nodes) if active_version else 0,
                'active_config_failed_nodes': len(active_version.failed_nodes) if active_version else 0
            }

        except Exception as e:
            self.logger.error(f"Error getting config status: {e}")
            return {}
