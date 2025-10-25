"""
Concurrent Transfer Optimizer for FSRsync

Provides intelligent concurrent transfer optimization with:
- Connection pooling and reuse
- Batch transfer optimization
- Parallel transfer scheduling
- Concurrency level auto-tuning
- Transfer prioritization
- Resource-aware scheduling
- Per-connection metrics tracking

## Transfer Optimization Strategies

SEQUENTIAL: Transfer files one at a time
PARALLEL: Transfer multiple files in parallel
BATCHED: Batch small files for efficiency
ADAPTIVE: Auto-select strategy based on workload
"""

import time
import logging
import threading
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict, deque
import statistics
from concurrent.futures import ThreadPoolExecutor


class TransferStrategy(Enum):
    """Transfer strategy"""
    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"
    BATCHED = "batched"
    ADAPTIVE = "adaptive"


@dataclass
class ConnectionMetrics:
    """Metrics for a connection"""
    connection_id: str
    throughput_mbps: float = 0.0
    latency_ms: float = 0.0
    files_transferred: int = 0
    total_bytes: int = 0
    error_count: int = 0
    created_at: float = field(default_factory=time.time)
    last_used: float = field(default_factory=time.time)


@dataclass
class TransferMetrics:
    """Metrics for transfer operation"""
    transfer_id: str
    strategy: TransferStrategy
    file_count: int
    total_size: int
    duration: float
    throughput: float  # MB/s
    parallelism: int
    errors: int = 0
    connection_reuse_count: int = 0


class ConcurrentOptimizer:
    """
    Concurrent transfer optimizer.

    Optimizes parallel file transfers through intelligent
    concurrency management and connection pooling.
    """

    def __init__(self, logger_instance=None):
        """
        Initialize concurrent optimizer.

        Args:
            logger_instance: Logger instance
        """
        self.logger = logger_instance or logging.getLogger(__name__)

        # Connection pool
        self.connection_pool: Dict[str, deque] = defaultdict(lambda: deque(maxlen=20))
        self.connection_metrics: Dict[str, ConnectionMetrics] = {}

        # Transfer tracking
        self.active_transfers: Dict[str, Any] = {}
        self.transfer_history: deque = deque(maxlen=1000)

        # Strategy selection
        self.current_strategy = TransferStrategy.ADAPTIVE
        self.concurrency_level = self._calculate_optimal_concurrency()

        # Thread pool
        self.executor = ThreadPoolExecutor(max_workers=self.concurrency_level)

        # Performance history for tuning
        self.performance_history: deque = deque(maxlen=500)

        self.logger.info("ConcurrentOptimizer initialized")

    def _calculate_optimal_concurrency(self) -> int:
        """Calculate optimal concurrency level"""
        try:
            import os
            cpu_count = os.cpu_count() or 4
            # Use 2-4x CPU count for I/O bound operations
            return min(cpu_count * 3, 16)
        except Exception as e:
            self.logger.error(f"Error calculating concurrency: {e}")
            return 8

    def select_strategy(self, file_count: int, total_size: int,
                      available_bandwidth: float) -> TransferStrategy:
        """
        Select optimal transfer strategy.

        Args:
            file_count: Number of files to transfer
            total_size: Total size in bytes
            available_bandwidth: Available bandwidth in MB/s

        Returns:
            Recommended strategy
        """
        try:
            if file_count == 1:
                return TransferStrategy.SEQUENTIAL

            avg_file_size = total_size / file_count if file_count > 0 else 0

            # Many small files: batch them
            if avg_file_size < 1 * 1024 * 1024 and file_count > 20:  # <1MB files
                return TransferStrategy.BATCHED

            # Few large files: parallel
            if file_count < 5 and avg_file_size > 100 * 1024 * 1024:  # >100MB
                return TransferStrategy.PARALLEL

            # Use adaptive for everything else
            return TransferStrategy.ADAPTIVE

        except Exception as e:
            self.logger.error(f"Error selecting strategy: {e}")
            return TransferStrategy.ADAPTIVE

    def optimize_parallelism(self, file_count: int, total_size: int) -> int:
        """
        Calculate optimal parallelism level.

        Args:
            file_count: Number of files
            total_size: Total size in bytes

        Returns:
            Optimal parallelism level
        """
        try:
            # Base parallelism
            base = min(file_count, self.concurrency_level)

            # Adjust based on file size
            avg_size = total_size / file_count if file_count > 0 else 0

            # Very small files: more parallelism
            if avg_size < 100 * 1024:  # <100KB
                return min(base * 2, self.concurrency_level)

            # Large files: less parallelism
            if avg_size > 1 * 1024 * 1024 * 1024:  # >1GB
                return max(base // 2, 1)

            return base

        except Exception as e:
            self.logger.error(f"Error optimizing parallelism: {e}")
            return self.concurrency_level

    def get_or_create_connection(self, destination: str) -> str:
        """
        Get or create a pooled connection.

        Args:
            destination: Destination identifier

        Returns:
            Connection ID
        """
        try:
            # Try to reuse existing connection
            pool = self.connection_pool[destination]
            if pool:
                conn_id = pool.popleft()
                self.logger.debug(f"Reused connection {conn_id}")
                return conn_id

            # Create new connection
            import uuid
            conn_id = str(uuid.uuid4())
            metrics = ConnectionMetrics(connection_id=conn_id)
            self.connection_metrics[conn_id] = metrics

            self.logger.debug(f"Created new connection {conn_id}")
            return conn_id

        except Exception as e:
            self.logger.error(f"Error getting connection: {e}")
            import uuid
            return str(uuid.uuid4())

    def return_connection(self, destination: str, connection_id: str, success: bool) -> None:
        """
        Return connection to pool.

        Args:
            destination: Destination identifier
            connection_id: Connection ID
            success: Whether connection was successful
        """
        try:
            if success:
                # Return to pool for reuse
                self.connection_pool[destination].append(connection_id)
            else:
                # Don't reuse failed connections
                pass

        except Exception as e:
            self.logger.error(f"Error returning connection: {e}")

    def record_transfer(self, transfer_id: str, strategy: TransferStrategy,
                       file_count: int, total_size: int, duration: float,
                       errors: int = 0) -> None:
        """
        Record transfer metrics.

        Args:
            transfer_id: Transfer identifier
            strategy: Strategy used
            file_count: Number of files
            total_size: Total size transferred
            duration: Transfer duration
            errors: Number of errors
        """
        try:
            throughput = (total_size / (1024 * 1024)) / duration if duration > 0 else 0

            metrics = TransferMetrics(
                transfer_id=transfer_id,
                strategy=strategy,
                file_count=file_count,
                total_size=total_size,
                duration=duration,
                throughput=throughput,
                parallelism=self.concurrency_level,
                errors=errors
            )

            self.transfer_history.append(metrics)
            self.performance_history.append({
                'timestamp': time.time(),
                'throughput': throughput,
                'strategy': strategy.value
            })

            self.logger.info(
                f"Transfer complete: {file_count} files, "
                f"{throughput:.1f} MB/s, {errors} errors"
            )

        except Exception as e:
            self.logger.error(f"Error recording transfer: {e}")

    def auto_tune_concurrency(self) -> None:
        """Auto-tune concurrency level based on recent performance"""
        try:
            if len(self.performance_history) < 5:
                return

            recent = list(self.performance_history)[-10:]
            throughputs = [p['throughput'] for p in recent]
            avg_throughput = statistics.mean(throughputs)

            # If throughput declining, reduce concurrency
            if len(throughputs) > 3:
                trend = (throughputs[-1] - throughputs[0]) / throughputs[0]
                if trend < -0.2:  # >20% decline
                    self.concurrency_level = max(self.concurrency_level - 1, 1)
                    self.executor = ThreadPoolExecutor(max_workers=self.concurrency_level)
                    self.logger.info(f"Reduced concurrency to {self.concurrency_level}")

        except Exception as e:
            self.logger.error(f"Error auto-tuning concurrency: {e}")

    def get_connection_stats(self) -> Dict[str, Any]:
        """Get connection pool statistics"""
        try:
            total_conns = len(self.connection_metrics)
            pooled_conns = sum(len(pool) for pool in self.connection_pool.values())
            active_conns = total_conns - pooled_conns

            reused_conns = sum(
                m.files_transferred for m in self.connection_metrics.values()
            )

            return {
                'timestamp': time.time(),
                'total_connections': total_conns,
                'active_connections': active_conns,
                'pooled_connections': pooled_conns,
                'total_files_via_pooled': reused_conns,
                'connection_reuse_rate': reused_conns / max(1, total_conns)
            }

        except Exception as e:
            self.logger.error(f"Error getting connection stats: {e}")
            return {}

    def get_optimization_summary(self) -> Dict[str, Any]:
        """Get optimization summary"""
        try:
            if not self.transfer_history:
                return {'timestamp': time.time(), 'transfers': 0}

            metrics_list = list(self.transfer_history)
            throughputs = [m.throughput for m in metrics_list]
            durations = [m.duration for m in metrics_list]

            return {
                'timestamp': time.time(),
                'total_transfers': len(metrics_list),
                'average_throughput_mbps': statistics.mean(throughputs),
                'max_throughput_mbps': max(throughputs),
                'average_parallelism': statistics.mean([m.parallelism for m in metrics_list]),
                'average_duration_seconds': statistics.mean(durations),
                'total_errors': sum(m.errors for m in metrics_list),
                'connection_stats': self.get_connection_stats(),
                'current_concurrency': self.concurrency_level
            }

        except Exception as e:
            self.logger.error(f"Error getting summary: {e}")
            return {}
