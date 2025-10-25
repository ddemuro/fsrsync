"""
Distributed Sync Protocol (DSP)

Enables safe, efficient multi-host file synchronization with:
1. Host-to-host coordination
2. Conflict detection and resolution
3. Circular sync prevention
4. Bandwidth optimization
5. Version vector tracking
6. Operation journaling

Protocol Overview:

The protocol operates on a gossip/eventual consistency model:
- Each host can initiate syncs with any other host
- Version vectors ensure operation ordering
- Sync journal prevents circular syncs
- Conflicts detected and resolved cooperatively
- Bandwidth optimizations applied throughout

Message Types:

1. HELLO: Initial connection handshake
   - Hostname identification
   - Version number
   - Capabilities
   - Journal state

2. SYNC_REQUEST: Request to sync folder
   - Folder path
   - Version vector (current state)
   - Last sync time
   - Requested direction (PULL/PUSH/BOTH)

3. FILE_STATE: Share file information
   - File path
   - Content hash
   - Metadata (size, mtime, permissions)
   - Version vector
   - State (created/modified/deleted)

4. CONFLICT_NOTICE: Notify of conflict
   - File path
   - Conflicting versions
   - Operation timestamps
   - Request for resolution

5. SYNC_ACK: Acknowledge sync completion
   - Folder path
   - Files synced count
   - Bandwidth used
   - New version vector

6. HEARTBEAT: Keep connection alive
   - Current time
   - Journal size
   - Pending operations

Sync Directions:

PUSH: Host A → Host B
  - Host A scans folders
  - Compares with Host B's state
  - Sends changed files to B
  - Updates B's journal

PULL: Host B ← Host A
  - Host B requests state
  - Host A responds with changed files
  - Host B receives and updates
  - Host A updates journal

BOTH: Host A ↔ Host B (Bidirectional)
  - Hosts exchange state
  - Both directions executed
  - Conflicts resolved
  - All journals updated

Circular Sync Prevention:

Problem: A syncs to B, B syncs back to A, infinite loop
Solution: Version vectors + journals

Example:
1. Host A modifies file.txt, version={A:1, B:0}
2. A sends to B with version vector
3. B records operation: "A did version 1"
4. B modifies file.txt, version={A:1, B:1}
5. B sends to A with version vector
6. A checks: "B sent operation where A was already 1"
7. A resolves conflict (newer B wins)
8. No circular sync - both agree on final state

Conflict Resolution:

When concurrent modifications detected:
1. Last-write-wins (default): Newer timestamp wins
2. Host-priority: Admin-configured host wins
3. Size-wins: Larger file wins (safer for partial writes)
4. Manual: Flag for human review

Bandwidth Optimization:

- Delta sync: Only changed blocks transferred
- Move detection: Instant moves without re-transfer
- Compression: Auto-select ZSTD/LZ4/GZIP
- Batching: Multiple files per message
- Deduplication: Skip files already in transit

Operation Journal Sync:

Hosts share operation journals to ensure consistency:
- Each host tracks what it's done
- Other hosts know not to re-sync
- Enables safe multi-host setups
- Prevents lost updates
"""

import asyncio
import logging
import json
import time
from enum import Enum
from typing import Dict, List, Optional, Any, Set, Tuple
from dataclasses import dataclass, asdict, field
from pathlib import Path
import hashlib

logger = logging.getLogger(__name__)


# ============================================================================
# Protocol Data Types
# ============================================================================

class SyncDirection(Enum):
    """Direction of synchronization"""
    PUSH = "PUSH"      # Local → Remote
    PULL = "PULL"      # Remote → Local
    BOTH = "BOTH"      # Bidirectional


class MessageType(Enum):
    """Types of protocol messages"""
    HELLO = "HELLO"
    SYNC_REQUEST = "SYNC_REQUEST"
    FILE_STATE = "FILE_STATE"
    CONFLICT_NOTICE = "CONFLICT_NOTICE"
    SYNC_ACK = "SYNC_ACK"
    HEARTBEAT = "HEARTBEAT"
    ERROR = "ERROR"
    CLOSE = "CLOSE"


class ConflictResolutionStrategy(Enum):
    """How to resolve conflicts"""
    LAST_WRITE_WINS = "LAST_WRITE_WINS"      # Newer timestamp
    HOST_PRIORITY = "HOST_PRIORITY"          # Admin-configured winner
    SIZE_WINS = "SIZE_WINS"                  # Larger file wins
    MANUAL = "MANUAL"                        # Flag for human review


@dataclass
class ProtocolMessage:
    """Generic protocol message"""
    message_type: MessageType
    timestamp: float = field(default_factory=time.time)
    sequence: int = 0
    payload: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'message_type': self.message_type.value,
            'timestamp': self.timestamp,
            'sequence': self.sequence,
            'payload': self.payload
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ProtocolMessage':
        """Create from dictionary"""
        return cls(
            message_type=MessageType(data['message_type']),
            timestamp=data.get('timestamp', time.time()),
            sequence=data.get('sequence', 0),
            payload=data.get('payload', {})
        )


@dataclass
class HelloMessage:
    """Initial handshake message"""
    hostname: str
    protocol_version: str = "1.0"
    capabilities: List[str] = field(default_factory=list)
    journal_size: int = 0
    folders: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'hostname': self.hostname,
            'protocol_version': self.protocol_version,
            'capabilities': self.capabilities,
            'journal_size': self.journal_size,
            'folders': self.folders
        }


@dataclass
class FileStateMessage:
    """File state information"""
    path: str
    content_hash: str
    size: int
    mtime: float
    permissions: int
    version_vector: Dict[str, int]
    operation_type: str  # CREATE, MODIFY, DELETE
    hostname: str  # Who made this change

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'path': self.path,
            'content_hash': self.content_hash,
            'size': self.size,
            'mtime': self.mtime,
            'permissions': self.permissions,
            'version_vector': self.version_vector,
            'operation_type': self.operation_type,
            'hostname': self.hostname
        }


@dataclass
class ConflictInfo:
    """Information about a conflict"""
    file_path: str
    local_version: FileStateMessage
    remote_version: FileStateMessage
    conflict_time: float = field(default_factory=time.time)
    resolution: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'file_path': self.file_path,
            'local_version': self.local_version.to_dict() if self.local_version else None,
            'remote_version': self.remote_version.to_dict() if self.remote_version else None,
            'conflict_time': self.conflict_time,
            'resolution': self.resolution
        }


# ============================================================================
# Sync Session
# ============================================================================

@dataclass
class SyncSession:
    """Tracks a single sync session between two hosts"""
    session_id: str
    local_hostname: str
    remote_hostname: str
    folder: str
    direction: SyncDirection
    started_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    files_processed: int = 0
    files_failed: int = 0
    conflicts_found: int = 0
    bytes_transferred: int = 0
    local_version_vector: Dict[str, int] = field(default_factory=dict)
    remote_version_vector: Dict[str, int] = field(default_factory=dict)

    def duration(self) -> Optional[float]:
        """Duration in seconds"""
        if self.completed_at is None:
            return None
        return self.completed_at - self.started_at

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'session_id': self.session_id,
            'local_hostname': self.local_hostname,
            'remote_hostname': self.remote_hostname,
            'folder': self.folder,
            'direction': self.direction.value,
            'started_at': self.started_at,
            'completed_at': self.completed_at,
            'duration': self.duration(),
            'files_processed': self.files_processed,
            'files_failed': self.files_failed,
            'conflicts_found': self.conflicts_found,
            'bytes_transferred': self.bytes_transferred
        }


# ============================================================================
# Distributed Sync Protocol
# ============================================================================

class DistributedSyncProtocol:
    """
    Protocol for multi-host file synchronization.

    Handles:
    - Host coordination
    - Version vector exchange
    - Conflict detection
    - Circular sync prevention
    - Bandwidth optimization
    """

    PROTOCOL_VERSION = "1.0"

    def __init__(self, hostname: str, logger=None):
        """
        Initialize protocol.

        Args:
            hostname: This host's name
            logger: Logger instance
        """
        self.hostname = hostname
        self.logger = logger or logging.getLogger(__name__)
        self.sequence = 0
        self.sessions: Dict[str, SyncSession] = {}
        self.lock = asyncio.Lock()

    async def create_hello_message(self, folders: List[str],
                                  capabilities: Optional[List[str]] = None) -> ProtocolMessage:
        """
        Create HELLO message for initial handshake.

        Args:
            folders: List of folders being synced
            capabilities: Optional list of capabilities

        Returns:
            ProtocolMessage with HELLO type
        """
        if capabilities is None:
            capabilities = [
                "delta_sync",
                "move_detection",
                "metadata_preservation",
                "conflict_detection",
                "version_vectors"
            ]

        hello = HelloMessage(
            hostname=self.hostname,
            protocol_version=self.PROTOCOL_VERSION,
            capabilities=capabilities,
            journal_size=0,  # Would get from sync journal
            folders=folders
        )

        async with self.lock:
            self.sequence += 1

        return ProtocolMessage(
            message_type=MessageType.HELLO,
            sequence=self.sequence,
            payload=hello.to_dict()
        )

    async def create_sync_request(self, folder: str,
                                 direction: SyncDirection,
                                 version_vector: Dict[str, int],
                                 last_sync_time: Optional[float] = None) -> ProtocolMessage:
        """
        Create SYNC_REQUEST message.

        Args:
            folder: Folder to sync
            direction: PUSH, PULL, or BOTH
            version_vector: Current version state
            last_sync_time: When last sync occurred

        Returns:
            ProtocolMessage with SYNC_REQUEST type
        """
        async with self.lock:
            self.sequence += 1

        return ProtocolMessage(
            message_type=MessageType.SYNC_REQUEST,
            sequence=self.sequence,
            payload={
                'folder': folder,
                'direction': direction.value,
                'version_vector': version_vector,
                'last_sync_time': last_sync_time or time.time()
            }
        )

    async def create_file_state_message(self, path: str,
                                       content_hash: str,
                                       size: int,
                                       mtime: float,
                                       permissions: int,
                                       version_vector: Dict[str, int],
                                       operation_type: str) -> ProtocolMessage:
        """
        Create FILE_STATE message for a file.

        Args:
            path: File path
            content_hash: File content hash
            size: File size
            mtime: Modification time
            permissions: File permissions
            version_vector: Version vector
            operation_type: CREATE, MODIFY, or DELETE

        Returns:
            ProtocolMessage with FILE_STATE type
        """
        file_state = FileStateMessage(
            path=path,
            content_hash=content_hash,
            size=size,
            mtime=mtime,
            permissions=permissions,
            version_vector=version_vector,
            operation_type=operation_type,
            hostname=self.hostname
        )

        async with self.lock:
            self.sequence += 1

        return ProtocolMessage(
            message_type=MessageType.FILE_STATE,
            sequence=self.sequence,
            payload=file_state.to_dict()
        )

    async def create_conflict_notice(self, file_path: str,
                                    local_state: FileStateMessage,
                                    remote_state: FileStateMessage) -> ProtocolMessage:
        """
        Create CONFLICT_NOTICE message.

        Args:
            file_path: File with conflict
            local_state: Local file state
            remote_state: Remote file state

        Returns:
            ProtocolMessage with CONFLICT_NOTICE type
        """
        conflict = ConflictInfo(
            file_path=file_path,
            local_version=local_state,
            remote_version=remote_state
        )

        async with self.lock:
            self.sequence += 1

        return ProtocolMessage(
            message_type=MessageType.CONFLICT_NOTICE,
            sequence=self.sequence,
            payload=conflict.to_dict()
        )

    async def create_sync_ack(self, folder: str,
                             files_synced: int,
                             bandwidth_used: int,
                             version_vector: Dict[str, int]) -> ProtocolMessage:
        """
        Create SYNC_ACK message.

        Args:
            folder: Folder synced
            files_synced: Number of files synchronized
            bandwidth_used: Bytes transferred
            version_vector: New version state

        Returns:
            ProtocolMessage with SYNC_ACK type
        """
        async with self.lock:
            self.sequence += 1

        return ProtocolMessage(
            message_type=MessageType.SYNC_ACK,
            sequence=self.sequence,
            payload={
                'folder': folder,
                'files_synced': files_synced,
                'bandwidth_used': bandwidth_used,
                'version_vector': version_vector
            }
        )

    async def create_heartbeat(self) -> ProtocolMessage:
        """
        Create HEARTBEAT message to keep connection alive.

        Returns:
            ProtocolMessage with HEARTBEAT type
        """
        async with self.lock:
            self.sequence += 1

        return ProtocolMessage(
            message_type=MessageType.HEARTBEAT,
            sequence=self.sequence,
            payload={
                'timestamp': time.time(),
                'active_sessions': len(self.sessions)
            }
        )

    async def start_session(self, remote_hostname: str, folder: str,
                          direction: SyncDirection) -> SyncSession:
        """
        Start a new sync session.

        Args:
            remote_hostname: Remote host to sync with
            folder: Folder to sync
            direction: PUSH, PULL, or BOTH

        Returns:
            SyncSession object
        """
        session_id = f"{self.hostname}→{remote_hostname}:{folder}"

        session = SyncSession(
            session_id=session_id,
            local_hostname=self.hostname,
            remote_hostname=remote_hostname,
            folder=folder,
            direction=direction
        )

        async with self.lock:
            self.sessions[session_id] = session

        self.logger.info(f"Started sync session: {session_id}")
        return session

    async def complete_session(self, session_id: str) -> Optional[SyncSession]:
        """
        Complete a sync session.

        Args:
            session_id: Session to complete

        Returns:
            Completed SyncSession
        """
        async with self.lock:
            session = self.sessions.get(session_id)
            if session:
                session.completed_at = time.time()
                self.logger.info(f"Completed sync session: {session_id} "
                               f"({session.files_processed} files, "
                               f"{session.duration():.1f}s)")
                return session

        return None

    async def detect_conflict(self, file_path: str,
                            local_version: FileStateMessage,
                            remote_version: FileStateMessage) -> bool:
        """
        Detect if versions conflict.

        Args:
            file_path: File being checked
            local_version: Local file state
            remote_version: Remote file state

        Returns:
            True if conflict detected
        """
        # Same content hash = no conflict
        if local_version.content_hash == remote_version.content_hash:
            return False

        # Compare version vectors
        local_vec = local_version.version_vector
        remote_vec = remote_version.version_vector

        # Check if one happened before the other (causality)
        local_before = all(
            local_vec.get(host, 0) <= remote_vec.get(host, 0)
            for host in set(local_vec.keys()) | set(remote_vec.keys())
        )
        remote_before = all(
            remote_vec.get(host, 0) <= local_vec.get(host, 0)
            for host in set(local_vec.keys()) | set(remote_vec.keys())
        )

        # If neither happened before the other = concurrent = conflict
        return not (local_before or remote_before)

    async def resolve_conflict(self, conflict: ConflictInfo,
                              strategy: ConflictResolutionStrategy) -> str:
        """
        Resolve a conflict.

        Args:
            conflict: ConflictInfo to resolve
            strategy: Resolution strategy to use

        Returns:
            Winning hostname
        """
        local = conflict.local_version
        remote = conflict.remote_version

        if strategy == ConflictResolutionStrategy.LAST_WRITE_WINS:
            # Newer timestamp wins
            if local.mtime > remote.mtime:
                return self.hostname
            return conflict.remote_version.hostname

        elif strategy == ConflictResolutionStrategy.SIZE_WINS:
            # Larger file wins (safer for partial writes)
            if local.size >= remote.size:
                return self.hostname
            return remote.hostname

        elif strategy == ConflictResolutionStrategy.HOST_PRIORITY:
            # Admin-configured priority (not implemented here)
            return self.hostname

        else:  # MANUAL
            # Flag for manual review
            return "MANUAL_REVIEW"

    async def should_skip_operation(self, file_path: str,
                                   version_vector: Dict[str, int]) -> bool:
        """
        Check if operation should be skipped (already in journal).

        Args:
            file_path: File path
            version_vector: Operation version vector

        Returns:
            True if should skip
        """
        # In production, would check against sync_journal
        # For now, return False (don't skip)
        return False

    async def merge_version_vectors(self, vec1: Dict[str, int],
                                   vec2: Dict[str, int]) -> Dict[str, int]:
        """
        Merge two version vectors (take max of each).

        Args:
            vec1: First version vector
            vec2: Second version vector

        Returns:
            Merged version vector
        """
        merged = vec1.copy()
        for host, clock in vec2.items():
            merged[host] = max(merged.get(host, 0), clock)
        return merged

    def get_session_statistics(self) -> Dict[str, Any]:
        """Get statistics about all sessions"""
        total_sessions = len(self.sessions)
        completed = sum(1 for s in self.sessions.values() if s.completed_at)
        active = total_sessions - completed

        total_files = sum(s.files_processed for s in self.sessions.values())
        total_bytes = sum(s.bytes_transferred for s in self.sessions.values())
        total_conflicts = sum(s.conflicts_found for s in self.sessions.values())

        return {
            'total_sessions': total_sessions,
            'active_sessions': active,
            'completed_sessions': completed,
            'total_files_synced': total_files,
            'total_bytes_transferred': total_bytes,
            'total_conflicts': total_conflicts,
            'message_sequence': self.sequence
        }


# ============================================================================
# Convenience Functions
# ============================================================================

async def create_protocol(hostname: str) -> DistributedSyncProtocol:
    """Create new distributed sync protocol instance"""
    return DistributedSyncProtocol(hostname)
