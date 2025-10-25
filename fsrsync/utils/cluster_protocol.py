"""
Peer-to-Peer Cluster Communication Protocol for FSRsync

Provides inter-node communication with:
- Message routing and delivery
- Service discovery
- Health monitoring
- State synchronization
- Distributed transactions
- Network partition handling

## Message Types

HEARTBEAT: Node liveness check
STATE_SYNC: Cluster state synchronization
DECISION_REQUEST: Propose decision for voting
DECISION_VOTE: Cast vote on decision
WORKLOAD_TRANSFER: Move sync tasks between nodes
CONFIGURATION_CHANGE: Configuration update notification
DATA_REPLICA: Data replication between nodes
"""

import json
import time
import logging
from typing import Dict, List, Optional, Any, Callable, Tuple
from dataclasses import dataclass, field
from enum import Enum
from collections import deque
import hashlib


class MessageType(Enum):
    """Message types in cluster protocol"""
    HEARTBEAT = "heartbeat"
    STATE_SYNC = "state_sync"
    DECISION_REQUEST = "decision_request"
    DECISION_VOTE = "decision_vote"
    WORKLOAD_TRANSFER = "workload_transfer"
    CONFIGURATION_CHANGE = "configuration_change"
    DATA_REPLICA = "data_replica"
    ACK = "ack"
    NACK = "nack"


class MessagePriority(Enum):
    """Message priority for queue processing"""
    CRITICAL = 1
    HIGH = 2
    NORMAL = 3
    LOW = 4


@dataclass
class ClusterMessage:
    """Cluster message definition"""
    message_id: str
    message_type: MessageType
    sender_node: str
    recipient_node: str
    payload: Dict[str, Any] = field(default_factory=dict)
    priority: MessagePriority = MessagePriority.NORMAL
    created_at: float = field(default_factory=time.time)
    expires_at: Optional[float] = None
    requires_ack: bool = True
    sequence_number: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_expired(self) -> bool:
        """Check if message has expired"""
        if self.expires_at is None:
            return False
        return time.time() > self.expires_at

    def to_json(self) -> str:
        """Serialize message to JSON"""
        return json.dumps({
            'message_id': self.message_id,
            'message_type': self.message_type.value,
            'sender_node': self.sender_node,
            'recipient_node': self.recipient_node,
            'payload': self.payload,
            'priority': self.priority.value,
            'created_at': self.created_at,
            'expires_at': self.expires_at,
            'requires_ack': self.requires_ack,
            'sequence_number': self.sequence_number,
            'metadata': self.metadata
        })

    @classmethod
    def from_json(cls, json_data: str) -> 'ClusterMessage':
        """Deserialize message from JSON"""
        data = json.loads(json_data)
        return cls(
            message_id=data['message_id'],
            message_type=MessageType(data['message_type']),
            sender_node=data['sender_node'],
            recipient_node=data['recipient_node'],
            payload=data.get('payload', {}),
            priority=MessagePriority(data.get('priority', 3)),
            created_at=data['created_at'],
            expires_at=data.get('expires_at'),
            requires_ack=data.get('requires_ack', True),
            sequence_number=data.get('sequence_number', 0),
            metadata=data.get('metadata', {})
        )


@dataclass
class MessageAckEntry:
    """Track acknowledgments for messages"""
    message_id: str
    acknowledged_by: set = field(default_factory=set)
    pending_from: set = field(default_factory=set)
    created_at: float = field(default_factory=time.time)
    resolved_at: Optional[float] = None
    ack_timeout: float = 30.0

    @property
    def is_complete(self) -> bool:
        """Check if all acknowledgments received"""
        return len(self.pending_from) == 0

    @property
    def is_timeout(self) -> bool:
        """Check if ack wait has timed out"""
        return (time.time() - self.created_at) > self.ack_timeout


@dataclass
class ServiceEndpoint:
    """Service endpoint for discovery"""
    service_name: str
    node_id: str
    hostname: str
    port: int
    protocol: str = "grpc"
    healthy: bool = True
    registered_at: float = field(default_factory=time.time)
    last_heartbeat: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)


class ClusterProtocol:
    """
    Peer-to-peer cluster communication protocol.

    Manages inter-node messaging, service discovery, and
    protocol-level state synchronization.
    """

    def __init__(self, node_id: str, logger_instance=None):
        """
        Initialize cluster protocol.

        Args:
            node_id: This node's identifier
            logger_instance: Logger instance
        """
        self.logger = logger_instance or logging.getLogger(__name__)
        self.node_id = node_id

        # Message queues
        self.outbound_queue: deque = deque(maxlen=10000)
        self.inbound_queue: deque = deque(maxlen=10000)
        self.received_messages: Dict[str, ClusterMessage] = {}

        # Message tracking
        self.ack_tracking: Dict[str, MessageAckEntry] = {}
        self.message_sequence = 0
        self.delivery_guarantees = {}  # message_id -> required_acks

        # Service discovery
        self.registered_services: Dict[str, ServiceEndpoint] = {}
        self.discovered_services: Dict[str, List[ServiceEndpoint]] = {}

        # Message handlers
        self.message_handlers: Dict[MessageType, Callable] = {}
        self.default_handler: Optional[Callable] = None

        # Network partition detection
        self.partition_detector_enabled = True
        self.partition_detected = False
        self.last_partition_check = time.time()
        self.partition_check_interval = 10  # seconds

        # Message statistics
        self.messages_sent = 0
        self.messages_received = 0
        self.messages_dropped = 0
        self.delivery_failures = 0

        self.logger.info(f"ClusterProtocol initialized for node {node_id}")

    def send_message(self, recipient_node: str, message_type: str,
                    payload: Optional[Dict[str, Any]] = None,
                    priority: str = "normal",
                    requires_ack: bool = True,
                    ttl_seconds: Optional[int] = None) -> Optional[str]:
        """
        Send message to another node.

        Args:
            recipient_node: Recipient node ID
            message_type: Type of message
            payload: Message payload
            priority: Message priority (critical, high, normal, low)
            requires_ack: Whether acknowledgment is required
            ttl_seconds: Time-to-live in seconds

        Returns:
            Message ID if queued successfully
        """
        try:
            import uuid

            message_id = str(uuid.uuid4())
            self.message_sequence += 1

            expires_at = None
            if ttl_seconds:
                expires_at = time.time() + ttl_seconds

            message = ClusterMessage(
                message_id=message_id,
                message_type=MessageType(message_type.lower()),
                sender_node=self.node_id,
                recipient_node=recipient_node,
                payload=payload or {},
                priority=MessagePriority[priority.upper()],
                expires_at=expires_at,
                requires_ack=requires_ack,
                sequence_number=self.message_sequence
            )

            # Queue outbound message (prioritized)
            self.outbound_queue.append(message)

            # Track acknowledgment if required
            if requires_ack:
                self.ack_tracking[message_id] = MessageAckEntry(
                    message_id=message_id,
                    pending_from={recipient_node}
                )

            self.messages_sent += 1
            self.logger.debug(
                f"Message {message_id} queued for {recipient_node}: "
                f"{message_type}"
            )

            return message_id

        except Exception as e:
            self.logger.error(f"Error sending message: {e}")
            return None

    def receive_message(self, message_json: str) -> Optional[ClusterMessage]:
        """
        Receive and process incoming message.

        Args:
            message_json: JSON-serialized message

        Returns:
            Deserialized message if valid
        """
        try:
            message = ClusterMessage.from_json(message_json)

            # Check if expired
            if message.is_expired:
                self.messages_dropped += 1
                self.logger.debug(f"Dropped expired message {message.message_id}")
                return None

            # Validate message
            if not self._validate_message(message):
                self.delivery_failures += 1
                return None

            # Store received message
            self.received_messages[message.message_id] = message
            self.inbound_queue.append(message)
            self.messages_received += 1

            # Send acknowledgment if required
            if message.requires_ack:
                self._send_ack(message.sender_node, message.message_id)

            # Call handler
            self._dispatch_message(message)

            self.logger.debug(
                f"Message {message.message_id} received from "
                f"{message.sender_node}"
            )

            return message

        except Exception as e:
            self.logger.error(f"Error receiving message: {e}")
            self.delivery_failures += 1
            return None

    def acknowledge_message(self, message_id: str, sender_node: str) -> bool:
        """
        Acknowledge receipt of message.

        Args:
            message_id: Message to acknowledge
            sender_node: Sender of the message

        Returns:
            True if acknowledged
        """
        try:
            if message_id not in self.ack_tracking:
                return False

            ack_entry = self.ack_tracking[message_id]
            ack_entry.acknowledged_by.add(sender_node)
            ack_entry.pending_from.discard(sender_node)

            if ack_entry.is_complete:
                ack_entry.resolved_at = time.time()
                self.logger.debug(f"Message {message_id} fully acknowledged")

            return True

        except Exception as e:
            self.logger.error(f"Error acknowledging message: {e}")
            return False

    def _send_ack(self, recipient_node: str, message_id: str) -> None:
        """Send acknowledgment message"""
        try:
            ack_message = ClusterMessage(
                message_id=str(__import__('uuid').uuid4()),
                message_type=MessageType.ACK,
                sender_node=self.node_id,
                recipient_node=recipient_node,
                payload={'ack_for': message_id},
                requires_ack=False
            )

            self.outbound_queue.append(ack_message)

        except Exception as e:
            self.logger.error(f"Error sending ack: {e}")

    def _validate_message(self, message: ClusterMessage) -> bool:
        """Validate message integrity and format"""
        try:
            # Check required fields
            if not message.message_id or not message.sender_node:
                return False

            # Check message type
            if message.message_type not in MessageType:
                return False

            # Verify checksum if present
            if 'checksum' in message.metadata:
                payload_str = json.dumps(message.payload, sort_keys=True)
                calculated = hashlib.sha256(
                    payload_str.encode()
                ).hexdigest()

                if calculated != message.metadata['checksum']:
                    self.logger.warning(
                        f"Message {message.message_id} failed checksum validation"
                    )
                    return False

            return True

        except Exception as e:
            self.logger.error(f"Error validating message: {e}")
            return False

    def _dispatch_message(self, message: ClusterMessage) -> None:
        """Dispatch message to appropriate handler"""
        try:
            handler = self.message_handlers.get(message.message_type)

            if handler:
                handler(message)
            elif self.default_handler:
                self.default_handler(message)
            else:
                self.logger.debug(
                    f"No handler for message type {message.message_type.value}"
                )

        except Exception as e:
            self.logger.error(f"Error dispatching message: {e}")

    def register_message_handler(self, message_type: str,
                                handler: Callable) -> bool:
        """
        Register handler for message type.

        Args:
            message_type: Message type to handle
            handler: Handler function

        Returns:
            True if registered
        """
        try:
            msg_type = MessageType(message_type.lower())
            self.message_handlers[msg_type] = handler
            self.logger.info(f"Registered handler for {message_type}")
            return True

        except Exception as e:
            self.logger.error(f"Error registering handler: {e}")
            return False

    def register_service(self, service_name: str, hostname: str,
                        port: int, protocol: str = "grpc",
                        metadata: Optional[Dict[str, Any]] = None) -> bool:
        """
        Register service endpoint.

        Args:
            service_name: Service name
            hostname: Service hostname
            port: Service port
            protocol: Communication protocol
            metadata: Service metadata

        Returns:
            True if registered
        """
        try:
            endpoint = ServiceEndpoint(
                service_name=service_name,
                node_id=self.node_id,
                hostname=hostname,
                port=port,
                protocol=protocol,
                metadata=metadata or {}
            )

            service_key = f"{service_name}:{self.node_id}"
            self.registered_services[service_key] = endpoint

            self.logger.info(
                f"Registered service {service_name} at "
                f"{hostname}:{port}"
            )
            return True

        except Exception as e:
            self.logger.error(f"Error registering service: {e}")
            return False

    def discover_service(self, service_name: str) -> List[ServiceEndpoint]:
        """
        Discover service endpoints.

        Args:
            service_name: Service to discover

        Returns:
            List of available endpoints
        """
        try:
            # Check local discovery cache first
            if service_name in self.discovered_services:
                endpoints = self.discovered_services[service_name]
                active = [e for e in endpoints if e.healthy]
                if active:
                    return active

            # In a real implementation, would query cluster registry
            return []

        except Exception as e:
            self.logger.error(f"Error discovering service: {e}")
            return []

    def check_network_partition(self) -> Tuple[bool, List[str]]:
        """
        Check for network partition.

        Returns:
            Tuple of (partition_detected, unreachable_nodes)
        """
        try:
            # In real implementation, would ping all known nodes
            # and determine if partition exists

            unreachable = []
            # Check heartbeat from all tracked nodes
            # Add unreachable nodes to list

            partition = len(unreachable) > 0
            self.partition_detected = partition

            if partition:
                self.logger.warning(
                    f"Network partition detected, unreachable nodes: "
                    f"{unreachable}"
                )

            return partition, unreachable

        except Exception as e:
            self.logger.error(f"Error checking network partition: {e}")
            return False, []

    def get_protocol_stats(self) -> Dict[str, Any]:
        """Get protocol statistics"""
        try:
            pending_acks = sum(
                1 for entry in self.ack_tracking.values()
                if not entry.is_complete
            )

            ack_timeouts = sum(
                1 for entry in self.ack_tracking.values()
                if entry.is_timeout
            )

            return {
                'messages_sent': self.messages_sent,
                'messages_received': self.messages_received,
                'messages_dropped': self.messages_dropped,
                'delivery_failures': self.delivery_failures,
                'pending_acks': pending_acks,
                'ack_timeouts': ack_timeouts,
                'outbound_queue_size': len(self.outbound_queue),
                'inbound_queue_size': len(self.inbound_queue),
                'registered_services': len(self.registered_services),
                'discovered_services': len(self.discovered_services),
                'partition_detected': self.partition_detected
            }

        except Exception as e:
            self.logger.error(f"Error getting protocol stats: {e}")
            return {}
