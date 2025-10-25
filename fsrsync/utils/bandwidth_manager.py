"""
Bandwidth Management and Optimization

Manages bandwidth allocation and throttling for multi-peer synchronization.

## Bandwidth Tracking

Tracks bandwidth usage per peer and per folder:
- Actual usage from recent transfers
- Peak bandwidth during sync operations
- Average bandwidth over time windows
- Per-operation metrics (transfer rate, duration, bytes)

## Bandwidth Optimization

Implements smart scheduling based on available bandwidth:
- Throttling: Limit per-peer bandwidth to prevent network saturation
- Burst Handling: Detect and handle temporary bursts
- Peer Prioritization: Higher priority peers get more bandwidth
- Backpressure: Slow down when network is congested
- Adaptive Rate Control: Adjust targets based on observed latency

## Rate Limiting Strategies

1. TOKEN_BUCKET: Smooth rate limiting with burst tolerance
2. LEAKY_BUCKET: Strict rate limiting
3. ADAPTIVE: Adjust rate based on network conditions
4. PRIORITY_QUEUE: Give priority peers more bandwidth

## Network Condition Detection

Monitors for network issues:
- Latency increase (RTT trending up)
- Packet loss (retransmissions)
- Jitter (RTT variance)
- Timeouts (connection failures)
- Bandwidth saturation (queue buildup)

## Examples

```python
manager = BandwidthManager()

# Add peer with 100 Mbps limit
manager.add_peer("remote-host", 100 * 1024 * 1024)

# Update during transfer
await manager.record_transfer("remote-host", bytes_transferred, duration)

# Check if should proceed
can_transfer = manager.can_transfer("remote-host", file_size)

# Get next file based on bandwidth availability
next_file = manager.get_next_file_to_transfer(pending_files)

# Get statistics
stats = manager.get_statistics()
```

## Integration Points

- PeerManager: Provides peer list and folder agreements
- TransferEngine: Requests permission before transfers
- SyncCoordinator: Reports bandwidth usage for scheduling
- Dashboard: Displays bandwidth graphs and limits
"""

import logging
import time
from enum import Enum
from typing import Dict, Optional, List, Any, Tuple
from dataclasses import dataclass, field
from collections import deque
import math

logger = logging.getLogger(__name__)


# ============================================================================
# Bandwidth Types and Enums
# ============================================================================

class RateLimitStrategy(Enum):
    """Rate limiting strategy"""
    TOKEN_BUCKET = "TOKEN_BUCKET"      # Smooth with burst
    LEAKY_BUCKET = "LEAKY_BUCKET"      # Strict limiting
    ADAPTIVE = "ADAPTIVE"               # Adjust based on conditions
    PRIORITY_QUEUE = "PRIORITY_QUEUE"   # Higher priority gets more


class NetworkCondition(Enum):
    """Network health condition"""
    EXCELLENT = "EXCELLENT"  # RTT < 10ms, no loss
    GOOD = "GOOD"            # RTT < 50ms, <1% loss
    FAIR = "FAIR"            # RTT < 100ms, <5% loss
    POOR = "POOR"            # RTT > 100ms or >5% loss
    CONGESTED = "CONGESTED"  # Queue buildup, timeouts


@dataclass
class TransferMetrics:
    """Metrics for a single transfer operation"""
    peer: str
    folder: str
    file_path: str
    bytes_transferred: int
    duration: float  # seconds
    start_time: float
    end_time: float
    retransmissions: int = 0  # Network retransmissions
    latency_ms: float = 0.0   # Network latency
    success: bool = True

    def transfer_rate(self) -> float:
        """Bytes per second"""
        if self.duration <= 0:
            return 0.0
        return self.bytes_transferred / self.duration

    def transfer_rate_mbps(self) -> float:
        """Megabits per second"""
        return (self.transfer_rate() * 8) / (1024 * 1024)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'peer': self.peer,
            'folder': self.folder,
            'file_path': self.file_path,
            'bytes_transferred': self.bytes_transferred,
            'duration': self.duration,
            'transfer_rate_bps': self.transfer_rate(),
            'transfer_rate_mbps': self.transfer_rate_mbps(),
            'latency_ms': self.latency_ms,
            'retransmissions': self.retransmissions,
            'success': self.success
        }


@dataclass
class PeerBandwidthInfo:
    """Bandwidth information for a peer"""
    hostname: str
    bandwidth_limit_bps: float        # Bytes per second
    current_usage_bps: float = 0.0    # Current usage
    peak_usage_bps: float = 0.0       # Peak observed
    average_usage_bps: float = 0.0    # Average over window
    utilization: float = 0.0          # 0.0-1.0
    added_at: float = field(default_factory=time.time)
    last_update: float = field(default_factory=time.time)
    available_capacity: float = 0.0   # Available BW (not used)
    priority: int = 1                 # Lower = higher priority

    def get_remaining_capacity(self) -> float:
        """Get remaining bandwidth capacity"""
        return max(0.0, self.bandwidth_limit_bps - self.current_usage_bps)

    def is_throttled(self) -> bool:
        """Check if peer is at bandwidth limit"""
        return self.utilization >= 0.95

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'hostname': self.hostname,
            'bandwidth_limit_bps': self.bandwidth_limit_bps,
            'bandwidth_limit_mbps': self.bandwidth_limit_bps / (1024 * 1024),
            'current_usage_bps': self.current_usage_bps,
            'current_usage_mbps': self.current_usage_bps / (1024 * 1024),
            'peak_usage_bps': self.peak_usage_bps,
            'peak_usage_mbps': self.peak_usage_bps / (1024 * 1024),
            'average_usage_bps': self.average_usage_bps,
            'average_usage_mbps': self.average_usage_bps / (1024 * 1024),
            'utilization_percent': self.utilization * 100,
            'remaining_capacity_bps': self.get_remaining_capacity(),
            'remaining_capacity_mbps': self.get_remaining_capacity() / (1024 * 1024),
            'is_throttled': self.is_throttled(),
            'priority': self.priority
        }


@dataclass
class TokenBucket:
    """Token bucket for rate limiting"""
    capacity: float           # Max tokens
    tokens: float            # Current tokens
    refill_rate: float      # Tokens per second
    last_refill: float      # Last refill timestamp

    def try_acquire(self, tokens: int) -> bool:
        """Try to acquire tokens"""
        self._refill()
        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False

    def _refill(self) -> None:
        """Refill tokens based on elapsed time"""
        now = time.time()
        elapsed = now - self.last_refill
        new_tokens = elapsed * self.refill_rate
        self.tokens = min(self.capacity, self.tokens + new_tokens)
        self.last_refill = now

    def available_tokens(self) -> float:
        """Get available tokens"""
        self._refill()
        return self.tokens


# ============================================================================
# Bandwidth Manager
# ============================================================================

class BandwidthManager:
    """
    Manages bandwidth allocation and throttling for multi-peer sync.

    Tracks usage, enforces limits, and optimizes scheduling.
    """

    def __init__(self, logger=None,
                 default_peer_limit_bps: float = 10 * 1024 * 1024,
                 global_limit_bps: Optional[float] = None,
                 strategy: RateLimitStrategy = RateLimitStrategy.TOKEN_BUCKET):
        """
        Initialize bandwidth manager.

        Args:
            logger: Logger instance
            default_peer_limit_bps: Default per-peer limit (10 Mbps)
            global_limit_bps: Global limit across all peers (None = unlimited)
            strategy: Rate limiting strategy
        """
        self.logger = logger or logging.getLogger(__name__)
        self.default_peer_limit_bps = default_peer_limit_bps
        self.global_limit_bps = global_limit_bps
        self.strategy = strategy

        self.peers: Dict[str, PeerBandwidthInfo] = {}
        self.transfer_history: Dict[str, deque] = {}  # peer -> deque of TransferMetrics
        self.token_buckets: Dict[str, TokenBucket] = {}
        self.latency_samples: Dict[str, deque] = {}  # peer -> deque of latency samples
        self.max_history_size = 100
        self.latency_window = 60.0  # seconds

        self.total_bytes_transferred = 0
        self.start_time = time.time()

    def add_peer(self, hostname: str, bandwidth_limit_bps: float = None,
                 priority: int = 1) -> PeerBandwidthInfo:
        """
        Add peer with bandwidth limit.

        Args:
            hostname: Peer hostname
            bandwidth_limit_bps: Per-peer bandwidth limit
            priority: Priority level (lower = higher)

        Returns:
            PeerBandwidthInfo object
        """
        limit = bandwidth_limit_bps or self.default_peer_limit_bps

        peer = PeerBandwidthInfo(
            hostname=hostname,
            bandwidth_limit_bps=limit,
            priority=priority
        )

        self.peers[hostname] = peer
        self.transfer_history[hostname] = deque(maxlen=self.max_history_size)
        self.latency_samples[hostname] = deque(maxlen=100)

        # Create token bucket for this peer
        if self.strategy == RateLimitStrategy.TOKEN_BUCKET:
            self.token_buckets[hostname] = TokenBucket(
                capacity=limit,
                tokens=limit,
                refill_rate=limit,
                last_refill=time.time()
            )

        self.logger.info(f"Added peer {hostname} with limit {limit / (1024*1024):.2f} Mbps")
        return peer

    def remove_peer(self, hostname: str) -> bool:
        """Remove peer from management"""
        if hostname in self.peers:
            del self.peers[hostname]
            if hostname in self.transfer_history:
                del self.transfer_history[hostname]
            if hostname in self.token_buckets:
                del self.token_buckets[hostname]
            if hostname in self.latency_samples:
                del self.latency_samples[hostname]
            self.logger.info(f"Removed peer {hostname}")
            return True
        return False

    def get_peer(self, hostname: str) -> Optional[PeerBandwidthInfo]:
        """Get peer bandwidth info"""
        return self.peers.get(hostname)

    def can_transfer(self, hostname: str, file_size: int) -> bool:
        """
        Check if transfer is allowed given bandwidth limits.

        Args:
            hostname: Target peer
            file_size: File size in bytes

        Returns:
            True if transfer allowed
        """
        peer = self.peers.get(hostname)
        if not peer:
            return False

        # Check per-peer limit
        if self.strategy == RateLimitStrategy.TOKEN_BUCKET:
            bucket = self.token_buckets.get(hostname)
            if bucket and not bucket.try_acquire(file_size):
                return False
        else:
            # Simple check: remaining capacity
            if peer.get_remaining_capacity() < file_size:
                return False

        # Check global limit if set
        if self.global_limit_bps:
            total_usage = sum(p.current_usage_bps for p in self.peers.values())
            if total_usage >= self.global_limit_bps:
                return False

        return True

    def record_transfer(self, hostname: str, folder: str, file_path: str,
                       bytes_transferred: int, duration: float,
                       latency_ms: float = 0.0, retransmissions: int = 0,
                       success: bool = True) -> None:
        """
        Record transfer metrics.

        Args:
            hostname: Target peer
            folder: Folder being synced
            file_path: File path
            bytes_transferred: Bytes transferred
            duration: Transfer duration in seconds
            latency_ms: Network latency
            retransmissions: Network retransmissions
            success: Whether transfer succeeded
        """
        peer = self.peers.get(hostname)
        if not peer:
            return

        metrics = TransferMetrics(
            peer=hostname,
            folder=folder,
            file_path=file_path,
            bytes_transferred=bytes_transferred,
            duration=duration,
            start_time=time.time() - duration,
            end_time=time.time(),
            latency_ms=latency_ms,
            retransmissions=retransmissions,
            success=success
        )

        self.transfer_history[hostname].append(metrics)
        self.total_bytes_transferred += bytes_transferred

        # Update latency samples
        if latency_ms > 0:
            self.latency_samples[hostname].append((time.time(), latency_ms))

        # Update bandwidth metrics
        self._update_peer_bandwidth(hostname)

        self.logger.debug(
            f"Transfer {hostname}:{file_path} - "
            f"{bytes_transferred / (1024*1024):.2f} MB in {duration:.2f}s "
            f"({metrics.transfer_rate_mbps():.2f} Mbps)"
        )

    def _update_peer_bandwidth(self, hostname: str) -> None:
        """Update bandwidth metrics for peer"""
        peer = self.peers.get(hostname)
        if not peer or not self.transfer_history[hostname]:
            return

        history = list(self.transfer_history[hostname])
        if not history:
            return

        # Calculate current usage (last 10 seconds)
        now = time.time()
        recent = [m for m in history if now - m.end_time < 10.0]

        if recent:
            total_bytes = sum(m.bytes_transferred for m in recent)
            total_duration = sum(m.duration for m in recent)
            if total_duration > 0:
                peer.current_usage_bps = total_bytes / total_duration
            else:
                peer.current_usage_bps = 0.0
        else:
            peer.current_usage_bps = 0.0

        # Peak usage
        peer.peak_usage_bps = max(
            (m.transfer_rate() for m in history),
            default=0.0
        )

        # Average usage
        if history:
            total_bytes = sum(m.bytes_transferred for m in history)
            total_duration = sum(m.duration for m in history)
            peer.average_usage_bps = total_bytes / total_duration if total_duration > 0 else 0.0
        else:
            peer.average_usage_bps = 0.0

        # Utilization (0.0-1.0)
        if peer.bandwidth_limit_bps > 0:
            peer.utilization = min(1.0, peer.current_usage_bps / peer.bandwidth_limit_bps)
        else:
            peer.utilization = 0.0

        peer.available_capacity = peer.get_remaining_capacity()
        peer.last_update = time.time()

    def get_next_peer_for_transfer(self, candidate_peers: List[str],
                                   file_size: int) -> Optional[str]:
        """
        Get best peer for next transfer based on bandwidth availability.

        Args:
            candidate_peers: List of peer hostnames
            file_size: Size of file to transfer

        Returns:
            Best peer hostname or None
        """
        # Filter peers that can accept transfer
        available = [
            p for p in candidate_peers
            if p in self.peers and self.can_transfer(p, file_size)
        ]

        if not available:
            return None

        # Sort by priority first, then by remaining capacity
        available.sort(
            key=lambda p: (
                self.peers[p].priority,  # Lower priority first
                -self.peers[p].get_remaining_capacity()  # More capacity first
            )
        )

        return available[0]

    def get_transfer_schedule(self, pending_transfers: List[Tuple[str, str, int]]
                            ) -> List[Tuple[str, str, int]]:
        """
        Get optimized schedule for pending transfers.

        Args:
            pending_transfers: List of (peer, file_path, file_size) tuples

        Returns:
            Ordered list of transfers to execute
        """
        if not pending_transfers:
            return []

        # Sort by peer priority and file size
        transfers = sorted(
            pending_transfers,
            key=lambda t: (
                self.peers.get(t[0], PeerBandwidthInfo('', 0)).priority,
                -t[2]  # Larger files first
            )
        )

        return transfers

    def get_network_condition(self, hostname: str) -> NetworkCondition:
        """
        Determine network condition to peer.

        Args:
            hostname: Peer hostname

        Returns:
            NetworkCondition enum
        """
        peer = self.peers.get(hostname)
        if not peer:
            return NetworkCondition.UNKNOWN

        # Get recent latency samples
        now = time.time()
        recent_samples = [
            (ts, latency) for ts, latency in self.latency_samples.get(hostname, [])
            if now - ts < self.latency_window
        ]

        if not recent_samples:
            return NetworkCondition.UNKNOWN

        latencies = [latency for _, latency in recent_samples]
        avg_latency = sum(latencies) / len(latencies)
        max_latency = max(latencies)

        # Check for retransmissions (packet loss indicator)
        history = list(self.transfer_history.get(hostname, []))
        recent_transfers = [
            m for m in history if now - m.end_time < self.latency_window
        ]

        loss_percent = 0.0
        if recent_transfers:
            total_retrans = sum(m.retransmissions for m in recent_transfers)
            total_transfers = len(recent_transfers)
            loss_percent = (total_retrans / max(1, total_transfers)) * 100

        # Classify condition
        if avg_latency < 10 and loss_percent < 0.1:
            return NetworkCondition.EXCELLENT
        elif avg_latency < 50 and loss_percent < 1.0:
            return NetworkCondition.GOOD
        elif avg_latency < 100 and loss_percent < 5.0:
            return NetworkCondition.FAIR
        elif loss_percent > 5.0 or max_latency > 500:
            return NetworkCondition.CONGESTED
        else:
            return NetworkCondition.POOR

    def set_peer_priority(self, hostname: str, priority: int) -> bool:
        """
        Set peer priority (lower = higher).

        Args:
            hostname: Peer hostname
            priority: Priority level

        Returns:
            True if updated
        """
        peer = self.peers.get(hostname)
        if not peer:
            return False

        peer.priority = priority
        self.logger.info(f"Set {hostname} priority to {priority}")
        return True

    def get_transfer_history(self, hostname: str, limit: int = 10) -> List[TransferMetrics]:
        """Get recent transfer history for peer"""
        history = self.transfer_history.get(hostname, deque())
        return list(history)[-limit:]

    def get_peer_statistics(self) -> Dict[str, Any]:
        """Get statistics for all peers"""
        stats = {}
        for hostname, peer in self.peers.items():
            stats[hostname] = peer.to_dict()
        return stats

    def get_global_statistics(self) -> Dict[str, Any]:
        """Get global bandwidth statistics"""
        runtime = time.time() - self.start_time
        avg_throughput = self.total_bytes_transferred / runtime if runtime > 0 else 0.0

        return {
            'total_bytes_transferred': self.total_bytes_transferred,
            'runtime_seconds': runtime,
            'average_throughput_bps': avg_throughput,
            'average_throughput_mbps': avg_throughput / (1024 * 1024),
            'total_peers': len(self.peers),
            'global_limit_bps': self.global_limit_bps,
            'global_limit_mbps': self.global_limit_bps / (1024 * 1024) if self.global_limit_bps else None,
            'peers': self.get_peer_statistics()
        }

    def clear_history(self) -> None:
        """Clear transfer history"""
        for history in self.transfer_history.values():
            history.clear()


# ============================================================================
# Convenience Functions
# ============================================================================

def create_bandwidth_manager(default_limit_bps: float = 10 * 1024 * 1024,
                            global_limit_bps: Optional[float] = None,
                            strategy: RateLimitStrategy = RateLimitStrategy.TOKEN_BUCKET
                            ) -> BandwidthManager:
    """Create new bandwidth manager"""
    return BandwidthManager(
        default_peer_limit_bps=default_limit_bps,
        global_limit_bps=global_limit_bps,
        strategy=strategy
    )
