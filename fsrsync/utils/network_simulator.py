"""
Network Simulation and Chaos Engineering for FSRsync

Provides network condition simulation with:
- Latency injection
- Packet loss simulation
- Bandwidth throttling
- Jitter simulation
- Network partition simulation
- Chaos scenarios

## Network Conditions

NORMAL: No degradation
DEGRADED: High latency, low packet loss
POOR: Very high latency, packet loss
FAILING: Severe degradation
OFFLINE: Complete network partition
"""

import time
import logging
import random
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from collections import deque


class NetworkCondition(Enum):
    """Network condition type"""
    NORMAL = "normal"
    DEGRADED = "degraded"
    POOR = "poor"
    FAILING = "failing"
    OFFLINE = "offline"


class ChaosScenario(Enum):
    """Chaos engineering scenario"""
    LATENCY_SPIKE = "latency_spike"
    PACKET_LOSS = "packet_loss"
    BANDWIDTH_LIMIT = "bandwidth_limit"
    JITTER = "jitter"
    PARTITION = "partition"
    CASCADING_FAILURE = "cascading_failure"
    RECOVERY = "recovery"


@dataclass
class NetworkConditionProfile:
    """Network condition profile"""
    name: str
    latency_ms: float  # milliseconds
    latency_jitter_ms: float
    packet_loss_percent: float
    bandwidth_limit_mbps: float
    is_online: bool = True


@dataclass
class ChaosEvent:
    """Chaos engineering event"""
    event_id: str
    scenario: ChaosScenario
    target_component: str
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    duration_seconds: float = 0.0
    severity: str = "medium"  # low, medium, high, critical
    affected_nodes: List[str] = field(default_factory=list)
    metrics_before: Dict[str, float] = field(default_factory=dict)
    metrics_after: Dict[str, float] = field(default_factory=dict)
    recovered: bool = False


class NetworkSimulator:
    """
    Network condition simulator for chaos testing.

    Simulates various network conditions and chaos
    scenarios for resilience testing.
    """

    def __init__(self, logger_instance=None):
        """
        Initialize network simulator.

        Args:
            logger_instance: Logger instance
        """
        self.logger = logger_instance or logging.getLogger(__name__)

        # Network profiles
        self.profiles: Dict[str, NetworkConditionProfile] = self._init_profiles()
        self.current_conditions: Dict[str, NetworkCondition] = {}

        # Per-node network conditions
        self.node_conditions: Dict[str, NetworkConditionProfile] = {}

        # Chaos scenarios
        self.active_scenarios: Dict[str, ChaosEvent] = {}
        self.scenario_history: deque = deque(maxlen=1000)

        # Network metrics
        self.packet_drop_rate: Dict[str, float] = {}
        self.latency_samples: Dict[str, deque] = {}
        self.bandwidth_utilization: Dict[str, float] = {}

        # Partition tracking
        self.partitions: Dict[str, set] = {}  # partition_id -> set of nodes

        self.logger.info("NetworkSimulator initialized")

    def _init_profiles(self) -> Dict[str, NetworkConditionProfile]:
        """Initialize standard network condition profiles"""
        return {
            'normal': NetworkConditionProfile(
                name='normal',
                latency_ms=10,
                latency_jitter_ms=2,
                packet_loss_percent=0,
                bandwidth_limit_mbps=1000
            ),
            'degraded': NetworkConditionProfile(
                name='degraded',
                latency_ms=50,
                latency_jitter_ms=10,
                packet_loss_percent=1,
                bandwidth_limit_mbps=100
            ),
            'poor': NetworkConditionProfile(
                name='poor',
                latency_ms=200,
                latency_jitter_ms=50,
                packet_loss_percent=5,
                bandwidth_limit_mbps=10
            ),
            'failing': NetworkConditionProfile(
                name='failing',
                latency_ms=1000,
                latency_jitter_ms=200,
                packet_loss_percent=20,
                bandwidth_limit_mbps=1,
                is_online=True
            ),
            'offline': NetworkConditionProfile(
                name='offline',
                latency_ms=float('inf'),
                latency_jitter_ms=0,
                packet_loss_percent=100,
                bandwidth_limit_mbps=0,
                is_online=False
            )
        }

    def set_node_condition(self, node_id: str, condition: str) -> bool:
        """
        Set network condition for a node.

        Args:
            node_id: Node identifier
            condition: Network condition name

        Returns:
            True if set successfully
        """
        try:
            if condition not in self.profiles:
                self.logger.warning(f"Unknown condition: {condition}")
                return False

            self.node_conditions[node_id] = self.profiles[condition]
            self.current_conditions[node_id] = NetworkCondition(condition)

            self.logger.info(f"Set node {node_id} condition to {condition}")
            return True

        except Exception as e:
            self.logger.error(f"Error setting node condition: {e}")
            return False

    def get_node_latency(self, node_id: str) -> float:
        """
        Get current latency for node.

        Args:
            node_id: Node identifier

        Returns:
            Latency in milliseconds
        """
        try:
            if node_id not in self.node_conditions:
                return self.profiles['normal'].latency_ms

            profile = self.node_conditions[node_id]

            # Add jitter
            jitter = random.uniform(
                -profile.latency_jitter_ms,
                profile.latency_jitter_ms
            )

            latency = max(0, profile.latency_ms + jitter)

            return latency

        except Exception as e:
            self.logger.error(f"Error getting node latency: {e}")
            return 0

    def should_drop_packet(self, node_id: str) -> bool:
        """
        Determine if packet should be dropped for node.

        Args:
            node_id: Node identifier

        Returns:
            True if packet should be dropped
        """
        try:
            if node_id not in self.node_conditions:
                return False

            profile = self.node_conditions[node_id]
            drop_probability = profile.packet_loss_percent / 100.0

            return random.random() < drop_probability

        except Exception as e:
            self.logger.error(f"Error checking packet drop: {e}")
            return False

    def get_bandwidth_limit(self, node_id: str) -> float:
        """
        Get bandwidth limit for node.

        Args:
            node_id: Node identifier

        Returns:
            Bandwidth limit in MB/s
        """
        try:
            if node_id not in self.node_conditions:
                return self.profiles['normal'].bandwidth_limit_mbps

            return self.node_conditions[node_id].bandwidth_limit_mbps

        except Exception as e:
            self.logger.error(f"Error getting bandwidth limit: {e}")
            return 0

    def inject_latency_spike(self, node_id: str, latency_ms: float,
                            duration_seconds: float = 5.0) -> Optional[str]:
        """
        Inject latency spike into node.

        Args:
            node_id: Node identifier
            latency_ms: Latency in milliseconds
            duration_seconds: Duration of spike

        Returns:
            Event ID if injected
        """
        try:
            import uuid

            event_id = str(uuid.uuid4())

            # Save current condition
            original_condition = self.node_conditions.get(node_id)

            # Create temporary profile with high latency
            temp_profile = NetworkConditionProfile(
                name=f"spike_{node_id}",
                latency_ms=latency_ms,
                latency_jitter_ms=50,
                packet_loss_percent=5,
                bandwidth_limit_mbps=50
            )

            self.node_conditions[node_id] = temp_profile

            event = ChaosEvent(
                event_id=event_id,
                scenario=ChaosScenario.LATENCY_SPIKE,
                target_component=node_id,
                duration_seconds=duration_seconds,
                severity="high",
                affected_nodes=[node_id]
            )

            self.active_scenarios[event_id] = event

            self.logger.warning(
                f"Injected latency spike on {node_id}: "
                f"{latency_ms}ms for {duration_seconds}s"
            )

            return event_id

        except Exception as e:
            self.logger.error(f"Error injecting latency spike: {e}")
            return None

    def inject_packet_loss(self, node_id: str, loss_percent: float,
                          duration_seconds: float = 10.0) -> Optional[str]:
        """
        Inject packet loss into node.

        Args:
            node_id: Node identifier
            loss_percent: Packet loss percentage
            duration_seconds: Duration of packet loss

        Returns:
            Event ID if injected
        """
        try:
            import uuid

            event_id = str(uuid.uuid4())

            # Create temporary profile with packet loss
            temp_profile = NetworkConditionProfile(
                name=f"loss_{node_id}",
                latency_ms=50,
                latency_jitter_ms=10,
                packet_loss_percent=loss_percent,
                bandwidth_limit_mbps=50
            )

            self.node_conditions[node_id] = temp_profile

            event = ChaosEvent(
                event_id=event_id,
                scenario=ChaosScenario.PACKET_LOSS,
                target_component=node_id,
                duration_seconds=duration_seconds,
                severity="high",
                affected_nodes=[node_id]
            )

            self.active_scenarios[event_id] = event

            self.logger.warning(
                f"Injected packet loss on {node_id}: "
                f"{loss_percent}% for {duration_seconds}s"
            )

            return event_id

        except Exception as e:
            self.logger.error(f"Error injecting packet loss: {e}")
            return None

    def create_network_partition(self, partition_id: str,
                                nodes: List[str]) -> Optional[str]:
        """
        Create network partition (split-brain scenario).

        Args:
            partition_id: Partition identifier
            nodes: List of nodes in this partition

        Returns:
            Partition ID if created
        """
        try:
            import uuid

            event_id = str(uuid.uuid4())

            # Set all nodes in partition to offline
            for node in nodes:
                self.set_node_condition(node, 'offline')

            self.partitions[partition_id] = set(nodes)

            event = ChaosEvent(
                event_id=event_id,
                scenario=ChaosScenario.PARTITION,
                target_component=partition_id,
                severity="critical",
                affected_nodes=nodes
            )

            self.active_scenarios[event_id] = event
            self.scenario_history.append(event)

            self.logger.critical(
                f"Created network partition {partition_id} "
                f"with nodes: {nodes}"
            )

            return partition_id

        except Exception as e:
            self.logger.error(f"Error creating network partition: {e}")
            return None

    def heal_partition(self, partition_id: str) -> bool:
        """
        Heal a network partition.

        Args:
            partition_id: Partition to heal

        Returns:
            True if healed
        """
        try:
            if partition_id not in self.partitions:
                return False

            nodes = self.partitions[partition_id]

            # Restore nodes to normal condition
            for node in nodes:
                self.set_node_condition(node, 'normal')

            del self.partitions[partition_id]

            self.logger.info(f"Healed network partition {partition_id}")
            return True

        except Exception as e:
            self.logger.error(f"Error healing partition: {e}")
            return False

    def limit_bandwidth(self, node_id: str, bandwidth_mbps: float,
                       duration_seconds: float = 30.0) -> Optional[str]:
        """
        Limit bandwidth for a node.

        Args:
            node_id: Node identifier
            bandwidth_mbps: Bandwidth limit in MB/s
            duration_seconds: Duration of limit

        Returns:
            Event ID if limited
        """
        try:
            import uuid

            event_id = str(uuid.uuid4())

            # Create temporary profile with bandwidth limit
            temp_profile = NetworkConditionProfile(
                name=f"bw_limit_{node_id}",
                latency_ms=50,
                latency_jitter_ms=10,
                packet_loss_percent=0,
                bandwidth_limit_mbps=bandwidth_mbps
            )

            self.node_conditions[node_id] = temp_profile

            event = ChaosEvent(
                event_id=event_id,
                scenario=ChaosScenario.BANDWIDTH_LIMIT,
                target_component=node_id,
                duration_seconds=duration_seconds,
                severity="medium",
                affected_nodes=[node_id]
            )

            self.active_scenarios[event_id] = event

            self.logger.warning(
                f"Limited bandwidth on {node_id}: "
                f"{bandwidth_mbps} MB/s for {duration_seconds}s"
            )

            return event_id

        except Exception as e:
            self.logger.error(f"Error limiting bandwidth: {e}")
            return None

    def end_chaos_scenario(self, event_id: str) -> bool:
        """
        End a chaos scenario and restore normal condition.

        Args:
            event_id: Event ID to end

        Returns:
            True if ended successfully
        """
        try:
            if event_id not in self.active_scenarios:
                return False

            event = self.active_scenarios[event_id]

            # Restore normal condition for all affected nodes
            for node in event.affected_nodes:
                self.set_node_condition(node, 'normal')

            event.end_time = time.time()
            event.recovered = True

            self.scenario_history.append(event)
            del self.active_scenarios[event_id]

            self.logger.info(f"Ended chaos scenario {event_id}")
            return True

        except Exception as e:
            self.logger.error(f"Error ending chaos scenario: {e}")
            return False

    def get_network_status(self) -> Dict[str, any]:
        """Get current network status"""
        try:
            return {
                'timestamp': time.time(),
                'node_conditions': {
                    node: condition.value
                    for node, condition in self.current_conditions.items()
                },
                'active_scenarios': len(self.active_scenarios),
                'partitions': len(self.partitions),
                'scenario_history': len(self.scenario_history),
                'profiles': list(self.profiles.keys())
            }

        except Exception as e:
            self.logger.error(f"Error getting network status: {e}")
            return {}

    def get_chaos_history(self, limit: int = 100) -> List[Dict[str, any]]:
        """Get chaos scenario history"""
        try:
            history = []

            for event in reversed(list(self.scenario_history)):
                history.append({
                    'event_id': event.event_id,
                    'scenario': event.scenario.value,
                    'target': event.target_component,
                    'severity': event.severity,
                    'duration_seconds': event.duration_seconds,
                    'affected_nodes': event.affected_nodes,
                    'recovered': event.recovered
                })

                if len(history) >= limit:
                    break

            return history

        except Exception as e:
            self.logger.error(f"Error getting chaos history: {e}")
            return []
