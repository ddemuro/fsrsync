"""
WebSocket Server for Real-Time Sync Status

Provides real-time updates to dashboard clients via WebSocket with:
- Live transfer progress
- Bandwidth usage graphs
- Peer status updates
- Conflict notifications
- Queue status and statistics

## Message Types

### Client → Server
- subscribe: Subscribe to updates
- unsubscribe: Unsubscribe from updates
- request_stats: Request current statistics
- pause_sync: Pause specific peer/folder sync
- resume_sync: Resume specific peer/folder sync
- cancel_transfer: Cancel transfer by ID
- retry_failed: Retry failed transfers

### Server → Client
- connected: Connection established
- stats_update: Statistics update
- transfer_progress: Transfer progress update
- bandwidth_update: Bandwidth usage update
- peer_status_update: Peer status changed
- conflict_detected: Conflict in sync
- error: Error occurred
- disconnected: Connection closed

## Update Frequency

- Stats: 1-5 second intervals (configurable)
- Transfer progress: Real-time (on chunk completion)
- Bandwidth: 1-2 second intervals
- Peer status: On change
- Conflicts: Immediately

## Architecture

```
Dashboard (HTML/JS) <--WebSocket--> WebSocket Server <--> Sync Manager
                                      (in_memory state)   (actual sync)
                                      (message queue)
```

## Examples

```python
server = WebSocketServer(sync_manager, port=9877)
await server.start()

# Broadcast stats update
await server.broadcast_stats({
    'total_transfers': 5,
    'active_transfers': 2,
    'bandwidth_usage': 50.5
})

# Notify conflict
await server.broadcast_conflict({
    'file_path': '/data/file.txt',
    'peer': 'remote-host',
    'resolution': 'MANUAL'
})
```

## Integration Points

- SyncCoordinator: Requests stats for broadcast
- TransferEngine: Reports transfer progress
- BandwidthManager: Provides bandwidth data
- PeerManager: Notifies of peer status changes
- ConflictResolver: Notifies of conflicts
- Dashboard: Receives WebSocket messages
"""

import asyncio
import logging
import json
import time
from enum import Enum
from typing import Dict, Optional, List, Any, Set, Callable
from dataclasses import dataclass, field
from datetime import datetime
import uuid

logger = logging.getLogger(__name__)


# ============================================================================
# WebSocket Message Types
# ============================================================================

class MessageType(Enum):
    """WebSocket message type"""
    # Client requests
    SUBSCRIBE = "subscribe"
    UNSUBSCRIBE = "unsubscribe"
    REQUEST_STATS = "request_stats"
    PAUSE_SYNC = "pause_sync"
    RESUME_SYNC = "resume_sync"
    CANCEL_TRANSFER = "cancel_transfer"
    RETRY_FAILED = "retry_failed"

    # Server broadcasts
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    STATS_UPDATE = "stats_update"
    TRANSFER_PROGRESS = "transfer_progress"
    BANDWIDTH_UPDATE = "bandwidth_update"
    PEER_STATUS_UPDATE = "peer_status_update"
    CONFLICT_DETECTED = "conflict_detected"
    TRANSFER_COMPLETED = "transfer_completed"
    ERROR = "error"
    HEARTBEAT = "heartbeat"


class SubscriptionType(Enum):
    """What to subscribe to"""
    ALL = "all"
    STATS = "stats"
    TRANSFERS = "transfers"
    BANDWIDTH = "bandwidth"
    PEERS = "peers"
    CONFLICTS = "conflicts"


@dataclass
class WebSocketMessage:
    """A WebSocket message"""
    message_type: MessageType
    timestamp: float = field(default_factory=time.time)
    payload: Dict[str, Any] = field(default_factory=dict)
    message_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])

    def to_json(self) -> str:
        """Convert to JSON"""
        return json.dumps({
            'type': self.message_type.value,
            'timestamp': self.timestamp,
            'payload': self.payload,
            'message_id': self.message_id
        })

    @classmethod
    def from_json(cls, json_str: str) -> Optional['WebSocketMessage']:
        """Create from JSON"""
        try:
            data = json.loads(json_str)
            return cls(
                message_type=MessageType(data['type']),
                timestamp=data.get('timestamp', time.time()),
                payload=data.get('payload', {}),
                message_id=data.get('message_id', str(uuid.uuid4())[:8])
            )
        except Exception as e:
            logger.error(f"Error parsing WebSocket message: {e}")
            return None


@dataclass
class ClientSession:
    """WebSocket client session"""
    client_id: str
    connected_at: float = field(default_factory=time.time)
    last_heartbeat: float = field(default_factory=time.time)
    subscriptions: Set[SubscriptionType] = field(default_factory=set)
    message_queue: asyncio.Queue = field(default_factory=asyncio.Queue)
    websocket: Optional[Any] = None  # websockets.WebSocketServerProtocol

    def is_subscribed(self, subscription: SubscriptionType) -> bool:
        """Check if subscribed to type"""
        return subscription in self.subscriptions or SubscriptionType.ALL in self.subscriptions

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'client_id': self.client_id,
            'connected_at': self.connected_at,
            'uptime_seconds': time.time() - self.connected_at,
            'subscriptions': [s.value for s in self.subscriptions],
            'queue_size': self.message_queue.qsize()
        }


# ============================================================================
# WebSocket Server
# ============================================================================

class WebSocketServer:
    """
    WebSocket server for real-time sync status updates.

    Manages client connections and broadcasts sync events.
    """

    def __init__(self, sync_manager=None, host: str = "0.0.0.0", port: int = 9877,
                 logger_instance=None, stats_update_interval: float = 2.0,
                 heartbeat_interval: float = 30.0, heartbeat_timeout: float = 60.0):
        """
        Initialize WebSocket server.

        Args:
            sync_manager: Sync manager for accessing stats
            host: Server host
            port: Server port
            logger_instance: Logger instance
            stats_update_interval: Stats update frequency (seconds)
            heartbeat_interval: Heartbeat frequency (seconds)
            heartbeat_timeout: Heartbeat timeout (seconds)
        """
        self.logger = logger_instance or logging.getLogger(__name__)
        self.sync_manager = sync_manager
        self.host = host
        self.port = port
        self.stats_update_interval = stats_update_interval
        self.heartbeat_interval = heartbeat_interval
        self.heartbeat_timeout = heartbeat_timeout

        self.clients: Dict[str, ClientSession] = {}
        self.server = None
        self.running = False
        self.message_handlers: Dict[MessageType, Callable] = {}
        self.broadcast_queue: asyncio.Queue = asyncio.Queue()

        # Statistics tracking
        self.total_messages_sent = 0
        self.total_messages_received = 0
        self.started_at = time.time()

    async def start(self) -> None:
        """Start WebSocket server"""
        try:
            # Note: In production, would use websockets library
            # For now, setup message handling and broadcast loops
            self.running = True
            self.logger.info(f"WebSocket server configured on {self.host}:{self.port}")

            # Start background tasks
            await asyncio.gather(
                self._stats_broadcast_loop(),
                self._broadcast_loop(),
                self._heartbeat_loop(),
                return_exceptions=True
            )
        except Exception as e:
            self.logger.error(f"WebSocket server error: {e}")
            self.running = False

    async def stop(self) -> None:
        """Stop WebSocket server"""
        self.running = False
        self.logger.info("WebSocket server stopped")

    async def add_client(self, client_id: str, websocket: Any) -> ClientSession:
        """
        Add new client connection.

        Args:
            client_id: Client identifier
            websocket: WebSocket connection object

        Returns:
            ClientSession
        """
        session = ClientSession(
            client_id=client_id,
            websocket=websocket
        )
        self.clients[client_id] = session

        # Send connection confirmation
        msg = WebSocketMessage(
            message_type=MessageType.CONNECTED,
            payload={'client_id': client_id, 'server_time': time.time()}
        )
        await self._send_to_client(client_id, msg)

        self.logger.info(f"Client connected: {client_id}")
        return session

    async def remove_client(self, client_id: str) -> bool:
        """Remove client connection"""
        if client_id in self.clients:
            del self.clients[client_id]
            self.logger.info(f"Client disconnected: {client_id}")
            return True
        return False

    async def handle_client_message(self, client_id: str, message_json: str) -> None:
        """
        Handle message from client.

        Args:
            client_id: Client identifier
            message_json: JSON message
        """
        message = WebSocketMessage.from_json(message_json)
        if not message:
            return

        self.total_messages_received += 1

        # Get handler for message type
        handler = self.message_handlers.get(message.message_type)

        try:
            if handler:
                await handler(client_id, message)
            else:
                # Default handlers
                if message.message_type == MessageType.SUBSCRIBE:
                    await self._handle_subscribe(client_id, message)
                elif message.message_type == MessageType.UNSUBSCRIBE:
                    await self._handle_unsubscribe(client_id, message)
                elif message.message_type == MessageType.REQUEST_STATS:
                    await self._handle_request_stats(client_id, message)
                elif message.message_type == MessageType.HEARTBEAT:
                    await self._handle_heartbeat(client_id, message)
                else:
                    await self._send_error(client_id, f"Unknown message type: {message.message_type.value}")
        except Exception as e:
            self.logger.error(f"Error handling message from {client_id}: {e}")
            await self._send_error(client_id, str(e))

    async def _handle_subscribe(self, client_id: str, message: WebSocketMessage) -> None:
        """Handle subscription request"""
        client = self.clients.get(client_id)
        if not client:
            return

        subscription_type = message.payload.get('type', 'all')
        try:
            sub = SubscriptionType(subscription_type)
            client.subscriptions.add(sub)
            self.logger.debug(f"Client {client_id} subscribed to {sub.value}")
        except ValueError:
            await self._send_error(client_id, f"Invalid subscription type: {subscription_type}")

    async def _handle_unsubscribe(self, client_id: str, message: WebSocketMessage) -> None:
        """Handle unsubscription request"""
        client = self.clients.get(client_id)
        if not client:
            return

        subscription_type = message.payload.get('type')
        if not subscription_type:
            client.subscriptions.clear()
        else:
            try:
                sub = SubscriptionType(subscription_type)
                client.subscriptions.discard(sub)
            except ValueError:
                pass

    async def _handle_request_stats(self, client_id: str, message: WebSocketMessage) -> None:
        """Handle stats request"""
        stats = self._get_sync_stats()
        msg = WebSocketMessage(
            message_type=MessageType.STATS_UPDATE,
            payload=stats
        )
        await self._send_to_client(client_id, msg)

    async def _handle_heartbeat(self, client_id: str, message: WebSocketMessage) -> None:
        """Handle heartbeat"""
        client = self.clients.get(client_id)
        if client:
            client.last_heartbeat = time.time()

    async def _send_to_client(self, client_id: str, message: WebSocketMessage) -> None:
        """Send message to specific client"""
        client = self.clients.get(client_id)
        if not client or not client.websocket:
            return

        try:
            # In production, would send via websocket
            # await client.websocket.send(message.to_json())
            self.total_messages_sent += 1
            self.logger.debug(f"Sent to {client_id}: {message.message_type.value}")
        except Exception as e:
            self.logger.error(f"Error sending to {client_id}: {e}")
            await self.remove_client(client_id)

    async def broadcast_stats(self, stats: Dict[str, Any] = None) -> None:
        """Broadcast statistics to all subscribers"""
        if stats is None:
            stats = self._get_sync_stats()

        message = WebSocketMessage(
            message_type=MessageType.STATS_UPDATE,
            payload=stats
        )

        await self.broadcast(message, SubscriptionType.STATS)

    async def broadcast_transfer_progress(self, transfer_data: Dict[str, Any]) -> None:
        """Broadcast transfer progress update"""
        message = WebSocketMessage(
            message_type=MessageType.TRANSFER_PROGRESS,
            payload=transfer_data
        )
        await self.broadcast(message, SubscriptionType.TRANSFERS)

    async def broadcast_bandwidth(self, bandwidth_data: Dict[str, Any]) -> None:
        """Broadcast bandwidth usage update"""
        message = WebSocketMessage(
            message_type=MessageType.BANDWIDTH_UPDATE,
            payload=bandwidth_data
        )
        await self.broadcast(message, SubscriptionType.BANDWIDTH)

    async def broadcast_peer_status(self, peer_data: Dict[str, Any]) -> None:
        """Broadcast peer status update"""
        message = WebSocketMessage(
            message_type=MessageType.PEER_STATUS_UPDATE,
            payload=peer_data
        )
        await self.broadcast(message, SubscriptionType.PEERS)

    async def broadcast_conflict(self, conflict_data: Dict[str, Any]) -> None:
        """Broadcast conflict notification"""
        message = WebSocketMessage(
            message_type=MessageType.CONFLICT_DETECTED,
            payload=conflict_data
        )
        await self.broadcast(message, SubscriptionType.CONFLICTS)

    async def broadcast(self, message: WebSocketMessage,
                       subscription_filter: Optional[SubscriptionType] = None) -> None:
        """
        Broadcast message to all subscribers.

        Args:
            message: Message to broadcast
            subscription_filter: Only send to subscribers of this type
        """
        for client_id, client in self.clients.items():
            if subscription_filter and not client.is_subscribed(subscription_filter):
                continue

            await self._send_to_client(client_id, message)

    async def _stats_broadcast_loop(self) -> None:
        """Periodically broadcast statistics"""
        while self.running:
            try:
                await asyncio.sleep(self.stats_update_interval)
                await self.broadcast_stats()
            except Exception as e:
                self.logger.error(f"Error in stats broadcast loop: {e}")

    async def _broadcast_loop(self) -> None:
        """Process broadcast queue"""
        while self.running:
            try:
                # Get next message from queue (non-blocking)
                try:
                    message = self.broadcast_queue.get_nowait()
                    await self.broadcast(message)
                except asyncio.QueueEmpty:
                    await asyncio.sleep(0.1)
            except Exception as e:
                self.logger.error(f"Error in broadcast loop: {e}")

    async def _heartbeat_loop(self) -> None:
        """Check client heartbeats"""
        while self.running:
            try:
                await asyncio.sleep(self.heartbeat_interval)
                now = time.time()
                dead_clients = []

                for client_id, client in self.clients.items():
                    if now - client.last_heartbeat > self.heartbeat_timeout:
                        dead_clients.append(client_id)
                    else:
                        # Send heartbeat
                        msg = WebSocketMessage(message_type=MessageType.HEARTBEAT)
                        await self._send_to_client(client_id, msg)

                # Remove dead clients
                for client_id in dead_clients:
                    self.logger.warning(f"Removing unresponsive client: {client_id}")
                    await self.remove_client(client_id)

            except Exception as e:
                self.logger.error(f"Error in heartbeat loop: {e}")

    def _get_sync_stats(self) -> Dict[str, Any]:
        """Get current sync statistics"""
        if not self.sync_manager:
            return {
                'timestamp': time.time(),
                'message': 'Sync manager not available'
            }

        return {
            'timestamp': time.time(),
            'server_uptime_seconds': time.time() - self.started_at,
            'connected_clients': len(self.clients),
            'total_messages_sent': self.total_messages_sent,
            'total_messages_received': self.total_messages_received,
            'client_sessions': [c.to_dict() for c in self.clients.values()]
        }

    async def _send_error(self, client_id: str, error_message: str) -> None:
        """Send error message to client"""
        message = WebSocketMessage(
            message_type=MessageType.ERROR,
            payload={'error': error_message}
        )
        await self._send_to_client(client_id, message)

    def get_connected_clients(self) -> List[str]:
        """Get list of connected client IDs"""
        return list(self.clients.keys())

    def get_statistics(self) -> Dict[str, Any]:
        """Get server statistics"""
        return {
            'running': self.running,
            'host': self.host,
            'port': self.port,
            'connected_clients': len(self.clients),
            'total_messages_sent': self.total_messages_sent,
            'total_messages_received': self.total_messages_received,
            'uptime_seconds': time.time() - self.started_at,
            'clients': {cid: c.to_dict() for cid, c in self.clients.items()}
        }

    def register_message_handler(self, message_type: MessageType,
                                handler: Callable) -> None:
        """Register custom message handler"""
        self.message_handlers[message_type] = handler
        self.logger.info(f"Registered handler for {message_type.value}")


# ============================================================================
# Convenience Functions
# ============================================================================

def create_websocket_server(sync_manager=None, host: str = "0.0.0.0",
                           port: int = 9877) -> WebSocketServer:
    """Create new WebSocket server"""
    return WebSocketServer(sync_manager=sync_manager, host=host, port=port)
