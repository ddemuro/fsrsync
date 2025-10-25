"""
Distributed Conflict Resolver

Resolves conflicts in multi-host synchronization through multiple strategies:

1. LAST_WRITE_WINS: Newer modification timestamp wins
2. HOST_PRIORITY: Admin-configured host preferences
3. SIZE_WINS: Larger file size wins (safer for partial writes)
4. HASH_BASED: Content hash determines winner
5. MANUAL: Flag for human review

Why Conflicts Occur:

In distributed systems, conflicts happen when:
- Same file modified on multiple hosts before sync
- Network partitions create islands of change
- High-latency links cause delayed updates
- Concurrent edits without strong consistency

Example Conflict:

Host A: Modifies report.pdf at 10:00:00 (v1)
Host B: Modifies report.pdf at 10:00:05 (v2)
Network: Delays sync by 5 minutes

When A and B sync:
- Both have conflicting versions
- A thinks it's newer (local bias)
- B thinks it's newer (local bias)
- Need distributed resolver

Resolution Process:

1. Detect Conflict
   - Compare version vectors
   - Check for concurrent modifications
   - Flag if neither happened-before the other

2. Collect Information
   - Get both file versions
   - Extract timestamps, sizes, hashes
   - Check operation history

3. Apply Strategy
   - Use configured strategy
   - Calculate winner deterministically
   - Log resolution for audit trail

4. Apply Resolution
   - Keep winning version
   - Update both hosts
   - Update journals
   - Record resolution metadata

Strategies Explained:

LAST_WRITE_WINS:
- Uses file modification time
- "Newer is better"
- Fast, deterministic
- Risk: User may have intentionally reverted file

HOST_PRIORITY:
- Admin specifies preference order
- Example: primary host wins conflicts
- Deterministic but inflexible
- Good for clear authority models

SIZE_WINS:
- Larger file wins
- Prevents accidental data loss from truncation
- Good for binary files
- May not be correct for code (smaller might be buggy)

HASH_BASED:
- Uses content hash lexicographic comparison
- Deterministic (same hash always wins)
- Symmetric (both hosts pick same winner)
- No human input needed

MANUAL:
- Flag conflict for human review
- Used when automated resolution risky
- Can escalate to administrator
- Good for critical files

Metadata Preservation:

When resolving conflicts, preserve:
- All version information
- Timestamps from both versions
- Hash of losing version
- Who had which version
- When conflict was detected
- How it was resolved

This allows:
- Audit trail for compliance
- Recovery of "lost" versions
- Analysis of conflict patterns
- Manual override if needed

Conflict Avoidance:

Best practices to minimize conflicts:
1. Sync frequently (smaller windows for conflicts)
2. Use centralized coordinator (primary host decides)
3. Assign exclusive regions (Host A: /clients/*, Host B: /servers/*)
4. Locking protocol (file locked during edit)
5. CRDT-style data structures (for text files)
"""

import logging
import time
from enum import Enum
from typing import Dict, Optional, Any, Tuple
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


# ============================================================================
# Conflict Resolution Strategies
# ============================================================================

class ResolutionStrategy(Enum):
    """Strategy for resolving conflicts"""
    LAST_WRITE_WINS = "LAST_WRITE_WINS"
    HOST_PRIORITY = "HOST_PRIORITY"
    SIZE_WINS = "SIZE_WINS"
    HASH_BASED = "HASH_BASED"
    MANUAL = "MANUAL"


@dataclass
class FileVersion:
    """A version of a file in a conflict"""
    hostname: str
    path: str
    mtime: float
    size: int
    content_hash: str
    permissions: int = 0o644
    version_vector: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'hostname': self.hostname,
            'path': self.path,
            'mtime': self.mtime,
            'size': self.size,
            'content_hash': self.content_hash,
            'permissions': self.permissions,
            'version_vector': self.version_vector
        }


@dataclass
class ConflictResolution:
    """Resolution of a conflict"""
    file_path: str
    winning_version: FileVersion
    losing_version: FileVersion
    strategy: ResolutionStrategy
    resolved_at: float = field(default_factory=time.time)
    reason: str = ""
    confidence: float = 1.0  # 0.0-1.0, how confident in resolution

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'file_path': self.file_path,
            'winning_version': self.winning_version.to_dict(),
            'losing_version': self.losing_version.to_dict(),
            'strategy': self.strategy.value,
            'resolved_at': self.resolved_at,
            'reason': self.reason,
            'confidence': self.confidence
        }


# ============================================================================
# Conflict Resolver
# ============================================================================

class ConflictResolver:
    """
    Resolves file conflicts in distributed synchronization.
    """

    def __init__(self, hostname: str, logger=None,
                 default_strategy: ResolutionStrategy = ResolutionStrategy.LAST_WRITE_WINS,
                 host_priorities: Optional[Dict[str, int]] = None):
        """
        Initialize conflict resolver.

        Args:
            hostname: This host's name
            logger: Logger instance
            default_strategy: Default resolution strategy
            host_priorities: Host preference order (lower = higher priority)
        """
        self.hostname = hostname
        self.logger = logger or logging.getLogger(__name__)
        self.default_strategy = default_strategy
        self.host_priorities = host_priorities or {}
        self.resolutions: Dict[str, ConflictResolution] = {}

    def resolve(self, file_path: str, version1: FileVersion, version2: FileVersion,
               strategy: Optional[ResolutionStrategy] = None) -> ConflictResolution:
        """
        Resolve conflict between two file versions.

        Args:
            file_path: Path of file with conflict
            version1: First version
            version2: Second version
            strategy: Resolution strategy (uses default if not provided)

        Returns:
            ConflictResolution with winner
        """
        strategy = strategy or self.default_strategy

        if strategy == ResolutionStrategy.LAST_WRITE_WINS:
            resolution = self._resolve_last_write_wins(file_path, version1, version2)
        elif strategy == ResolutionStrategy.HOST_PRIORITY:
            resolution = self._resolve_host_priority(file_path, version1, version2)
        elif strategy == ResolutionStrategy.SIZE_WINS:
            resolution = self._resolve_size_wins(file_path, version1, version2)
        elif strategy == ResolutionStrategy.HASH_BASED:
            resolution = self._resolve_hash_based(file_path, version1, version2)
        else:  # MANUAL
            resolution = self._resolve_manual(file_path, version1, version2)

        resolution.strategy = strategy
        self.resolutions[file_path] = resolution

        self.logger.info(f"Resolved conflict: {file_path} → {resolution.winning_version.hostname} "
                        f"(strategy: {strategy.value}, confidence: {resolution.confidence:.2f})")

        return resolution

    def _resolve_last_write_wins(self, file_path: str,
                                version1: FileVersion,
                                version2: FileVersion) -> ConflictResolution:
        """Resolve using last write timestamp"""
        if version1.mtime > version2.mtime:
            winner = version1
            loser = version2
            reason = f"Newer mtime: {version1.mtime:.1f} > {version2.mtime:.1f}"
        elif version2.mtime > version1.mtime:
            winner = version2
            loser = version1
            reason = f"Newer mtime: {version2.mtime:.1f} > {version1.mtime:.1f}"
        else:
            # Same timestamp - use hostname (deterministic tiebreaker)
            if version1.hostname < version2.hostname:
                winner = version1
                loser = version2
            else:
                winner = version2
                loser = version1
            reason = f"Same mtime ({version1.mtime:.1f}), sorted by hostname"
            confidence = 0.5  # Low confidence on tiebreak

        return ConflictResolution(
            file_path=file_path,
            winning_version=winner,
            losing_version=loser,
            strategy=ResolutionStrategy.LAST_WRITE_WINS,
            reason=reason,
            confidence=1.0 if version1.mtime != version2.mtime else 0.5
        )

    def _resolve_host_priority(self, file_path: str,
                              version1: FileVersion,
                              version2: FileVersion) -> ConflictResolution:
        """Resolve using configured host priorities"""
        priority1 = self.host_priorities.get(version1.hostname, 999)
        priority2 = self.host_priorities.get(version2.hostname, 999)

        if priority1 < priority2:
            winner = version1
            loser = version2
            reason = f"{version1.hostname} has higher priority ({priority1} < {priority2})"
        elif priority2 < priority1:
            winner = version2
            loser = version1
            reason = f"{version2.hostname} has higher priority ({priority2} < {priority1})"
        else:
            # Same priority - fallback to mtime
            return self._resolve_last_write_wins(file_path, version1, version2)

        return ConflictResolution(
            file_path=file_path,
            winning_version=winner,
            losing_version=loser,
            strategy=ResolutionStrategy.HOST_PRIORITY,
            reason=reason,
            confidence=1.0
        )

    def _resolve_size_wins(self, file_path: str,
                          version1: FileVersion,
                          version2: FileVersion) -> ConflictResolution:
        """Resolve using file size (larger wins)"""
        if version1.size > version2.size:
            winner = version1
            loser = version2
            reason = f"Larger size: {version1.size} > {version2.size} bytes"
        elif version2.size > version1.size:
            winner = version2
            loser = version1
            reason = f"Larger size: {version2.size} > {version1.size} bytes"
        else:
            # Same size - fallback to mtime
            return self._resolve_last_write_wins(file_path, version1, version2)

        return ConflictResolution(
            file_path=file_path,
            winning_version=winner,
            losing_version=loser,
            strategy=ResolutionStrategy.SIZE_WINS,
            reason=reason,
            confidence=0.8 if version1.size != version2.size else 0.5
        )

    def _resolve_hash_based(self, file_path: str,
                           version1: FileVersion,
                           version2: FileVersion) -> ConflictResolution:
        """Resolve using content hash lexicographic comparison"""
        if version1.content_hash >= version2.content_hash:
            winner = version1
            loser = version2
            reason = f"Hash {version1.content_hash[:8]}... >= {version2.content_hash[:8]}..."
        else:
            winner = version2
            loser = version1
            reason = f"Hash {version2.content_hash[:8]}... > {version1.content_hash[:8]}..."

        return ConflictResolution(
            file_path=file_path,
            winning_version=winner,
            losing_version=loser,
            strategy=ResolutionStrategy.HASH_BASED,
            reason=reason,
            confidence=1.0  # Deterministic
        )

    def _resolve_manual(self, file_path: str,
                       version1: FileVersion,
                       version2: FileVersion) -> ConflictResolution:
        """Mark for manual review"""
        # Default to version1 as placeholder
        return ConflictResolution(
            file_path=file_path,
            winning_version=version1,
            losing_version=version2,
            strategy=ResolutionStrategy.MANUAL,
            reason="Flagged for manual review",
            confidence=0.0  # No confidence in auto-resolution
        )

    def get_resolution(self, file_path: str) -> Optional[ConflictResolution]:
        """Get resolution for file"""
        return self.resolutions.get(file_path)

    def list_resolutions(self) -> list:
        """List all resolutions"""
        return list(self.resolutions.values())

    def get_unresolved_conflicts(self) -> list:
        """Get conflicts flagged for manual review"""
        return [r for r in self.resolutions.values()
                if r.strategy == ResolutionStrategy.MANUAL]

    def clear_resolutions(self) -> None:
        """Clear all resolutions"""
        self.resolutions.clear()

    def get_conflict_statistics(self) -> Dict[str, Any]:
        """Get statistics about conflicts"""
        total = len(self.resolutions)
        manual = len(self.get_unresolved_conflicts())

        strategy_counts = {}
        for resolution in self.resolutions.values():
            strategy = resolution.strategy.value
            strategy_counts[strategy] = strategy_counts.get(strategy, 0) + 1

        avg_confidence = (
            sum(r.confidence for r in self.resolutions.values()) / total
            if total > 0 else 0.0
        )

        return {
            'total_conflicts': total,
            'manual_review': manual,
            'auto_resolved': total - manual,
            'average_confidence': avg_confidence,
            'by_strategy': strategy_counts
        }


# ============================================================================
# Conflict Avoidance Strategies
# ============================================================================

class ConflictAvoidanceStrategy:
    """
    Helps avoid conflicts through exclusivity regions.
    """

    def __init__(self, hostname: str, logger=None):
        """
        Initialize strategy.

        Args:
            hostname: This host's name
            logger: Logger instance
        """
        self.hostname = hostname
        self.logger = logger or logging.getLogger(__name__)
        self.exclusive_regions: Dict[str, str] = {}  # folder -> hostname

    def register_exclusive_region(self, folder: str, hostname: str) -> bool:
        """
        Register folder as exclusive to hostname.

        Args:
            folder: Folder path
            hostname: Exclusive owner

        Returns:
            True if registered
        """
        if folder in self.exclusive_regions:
            existing = self.exclusive_regions[folder]
            if existing != hostname:
                self.logger.warning(f"Folder {folder} already exclusive to {existing}")
                return False

        self.exclusive_regions[folder] = hostname
        self.logger.info(f"Registered exclusive region: {folder} → {hostname}")
        return True

    def is_exclusive_to_me(self, folder: str) -> bool:
        """Check if folder is exclusive to this host"""
        return self.exclusive_regions.get(folder) == self.hostname

    def is_exclusive_to_other(self, folder: str) -> bool:
        """Check if folder is exclusive to another host"""
        owner = self.exclusive_regions.get(folder)
        return owner is not None and owner != self.hostname

    def get_exclusive_folders(self) -> Dict[str, str]:
        """Get all exclusive regions"""
        return self.exclusive_regions.copy()


# ============================================================================
# Convenience Functions
# ============================================================================

def create_resolver(hostname: str,
                   default_strategy: ResolutionStrategy = ResolutionStrategy.LAST_WRITE_WINS,
                   host_priorities: Optional[Dict[str, int]] = None) -> ConflictResolver:
    """Create new conflict resolver"""
    return ConflictResolver(hostname, default_strategy=default_strategy,
                          host_priorities=host_priorities)
