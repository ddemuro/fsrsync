"""
Multi-Cluster Management for FSRsync

Provides comprehensive multi-cluster orchestration with:
- Cluster discovery and registration
- Node health monitoring
- Distributed consensus
- Cross-cluster synchronization
- Cluster topology management
- Automatic failover and recovery

## Cluster Architecture

Master-Slave: One master node, multiple replica nodes
Peer-to-Peer: All nodes equal, consensus-based coordination
Hybrid: Mix of dedicated coordinators and worker nodes

## Node Roles

MASTER: Primary coordinator, handles decisions
WORKER: Data sync node, participates in operations
REPLICA: Read-only replica, handles query distribution
COORDINATOR: Distributed coordinator (in peer-to-peer mode)
"""

import time
import logging
import uuid
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field
from enum import Enum
from collections import deque


class NodeRole(Enum):
    """Node role in cluster"""
    MASTER = "master"
    WORKER = "worker"
    REPLICA = "replica"
    COORDINATOR = "coordinator"


class ClusterArchitecture(Enum):
    """Cluster architecture type"""
    MASTER_SLAVE = "master_slave"
    PEER_TO_PEER = "peer_to_peer"
    HYBRID = "hybrid"


class NodeHealth(Enum):
    """Node health status"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    CRITICAL = "critical"
    OFFLINE = "offline"


@dataclass
class ClusterNode:
    """Cluster node definition"""
    node_id: str
    hostname: str
    port: int
    role: NodeRole
    address: str = field(init=False)
    healthy: bool = True
    health_status: NodeHealth = NodeHealth.HEALTHY
    last_heartbeat: float = field(default_factory=time.time)
    heartbeat_failures: int = 0
    cpu_usage: float = 0.0
    memory_usage: float = 0.0
    disk_usage: float = 0.0
    active_syncs: int = 0
    total_syncs: int = 0
    last_error: Optional[str] = None
    joined_at: float = field(default_factory=time.time)
    metadata: Dict[str, any] = field(default_factory=dict)

    def __post_init__(self):
        self.address = f"{self.hostname}:{self.port}"

    @property
    def is_online(self) -> bool:
        """Check if node is online"""
        return self.health_status != NodeHealth.OFFLINE

    @property
    def is_functional(self) -> bool:
        """Check if node is functional"""
        return self.health_status in [NodeHealth.HEALTHY, NodeHealth.DEGRADED]


@dataclass
class ClusterState:
    """Cluster state snapshot"""
    cluster_id: str
    master_node: Optional[str]
    total_nodes: int
    healthy_nodes: int
    version: int
    timestamp: float = field(default_factory=time.time)
    nodes_info: Dict[str, Dict[str, any]] = field(default_factory=dict)


@dataclass
class ConsensusDecision:
    """Consensus decision record"""
    decision_id: str
    decision_type: str
    description: str
    votes_for: int = 0
    votes_against: int = 0
    abstentions: int = 0
    decided: bool = False
    approved: bool = False
    created_at: float = field(default_factory=time.time)
    resolved_at: Optional[float] = None
    participants: Set[str] = field(default_factory=set)


class ClusterManager:
    """
    Multi-cluster manager for FSRsync.

    Manages cluster topology, node health, distributed consensus,
    and inter-cluster communication.
    """

    def __init__(self, cluster_id: str, node_id: str, node_role: str,
                 architecture: str = "peer_to_peer", logger_instance=None):
        """
        Initialize cluster manager.

        Args:
            cluster_id: Unique cluster identifier
            node_id: This node's unique identifier
            node_role: This node's role in cluster
            architecture: Cluster architecture type
            logger_instance: Logger instance
        """
        self.logger = logger_instance or logging.getLogger(__name__)
        self.cluster_id = cluster_id
        self.node_id = node_id
        self.node_role = NodeRole(node_role.lower())
        self.architecture = ClusterArchitecture(architecture.lower())

        # Cluster topology
        self.nodes: Dict[str, ClusterNode] = {}
        self.master_node: Optional[str] = None
        self.replica_nodes: Set[str] = set()
        self.worker_nodes: Set[str] = set()
        self.coordinator_nodes: Set[str] = set()

        # Consensus mechanism
        self.decisions: Dict[str, ConsensusDecision] = {}
        self.consensus_threshold = 0.5  # >50% votes needed
        self.pending_decisions: deque = deque(maxlen=1000)

        # Cluster state tracking
        self.cluster_version = 1
        self.state_history: deque = deque(maxlen=100)
        self.last_state_update = time.time()

        # Node communication
        self.node_connections: Dict[str, any] = {}
        self.connection_timeout = 30  # seconds
        self.heartbeat_interval = 5  # seconds
        self.heartbeat_threshold = 3  # missing heartbeats before offline

        # Inter-cluster synchronization
        self.sync_in_progress: Dict[str, bool] = {}
        self.last_sync_time: Dict[str, float] = {}
        self.sync_queue: deque = deque(maxlen=10000)

        self.logger.info(
            f"ClusterManager initialized: cluster={cluster_id}, "
            f"node={node_id}, role={node_role}, arch={architecture}"
        )

    def register_node(self, hostname: str, port: int, role: str,
                     metadata: Optional[Dict[str, any]] = None) -> bool:
        """
        Register node in cluster.

        Args:
            hostname: Node hostname/IP
            port: Node port
            role: Node role
            metadata: Additional node metadata

        Returns:
            True if registered successfully
        """
        try:
            node_id = str(uuid.uuid4())

            node = ClusterNode(
                node_id=node_id,
                hostname=hostname,
                port=port,
                role=NodeRole(role.lower()),
                metadata=metadata or {}
            )

            self.nodes[node_id] = node

            # Update role tracking
            if node.role == NodeRole.MASTER:
                self.master_node = node_id
            elif node.role == NodeRole.REPLICA:
                self.replica_nodes.add(node_id)
            elif node.role == NodeRole.WORKER:
                self.worker_nodes.add(node_id)
            elif node.role == NodeRole.COORDINATOR:
                self.coordinator_nodes.add(node_id)

            self.cluster_version += 1
            self.logger.info(
                f"Registered node {node_id} at {hostname}:{port} "
                f"with role {role}"
            )
            return True

        except Exception as e:
            self.logger.error(f"Error registering node: {e}")
            return False

    def deregister_node(self, node_id: str) -> bool:
        """
        Deregister node from cluster.

        Args:
            node_id: Node identifier

        Returns:
            True if deregistered successfully
        """
        try:
            if node_id not in self.nodes:
                return False

            node = self.nodes[node_id]

            # Update role tracking
            if node.role == NodeRole.MASTER:
                self.master_node = None
            elif node.role == NodeRole.REPLICA:
                self.replica_nodes.discard(node_id)
            elif node.role == NodeRole.WORKER:
                self.worker_nodes.discard(node_id)
            elif node.role == NodeRole.COORDINATOR:
                self.coordinator_nodes.discard(node_id)

            del self.nodes[node_id]
            self.cluster_version += 1

            self.logger.info(f"Deregistered node {node_id}")
            return True

        except Exception as e:
            self.logger.error(f"Error deregistering node: {e}")
            return False

    def update_node_health(self, node_id: str, health_status: str,
                          cpu: float = 0.0, memory: float = 0.0,
                          disk: float = 0.0, error: Optional[str] = None) -> bool:
        """
        Update node health status.

        Args:
            node_id: Node identifier
            health_status: Health status (healthy, degraded, critical, offline)
            cpu: CPU usage percentage
            memory: Memory usage percentage
            disk: Disk usage percentage
            error: Last error message

        Returns:
            True if updated successfully
        """
        try:
            if node_id not in self.nodes:
                return False

            node = self.nodes[node_id]
            node.health_status = NodeHealth(health_status.lower())
            node.cpu_usage = cpu
            node.memory_usage = memory
            node.disk_usage = disk
            node.last_heartbeat = time.time()
            node.heartbeat_failures = 0

            if error:
                node.last_error = error

            # Update node healthy flag
            node.healthy = node.health_status in [
                NodeHealth.HEALTHY, NodeHealth.DEGRADED
            ]

            return True

        except Exception as e:
            self.logger.error(f"Error updating node health: {e}")
            return False

    def record_missing_heartbeat(self, node_id: str) -> bool:
        """
        Record missing heartbeat for node.

        Args:
            node_id: Node identifier

        Returns:
            True if recorded, False if node taken offline
        """
        try:
            if node_id not in self.nodes:
                return False

            node = self.nodes[node_id]
            node.heartbeat_failures += 1

            if node.heartbeat_failures >= self.heartbeat_threshold:
                node.health_status = NodeHealth.OFFLINE
                node.healthy = False
                self.logger.warning(
                    f"Node {node_id} marked offline after "
                    f"{node.heartbeat_failures} missed heartbeats"
                )
                return False

            return True

        except Exception as e:
            self.logger.error(f"Error recording missing heartbeat: {e}")
            return False

    def propose_decision(self, decision_type: str, description: str) -> Optional[str]:
        """
        Propose decision for consensus voting.

        Args:
            decision_type: Type of decision
            description: Decision description

        Returns:
            Decision ID if proposed successfully
        """
        try:
            decision_id = str(uuid.uuid4())

            decision = ConsensusDecision(
                decision_id=decision_id,
                decision_type=decision_type,
                description=description,
                participants=set(self.nodes.keys())
            )

            self.decisions[decision_id] = decision
            self.pending_decisions.append(decision_id)

            self.logger.info(
                f"Proposed decision {decision_id}: {decision_type} - {description}"
            )
            return decision_id

        except Exception as e:
            self.logger.error(f"Error proposing decision: {e}")
            return None

    def vote_on_decision(self, decision_id: str, node_id: str,
                        vote: bool, abstain: bool = False) -> bool:
        """
        Record vote on proposed decision.

        Args:
            decision_id: Decision identifier
            node_id: Voting node identifier
            vote: True for yes, False for no
            abstain: True to abstain from voting

        Returns:
            True if vote recorded
        """
        try:
            if decision_id not in self.decisions:
                return False

            decision = self.decisions[decision_id]

            if abstain:
                decision.abstentions += 1
            elif vote:
                decision.votes_for += 1
            else:
                decision.votes_against += 1

            # Check if consensus reached
            total_votes = (decision.votes_for + decision.votes_against +
                          decision.abstentions)

            if total_votes >= len(decision.participants):
                decision.decided = True
                decision.resolved_at = time.time()

                # Calculate approval
                required_votes = len(decision.participants) * self.consensus_threshold
                decision.approved = decision.votes_for >= required_votes

                self.logger.info(
                    f"Decision {decision_id} resolved: "
                    f"approved={decision.approved}, "
                    f"for={decision.votes_for}, against={decision.votes_against}"
                )

            return True

        except Exception as e:
            self.logger.error(f"Error voting on decision: {e}")
            return False

    def get_cluster_state(self) -> ClusterState:
        """
        Get current cluster state snapshot.

        Returns:
            ClusterState object
        """
        try:
            healthy_count = sum(
                1 for n in self.nodes.values() if n.healthy
            )

            nodes_info = {
                node_id: {
                    'hostname': node.hostname,
                    'port': node.port,
                    'role': node.role.value,
                    'health': node.health_status.value,
                    'cpu': node.cpu_usage,
                    'memory': node.memory_usage,
                    'disk': node.disk_usage,
                    'active_syncs': node.active_syncs,
                    'total_syncs': node.total_syncs
                }
                for node_id, node in self.nodes.items()
            }

            state = ClusterState(
                cluster_id=self.cluster_id,
                master_node=self.master_node,
                total_nodes=len(self.nodes),
                healthy_nodes=healthy_count,
                version=self.cluster_version,
                nodes_info=nodes_info
            )

            self.state_history.append(state)
            self.last_state_update = time.time()

            return state

        except Exception as e:
            self.logger.error(f"Error getting cluster state: {e}")
            return ClusterState(
                cluster_id=self.cluster_id,
                master_node=self.master_node,
                total_nodes=0,
                healthy_nodes=0,
                version=self.cluster_version
            )

    def select_primary_node(self) -> Optional[str]:
        """
        Select primary/master node for operations.

        Returns:
            Node ID of selected primary
        """
        try:
            # If we have a master, use it
            if self.master_node and self.master_node in self.nodes:
                master = self.nodes[self.master_node]
                if master.is_functional:
                    return self.master_node

            # Fallback: select healthiest node
            candidates = [
                node_id for node_id, node in self.nodes.items()
                if node.is_functional
            ]

            if not candidates:
                self.logger.warning("No functional nodes available for primary selection")
                return None

            # Select node with lowest resource usage
            best_node = min(
                candidates,
                key=lambda nid: (
                    self.nodes[nid].cpu_usage +
                    self.nodes[nid].memory_usage
                )
            )

            return best_node

        except Exception as e:
            self.logger.error(f"Error selecting primary node: {e}")
            return None

    def initiate_failover(self, failed_node_id: str) -> bool:
        """
        Initiate failover for failed node.

        Args:
            failed_node_id: Failed node identifier

        Returns:
            True if failover initiated
        """
        try:
            if failed_node_id not in self.nodes:
                return False

            node = self.nodes[failed_node_id]

            if node.role == NodeRole.MASTER:
                # Master failure - promote coordinator or worker
                new_master = self.select_primary_node()
                if new_master:
                    self.master_node = new_master
                    self.nodes[new_master].role = NodeRole.MASTER
                    self.logger.warning(
                        f"Master node {failed_node_id} failed, "
                        f"promoted {new_master} to master"
                    )
                    return True

            else:
                # Worker/replica failure - redistribute workload
                self.logger.warning(
                    f"Node {failed_node_id} failed, initiating workload redistribution"
                )

                # Redistribute syncs from failed node to healthy nodes
                if node.active_syncs > 0:
                    healthy_workers = [
                        nid for nid, n in self.nodes.items()
                        if n.is_functional and n.role == NodeRole.WORKER
                    ]

                    if healthy_workers:
                        per_node = node.active_syncs // len(healthy_workers)
                        for worker_id in healthy_workers:
                            self.nodes[worker_id].active_syncs += per_node

                        node.active_syncs = 0
                        self.logger.info(
                            f"Redistributed {node.active_syncs} syncs from "
                            f"failed node {failed_node_id}"
                        )
                        return True

            return False

        except Exception as e:
            self.logger.error(f"Error initiating failover: {e}")
            return False

    def get_cluster_summary(self) -> Dict[str, any]:
        """Get cluster status summary"""
        try:
            healthy_nodes = [n for n in self.nodes.values() if n.healthy]

            return {
                'cluster_id': self.cluster_id,
                'node_id': self.node_id,
                'architecture': self.architecture.value,
                'total_nodes': len(self.nodes),
                'healthy_nodes': len(healthy_nodes),
                'master_node': self.master_node,
                'replicas': len(self.replica_nodes),
                'workers': len(self.worker_nodes),
                'coordinators': len(self.coordinator_nodes),
                'cluster_version': self.cluster_version,
                'pending_decisions': len(self.pending_decisions),
                'avg_cpu': sum(n.cpu_usage for n in self.nodes.values()) / max(len(self.nodes), 1),
                'avg_memory': sum(n.memory_usage for n in self.nodes.values()) / max(len(self.nodes), 1),
                'total_syncs': sum(n.total_syncs for n in self.nodes.values()),
                'active_syncs': sum(n.active_syncs for n in self.nodes.values())
            }

        except Exception as e:
            self.logger.error(f"Error getting cluster summary: {e}")
            return {}
