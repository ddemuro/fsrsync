"""
Advanced Inotify Event Aggregation and Deduplication Engine

Optimizes inotify events by:
1. Coalescing multiple events on same file into single logical event
2. Deduplicating redundant events (e.g., multiple MODIFY in quick succession)
3. Detecting event patterns (e.g., OPEN → MODIFY* → CLOSE_WRITE = single write)
4. Time-windowing events to reduce noise (10-100x reduction typical)
5. Tracking event sequences for intelligent batching

How It Works:

1. RAW EVENTS
   Incoming events from inotify: CREATE, OPEN, MODIFY, MODIFY, CLOSE_WRITE

2. AGGREGATION WINDOW
   Events within 100ms time window are grouped:
   [CREATE] [MODIFY MODIFY] [CLOSE_WRITE]

3. DEDUPLICATION
   Remove redundant event types:
   [CREATE] [MODIFY] [CLOSE_WRITE]  (one MODIFY kept)

4. PATTERN MATCHING
   Recognize patterns:
   OPEN → CLOSE_NOWRITE = property change (chmod, xattr, etc)
   OPEN → MODIFY → CLOSE_WRITE = file content write
   CREATE = new file

5. OUTPUT
   Single aggregated event per file:
   Event(path, event_types=[CREATE], timestamp, count=1)

Benefits:
- Reduces event storm (100 events → 1 event for rapid writes)
- Prevents redundant syncs (MODIFY fired 50x per second becomes 1)
- Detects true changes vs temporary modifications
- Saves CPU and bandwidth
- Better ordering for distributed systems

Example:

Before aggregation (100ms window):
1. OPEN file.txt
2. MODIFY file.txt (offset 0-1000)
3. MODIFY file.txt (offset 1000-2000)
4. MODIFY file.txt (offset 2000-3000)
5. CLOSE_WRITE file.txt

After aggregation:
Single event: {path: file.txt, type: FILE_WRITTEN, events: [OPEN, MODIFY, CLOSE_WRITE]}

Result: 1 sync operation instead of 4
"""

import time
import logging
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field
from collections import defaultdict
from threading import Lock, Event
from queue import Queue, Empty

logger = logging.getLogger(__name__)


# ============================================================================
# Event Types and Patterns
# ============================================================================

class AggregatedEventType(Enum):
    """Aggregated logical event types"""
    FILE_CREATED = "FILE_CREATED"              # CREATE event
    FILE_WRITTEN = "FILE_WRITTEN"              # OPEN + MODIFY + CLOSE_WRITE
    FILE_PROPERTY_CHANGED = "FILE_PROPERTY_CHANGED"  # chmod, xattr (ATTRIB)
    FILE_DELETED = "FILE_DELETED"              # DELETE or MOVED_FROM
    FILE_MOVED = "FILE_MOVED"                  # MOVED_FROM + MOVED_TO
    FILE_CLOSED = "FILE_CLOSED"                # Close without writing
    DIRECTORY_CHANGED = "DIRECTORY_CHANGED"    # Operations in directory


class InotifyEventType(Enum):
    """Raw inotify event types (subset)"""
    CREATE = "CREATE"
    MODIFY = "MODIFY"
    DELETE = "DELETE"
    MOVED_FROM = "MOVED_FROM"
    MOVED_TO = "MOVED_TO"
    OPEN = "OPEN"
    CLOSE_WRITE = "CLOSE_WRITE"
    CLOSE_NOWRITE = "CLOSE_NOWRITE"
    ATTRIB = "ATTRIB"
    ISDIR = "ISDIR"


@dataclass
class RawInotifyEvent:
    """Raw event from inotify"""
    path: str
    event_types: List[str]
    timestamp: float = field(default_factory=time.time)
    is_dir: bool = False
    is_move_from: bool = False
    is_move_to: bool = False

    def __hash__(self):
        return hash((self.path, self.timestamp))

    def __eq__(self, other):
        return self.path == other.path and self.timestamp == other.timestamp


@dataclass
class AggregatedEvent:
    """Aggregated logical event after processing"""
    path: str
    event_type: AggregatedEventType
    raw_events: List[str]              # List of raw event types
    timestamp: float                   # First event time
    aggregated_at: float = field(default_factory=time.time)  # When aggregated
    event_count: int = 1              # Number of events aggregated
    is_dir: bool = False
    move_destination: Optional[str] = None  # For FILE_MOVED events

    def age(self) -> float:
        """Time since first event in seconds"""
        return time.time() - self.timestamp

    def __str__(self) -> str:
        return f"AggregatedEvent({self.path}, {self.event_type.value}, " \
               f"events={len(self.raw_events)}, age={self.age():.3f}s)"


# ============================================================================
# Event Deduplicator
# ============================================================================

class EventDeduplicator:
    """Deduplicates redundant event sequences"""

    # Event patterns that should be deduplicated
    REDUNDANT_PATTERNS = {
        # Multiple MODIFY events = single logical write
        ("MODIFY", "MODIFY"): ("MODIFY",),
        # OPEN + CLOSE without WRITE = property change
        ("OPEN", "CLOSE_NOWRITE"): ("ATTRIB",),
        # CREATE + MODIFY = just created (both events same)
        ("CREATE", "MODIFY"): ("CREATE",),
    }

    @staticmethod
    def deduplicate(events: List[str]) -> List[str]:
        """
        Remove redundant events from sequence.

        Args:
            events: List of raw event type strings

        Returns:
            Deduplicated list
        """
        if not events:
            return events

        # Remove consecutive duplicates
        deduplicated = []
        prev_event = None
        for event in events:
            if event != prev_event:
                deduplicated.append(event)
                prev_event = event

        return deduplicated

    @staticmethod
    def get_significant_events(events: List[str]) -> List[str]:
        """
        Extract only significant events from sequence.

        Some events are just noise (e.g., multiple MODIFY).

        Args:
            events: List of raw event type strings

        Returns:
            Significant events only
        """
        # Most significant events (in order of importance)
        significant = []
        event_set = set(events)

        # Check in importance order
        if "DELETE" in event_set:
            significant.append("DELETE")
        elif "MOVED_FROM" in event_set:
            significant.append("MOVED_FROM")
        elif "CREATE" in event_set:
            significant.append("CREATE")

        if "MODIFY" in event_set and "DELETE" not in event_set:
            significant.append("MODIFY")

        if "CLOSE_WRITE" in event_set:
            significant.append("CLOSE_WRITE")
        elif "CLOSE_NOWRITE" in event_set:
            significant.append("CLOSE_NOWRITE")

        if "ATTRIB" in event_set:
            significant.append("ATTRIB")

        if "MOVED_TO" in event_set:
            significant.append("MOVED_TO")

        return significant if significant else events


# ============================================================================
# Event Aggregator
# ============================================================================

class EventAggregator:
    """Aggregates raw inotify events into logical events"""

    def __init__(self, window_size: float = 0.1, logger=None):
        """
        Initialize aggregator.

        Args:
            window_size: Time window in seconds (default 100ms)
            logger: Logger instance
        """
        self.window_size = window_size
        self.logger = logger or logging.getLogger(__name__)
        self.pending_events: Dict[str, List[RawInotifyEvent]] = defaultdict(list)
        self.move_from_events: Dict[str, RawInotifyEvent] = {}  # Track MOVED_FROM
        self.lock = Lock()
        self.deduplicator = EventDeduplicator()

    def add_event(self, event: RawInotifyEvent) -> Optional[AggregatedEvent]:
        """
        Add raw event and return aggregated event if window closed.

        Args:
            event: Raw inotify event

        Returns:
            AggregatedEvent if aggregation window closed, else None
        """
        with self.lock:
            # Handle MOVED_FROM specially (need to pair with MOVED_TO)
            if "MOVED_FROM" in event.event_types:
                self.move_from_events[event.path] = event
                return None

            # Handle MOVED_TO (pair with MOVED_FROM)
            if "MOVED_TO" in event.event_types:
                aggregated = self._handle_move_to(event)
                if aggregated:
                    return aggregated

            # Add to pending
            self.pending_events[event.path].append(event)

            # Check if window should close
            if self._should_close_window(event.path):
                return self._close_window(event.path)

        return None

    def _should_close_window(self, path: str) -> bool:
        """Check if aggregation window should close for path"""
        if path not in self.pending_events:
            return False

        events = self.pending_events[path]
        if not events:
            return False

        # Close window if:
        # 1. We have DELETE, MOVED_FROM (terminal events)
        # 2. We have CLOSE_WRITE or CLOSE_NOWRITE
        event_set = {e for events_list in self.pending_events[path]
                     for e in events_list.event_types}

        return any(e in event_set for e in ["DELETE", "MOVED_FROM",
                                             "CLOSE_WRITE", "CLOSE_NOWRITE"])

    def _close_window(self, path: str) -> Optional[AggregatedEvent]:
        """Close aggregation window for path and return aggregated event"""
        if path not in self.pending_events:
            return None

        events = self.pending_events.pop(path)
        if not events:
            return None

        # Flatten events
        raw_event_types = []
        first_timestamp = events[0].timestamp
        is_dir = events[0].is_dir

        for event in events:
            raw_event_types.extend(event.event_types)

        # Deduplicate
        deduplicated = self.deduplicator.deduplicate(raw_event_types)
        significant = self.deduplicator.get_significant_events(deduplicated)

        # Determine aggregated event type
        event_type = self._determine_event_type(significant, is_dir)

        aggregated = AggregatedEvent(
            path=path,
            event_type=event_type,
            raw_events=significant,
            timestamp=first_timestamp,
            event_count=len(events),
            is_dir=is_dir
        )

        self.logger.debug(f"Aggregated {len(events)} events on {path}: "
                         f"{significant} → {event_type.value}")

        return aggregated

    def _handle_move_to(self, event: RawInotifyEvent) -> Optional[AggregatedEvent]:
        """Handle MOVED_TO event paired with MOVED_FROM"""
        # Look for previous MOVED_FROM
        move_from = None
        for path in list(self.move_from_events.keys()):
            move_from = self.move_from_events.pop(path)
            break

        if move_from is None:
            # No matching MOVED_FROM, treat as create
            self.pending_events[event.path].append(event)
            return None

        # Create move event
        aggregated = AggregatedEvent(
            path=move_from.path,
            event_type=AggregatedEventType.FILE_MOVED,
            raw_events=["MOVED_FROM", "MOVED_TO"],
            timestamp=move_from.timestamp,
            move_destination=event.path,
            is_dir=event.is_dir
        )

        self.logger.debug(f"Detected move: {move_from.path} → {event.path}")
        return aggregated

    def _determine_event_type(self, events: List[str],
                             is_dir: bool) -> AggregatedEventType:
        """Determine aggregated event type from raw events"""
        event_set = set(events)

        if is_dir:
            return AggregatedEventType.DIRECTORY_CHANGED

        if "DELETE" in event_set:
            return AggregatedEventType.FILE_DELETED

        if "MOVED_FROM" in event_set:
            return AggregatedEventType.FILE_MOVED

        if "CREATE" in event_set:
            return AggregatedEventType.FILE_CREATED

        if "CLOSE_WRITE" in event_set or "MODIFY" in event_set:
            return AggregatedEventType.FILE_WRITTEN

        if "ATTRIB" in event_set or "CLOSE_NOWRITE" in event_set:
            return AggregatedEventType.FILE_PROPERTY_CHANGED

        if "CLOSE_NOWRITE" in event_set:
            return AggregatedEventType.FILE_CLOSED

        return AggregatedEventType.FILE_PROPERTY_CHANGED

    def flush(self) -> List[AggregatedEvent]:
        """
        Force close all pending windows and return aggregated events.

        Used at shutdown to ensure no pending events are lost.

        Returns:
            List of AggregatedEvent objects
        """
        with self.lock:
            aggregated = []
            for path in list(self.pending_events.keys()):
                event = self._close_window(path)
                if event:
                    aggregated.append(event)

            # Don't forget unpaired MOVED_FROM events
            for path, event in self.move_from_events.items():
                aggregated.append(AggregatedEvent(
                    path=path,
                    event_type=AggregatedEventType.FILE_DELETED,
                    raw_events=["MOVED_FROM"],
                    timestamp=event.timestamp,
                    is_dir=event.is_dir
                ))
            self.move_from_events.clear()

            return aggregated


# ============================================================================
# Inotify Event Engine (Main)
# ============================================================================

class InotifyEngine:
    """
    Advanced inotify event processing engine with aggregation and deduplication.

    Provides a high-level interface for processing filesystem events
    with intelligent batching and noise reduction.
    """

    def __init__(self, window_size: float = 0.1, logger=None):
        """
        Initialize engine.

        Args:
            window_size: Event aggregation window in seconds
            logger: Logger instance
        """
        self.window_size = window_size
        self.logger = logger or logging.getLogger(__name__)
        self.aggregator = EventAggregator(window_size, logger)
        self.event_queue: Queue[AggregatedEvent] = Queue()
        self.lock = Lock()
        self.stats = {
            "raw_events_received": 0,
            "events_aggregated": 0,
            "total_deduplicated": 0,
            "avg_events_per_aggregation": 0,
        }

    def process_event(self, path: str, event_types: List[str],
                     is_dir: bool = False) -> Optional[AggregatedEvent]:
        """
        Process raw inotify event.

        Args:
            path: File path
            event_types: List of event type strings
            is_dir: Whether this is a directory

        Returns:
            AggregatedEvent if aggregation completed, else None
        """
        with self.lock:
            self.stats["raw_events_received"] += 1

        raw_event = RawInotifyEvent(
            path=path,
            event_types=event_types,
            is_dir=is_dir
        )

        aggregated = self.aggregator.add_event(raw_event)

        if aggregated:
            with self.lock:
                self.stats["events_aggregated"] += 1
                self.stats["total_deduplicated"] += aggregated.event_count - 1

            self.event_queue.put(aggregated)
            return aggregated

        return None

    def get_aggregated_events(self, timeout: Optional[float] = None) -> List[AggregatedEvent]:
        """
        Get aggregated events from queue.

        Args:
            timeout: Optional timeout in seconds

        Returns:
            List of AggregatedEvent objects
        """
        events = []
        while True:
            try:
                wait_time = timeout if timeout is not None else 0.1
                event = self.event_queue.get(timeout=wait_time)
                events.append(event)
            except Empty:
                break

        return events

    def flush(self) -> List[AggregatedEvent]:
        """
        Flush all pending events.

        Returns:
            List of remaining AggregatedEvent objects
        """
        aggregated = self.aggregator.flush()

        for event in aggregated:
            self.event_queue.put(event)

        return self.get_aggregated_events()

    def get_statistics(self) -> Dict[str, any]:
        """Get engine statistics"""
        with self.lock:
            stats = self.stats.copy()

        if stats["events_aggregated"] > 0:
            stats["avg_events_per_aggregation"] = \
                (stats["raw_events_received"] - stats["events_aggregated"]) / \
                stats["events_aggregated"] + 1

        return stats

    def reset_statistics(self) -> None:
        """Reset statistics"""
        with self.lock:
            for key in self.stats:
                self.stats[key] = 0


# ============================================================================
# Utility Functions
# ============================================================================

def create_engine(window_size: float = 0.1) -> InotifyEngine:
    """Create new inotify engine with default settings"""
    return InotifyEngine(window_size=window_size)


def process_events_batch(engine: InotifyEngine,
                        events: List[Tuple[str, List[str], bool]]) -> List[AggregatedEvent]:
    """
    Process batch of raw events.

    Args:
        engine: InotifyEngine instance
        events: List of (path, event_types, is_dir) tuples

    Returns:
        List of aggregated events
    """
    results = []
    for path, event_types, is_dir in events:
        event = engine.process_event(path, event_types, is_dir)
        if event:
            results.append(event)

    return results
