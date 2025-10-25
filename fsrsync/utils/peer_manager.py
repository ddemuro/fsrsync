"""
Peer Discovery and Management

Enables FSRsync instances to discover each other and manage connections:

1. DISCOVERY: Find peers on network
   - mDNS (Multicast DNS) for local networks
   - Central registry for remote peers
   - Configuration file for static peers

2. CONNECTION: Establish connections
   - TCP connections with heartbeat
   - Connection pooling to reduce overhead
   - Automatic reconnection on failure

3. MANAGEMENT: Track peer state
   - Online/offline tracking
   - Last seen timestamps
   - Folder sharing agreements
   - Sync history

4. COORDINATION: Sync scheduling
   - Periodic sync intervals
   - Manual sync requests
   - Conflict notification
   - Version vector exchange

Discovery Methods:

1. mDNS (Zero-Config)
   - Advertise: "_fsrsync._tcp" service
   - Discover: Query for other instances
   - No configuration needed
   - Works on local network only

2. Central Registry
   - Connect to registry server
   - Register this instance
   - Query for other instances
   - Works across networks

3. Configuration File
   - Static peer list in config
   - Manual discovery
   - Works without network
   - Good for stable topologies

4. DNS-SD
   - Use DNS for service discovery
   - Scalable for large networks
   - Requires DNS infrastructure

Peer Status:

UNKNOWN: Initial state
DISCOVERED: Found via discovery
CONNECTING: Attempting to connect
CONNECTED: Active connection
IDLE: Connected but no activity
SYNCING: Currently syncing
OFFLINE: Connection lost
UNREACHABLE: Connection failed repeatedly

Connection Pooling:

- Keep N persistent connections
- Reuse for multiple operations
- Idle timeout for resource cleanup
- Exponential backoff on failures
- Connection health checks

Folder Sharing:

Each peer tracks:
- Which folders to sync
- Preferred directions (PUSH/PULL/BOTH)
- Conflict resolution strategy
- Last sync time
- Outstanding conflicts

Sync Scheduling:

- Periodic syncs (hourly, daily, etc)
- Manual sync on-demand
- Conflict-driven syncs
- Bandwidth-aware scheduling
"""

import asyncio
import logging
import time
from enum import Enum
from typing import Dict, List, Optional, Set, Any, Tuple
from dataclasses import dataclass, field
from pathlib import Path
import socket
import json

logger = logging.getLogger(__name__)


# ============================================================================
# Peer Status and Types
# ============================================================================

class PeerStatus(Enum):
    """Status of peer connection"""
    UNKNOWN = "UNKNOWN"
    DISCOVERED = "DISCOVERED"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    IDLE = "IDLE"
    SYNCING = "SYNCING"
    OFFLINE = "OFFLINE"
    UNREACHABLE = "UNREACHABLE"


class DiscoveryMethod(Enum):
    """How peer was discovered"""
    MDNS = "MDNS"
    REGISTRY = "REGISTRY"
    CONFIG = "CONFIG"
    MANUAL = "MANUAL"


@dataclass
class PeerInfo:
    """Information about a peer"""
    hostname: str
    address: str                               # IP address or hostname
    port: int = 9876                          # Default FSRsync port
    status: PeerStatus = PeerStatus.UNKNOWN
    discovery_method: DiscoveryMethod = DiscoveryMethod.MANUAL
    discovered_at: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    connection_attempts: int = 0
    connection_failures: int = 0
    last_error: Optional[str] = None
    capabilities: List[str] = field(default_factory=list)
    shared_folders: List[str] = field(default_factory=list)
    sync_history: Dict[str, float] = field(default_factory=dict)  # folder -> last_sync_time

    def is_online(self) -> bool:
        """Check if peer is likely online"""
        return self.status in (
            PeerStatus.CONNECTED,
            PeerStatus.IDLE,
            PeerStatus.SYNCING
        )

    def is_connecting(self) -> bool:
        """Check if actively attempting connection"""
        return self.status in (
            PeerStatus.CONNECTING,
            PeerStatus.DISCOVERED
        )

    def time_since_seen(self) -> float:
        """Seconds since last communication"""
        return time.time() - self.last_seen

    def address_tuple(self) -> Tuple[str, int]:
        """Get (address, port) tuple"""
        return (self.address, self.port)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'hostname': self.hostname,
            'address': self.address,
            'port': self.port,
            'status': self.status.value,
            'discovery_method': self.discovery_method.value,
            'discovered_at': self.discovered_at,
            'last_seen': self.last_seen,
            'connection_attempts': self.connection_attempts,
            'connection_failures': self.connection_failures,
            'capabilities': self.capabilities,
            'shared_folders': self.shared_folders,
            'sync_history': self.sync_history
        }


@dataclass
class FolderSharingAgreement:
    """Agreement to sync a folder between peers"""
    folder: str
    local_hostname: str
    remote_hostname: str
    direction: str                              # PUSH, PULL, BOTH
    conflict_strategy: str = "LAST_WRITE_WINS"
    sync_interval: Optional[float] = None       # Seconds (None = manual)
    last_sync: Optional[float] = None
    next_sync: Optional[float] = None
    enabled: bool = True

    def is_due_for_sync(self) -> bool:
        """Check if sync is due based on interval"""
        if not self.enabled or not self.sync_interval:
            return False
        if self.last_sync is None:
            return True
        return (time.time() - self.last_sync) >= self.sync_interval

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'folder': self.folder,
            'local_hostname': self.local_hostname,
            'remote_hostname': self.remote_hostname,
            'direction': self.direction,
            'conflict_strategy': self.conflict_strategy,
            'sync_interval': self.sync_interval,
            'last_sync': self.last_sync,
            'next_sync': self.next_sync,
            'enabled': self.enabled
        }


# ============================================================================
# Peer Manager
# ============================================================================

class PeerManager:
    """
    Manages peer discovery, connections, and coordination.

    Tracks all known peers and their sync status.
    """

    def __init__(self, hostname: str, logger=None):
        """
        Initialize peer manager.

        Args:
            hostname: This host's name
            logger: Logger instance
        """
        self.hostname = hostname
        self.logger = logger or logging.getLogger(__name__)
        self.peers: Dict[str, PeerInfo] = {}
        self.folder_agreements: Dict[str, FolderSharingAgreement] = {}
        self.lock = asyncio.Lock()
        self.connection_pool: Dict[str, Any] = {}  # hostname -> connection
        self.max_connection_attempts = 5
        self.connection_timeout = 10.0

    async def add_peer(self, hostname: str, address: str, port: int = 9876,
                      discovery_method: DiscoveryMethod = DiscoveryMethod.MANUAL) -> PeerInfo:
        """
        Add a known peer.

        Args:
            hostname: Peer hostname
            address: Peer address (IP or hostname)
            port: Peer port
            discovery_method: How peer was discovered

        Returns:
            PeerInfo object
        """
        async with self.lock:
            if hostname in self.peers:
                return self.peers[hostname]

            peer = PeerInfo(
                hostname=hostname,
                address=address,
                port=port,
                discovery_method=discovery_method,
                status=PeerStatus.DISCOVERED
            )

            self.peers[hostname] = peer
            self.logger.info(f"Added peer: {hostname} at {address}:{port}")
            return peer

    async def remove_peer(self, hostname: str) -> bool:
        """
        Remove a peer.

        Args:
            hostname: Peer to remove

        Returns:
            True if removed
        """
        async with self.lock:
            if hostname in self.peers:
                del self.peers[hostname]
                self.logger.info(f"Removed peer: {hostname}")
                return True
        return False

    async def get_peer(self, hostname: str) -> Optional[PeerInfo]:
        """
        Get peer information.

        Args:
            hostname: Peer to get

        Returns:
            PeerInfo or None
        """
        async with self.lock:
            return self.peers.get(hostname)

    async def list_peers(self, status_filter: Optional[PeerStatus] = None) -> List[PeerInfo]:
        """
        List all known peers.

        Args:
            status_filter: Optional status to filter by

        Returns:
            List of PeerInfo objects
        """
        async with self.lock:
            peers = list(self.peers.values())
            if status_filter:
                peers = [p for p in peers if p.status == status_filter]
            return peers

    async def update_peer_status(self, hostname: str,
                                status: PeerStatus,
                                error: Optional[str] = None) -> bool:
        """
        Update peer status.

        Args:
            hostname: Peer to update
            status: New status
            error: Optional error message

        Returns:
            True if updated
        """
        async with self.lock:
            peer = self.peers.get(hostname)
            if not peer:
                return False

            peer.status = status
            peer.last_seen = time.time()
            peer.last_error = error

            if status == PeerStatus.CONNECTED:
                peer.connection_failures = 0
            elif status == PeerStatus.OFFLINE:
                peer.connection_failures += 1

            self.logger.debug(f"Updated {hostname} status to {status.value}")
            return True

    async def mark_sync_completed(self, hostname: str, folder: str) -> bool:
        """
        Mark sync completed for peer/folder.

        Args:
            hostname: Peer that was synced
            folder: Folder that was synced

        Returns:
            True if updated
        """
        async with self.lock:
            peer = self.peers.get(hostname)
            if not peer:
                return False

            peer.sync_history[folder] = time.time()
            self.logger.debug(f"Marked sync completed: {hostname}:{folder}")
            return True

    async def add_folder_agreement(self, folder: str, remote_hostname: str,
                                  direction: str,
                                  sync_interval: Optional[float] = None,
                                  conflict_strategy: str = "LAST_WRITE_WINS") -> FolderSharingAgreement:
        """
        Add folder sharing agreement.

        Args:
            folder: Folder to share
            remote_hostname: Remote peer
            direction: PUSH, PULL, or BOTH
            sync_interval: Optional sync interval in seconds
            conflict_strategy: How to resolve conflicts

        Returns:
            FolderSharingAgreement object
        """
        async with self.lock:
            agreement_key = f"{folder}:{remote_hostname}"

            agreement = FolderSharingAgreement(
                folder=folder,
                local_hostname=self.hostname,
                remote_hostname=remote_hostname,
                direction=direction,
                conflict_strategy=conflict_strategy,
                sync_interval=sync_interval
            )

            self.folder_agreements[agreement_key] = agreement
            self.logger.info(f"Added folder agreement: {agreement_key} ({direction})")
            return agreement

    async def get_folder_agreements(self, remote_hostname: Optional[str] = None,
                                   due_only: bool = False) -> List[FolderSharingAgreement]:
        """
        Get folder sharing agreements.

        Args:
            remote_hostname: Optional filter by peer
            due_only: Only return agreements due for sync

        Returns:
            List of FolderSharingAgreement objects
        """
        async with self.lock:
            agreements = list(self.folder_agreements.values())

            if remote_hostname:
                agreements = [a for a in agreements
                            if a.remote_hostname == remote_hostname]

            if due_only:
                agreements = [a for a in agreements if a.is_due_for_sync()]

            return agreements

    async def get_connection(self, hostname: str) -> Optional[Any]:
        """
        Get connection to peer (from pool if available).

        Args:
            hostname: Peer to connect to

        Returns:
            Connection object or None
        """
        # Check pool first
        if hostname in self.connection_pool:
            return self.connection_pool[hostname]

        # Get peer info
        peer = await self.get_peer(hostname)
        if not peer:
            self.logger.error(f"Unknown peer: {hostname}")
            return None

        # Try to connect (in production, would create actual socket)
        try:
            await self.update_peer_status(hostname, PeerStatus.CONNECTING)

            # Simulated connection (in production, create actual socket)
            connection = {
                'hostname': hostname,
                'address': peer.address,
                'port': peer.port,
                'established_at': time.time()
            }

            self.connection_pool[hostname] = connection
            await self.update_peer_status(hostname, PeerStatus.CONNECTED)

            self.logger.info(f"Connected to peer: {hostname}")
            return connection

        except Exception as e:
            await self.update_peer_status(hostname, PeerStatus.OFFLINE, str(e))
            self.logger.error(f"Failed to connect to {hostname}: {e}")
            return None

    async def close_connection(self, hostname: str) -> bool:
        """
        Close connection to peer.

        Args:
            hostname: Peer to disconnect

        Returns:
            True if closed
        """
        if hostname in self.connection_pool:
            del self.connection_pool[hostname]
            await self.update_peer_status(hostname, PeerStatus.IDLE)
            self.logger.info(f"Closed connection to: {hostname}")
            return True
        return False

    async def get_syncs_due(self) -> List[Tuple[str, str, str]]:
        """
        Get all syncs that are due to run.

        Returns:
            List of (remote_hostname, folder, direction) tuples
        """
        due_syncs = []

        agreements = await self.get_folder_agreements(due_only=True)
        for agreement in agreements:
            due_syncs.append((
                agreement.remote_hostname,
                agreement.folder,
                agreement.direction
            ))

        return due_syncs

    async def get_peer_statistics(self) -> Dict[str, Any]:
        """Get statistics about peers"""
        async with self.lock:
            total_peers = len(self.peers)
            online = sum(1 for p in self.peers.values() if p.is_online())
            offline = total_peers - online

            total_agreements = len(self.folder_agreements)
            total_folders = len(set(a.folder for a in self.folder_agreements.values()))

            return {
                'total_peers': total_peers,
                'online_peers': online,
                'offline_peers': offline,
                'total_agreements': total_agreements,
                'unique_folders': total_folders,
                'active_connections': len(self.connection_pool)
            }

    async def save_configuration(self, config_file: str) -> bool:
        """
        Save peer configuration to file.

        Args:
            config_file: Path to save config

        Returns:
            True if successful
        """
        try:
            async with self.lock:
                config = {
                    'hostname': self.hostname,
                    'peers': [p.to_dict() for p in self.peers.values()],
                    'folder_agreements': [a.to_dict() for a in self.folder_agreements.values()],
                    'saved_at': time.time()
                }

            with open(config_file, 'w') as f:
                json.dump(config, f, indent=2)

            self.logger.info(f"Saved peer configuration to {config_file}")
            return True

        except Exception as e:
            self.logger.error(f"Error saving configuration: {e}")
            return False

    async def load_configuration(self, config_file: str) -> bool:
        """
        Load peer configuration from file.

        Args:
            config_file: Path to load config from

        Returns:
            True if successful
        """
        try:
            if not Path(config_file).exists():
                self.logger.warning(f"Configuration file not found: {config_file}")
                return False

            with open(config_file, 'r') as f:
                config = json.load(f)

            async with self.lock:
                # Load peers
                for peer_dict in config.get('peers', []):
                    peer = PeerInfo(
                        hostname=peer_dict['hostname'],
                        address=peer_dict['address'],
                        port=peer_dict['port'],
                        status=PeerStatus[peer_dict['status']],
                        discovery_method=DiscoveryMethod[peer_dict['discovery_method']],
                        capabilities=peer_dict.get('capabilities', []),
                        shared_folders=peer_dict.get('shared_folders', [])
                    )
                    self.peers[peer['hostname']] = peer

                # Load agreements
                for agreement_dict in config.get('folder_agreements', []):
                    agreement = FolderSharingAgreement(
                        folder=agreement_dict['folder'],
                        local_hostname=agreement_dict['local_hostname'],
                        remote_hostname=agreement_dict['remote_hostname'],
                        direction=agreement_dict['direction'],
                        conflict_strategy=agreement_dict.get('conflict_strategy', 'LAST_WRITE_WINS'),
                        sync_interval=agreement_dict.get('sync_interval'),
                        last_sync=agreement_dict.get('last_sync'),
                        enabled=agreement_dict.get('enabled', True)
                    )
                    key = f"{agreement.folder}:{agreement.remote_hostname}"
                    self.folder_agreements[key] = agreement

            self.logger.info(f"Loaded peer configuration from {config_file}")
            return True

        except Exception as e:
            self.logger.error(f"Error loading configuration: {e}")
            return False


# ============================================================================
# Convenience Functions
# ============================================================================

async def create_peer_manager(hostname: str) -> PeerManager:
    """Create new peer manager"""
    return PeerManager(hostname)
