"""
Sync Coordinator - Orchestrates all advanced FSRsync components

This module brings together all the advanced FSRsync utilities:
- Sync Protocol: Multi-host distributed synchronization
- Peer Manager: Peer discovery and connection management
- Conflict Resolver: Distributed conflict resolution
- Bandwidth Manager: Rate limiting and throttling
- Transfer Engine: Parallel file transfers with integrity
- Queue Manager: Intelligent transfer scheduling
- WebSocket Server: Real-time dashboard updates
- Metrics Collector: Performance metrics and analytics

The SyncCoordinator acts as a central orchestrator that manages the
lifecycle of all components and coordinates their interactions.
"""

import asyncio
import logging
import time
from typing import Dict, Optional, Any, List
from dataclasses import dataclass, field
from enum import Enum

# Import all advanced components
from .sync_protocol import DistributedSyncProtocol
from .peer_manager import PeerManager
from .conflict_resolver import ConflictResolver
from .bandwidth_manager import BandwidthManager
from .transfer_engine import TransferEngine
from .queue_manager import QueueManager
from .websocket_server import WebSocketServer
from .metrics import MetricsCollector

# Import optimization modules (Phase 17)
try:
    from .delta_optimizer import DeltaOptimizer
    from .concurrent_optimizer import ConcurrentOptimizer
    from .adaptive_chunk_sizing import AdaptiveChunkSizer
    from .transfer_connection_pooling import TransferConnectionPooling
    HAS_OPTIMIZERS = True
except ImportError:
    HAS_OPTIMIZERS = False


class CoordinatorState(Enum):
    """State of the sync coordinator"""
    IDLE = "idle"
    STARTING = "starting"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"
    STOPPED = "stopped"


@dataclass
class CoordinatorStatistics:
    """Statistics from the coordinator"""
    state: str
    uptime_seconds: float
    active_transfers: int
    queued_transfers: int
    total_transferred_bytes: int
    bandwidth_usage_mbps: float
    connected_peers: int
    pending_conflicts: int
    success_rate_percent: float
    error_count: int
    peer_stats: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


class SyncCoordinator:
    """
    Orchestrator for all FSRsync advanced components.
    """

    def __init__(self, sync_app=None, host: str = "0.0.0.0", port: int = 9876,
                 logger_instance=None):
        """Initialize the SyncCoordinator"""
        self.logger = logger_instance or logging.getLogger(__name__)
        self.sync_app = sync_app
        self.host = host
        self.port = port
        self.state = CoordinatorState.IDLE
        self.started_at = None

        # Initialize all components
        self.sync_protocol = DistributedSyncProtocol(
            local_hostname=getattr(sync_app, 'hostname', 'local'),
            logger_instance=self.logger
        )

        self.peer_manager = PeerManager(
            local_hostname=getattr(sync_app, 'hostname', 'local'),
            logger_instance=self.logger
        )

        self.conflict_resolver = ConflictResolver(
            logger_instance=self.logger
        )

        self.bandwidth_manager = BandwidthManager(
            logger_instance=self.logger
        )

        self.transfer_engine = TransferEngine(
            logger_instance=self.logger
        )

        self.queue_manager = QueueManager(
            logger_instance=self.logger
        )

        self.websocket_server = WebSocketServer(
            sync_manager=self,
            host=host,
            port=port + 1,
            logger_instance=self.logger
        )

        self.metrics_collector = MetricsCollector(
            logger_instance=self.logger
        )

        # Initialize optimization modules (Phase 17)
        self.delta_optimizer = None
        self.concurrent_optimizer = None
        self.adaptive_chunk_sizer = None
        self.connection_pooling = None

        if HAS_OPTIMIZERS:
            try:
                self.delta_optimizer = DeltaOptimizer(logger_instance=self.logger)
                self.concurrent_optimizer = ConcurrentOptimizer(logger_instance=self.logger)
                self.adaptive_chunk_sizer = AdaptiveChunkSizer(logger_instance=self.logger)
                self.connection_pooling = TransferConnectionPooling(logger_instance=self.logger)
                self.logger.info("Phase 17 optimizers initialized successfully")
            except Exception as e:
                self.logger.warning(f"Failed to initialize optimizers: {e}")

        # Statistics tracking
        self.error_count = 0
        self.success_count = 0
        self.total_transferred_bytes = 0

        self.logger.info(f"SyncCoordinator initialized for {self.host}:{self.port}")

    async def start(self) -> None:
        """Start all coordinator components"""
        try:
            self.state = CoordinatorState.STARTING
            self.logger.info("Starting SyncCoordinator")

            # Start components in order of dependency
            await self.peer_manager.discover_peers()
            self.logger.info(f"Discovered {len(self.peer_manager.peers)} peers")

            # Start WebSocket server for dashboard
            await self.websocket_server.start()
            self.logger.info("WebSocket server started")

            # Start metrics collection
            self.metrics_collector.start()
            self.logger.info("Metrics collection started")

            self.state = CoordinatorState.RUNNING
            self.started_at = time.time()
            self.logger.info("SyncCoordinator running")

        except Exception as e:
            self.logger.error(f"Error starting SyncCoordinator: {e}")
            self.state = CoordinatorState.STOPPED
            raise

    async def stop(self) -> None:
        """Stop all coordinator components gracefully"""
        try:
            self.state = CoordinatorState.STOPPING
            self.logger.info("Stopping SyncCoordinator")

            # Stop components in reverse order
            await self.websocket_server.stop()
            self.metrics_collector.stop()
            await self.transfer_engine.cancel_all_transfers()
            self.queue_manager.clear_queue()

            self.state = CoordinatorState.STOPPED
            self.logger.info("SyncCoordinator stopped")

        except Exception as e:
            self.logger.error(f"Error stopping SyncCoordinator: {e}")

    def get_statistics(self) -> CoordinatorStatistics:
        """Get current coordinator statistics"""
        uptime = (time.time() - self.started_at) if self.started_at else 0
        total_transfers = self.success_count + self.error_count

        return CoordinatorStatistics(
            state=self.state.value,
            uptime_seconds=uptime,
            active_transfers=0,
            queued_transfers=0,
            total_transferred_bytes=self.total_transferred_bytes,
            bandwidth_usage_mbps=0.0,
            connected_peers=len(self.peer_manager.peers),
            pending_conflicts=0,
            success_rate_percent=(
                (self.success_count / total_transfers * 100) if total_transfers > 0 else 100
            ),
            error_count=self.error_count,
            peer_stats={},
            timestamp=time.time()
        )

    def pause(self) -> None:
        """Pause all sync operations"""
        self.state = CoordinatorState.PAUSED
        self.logger.info("SyncCoordinator paused")

    def resume(self) -> None:
        """Resume sync operations"""
        self.state = CoordinatorState.RUNNING
        self.logger.info("SyncCoordinator resumed")

    def is_running(self) -> bool:
        """Check if coordinator is running"""
        return self.state == CoordinatorState.RUNNING

    # ==================== Phase 17 Optimization Methods ====================

    def get_delta_optimization(self, file_path: str, file_size: int,
                              recent_changes: Optional[List[tuple]] = None) -> Optional[Dict[str, Any]]:
        """
        Get delta optimization recommendations for a file.

        Args:
            file_path: Path to file
            file_size: File size in bytes
            recent_changes: List of (offset, length) tuples

        Returns:
            Delta analysis with optimization recommendations
        """
        if not self.delta_optimizer:
            return None

        try:
            analysis = self.delta_optimizer.analyze_file(
                file_path=file_path,
                file_size=file_size,
                recent_changes=recent_changes
            )
            return {
                'file': file_path,
                'strategy': analysis.recommended_strategy.value,
                'chunk_size': analysis.recommended_chunk_size,
                'compression_benefit': analysis.compression_benefit,
                'bandwidth_reduction': analysis.estimated_bandwidth_reduction,
                'confidence': analysis.confidence
            }
        except Exception as e:
            self.logger.error(f"Error getting delta optimization: {e}")
            return None

    def get_concurrent_transfer_strategy(self, file_count: int, total_size: int,
                                        available_bandwidth: float) -> Optional[Dict[str, Any]]:
        """
        Get optimal transfer strategy for multiple files.

        Args:
            file_count: Number of files
            total_size: Total size in bytes
            available_bandwidth: Available bandwidth in MB/s

        Returns:
            Strategy recommendation
        """
        if not self.concurrent_optimizer:
            return None

        try:
            strategy = self.concurrent_optimizer.select_strategy(
                file_count=file_count,
                total_size=total_size,
                available_bandwidth=available_bandwidth
            )
            parallelism = self.concurrent_optimizer.optimize_parallelism(
                file_count=file_count,
                total_size=total_size
            )
            return {
                'strategy': strategy.value,
                'parallelism_level': parallelism,
                'file_count': file_count,
                'total_size_mb': total_size / (1024 * 1024),
                'available_bandwidth_mbps': available_bandwidth
            }
        except Exception as e:
            self.logger.error(f"Error getting transfer strategy: {e}")
            return None

    def get_chunk_size_recommendation(self, file_type: str, file_size: int,
                                     bandwidth_mbps: float, latency_ms: float) -> Optional[Dict[str, Any]]:
        """
        Get adaptive chunk size recommendation.

        Args:
            file_type: Type of file
            file_size: File size in bytes
            bandwidth_mbps: Network bandwidth in MB/s
            latency_ms: Network latency in ms

        Returns:
            Chunk size recommendation
        """
        if not self.adaptive_chunk_sizer:
            return None

        try:
            from .adaptive_chunk_sizing import SizingMetrics, NetworkConditions, SystemResources
            import os
            import psutil

            # Build metrics
            metrics = SizingMetrics(
                file_size=file_size,
                file_type=file_type,
                network_bandwidth=bandwidth_mbps,
                network_latency=latency_ms,
                memory_available=psutil.virtual_memory().available / (1024 * 1024),
                cpu_available=100 - psutil.cpu_percent(interval=0.1)
            )

            # Build network conditions
            network = NetworkConditions(
                bandwidth_mbps=bandwidth_mbps,
                latency_ms=latency_ms
            )

            # Build system resources
            resources = SystemResources(
                available_memory_mb=psutil.virtual_memory().available / (1024 * 1024),
                available_cpu_percent=100 - psutil.cpu_percent(interval=0.1)
            )

            recommendation = self.adaptive_chunk_sizer.recommend_chunk_size(
                metrics=metrics,
                network=network,
                resources=resources
            )

            return {
                'recommended_chunk_size': recommendation.recommended_size,
                'min_size': recommendation.min_size,
                'max_size': recommendation.max_size,
                'strategy': recommendation.strategy.value,
                'confidence': recommendation.confidence,
                'estimated_throughput_mbps': recommendation.estimated_throughput_mbps,
                'reasoning': recommendation.reasoning
            }
        except Exception as e:
            self.logger.error(f"Error getting chunk size recommendation: {e}")
            return None

    def get_connection_for_transfer(self, destination: str) -> Optional[str]:
        """
        Get a connection from the pool for transfer.

        Args:
            destination: Destination identifier

        Returns:
            Connection ID
        """
        if not self.connection_pooling:
            return None

        try:
            return self.connection_pooling.get_connection(destination)
        except Exception as e:
            self.logger.error(f"Error getting connection: {e}")
            return None

    def record_transfer_completion(self, destination: str, connection_id: str,
                                  success: bool, bytes_transferred: int = 0,
                                  duration_seconds: float = 0.0) -> None:
        """
        Record transfer completion and return connection to pool.

        Args:
            destination: Destination identifier
            connection_id: Connection ID
            success: Whether transfer was successful
            bytes_transferred: Bytes transferred
            duration_seconds: Duration of transfer
        """
        if not self.connection_pooling:
            return

        try:
            self.connection_pooling.return_connection(
                destination=destination,
                connection_id=connection_id,
                success=success,
                bytes_transferred=bytes_transferred,
                duration_seconds=duration_seconds
            )
        except Exception as e:
            self.logger.error(f"Error recording transfer: {e}")

    def get_optimization_summary(self) -> Dict[str, Any]:
        """Get optimization summary from all Phase 17 modules"""
        summary = {
            'timestamp': time.time(),
            'optimizers_enabled': HAS_OPTIMIZERS,
            'optimizers': {}
        }

        try:
            if self.delta_optimizer:
                summary['optimizers']['delta'] = self.delta_optimizer.get_optimization_summary()

            if self.concurrent_optimizer:
                summary['optimizers']['concurrent'] = self.concurrent_optimizer.get_optimization_summary()

            if self.adaptive_chunk_sizer:
                summary['optimizers']['chunk_sizing'] = self.adaptive_chunk_sizer.get_optimization_summary()

            if self.connection_pooling:
                summary['optimizers']['connection_pooling'] = self.connection_pooling.get_optimization_summary()

        except Exception as e:
            self.logger.error(f"Error getting optimization summary: {e}")

        return summary
