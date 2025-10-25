"""
Performance Optimization Advisor for FSRsync

Provides intelligent optimization recommendations with:
- Performance bottleneck analysis
- Resource utilization optimization
- Caching strategy recommendations
- Parallelization opportunities
- Memory optimization suggestions
- I/O optimization recommendations
- Comprehensive optimization reports

## Optimization Categories

CACHING: Caching and memoization strategies
PARALLELIZATION: Concurrency and parallel processing
MEMORY: Memory usage optimization
IO: Disk I/O optimization
CPU: CPU utilization optimization
NETWORK: Network optimization
GENERAL: General optimization tips
"""

import time
import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict


class OptimizationCategory(Enum):
    """Category of optimization"""
    CACHING = "caching"
    PARALLELIZATION = "parallelization"
    MEMORY = "memory"
    IO = "io"
    CPU = "cpu"
    NETWORK = "network"
    GENERAL = "general"


class PriorityLevel(Enum):
    """Priority level for optimization"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class OptimizationRecommendation:
    """Performance optimization recommendation"""
    recommendation_id: str
    category: OptimizationCategory
    title: str
    description: str
    current_value: float
    potential_improvement: float  # percentage improvement (0-100)
    priority: PriorityLevel
    effort: str  # low, medium, high
    implementation_steps: List[str] = field(default_factory=list)
    estimated_impact: str = ""
    related_metrics: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)


@dataclass
class OptimizationProfile:
    """Performance profile for optimization analysis"""
    profile_id: str
    function_name: str
    call_count: int = 0
    total_time: float = 0.0
    avg_time: float = 0.0
    memory_usage: int = 0  # bytes
    cache_hits: int = 0
    cache_misses: int = 0
    io_operations: int = 0
    network_calls: int = 0


class OptimizationAdvisor:
    """
    Performance optimization advisor.

    Analyzes performance metrics and provides actionable
    optimization recommendations.
    """

    def __init__(self, logger_instance=None):
        """
        Initialize optimization advisor.

        Args:
            logger_instance: Logger instance
        """
        self.logger = logger_instance or logging.getLogger(__name__)

        # Profiles (function_name -> OptimizationProfile)
        self.profiles: Dict[str, OptimizationProfile] = {}

        # Recommendations (recommendation_id -> OptimizationRecommendation)
        self.recommendations: Dict[str, OptimizationRecommendation] = {}

        # History (category -> list of recommendations)
        self.recommendation_history: Dict[str, List[OptimizationRecommendation]] = defaultdict(list)

        # Performance thresholds
        self.thresholds: Dict[str, float] = {
            'slow_function_ms': 100.0,  # Function takes >100ms
            'memory_intensive_mb': 50.0,  # Function uses >50MB
            'high_call_count': 1000,  # Function called >1000 times
            'low_cache_hit_ratio': 0.5,  # Cache hit ratio <50%
            'high_io_count': 100  # >100 I/O operations
        }

        # Optimization knowledge base
        self.optimization_rules = self._init_optimization_rules()

        self.logger.info("OptimizationAdvisor initialized")

    def _init_optimization_rules(self) -> Dict[str, Any]:
        """Initialize optimization rules and patterns"""
        return {
            'caching_rules': [
                {
                    'pattern': 'high_call_count_low_variance',
                    'description': 'Function called frequently with similar inputs',
                    'recommendation': 'Implement memoization or LRU cache',
                    'improvement': 30
                },
                {
                    'pattern': 'repeated_calculations',
                    'description': 'Same calculations performed multiple times',
                    'recommendation': 'Cache results of expensive computations',
                    'improvement': 40
                }
            ],
            'parallelization_rules': [
                {
                    'pattern': 'independent_operations',
                    'description': 'Multiple independent operations executed sequentially',
                    'recommendation': 'Use thread pool or async processing',
                    'improvement': 50
                },
                {
                    'pattern': 'map_reduce_pattern',
                    'description': 'Data transformation followed by aggregation',
                    'recommendation': 'Implement parallel map-reduce pattern',
                    'improvement': 60
                }
            ],
            'memory_rules': [
                {
                    'pattern': 'large_intermediate_objects',
                    'description': 'Large temporary objects created during processing',
                    'recommendation': 'Stream data or use generators for large datasets',
                    'improvement': 35
                },
                {
                    'pattern': 'memory_leak_pattern',
                    'description': 'Memory usage grows without bound',
                    'recommendation': 'Check for circular references and implement cleanup',
                    'improvement': 25
                }
            ],
            'io_rules': [
                {
                    'pattern': 'sequential_io_operations',
                    'description': 'Multiple I/O operations executed sequentially',
                    'recommendation': 'Batch I/O operations or use async I/O',
                    'improvement': 45
                },
                {
                    'pattern': 'small_io_operations',
                    'description': 'Many small I/O operations instead of bulk operations',
                    'recommendation': 'Buffer and batch I/O operations',
                    'improvement': 50
                }
            ]
        }

    def analyze_function(self, function_name: str, call_count: int,
                        total_time: float, memory_usage: int = 0,
                        io_ops: int = 0, network_calls: int = 0) -> Optional[str]:
        """
        Analyze function performance and create profile.

        Args:
            function_name: Name of function
            call_count: Number of calls
            total_time: Total execution time in seconds
            memory_usage: Memory usage in bytes
            io_ops: Number of I/O operations
            network_calls: Number of network calls

        Returns:
            Profile ID if successful
        """
        try:
            import uuid

            profile_id = str(uuid.uuid4())
            avg_time = (total_time / call_count * 1000) if call_count > 0 else 0  # in ms

            profile = OptimizationProfile(
                profile_id=profile_id,
                function_name=function_name,
                call_count=call_count,
                total_time=total_time,
                avg_time=avg_time,
                memory_usage=memory_usage,
                io_operations=io_ops,
                network_calls=network_calls
            )

            self.profiles[function_name] = profile

            # Generate recommendations based on profile
            self._generate_recommendations(profile)

            self.logger.info(f"Analyzed function {function_name}: {call_count} calls, {avg_time:.2f}ms avg")
            return profile_id

        except Exception as e:
            self.logger.error(f"Error analyzing function: {e}")
            return None

    def _generate_recommendations(self, profile: OptimizationProfile) -> None:
        """Generate optimization recommendations for profile"""
        try:
            # Check for caching opportunities
            if profile.call_count > self.thresholds['high_call_count']:
                self._recommend_caching(profile)

            # Check for parallelization opportunities
            if profile.total_time > self.thresholds['slow_function_ms'] / 1000:
                self._recommend_parallelization(profile)

            # Check for memory optimization
            if profile.memory_usage > self.thresholds['memory_intensive_mb'] * 1024 * 1024:
                self._recommend_memory_optimization(profile)

            # Check for I/O optimization
            if profile.io_operations > self.thresholds['high_io_count']:
                self._recommend_io_optimization(profile)

        except Exception as e:
            self.logger.error(f"Error generating recommendations: {e}")

    def _recommend_caching(self, profile: OptimizationProfile) -> None:
        """Recommend caching strategies"""
        try:
            import uuid

            rec_id = str(uuid.uuid4())

            recommendation = OptimizationRecommendation(
                recommendation_id=rec_id,
                category=OptimizationCategory.CACHING,
                title=f"Implement caching for {profile.function_name}",
                description=(
                    f"Function {profile.function_name} is called {profile.call_count} times. "
                    f"Consider implementing memoization or LRU cache to avoid redundant computations."
                ),
                current_value=profile.avg_time,
                potential_improvement=30,
                priority=self._get_priority(profile.call_count, 10000),
                effort="low",
                implementation_steps=[
                    "1. Identify function inputs that determine output",
                    "2. Use functools.lru_cache() decorator for pure functions",
                    "3. For complex cases, implement custom caching logic",
                    "4. Monitor cache hit/miss ratio"
                ],
                estimated_impact=f"Reduce avg time from {profile.avg_time:.2f}ms by ~30%",
                related_metrics=[f"{profile.function_name}_call_count", f"{profile.function_name}_avg_time"]
            )

            self.recommendations[rec_id] = recommendation
            self.recommendation_history[OptimizationCategory.CACHING.value].append(recommendation)

        except Exception as e:
            self.logger.error(f"Error recommending caching: {e}")

    def _recommend_parallelization(self, profile: OptimizationProfile) -> None:
        """Recommend parallelization strategies"""
        try:
            import uuid

            rec_id = str(uuid.uuid4())

            recommendation = OptimizationRecommendation(
                recommendation_id=rec_id,
                category=OptimizationCategory.PARALLELIZATION,
                title=f"Parallelize {profile.function_name}",
                description=(
                    f"Function {profile.function_name} takes {profile.total_time:.2f}s total time. "
                    f"Consider parallelizing independent operations."
                ),
                current_value=profile.total_time,
                potential_improvement=50,
                priority=self._get_priority(profile.total_time, 5.0),
                effort="medium",
                implementation_steps=[
                    "1. Identify independent operations in the function",
                    "2. Use ThreadPoolExecutor for I/O-bound tasks",
                    "3. Use ProcessPoolExecutor for CPU-bound tasks",
                    "4. Monitor overhead from thread context switching"
                ],
                estimated_impact=f"Reduce total time from {profile.total_time:.2f}s by ~50%",
                related_metrics=[f"{profile.function_name}_total_time", f"{profile.function_name}_call_count"]
            )

            self.recommendations[rec_id] = recommendation
            self.recommendation_history[OptimizationCategory.PARALLELIZATION.value].append(recommendation)

        except Exception as e:
            self.logger.error(f"Error recommending parallelization: {e}")

    def _recommend_memory_optimization(self, profile: OptimizationProfile) -> None:
        """Recommend memory optimization strategies"""
        try:
            import uuid

            rec_id = str(uuid.uuid4())
            memory_mb = profile.memory_usage / 1024 / 1024

            recommendation = OptimizationRecommendation(
                recommendation_id=rec_id,
                category=OptimizationCategory.MEMORY,
                title=f"Optimize memory usage for {profile.function_name}",
                description=(
                    f"Function {profile.function_name} uses {memory_mb:.1f}MB memory. "
                    f"Consider using generators, streaming, or reducing temporary objects."
                ),
                current_value=profile.memory_usage,
                potential_improvement=35,
                priority=self._get_priority(profile.memory_usage, 100 * 1024 * 1024),
                effort="medium",
                implementation_steps=[
                    "1. Profile memory usage with tracemalloc",
                    "2. Replace lists with generators for large datasets",
                    "3. Use __slots__ for classes with many instances",
                    "4. Implement cleanup for temporary objects"
                ],
                estimated_impact=f"Reduce memory from {memory_mb:.1f}MB by ~35%",
                related_metrics=[f"{profile.function_name}_memory_usage"]
            )

            self.recommendations[rec_id] = recommendation
            self.recommendation_history[OptimizationCategory.MEMORY.value].append(recommendation)

        except Exception as e:
            self.logger.error(f"Error recommending memory optimization: {e}")

    def _recommend_io_optimization(self, profile: OptimizationProfile) -> None:
        """Recommend I/O optimization strategies"""
        try:
            import uuid

            rec_id = str(uuid.uuid4())

            recommendation = OptimizationRecommendation(
                recommendation_id=rec_id,
                category=OptimizationCategory.IO,
                title=f"Optimize I/O operations in {profile.function_name}",
                description=(
                    f"Function {profile.function_name} performs {profile.io_operations} I/O operations. "
                    f"Consider batching or using async I/O."
                ),
                current_value=profile.io_operations,
                potential_improvement=45,
                priority=self._get_priority(profile.io_operations, 500),
                effort="medium",
                implementation_steps=[
                    "1. Analyze I/O operation patterns",
                    "2. Batch small I/O operations into larger ones",
                    "3. Use async I/O libraries for non-blocking operations",
                    "4. Implement read/write buffering"
                ],
                estimated_impact=f"Reduce I/O operations from {profile.io_operations} by ~45%",
                related_metrics=[f"{profile.function_name}_io_operations"]
            )

            self.recommendations[rec_id] = recommendation
            self.recommendation_history[OptimizationCategory.IO.value].append(recommendation)

        except Exception as e:
            self.logger.error(f"Error recommending I/O optimization: {e}")

    def _get_priority(self, current_value: float, critical_threshold: float) -> PriorityLevel:
        """Determine priority based on current value and threshold"""
        if current_value >= critical_threshold:
            return PriorityLevel.CRITICAL
        elif current_value >= critical_threshold * 0.7:
            return PriorityLevel.HIGH
        elif current_value >= critical_threshold * 0.4:
            return PriorityLevel.MEDIUM
        else:
            return PriorityLevel.LOW

    def get_recommendations(self, category: Optional[str] = None,
                           priority: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get optimization recommendations.

        Args:
            category: Optional category filter
            priority: Optional priority filter

        Returns:
            List of recommendations
        """
        try:
            recs = list(self.recommendations.values())

            if category:
                try:
                    cat = OptimizationCategory[category.upper()]
                    recs = [r for r in recs if r.category == cat]
                except (KeyError, ValueError):
                    pass

            if priority:
                try:
                    prio = PriorityLevel[priority.upper()]
                    recs = [r for r in recs if r.priority == prio]
                except (KeyError, ValueError):
                    pass

            return [
                {
                    'recommendation_id': r.recommendation_id,
                    'category': r.category.value,
                    'title': r.title,
                    'description': r.description,
                    'priority': r.priority.value,
                    'effort': r.effort,
                    'potential_improvement': r.potential_improvement,
                    'steps': r.implementation_steps,
                    'impact': r.estimated_impact
                }
                for r in sorted(recs, key=lambda x: (
                    ['critical', 'high', 'medium', 'low'].index(x.priority.value),
                    -x.potential_improvement
                ))
            ]

        except Exception as e:
            self.logger.error(f"Error getting recommendations: {e}")
            return []

    def get_optimization_report(self) -> Dict[str, Any]:
        """Get comprehensive optimization report"""
        try:
            total_recs = len(self.recommendations)
            by_category = defaultdict(int)
            by_priority = defaultdict(int)
            total_improvement = 0.0

            for rec in self.recommendations.values():
                by_category[rec.category.value] += 1
                by_priority[rec.priority.value] += 1
                total_improvement += rec.potential_improvement

            avg_improvement = (total_improvement / total_recs) if total_recs > 0 else 0

            return {
                'timestamp': time.time(),
                'total_recommendations': total_recs,
                'by_category': dict(by_category),
                'by_priority': dict(by_priority),
                'total_potential_improvement': total_improvement,
                'average_improvement': avg_improvement,
                'top_recommendations': self.get_recommendations(priority='critical')[:5],
                'functions_analyzed': len(self.profiles)
            }

        except Exception as e:
            self.logger.error(f"Error generating report: {e}")
            return {}

    def get_function_recommendations(self, function_name: str) -> List[Dict[str, Any]]:
        """Get recommendations for specific function"""
        try:
            if function_name not in self.profiles:
                return []

            profile = self.profiles[function_name]
            all_recs = self.get_recommendations()

            return [
                r for r in all_recs
                if function_name in r.get('impact', '')
            ]

        except Exception as e:
            self.logger.error(f"Error getting function recommendations: {e}")
            return []

    def estimate_total_improvement(self) -> float:
        """Estimate total potential improvement from all recommendations"""
        try:
            if not self.recommendations:
                return 0.0

            # Estimate cumulative improvement (with diminishing returns)
            total = 0.0
            for rec in sorted(self.recommendations.values(),
                             key=lambda x: -x.potential_improvement):
                # Each optimization reduces remaining room for improvement
                improvement = rec.potential_improvement * (1 - total / 100)
                total += improvement

            return min(total, 95.0)  # Cap at 95% improvement

        except Exception as e:
            self.logger.error(f"Error estimating improvement: {e}")
            return 0.0

    def get_advisor_summary(self) -> Dict[str, Any]:
        """Get advisor system summary"""
        try:
            return {
                'timestamp': time.time(),
                'total_recommendations': len(self.recommendations),
                'functions_analyzed': len(self.profiles),
                'estimated_total_improvement': self.estimate_total_improvement(),
                'recommendations_by_priority': {
                    'critical': len([r for r in self.recommendations.values()
                                   if r.priority == PriorityLevel.CRITICAL]),
                    'high': len([r for r in self.recommendations.values()
                               if r.priority == PriorityLevel.HIGH]),
                    'medium': len([r for r in self.recommendations.values()
                                 if r.priority == PriorityLevel.MEDIUM]),
                    'low': len([r for r in self.recommendations.values()
                              if r.priority == PriorityLevel.LOW])
                },
                'recommendations_by_category': {
                    cat.value: len([r for r in self.recommendations.values()
                                   if r.category == cat])
                    for cat in OptimizationCategory
                }
            }

        except Exception as e:
            self.logger.error(f"Error getting summary: {e}")
            return {}
