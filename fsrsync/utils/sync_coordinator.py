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
