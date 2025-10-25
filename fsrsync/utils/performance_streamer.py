"""
Real-time Performance Streaming System for FSRsync

Provides WebSocket-based real-time performance monitoring with:
- Live metric streaming
- Performance event broadcasting
- Client subscription management
- Rate limiting and buffering
- Performance alert streaming
- Dashboard real-time updates

## Stream Types

METRICS: Real-time metric updates
ALERTS: Performance alerts and anomalies
EVENTS: Performance-related events
TRENDS: Trend analysis updates
"""

import time
import logging
import asyncio
import json
from typing import Dict, List, Optional, Any, Set, Callable
from dataclasses import dataclass, field, asdict
from enum import Enum
from collections import defaultdict, deque
import threading


class StreamType(Enum):
    """Type of performance stream"""
    METRICS = "metrics"
    ALERTS = "alerts"
    EVENTS = "events"
    TRENDS = "trends"
    DIAGNOSTICS = "diagnostics"


class ClientStatus(Enum):
    """Status of stream client"""
    CONNECTED = "connected"
    SUBSCRIBED = "subscribed"
    PAUSED = "paused"
    DISCONNECTED = "disconnected"


@dataclass
class PerformanceEvent:
    """Performance event for streaming"""
    event_id: str
    event_type: str
    timestamp: float
    metric_name: str
    value: float
    metadata: Dict[str, Any] = field(default_factory=dict)
    severity: str = "info"  # info, warning, error, critical


@dataclass
class StreamSubscription:
    """Client subscription to performance streams"""
    client_id: str
    subscribed_streams: Set[StreamType] = field(default_factory=set)
    metrics_filter: Set[str] = field(default_factory=set)  # Empty = all
    update_interval: int = 1000  # milliseconds
    max_buffer_size: int = 100
    created_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)


@dataclass
class StreamBuffer:
    """Buffer for streaming data"""
    buffer_id: str
    buffer_type: StreamType
    max_size: int = 1000
    events: deque = field(default_factory=lambda: deque(maxlen=1000))
    created_at: float = field(default_factory=time.time)
    last_sent: float = field(default_factory=time.time)


class PerformanceStreamer:
    """
    Real-time performance streaming system.

    Streams live performance metrics and alerts to connected clients
    via WebSocket using publish-subscribe pattern.
    """

    def __init__(self, logger_instance=None):
        """
        Initialize performance streamer.

        Args:
            logger_instance: Logger instance
        """
        self.logger = logger_instance or logging.getLogger(__name__)

        # Client management
        self.clients: Dict[str, StreamSubscription] = {}
        self.client_status: Dict[str, ClientStatus] = {}

        # Stream buffers (stream_type -> StreamBuffer)
        self.buffers: Dict[str, StreamBuffer] = {}
        self._init_buffers()

        # Event callbacks for each stream type
        self.callbacks: Dict[StreamType, List[Callable]] = defaultdict(list)

        # Performance event queue
        self.event_queue: deque = deque(maxlen=10000)

        # Streaming statistics
        self.stats: Dict[str, Any] = {
            'total_events': 0,
            'total_clients': 0,
            'active_streams': 0,
            'events_sent': 0
        }

        # Rate limiting
        self.rate_limits: Dict[str, Tuple[int, int]] = {
            'metrics': (100, 1),  # 100 events per 1 second
            'alerts': (50, 1),
            'events': (100, 1),
            'trends': (20, 5)
        }

        self.rate_trackers: Dict[str, deque] = defaultdict(lambda: deque(maxlen=100))

        self.logger.info("PerformanceStreamer initialized")

    def _init_buffers(self) -> None:
        """Initialize stream buffers for each stream type"""
        try:
            for stream_type in StreamType:
                buffer = StreamBuffer(
                    buffer_id=f"buffer_{stream_type.value}",
                    buffer_type=stream_type,
                    max_size=1000
                )
                self.buffers[stream_type.value] = buffer

        except Exception as e:
            self.logger.error(f"Error initializing buffers: {e}")

    def register_client(self, client_id: str, update_interval: int = 1000) -> bool:
        """
        Register a new client for streaming.

        Args:
            client_id: Unique client identifier
            update_interval: Update interval in milliseconds

        Returns:
            True if registered successfully
        """
        try:
            if client_id in self.clients:
                self.logger.warning(f"Client already registered: {client_id}")
                return False

            subscription = StreamSubscription(
                client_id=client_id,
                update_interval=update_interval
            )

            self.clients[client_id] = subscription
            self.client_status[client_id] = ClientStatus.CONNECTED

            self.stats['total_clients'] += 1

            self.logger.info(f"Registered client: {client_id}")
            return True

        except Exception as e:
            self.logger.error(f"Error registering client: {e}")
            return False

    def unregister_client(self, client_id: str) -> bool:
        """
        Unregister a client.

        Args:
            client_id: Client identifier

        Returns:
            True if unregistered successfully
        """
        try:
            if client_id not in self.clients:
                return False

            del self.clients[client_id]
            self.client_status[client_id] = ClientStatus.DISCONNECTED

            self.logger.info(f"Unregistered client: {client_id}")
            return True

        except Exception as e:
            self.logger.error(f"Error unregistering client: {e}")
            return False

    def subscribe_client(self, client_id: str, stream_types: List[str],
                        metrics_filter: Optional[List[str]] = None) -> bool:
        """
        Subscribe client to specific streams.

        Args:
            client_id: Client identifier
            stream_types: List of stream type names
            metrics_filter: Optional metric name filter

        Returns:
            True if subscribed successfully
        """
        try:
            if client_id not in self.clients:
                self.logger.warning(f"Client not registered: {client_id}")
                return False

            subscription = self.clients[client_id]

            # Add stream subscriptions
            for stream_type_name in stream_types:
                try:
                    stream_type = StreamType[stream_type_name.upper()]
                    subscription.subscribed_streams.add(stream_type)
                except (KeyError, ValueError):
                    self.logger.warning(f"Invalid stream type: {stream_type_name}")

            # Set metrics filter
            if metrics_filter:
                subscription.metrics_filter = set(metrics_filter)

            self.client_status[client_id] = ClientStatus.SUBSCRIBED
            self.stats['active_streams'] = len([c for c in self.client_status.values()
                                               if c == ClientStatus.SUBSCRIBED])

            self.logger.info(f"Subscribed client {client_id} to streams: {stream_types}")
            return True

        except Exception as e:
            self.logger.error(f"Error subscribing client: {e}")
            return False

    def unsubscribe_client(self, client_id: str, stream_types: Optional[List[str]] = None) -> bool:
        """
        Unsubscribe client from streams.

        Args:
            client_id: Client identifier
            stream_types: Optional specific stream types to unsubscribe from

        Returns:
            True if unsubscribed successfully
        """
        try:
            if client_id not in self.clients:
                return False

            subscription = self.clients[client_id]

            if stream_types:
                for stream_type_name in stream_types:
                    try:
                        stream_type = StreamType[stream_type_name.upper()]
                        subscription.subscribed_streams.discard(stream_type)
                    except (KeyError, ValueError):
                        pass
            else:
                subscription.subscribed_streams.clear()

            if not subscription.subscribed_streams:
                self.client_status[client_id] = ClientStatus.CONNECTED

            return True

        except Exception as e:
            self.logger.error(f"Error unsubscribing client: {e}")
            return False

    def publish_metric(self, metric_name: str, value: float,
                      metadata: Optional[Dict[str, Any]] = None) -> None:
        """
        Publish a performance metric.

        Args:
            metric_name: Name of metric
            value: Metric value
            metadata: Optional metadata
        """
        try:
            # Check rate limiting
            if not self._check_rate_limit('metrics'):
                return

            import uuid
            event = PerformanceEvent(
                event_id=str(uuid.uuid4()),
                event_type="metric",
                timestamp=time.time(),
                metric_name=metric_name,
                value=value,
                metadata=metadata or {},
                severity="info"
            )

            self._queue_event(event, StreamType.METRICS)

        except Exception as e:
            self.logger.error(f"Error publishing metric: {e}")

    def publish_alert(self, metric_name: str, severity: str,
                     message: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """
        Publish a performance alert.

        Args:
            metric_name: Name of metric
            severity: Alert severity (info, warning, error, critical)
            message: Alert message
            metadata: Optional metadata
        """
        try:
            if not self._check_rate_limit('alerts'):
                return

            import uuid
            event = PerformanceEvent(
                event_id=str(uuid.uuid4()),
                event_type="alert",
                timestamp=time.time(),
                metric_name=metric_name,
                value=0.0,
                metadata={'message': message, **(metadata or {})},
                severity=severity
            )

            self._queue_event(event, StreamType.ALERTS)

        except Exception as e:
            self.logger.error(f"Error publishing alert: {e}")

    def publish_event(self, event_type: str, metric_name: str,
                     value: float, metadata: Optional[Dict[str, Any]] = None) -> None:
        """
        Publish a generic performance event.

        Args:
            event_type: Type of event
            metric_name: Name of metric
            value: Event value
            metadata: Optional metadata
        """
        try:
            if not self._check_rate_limit('events'):
                return

            import uuid
            event = PerformanceEvent(
                event_id=str(uuid.uuid4()),
                event_type=event_type,
                timestamp=time.time(),
                metric_name=metric_name,
                value=value,
                metadata=metadata or {}
            )

            self._queue_event(event, StreamType.EVENTS)

        except Exception as e:
            self.logger.error(f"Error publishing event: {e}")

    def _queue_event(self, event: PerformanceEvent, stream_type: StreamType) -> None:
        """Queue event for delivery"""
        try:
            self.event_queue.append({
                'event': event,
                'stream_type': stream_type,
                'enqueued_at': time.time()
            })

            # Add to appropriate buffer
            if stream_type.value in self.buffers:
                buffer = self.buffers[stream_type.value]
                buffer.events.append(asdict(event))

            self.stats['total_events'] += 1

            # Trigger callbacks
            for callback in self.callbacks.get(stream_type, []):
                try:
                    callback(event)
                except Exception as e:
                    self.logger.error(f"Error in callback: {e}")

        except Exception as e:
            self.logger.error(f"Error queueing event: {e}")

    def _check_rate_limit(self, stream_type_name: str) -> bool:
        """Check if event can be published based on rate limit"""
        try:
            if stream_type_name not in self.rate_limits:
                return True

            limit, window = self.rate_limits[stream_type_name]
            tracker = self.rate_trackers[stream_type_name]

            now = time.time()
            cutoff = now - window

            # Remove old entries
            while tracker and tracker[0] < cutoff:
                tracker.popleft()

            if len(tracker) < limit:
                tracker.append(now)
                return True

            return False

        except Exception as e:
            self.logger.error(f"Error checking rate limit: {e}")
            return True

    def register_callback(self, stream_type: str, callback: Callable) -> None:
        """
        Register callback for stream events.

        Args:
            stream_type: Stream type name
            callback: Callback function
        """
        try:
            try:
                st = StreamType[stream_type.upper()]
                self.callbacks[st].append(callback)
            except (KeyError, ValueError):
                self.logger.warning(f"Invalid stream type: {stream_type}")

        except Exception as e:
            self.logger.error(f"Error registering callback: {e}")

    def get_client_updates(self, client_id: str) -> Optional[Dict[str, Any]]:
        """
        Get pending updates for client.

        Args:
            client_id: Client identifier

        Returns:
            Updates data if client is subscribed
        """
        try:
            if client_id not in self.clients:
                return None

            subscription = self.clients[client_id]

            if not subscription.subscribed_streams:
                return None

            updates = {
                'timestamp': time.time(),
                'client_id': client_id,
                'streams': {}
            }

            for stream_type in subscription.subscribed_streams:
                buffer = self.buffers.get(stream_type.value)
                if buffer:
                    events = list(buffer.events)

                    # Filter by metrics if specified
                    if subscription.metrics_filter:
                        events = [e for e in events
                                 if e.get('metric_name') in subscription.metrics_filter]

                    updates['streams'][stream_type.value] = events[-10:]  # Last 10 events

            # Update last activity
            subscription.last_activity = time.time()
            self.stats['events_sent'] += sum(
                len(v.get('streams', {}).get(k, []))
                for k, v in [('', updates)]
            )

            return updates

        except Exception as e:
            self.logger.error(f"Error getting client updates: {e}")
            return None

    def get_connected_clients(self) -> List[Dict[str, Any]]:
        """Get list of connected clients"""
        try:
            return [
                {
                    'client_id': client_id,
                    'status': self.client_status.get(client_id, ClientStatus.DISCONNECTED).value,
                    'subscriptions': len(subscription.subscribed_streams),
                    'last_activity': subscription.last_activity
                }
                for client_id, subscription in self.clients.items()
            ]

        except Exception as e:
            self.logger.error(f"Error getting clients: {e}")
            return []

    def get_streaming_summary(self) -> Dict[str, Any]:
        """Get streaming system summary"""
        try:
            active_count = sum(1 for status in self.client_status.values()
                              if status == ClientStatus.SUBSCRIBED)

            return {
                'timestamp': time.time(),
                'total_clients': len(self.clients),
                'active_streams': active_count,
                'total_events_published': self.stats['total_events'],
                'total_events_sent': self.stats['events_sent'],
                'event_queue_size': len(self.event_queue),
                'connected_clients': self.get_connected_clients()
            }

        except Exception as e:
            self.logger.error(f"Error getting summary: {e}")
            return {}
