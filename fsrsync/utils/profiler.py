"""
Code Profiling and Optimization Analysis for FSRsync

Provides performance profiling with:
- Function call profiling
- Memory profiling
- CPU profiling
- Bottleneck identification
- Optimization recommendations
- Performance comparison

## Profile Types

CPU: CPU time usage
MEMORY: Memory allocation
TIME: Execution time
CALLS: Function call counts
"""

import time
import logging
import tracemalloc
import cProfile
import pstats
import io
from typing import Dict, List, Optional, Any, Callable, Tuple
from dataclasses import dataclass, field
from enum import Enum
from functools import wraps
from collections import defaultdict, deque


class ProfileType(Enum):
    """Type of profiling"""
    CPU = "cpu"
    MEMORY = "memory"
    TIME = "time"
    CALLS = "calls"


@dataclass
class FunctionProfile:
    """Profile of a function"""
    function_name: str
    total_time: float = 0.0
    total_calls: int = 0
    min_time: float = float('inf')
    max_time: float = float('-inf')
    avg_time: float = 0.0
    memory_used: int = 0  # bytes
    memory_peak: int = 0  # bytes


@dataclass
class BottleneckReport:
    """Bottleneck analysis report"""
    function_name: str
    profile_type: ProfileType
    current_value: float
    baseline_value: float
    overhead_percent: float
    severity: str  # low, medium, high, critical
    recommendations: List[str] = field(default_factory=list)


class FunctionProfiler:
    """
    Decorator-based function profiler.

    Profiles individual function calls and collects statistics.
    """

    def __init__(self, logger_instance=None):
        """
        Initialize function profiler.

        Args:
            logger_instance: Logger instance
        """
        self.logger = logger_instance or logging.getLogger(__name__)
        self.profiles: Dict[str, FunctionProfile] = {}
        self.call_history: Dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))

    def profile_function(self, func: Callable) -> Callable:
        """
        Decorator to profile a function.

        Args:
            func: Function to profile

        Returns:
            Wrapped function
        """
        @wraps(func)
        def wrapper(*args, **kwargs):
            func_name = func.__name__

            start_time = time.time()
            start_memory = tracemalloc.get_traced_memory()[0]

            try:
                result = func(*args, **kwargs)
                return result

            finally:
                end_time = time.time()
                end_memory, peak_memory = tracemalloc.get_traced_memory()

                elapsed = end_time - start_time
                memory_used = end_memory - start_memory

                # Update profile
                if func_name not in self.profiles:
                    self.profiles[func_name] = FunctionProfile(
                        function_name=func_name
                    )

                profile = self.profiles[func_name]
                profile.total_time += elapsed
                profile.total_calls += 1
                profile.min_time = min(profile.min_time, elapsed)
                profile.max_time = max(profile.max_time, elapsed)
                profile.avg_time = profile.total_time / profile.total_calls
                profile.memory_used += memory_used
                profile.memory_peak = max(profile.memory_peak, peak_memory)

                # Record call
                self.call_history[func_name].append({
                    'time': elapsed,
                    'memory': memory_used,
                    'timestamp': end_time
                })

        return wrapper

    def get_profile(self, function_name: str) -> Optional[FunctionProfile]:
        """Get profile for a function"""
        return self.profiles.get(function_name)

    def get_slowest_functions(self, limit: int = 10) -> List[Tuple[str, float]]:
        """Get slowest functions by total time"""
        return sorted(
            [(name, profile.total_time) for name, profile in self.profiles.items()],
            key=lambda x: x[1],
            reverse=True
        )[:limit]

    def get_most_called_functions(self, limit: int = 10) -> List[Tuple[str, int]]:
        """Get most called functions"""
        return sorted(
            [(name, profile.total_calls) for name, profile in self.profiles.items()],
            key=lambda x: x[1],
            reverse=True
        )[:limit]

    def get_memory_hogs(self, limit: int = 10) -> List[Tuple[str, int]]:
        """Get functions using most memory"""
        return sorted(
            [(name, profile.memory_used) for name, profile in self.profiles.items()],
            key=lambda x: x[1],
            reverse=True
        )[:limit]


class CPUProfiler:
    """
    CPU profiler using cProfile.

    Profiles CPU usage across entire application.
    """

    def __init__(self, logger_instance=None):
        """
        Initialize CPU profiler.

        Args:
            logger_instance: Logger instance
        """
        self.logger = logger_instance or logging.getLogger(__name__)
        self.profiler = None
        self.stats = None
        self.is_running = False

    def start(self) -> None:
        """Start CPU profiling"""
        if self.is_running:
            self.logger.warning("Profiler already running")
            return

        self.profiler = cProfile.Profile()
        self.profiler.enable()
        self.is_running = True

        self.logger.info("CPU profiler started")

    def stop(self) -> None:
        """Stop CPU profiling"""
        if not self.is_running:
            self.logger.warning("Profiler not running")
            return

        self.profiler.disable()
        self.is_running = False

        self.logger.info("CPU profiler stopped")

    def get_stats(self, sort_by: str = 'cumulative') -> Dict[str, Any]:
        """Get CPU profiling statistics"""
        try:
            if self.profiler is None:
                return {}

            s = pstats.Stats(self.profiler)
            s.sort_stats(sort_by)

            # Capture stats output
            output = io.StringIO()
            s.print_stats(output)

            return {
                'sort_by': sort_by,
                'output': output.getvalue()
            }

        except Exception as e:
            self.logger.error(f"Error getting stats: {e}")
            return {}

    def export_stats(self, filename: str) -> bool:
        """Export profiling stats to file"""
        try:
            if self.profiler is None:
                return False

            self.profiler.dump_stats(filename)
            self.logger.info(f"Exported CPU profile to {filename}")
            return True

        except Exception as e:
            self.logger.error(f"Error exporting stats: {e}")
            return False


class MemoryProfiler:
    """
    Memory profiler using tracemalloc.

    Tracks memory allocation and identifies leaks.
    """

    def __init__(self, logger_instance=None):
        """
        Initialize memory profiler.

        Args:
            logger_instance: Logger instance
        """
        self.logger = logger_instance or logging.getLogger(__name__)
        self.snapshots: List[tracemalloc.Snapshot] = []
        self.is_tracing = False

    def start(self) -> None:
        """Start memory tracing"""
        if self.is_tracing:
            self.logger.warning("Memory tracing already running")
            return

        tracemalloc.start()
        self.is_tracing = True

        self.logger.info("Memory profiler started")

    def stop(self) -> None:
        """Stop memory tracing"""
        if not self.is_tracing:
            self.logger.warning("Memory tracing not running")
            return

        tracemalloc.stop()
        self.is_tracing = False

        self.logger.info("Memory profiler stopped")

    def take_snapshot(self) -> Optional[tracemalloc.Snapshot]:
        """Take memory snapshot"""
        try:
            if not self.is_tracing:
                return None

            snapshot = tracemalloc.take_snapshot()
            self.snapshots.append(snapshot)

            return snapshot

        except Exception as e:
            self.logger.error(f"Error taking snapshot: {e}")
            return None

    def get_top_allocations(self, snapshot_index: int = -1,
                           limit: int = 10) -> List[Tuple[str, int]]:
        """Get top memory allocations"""
        try:
            if not self.snapshots or snapshot_index >= len(self.snapshots):
                return []

            snapshot = self.snapshots[snapshot_index]
            top_stats = snapshot.statistics('lineno')

            result = []
            for stat in top_stats[:limit]:
                result.append((stat.traceback.format()[0], stat.size))

            return result

        except Exception as e:
            self.logger.error(f"Error getting allocations: {e}")
            return []

    def get_memory_diff(self, snapshot1_index: int = -2,
                       snapshot2_index: int = -1) -> List[Tuple[str, int, int]]:
        """Get memory allocation differences between snapshots"""
        try:
            if len(self.snapshots) < 2:
                return []

            snapshot1 = self.snapshots[snapshot1_index]
            snapshot2 = self.snapshots[snapshot2_index]

            top_stats = snapshot2.compare_to(snapshot1, 'lineno')

            result = []
            for stat in top_stats[:10]:
                result.append((
                    stat.traceback.format()[0],
                    stat.size,
                    stat.count
                ))

            return result

        except Exception as e:
            self.logger.error(f"Error getting memory diff: {e}")
            return []


class PerformanceAnalyzer:
    """
    High-level performance analysis.

    Identifies bottlenecks and provides recommendations.
    """

    def __init__(self, logger_instance=None):
        """
        Initialize performance analyzer.

        Args:
            logger_instance: Logger instance
        """
        self.logger = logger_instance or logging.getLogger(__name__)
        self.function_profiler = FunctionProfiler(logger_instance)
        self.cpu_profiler = CPUProfiler(logger_instance)
        self.memory_profiler = MemoryProfiler(logger_instance)

        self.baselines: Dict[str, float] = {}
        self.bottlenecks: List[BottleneckReport] = []

    def identify_bottlenecks(self, threshold_percent: float = 10.0) -> List[BottleneckReport]:
        """
        Identify performance bottlenecks.

        Args:
            threshold_percent: Threshold for identifying bottlenecks

        Returns:
            List of bottleneck reports
        """
        try:
            bottlenecks = []

            # Check function execution times
            for func_name, profile in self.function_profiler.profiles.items():
                if func_name in self.baselines:
                    baseline = self.baselines[func_name]
                    overhead = ((profile.avg_time - baseline) / baseline) * 100

                    if overhead > threshold_percent:
                        severity = self._get_severity(overhead)

                        report = BottleneckReport(
                            function_name=func_name,
                            profile_type=ProfileType.TIME,
                            current_value=profile.avg_time,
                            baseline_value=baseline,
                            overhead_percent=overhead,
                            severity=severity,
                            recommendations=self._get_recommendations(func_name, profile)
                        )

                        bottlenecks.append(report)

            self.bottlenecks = bottlenecks
            return bottlenecks

        except Exception as e:
            self.logger.error(f"Error identifying bottlenecks: {e}")
            return []

    def _get_severity(self, overhead_percent: float) -> str:
        """Determine severity level"""
        if overhead_percent < 10:
            return "low"
        elif overhead_percent < 25:
            return "medium"
        elif overhead_percent < 50:
            return "high"
        else:
            return "critical"

    def _get_recommendations(self, func_name: str,
                            profile: FunctionProfile) -> List[str]:
        """Get optimization recommendations"""
        recommendations = []

        if profile.total_calls > 1000:
            recommendations.append(
                f"Function {func_name} called {profile.total_calls} times. "
                "Consider caching or memoization."
            )

        if profile.max_time > profile.avg_time * 5:
            recommendations.append(
                f"Function {func_name} has high variance in execution time. "
                "Check for data-dependent performance."
            )

        if profile.memory_used > 100 * 1024 * 1024:  # 100 MB
            recommendations.append(
                f"Function {func_name} uses significant memory ({profile.memory_used / 1024 / 1024:.1f} MB). "
                "Consider optimizing memory usage."
            )

        return recommendations

    def set_baseline(self, function_name: str, value: float) -> None:
        """Set baseline value for function"""
        self.baselines[function_name] = value

    def get_optimization_report(self) -> Dict[str, Any]:
        """Generate optimization report"""
        try:
            return {
                'timestamp': time.time(),
                'bottlenecks': [
                    {
                        'function': b.function_name,
                        'overhead_percent': b.overhead_percent,
                        'severity': b.severity,
                        'recommendations': b.recommendations
                    }
                    for b in self.bottlenecks
                ],
                'slowest_functions': dict(self.function_profiler.get_slowest_functions()),
                'most_called_functions': dict(self.function_profiler.get_most_called_functions()),
                'memory_hogs': dict(self.function_profiler.get_memory_hogs())
            }

        except Exception as e:
            self.logger.error(f"Error generating report: {e}")
            return {}
