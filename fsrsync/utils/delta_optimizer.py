"""
Advanced Delta Sync Optimizer for FSRsync

Provides intelligent delta synchronization optimization with:
- Adaptive chunk sizing based on file characteristics
- Algorithm selection based on workload
- Compression optimization
- Chunk cache for frequently accessed blocks
- Parallelized delta computation
- Bandwidth estimation and adaptation
- Progressive transfer strategies

## Delta Optimization Strategies

FAST_SMALL: Fast algorithm for small files (<1MB)
BALANCED: Balanced algorithm for medium files (1-100MB)
THROUGHPUT: Throughput-optimized for large files (>100MB)
ADAPTIVE: Automatically selects algorithm based on analysis
STREAMING: Stream-optimized for very large files
"""

import time
import logging
import threading
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict, deque
import statistics


class DeltaStrategy(Enum):
    """Delta sync strategy"""
    FAST_SMALL = "fast_small"
    BALANCED = "balanced"
    THROUGHPUT = "throughput"
    ADAPTIVE = "adaptive"
    STREAMING = "streaming"


class CompressionLevel(Enum):
    """Compression level for delta data"""
    NONE = 0
    FAST = 1
    BALANCED = 6
    BEST = 9


@dataclass
class ChunkConfig:
    """Delta chunk configuration"""
    strategy: DeltaStrategy
    chunk_size: int  # bytes
    min_chunk_size: int = 512
    max_chunk_size: int = 64 * 1024 * 1024  # 64MB
    compression_level: CompressionLevel = CompressionLevel.BALANCED
    parallelism: int = 4
    cache_enabled: bool = True
    cache_size: int = 100  # number of chunks
    timeout: float = 300.0


@dataclass
class DeltaAnalysis:
    """Analysis of file for optimal delta strategy"""
    file_size: int
    file_type: str
    estimated_change_percent: float
    recommended_strategy: DeltaStrategy
    recommended_chunk_size: int
    compression_benefit: float  # 0-100%
    estimated_bandwidth_reduction: float  # 0-100%
    analysis_time: float = 0.0
    confidence: float = 0.0  # 0-1


@dataclass
class DeltaMetrics:
    """Metrics for delta sync operation"""
    original_size: int
    delta_size: int
    reduction_percent: float
    chunks_processed: int
    chunks_cached: int
    compression_ratio: float
    duration: float
    throughput: float  # MB/s
    cache_hit_rate: float


class DeltaOptimizer:
    """
    Advanced delta sync optimizer.

    Intelligently optimizes delta synchronization based on
    file characteristics and network conditions.
    """

    def __init__(self, logger_instance=None):
        """
        Initialize delta optimizer.

        Args:
            logger_instance: Logger instance
        """
        self.logger = logger_instance or logging.getLogger(__name__)

        # Configuration
        self.chunk_config = ChunkConfig(strategy=DeltaStrategy.ADAPTIVE)

        # Analysis cache (file_path -> DeltaAnalysis)
        self.analysis_cache: Dict[str, DeltaAnalysis] = {}

        # Chunk cache (file_path -> deque of chunks)
        self.chunk_cache: Dict[str, deque] = defaultdict(
            lambda: deque(maxlen=100)
        )

        # Metrics tracking
        self.metrics: Dict[str, DeltaMetrics] = {}

        # Performance history
        self.optimization_history: deque = deque(maxlen=1000)

        # Bandwidth estimator
        self.estimated_bandwidth = 10.0  # MB/s default

        self.logger.info("DeltaOptimizer initialized")

    def analyze_file(self, file_path: str, file_size: int,
                     recent_changes: Optional[List[Tuple[int, int]]] = None) -> DeltaAnalysis:
        """
        Analyze file to determine optimal delta strategy.

        Args:
            file_path: Path to file
            file_size: File size in bytes
            recent_changes: List of (offset, length) tuples of recent changes

        Returns:
            DeltaAnalysis with recommendations
        """
        try:
            # Check cache first
            if file_path in self.analysis_cache:
                cached = self.analysis_cache[file_path]
                if time.time() - cached.analysis_time < 300:  # 5 min cache
                    return cached

            analysis_start = time.time()

            # Estimate change percentage
            change_percent = self._estimate_change_percent(file_size, recent_changes)

            # File type detection (rough)
            file_type = self._detect_file_type(file_path)

            # Recommend strategy
            strategy = self._recommend_strategy(file_size, change_percent, file_type)

            # Recommend chunk size
            chunk_size = self._recommend_chunk_size(file_size, strategy)

            # Estimate compression benefit
            compression_benefit = self._estimate_compression_benefit(
                file_type, change_percent
            )

            # Estimate bandwidth reduction
            bandwidth_reduction = self._estimate_bandwidth_reduction(
                file_size, change_percent, compression_benefit
            )

            analysis = DeltaAnalysis(
                file_size=file_size,
                file_type=file_type,
                estimated_change_percent=change_percent,
                recommended_strategy=strategy,
                recommended_chunk_size=chunk_size,
                compression_benefit=compression_benefit,
                estimated_bandwidth_reduction=bandwidth_reduction,
                analysis_time=time.time() - analysis_start,
                confidence=self._calculate_confidence(file_size, recent_changes)
            )

            # Cache analysis
            self.analysis_cache[file_path] = analysis

            self.logger.info(
                f"Analyzed {file_path}: {strategy.value}, "
                f"chunk_size={chunk_size}, reduction={bandwidth_reduction:.1f}%"
            )

            return analysis

        except Exception as e:
            self.logger.error(f"Error analyzing file: {e}")
            # Return default analysis
            return DeltaAnalysis(
                file_size=file_size,
                file_type="unknown",
                estimated_change_percent=50.0,
                recommended_strategy=DeltaStrategy.BALANCED,
                recommended_chunk_size=4 * 1024 * 1024,
                compression_benefit=20.0,
                estimated_bandwidth_reduction=30.0,
                confidence=0.0
            )

    def _estimate_change_percent(self, file_size: int,
                                recent_changes: Optional[List[Tuple[int, int]]]) -> float:
        """Estimate percentage of file that changed"""
        try:
            if not recent_changes:
                return 50.0  # Default estimate

            total_changed = sum(length for _, length in recent_changes)
            change_percent = (total_changed / file_size) * 100

            return min(change_percent, 100.0)

        except Exception as e:
            self.logger.error(f"Error estimating changes: {e}")
            return 50.0

    def _detect_file_type(self, file_path: str) -> str:
        """Detect file type from extension"""
        try:
            # Common file types
            extension = file_path.split('.')[-1].lower() if '.' in file_path else ''

            if extension in ['txt', 'log', 'csv', 'json', 'xml']:
                return 'text'
            elif extension in ['jpg', 'jpeg', 'png', 'gif', 'webp']:
                return 'image'
            elif extension in ['mp4', 'avi', 'mov', 'mkv']:
                return 'video'
            elif extension in ['zip', 'gz', 'bz2', 'rar']:
                return 'archive'
            elif extension in ['py', 'js', 'java', 'cpp', 'go', 'rs']:
                return 'code'
            else:
                return 'binary'

        except Exception as e:
            self.logger.error(f"Error detecting file type: {e}")
            return 'unknown'

    def _recommend_strategy(self, file_size: int, change_percent: float,
                           file_type: str) -> DeltaStrategy:
        """Recommend delta strategy based on analysis"""
        try:
            # Small files: use fast algorithm
            if file_size < 1024 * 1024:  # < 1MB
                return DeltaStrategy.FAST_SMALL

            # Large files with low changes: use throughput optimization
            if file_size > 100 * 1024 * 1024 and change_percent < 10:  # >100MB, <10% change
                return DeltaStrategy.THROUGHPUT

            # Very large files: use streaming
            if file_size > 1024 * 1024 * 1024:  # > 1GB
                return DeltaStrategy.STREAMING

            # Binary/video files: prefer throughput
            if file_type in ['binary', 'video', 'archive']:
                return DeltaStrategy.THROUGHPUT

            # Text/code files: prefer balanced
            if file_type in ['text', 'code']:
                return DeltaStrategy.BALANCED

            # Default: adaptive
            return DeltaStrategy.ADAPTIVE

        except Exception as e:
            self.logger.error(f"Error recommending strategy: {e}")
            return DeltaStrategy.BALANCED

    def _recommend_chunk_size(self, file_size: int, strategy: DeltaStrategy) -> int:
        """Recommend chunk size based on strategy"""
        try:
            chunk_sizes = {
                DeltaStrategy.FAST_SMALL: 64 * 1024,        # 64KB
                DeltaStrategy.BALANCED: 1 * 1024 * 1024,    # 1MB
                DeltaStrategy.THROUGHPUT: 16 * 1024 * 1024, # 16MB
                DeltaStrategy.STREAMING: 32 * 1024 * 1024,  # 32MB
                DeltaStrategy.ADAPTIVE: 4 * 1024 * 1024     # 4MB
            }

            base_size = chunk_sizes.get(strategy, 4 * 1024 * 1024)

            # Adapt based on file size
            if file_size < 1024 * 1024:
                return max(base_size // 8, 16 * 1024)
            elif file_size < 100 * 1024 * 1024:
                return base_size
            else:
                return min(base_size * 4, 64 * 1024 * 1024)

        except Exception as e:
            self.logger.error(f"Error recommending chunk size: {e}")
            return 4 * 1024 * 1024

    def _estimate_compression_benefit(self, file_type: str, change_percent: float) -> float:
        """Estimate compression benefit percentage"""
        try:
            # Compression benefit by file type
            benefits = {
                'text': 60.0,    # High compression for text
                'code': 55.0,    # Good compression for code
                'log': 70.0,     # Very high for logs
                'binary': 5.0,   # Low for binary
                'video': 2.0,    # Very low for video
                'image': 3.0,    # Very low for images
                'archive': 2.0,  # Already compressed
                'unknown': 20.0
            }

            base_benefit = benefits.get(file_type, 20.0)

            # Only changes can be compressed, adjust by change percentage
            adjusted_benefit = base_benefit * (change_percent / 100)

            return min(adjusted_benefit, 90.0)

        except Exception as e:
            self.logger.error(f"Error estimating compression: {e}")
            return 20.0

    def _estimate_bandwidth_reduction(self, file_size: int, change_percent: float,
                                     compression_benefit: float) -> float:
        """Estimate total bandwidth reduction"""
        try:
            # Only changed bytes need to be transferred
            reduction_from_delta = (100 - change_percent)

            # Additional reduction from compression
            remaining_after_delta = change_percent * (100 - compression_benefit) / 100
            reduction_from_compression = change_percent - remaining_after_delta

            total_reduction = reduction_from_delta + reduction_from_compression

            return min(total_reduction, 95.0)

        except Exception as e:
            self.logger.error(f"Error estimating bandwidth: {e}")
            return 30.0

    def _calculate_confidence(self, file_size: int,
                             recent_changes: Optional[List[Tuple[int, int]]] = None) -> float:
        """Calculate analysis confidence"""
        try:
            confidence = 0.5

            # More confidence with recent change data
            if recent_changes:
                confidence += 0.3

            # More confidence with larger files (more predictable)
            if file_size > 100 * 1024 * 1024:
                confidence += 0.1
            elif file_size < 1024 * 1024:
                confidence -= 0.1

            return min(confidence, 1.0)

        except Exception as e:
            self.logger.error(f"Error calculating confidence: {e}")
            return 0.5

    def optimize_chunk_size(self, current_chunk_size: int,
                           recent_metrics: Optional[List[DeltaMetrics]] = None) -> int:
        """
        Dynamically optimize chunk size based on recent performance.

        Args:
            current_chunk_size: Current chunk size
            recent_metrics: Recent metrics for tuning

        Returns:
            Optimized chunk size
        """
        try:
            if not recent_metrics or len(recent_metrics) < 3:
                return current_chunk_size

            # Calculate average throughput
            throughputs = [m.throughput for m in recent_metrics[-10:]]
            avg_throughput = statistics.mean(throughputs)

            # If throughput is suboptimal, adjust chunk size
            if avg_throughput < 5.0:  # <5 MB/s
                # Increase chunk size to reduce overhead
                return min(current_chunk_size * 2, 64 * 1024 * 1024)
            elif avg_throughput > 50.0:  # >50 MB/s
                # Decrease chunk size for better interactivity
                return max(current_chunk_size // 2, 512 * 1024)

            return current_chunk_size

        except Exception as e:
            self.logger.error(f"Error optimizing chunk size: {e}")
            return current_chunk_size

    def record_metrics(self, file_path: str, metrics: DeltaMetrics) -> None:
        """
        Record delta sync metrics.

        Args:
            file_path: File path
            metrics: DeltaMetrics to record
        """
        try:
            self.metrics[file_path] = metrics
            self.optimization_history.append({
                'timestamp': time.time(),
                'file': file_path,
                'metrics': metrics
            })

        except Exception as e:
            self.logger.error(f"Error recording metrics: {e}")

    def get_optimization_summary(self) -> Dict[str, Any]:
        """Get optimization summary"""
        try:
            if not self.metrics:
                return {'timestamp': time.time(), 'optimizations': []}

            total_original = sum(m.original_size for m in self.metrics.values())
            total_delta = sum(m.delta_size for m in self.metrics.values())
            avg_reduction = statistics.mean([m.reduction_percent for m in self.metrics.values()])
            avg_throughput = statistics.mean([m.throughput for m in self.metrics.values()])

            return {
                'timestamp': time.time(),
                'files_optimized': len(self.metrics),
                'total_original_size': total_original,
                'total_delta_size': total_delta,
                'average_reduction_percent': avg_reduction,
                'average_throughput_mbps': avg_throughput,
                'total_bandwidth_saved': total_original - total_delta,
                'average_cache_hit_rate': statistics.mean([m.cache_hit_rate for m in self.metrics.values()])
            }

        except Exception as e:
            self.logger.error(f"Error getting summary: {e}")
            return {}
