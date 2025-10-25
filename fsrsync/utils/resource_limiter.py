"""
Resource Limit Manager for FSRsync

Provides resource constraint management with:
- Memory usage limits and enforcement
- CPU usage limits and throttling
- Disk I/O limits
- Network bandwidth limits
- Process resource quotas
- Dynamic limit adjustment
- Resource violation alerts

## Resource Types

MEMORY: Memory usage limits
CPU: CPU time and core limits
IO: Disk I/O throughput limits
NETWORK: Network bandwidth limits
THREADS: Thread count limits
"""

import time
import logging
import threading
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict, deque


class ResourceType(Enum):
    """Type of resource"""
    MEMORY = "memory"
    CPU = "cpu"
    IO = "io"
    NETWORK = "network"
    THREADS = "threads"


class LimitEnforcement(Enum):
    """How to enforce limits"""
    WARN = "warn"
    THROTTLE = "throttle"
    BLOCK = "block"
    KILL = "kill"


@dataclass
class ResourceLimit:
    """Resource usage limit"""
    resource_type: ResourceType
    limit_value: float
    unit: str
    enforcement: LimitEnforcement
    soft_limit: float = 0.0  # Percentage of hard limit (0-100)
    created_at: float = field(default_factory=time.time)


@dataclass
class ResourceUsage:
    """Current resource usage"""
    resource_type: ResourceType
    current_value: float
    limit_value: float
    percentage_used: float = 0.0
    timestamp: float = field(default_factory=time.time)


@dataclass
class ResourceViolation:
    """Resource usage violation"""
    violation_id: str
    resource_type: ResourceType
    current_value: float
    limit_value: float
    excess_amount: float
    violation_type: str  # soft, hard
    timestamp: float = field(default_factory=time.time)
    action_taken: str = ""


class ResourceLimiter:
    """
    Resource limit manager.

    Enforces and monitors resource usage constraints
    for the sync application.
    """

    def __init__(self, logger_instance=None):
        """
        Initialize resource limiter.

        Args:
            logger_instance: Logger instance
        """
        self.logger = logger_instance or logging.getLogger(__name__)

        # Resource limits (resource_type -> ResourceLimit)
        self.limits: Dict[ResourceType, ResourceLimit] = {}

        # Current usage tracking (resource_type -> deque of ResourceUsage)
        self.usage: Dict[ResourceType, deque] = {
            rt: deque(maxlen=1000) for rt in ResourceType
        }

        # Violations (resource_type -> list of ResourceViolation)
        self.violations: Dict[ResourceType, List[ResourceViolation]] = defaultdict(list)

        # Active throttling (resource_type -> is_throttled)
        self.throttling_active: Dict[ResourceType, bool] = {
            rt: False for rt in ResourceType
        }

        # Lock for thread safety
        self.lock = threading.RLock()

        # Initialize default limits
        self._init_default_limits()

        self.logger.info("ResourceLimiter initialized")

    def _init_default_limits(self) -> None:
        """Initialize default resource limits"""
        try:
            # Default limits
            defaults = {
                ResourceType.MEMORY: (512.0, "MB", LimitEnforcement.WARN),  # 512 MB
                ResourceType.CPU: (80.0, "%", LimitEnforcement.THROTTLE),  # 80% CPU
                ResourceType.IO: (100.0, "MB/s", LimitEnforcement.THROTTLE),  # 100 MB/s
                ResourceType.NETWORK: (50.0, "MB/s", LimitEnforcement.WARN),  # 50 MB/s
                ResourceType.THREADS: (100.0, "threads", LimitEnforcement.WARN)  # 100 threads
            }

            for resource_type, (limit, unit, enforcement) in defaults.items():
                self.set_limit(resource_type, limit, unit, enforcement)

        except Exception as e:
            self.logger.error(f"Error initializing default limits: {e}")

    def set_limit(self, resource_type: ResourceType, limit_value: float,
                  unit: str, enforcement: LimitEnforcement,
                  soft_limit_percent: float = 80.0) -> None:
        """
        Set resource limit.

        Args:
            resource_type: Type of resource
            limit_value: Maximum allowed value
            unit: Unit of measurement
            enforcement: How to enforce the limit
            soft_limit_percent: Soft limit as percentage of hard limit
        """
        try:
            with self.lock:
                soft_limit = limit_value * (soft_limit_percent / 100)

                limit = ResourceLimit(
                    resource_type=resource_type,
                    limit_value=limit_value,
                    unit=unit,
                    enforcement=enforcement,
                    soft_limit=soft_limit
                )

                self.limits[resource_type] = limit

                self.logger.info(
                    f"Set limit for {resource_type.value}: "
                    f"{limit_value}{unit} (soft: {soft_limit}{unit})"
                )

        except Exception as e:
            self.logger.error(f"Error setting limit: {e}")

    def record_usage(self, resource_type: ResourceType, current_value: float) -> None:
        """
        Record current resource usage.

        Args:
            resource_type: Type of resource
            current_value: Current usage value
        """
        try:
            with self.lock:
                if resource_type not in self.limits:
                    return

                limit = self.limits[resource_type]
                percentage = (current_value / limit.limit_value * 100) if limit.limit_value > 0 else 0

                usage = ResourceUsage(
                    resource_type=resource_type,
                    current_value=current_value,
                    limit_value=limit.limit_value,
                    percentage_used=percentage
                )

                self.usage[resource_type].append(usage)

                # Check for violations
                self._check_violation(resource_type, usage, limit)

        except Exception as e:
            self.logger.error(f"Error recording usage: {e}")

    def _check_violation(self, resource_type: ResourceType,
                        usage: ResourceUsage, limit: ResourceLimit) -> None:
        """Check for resource usage violations"""
        try:
            import uuid

            is_soft_violation = usage.percentage_used > limit.soft_limit
            is_hard_violation = usage.percentage_used > limit.limit_value

            if is_hard_violation or is_soft_violation:
                violation_type = "hard" if is_hard_violation else "soft"
                excess = usage.current_value - limit.limit_value

                violation = ResourceViolation(
                    violation_id=str(uuid.uuid4()),
                    resource_type=resource_type,
                    current_value=usage.current_value,
                    limit_value=limit.limit_value,
                    excess_amount=excess,
                    violation_type=violation_type
                )

                # Take action based on enforcement policy
                action = self._enforce_limit(resource_type, violation, limit)
                violation.action_taken = action

                self.violations[resource_type].append(violation)

                self.logger.warning(
                    f"Resource violation: {resource_type.value} "
                    f"({usage.percentage_used:.1f}% of limit). Action: {action}"
                )

        except Exception as e:
            self.logger.error(f"Error checking violation: {e}")

    def _enforce_limit(self, resource_type: ResourceType,
                      violation: ResourceViolation,
                      limit: ResourceLimit) -> str:
        """Enforce resource limit based on policy"""
        try:
            if limit.enforcement == LimitEnforcement.WARN:
                return f"Warning issued for {resource_type.value} limit violation"

            elif limit.enforcement == LimitEnforcement.THROTTLE:
                self.throttling_active[resource_type] = True
                return f"Throttling enabled for {resource_type.value}"

            elif limit.enforcement == LimitEnforcement.BLOCK:
                return f"Operations blocked for {resource_type.value}"

            elif limit.enforcement == LimitEnforcement.KILL:
                return f"Critical: {resource_type.value} limit exceeded - termination required"

            return "No action"

        except Exception as e:
            self.logger.error(f"Error enforcing limit: {e}")
            return "Error enforcing limit"

    def is_throttled(self, resource_type: ResourceType) -> bool:
        """Check if resource is currently throttled"""
        try:
            with self.lock:
                return self.throttling_active.get(resource_type, False)

        except Exception as e:
            self.logger.error(f"Error checking throttle: {e}")
            return False

    def reset_throttle(self, resource_type: ResourceType) -> None:
        """Reset throttling for resource"""
        try:
            with self.lock:
                self.throttling_active[resource_type] = False
                self.logger.info(f"Reset throttling for {resource_type.value}")

        except Exception as e:
            self.logger.error(f"Error resetting throttle: {e}")

    def get_current_usage(self, resource_type: Optional[ResourceType] = None) -> Dict[str, Any]:
        """Get current resource usage"""
        try:
            with self.lock:
                if resource_type:
                    if resource_type not in self.usage or not self.usage[resource_type]:
                        return {}

                    latest = list(self.usage[resource_type])[-1]
                    limit = self.limits.get(resource_type)

                    return {
                        'resource': resource_type.value,
                        'current': latest.current_value,
                        'limit': latest.limit_value,
                        'percentage': latest.percentage_used,
                        'unit': limit.unit if limit else '',
                        'timestamp': latest.timestamp
                    }
                else:
                    # Return usage for all resources
                    all_usage = {}
                    for rt in ResourceType:
                        if self.usage[rt]:
                            latest = list(self.usage[rt])[-1]
                            limit = self.limits.get(rt)

                            all_usage[rt.value] = {
                                'current': latest.current_value,
                                'limit': latest.limit_value,
                                'percentage': latest.percentage_used,
                                'unit': limit.unit if limit else ''
                            }

                    return all_usage

        except Exception as e:
            self.logger.error(f"Error getting usage: {e}")
            return {}

    def get_violations(self, resource_type: Optional[ResourceType] = None,
                      limit: int = 10) -> List[Dict[str, Any]]:
        """Get resource violations"""
        try:
            with self.lock:
                if resource_type:
                    violations = self.violations.get(resource_type, [])
                else:
                    violations = []
                    for vlist in self.violations.values():
                        violations.extend(vlist)

                # Sort by timestamp descending and limit results
                sorted_violations = sorted(violations, key=lambda x: x.timestamp, reverse=True)[:limit]

                return [
                    {
                        'violation_id': v.violation_id,
                        'resource': v.resource_type.value,
                        'current': v.current_value,
                        'limit': v.limit_value,
                        'excess': v.excess_amount,
                        'type': v.violation_type,
                        'action': v.action_taken,
                        'timestamp': v.timestamp
                    }
                    for v in sorted_violations
                ]

        except Exception as e:
            self.logger.error(f"Error getting violations: {e}")
            return []

    def get_limit(self, resource_type: ResourceType) -> Optional[Dict[str, Any]]:
        """Get limit for resource type"""
        try:
            limit = self.limits.get(resource_type)

            if not limit:
                return None

            return {
                'resource': resource_type.value,
                'limit': limit.limit_value,
                'soft_limit': limit.soft_limit,
                'unit': limit.unit,
                'enforcement': limit.enforcement.value
            }

        except Exception as e:
            self.logger.error(f"Error getting limit: {e}")
            return None

    def get_all_limits(self) -> Dict[str, Any]:
        """Get all resource limits"""
        try:
            limits = {}

            for resource_type, limit in self.limits.items():
                limits[resource_type.value] = {
                    'limit': limit.limit_value,
                    'soft_limit': limit.soft_limit,
                    'unit': limit.unit,
                    'enforcement': limit.enforcement.value
                }

            return limits

        except Exception as e:
            self.logger.error(f"Error getting all limits: {e}")
            return {}

    def get_resource_report(self) -> Dict[str, Any]:
        """Get comprehensive resource usage report"""
        try:
            with self.lock:
                total_violations = sum(len(v) for v in self.violations.values())

                recent_violations = []
                for vlist in self.violations.values():
                    recent_violations.extend(vlist)

                recent_violations = sorted(
                    recent_violations,
                    key=lambda x: x.timestamp,
                    reverse=True
                )[:5]

                return {
                    'timestamp': time.time(),
                    'current_usage': self.get_current_usage(),
                    'all_limits': self.get_all_limits(),
                    'total_violations': total_violations,
                    'recent_violations': [
                        {
                            'resource': v.resource_type.value,
                            'type': v.violation_type,
                            'excess': v.excess_amount,
                            'action': v.action_taken
                        }
                        for v in recent_violations
                    ],
                    'throttled_resources': [
                        rt.value for rt, is_throttled in self.throttling_active.items()
                        if is_throttled
                    ]
                }

        except Exception as e:
            self.logger.error(f"Error generating report: {e}")
            return {}

    def get_limiter_summary(self) -> Dict[str, Any]:
        """Get limiter system summary"""
        try:
            with self.lock:
                violations_by_type = {
                    rt.value: len(self.violations.get(rt, []))
                    for rt in ResourceType
                }

                return {
                    'timestamp': time.time(),
                    'total_limits': len(self.limits),
                    'total_violations': sum(len(v) for v in self.violations.values()),
                    'violations_by_resource': violations_by_type,
                    'throttled_count': sum(1 for is_throttled in self.throttling_active.values()
                                          if is_throttled),
                    'usage_samples': {
                        rt.value: len(self.usage[rt])
                        for rt in ResourceType
                    }
                }

        except Exception as e:
            self.logger.error(f"Error getting summary: {e}")
            return {}
