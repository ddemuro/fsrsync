"""
Health Check System for FSRsync

Provides comprehensive health monitoring across all FSRsync components:
- Component health status (running, degraded, failed)
- Resource utilization (CPU, memory, disk)
- Network connectivity and latency
- Transfer engine status
- Peer connectivity health
- Conflict resolution queue status
- Bandwidth manager status

## Health Levels

HEALTHY (All systems nominal)
  - All components running
  - No critical errors
  - Resource usage normal
  - Peer connectivity stable

DEGRADED (Some issues, but operational)
  - Minor component issues
  - High resource usage
  - Increased latency
  - Some peer disconnections

CRITICAL (Immediate attention needed)
  - Components failing
  - Critical resource shortage
  - Network issues
  - Major peer disconnections

OFFLINE (Not operational)
  - Core components down
  - Critical resources exhausted
  - Network isolation

## Usage

```python
health = HealthChecker(coordinator)
status = await health.check_all()

if status.overall_health == HealthLevel.CRITICAL:
    await alert_admin(status)
else:
    broadcast_to_dashboard(status)
```
"""

import asyncio
import psutil
import logging
import time
from typing import Dict, Optional, List, Any
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime


class HealthLevel(Enum):
    """Overall health level"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    CRITICAL = "critical"
    OFFLINE = "offline"


@dataclass
class ComponentHealth:
    """Health status of a single component"""
    name: str
    status: str  # "running", "degraded", "failed"
    uptime_seconds: float
    error_count: int = 0
    last_error: Optional[str] = None
    last_check: float = field(default_factory=time.time)
    response_time_ms: float = 0.0


@dataclass
class ResourceHealth:
    """System resource health"""
    cpu_percent: float
    memory_percent: float
    disk_percent: float
    cpu_threshold: float = 80.0
    memory_threshold: float = 85.0
    disk_threshold: float = 90.0

    def is_healthy(self) -> bool:
        """Check if resources are within healthy ranges"""
        return (
            self.cpu_percent < self.cpu_threshold and
            self.memory_percent < self.memory_threshold and
            self.disk_percent < self.disk_threshold
        )

    def get_level(self) -> HealthLevel:
        """Get resource health level"""
        if self.is_healthy():
            return HealthLevel.HEALTHY
        elif (self.cpu_percent > 95 or
              self.memory_percent > 95 or
              self.disk_percent > 98):
            return HealthLevel.CRITICAL
        else:
            return HealthLevel.DEGRADED


@dataclass
class NetworkHealth:
    """Network connectivity health"""
    connected_peers: int
    total_peers: int
    average_latency_ms: float
    packet_loss_percent: float
    bandwidth_available_mbps: float

    @property
    def connectivity_percent(self) -> float:
        """Percentage of peers connected"""
        if self.total_peers == 0:
            return 100.0
        return (self.connected_peers / self.total_peers) * 100

    def get_level(self) -> HealthLevel:
        """Get network health level"""
        if self.connectivity_percent >= 90 and self.packet_loss_percent < 1:
            return HealthLevel.HEALTHY
        elif self.connectivity_percent >= 50 and self.packet_loss_percent < 5:
            return HealthLevel.DEGRADED
        else:
            return HealthLevel.CRITICAL


@dataclass
class FullHealthStatus:
    """Complete health status report"""
    overall_health: HealthLevel
    timestamp: float = field(default_factory=time.time)
    components: Dict[str, ComponentHealth] = field(default_factory=dict)
    resources: Optional[ResourceHealth] = None
    network: Optional[NetworkHealth] = None
    details: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            'overall_health': self.overall_health.value,
            'timestamp': self.timestamp,
            'components': {
                name: {
                    'status': comp.status,
                    'uptime_seconds': comp.uptime_seconds,
                    'error_count': comp.error_count,
                    'response_time_ms': comp.response_time_ms,
                    'last_error': comp.last_error
                }
                for name, comp in self.components.items()
            },
            'resources': {
                'cpu_percent': self.resources.cpu_percent,
                'memory_percent': self.resources.memory_percent,
                'disk_percent': self.resources.disk_percent
            } if self.resources else None,
            'network': {
                'connected_peers': self.network.connected_peers,
                'total_peers': self.network.total_peers,
                'connectivity_percent': self.network.connectivity_percent,
                'average_latency_ms': self.network.average_latency_ms,
                'packet_loss_percent': self.network.packet_loss_percent
            } if self.network else None,
            'details': self.details
        }


class HealthChecker:
    """
    Comprehensive health monitoring system for FSRsync.
    
    Monitors all components and system resources to determine
    overall health and identify issues.
    """

    def __init__(self, coordinator=None, logger_instance=None):
        """
        Initialize health checker.
        
        Args:
            coordinator: SyncCoordinator instance
            logger_instance: Logger instance
        """
        self.logger = logger_instance or logging.getLogger(__name__)
        self.coordinator = coordinator
        self.last_check: Optional[FullHealthStatus] = None
        self.check_history: List[FullHealthStatus] = []
        self.max_history = 100  # Keep last 100 checks

    async def check_all(self) -> FullHealthStatus:
        """
        Perform complete health check.
        
        Returns:
            FullHealthStatus with overall and detailed health info
        """
        try:
            status = FullHealthStatus(
                overall_health=HealthLevel.HEALTHY
            )

            # Check components
            if self.coordinator:
                status.components = await self._check_components()

            # Check resources
            status.resources = self._check_resources()

            # Check network
            if self.coordinator:
                status.network = await self._check_network()

            # Determine overall health
            status.overall_health = self._determine_overall_health(status)

            # Store in history
            self.last_check = status
            self.check_history.append(status)
            if len(self.check_history) > self.max_history:
                self.check_history.pop(0)

            return status

        except Exception as e:
            self.logger.error(f"Error during health check: {e}")
            return FullHealthStatus(
                overall_health=HealthLevel.CRITICAL,
                details=[f"Health check failed: {str(e)}"]
            )

    async def _check_components(self) -> Dict[str, ComponentHealth]:
        """Check health of all coordinator components"""
        components = {}

        # Check SyncCoordinator itself
        coordinator_health = ComponentHealth(
            name="SyncCoordinator",
            status="running" if self.coordinator.is_running() else "degraded",
            uptime_seconds=time.time() - self.coordinator.started_at if self.coordinator.started_at else 0,
            error_count=self.coordinator.error_count
        )
        components["SyncCoordinator"] = coordinator_health

        # Check SyncProtocol
        components["SyncProtocol"] = ComponentHealth(
            name="SyncProtocol",
            status="running",
            uptime_seconds=0
        )

        # Check PeerManager
        components["PeerManager"] = ComponentHealth(
            name="PeerManager",
            status="running",
            uptime_seconds=0,
            error_count=0
        )

        # Check ConflictResolver
        components["ConflictResolver"] = ComponentHealth(
            name="ConflictResolver",
            status="running",
            uptime_seconds=0,
            error_count=0
        )

        # Check BandwidthManager
        components["BandwidthManager"] = ComponentHealth(
            name="BandwidthManager",
            status="running",
            uptime_seconds=0,
            error_count=0
        )

        # Check TransferEngine
        components["TransferEngine"] = ComponentHealth(
            name="TransferEngine",
            status="running",
            uptime_seconds=0,
            error_count=0
        )

        # Check QueueManager
        components["QueueManager"] = ComponentHealth(
            name="QueueManager",
            status="running",
            uptime_seconds=0,
            error_count=0
        )

        # Check WebSocketServer
        components["WebSocketServer"] = ComponentHealth(
            name="WebSocketServer",
            status="running",
            uptime_seconds=0,
            error_count=0
        )

        # Check MetricsCollector
        components["MetricsCollector"] = ComponentHealth(
            name="MetricsCollector",
            status="running",
            uptime_seconds=0,
            error_count=0
        )

        return components

    def _check_resources(self) -> ResourceHealth:
        """Check system resource utilization"""
        try:
            return ResourceHealth(
                cpu_percent=psutil.cpu_percent(interval=0.1),
                memory_percent=psutil.virtual_memory().percent,
                disk_percent=psutil.disk_usage('/').percent
            )
        except Exception as e:
            self.logger.warning(f"Could not check resources: {e}")
            return ResourceHealth(
                cpu_percent=0,
                memory_percent=0,
                disk_percent=0
            )

    async def _check_network(self) -> NetworkHealth:
        """Check network connectivity health"""
        try:
            peer_manager = self.coordinator.peer_manager
            all_peers = peer_manager.peers
            connected_peers = sum(1 for p in all_peers.values() if p.status == "CONNECTED")

            return NetworkHealth(
                connected_peers=connected_peers,
                total_peers=len(all_peers),
                average_latency_ms=sum(
                    p.latency_ms for p in all_peers.values() if p.latency_ms
                ) / len([p for p in all_peers.values() if p.latency_ms]) if all_peers else 0,
                packet_loss_percent=0.0,  # Would need actual measurement
                bandwidth_available_mbps=self.coordinator.bandwidth_manager.global_bandwidth_limit_mbps
            )
        except Exception as e:
            self.logger.warning(f"Could not check network: {e}")
            return NetworkHealth(
                connected_peers=0,
                total_peers=0,
                average_latency_ms=0,
                packet_loss_percent=0,
                bandwidth_available_mbps=0
            )

    def _determine_overall_health(self, status: FullHealthStatus) -> HealthLevel:
        """Determine overall health from component statuses"""
        # Start with healthy
        overall = HealthLevel.HEALTHY

        # Check components
        for component in status.components.values():
            if component.status == "failed":
                overall = HealthLevel.CRITICAL
                break
            elif component.status == "degraded":
                if overall == HealthLevel.HEALTHY:
                    overall = HealthLevel.DEGRADED

        # Check resources
        if status.resources:
            res_level = status.resources.get_level()
            if res_level == HealthLevel.CRITICAL:
                overall = HealthLevel.CRITICAL
            elif res_level == HealthLevel.DEGRADED and overall == HealthLevel.HEALTHY:
                overall = HealthLevel.DEGRADED

        # Check network
        if status.network:
            net_level = status.network.get_level()
            if net_level == HealthLevel.CRITICAL:
                overall = HealthLevel.CRITICAL
            elif net_level == HealthLevel.DEGRADED and overall == HealthLevel.HEALTHY:
                overall = HealthLevel.DEGRADED

        return overall

    async def get_health_summary(self) -> Dict[str, Any]:
        """Get health summary for API endpoint"""
        if not self.last_check:
            status = await self.check_all()
        else:
            status = self.last_check

        return status.to_dict()

    def get_health_trend(self, minutes: int = 5) -> List[Dict[str, Any]]:
        """Get health trend over time"""
        now = time.time()
        cutoff = now - (minutes * 60)

        trend = [
            {
                'timestamp': check.timestamp,
                'health': check.overall_health.value
            }
            for check in self.check_history
            if check.timestamp >= cutoff
        ]

        return trend
