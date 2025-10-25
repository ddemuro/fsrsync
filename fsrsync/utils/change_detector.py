"""
Multi-Level Change Detection Strategy

Implements intelligent change detection across multiple layers:
1. Timestamp-based (fastest, least reliable)
2. Size-based (fast, catches obvious changes)
3. Hash-based (slow, most reliable)
4. Selective application based on file type and frequency

Why Multiple Levels?

Different files change at different rates:
- Config files: Change rarely, small → can use hashing
- Video files: Change rarely, huge → can skip hash, use size + mtime
- Source code: Change frequently, medium → use timestamp initially, hash on sync
- Temp files: Change constantly, medium → use mtime window

The strategy uses:
1. Initial filtering (timestamp or size)
2. Quick abort for unchanged files
3. On-demand deeper checks (hash) when needed

Algorithm:

1. TIMESTAMP LEVEL (O(1))
   - Compare modification time only
   - Fastest, catches 90% of changes
   - Used for quick filtering
   - False positives: permission change (mtime changes but content same)

2. SIZE LEVEL (O(1))
   - Compare file size only
   - Very fast, catches most actual changes
   - Used after timestamp if mtime matches but we want to be sure
   - False positives: sparse files, truncated then expanded

3. HASH LEVEL (O(n))
   - Calculate xxHash64 of full content
   - Most reliable, catches all actual changes
   - Expensive for large files
   - Used only when necessary (confirmed different by lower levels)

4. BLOCK-LEVEL HASH (O(n) but returns partial info)
   - Calculate hash of blocks (4KB chunks)
   - Used for efficient sync (see delta_sync.py)
   - Can detect which blocks changed

Application Strategy:

For each file:
1. Check timestamp (mtime) first
   - If unchanged: file is SAME (exit)
   - If changed: proceed to level 2

2. Check size
   - If different: file is DIFFERENT (exit)
   - If same: might be false positive, proceed to level 3

3. Check full hash
   - If different: file is DIFFERENT (exit)
   - If same: file is SAME (content unchanged, only metadata changed)

4. For sync, use block-level hash to identify changed blocks

Result: Most files checked in O(1), occasionally O(n), but we avoid
redundant syncs while catching all real changes.
"""

import time
import logging
from enum import Enum
from typing import Optional, Dict, Tuple, List
from dataclasses import dataclass, field
from pathlib import Path
import xxhash
from threading import Lock

logger = logging.getLogger(__name__)


# ============================================================================
# Change Detection Levels
# ============================================================================

class ChangeLevel(Enum):
    """Change detection checking levels"""
    TIMESTAMP = 1      # mtime only (O(1))
    SIZE = 2           # size only (O(1))
    CONTENT = 3        # full hash (O(n))
    BLOCKS = 4         # block-level hash (O(n) but returns blocks)


class ChangeStatus(Enum):
    """Result of change detection"""
    UNCHANGED = "UNCHANGED"    # File hasn't changed
    CHANGED = "CHANGED"        # File has definitely changed
    UNKNOWN = "UNKNOWN"        # Can't determine without deeper check
    METADATA_ONLY = "METADATA_ONLY"  # Content same, metadata changed


@dataclass
class FileMetrics:
    """Metrics about a file for change detection"""
    path: str
    size: int
    mtime: float
    hash: Optional[str] = None          # Full content hash
    block_hashes: Optional[List[str]] = None  # Block hashes
    checked_at: float = field(default_factory=time.time)

    def is_fresh(self, staleness_threshold: float = 60.0) -> bool:
        """Check if metrics are fresh (within threshold seconds)"""
        return time.time() - self.checked_at < staleness_threshold


# ============================================================================
# Change Detector
# ============================================================================

class ChangeDetector:
    """
    Multi-level change detection with intelligent strategy selection.
    """

    # File type heuristics for strategy selection
    BINARY_EXTENSIONS = {
        'bin', 'exe', 'so', 'dll', 'dylib',  # Binaries
        'mp3', 'mp4', 'mkv', 'avi', 'mov',   # Video/audio
        'jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp',  # Images
        'zip', 'tar', 'gz', 'rar', '7z', 'bz2',      # Archives
        'pdf', 'doc', 'docx', 'xls', 'xlsx',         # Documents
    }

    HUGE_FILE_THRESHOLD = 100 * 1024 * 1024  # 100MB - don't hash these
    MEDIUM_FILE_THRESHOLD = 10 * 1024 * 1024  # 10MB

    def __init__(self, logger=None, cache_metrics: bool = True):
        """
        Initialize detector.

        Args:
            logger: Logger instance
            cache_metrics: Whether to cache file metrics
        """
        self.logger = logger or logging.getLogger(__name__)
        self.cache_metrics = cache_metrics
        self.metrics_cache: Dict[str, FileMetrics] = {}
        self.cache_lock = Lock()

    def detect_change(self, path: str, previous_metrics: Optional[FileMetrics] = None,
                     level: ChangeLevel = ChangeLevel.CONTENT) -> Tuple[ChangeStatus, Optional[FileMetrics]]:
        """
        Detect if file has changed using optimal strategy.

        Args:
            path: Path to file
            previous_metrics: Previous file metrics (optional)
            level: Minimum detection level required

        Returns:
            Tuple of (ChangeStatus, FileMetrics)
        """
        try:
            current_metrics = self._get_metrics(path)
            if current_metrics is None:
                return (ChangeStatus.UNKNOWN, None)

            if previous_metrics is None:
                # No previous metrics, always unknown
                return (ChangeStatus.UNKNOWN, current_metrics)

            # Start from cheapest checks
            return self._check_levels(path, current_metrics, previous_metrics, level)

        except Exception as e:
            self.logger.error(f"Error detecting change on {path}: {e}")
            return (ChangeStatus.UNKNOWN, None)

    def _get_metrics(self, path: str) -> Optional[FileMetrics]:
        """Get basic metrics (size, mtime) for file"""
        try:
            file_path = Path(path)
            if not file_path.exists():
                return None

            stat = file_path.stat()
            return FileMetrics(
                path=path,
                size=stat.st_size,
                mtime=stat.st_mtime
            )

        except Exception as e:
            self.logger.debug(f"Error getting metrics for {path}: {e}")
            return None

    def _check_levels(self, path: str, current: FileMetrics,
                     previous: FileMetrics,
                     min_level: ChangeLevel) -> Tuple[ChangeStatus, FileMetrics]:
        """Check change detection levels in order"""

        # Level 1: Timestamp (fastest)
        if min_level == ChangeLevel.TIMESTAMP:
            if current.mtime == previous.mtime:
                return (ChangeStatus.UNCHANGED, current)
            return (ChangeStatus.CHANGED, current)

        # Level 2: Size (fast)
        if current.size != previous.size:
            return (ChangeStatus.CHANGED, current)

        if min_level == ChangeLevel.SIZE:
            if current.mtime == previous.mtime:
                return (ChangeStatus.UNCHANGED, current)
            # Size same but mtime changed - might be false positive
            return (ChangeStatus.UNKNOWN, current)

        # Level 3: Content hash (slow)
        current_hash = self._get_hash(path)
        if current_hash is None:
            return (ChangeStatus.UNKNOWN, current)

        current.hash = current_hash

        # Did we have previous hash?
        if previous.hash is None:
            # Can't compare, but we know size is same
            # Get previous hash for comparison
            previous.hash = self._get_hash_cached(path, previous)

        if previous.hash is None:
            return (ChangeStatus.UNKNOWN, current)

        if current_hash == previous.hash:
            # Content unchanged
            if current.mtime != previous.mtime:
                return (ChangeStatus.METADATA_ONLY, current)
            return (ChangeStatus.UNCHANGED, current)

        return (ChangeStatus.CHANGED, current)

    def _get_hash(self, path: str, chunk_size: int = 65536) -> Optional[str]:
        """Calculate xxHash64 of file content"""
        try:
            file_path = Path(path)
            if not file_path.exists():
                return None

            hasher = xxhash.xxh64()
            with open(path, 'rb') as f:
                while True:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    hasher.update(chunk)

            return hasher.hexdigest()

        except Exception as e:
            self.logger.debug(f"Error hashing {path}: {e}")
            return None

    def _get_hash_cached(self, path: str,
                        metrics: Optional[FileMetrics] = None) -> Optional[str]:
        """Get hash with caching"""
        if not self.cache_metrics:
            return self._get_hash(path)

        with self.cache_lock:
            cached = self.metrics_cache.get(path)
            if cached and cached.hash and cached.is_fresh():
                return cached.hash

        # Calculate and cache
        hash_value = self._get_hash(path)

        if hash_value and metrics:
            metrics.hash = hash_value
            with self.cache_lock:
                self.metrics_cache[path] = metrics

        return hash_value

    def get_strategy_for_file(self, path: str, size: int) -> ChangeLevel:
        """
        Determine optimal detection strategy for file based on size and type.

        Args:
            path: File path
            size: File size in bytes

        Returns:
            Recommended ChangeLevel
        """
        # Don't hash huge files - use size and mtime
        if size > self.HUGE_FILE_THRESHOLD:
            return ChangeLevel.SIZE

        # Check file type
        extension = Path(path).suffix.lower().lstrip('.')
        if extension in self.BINARY_EXTENSIONS:
            # Binary files - use size + mtime, no hash
            if size > self.MEDIUM_FILE_THRESHOLD:
                return ChangeLevel.SIZE
            return ChangeLevel.CONTENT  # For smaller binaries, hash is OK

        # Text/source files - use full content hash
        return ChangeLevel.CONTENT

    def batch_detect_changes(self, files: List[Tuple[str, Optional[FileMetrics]]],
                            strategy: Optional[Dict[str, ChangeLevel]] = None) -> \
            Dict[str, Tuple[ChangeStatus, Optional[FileMetrics]]]:
        """
        Detect changes for multiple files efficiently.

        Args:
            files: List of (path, previous_metrics) tuples
            strategy: Optional custom strategy per file

        Returns:
            Dict mapping path to (ChangeStatus, CurrentMetrics)
        """
        results = {}
        for path, previous in files:
            level = ChangeLevel.CONTENT
            if strategy and path in strategy:
                level = strategy[path]

            status, metrics = self.detect_change(path, previous, level)
            results[path] = (status, metrics)

        return results

    def get_priority_files(self, results: Dict[str, Tuple[ChangeStatus, Optional[FileMetrics]]],
                          changed_only: bool = True) -> List[str]:
        """
        Get files ordered by priority (changed files first).

        Args:
            results: Results from batch_detect_changes
            changed_only: Only return changed files

        Returns:
            List of paths ordered by priority
        """
        priority = []

        # Changed files first (by priority)
        for path, (status, metrics) in results.items():
            if status == ChangeStatus.CHANGED:
                priority.append((path, 0, metrics.size if metrics else 0))
            elif not changed_only and status != ChangeStatus.UNCHANGED:
                priority.append((path, 1, metrics.size if metrics else 0))

        # Sort by priority, then by size (smaller first)
        priority.sort(key=lambda x: (x[1], x[2]))
        return [p[0] for p in priority]

    def clear_cache(self, path: Optional[str] = None) -> None:
        """Clear metrics cache"""
        with self.cache_lock:
            if path:
                self.metrics_cache.pop(path, None)
            else:
                self.metrics_cache.clear()

    def get_cache_statistics(self) -> Dict[str, int]:
        """Get cache statistics"""
        with self.cache_lock:
            fresh = sum(1 for m in self.metrics_cache.values() if m.is_fresh())
            stale = len(self.metrics_cache) - fresh

        return {
            "cached_files": len(self.metrics_cache),
            "fresh_entries": fresh,
            "stale_entries": stale
        }


# ============================================================================
# Convenience Functions
# ============================================================================

def detect_change(path: str, previous_metrics: Optional[FileMetrics] = None,
                 level: ChangeLevel = ChangeLevel.CONTENT) -> Tuple[ChangeStatus, Optional[FileMetrics]]:
    """
    Convenience function to detect file change.

    Args:
        path: File path
        previous_metrics: Previous metrics
        level: Detection level

    Returns:
        Tuple of (ChangeStatus, FileMetrics)
    """
    detector = ChangeDetector()
    return detector.detect_change(path, previous_metrics, level)


def batch_detect_changes(files: List[Tuple[str, Optional[FileMetrics]]]) -> \
        Dict[str, Tuple[ChangeStatus, Optional[FileMetrics]]]:
    """
    Convenience function to detect changes for multiple files.

    Args:
        files: List of (path, previous_metrics) tuples

    Returns:
        Dict mapping path to (ChangeStatus, CurrentMetrics)
    """
    detector = ChangeDetector()
    return detector.batch_detect_changes(files)
