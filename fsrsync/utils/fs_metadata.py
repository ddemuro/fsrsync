"""
Filesystem Metadata Preservation

Handles extraction, mapping, and application of filesystem metadata
including permissions, ownership, ACLs, extended attributes, and more.

Features:
- Support for POSIX permissions (rwxrwxrwx + suid/sgid/sticky)
- Ownership preservation (UID/GID)
- POSIX ACLs (if filesystem supports)
- Extended attributes (xattr)
- SELinux context (if available)
- Optional forced mapping (force user, group, mode)
- Graceful fallback when features unsupported
"""

import os
import stat
import logging
from pathlib import Path
from typing import Optional, Dict, Tuple, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)


# ============================================================================
# Constants
# ============================================================================

# Permission bits
PERMISSION_MASK = 0o7777
SUID_BIT = 0o4000
SGID_BIT = 0o2000
STICKY_BIT = 0o1000


# ============================================================================
# Data Structures
# ============================================================================

@dataclass
class FileMetadata:
    """Complete filesystem metadata for a file"""

    # Standard POSIX
    mode: int                           # Permission bits (0o644, etc)
    uid: Optional[int] = None           # Owner user ID
    gid: Optional[int] = None           # Owner group ID
    mtime: Optional[float] = None       # Modification time (Unix timestamp)
    atime: Optional[float] = None       # Access time (Unix timestamp)

    # Advanced
    acls: Optional[str] = None          # POSIX ACL string (setfacl format)
    xattrs: Optional[Dict[str, bytes]] = None  # Extended attributes
    selinux_context: Optional[str] = None  # SELinux context string

    def has_suid(self) -> bool:
        """Check if SUID bit is set"""
        return bool(self.mode & SUID_BIT)

    def has_sgid(self) -> bool:
        """Check if SGID bit is set"""
        return bool(self.mode & SGID_BIT)

    def has_sticky(self) -> bool:
        """Check if sticky bit is set"""
        return bool(self.mode & STICKY_BIT)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'mode': oct(self.mode),
            'uid': self.uid,
            'gid': self.gid,
            'mtime': self.mtime,
            'atime': self.atime,
            'acls': self.acls,
            'xattrs': {k: v.hex() if v else None for k, v in (self.xattrs or {}).items()},
            'selinux_context': self.selinux_context
        }


# ============================================================================
# Metadata Extraction
# ============================================================================

class MetadataExtractor:
    """Extract filesystem metadata from files"""

    def __init__(self, logger=None):
        self.logger = logger or logging.getLogger(__name__)

    def extract(self, file_path: str) -> Optional[FileMetadata]:
        """
        Extract all available metadata from file.

        Args:
            file_path: Path to file

        Returns:
            FileMetadata object or None on error
        """
        try:
            path = Path(file_path)
            stat_info = path.lstat()  # Use lstat to handle symlinks

            metadata = FileMetadata(
                mode=stat.S_IMODE(stat_info.st_mode),
                uid=stat_info.st_uid,
                gid=stat_info.st_gid,
                mtime=stat_info.st_mtime,
                atime=stat_info.st_atime
            )

            # Extract ACLs if available
            acls = self._extract_acls(file_path)
            if acls:
                metadata.acls = acls

            # Extract extended attributes
            xattrs = self._extract_xattrs(file_path)
            if xattrs:
                metadata.xattrs = xattrs

            # Extract SELinux context if available
            selinux_context = self._extract_selinux_context(file_path)
            if selinux_context:
                metadata.selinux_context = selinux_context

            return metadata

        except Exception as e:
            self.logger.error(f"Failed to extract metadata for {file_path}: {e}")
            return None

    def _extract_acls(self, file_path: str) -> Optional[str]:
        """
        Extract POSIX ACLs from file.

        Returns:
            ACL string in setfacl format or None
        """
        try:
            import acl
            acl_obj = acl.ACL(file=file_path)
            return str(acl_obj)
        except ImportError:
            # python-acl not available
            return None
        except Exception as e:
            self.logger.debug(f"Failed to extract ACLs: {e}")
            return None

    def _extract_xattrs(self, file_path: str) -> Optional[Dict[str, bytes]]:
        """
        Extract extended attributes from file.

        Returns:
            Dict of {name: value} or None
        """
        try:
            xattrs = {}
            for name in os.listxattr(file_path, follow_symlinks=False):
                try:
                    value = os.getxattr(file_path, name, follow_symlinks=False)
                    xattrs[name] = value
                except Exception as e:
                    self.logger.debug(f"Failed to get xattr {name}: {e}")
            return xattrs if xattrs else None
        except Exception as e:
            self.logger.debug(f"Failed to extract xattrs: {e}")
            return None

    def _extract_selinux_context(self, file_path: str) -> Optional[str]:
        """
        Extract SELinux context from file.

        Returns:
            SELinux context string or None
        """
        try:
            context = os.getxattr(file_path, 'security.selinux', follow_symlinks=False)
            return context.decode('utf-8').rstrip('\x00')
        except Exception:
            return None


# ============================================================================
# Permission Mapping
# ============================================================================

class PermissionMapper:
    """
    Map permissions from source to target with optional forcing.

    Allows fine-grained control over how permissions are applied:
    - Preserve source permissions exactly
    - Force specific user/group
    - Force specific permission mode
    - Mix of above (force user, preserve group, etc)
    """

    def __init__(self, force_user: Optional[str] = None,
                 force_group: Optional[str] = None,
                 force_mode: Optional[int] = None,
                 logger=None):
        """
        Initialize permission mapper.

        Args:
            force_user: Force all files to this user (e.g., "nobody")
            force_group: Force all files to this group (e.g., "nogroup")
            force_mode: Force all files to this mode (e.g., 0o755)
            logger: Logger instance
        """
        self.force_user = force_user
        self.force_group = force_group
        self.force_mode = force_mode
        self.logger = logger or logging.getLogger(__name__)

        # Resolve forced user/group to UID/GID
        self.force_uid = self._resolve_user(force_user) if force_user else None
        self.force_gid = self._resolve_group(force_group) if force_group else None

    def _resolve_user(self, username: str) -> Optional[int]:
        """Resolve username to UID"""
        try:
            import pwd
            return pwd.getpwnam(username).pw_uid
        except Exception as e:
            self.logger.warning(f"Failed to resolve user {username}: {e}")
            return None

    def _resolve_group(self, groupname: str) -> Optional[int]:
        """Resolve groupname to GID"""
        try:
            import grp
            return grp.getgrnam(groupname).gr_gid
        except Exception as e:
            self.logger.warning(f"Failed to resolve group {groupname}: {e}")
            return None

    def map_mode(self, source_mode: int) -> int:
        """
        Map permission mode with optional forcing.

        Args:
            source_mode: Source file mode

        Returns:
            Target file mode
        """
        if self.force_mode is not None:
            return self.force_mode
        return source_mode

    def map_uid(self, source_uid: Optional[int]) -> Optional[int]:
        """
        Map UID with optional forcing.

        Args:
            source_uid: Source UID

        Returns:
            Target UID or None
        """
        if self.force_uid is not None:
            return self.force_uid
        return source_uid

    def map_gid(self, source_gid: Optional[int]) -> Optional[int]:
        """
        Map GID with optional forcing.

        Args:
            source_gid: Source GID

        Returns:
            Target GID or None
        """
        if self.force_gid is not None:
            return self.force_gid
        return source_gid


# ============================================================================
# Metadata Application
# ============================================================================

class MetadataApplier:
    """Apply filesystem metadata to files with graceful fallback"""

    def __init__(self, permission_mapper: Optional[PermissionMapper] = None, logger=None):
        """
        Initialize metadata applier.

        Args:
            permission_mapper: PermissionMapper for custom mappings
            logger: Logger instance
        """
        self.permission_mapper = permission_mapper or PermissionMapper()
        self.logger = logger or logging.getLogger(__name__)

    def apply(self, file_path: str, metadata: FileMetadata) -> bool:
        """
        Apply metadata to file with graceful fallback.

        Returns True if all metadata applied, False if some features skipped.

        Args:
            file_path: Path to file
            metadata: FileMetadata to apply

        Returns:
            True if successful (all or partial application)
        """
        try:
            path = Path(file_path)
            success = True

            # Apply permissions
            if not self._apply_mode(path, metadata.mode):
                success = False

            # Apply ownership
            if not self._apply_ownership(path, metadata.uid, metadata.gid):
                success = False

            # Apply timestamps
            if not self._apply_timestamps(path, metadata.mtime, metadata.atime):
                success = False

            # Apply ACLs
            if metadata.acls and not self._apply_acls(path, metadata.acls):
                success = False

            # Apply extended attributes
            if metadata.xattrs and not self._apply_xattrs(path, metadata.xattrs):
                success = False

            # Apply SELinux context
            if metadata.selinux_context and not self._apply_selinux(path, metadata.selinux_context):
                success = False

            return success

        except Exception as e:
            self.logger.error(f"Error applying metadata to {file_path}: {e}")
            return False

    def _apply_mode(self, path: Path, source_mode: int) -> bool:
        """Apply file permissions"""
        try:
            target_mode = self.permission_mapper.map_mode(source_mode)
            os.chmod(path, target_mode)
            self.logger.debug(f"Applied mode {oct(target_mode)} to {path}")
            return True
        except PermissionError:
            self.logger.warning(f"Permission denied setting mode on {path}")
            return False
        except Exception as e:
            self.logger.warning(f"Failed to apply mode: {e}")
            return False

    def _apply_ownership(self, path: Path, source_uid: Optional[int],
                         source_gid: Optional[int]) -> bool:
        """Apply file ownership"""
        try:
            target_uid = self.permission_mapper.map_uid(source_uid)
            target_gid = self.permission_mapper.map_gid(source_gid)

            if target_uid is None and target_gid is None:
                return True

            uid = target_uid if target_uid is not None else -1
            gid = target_gid if target_gid is not None else -1

            os.chown(path, uid, gid)
            self.logger.debug(f"Applied ownership {uid}:{gid} to {path}")
            return True
        except PermissionError:
            self.logger.warning(f"Permission denied setting ownership on {path} (not root)")
            return False
        except Exception as e:
            self.logger.warning(f"Failed to apply ownership: {e}")
            return False

    def _apply_timestamps(self, path: Path, mtime: Optional[float],
                          atime: Optional[float]) -> bool:
        """Apply file timestamps"""
        try:
            if mtime is None and atime is None:
                return True

            # Use mtime for both if atime not provided
            access_time = atime if atime is not None else mtime
            os.utime(path, (access_time, mtime))
            self.logger.debug(f"Applied timestamps to {path}")
            return True
        except Exception as e:
            self.logger.warning(f"Failed to apply timestamps: {e}")
            return False

    def _apply_acls(self, path: Path, acl_string: str) -> bool:
        """Apply POSIX ACLs"""
        try:
            import acl
            acl_obj = acl.ACL(text=acl_string)
            acl_obj.applyto(str(path))
            self.logger.debug(f"Applied ACLs to {path}")
            return True
        except ImportError:
            self.logger.debug("python-acl not available, skipping ACLs")
            return False
        except Exception as e:
            self.logger.warning(f"Failed to apply ACLs: {e}")
            return False

    def _apply_xattrs(self, path: Path, xattrs: Dict[str, bytes]) -> bool:
        """Apply extended attributes"""
        try:
            for name, value in xattrs.items():
                try:
                    os.setxattr(path, name, value, follow_symlinks=False)
                except Exception as e:
                    self.logger.debug(f"Failed to set xattr {name}: {e}")
            self.logger.debug(f"Applied xattrs to {path}")
            return True
        except Exception as e:
            self.logger.warning(f"Failed to apply xattrs: {e}")
            return False

    def _apply_selinux(self, path: Path, context: str) -> bool:
        """Apply SELinux context"""
        try:
            os.setxattr(path, 'security.selinux', context.encode('utf-8'),
                       follow_symlinks=False)
            self.logger.debug(f"Applied SELinux context to {path}")
            return True
        except PermissionError:
            self.logger.warning(f"Permission denied setting SELinux context (not root)")
            return False
        except Exception as e:
            self.logger.debug(f"Failed to apply SELinux context: {e}")
            return False


# ============================================================================
# Helper Functions
# ============================================================================

def extract_metadata(file_path: str) -> Optional[FileMetadata]:
    """
    Extract metadata from file.

    Args:
        file_path: Path to file

    Returns:
        FileMetadata or None
    """
    extractor = MetadataExtractor()
    return extractor.extract(file_path)


def apply_metadata(file_path: str, metadata: FileMetadata,
                  force_user: Optional[str] = None,
                  force_group: Optional[str] = None,
                  force_mode: Optional[int] = None) -> bool:
    """
    Apply metadata to file with optional forcing.

    Args:
        file_path: Path to file
        metadata: FileMetadata to apply
        force_user: Force user (optional)
        force_group: Force group (optional)
        force_mode: Force mode (optional)

    Returns:
        True if successful
    """
    mapper = PermissionMapper(force_user, force_group, force_mode)
    applier = MetadataApplier(mapper)
    return applier.apply(file_path, metadata)


def get_user_name(uid: int) -> Optional[str]:
    """Get username for UID"""
    try:
        import pwd
        return pwd.getpwuid(uid).pw_name
    except:
        return None


def get_group_name(gid: int) -> Optional[str]:
    """Get groupname for GID"""
    try:
        import grp
        return grp.getgrgid(gid).gr_name
    except:
        return None
