"""
I/O Performance Analysis System for FSRsync

Provides disk I/O performance profiling with:
- File operation timing analysis
- Disk I/O metrics collection
- Filesystem access pattern detection
- Read/write performance tracking
- I/O bottleneck identification
- Optimization recommendations

## I/O Operation Types

READ: File read operations
WRITE: File write operations
SEEK: File seek/position operations
SYNC: Filesystem sync operations
STAT: File stat/metadata operations
"""

import time
import logging
import os
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict, deque
import statistics


class IOOperationType(Enum):
    """Type of I/O operation"""
    READ = "read"
    WRITE = "write"
    SEEK = "seek"
    SYNC = "sync"
    STAT = "stat"
    DELETE = "delete"
    RENAME = "rename"
    MKDIR = "mkdir"


@dataclass
class IOOperation:
    """I/O operation record"""
    operation_type: IOOperationType
    path: str
    size: int = 0  # bytes
    duration: float = 0.0  # seconds
    timestamp: float = field(default_factory=time.time)
    success: bool = True
    error_msg: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class IOMetrics:
    """I/O performance metrics"""
    operation_type: IOOperationType
    total_operations: int = 0
    total_time: float = 0.0
    total_bytes: int = 0
    min_time: float = float('inf')
    max_time: float = float('-inf')
    avg_time: float = 0.0
    throughput: float = 0.0  # bytes per second
    success_rate: float = 100.0
    error_count: int = 0


@dataclass
class IOBottleneck:
    """I/O bottleneck report"""
    bottleneck_type: str
    severity: str  # low, medium, high, critical
    description: str
    affected_operation: IOOperationType
    current_value: float
    baseline_value: float
    recommendation: str


class IOAnalyzer:
    """
    I/O performance analyzer.

    Tracks and analyzes filesystem I/O operations to identify
    performance bottlenecks and optimization opportunities.
    """

    def __init__(self, logger_instance=None):
        """
        Initialize I/O analyzer.

        Args:
            logger_instance: Logger instance
        """
        self.logger = logger_instance or logging.getLogger(__name__)

        # Operation tracking (operation_type -> deque of IOOperations)
        self.operations: Dict[IOOperationType, deque] = {
            op_type: deque(maxlen=10000) for op_type in IOOperationType
        }

        # Operation metrics (operation_type -> IOMetrics)
        self.metrics: Dict[IOOperationType, IOMetrics] = {
            op_type: IOMetrics(operation_type=op_type) for op_type in IOOperationType
        }

        # Path-specific analysis (path -> list of operations)
        self.path_analysis: Dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))

        # Bottleneck tracking
        self.bottlenecks: List[IOBottleneck] = []

        # Baseline values for comparison
        self.baselines: Dict[str, float] = {}

        # Configuration
        self.slow_operation_threshold = 0.1  # 100ms
        self.min_operations_for_analysis = 10

        self.logger.info("IOAnalyzer initialized")

    def record_operation(self, operation_type: str, path: str, duration: float,
                        size: int = 0, success: bool = True,
                        error_msg: str = "", metadata: Optional[Dict[str, Any]] = None) -> None:
        """
        Record an I/O operation.

        Args:
            operation_type: Type of operation
            path: File path
            duration: Operation duration in seconds
            size: Bytes transferred
            success: Whether operation succeeded
            error_msg: Error message if failed
            metadata: Optional metadata
        """
        try:
            op_type = IOOperationType[operation_type.upper()]

            operation = IOOperation(
                operation_type=op_type,
                path=path,
                size=size,
                duration=duration,
                success=success,
                error_msg=error_msg,
                metadata=metadata or {}
            )

            self.operations[op_type].append(operation)
            self.path_analysis[path].append(operation)

            # Update metrics
            self._update_metrics(op_type, operation)

            # Check for bottlenecks
            if duration > self.slow_operation_threshold:
                self._check_bottleneck(op_type, operation)

        except (KeyError, ValueError):
            self.logger.warning(f"Invalid operation type: {operation_type}")
        except Exception as e:
            self.logger.error(f"Error recording operation: {e}")

    def _update_metrics(self, op_type: IOOperationType, operation: IOOperation) -> None:
        """Update metrics for operation type"""
        try:
            metrics = self.metrics[op_type]

            metrics.total_operations += 1
            metrics.total_time += operation.duration
            metrics.total_bytes += operation.size

            metrics.min_time = min(metrics.min_time, operation.duration)
            metrics.max_time = max(metrics.max_time, operation.duration)

            metrics.avg_time = metrics.total_time / metrics.total_operations

            if operation.size > 0 and operation.duration > 0:
                metrics.throughput = metrics.total_bytes / metrics.total_time

            if not operation.success:
                metrics.error_count += 1

            metrics.success_rate = ((metrics.total_operations - metrics.error_count) /
                                   metrics.total_operations * 100)

        except Exception as e:
            self.logger.error(f"Error updating metrics: {e}")

    def _check_bottleneck(self, op_type: IOOperationType, operation: IOOperation) -> None:
        """Check if operation indicates a bottleneck"""
        try:
            baseline_key = f"{op_type.value}_avg"
            baseline = self.baselines.get(baseline_key, self.slow_operation_threshold)

            if operation.duration > baseline * 1.5:
                severity = self._get_severity(operation.duration, baseline)

                bottleneck = IOBottleneck(
                    bottleneck_type="slow_operation",
                    severity=severity,
                    description=f"Slow {op_type.value} operation on {operation.path}",
                    affected_operation=op_type,
                    current_value=operation.duration,
                    baseline_value=baseline,
                    recommendation=self._get_recommendation(op_type, operation.duration)
                )

                self.bottlenecks.append(bottleneck)

                self.logger.warning(
                    f"Bottleneck detected: {op_type.value} on {operation.path} "
                    f"({operation.duration:.3f}s)"
                )

        except Exception as e:
            self.logger.error(f"Error checking bottleneck: {e}")

    def _get_severity(self, current_time: float, baseline: float) -> str:
        """Determine bottleneck severity"""
        ratio = current_time / baseline

        if ratio < 1.5:
            return "low"
        elif ratio < 3.0:
            return "medium"
        elif ratio < 5.0:
            return "high"
        else:
            return "critical"

    def _get_recommendation(self, op_type: IOOperationType, duration: float) -> str:
        """Get optimization recommendation"""
        if op_type == IOOperationType.READ:
            return "Consider increasing read buffer size or using mmap for large files"
        elif op_type == IOOperationType.WRITE:
            return "Consider batching writes or using async I/O"
        elif op_type == IOOperationType.SYNC:
            return "Reduce frequency of fsync calls or batch operations"
        elif op_type == IOOperationType.STAT:
            return "Cache file stat results where possible"
        elif op_type == IOOperationType.SEEK:
            return "Optimize file access patterns to reduce seeking"
        else:
            return "Review file operation patterns"

    def analyze_path_performance(self, path: str) -> Optional[Dict[str, Any]]:
        """
        Analyze I/O performance for a specific path.

        Args:
            path: File path

        Returns:
            Path performance analysis
        """
        try:
            if path not in self.path_analysis:
                return None

            operations = list(self.path_analysis[path])

            if len(operations) < self.min_operations_for_analysis:
                return None

            # Group by operation type
            by_type = defaultdict(list)
            for op in operations:
                by_type[op.operation_type].append(op)

            analysis = {
                'path': path,
                'total_operations': len(operations),
                'operation_breakdown': {},
                'timing_stats': {},
                'throughput_stats': {}
            }

            for op_type, ops in by_type.items():
                durations = [op.duration for op in ops]
                sizes = [op.size for op in ops if op.size > 0]

                analysis['operation_breakdown'][op_type.value] = len(ops)

                analysis['timing_stats'][op_type.value] = {
                    'min': min(durations),
                    'max': max(durations),
                    'avg': statistics.mean(durations),
                    'stdev': statistics.stdev(durations) if len(durations) > 1 else 0
                }

                if sizes:
                    total_bytes = sum(sizes)
                    total_time = sum(durations)
                    analysis['throughput_stats'][op_type.value] = {
                        'bytes': total_bytes,
                        'throughput': total_bytes / total_time if total_time > 0 else 0
                    }

            return analysis

        except Exception as e:
            self.logger.error(f"Error analyzing path: {e}")
            return None

    def detect_access_patterns(self) -> Dict[str, Any]:
        """
        Detect file access patterns.

        Returns:
            Access pattern analysis
        """
        try:
            patterns = {
                'sequential_reads': 0,
                'sequential_writes': 0,
                'random_access': 0,
                'mixed_access': 0,
                'hot_paths': []
            }

            # Count operation types
            read_count = len(self.operations[IOOperationType.READ])
            write_count = len(self.operations[IOOperationType.WRITE])
            seek_count = len(self.operations[IOOperationType.SEEK])

            # Classify patterns
            if read_count > write_count * 2:
                patterns['sequential_reads'] += 1
            if write_count > read_count * 2:
                patterns['sequential_writes'] += 1
            if seek_count > (read_count + write_count) * 0.5:
                patterns['random_access'] += 1
            if seek_count > 0 and (read_count > 0 or write_count > 0):
                patterns['mixed_access'] += 1

            # Find hot paths (most accessed)
            path_counts = defaultdict(int)
            for ops in self.operations.values():
                for op in ops:
                    path_counts[op.path] += 1

            patterns['hot_paths'] = sorted(
                path_counts.items(),
                key=lambda x: x[1],
                reverse=True
            )[:10]

            return patterns

        except Exception as e:
            self.logger.error(f"Error detecting patterns: {e}")
            return {}

    def get_operation_metrics(self, operation_type: Optional[str] = None) -> Dict[str, Any]:
        """
        Get I/O operation metrics.

        Args:
            operation_type: Optional specific operation type

        Returns:
            Operation metrics
        """
        try:
            if operation_type:
                try:
                    op_type = IOOperationType[operation_type.upper()]
                    metrics = self.metrics[op_type]
                    return {
                        'operation': op_type.value,
                        'total_operations': metrics.total_operations,
                        'total_time': metrics.total_time,
                        'total_bytes': metrics.total_bytes,
                        'avg_time': metrics.avg_time,
                        'min_time': metrics.min_time,
                        'max_time': metrics.max_time,
                        'throughput': metrics.throughput,
                        'success_rate': metrics.success_rate,
                        'error_count': metrics.error_count
                    }
                except (KeyError, ValueError):
                    return {}
            else:
                # Return all metrics
                all_metrics = {}
                for op_type, metrics in self.metrics.items():
                    all_metrics[op_type.value] = {
                        'total_operations': metrics.total_operations,
                        'total_time': metrics.total_time,
                        'total_bytes': metrics.total_bytes,
                        'avg_time': metrics.avg_time,
                        'throughput': metrics.throughput,
                        'success_rate': metrics.success_rate
                    }
                return all_metrics

        except Exception as e:
            self.logger.error(f"Error getting metrics: {e}")
            return {}

    def identify_bottlenecks(self) -> List[Dict[str, Any]]:
        """
        Identify I/O bottlenecks.

        Returns:
            List of bottleneck reports
        """
        try:
            bottleneck_list = []

            # Check each operation type
            for op_type, metrics in self.metrics.items():
                if metrics.total_operations < self.min_operations_for_analysis:
                    continue

                # Check if average time exceeds threshold
                if metrics.avg_time > self.slow_operation_threshold:
                    severity = self._get_severity(metrics.avg_time, self.slow_operation_threshold)

                    bottleneck = IOBottleneck(
                        bottleneck_type="slow_operation_type",
                        severity=severity,
                        description=f"High average time for {op_type.value} operations",
                        affected_operation=op_type,
                        current_value=metrics.avg_time,
                        baseline_value=self.slow_operation_threshold,
                        recommendation=self._get_recommendation(op_type, metrics.avg_time)
                    )

                    bottleneck_list.append({
                        'type': bottleneck.bottleneck_type,
                        'severity': bottleneck.severity,
                        'description': bottleneck.description,
                        'operation': bottleneck.affected_operation.value,
                        'current_avg': bottleneck.current_value,
                        'recommendation': bottleneck.recommendation
                    })

            # Check for high error rates
            for op_type, metrics in self.metrics.items():
                if metrics.success_rate < 95.0:
                    bottleneck_list.append({
                        'type': 'high_error_rate',
                        'severity': 'high' if metrics.success_rate < 90 else 'medium',
                        'description': f"High error rate for {op_type.value} ({metrics.success_rate:.1f}%)",
                        'operation': op_type.value,
                        'error_count': metrics.error_count,
                        'recommendation': 'Investigate operation failures and error logs'
                    })

            return bottleneck_list

        except Exception as e:
            self.logger.error(f"Error identifying bottlenecks: {e}")
            return []

    def set_baseline(self, operation_type: str, value: float) -> bool:
        """
        Set performance baseline for operation.

        Args:
            operation_type: Operation type
            value: Baseline value

        Returns:
            True if set successfully
        """
        try:
            key = f"{operation_type.lower()}_avg"
            self.baselines[key] = value
            self.logger.info(f"Set baseline for {operation_type}: {value:.3f}s")
            return True

        except Exception as e:
            self.logger.error(f"Error setting baseline: {e}")
            return False

    def get_io_summary(self) -> Dict[str, Any]:
        """Get I/O system summary"""
        try:
            total_operations = sum(m.total_operations for m in self.metrics.values())
            total_bytes = sum(m.total_bytes for m in self.metrics.values())
            total_time = sum(m.total_time for m in self.metrics.values())
            avg_throughput = total_bytes / total_time if total_time > 0 else 0

            return {
                'timestamp': time.time(),
                'total_operations': total_operations,
                'total_bytes': total_bytes,
                'total_time': total_time,
                'average_throughput': avg_throughput,
                'bottleneck_count': len(self.bottlenecks),
                'critical_bottlenecks': sum(1 for b in self.bottlenecks if b.severity == 'critical'),
                'paths_analyzed': len(self.path_analysis),
                'operation_breakdown': {
                    op_type.value: self.metrics[op_type].total_operations
                    for op_type in IOOperationType
                }
            }

        except Exception as e:
            self.logger.error(f"Error getting summary: {e}")
            return {}
