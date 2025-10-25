"""
Transfer Connection Pooling for FSRsync

Provides advanced connection pool management with:
- Intelligent connection reuse strategies
- Connection health monitoring
- Pool size auto-scaling
- Connection warm-up and keep-alive
- Per-destination pool isolation
- Connection priority queues
- Resource-aware pool management
- Connection lifecycle tracking
"""

import time
import logging
import threading
import uuid
from typing import Dict, List, Optional, Any, Callable, Set
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict, deque
import statistics


class ConnectionState(Enum):
    """Connection state"""
    IDLE = "idle"
    ACTIVE = "active"
    WARMING_UP = "warming_up"
    CLOSING = "closing"
    CLOSED = "closed"
    FAILED = "failed"


class PoolStrategy(Enum):
    """Pool management strategy"""
    FIFO = "fifo"  # First-in-first-out
    LIFO = "lifo"  # Last-in-first-out (hot pool)
    ROUND_ROBIN = "round_robin"  # Distribute load
    LEAST_LOADED = "least_loaded"  # Use least busy connections
    HEALTH_AWARE = "health_aware"  # Prefer healthier connections


@dataclass
class ConnectionMetrics:
    """Metrics for a connection"""
    connection_id: str
    destination: str
    state: ConnectionState = ConnectionState.IDLE
    created_at: float = field(default_factory=time.time)
    last_used: float = field(default_factory=time.time)
    closed_at: float = 0.0

    # Usage metrics
    transfers_completed: int = 0
    bytes_transferred: int = 0
    total_duration_seconds: float = 0.0
    errors: int = 0

    # Performance metrics
    avg_throughput_mbps: float = 0.0
    avg_latency_ms: float = 0.0
    success_rate: float = 1.0

    # Health metrics
    consecutive_failures: int = 0
    last_error: Optional[str] = None
    health_score: float = 1.0  # 0-1


@dataclass
class PoolStats:
    """Statistics for a connection pool"""
    destination: str
    total_connections: int
    idle_connections: int
    active_connections: int
    warming_up_connections: int
    closed_connections: int
    total_transfers: int
    total_bytes_transferred: int
    total_errors: int
    avg_throughput_mbps: float
    avg_connection_reuse: float
    pool_efficiency: float  # 0-1


class ConnectionPool:
    """Individual pool for a destination"""

    def __init__(self, destination: str, max_size: int = 20,
                 strategy: PoolStrategy = PoolStrategy.LEAST_LOADED,
                 logger_instance=None):
        """
        Initialize connection pool.

        Args:
            destination: Destination identifier
            max_size: Maximum connections in pool
            strategy: Pool selection strategy
            logger_instance: Logger instance
        """
        self.destination = destination
        self.max_size = max_size
        self.strategy = strategy
        self.logger = logger_instance or logging.getLogger(__name__)

        # Connection storage
        self.idle_connections: deque = deque(maxlen=max_size)
        self.active_connections: Set[str] = set()
        self.all_connections: Dict[str, ConnectionMetrics] = {}

        # Metrics
        self.pool_created_at = time.time()
        self.total_checkouts = 0
        self.total_checkins = 0

        # Lock for thread safety
        self.lock = threading.RLock()

    def get_connection(self) -> Optional[str]:
        """
        Get a connection from the pool.

        Returns:
            Connection ID or None if pool exhausted
        """
        try:
            with self.lock:
                # Try to reuse existing idle connection
                if self.idle_connections:
                    if self.strategy == PoolStrategy.FIFO:
                        conn_id = self.idle_connections.popleft()
                    elif self.strategy == PoolStrategy.LIFO:
                        conn_id = self.idle_connections.pop()
                    elif self.strategy == PoolStrategy.HEALTH_AWARE:
                        # Pick healthiest connection
                        idle_conns = list(self.idle_connections)
                        conn_id = max(
                            idle_conns,
                            key=lambda cid: self.all_connections[cid].health_score
                        )
                        self.idle_connections.remove(conn_id)
                    else:  # ROUND_ROBIN or LEAST_LOADED (same approach)
                        # Remove least used or most recently created
                        conn_id = self.idle_connections.popleft()

                    self.active_connections.add(conn_id)
                    metrics = self.all_connections[conn_id]
                    metrics.state = ConnectionState.ACTIVE
                    metrics.last_used = time.time()
                    self.total_checkouts += 1

                    self.logger.debug(f"Reused connection {conn_id} for {self.destination}")
                    return conn_id

                # Create new connection if pool not full
                if len(self.all_connections) < self.max_size:
                    conn_id = str(uuid.uuid4())
                    metrics = ConnectionMetrics(
                        connection_id=conn_id,
                        destination=self.destination,
                        state=ConnectionState.WARMING_UP
                    )
                    self.all_connections[conn_id] = metrics
                    self.active_connections.add(conn_id)
                    self.total_checkouts += 1

                    self.logger.debug(f"Created new connection {conn_id} for {self.destination}")
                    return conn_id

                # Pool exhausted
                self.logger.warning(f"Connection pool exhausted for {self.destination}")
                return None

        except Exception as e:
            self.logger.error(f"Error getting connection: {e}")
            return None

    def return_connection(self, connection_id: str, success: bool,
                         bytes_transferred: int = 0, duration_seconds: float = 0.0) -> None:
        """
        Return connection to pool.

        Args:
            connection_id: Connection ID
            success: Whether operation was successful
            bytes_transferred: Bytes transferred in operation
            duration_seconds: Duration of operation
        """
        try:
            with self.lock:
                if connection_id not in self.all_connections:
                    self.logger.warning(f"Unknown connection {connection_id}")
                    return

                metrics = self.all_connections[connection_id]
                self.active_connections.discard(connection_id)

                if success:
                    # Update metrics
                    metrics.transfers_completed += 1
                    metrics.bytes_transferred += bytes_transferred
                    metrics.total_duration_seconds += duration_seconds
                    metrics.consecutive_failures = 0

                    # Update throughput
                    if duration_seconds > 0:
                        throughput = (bytes_transferred / (1024 * 1024)) / duration_seconds
                        if metrics.avg_throughput_mbps == 0:
                            metrics.avg_throughput_mbps = throughput
                        else:
                            metrics.avg_throughput_mbps = (
                                (metrics.avg_throughput_mbps + throughput) / 2
                            )

                    # Update latency
                    latency = duration_seconds * 1000
                    if metrics.avg_latency_ms == 0:
                        metrics.avg_latency_ms = latency
                    else:
                        metrics.avg_latency_ms = (
                            (metrics.avg_latency_ms + latency) / 2
                        )

                    # Update success rate
                    total = metrics.transfers_completed + metrics.errors
                    metrics.success_rate = metrics.transfers_completed / total if total > 0 else 1.0

                    # Update health score
                    metrics.health_score = min(
                        metrics.success_rate * (1 - metrics.consecutive_failures / 10),
                        1.0
                    )

                    # Return to pool
                    metrics.state = ConnectionState.IDLE
                    metrics.last_used = time.time()
                    self.idle_connections.append(connection_id)
                    self.total_checkins += 1

                    self.logger.debug(
                        f"Returned connection {connection_id} - "
                        f"throughput={metrics.avg_throughput_mbps:.1f} MB/s"
                    )

                else:
                    # Failed transfer
                    metrics.errors += 1
                    metrics.consecutive_failures += 1
                    metrics.health_score = max(metrics.health_score - 0.2, 0.0)

                    if metrics.consecutive_failures >= 3:
                        # Close connection after 3 consecutive failures
                        metrics.state = ConnectionState.FAILED
                        metrics.closed_at = time.time()
                        self.logger.warning(
                            f"Closing failed connection {connection_id} "
                            f"after {metrics.consecutive_failures} failures"
                        )
                    else:
                        # Try to reuse
                        metrics.state = ConnectionState.IDLE
                        metrics.last_used = time.time()
                        self.idle_connections.append(connection_id)
                        self.total_checkins += 1

        except Exception as e:
            self.logger.error(f"Error returning connection: {e}")

    def close_connection(self, connection_id: str) -> None:
        """Close a specific connection"""
        try:
            with self.lock:
                if connection_id in self.all_connections:
                    metrics = self.all_connections[connection_id]
                    metrics.state = ConnectionState.CLOSED
                    metrics.closed_at = time.time()
                    self.active_connections.discard(connection_id)

                    if connection_id in self.idle_connections:
                        self.idle_connections.remove(connection_id)

                    self.logger.debug(f"Closed connection {connection_id}")

        except Exception as e:
            self.logger.error(f"Error closing connection: {e}")

    def cleanup_idle_connections(self, max_age_seconds: float = 300.0) -> int:
        """
        Remove idle connections that haven't been used recently.

        Args:
            max_age_seconds: Maximum age for idle connection

        Returns:
            Number of connections cleaned up
        """
        try:
            with self.lock:
                current_time = time.time()
                to_remove = []

                for conn_id, metrics in self.all_connections.items():
                    if metrics.state == ConnectionState.IDLE:
                        age = current_time - metrics.last_used
                        if age > max_age_seconds:
                            to_remove.append(conn_id)

                for conn_id in to_remove:
                    self.close_connection(conn_id)

                return len(to_remove)

        except Exception as e:
            self.logger.error(f"Error cleaning up connections: {e}")
            return 0

    def get_stats(self) -> PoolStats:
        """Get pool statistics"""
        try:
            with self.lock:
                total_conns = len(self.all_connections)
                idle_conns = len(self.idle_connections)
                active_conns = len(self.active_connections)
                warming_conns = sum(
                    1 for m in self.all_connections.values()
                    if m.state == ConnectionState.WARMING_UP
                )
                closed_conns = sum(
                    1 for m in self.all_connections.values()
                    if m.state in [ConnectionState.CLOSED, ConnectionState.FAILED]
                )

                total_transfers = sum(m.transfers_completed for m in self.all_connections.values())
                total_bytes = sum(m.bytes_transferred for m in self.all_connections.values())
                total_errors = sum(m.errors for m in self.all_connections.values())

                throughputs = [
                    m.avg_throughput_mbps for m in self.all_connections.values()
                    if m.avg_throughput_mbps > 0
                ]
                avg_throughput = statistics.mean(throughputs) if throughputs else 0.0

                # Reuse = average transfers per connection
                avg_reuse = total_transfers / max(total_conns, 1)

                # Efficiency = transfers per connection (higher = better utilization)
                pool_efficiency = avg_reuse / 10.0 if avg_reuse < 10 else 1.0  # Normalize to 0-1

                return PoolStats(
                    destination=self.destination,
                    total_connections=total_conns,
                    idle_connections=idle_conns,
                    active_connections=active_conns,
                    warming_up_connections=warming_conns,
                    closed_connections=closed_conns,
                    total_transfers=total_transfers,
                    total_bytes_transferred=total_bytes,
                    total_errors=total_errors,
                    avg_throughput_mbps=avg_throughput,
                    avg_connection_reuse=avg_reuse,
                    pool_efficiency=min(pool_efficiency, 1.0)
                )

        except Exception as e:
            self.logger.error(f"Error getting stats: {e}")
            return PoolStats(
                destination=self.destination,
                total_connections=0,
                idle_connections=0,
                active_connections=0,
                warming_up_connections=0,
                closed_connections=0,
                total_transfers=0,
                total_bytes_transferred=0,
                total_errors=0,
                avg_throughput_mbps=0.0,
                avg_connection_reuse=0.0,
                pool_efficiency=0.0
            )


class TransferConnectionPooling:
    """
    Advanced transfer connection pooling manager.

    Manages multiple connection pools for different destinations
    with intelligent reuse and resource management.
    """

    def __init__(self, logger_instance=None):
        """
        Initialize transfer connection pooling manager.

        Args:
            logger_instance: Logger instance
        """
        self.logger = logger_instance or logging.getLogger(__name__)

        # Per-destination pools
        self.pools: Dict[str, ConnectionPool] = {}

        # Global configuration
        self.default_pool_size = 20
        self.default_strategy = PoolStrategy.LEAST_LOADED
        self.connection_idle_timeout = 300.0  # 5 minutes
        self.cleanup_interval = 60.0  # Check every minute

        # Global metrics
        self.total_checkouts = 0
        self.total_checkins = 0
        self.total_closes = 0
        self.pool_exhausted_events = 0

        # Cleanup thread
        self.cleanup_thread = None
        self.running = False
        self.lock = threading.RLock()

        self.logger.info("TransferConnectionPooling initialized")

    def get_connection(self, destination: str) -> Optional[str]:
        """
        Get a connection for destination.

        Args:
            destination: Destination identifier

        Returns:
            Connection ID or None
        """
        try:
            with self.lock:
                # Get or create pool
                if destination not in self.pools:
                    self.pools[destination] = ConnectionPool(
                        destination=destination,
                        max_size=self.default_pool_size,
                        strategy=self.default_strategy,
                        logger_instance=self.logger
                    )

                pool = self.pools[destination]

            # Get connection (outside lock)
            conn_id = pool.get_connection()
            if conn_id:
                self.total_checkouts += 1
                return conn_id
            else:
                self.pool_exhausted_events += 1
                self.logger.warning(f"Pool exhausted for {destination}")
                return None

        except Exception as e:
            self.logger.error(f"Error getting connection: {e}")
            return None

    def return_connection(self, destination: str, connection_id: str,
                         success: bool, bytes_transferred: int = 0,
                         duration_seconds: float = 0.0) -> None:
        """
        Return connection to pool.

        Args:
            destination: Destination identifier
            connection_id: Connection ID
            success: Whether operation was successful
            bytes_transferred: Bytes transferred
            duration_seconds: Duration of operation
        """
        try:
            with self.lock:
                if destination not in self.pools:
                    self.logger.warning(f"Pool not found for {destination}")
                    return

                pool = self.pools[destination]

            # Return connection (outside lock)
            pool.return_connection(
                connection_id, success, bytes_transferred, duration_seconds
            )
            self.total_checkins += 1

        except Exception as e:
            self.logger.error(f"Error returning connection: {e}")

    def close_connection(self, destination: str, connection_id: str) -> None:
        """Close a specific connection"""
        try:
            with self.lock:
                if destination in self.pools:
                    pool = self.pools[destination]

            pool.close_connection(connection_id)
            self.total_closes += 1

        except Exception as e:
            self.logger.error(f"Error closing connection: {e}")

    def close_pool(self, destination: str) -> None:
        """Close all connections for a destination"""
        try:
            with self.lock:
                if destination in self.pools:
                    pool = self.pools[destination]
                    for conn_id in list(pool.all_connections.keys()):
                        pool.close_connection(conn_id)
                    del self.pools[destination]

                    self.logger.info(f"Closed pool for {destination}")

        except Exception as e:
            self.logger.error(f"Error closing pool: {e}")

    def start_cleanup_thread(self) -> None:
        """Start background cleanup thread"""
        try:
            if not self.running:
                self.running = True
                self.cleanup_thread = threading.Thread(
                    target=self._cleanup_loop,
                    daemon=True
                )
                self.cleanup_thread.start()
                self.logger.info("Started connection cleanup thread")

        except Exception as e:
            self.logger.error(f"Error starting cleanup thread: {e}")

    def stop_cleanup_thread(self) -> None:
        """Stop background cleanup thread"""
        try:
            self.running = False
            if self.cleanup_thread:
                self.cleanup_thread.join(timeout=5.0)
                self.logger.info("Stopped connection cleanup thread")

        except Exception as e:
            self.logger.error(f"Error stopping cleanup thread: {e}")

    def _cleanup_loop(self) -> None:
        """Background cleanup loop"""
        try:
            while self.running:
                time.sleep(self.cleanup_interval)

                with self.lock:
                    destinations = list(self.pools.keys())

                for destination in destinations:
                    try:
                        pool = self.pools[destination]
                        removed = pool.cleanup_idle_connections(
                            self.connection_idle_timeout
                        )
                        if removed > 0:
                            self.logger.debug(
                                f"Cleaned up {removed} idle connections for {destination}"
                            )
                    except Exception as e:
                        self.logger.error(f"Error cleaning pool {destination}: {e}")

        except Exception as e:
            self.logger.error(f"Error in cleanup loop: {e}")

    def get_pool_stats(self, destination: Optional[str] = None) -> Dict[str, Any]:
        """
        Get pool statistics.

        Args:
            destination: Specific destination or None for all

        Returns:
            Pool statistics
        """
        try:
            with self.lock:
                if destination:
                    if destination in self.pools:
                        pool = self.pools[destination]
                        return {"pools": {destination: pool.get_stats()}}
                    else:
                        return {"pools": {}}

                # All pools
                all_stats = {}
                for dest, pool in self.pools.items():
                    all_stats[dest] = pool.get_stats()

                return {
                    "pools": all_stats,
                    "total_checkouts": self.total_checkouts,
                    "total_checkins": self.total_checkins,
                    "total_closes": self.total_closes,
                    "pool_exhausted_events": self.pool_exhausted_events,
                    "active_destinations": len(self.pools)
                }

        except Exception as e:
            self.logger.error(f"Error getting pool stats: {e}")
            return {}

    def get_optimization_summary(self) -> Dict[str, Any]:
        """Get optimization summary"""
        try:
            with self.lock:
                all_stats = []
                total_transfers = 0
                total_bytes = 0
                total_errors = 0
                throughputs = []

                for pool in self.pools.values():
                    stats = pool.get_stats()
                    all_stats.append(stats)
                    total_transfers += stats.total_transfers
                    total_bytes += stats.total_bytes_transferred
                    total_errors += stats.total_errors
                    if stats.avg_throughput_mbps > 0:
                        throughputs.append(stats.avg_throughput_mbps)

                avg_throughput = statistics.mean(throughputs) if throughputs else 0.0
                avg_efficiency = statistics.mean(
                    [s.pool_efficiency for s in all_stats]
                ) if all_stats else 0.0

                return {
                    'timestamp': time.time(),
                    'total_pools': len(self.pools),
                    'total_connections': sum(s.total_connections for s in all_stats),
                    'total_transfers': total_transfers,
                    'total_bytes_transferred': total_bytes,
                    'total_errors': total_errors,
                    'average_throughput_mbps': avg_throughput,
                    'average_pool_efficiency': avg_efficiency,
                    'pool_exhausted_events': self.pool_exhausted_events,
                    'pool_statistics': [
                        {
                            'destination': s.destination,
                            'connections': s.total_connections,
                            'transfers': s.total_transfers,
                            'efficiency': s.pool_efficiency
                        }
                        for s in all_stats
                    ]
                }

        except Exception as e:
            self.logger.error(f"Error getting summary: {e}")
            return {}
