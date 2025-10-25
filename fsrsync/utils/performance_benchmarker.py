"""
Advanced Performance Benchmarking Module for FSRsync

Provides comprehensive performance metrics collection with:
- Multi-component profiling
- Latency and throughput measurement
- Memory and CPU tracking
- I/O performance analysis
- Baseline comparison and regression detection
- Detailed performance reports

## Metrics Categories

LATENCY: Response time measurement
THROUGHPUT: Operations per second
MEMORY: Memory usage and allocation
CPU: CPU utilization and time
IO: Disk I/O operations and bandwidth
NETWORK: Network latency and bandwidth
"""

import time
import logging
import psutil
import json
from typing import Dict, List, Optional, Any, Tuple, Callable
from dataclasses import dataclass, field
from enum import Enum
from collections import deque, defaultdict
import statistics


class MetricType(Enum):
    """Type of performance metric"""
    LATENCY = "latency"
    THROUGHPUT = "throughput"
    MEMORY = "memory"
    CPU = "cpu"
    IO = "io"
    NETWORK = "network"


class PerformanceLevel(Enum):
    """Performance level classification"""
    EXCELLENT = "excellent"  # <= 50% of threshold
    GOOD = "good"  # <= 75% of threshold
    ACCEPTABLE = "acceptable"  # <= 100% of threshold
    DEGRADED = "degraded"  # 100-150% of threshold
    CRITICAL = "critical"  # > 150% of threshold


@dataclass
class MetricSample:
    """Single metric measurement"""
    metric_type: MetricType
    component: str
    value: float
    unit: str
    timestamp: float = field(default_factory=time.time)
    tags: Dict[str, str] = field(default_factory=dict)


@dataclass
class MetricStats:
    """Statistics for a metric"""
    component: str
    metric_type: MetricType
    unit: str
    count: int = 0
    min_value: float = float('inf')
    max_value: float = float('-inf')
    mean_value: float = 0.0
    median_value: float = 0.0
    p95_value: float = 0.0
    p99_value: float = 0.0
    std_dev: float = 0.0
    total_value: float = 0.0
    performance_level: PerformanceLevel = PerformanceLevel.ACCEPTABLE
    threshold: Optional[float] = None


@dataclass
class BenchmarkResult:
    """Complete benchmark result"""
    benchmark_id: str
    component: str
    operation: str
    duration_seconds: float
    start_time: float = field(default_factory=time.time)
    end_time: float = field(default_factory=time.time)
    metrics: Dict[MetricType, MetricStats] = field(default_factory=dict)
    success: bool = True
    error: Optional[str] = None
    iterations: int = 1
    throughput: float = 0.0  # operations per second


class PerformanceBenchmarker:
    """
    Advanced performance benchmarking system.

    Measures and tracks performance metrics across all
    components with statistical analysis and reporting.
    """

    def __init__(self, logger_instance=None):
        """
        Initialize performance benchmarker.

        Args:
            logger_instance: Logger instance
        """
        self.logger = logger_instance or logging.getLogger(__name__)

        # Metric storage
        self.samples: Dict[str, deque] = defaultdict(lambda: deque(maxlen=10000))
        self.results: Dict[str, BenchmarkResult] = {}
        self.baselines: Dict[str, float] = {}

        # Performance thresholds
        self.thresholds: Dict[str, float] = {
            'file_tracking_latency_ms': 2000,  # 2 seconds for 1000 files
            'file_retrieval_latency_ms': 1000,  # 1 second for 5000 files
            'concurrent_op_latency_ms': 5000,  # 5 seconds for 1000 ops
            'memory_usage_mb': 512,  # 512 MB max
            'cpu_usage_percent': 80,  # 80% max
            'disk_io_throughput_mbps': 100,  # 100 MB/s
        }

        # Active benchmarks
        self.active_benchmarks: Dict[str, float] = {}
        self.benchmark_counter = 0

        # Process monitoring
        self.process = psutil.Process()
        self.baseline_memory = self.process.memory_info().rss / (1024 * 1024)
        self.baseline_cpu = 0.0

        self.logger.info("PerformanceBenchmarker initialized")

    def start_benchmark(self, component: str, operation: str) -> str:
        """
        Start a benchmark measurement.

        Args:
            component: Component being benchmarked
            operation: Operation being performed

        Returns:
            Benchmark ID
        """
        try:
            self.benchmark_counter += 1
            benchmark_id = f"{component}_{operation}_{self.benchmark_counter}"

            self.active_benchmarks[benchmark_id] = time.time()

            self.logger.debug(f"Started benchmark: {benchmark_id}")
            return benchmark_id

        except Exception as e:
            self.logger.error(f"Error starting benchmark: {e}")
            return ""

    def end_benchmark(self, benchmark_id: str, success: bool = True,
                     error: Optional[str] = None, iterations: int = 1) -> Optional[BenchmarkResult]:
        """
        End a benchmark measurement.

        Args:
            benchmark_id: Benchmark ID from start_benchmark
            success: Whether benchmark succeeded
            error: Error message if failed
            iterations: Number of iterations performed

        Returns:
            BenchmarkResult if successful
        """
        try:
            if benchmark_id not in self.active_benchmarks:
                self.logger.warning(f"Benchmark {benchmark_id} not found")
                return None

            start_time = self.active_benchmarks[benchmark_id]
            end_time = time.time()
            duration = end_time - start_time

            # Parse benchmark ID
            parts = benchmark_id.rsplit('_', 1)
            component_op = parts[0] if parts else "unknown"
            component, operation = component_op.rsplit('_', 1) if '_' in component_op else (component_op, "unknown")

            # Collect system metrics
            metrics = self._collect_metrics(duration)

            # Create result
            result = BenchmarkResult(
                benchmark_id=benchmark_id,
                component=component,
                operation=operation,
                duration_seconds=duration,
                start_time=start_time,
                end_time=end_time,
                success=success,
                error=error,
                iterations=iterations,
                throughput=iterations / duration if duration > 0 else 0,
                metrics=metrics
            )

            self.results[benchmark_id] = result
            del self.active_benchmarks[benchmark_id]

            self.logger.debug(
                f"Ended benchmark: {benchmark_id}, "
                f"duration={duration:.3f}s, throughput={result.throughput:.2f} ops/s"
            )

            return result

        except Exception as e:
            self.logger.error(f"Error ending benchmark: {e}")
            return None

    def record_metric(self, metric_type: str, component: str, value: float,
                     unit: str, tags: Optional[Dict[str, str]] = None) -> None:
        """
        Record a metric sample.

        Args:
            metric_type: Type of metric
            component: Component name
            value: Metric value
            unit: Unit of measurement
            tags: Optional metric tags
        """
        try:
            metric = MetricSample(
                metric_type=MetricType(metric_type.lower()),
                component=component,
                value=value,
                unit=unit,
                tags=tags or {}
            )

            key = f"{component}_{metric_type}"
            self.samples[key].append(metric)

        except Exception as e:
            self.logger.error(f"Error recording metric: {e}")

    def _collect_metrics(self, duration: float) -> Dict[MetricType, MetricStats]:
        """Collect system performance metrics"""
        try:
            metrics = {}

            # Memory metrics
            mem_info = self.process.memory_info()
            current_memory_mb = mem_info.rss / (1024 * 1024)
            memory_delta = current_memory_mb - self.baseline_memory

            metrics[MetricType.MEMORY] = MetricStats(
                component="system",
                metric_type=MetricType.MEMORY,
                unit="MB",
                count=1,
                min_value=current_memory_mb,
                max_value=current_memory_mb,
                mean_value=current_memory_mb,
                total_value=current_memory_mb
            )

            # CPU metrics
            cpu_percent = self.process.cpu_percent(interval=0.1)

            metrics[MetricType.CPU] = MetricStats(
                component="system",
                metric_type=MetricType.CPU,
                unit="%",
                count=1,
                min_value=cpu_percent,
                max_value=cpu_percent,
                mean_value=cpu_percent,
                total_value=cpu_percent
            )

            # I/O metrics
            io_counters = self.process.io_counters()
            io_throughput = (io_counters.write_bytes + io_counters.read_bytes) / (1024 * 1024) / duration if duration > 0 else 0

            metrics[MetricType.IO] = MetricStats(
                component="system",
                metric_type=MetricType.IO,
                unit="MB/s",
                count=1,
                min_value=io_throughput,
                max_value=io_throughput,
                mean_value=io_throughput,
                total_value=io_throughput
            )

            # Latency metric (duration of operation)
            metrics[MetricType.LATENCY] = MetricStats(
                component="system",
                metric_type=MetricType.LATENCY,
                unit="ms",
                count=1,
                min_value=duration * 1000,
                max_value=duration * 1000,
                mean_value=duration * 1000,
                total_value=duration * 1000
            )

            return metrics

        except Exception as e:
            self.logger.error(f"Error collecting metrics: {e}")
            return {}

    def get_metric_stats(self, component: str, metric_type: str) -> Optional[MetricStats]:
        """
        Get statistics for a metric.

        Args:
            component: Component name
            metric_type: Type of metric

        Returns:
            MetricStats if available
        """
        try:
            key = f"{component}_{metric_type}"

            if key not in self.samples or len(self.samples[key]) == 0:
                return None

            samples = list(self.samples[key])
            values = [s.value for s in samples]

            # Calculate statistics
            stats = MetricStats(
                component=component,
                metric_type=MetricType(metric_type.lower()),
                unit=samples[0].unit if samples else "",
                count=len(values),
                min_value=min(values),
                max_value=max(values),
                mean_value=statistics.mean(values),
                median_value=statistics.median(values),
                p95_value=self._percentile(values, 95),
                p99_value=self._percentile(values, 99),
                std_dev=statistics.stdev(values) if len(values) > 1 else 0.0,
                total_value=sum(values),
                threshold=self.thresholds.get(f"{component}_{metric_type}_ms")
            )

            # Determine performance level
            if stats.threshold:
                if stats.mean_value <= stats.threshold * 0.5:
                    stats.performance_level = PerformanceLevel.EXCELLENT
                elif stats.mean_value <= stats.threshold * 0.75:
                    stats.performance_level = PerformanceLevel.GOOD
                elif stats.mean_value <= stats.threshold:
                    stats.performance_level = PerformanceLevel.ACCEPTABLE
                elif stats.mean_value <= stats.threshold * 1.5:
                    stats.performance_level = PerformanceLevel.DEGRADED
                else:
                    stats.performance_level = PerformanceLevel.CRITICAL

            return stats

        except Exception as e:
            self.logger.error(f"Error getting metric stats: {e}")
            return None

    def _percentile(self, values: List[float], percentile: float) -> float:
        """Calculate percentile value"""
        if not values:
            return 0.0

        sorted_values = sorted(values)
        index = (percentile / 100.0) * len(sorted_values)

        if index == int(index):
            return sorted_values[int(index) - 1]
        else:
            lower = sorted_values[int(index)]
            upper = sorted_values[int(index) + 1]
            return lower + (upper - lower) * (index - int(index))

    def set_baseline(self, metric_name: str, value: float) -> None:
        """Set baseline value for regression detection"""
        self.baselines[metric_name] = value
        self.logger.info(f"Set baseline {metric_name} = {value}")

    def check_regression(self, metric_name: str, current_value: float,
                        threshold_percent: float = 10.0) -> Tuple[bool, float]:
        """
        Check if metric has regressed compared to baseline.

        Args:
            metric_name: Name of metric
            current_value: Current value
            threshold_percent: Regression threshold percentage

        Returns:
            Tuple of (has_regressed, regression_percent)
        """
        try:
            if metric_name not in self.baselines:
                return False, 0.0

            baseline = self.baselines[metric_name]
            if baseline == 0:
                return False, 0.0

            regression_percent = ((current_value - baseline) / baseline) * 100

            has_regressed = regression_percent > threshold_percent

            return has_regressed, regression_percent

        except Exception as e:
            self.logger.error(f"Error checking regression: {e}")
            return False, 0.0

    def get_performance_report(self) -> Dict[str, Any]:
        """Generate comprehensive performance report"""
        try:
            report = {
                'timestamp': time.time(),
                'total_benchmarks': len(self.results),
                'successful_benchmarks': sum(1 for r in self.results.values() if r.success),
                'failed_benchmarks': sum(1 for r in self.results.values() if not r.success),
                'total_samples': sum(len(s) for s in self.samples.values()),
                'benchmarks': {},
                'metrics_summary': {},
                'system_info': {
                    'memory_usage_mb': self.process.memory_info().rss / (1024 * 1024),
                    'cpu_percent': self.process.cpu_percent(),
                    'num_threads': self.process.num_threads(),
                    'num_fds': self.process.num_fds() if hasattr(self.process, 'num_fds') else 0
                }
            }

            # Add benchmark results
            for benchmark_id, result in self.results.items():
                report['benchmarks'][benchmark_id] = {
                    'component': result.component,
                    'operation': result.operation,
                    'duration_seconds': result.duration_seconds,
                    'throughput_ops_per_sec': result.throughput,
                    'success': result.success,
                    'error': result.error,
                    'iterations': result.iterations
                }

            # Add metric summaries
            for key in self.samples.keys():
                component, metric_type = key.rsplit('_', 1)
                stats = self.get_metric_stats(component, metric_type)

                if stats:
                    report['metrics_summary'][key] = {
                        'count': stats.count,
                        'min': stats.min_value,
                        'max': stats.max_value,
                        'mean': stats.mean_value,
                        'median': stats.median_value,
                        'p95': stats.p95_value,
                        'p99': stats.p99_value,
                        'std_dev': stats.std_dev,
                        'unit': stats.unit,
                        'performance_level': stats.performance_level.value
                    }

            return report

        except Exception as e:
            self.logger.error(f"Error generating performance report: {e}")
            return {}

    def export_report(self, filename: str) -> bool:
        """Export performance report to JSON file"""
        try:
            report = self.get_performance_report()

            with open(filename, 'w') as f:
                json.dump(report, f, indent=2)

            self.logger.info(f"Exported performance report to {filename}")
            return True

        except Exception as e:
            self.logger.error(f"Error exporting report: {e}")
            return False
