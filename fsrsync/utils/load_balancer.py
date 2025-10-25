"""
Load Balancer Configuration for FSRsync

Provides load balancing strategies for:
- Multi-instance deployments
- Instance health monitoring
- Traffic distribution
- Failover handling
- Session persistence

## Load Balancing Strategies

ROUND_ROBIN: Distribute requests in order
LEAST_CONNECTIONS: Send to instance with fewest connections
IP_HASH: Same IP always goes to same instance
WEIGHTED: Distribute based on instance weight
RANDOM: Random instance selection
"""

import time
import logging
import random
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum


class LoadBalancingStrategy(Enum):
    """Load balancing strategy"""
    ROUND_ROBIN = "round_robin"
    LEAST_CONNECTIONS = "least_connections"
    IP_HASH = "ip_hash"
    WEIGHTED = "weighted"
    RANDOM = "random"


@dataclass
class Instance:
    """Backend instance"""
    instance_id: str
    host: str
    port: int
    weight: float = 1.0
    healthy: bool = True
    active_connections: int = 0
    total_requests: int = 0
    last_health_check: float = field(default_factory=time.time)
    health_check_failures: int = 0


class LoadBalancer:
    """
    Load balancer for FSRsync multi-instance deployments.
    
    Distributes traffic across multiple instances with
    health monitoring and failover support.
    """

    def __init__(self, strategy: str = "round_robin", logger_instance=None):
        """
        Initialize load balancer.
        
        Args:
            strategy: Load balancing strategy
            logger_instance: Logger instance
        """
        self.logger = logger_instance or logging.getLogger(__name__)
        self.strategy = LoadBalancingStrategy(strategy.lower())
        self.instances: Dict[str, Instance] = {}
        self.current_index = 0
        self.last_health_check = time.time()
        self.health_check_interval = 30  # seconds

        self.logger.info(f"LoadBalancer initialized with strategy: {self.strategy.value}")

    def add_instance(self, instance_id: str, host: str, port: int,
                     weight: float = 1.0) -> bool:
        """
        Add backend instance.
        
        Args:
            instance_id: Unique instance identifier
            host: Instance host/IP
            port: Instance port
            weight: Instance weight (for weighted strategy)
            
        Returns:
            True if successful
        """
        try:
            if instance_id in self.instances:
                self.logger.warning(f"Instance {instance_id} already exists")
                return False

            instance = Instance(
                instance_id=instance_id,
                host=host,
                port=port,
                weight=weight
            )

            self.instances[instance_id] = instance
            self.logger.info(f"Added instance {instance_id} at {host}:{port}")
            return True

        except Exception as e:
            self.logger.error(f"Error adding instance: {e}")
            return False

    def select_instance(self, client_ip: Optional[str] = None) -> Optional[Instance]:
        """
        Select instance for request.
        
        Args:
            client_ip: Client IP for IP_HASH strategy
            
        Returns:
            Selected instance or None
        """
        try:
            # Filter healthy instances
            healthy = [i for i in self.instances.values() if i.healthy]

            if not healthy:
                self.logger.warning("No healthy instances available")
                return None

            # Select based on strategy
            if self.strategy == LoadBalancingStrategy.ROUND_ROBIN:
                instance = self._select_round_robin(healthy)
            elif self.strategy == LoadBalancingStrategy.LEAST_CONNECTIONS:
                instance = self._select_least_connections(healthy)
            elif self.strategy == LoadBalancingStrategy.IP_HASH:
                instance = self._select_ip_hash(healthy, client_ip)
            elif self.strategy == LoadBalancingStrategy.WEIGHTED:
                instance = self._select_weighted(healthy)
            else:  # RANDOM
                instance = random.choice(healthy)

            if instance:
                instance.active_connections += 1
                instance.total_requests += 1

            return instance

        except Exception as e:
            self.logger.error(f"Error selecting instance: {e}")
            return None

    def _select_round_robin(self, instances: List[Instance]) -> Optional[Instance]:
        """Round robin selection"""
        if not instances:
            return None

        instance = instances[self.current_index % len(instances)]
        self.current_index += 1
        return instance

    def _select_least_connections(self, instances: List[Instance]) -> Optional[Instance]:
        """Least connections selection"""
        if not instances:
            return None

        return min(instances, key=lambda x: x.active_connections)

    def _select_ip_hash(self, instances: List[Instance],
                        client_ip: Optional[str] = None) -> Optional[Instance]:
        """IP hash selection"""
        if not instances:
            return None

        if not client_ip:
            return instances[0]

        # Hash IP to select instance
        ip_hash = hash(client_ip)
        index = ip_hash % len(instances)
        return instances[index]

    def _select_weighted(self, instances: List[Instance]) -> Optional[Instance]:
        """Weighted selection"""
        if not instances:
            return None

        # Weighted random selection
        total_weight = sum(i.weight for i in instances)
        if total_weight == 0:
            return instances[0]

        choice = random.uniform(0, total_weight)
        current = 0

        for instance in instances:
            current += instance.weight
            if choice <= current:
                return instance

        return instances[-1]

    def release_instance(self, instance_id: str) -> bool:
        """
        Release instance after request completion.
        
        Args:
            instance_id: Instance identifier
            
        Returns:
            True if successful
        """
        try:
            if instance_id not in self.instances:
                return False

            instance = self.instances[instance_id]
            instance.active_connections = max(0, instance.active_connections - 1)
            return True

        except Exception as e:
            self.logger.error(f"Error releasing instance: {e}")
            return False

    def mark_unhealthy(self, instance_id: str, reason: str = "") -> bool:
        """
        Mark instance as unhealthy.
        
        Args:
            instance_id: Instance identifier
            reason: Reason for marking unhealthy
            
        Returns:
            True if successful
        """
        try:
            if instance_id not in self.instances:
                return False

            instance = self.instances[instance_id]
            instance.healthy = False
            instance.health_check_failures += 1

            self.logger.warning(f"Marked {instance_id} unhealthy: {reason}")
            return True

        except Exception as e:
            self.logger.error(f"Error marking unhealthy: {e}")
            return False

    def mark_healthy(self, instance_id: str) -> bool:
        """Mark instance as healthy"""
        try:
            if instance_id not in self.instances:
                return False

            instance = self.instances[instance_id]
            instance.healthy = True
            instance.health_check_failures = 0

            self.logger.info(f"Marked {instance_id} healthy")
            return True

        except Exception as e:
            self.logger.error(f"Error marking healthy: {e}")
            return False

    def get_status(self) -> Dict[str, any]:
        """Get load balancer status"""
        healthy_count = sum(1 for i in self.instances.values() if i.healthy)

        return {
            'strategy': self.strategy.value,
            'total_instances': len(self.instances),
            'healthy_instances': healthy_count,
            'total_requests': sum(i.total_requests for i in self.instances.values()),
            'active_connections': sum(i.active_connections for i in self.instances.values()),
            'instances': [
                {
                    'id': i.instance_id,
                    'host': f"{i.host}:{i.port}",
                    'healthy': i.healthy,
                    'connections': i.active_connections,
                    'requests': i.total_requests,
                    'weight': i.weight
                }
                for i in self.instances.values()
            ]
        }
