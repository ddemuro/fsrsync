"""
Role-Based Access Control (RBAC) System for FSRsync

Provides comprehensive permission management with:
- Role definitions with hierarchies
- Permission assignment to roles
- User role assignment
- Resource-level access control
- Dynamic permission evaluation
- Audit trail for permission changes

## Built-in Roles

ADMIN: Full system access
OPERATOR: Can manage sync operations
VIEWER: Read-only access
GUEST: Limited read access

## Permission Categories

SYNC: File synchronization operations
PEER: Peer management operations
CONFIG: Configuration changes
AUDIT: Audit log access
USERS: User management
"""

import logging
import time
from typing import Set, Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum


class BuiltInRole(Enum):
    """Built-in roles"""
    ADMIN = "admin"
    OPERATOR = "operator"
    VIEWER = "viewer"
    GUEST = "guest"


class Permission(Enum):
    """Permission types"""
    # Sync permissions
    SYNC_START = "sync:start"
    SYNC_STOP = "sync:stop"
    SYNC_PAUSE = "sync:pause"
    SYNC_VIEW = "sync:view"

    # Peer permissions
    PEER_ADD = "peer:add"
    PEER_REMOVE = "peer:remove"
    PEER_VIEW = "peer:view"
    PEER_CONFIGURE = "peer:configure"

    # Config permissions
    CONFIG_READ = "config:read"
    CONFIG_WRITE = "config:write"
    BANDWIDTH_LIMIT = "config:bandwidth_limit"
    CONFLICT_RESOLUTION = "config:conflict_resolution"

    # Audit permissions
    AUDIT_VIEW = "audit:view"
    AUDIT_EXPORT = "audit:export"

    # User permissions
    USER_CREATE = "user:create"
    USER_DELETE = "user:delete"
    USER_MODIFY = "user:modify"
    USER_VIEW = "user:view"


@dataclass
class Role:
    """Role definition"""
    role_id: str
    name: str
    description: str
    permissions: Set[Permission] = field(default_factory=set)
    parent_role: Optional[str] = None  # For role inheritance
    created_at: float = field(default_factory=time.time)
    modified_at: float = field(default_factory=time.time)


@dataclass
class UserRole:
    """User role assignment"""
    user_id: str
    role_id: str
    assigned_at: float = field(default_factory=time.time)
    assigned_by: Optional[str] = None
    expires_at: Optional[float] = None

    @property
    def is_expired(self) -> bool:
        """Check if role assignment is expired"""
        if self.expires_at is None:
            return False
        return time.time() > self.expires_at


class RBACManager:
    """
    Role-Based Access Control manager for FSRsync.
    
    Manages user roles, permissions, and access control
    with hierarchical role support and permission inheritance.
    """

    def __init__(self, logger_instance=None):
        """Initialize RBAC manager"""
        self.logger = logger_instance or logging.getLogger(__name__)
        self.roles: Dict[str, Role] = {}
        self.user_roles: Dict[str, List[UserRole]] = {}
        self._initialize_builtin_roles()
        self.logger.info("RBACManager initialized")

    def _initialize_builtin_roles(self) -> None:
        """Initialize built-in roles"""
        # Admin role - full access
        admin_role = Role(
            role_id=BuiltInRole.ADMIN.value,
            name="Administrator",
            description="Full system access",
            permissions=set(Permission)  # All permissions
        )
        self.roles[admin_role.role_id] = admin_role

        # Operator role - manage operations
        operator_perms = {
            Permission.SYNC_START, Permission.SYNC_STOP, Permission.SYNC_PAUSE,
            Permission.SYNC_VIEW, Permission.PEER_VIEW, Permission.CONFIG_READ,
            Permission.BANDWIDTH_LIMIT, Permission.CONFLICT_RESOLUTION,
            Permission.AUDIT_VIEW
        }
        operator_role = Role(
            role_id=BuiltInRole.OPERATOR.value,
            name="Operator",
            description="Manage sync operations",
            permissions=operator_perms,
            parent_role=BuiltInRole.ADMIN.value
        )
        self.roles[operator_role.role_id] = operator_role

        # Viewer role - read-only
        viewer_perms = {
            Permission.SYNC_VIEW, Permission.PEER_VIEW, Permission.CONFIG_READ,
            Permission.AUDIT_VIEW
        }
        viewer_role = Role(
            role_id=BuiltInRole.VIEWER.value,
            name="Viewer",
            description="Read-only access",
            permissions=viewer_perms,
            parent_role=BuiltInRole.OPERATOR.value
        )
        self.roles[viewer_role.role_id] = viewer_role

        # Guest role - limited access
        guest_perms = {
            Permission.SYNC_VIEW, Permission.PEER_VIEW
        }
        guest_role = Role(
            role_id=BuiltInRole.GUEST.value,
            name="Guest",
            description="Limited read access",
            permissions=guest_perms,
            parent_role=BuiltInRole.VIEWER.value
        )
        self.roles[guest_role.role_id] = guest_role

        self.logger.info("Built-in roles initialized")

    def create_role(self, role_id: str, name: str, description: str,
                   permissions: Optional[Set[Permission]] = None) -> bool:
        """
        Create custom role.
        
        Args:
            role_id: Unique role identifier
            name: Role name
            description: Role description
            permissions: Set of permissions
            
        Returns:
            True if created successfully
        """
        try:
            if role_id in self.roles:
                self.logger.warning(f"Role {role_id} already exists")
                return False

            role = Role(
                role_id=role_id,
                name=name,
                description=description,
                permissions=permissions or set()
            )

            self.roles[role_id] = role
            self.logger.info(f"Created role: {role_id}")
            return True

        except Exception as e:
            self.logger.error(f"Error creating role: {e}")
            return False

    def assign_role(self, user_id: str, role_id: str,
                   expires_in: Optional[int] = None,
                   assigned_by: Optional[str] = None) -> bool:
        """
        Assign role to user.
        
        Args:
            user_id: User identifier
            role_id: Role identifier
            expires_in: Expiration in seconds (None = no expiration)
            assigned_by: Admin who assigned the role
            
        Returns:
            True if assigned successfully
        """
        try:
            if role_id not in self.roles:
                self.logger.warning(f"Role {role_id} does not exist")
                return False

            expires_at = None
            if expires_in:
                expires_at = time.time() + expires_in

            user_role = UserRole(
                user_id=user_id,
                role_id=role_id,
                expires_at=expires_at,
                assigned_by=assigned_by
            )

            if user_id not in self.user_roles:
                self.user_roles[user_id] = []

            self.user_roles[user_id].append(user_role)
            self.logger.info(f"Assigned role {role_id} to user {user_id}")
            return True

        except Exception as e:
            self.logger.error(f"Error assigning role: {e}")
            return False

    def revoke_role(self, user_id: str, role_id: str) -> bool:
        """
        Revoke role from user.
        
        Args:
            user_id: User identifier
            role_id: Role identifier
            
        Returns:
            True if revoked successfully
        """
        try:
            if user_id not in self.user_roles:
                return False

            self.user_roles[user_id] = [
                ur for ur in self.user_roles[user_id]
                if ur.role_id != role_id
            ]

            self.logger.info(f"Revoked role {role_id} from user {user_id}")
            return True

        except Exception as e:
            self.logger.error(f"Error revoking role: {e}")
            return False

    def has_permission(self, user_id: str, permission: Permission) -> bool:
        """
        Check if user has permission.
        
        Args:
            user_id: User identifier
            permission: Permission to check
            
        Returns:
            True if user has permission
        """
        try:
            if user_id not in self.user_roles:
                return False

            for user_role in self.user_roles[user_id]:
                # Skip expired roles
                if user_role.is_expired:
                    continue

                role = self.roles.get(user_role.role_id)
                if not role:
                    continue

                # Check direct permission
                if permission in role.permissions:
                    return True

                # Check inherited permissions
                if self._has_inherited_permission(role, permission):
                    return True

            return False

        except Exception as e:
            self.logger.error(f"Error checking permission: {e}")
            return False

    def _has_inherited_permission(self, role: Role, permission: Permission) -> bool:
        """Check if permission is inherited from parent role"""
        if not role.parent_role:
            return False

        parent = self.roles.get(role.parent_role)
        if not parent:
            return False

        if permission in parent.permissions:
            return True

        return self._has_inherited_permission(parent, permission)

    def get_user_permissions(self, user_id: str) -> Set[Permission]:
        """Get all permissions for user"""
        try:
            permissions = set()

            if user_id not in self.user_roles:
                return permissions

            for user_role in self.user_roles[user_id]:
                if user_role.is_expired:
                    continue

                role = self.roles.get(user_role.role_id)
                if role:
                    permissions.update(role.permissions)
                    permissions.update(self._get_inherited_permissions(role))

            return permissions

        except Exception as e:
            self.logger.error(f"Error getting user permissions: {e}")
            return set()

    def _get_inherited_permissions(self, role: Role) -> Set[Permission]:
        """Get permissions inherited from parent roles"""
        permissions = set()

        if not role.parent_role:
            return permissions

        parent = self.roles.get(role.parent_role)
        if not parent:
            return permissions

        permissions.update(parent.permissions)
        permissions.update(self._get_inherited_permissions(parent))

        return permissions

    def get_user_roles(self, user_id: str) -> List[str]:
        """Get roles assigned to user"""
        try:
            if user_id not in self.user_roles:
                return []

            return [
                ur.role_id for ur in self.user_roles[user_id]
                if not ur.is_expired
            ]

        except Exception as e:
            self.logger.error(f"Error getting user roles: {e}")
            return []

    def get_rbac_status(self) -> Dict[str, any]:
        """Get RBAC system status"""
        active_assignments = sum(
            len([ur for ur in roles if not ur.is_expired])
            for roles in self.user_roles.values()
        )

        return {
            'total_roles': len(self.roles),
            'total_users': len(self.user_roles),
            'active_assignments': active_assignments,
            'builtin_roles': len([r for r in self.roles.values() 
                                 if r.role_id in [br.value for br in BuiltInRole]]),
            'custom_roles': len([r for r in self.roles.values() 
                               if r.role_id not in [br.value for br in BuiltInRole]])
        }
