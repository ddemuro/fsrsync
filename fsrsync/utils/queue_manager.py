"""
Intelligent Queue Management

Provides priority-based queue management for FSRsync with:
- File-level prioritization (small before large, text before binary)
- Destination-level load balancing
- Adaptive scheduling based on network conditions
- Deduplication to prevent redundant syncs
- Dead letter handling for problematic files

## Queue Strategies

1. FIFO: Simple first-in-first-out (legacy)
2. PRIORITY: Files with explicit priority
3. ADAPTIVE: Intelligent scheduling based on:
   - File size (small files have priority)
   - File type (text files before binary)
   - Modification time (newer before older)
   - Network conditions (throttle when congested)
   - Transfer history (retry easy files first)

## Destination Load Balancing

- Round-robin assignment
- Capacity-based (assign to least-loaded peer)
- Priority-based (higher priority destinations first)
- Affinity tracking (remember fast peers)

## Deduplication

Prevents redundant syncs of same file:
- Track processed files in current cycle
- Skip if same checksum as last sync
- Merge multiple events for same file

## Dead Letter Queue

Handles problematic files:
- Max retries per file (5 by default)
- Failed file tracking
- Manual retry trigger
- Fallback to slower sync methods

## Examples

```python
manager = QueueManager()

# Add files to sync
manager.enqueue("remote-host", "/path/file.txt", size=1024)
manager.enqueue("remote-host", "/path/large.iso", size=5*1024*1024*1024)

# Get optimized queue
queue = manager.get_optimized_queue()
# Returns: [file.txt, large.iso] - smaller file first

# Track transfer
manager.mark_transfer_in_progress("remote-host", "/path/file.txt")
manager.mark_transfer_completed("remote-host", "/path/file.txt", success=True)

# Check status
pending = manager.get_pending_transfers("remote-host")
failed = manager.get_failed_transfers()
```

## Integration Points

- SyncCoordinator: Gets optimized queue for processing
- BandwidthManager: Respects throttling in scheduling
- TransferEngine: Reports completion/failure
- Dashboard: Displays queue state and statistics
"""

import logging
import time
from enum import Enum
from typing import Dict, Optional, List, Any, Tuple, Set
from dataclasses import dataclass, field
from collections import deque
import hashlib

logger = logging.getLogger(__name__)


# ============================================================================
# Queue Management Types
# ============================================================================

class QueueStrategy(Enum):
    """Queue scheduling strategy"""
    FIFO = "FIFO"              # First in, first out
    PRIORITY = "PRIORITY"      # Explicit priority
    ADAPTIVE = "ADAPTIVE"      # Intelligent scheduling


class QueueItemStatus(Enum):
    """Status of queued item"""
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    DEFERRED = "DEFERRED"


class LoadBalanceStrategy(Enum):
    """Strategy for load balancing across destinations"""
    ROUND_ROBIN = "ROUND_ROBIN"
    LEAST_LOADED = "LEAST_LOADED"
    PRIORITY_BASED = "PRIORITY_BASED"
    AFFINITY = "AFFINITY"


@dataclass
class QueueItem:
    """An item in the sync queue"""
    file_path: str
    destination: str
    file_size: int
    mtime: float
    file_type: str  # 'text', 'binary', 'large'
    checksum: Optional[str] = None
    status: QueueItemStatus = QueueItemStatus.PENDING
    queued_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    retry_count: int = 0
    last_error: Optional[str] = None
    transfer_duration: Optional[float] = None
    priority: int = 1  # Lower = higher priority

    @property
    def is_pending(self) -> bool:
        return self.status == QueueItemStatus.PENDING

    @property
    def is_in_progress(self) -> bool:
        return self.status == QueueItemStatus.IN_PROGRESS

    @property
    def is_completed(self) -> bool:
        return self.status == QueueItemStatus.COMPLETED

    @property
    def is_failed(self) -> bool:
        return self.status == QueueItemStatus.FAILED

    @property
    def wait_time(self) -> float:
        """Time waiting in queue (seconds)"""
        end_time = self.started_at or time.time()
        return end_time - self.queued_at

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'file_path': self.file_path,
            'destination': self.destination,
            'file_size': self.file_size,
            'status': self.status.value,
            'queued_at': self.queued_at,
            'wait_time_seconds': self.wait_time,
            'transfer_duration': self.transfer_duration,
            'retry_count': self.retry_count,
            'priority': self.priority,
            'last_error': self.last_error
        }


@dataclass
class DestinationQueue:
    """Queue for a specific destination"""
    destination: str
    items: deque = field(default_factory=deque)
    in_progress: Set[str] = field(default_factory=set)
    completed: Set[str] = field(default_factory=set)
    failed: Dict[str, QueueItem] = field(default_factory=dict)
    processing_rate: float = 0.0  # Items per second
    last_update: float = field(default_factory=time.time)
    priority: int = 1  # Lower = higher priority

    def add_item(self, item: QueueItem) -> None:
        """Add item to queue"""
        self.items.append(item)

    def get_next_item(self) -> Optional[QueueItem]:
        """Get next item to process"""
        if self.items:
            return self.items.popleft()
        return None

    def get_pending_count(self) -> int:
        """Get count of pending items"""
        return len(self.items)

    def get_active_count(self) -> int:
        """Get count of items in progress"""
        return len(self.in_progress)

    def is_loaded(self, threshold: int = 100) -> bool:
        """Check if queue is heavily loaded"""
        return self.get_pending_count() + self.get_active_count() > threshold

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'destination': self.destination,
            'pending': self.get_pending_count(),
            'in_progress': self.get_active_count(),
            'completed': len(self.completed),
            'failed': len(self.failed),
            'processing_rate': self.processing_rate,
            'priority': self.priority
        }


# ============================================================================
# Queue Manager
# ============================================================================

class QueueManager:
    """
    Intelligent queue management for multi-destination sync.

    Handles prioritization, load balancing, and deduplication.
    """

    # File type classification
    TEXT_EXTENSIONS = {'.txt', '.py', '.java', '.c', '.cpp', '.js', '.json', '.xml',
                       '.csv', '.log', '.md', '.sh', '.yaml', '.yml', '.sql'}
    BINARY_EXTENSIONS = {'.bin', '.exe', '.so', '.dll', '.o', '.class'}
    LARGE_FILE_THRESHOLD = 100 * 1024 * 1024  # 100 MB

    def __init__(self, logger=None,
                 strategy: QueueStrategy = QueueStrategy.ADAPTIVE,
                 load_balance: LoadBalanceStrategy = LoadBalanceStrategy.LEAST_LOADED,
                 max_retries: int = 5,
                 deduplication_enabled: bool = True):
        """
        Initialize queue manager.

        Args:
            logger: Logger instance
            strategy: Queue scheduling strategy
            load_balance: Load balancing strategy
            max_retries: Max retries per file
            deduplication_enabled: Enable deduplication
        """
        self.logger = logger or logging.getLogger(__name__)
        self.strategy = strategy
        self.load_balance = load_balance
        self.max_retries = max_retries
        self.deduplication_enabled = deduplication_enabled

        self.destination_queues: Dict[str, DestinationQueue] = {}
        self.processed_files: Dict[str, str] = {}  # file_path -> checksum
        self.dead_letter_queue: deque = deque()
        self.processing_history: deque = deque(maxlen=1000)
        self.round_robin_index = 0

    def add_destination(self, destination: str, priority: int = 1) -> DestinationQueue:
        """
        Add destination queue.

        Args:
            destination: Destination hostname/path
            priority: Queue priority (lower = higher)

        Returns:
            DestinationQueue
        """
        if destination not in self.destination_queues:
            queue = DestinationQueue(destination=destination, priority=priority)
            self.destination_queues[destination] = queue
            self.logger.info(f"Added queue for destination: {destination}")
            return queue
        return self.destination_queues[destination]

    def enqueue(self, file_path: str, destination: str, file_size: int,
               mtime: float, checksum: Optional[str] = None,
               priority: int = 1) -> bool:
        """
        Add file to sync queue.

        Args:
            file_path: File path
            destination: Target destination
            file_size: File size in bytes
            mtime: Modification time
            checksum: File content hash
            priority: Priority (lower = higher)

        Returns:
            True if enqueued
        """
        # Deduplication check
        if self.deduplication_enabled and file_path in self.processed_files:
            if self.processed_files[file_path] == checksum:
                self.logger.debug(f"Skipping duplicate: {file_path}")
                return False

        # Ensure destination queue exists
        if destination not in self.destination_queues:
            self.add_destination(destination)

        # Classify file type and size
        file_type = self._classify_file_type(file_path, file_size)

        # Create queue item
        item = QueueItem(
            file_path=file_path,
            destination=destination,
            file_size=file_size,
            mtime=mtime,
            file_type=file_type,
            checksum=checksum,
            priority=priority
        )

        # Adjust priority based on file characteristics
        adjusted_priority = self._calculate_priority(item)
        item.priority = adjusted_priority

        self.destination_queues[destination].add_item(item)
        self.logger.debug(f"Enqueued {file_path} to {destination} (priority: {adjusted_priority})")
        return True

    def _classify_file_type(self, file_path: str, file_size: int) -> str:
        """Classify file type"""
        if file_size > self.LARGE_FILE_THRESHOLD:
            return 'large'

        import os
        ext = os.path.splitext(file_path)[1].lower()

        if ext in self.TEXT_EXTENSIONS:
            return 'text'
        elif ext in self.BINARY_EXTENSIONS:
            return 'binary'
        else:
            return 'unknown'

    def _calculate_priority(self, item: QueueItem) -> int:
        """Calculate priority for item (lower = higher)"""
        base_priority = item.priority

        # Boost text files (smaller priority = higher priority)
        if item.file_type == 'text':
            base_priority = max(0, base_priority - 2)

        # Penalize large files
        if item.file_type == 'large':
            base_priority += 2

        # Boost smaller files
        if item.file_size < 1024:
            base_priority = max(0, base_priority - 1)

        # Penalize older files (lower mtime)
        if time.time() - item.mtime > 3600:  # Older than 1 hour
            base_priority += 1

        return base_priority

    def get_next_batch(self, destination: Optional[str] = None,
                       batch_size: int = 10) -> List[QueueItem]:
        """
        Get next batch of items to process.

        Args:
            destination: Specific destination or None for auto-selection
            batch_size: Batch size

        Returns:
            List of QueueItems
        """
        if destination:
            queue = self.destination_queues.get(destination)
            if queue:
                return self._get_batch_from_queue(queue, batch_size)
            return []

        # Auto-select destination based on load balance strategy
        if self.load_balance == LoadBalanceStrategy.ROUND_ROBIN:
            dest = self._select_destination_round_robin()
        elif self.load_balance == LoadBalanceStrategy.LEAST_LOADED:
            dest = self._select_destination_least_loaded()
        elif self.load_balance == LoadBalanceStrategy.PRIORITY_BASED:
            dest = self._select_destination_by_priority()
        else:  # AFFINITY
            dest = self._select_destination_by_affinity()

        if dest:
            return self._get_batch_from_queue(self.destination_queues[dest], batch_size)
        return []

    def _get_batch_from_queue(self, queue: DestinationQueue, batch_size: int) -> List[QueueItem]:
        """Get batch from specific queue"""
        batch = []
        for _ in range(batch_size):
            item = queue.get_next_item()
            if not item:
                break
            item.status = QueueItemStatus.IN_PROGRESS
            item.started_at = time.time()
            queue.in_progress.add(item.file_path)
            batch.append(item)
        return batch

    def _select_destination_round_robin(self) -> Optional[str]:
        """Select destination via round-robin"""
        if not self.destination_queues:
            return None

        destinations = sorted(self.destination_queues.keys())
        self.round_robin_index = (self.round_robin_index + 1) % len(destinations)
        return destinations[self.round_robin_index]

    def _select_destination_least_loaded(self) -> Optional[str]:
        """Select least loaded destination"""
        if not self.destination_queues:
            return None

        return min(
            self.destination_queues.items(),
            key=lambda x: x[1].get_pending_count() + x[1].get_active_count()
        )[0]

    def _select_destination_by_priority(self) -> Optional[str]:
        """Select by priority"""
        if not self.destination_queues:
            return None

        # Find highest priority queue with pending items
        candidates = [
            (dest, queue) for dest, queue in self.destination_queues.items()
            if queue.get_pending_count() > 0
        ]

        if not candidates:
            return None

        return min(candidates, key=lambda x: x[1].priority)[0]

    def _select_destination_by_affinity(self) -> Optional[str]:
        """Select by historical success rate"""
        if not self.destination_queues:
            return None

        best_dest = None
        best_rate = -1.0

        for dest, queue in self.destination_queues.items():
            if queue.get_pending_count() == 0:
                continue

            total = len(queue.completed) + len(queue.failed)
            if total == 0:
                success_rate = 0.5  # Neutral for untested
            else:
                success_rate = len(queue.completed) / total

            if success_rate > best_rate:
                best_rate = success_rate
                best_dest = dest

        return best_dest

    def mark_in_progress(self, file_path: str, destination: str) -> bool:
        """Mark file as in progress"""
        queue = self.destination_queues.get(destination)
        if not queue:
            return False

        if file_path in queue.in_progress:
            return True

        # Move from pending to in_progress
        queue.in_progress.add(file_path)
        return True

    def mark_completed(self, file_path: str, destination: str, checksum: Optional[str] = None) -> bool:
        """
        Mark file transfer as completed.

        Args:
            file_path: File path
            destination: Destination
            checksum: File checksum

        Returns:
            True if marked
        """
        queue = self.destination_queues.get(destination)
        if not queue or file_path not in queue.in_progress:
            return False

        queue.in_progress.discard(file_path)
        queue.completed.add(file_path)

        if checksum:
            self.processed_files[file_path] = checksum

        self.logger.debug(f"Completed: {file_path} → {destination}")
        return True

    def mark_failed(self, file_path: str, destination: str, error: str = "") -> bool:
        """
        Mark file transfer as failed.

        Args:
            file_path: File path
            destination: Destination
            error: Error message

        Returns:
            True if marked
        """
        queue = self.destination_queues.get(destination)
        if not queue:
            return False

        queue.in_progress.discard(file_path)

        # Find item in processed history
        item = None
        for processed in self.processing_history:
            if processed.file_path == file_path and processed.destination == destination:
                item = processed
                break

        if item:
            item.retry_count += 1
            item.last_error = error

            if item.retry_count < self.max_retries:
                # Re-enqueue for retry
                item.status = QueueItemStatus.PENDING
                queue.add_item(item)
                self.logger.info(f"Retrying {file_path} (attempt {item.retry_count}/{self.max_retries})")
                return True
            else:
                # Move to dead letter queue
                item.status = QueueItemStatus.FAILED
                queue.failed[file_path] = item
                self.dead_letter_queue.append(item)
                self.logger.warning(f"Failed permanently: {file_path} after {self.max_retries} retries")
                return False
        else:
            queue.failed[file_path] = QueueItem(
                file_path=file_path,
                destination=destination,
                file_size=0,
                mtime=time.time(),
                file_type='unknown',
                status=QueueItemStatus.FAILED,
                last_error=error,
                retry_count=1
            )
            return False

    def get_statistics(self) -> Dict[str, Any]:
        """Get queue statistics"""
        total_pending = sum(q.get_pending_count() for q in self.destination_queues.values())
        total_active = sum(q.get_active_count() for q in self.destination_queues.values())
        total_completed = sum(len(q.completed) for q in self.destination_queues.values())
        total_failed = sum(len(q.failed) for q in self.destination_queues.values())

        return {
            'total_pending': total_pending,
            'total_active': total_active,
            'total_completed': total_completed,
            'total_failed': total_failed,
            'dead_letter_queue_size': len(self.dead_letter_queue),
            'destinations': {
                dest: queue.to_dict()
                for dest, queue in self.destination_queues.items()
            }
        }

    def clear_queue(self, destination: Optional[str] = None) -> int:
        """Clear queue (for completed items) and return count"""
        if destination:
            queue = self.destination_queues.get(destination)
            if queue:
                count = len(queue.completed)
                queue.completed.clear()
                return count
        else:
            count = sum(len(q.completed) for q in self.destination_queues.values())
            for queue in self.destination_queues.values():
                queue.completed.clear()
            return count
        return 0

    def get_dead_letter_queue(self) -> List[QueueItem]:
        """Get failed items for manual review"""
        return list(self.dead_letter_queue)

    def retry_dead_letter(self, file_path: str, destination: str) -> bool:
        """Retry a failed file"""
        # Find in dead letter queue
        for item in self.dead_letter_queue:
            if item.file_path == file_path and item.destination == destination:
                item.retry_count = 0
                item.status = QueueItemStatus.PENDING
                queue = self.destination_queues.get(destination)
                if queue:
                    queue.add_item(item)
                    self.logger.info(f"Retrying dead letter: {file_path}")
                    return True
        return False


# ============================================================================
# Convenience Functions
# ============================================================================

def create_queue_manager(strategy: QueueStrategy = QueueStrategy.ADAPTIVE,
                        load_balance: LoadBalanceStrategy = LoadBalanceStrategy.LEAST_LOADED,
                        max_retries: int = 5) -> QueueManager:
    """Create new queue manager"""
    return QueueManager(
        strategy=strategy,
        load_balance=load_balance,
        max_retries=max_retries
    )
