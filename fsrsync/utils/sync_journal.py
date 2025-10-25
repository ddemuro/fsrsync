"""
Sync Journal with Version Vectors

Implements a distributed operation log to prevent circular syncs and enable
multi-host synchronization with conflict detection.

Features:
- Operation journal: Track all sync operations
- Version vectors: Per-host logical clocks for ordering
- Conflict detection: Identify conflicting changes
- Circular sync prevention: Don't re-sync your own changes

How It Works:

1. OPERATION LOGGING
   Each sync operation is recorded with:
   - Hostname of origin
   - File path
   - Operation type (CREATE, MODIFY, DELETE, MOVE)
   - File hash (for identification)
   - Timestamp
   - Version vector (logical clock)

2. VERSION VECTORS
   Each host maintains a clock:
   {
     "host1": 42,  # Host1 has done 42 operations
     "host2": 18,  # Host2 has done 18 operations
     "host3": 7    # Host3 has done 7 operations
   }

   When Host1 sends an operation, it includes its full vector clock.
   Remote sees it originated from Host1 and knows not to re-sync it.

3. CIRCULAR SYNC PREVENTION
   Before syncing a change:
   - Check if operation is in journal from MY hostname
   - If yes: SKIP (don't re-sync own changes)
   - If no: PROCESS

4. CONFLICT DETECTION
   Same file modified by two hosts simultaneously:
   - Both operations in journal
   - Last-write-wins by default (configurable)
   - Can flag for manual review

Example:

Host A:
  - Modifies file.txt at 10:00:00
  - Sends: MODIFY file.txt, v_vector={A:1, B:0}

Host B:
  - Receives file.txt from Host A
  - Journal records: MODIFY from Host A, v_vector={A:1, B:0}
  - Host B modifies file.txt at 10:00:05
  - Before syncing back to A: checks journal
  - Sees Host A already modified it at v_vector={A:1}
  - Can handle conflict (last-write-wins: B wins)

Result: No circular sync, clear operation history
"""

import json
import logging
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, asdict, field
from enum import Enum
from datetime import datetime
import threading

logger = logging.getLogger(__name__)


# ============================================================================
# Data Structures
# ============================================================================

class OperationType(Enum):
    """Types of sync operations"""
    CREATE = "CREATE"
    MODIFY = "MODIFY"
    DELETE = "DELETE"
    MOVE = "MOVE"
    CHMOD = "CHMOD"


@dataclass
class VersionVector:
    """Logical clock for distributed ordering"""
    clocks: Dict[str, int] = field(default_factory=dict)

    def increment(self, hostname: str) -> None:
        """Increment clock for hostname"""
        self.clocks[hostname] = self.clocks.get(hostname, 0) + 1

    def merge(self, other: 'VersionVector') -> 'VersionVector':
        """Merge with another vector (take max of each clock)"""
        merged = VersionVector(self.clocks.copy())
        for host, clock in other.clocks.items():
            merged.clocks[host] = max(merged.clocks.get(host, 0), clock)
        return merged

    def happens_before(self, other: 'VersionVector') -> bool:
        """Check if this vector happened before other"""
        less_equal = all(
            self.clocks.get(h, 0) <= other.clocks.get(h, 0)
            for h in set(self.clocks.keys()) | set(other.clocks.keys())
        )
        less = any(
            self.clocks.get(h, 0) < other.clocks.get(h, 0)
            for h in set(self.clocks.keys()) | set(other.clocks.keys())
        )
        return less_equal and less

    def concurrent_with(self, other: 'VersionVector') -> bool:
        """Check if vectors are concurrent (neither happens before)"""
        return not (self.happens_before(other) or other.happens_before(self))

    def to_dict(self) -> Dict[str, int]:
        """Convert to dictionary"""
        return self.clocks.copy()

    @classmethod
    def from_dict(cls, data: Dict[str, int]) -> 'VersionVector':
        """Create from dictionary"""
        return cls(clocks=data.copy())

    def __str__(self) -> str:
        return str(self.clocks)


@dataclass
class SyncOperation:
    """Represents a single sync operation"""
    operation_type: OperationType
    hostname: str                          # Which host made this change
    file_path: str                         # Relative path to file
    file_hash: Optional[str] = None        # Content hash
    old_path: Optional[str] = None         # For MOVE operations
    timestamp: float = field(default_factory=time.time)
    version_vector: VersionVector = field(default_factory=VersionVector)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            'operation_type': self.operation_type.value,
            'hostname': self.hostname,
            'file_path': self.file_path,
            'file_hash': self.file_hash,
            'old_path': self.old_path,
            'timestamp': self.timestamp,
            'version_vector': self.version_vector.to_dict(),
            'metadata': self.metadata
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SyncOperation':
        """Create from dictionary"""
        return cls(
            operation_type=OperationType(data['operation_type']),
            hostname=data['hostname'],
            file_path=data['file_path'],
            file_hash=data.get('file_hash'),
            old_path=data.get('old_path'),
            timestamp=data.get('timestamp', time.time()),
            version_vector=VersionVector.from_dict(data.get('version_vector', {})),
            metadata=data.get('metadata', {})
        )


@dataclass
class Conflict:
    """Represents a conflict between operations"""
    file_path: str
    operations: List[SyncOperation]
    timestamp: float = field(default_factory=time.time)
    resolved: bool = False
    resolution: Optional[str] = None        # Which operation won

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'file_path': self.file_path,
            'operations': [op.to_dict() for op in self.operations],
            'timestamp': self.timestamp,
            'resolved': self.resolved,
            'resolution': self.resolution
        }


# ============================================================================
# Sync Journal
# ============================================================================

class SyncJournal:
    """
    Distributed operation journal for sync coordination.

    Stores all operations and version vectors to prevent circular syncs
    and detect conflicts.
    """

    def __init__(self, hostname: str, journal_file: Optional[str] = None, logger=None):
        """
        Initialize journal.

        Args:
            hostname: Hostname of this sync instance
            journal_file: Path to persistent journal file (optional)
            logger: Logger instance
        """
        self.hostname = hostname
        self.journal_file = journal_file
        self.logger = logger or logging.getLogger(__name__)
        self.lock = threading.RLock()

        # In-memory journal
        self.operations: List[SyncOperation] = []
        self.conflicts: List[Conflict] = []
        self.version_vector = VersionVector(clocks={hostname: 0})

        # Load from file if provided
        if journal_file:
            self.load()

    def record_operation(self, operation_type: OperationType, file_path: str,
                        file_hash: Optional[str] = None,
                        old_path: Optional[str] = None,
                        metadata: Optional[Dict[str, Any]] = None) -> SyncOperation:
        """
        Record a sync operation.

        Args:
            operation_type: Type of operation
            file_path: File path
            file_hash: Content hash
            old_path: For MOVE operations
            metadata: Additional metadata

        Returns:
            SyncOperation object
        """
        with self.lock:
            # Increment our version vector
            self.version_vector.increment(self.hostname)

            # Create operation
            operation = SyncOperation(
                operation_type=operation_type,
                hostname=self.hostname,
                file_path=file_path,
                file_hash=file_hash,
                old_path=old_path,
                version_vector=self.version_vector.merge(VersionVector()),
                metadata=metadata or {}
            )

            # Add to journal
            self.operations.append(operation)

            self.logger.debug(f"Recorded operation: {operation_type.value} {file_path}")

            # Persist if file provided
            if self.journal_file:
                self.save()

            return operation

    def receive_operation(self, operation: SyncOperation) -> bool:
        """
        Receive an operation from another host.

        Merges version vector and checks for conflicts.

        Args:
            operation: SyncOperation from another host

        Returns:
            True if operation should be applied (not from our own sync)
        """
        with self.lock:
            # Merge version vectors
            self.version_vector = self.version_vector.merge(operation.version_vector)

            # Check if this is from our hostname (don't re-sync own changes)
            if operation.hostname == self.hostname:
                self.logger.debug(f"Skipping operation from own host: {operation.file_path}")
                return False

            # Check for conflicts
            conflicts = self._check_conflicts(operation)
            if conflicts:
                self.logger.warning(f"Conflict detected for {operation.file_path}")
                conflict = Conflict(
                    file_path=operation.file_path,
                    operations=conflicts + [operation]
                )
                self.conflicts.append(conflict)

            # Add to journal
            self.operations.append(operation)

            self.logger.debug(f"Received operation: {operation.operation_type.value} {operation.file_path} from {operation.hostname}")

            # Persist if file provided
            if self.journal_file:
                self.save()

            return True

    def _check_conflicts(self, operation: SyncOperation) -> List[SyncOperation]:
        """
        Check if operation conflicts with existing operations.

        Args:
            operation: Operation to check

        Returns:
            List of conflicting operations
        """
        conflicts = []

        # Find all operations on same file
        for existing_op in self.operations:
            if existing_op.file_path != operation.file_path:
                continue

            # Check if operations are concurrent (happened at same time)
            if operation.version_vector.concurrent_with(existing_op.version_vector):
                # Both operations happened independently - conflict!
                if existing_op.operation_type in (OperationType.MODIFY, OperationType.CREATE):
                    if operation.operation_type in (OperationType.MODIFY, OperationType.CREATE):
                        conflicts.append(existing_op)

        return conflicts

    def should_skip_operation(self, operation_type: OperationType,
                             file_path: str) -> bool:
        """
        Check if an operation should be skipped (already synced).

        Args:
            operation_type: Type of operation
            file_path: File path

        Returns:
            True if operation should be skipped
        """
        with self.lock:
            # Look for same operation from our hostname
            for op in self.operations:
                if (op.hostname == self.hostname and
                    op.file_path == file_path and
                    op.operation_type == operation_type):
                    # We already synced this
                    return True

        return False

    def resolve_conflict(self, file_path: str, winning_hostname: str) -> bool:
        """
        Resolve a conflict by choosing winning operation.

        Args:
            file_path: File path
            winning_hostname: Which host's operation wins

        Returns:
            True if conflict was resolved
        """
        with self.lock:
            for conflict in self.conflicts:
                if conflict.file_path == file_path:
                    # Find winning operation
                    for op in conflict.operations:
                        if op.hostname == winning_hostname:
                            conflict.resolution = winning_hostname
                            conflict.resolved = True
                            self.logger.info(f"Resolved conflict for {file_path}: {winning_hostname} wins")
                            if self.journal_file:
                                self.save()
                            return True

        return False

    def get_conflicts(self) -> List[Conflict]:
        """Get unresolved conflicts"""
        with self.lock:
            return [c for c in self.conflicts if not c.resolved]

    def save(self) -> bool:
        """Save journal to file"""
        if not self.journal_file:
            return False

        try:
            with self.lock:
                data = {
                    'hostname': self.hostname,
                    'version_vector': self.version_vector.to_dict(),
                    'operations': [op.to_dict() for op in self.operations],
                    'conflicts': [c.to_dict() for c in self.conflicts],
                    'saved_at': time.time()
                }

                path = Path(self.journal_file)
                path.parent.mkdir(parents=True, exist_ok=True)

                with open(self.journal_file, 'w') as f:
                    json.dump(data, f, indent=2)

                self.logger.debug(f"Saved journal to {self.journal_file}")
                return True

        except Exception as e:
            self.logger.error(f"Error saving journal: {e}")
            return False

    def load(self) -> bool:
        """Load journal from file"""
        if not self.journal_file:
            return False

        try:
            path = Path(self.journal_file)
            if not path.exists():
                self.logger.debug(f"Journal file does not exist: {self.journal_file}")
                return False

            with open(self.journal_file, 'r') as f:
                data = json.load(f)

            with self.lock:
                self.version_vector = VersionVector.from_dict(data.get('version_vector', {}))
                self.operations = [SyncOperation.from_dict(op) for op in data.get('operations', [])]
                self.conflicts = [Conflict(**c) for c in data.get('conflicts', [])]

            self.logger.debug(f"Loaded journal from {self.journal_file}")
            return True

        except Exception as e:
            self.logger.error(f"Error loading journal: {e}")
            return False

    def get_statistics(self) -> Dict[str, Any]:
        """Get journal statistics"""
        with self.lock:
            op_counts = {}
            for op in self.operations:
                op_type = op.operation_type.value
                op_counts[op_type] = op_counts.get(op_type, 0) + 1

            return {
                'hostname': self.hostname,
                'total_operations': len(self.operations),
                'operations_by_type': op_counts,
                'total_conflicts': len(self.conflicts),
                'unresolved_conflicts': len([c for c in self.conflicts if not c.resolved]),
                'version_vector': self.version_vector.to_dict(),
                'first_operation': self.operations[0].timestamp if self.operations else None,
                'last_operation': self.operations[-1].timestamp if self.operations else None
            }

    def clear(self) -> None:
        """Clear journal (for testing)"""
        with self.lock:
            self.operations.clear()
            self.conflicts.clear()
            self.version_vector = VersionVector(clocks={self.hostname: 0})
            if self.journal_file:
                self.save()


# ============================================================================
# Utility Functions
# ============================================================================

def create_journal(hostname: str, journal_file: Optional[str] = None) -> SyncJournal:
    """Create a new sync journal"""
    return SyncJournal(hostname, journal_file)
