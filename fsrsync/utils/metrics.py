"""
Metrics and Analytics System

Collects, aggregates, and analyzes performance metrics for FSRsync.

## Metrics Categories

1. TRANSFER: File transfer metrics
   - Files transferred, bytes transferred
   - Transfer rate, duration
   - Compression ratio
   - Success rate

2. BANDWIDTH: Network usage metrics
   - Peak usage, average usage
   - Per-peer bandwidth
   - Throttling frequency
   - Latency trends

3. PERFORMANCE: System performance metrics
   - Event processing rate
   - Change detection latency
   - Queue processing time
   - CPU and memory usage

4. RELIABILITY: Reliability metrics
   - Retry rate, failure rate
   - Conflicts resolved, manual conflicts
   - Timeout frequency
   - Recovery success rate

5. PEER: Per-peer metrics
   - Success rate per peer
   - Average latency
   - Bandwidth utilization
   - Uptime percentage

## Time Windows

- Instantaneous: Current value
- 1-minute: Last 60 seconds
- 5-minute: Last 300 seconds
- 1-hour: Last 3600 seconds
- Daily: Last 24 hours
- Lifetime: Since startup

## Examples

```python
collector = MetricsCollector()

# Record transfer
collector.record_transfer(
    peer="remote-host",
    folder="/data",
    file_count=100,
    bytes_transferred=1024*1024*100,
    duration=10.5,
    success=True
)

# Record bandwidth
collector.record_bandwidth(peer="remote-host", bps=50*1024*1024)

# Query metrics
stats_1min = collector.get_metrics(window="1-minute", metric_type="transfer")
stats_lifetime = collector.get_metrics(window="lifetime", metric_type="transfer")

# Export for dashboard
export_data = collector.export_metrics()
```

## Integration Points

- TransferEngine: Reports completion/failure
- BandwidthManager: Reports usage
- SyncCoordinator: Reports processing
- WebSocketServer: Sends metrics updates
- Dashboard: Displays metrics graphs
"""

import logging
import time
from enum import Enum
from typing import Dict, Optional, List, Any, Tuple
from dataclasses import dataclass, field
from collections import deque
import statistics

logger = logging.getLogger(__name__)


# ============================================================================
# Metrics Types
# ============================================================================

class MetricType(Enum):
    """Type of metric"""
    TRANSFER = "TRANSFER"
    BANDWIDTH = "BANDWIDTH"
    PERFORMANCE = "PERFORMANCE"
    RELIABILITY = "RELIABILITY"
    PEER = "PEER"


class TimeWindow(Enum):
    """Time window for aggregation"""
    INSTANT = "instant"
    ONE_MINUTE = "1-minute"
    FIVE_MINUTE = "5-minute"
    ONE_HOUR = "1-hour"
    DAILY = "daily"
    LIFETIME = "lifetime"


@dataclass
class TransferMetric:
    """Transfer metric data point"""
    timestamp: float
    peer: str
    folder: str
    file_count: int
    bytes_transferred: int
    bytes_compressed: int = 0
    duration: float = 0.0
    success: bool = True
    transfer_rate_bps: float = 0.0
    compression_ratio: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        if self.duration > 0:
            rate = self.bytes_transferred / self.duration
        else:
            rate = 0.0

        ratio = 1.0
        if self.bytes_compressed > 0 and self.bytes_transferred > 0:
            ratio = self.bytes_transferred / self.bytes_compressed

        return {
            'timestamp': self.timestamp,
            'peer': self.peer,
            'folder': self.folder,
            'file_count': self.file_count,
            'bytes_transferred': self.bytes_transferred,
            'bytes_compressed': self.bytes_compressed,
            'duration_seconds': self.duration,
            'transfer_rate_bps': rate,
            'transfer_rate_mbps': rate / (1024 * 1024),
            'compression_ratio': ratio,
            'success': self.success
        }


@dataclass
class BandwidthMetric:
    """Bandwidth metric data point"""
    timestamp: float
    peer: str
    bps: float  # Bytes per second
    utilization: float = 0.0  # 0.0-1.0
    peak_bps: float = 0.0
    latency_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'timestamp': self.timestamp,
            'peer': self.peer,
            'bandwidth_bps': self.bps,
            'bandwidth_mbps': self.bps / (1024 * 1024),
            'utilization_percent': self.utilization * 100,
            'peak_bandwidth_mbps': self.peak_bps / (1024 * 1024),
            'latency_ms': self.latency_ms
        }


@dataclass
class PerformanceMetric:
    """Performance metric data point"""
    timestamp: float
    event_processing_rate: float
    change_detection_latency_us: float
    queue_processing_time_ms: float
    cpu_percent: float = 0.0
    memory_mb: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'timestamp': self.timestamp,
            'event_processing_rate': self.event_processing_rate,
            'change_detection_latency_us': self.change_detection_latency_us,
            'queue_processing_time_ms': self.queue_processing_time_ms,
            'cpu_percent': self.cpu_percent,
            'memory_mb': self.memory_mb
        }


@dataclass
class ReliabilityMetric:
    """Reliability metric data point"""
    timestamp: float
    retry_count: int
    failure_count: int
    conflicts_detected: int
    conflicts_resolved: int
    conflicts_manual: int
    timeout_count: int
    recovery_success: int
    recovery_failed: int

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        total_retries = max(1, self.retry_count)
        retry_rate = (self.retry_count / (self.retry_count + self.failure_count)) if (self.retry_count + self.failure_count) > 0 else 0
        conflict_resolution_rate = (self.conflicts_resolved / self.conflicts_detected) if self.conflicts_detected > 0 else 1.0

        return {
            'timestamp': self.timestamp,
            'retry_count': self.retry_count,
            'failure_count': self.failure_count,
            'retry_rate': retry_rate,
            'conflicts_detected': self.conflicts_detected,
            'conflicts_resolved': self.conflicts_resolved,
            'conflicts_manual': self.conflicts_manual,
            'conflict_resolution_rate': conflict_resolution_rate,
            'timeout_count': self.timeout_count,
            'recovery_success': self.recovery_success,
            'recovery_failed': self.recovery_failed
        }


@dataclass
class PeerMetric:
    """Per-peer metric data point"""
    timestamp: float
    peer: str
    success_count: int
    failure_count: int
    average_latency_ms: float
    bandwidth_utilization: float = 0.0
    uptime_percent: float = 100.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        total = self.success_count + self.failure_count
        success_rate = (self.success_count / total) if total > 0 else 0.0

        return {
            'timestamp': self.timestamp,
            'peer': self.peer,
            'success_count': self.success_count,
            'failure_count': self.failure_count,
            'success_rate': success_rate,
            'average_latency_ms': self.average_latency_ms,
            'bandwidth_utilization_percent': self.bandwidth_utilization * 100,
            'uptime_percent': self.uptime_percent
        }


# ============================================================================
# Metrics Collector
# ============================================================================

class MetricsCollector:
    """
    Collects and aggregates metrics for FSRsync.

    Maintains rolling windows of metrics for analysis and reporting.
    """

    def __init__(self, logger=None, retention_seconds: int = 86400):
        """
        Initialize metrics collector.

        Args:
            logger: Logger instance
            retention_seconds: How long to keep metrics (24 hours default)
        """
        self.logger = logger or logging.getLogger(__name__)
        self.retention_seconds = retention_seconds
        self.started_at = time.time()

        # Metric storage (deques for rolling windows)
        self.transfers: deque = deque()
        self.bandwidth: deque = deque()
        self.performance: deque = deque()
        self.reliability: deque = deque()
        self.peers: deque = deque()

        # Aggregated statistics
        self.lifetime_stats = {
            'transfers': 0,
            'bytes_transferred': 0,
            'compression_savings': 0,
            'conflicts': 0,
            'retries': 0,
            'failures': 0
        }

    def record_transfer(self, peer: str, folder: str, file_count: int,
                       bytes_transferred: int, bytes_compressed: int = 0,
                       duration: float = 0.0, success: bool = True) -> None:
        """
        Record file transfer metric.

        Args:
            peer: Target peer
            folder: Sync folder
            file_count: Number of files
            bytes_transferred: Bytes transferred
            bytes_compressed: Bytes after compression
            duration: Transfer duration
            success: Whether transfer succeeded
        """
        metric = TransferMetric(
            timestamp=time.time(),
            peer=peer,
            folder=folder,
            file_count=file_count,
            bytes_transferred=bytes_transferred,
            bytes_compressed=bytes_compressed,
            duration=duration,
            success=success
        )

        self.transfers.append(metric)
        self._cleanup_old_metrics(self.transfers)

        # Update lifetime stats
        if success:
            self.lifetime_stats['transfers'] += file_count
            self.lifetime_stats['bytes_transferred'] += bytes_transferred
            if bytes_compressed > 0:
                self.lifetime_stats['compression_savings'] += (bytes_transferred - bytes_compressed)

        self.logger.debug(f"Recorded transfer: {peer}:{folder} - {file_count} files")

    def record_bandwidth(self, peer: str, bps: float, utilization: float = 0.0,
                        peak_bps: float = 0.0, latency_ms: float = 0.0) -> None:
        """
        Record bandwidth metric.

        Args:
            peer: Target peer
            bps: Bandwidth in bytes per second
            utilization: Utilization ratio (0.0-1.0)
            peak_bps: Peak bandwidth in this period
            latency_ms: Network latency
        """
        metric = BandwidthMetric(
            timestamp=time.time(),
            peer=peer,
            bps=bps,
            utilization=utilization,
            peak_bps=peak_bps,
            latency_ms=latency_ms
        )

        self.bandwidth.append(metric)
        self._cleanup_old_metrics(self.bandwidth)

    def record_performance(self, event_processing_rate: float,
                          change_detection_latency_us: float,
                          queue_processing_time_ms: float,
                          cpu_percent: float = 0.0, memory_mb: float = 0.0) -> None:
        """Record performance metric"""
        metric = PerformanceMetric(
            timestamp=time.time(),
            event_processing_rate=event_processing_rate,
            change_detection_latency_us=change_detection_latency_us,
            queue_processing_time_ms=queue_processing_time_ms,
            cpu_percent=cpu_percent,
            memory_mb=memory_mb
        )

        self.performance.append(metric)
        self._cleanup_old_metrics(self.performance)

    def record_reliability(self, retry_count: int, failure_count: int,
                          conflicts_detected: int, conflicts_resolved: int,
                          conflicts_manual: int = 0, timeout_count: int = 0,
                          recovery_success: int = 0, recovery_failed: int = 0) -> None:
        """Record reliability metric"""
        metric = ReliabilityMetric(
            timestamp=time.time(),
            retry_count=retry_count,
            failure_count=failure_count,
            conflicts_detected=conflicts_detected,
            conflicts_resolved=conflicts_resolved,
            conflicts_manual=conflicts_manual,
            timeout_count=timeout_count,
            recovery_success=recovery_success,
            recovery_failed=recovery_failed
        )

        self.reliability.append(metric)
        self._cleanup_old_metrics(self.reliability)

        # Update lifetime stats
        self.lifetime_stats['conflicts'] += conflicts_detected
        self.lifetime_stats['retries'] += retry_count
        self.lifetime_stats['failures'] += failure_count

    def record_peer_metric(self, peer: str, success_count: int, failure_count: int,
                          average_latency_ms: float, bandwidth_utilization: float = 0.0,
                          uptime_percent: float = 100.0) -> None:
        """Record per-peer metric"""
        metric = PeerMetric(
            timestamp=time.time(),
            peer=peer,
            success_count=success_count,
            failure_count=failure_count,
            average_latency_ms=average_latency_ms,
            bandwidth_utilization=bandwidth_utilization,
            uptime_percent=uptime_percent
        )

        self.peers.append(metric)
        self._cleanup_old_metrics(self.peers)

    def _cleanup_old_metrics(self, metrics_deque: deque) -> None:
        """Remove metrics older than retention period"""
        cutoff_time = time.time() - self.retention_seconds

        while metrics_deque and metrics_deque[0].timestamp < cutoff_time:
            metrics_deque.popleft()

    def get_metrics(self, metric_type: MetricType,
                   window: TimeWindow = TimeWindow.LIFETIME,
                   peer: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get metrics for analysis.

        Args:
            metric_type: Type of metrics to retrieve
            window: Time window to filter
            peer: Optional peer filter

        Returns:
            List of metric dictionaries
        """
        if metric_type == MetricType.TRANSFER:
            metrics = list(self.transfers)
        elif metric_type == MetricType.BANDWIDTH:
            metrics = list(self.bandwidth)
        elif metric_type == MetricType.PERFORMANCE:
            metrics = list(self.performance)
        elif metric_type == MetricType.RELIABILITY:
            metrics = list(self.reliability)
        elif metric_type == MetricType.PEER:
            metrics = list(self.peers)
        else:
            return []

        # Filter by time window
        filtered = self._filter_by_window(metrics, window)

        # Filter by peer if specified
        if peer and hasattr(filtered[0] if filtered else None, 'peer'):
            filtered = [m for m in filtered if m.peer == peer]

        return [m.to_dict() for m in filtered]

    def _filter_by_window(self, metrics: List, window: TimeWindow) -> List:
        """Filter metrics by time window"""
        if window == TimeWindow.LIFETIME or not metrics:
            return metrics

        now = time.time()
        window_seconds = {
            TimeWindow.INSTANT: 1,
            TimeWindow.ONE_MINUTE: 60,
            TimeWindow.FIVE_MINUTE: 300,
            TimeWindow.ONE_HOUR: 3600,
            TimeWindow.DAILY: 86400,
        }.get(window, self.retention_seconds)

        cutoff = now - window_seconds
        return [m for m in metrics if m.timestamp >= cutoff]

    def get_summary_statistics(self) -> Dict[str, Any]:
        """Get summary statistics"""
        uptime = time.time() - self.started_at

        # Calculate averages
        transfer_metrics = list(self.transfers)
        if transfer_metrics:
            avg_transfer_rate = statistics.mean(
                [m.bytes_transferred / m.duration for m in transfer_metrics if m.duration > 0]
            ) if transfer_metrics else 0
        else:
            avg_transfer_rate = 0

        bandwidth_metrics = list(self.bandwidth)
        if bandwidth_metrics:
            avg_bandwidth = statistics.mean([m.bps for m in bandwidth_metrics])
            peak_bandwidth = max([m.peak_bps for m in bandwidth_metrics])
        else:
            avg_bandwidth = peak_bandwidth = 0

        return {
            'uptime_seconds': uptime,
            'started_at': self.started_at,
            'lifetime_stats': self.lifetime_stats.copy(),
            'average_transfer_rate_bps': avg_transfer_rate,
            'average_bandwidth_mbps': avg_bandwidth / (1024 * 1024),
            'peak_bandwidth_mbps': peak_bandwidth / (1024 * 1024),
            'total_peers': len(set(p.peer for p in self.peers)) if self.peers else 0,
            'total_transfers': len(self.transfers),
            'total_bandwidth_records': len(self.bandwidth),
            'total_reliability_records': len(self.reliability)
        }

    def export_metrics(self) -> Dict[str, Any]:
        """Export all metrics for external use"""
        return {
            'timestamp': time.time(),
            'summary': self.get_summary_statistics(),
            'transfers': [m.to_dict() for m in list(self.transfers)[-100:]],
            'bandwidth': [m.to_dict() for m in list(self.bandwidth)[-100:]],
            'performance': [m.to_dict() for m in list(self.performance)[-100:]],
            'reliability': [m.to_dict() for m in list(self.reliability)[-100:]],
            'peers': [m.to_dict() for m in list(self.peers)[-100:]]
        }

    def clear_metrics(self) -> None:
        """Clear all metrics"""
        self.transfers.clear()
        self.bandwidth.clear()
        self.performance.clear()
        self.reliability.clear()
        self.peers.clear()


# ============================================================================
# Convenience Functions
# ============================================================================

def create_metrics_collector(retention_seconds: int = 86400) -> MetricsCollector:
    """Create new metrics collector"""
    return MetricsCollector(retention_seconds=retention_seconds)
