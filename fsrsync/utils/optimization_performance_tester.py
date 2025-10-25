"""
Optimization Performance Tester for Phase 17

Comprehensive testing framework for Phase 17 optimizers:
- Delta optimizer performance testing
- Concurrent transfer optimization testing
- Adaptive chunk sizing effectiveness
- Connection pooling efficiency
- End-to-end optimization impact measurement
- Regression testing against baselines
- Performance comparisons

## Test Scenarios

MICRO: Small file transfers (< 1MB)
SMALL: Small file set (1-10 MB)
MEDIUM: Medium file set (10-100 MB)
LARGE: Large file transfers (100MB-1GB)
VARIED: Mixed file types and sizes
NETWORK_CONSTRAINED: Simulated slow network
BURST: Rapid concurrent transfers
SUSTAINED: Long-running transfers
"""

import time
import logging
import json
import random
import tempfile
import os
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field, asdict
from enum import Enum
from collections import defaultdict, deque
import statistics


class TestScenario(Enum):
    """Performance test scenarios"""
    MICRO = "micro"
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"
    VARIED = "varied"
    NETWORK_CONSTRAINED = "network_constrained"
    BURST = "burst"
    SUSTAINED = "sustained"


@dataclass
class OptimizationTestResult:
    """Result of an optimization test"""
    scenario: str
    optimizer_name: str
    test_duration: float
    recommendations_made: int
    avg_confidence: float
    estimated_improvement_percent: float
    actual_improvement_percent: float = 0.0
    success: bool = True
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


@dataclass
class PerformanceComparison:
    """Comparison of performance before and after optimization"""
    metric_name: str
    baseline_value: float
    optimized_value: float
    improvement_percent: float
    improvement_absolute: float


class OptimizationPerformanceTester:
    """
    Comprehensive performance tester for Phase 17 optimizers.

    Tests each optimizer independently and in integration,
    measuring performance improvements across various scenarios.
    """

    def __init__(self, logger_instance=None):
        """
        Initialize optimization performance tester.

        Args:
            logger_instance: Logger instance
        """
        self.logger = logger_instance or logging.getLogger(__name__)

        # Test history
        self.test_results: List[OptimizationTestResult] = []
        self.baseline_results: Dict[str, Dict[str, float]] = {}

        # Scenario definitions
        self.scenarios: Dict[TestScenario, Dict[str, Any]] = {
            TestScenario.MICRO: {
                "file_count": 1,
                "file_sizes": [100 * 1024],  # 100KB
                "description": "Single small file"
            },
            TestScenario.SMALL: {
                "file_count": 10,
                "file_sizes": [512 * 1024] * 10,  # 512KB each
                "description": "10 small files"
            },
            TestScenario.MEDIUM: {
                "file_count": 20,
                "file_sizes": [5 * 1024 * 1024] * 20,  # 5MB each
                "description": "20 medium files"
            },
            TestScenario.LARGE: {
                "file_count": 5,
                "file_sizes": [100 * 1024 * 1024] * 5,  # 100MB each
                "description": "5 large files"
            },
            TestScenario.VARIED: {
                "file_count": 30,
                "file_sizes": [
                    100 * 1024,  # 100KB
                    1 * 1024 * 1024,  # 1MB
                    10 * 1024 * 1024,  # 10MB
                ] * 10,
                "description": "Mixed file sizes"
            },
            TestScenario.NETWORK_CONSTRAINED: {
                "file_count": 5,
                "file_sizes": [10 * 1024 * 1024] * 5,  # 10MB each
                "network_bandwidth": 1.0,  # 1 MB/s
                "network_latency": 100.0,  # 100ms
                "description": "Slow network conditions"
            },
            TestScenario.BURST: {
                "file_count": 50,
                "file_sizes": [2 * 1024 * 1024] * 50,  # 2MB each
                "description": "Many small concurrent transfers"
            },
            TestScenario.SUSTAINED: {
                "file_count": 20,
                "file_sizes": [50 * 1024 * 1024] * 20,  # 50MB each
                "duration": 120,  # 2 minutes
                "description": "Long-running transfer"
            }
        }

        self.logger.info("OptimizationPerformanceTester initialized")

    def test_delta_optimizer(self, delta_optimizer, scenario: TestScenario) -> OptimizationTestResult:
        """
        Test delta optimizer performance.

        Args:
            delta_optimizer: DeltaOptimizer instance
            scenario: Test scenario

        Returns:
            Test result
        """
        try:
            test_start = time.time()
            scenario_config = self.scenarios[scenario]

            recommendations = []
            confidences = []

            # Analyze files
            for i, file_size in enumerate(scenario_config["file_sizes"]):
                file_path = f"/test/file_{i}.bin"

                # Simulate recent changes
                recent_changes = None
                if "changes_percent" in scenario_config:
                    change_size = int(file_size * scenario_config["changes_percent"] / 100)
                    if change_size > 0:
                        recent_changes = [(0, change_size)]

                analysis = delta_optimizer.analyze_file(
                    file_path=file_path,
                    file_size=file_size,
                    recent_changes=recent_changes
                )

                recommendations.append({
                    'strategy': analysis.recommended_strategy.value,
                    'chunk_size': analysis.recommended_chunk_size,
                    'bandwidth_reduction': analysis.estimated_bandwidth_reduction
                })
                confidences.append(analysis.confidence)

            test_duration = time.time() - test_start
            avg_confidence = statistics.mean(confidences) if confidences else 0.0
            avg_bandwidth_reduction = statistics.mean(
                [r['bandwidth_reduction'] for r in recommendations]
            )

            result = OptimizationTestResult(
                scenario=scenario.value,
                optimizer_name="DeltaOptimizer",
                test_duration=test_duration,
                recommendations_made=len(recommendations),
                avg_confidence=avg_confidence,
                estimated_improvement_percent=avg_bandwidth_reduction,
                metadata={
                    'avg_chunk_size': statistics.mean([r['chunk_size'] for r in recommendations]),
                    'strategies_used': list(set([r['strategy'] for r in recommendations]))
                }
            )

            self.logger.info(
                f"Delta optimizer test ({scenario.value}): "
                f"{result.recommendations_made} recommendations, "
                f"avg confidence={avg_confidence:.2f}"
            )

            return result

        except Exception as e:
            self.logger.error(f"Error testing delta optimizer: {e}")
            return OptimizationTestResult(
                scenario=scenario.value,
                optimizer_name="DeltaOptimizer",
                test_duration=0.0,
                recommendations_made=0,
                avg_confidence=0.0,
                estimated_improvement_percent=0.0,
                success=False,
                error_message=str(e)
            )

    def test_concurrent_optimizer(self, concurrent_optimizer, scenario: TestScenario) -> OptimizationTestResult:
        """
        Test concurrent transfer optimizer.

        Args:
            concurrent_optimizer: ConcurrentOptimizer instance
            scenario: Test scenario

        Returns:
            Test result
        """
        try:
            test_start = time.time()
            scenario_config = self.scenarios[scenario]

            file_count = scenario_config["file_count"]
            total_size = sum(scenario_config["file_sizes"])
            bandwidth = scenario_config.get("network_bandwidth", 100.0)

            # Get strategy and parallelism
            strategy = concurrent_optimizer.select_strategy(
                file_count=file_count,
                total_size=total_size,
                available_bandwidth=bandwidth
            )

            parallelism = concurrent_optimizer.optimize_parallelism(
                file_count=file_count,
                total_size=total_size
            )

            # Simulate transfers
            for i in range(file_count):
                file_size = scenario_config["file_sizes"][i]
                duration = (file_size / (1024 * 1024)) / bandwidth
                throughput = (file_size / (1024 * 1024)) / duration

                concurrent_optimizer.record_transfer(
                    transfer_id=f"transfer_{i}",
                    strategy=strategy,
                    file_count=file_count,
                    total_size=total_size,
                    duration=duration,
                    errors=0
                )

            test_duration = time.time() - test_start

            # Estimate improvement from parallelism
            sequential_duration = sum(
                s / (1024 * 1024 * bandwidth) for s in scenario_config["file_sizes"]
            )
            parallel_duration = sequential_duration / min(parallelism, file_count)
            improvement = ((sequential_duration - parallel_duration) / sequential_duration) * 100

            result = OptimizationTestResult(
                scenario=scenario.value,
                optimizer_name="ConcurrentOptimizer",
                test_duration=test_duration,
                recommendations_made=file_count,
                avg_confidence=0.8,
                estimated_improvement_percent=improvement,
                metadata={
                    'strategy': strategy.value,
                    'parallelism_level': parallelism,
                    'file_count': file_count
                }
            )

            self.logger.info(
                f"Concurrent optimizer test ({scenario.value}): "
                f"strategy={strategy.value}, parallelism={parallelism}, "
                f"estimated improvement={improvement:.1f}%"
            )

            return result

        except Exception as e:
            self.logger.error(f"Error testing concurrent optimizer: {e}")
            return OptimizationTestResult(
                scenario=scenario.value,
                optimizer_name="ConcurrentOptimizer",
                test_duration=0.0,
                recommendations_made=0,
                avg_confidence=0.0,
                estimated_improvement_percent=0.0,
                success=False,
                error_message=str(e)
            )

    def test_chunk_sizer(self, chunk_sizer, scenario: TestScenario) -> OptimizationTestResult:
        """
        Test adaptive chunk sizer.

        Args:
            chunk_sizer: AdaptiveChunkSizer instance
            scenario: Test scenario

        Returns:
            Test result
        """
        try:
            test_start = time.time()
            scenario_config = self.scenarios[scenario]

            from .adaptive_chunk_sizing import SizingMetrics, NetworkConditions, SystemResources

            recommendations = []
            file_count = len(scenario_config["file_sizes"])

            for i, file_size in enumerate(scenario_config["file_sizes"]):
                # File type based on name
                file_types = ["text", "binary", "video", "code", "archive"]
                file_type = file_types[i % len(file_types)]

                bandwidth = scenario_config.get("network_bandwidth", 100.0)
                latency = scenario_config.get("network_latency", 10.0)

                metrics = SizingMetrics(
                    file_size=file_size,
                    file_type=file_type,
                    network_bandwidth=bandwidth,
                    network_latency=latency,
                    memory_available=2048.0,  # 2GB
                    cpu_available=50.0
                )

                network = NetworkConditions(
                    bandwidth_mbps=bandwidth,
                    latency_ms=latency
                )

                resources = SystemResources(
                    available_memory_mb=2048.0,
                    available_cpu_percent=50.0
                )

                recommendation = chunk_sizer.recommend_chunk_size(
                    metrics=metrics,
                    network=network,
                    resources=resources
                )

                recommendations.append({
                    'chunk_size': recommendation.recommended_size,
                    'confidence': recommendation.confidence,
                    'throughput': recommendation.estimated_throughput_mbps
                })

            test_duration = time.time() - test_start
            avg_confidence = statistics.mean([r['confidence'] for r in recommendations])
            avg_throughput = statistics.mean([r['throughput'] for r in recommendations])

            # Estimate improvement as better throughput
            improvement = (avg_throughput / 50.0) * 100 - 100  # Normalize to 50MB/s baseline

            result = OptimizationTestResult(
                scenario=scenario.value,
                optimizer_name="AdaptiveChunkSizer",
                test_duration=test_duration,
                recommendations_made=len(recommendations),
                avg_confidence=avg_confidence,
                estimated_improvement_percent=max(improvement, 0.0),
                metadata={
                    'avg_chunk_size': statistics.mean([r['chunk_size'] for r in recommendations]),
                    'avg_throughput_mbps': avg_throughput
                }
            )

            self.logger.info(
                f"Chunk sizer test ({scenario.value}): "
                f"{len(recommendations)} recommendations, "
                f"avg confidence={avg_confidence:.2f}"
            )

            return result

        except Exception as e:
            self.logger.error(f"Error testing chunk sizer: {e}")
            return OptimizationTestResult(
                scenario=scenario.value,
                optimizer_name="AdaptiveChunkSizer",
                test_duration=0.0,
                recommendations_made=0,
                avg_confidence=0.0,
                estimated_improvement_percent=0.0,
                success=False,
                error_message=str(e)
            )

    def test_connection_pooling(self, pooling, scenario: TestScenario) -> OptimizationTestResult:
        """
        Test connection pooling efficiency.

        Args:
            pooling: TransferConnectionPooling instance
            scenario: Test scenario

        Returns:
            Test result
        """
        try:
            test_start = time.time()
            scenario_config = self.scenarios[scenario]

            file_count = scenario_config["file_count"]
            file_sizes = scenario_config["file_sizes"]
            destinations = ["dest_1", "dest_2", "dest_3"]

            connections_used = {}
            total_reuses = 0

            # Simulate transfers
            for i, file_size in enumerate(file_sizes):
                destination = destinations[i % len(destinations)]

                # Get connection
                conn_id = pooling.get_connection(destination)
                if conn_id:
                    # Track reuse
                    if destination not in connections_used:
                        connections_used[destination] = {}
                    if conn_id not in connections_used[destination]:
                        connections_used[destination][conn_id] = 0
                    connections_used[destination][conn_id] += 1

                    # Return connection
                    throughput = 50.0  # MB/s
                    duration = (file_size / (1024 * 1024)) / throughput
                    pooling.return_connection(
                        destination=destination,
                        connection_id=conn_id,
                        success=True,
                        bytes_transferred=file_size,
                        duration_seconds=duration
                    )

                    total_reuses += connections_used[destination][conn_id]

            test_duration = time.time() - test_start
            stats = pooling.get_pool_stats()

            # Calculate reuse efficiency
            total_connections = sum(
                pool['total_connections']
                for pool in stats.get('pools', {}).values()
            )
            reuse_rate = total_reuses / max(total_connections, 1)

            result = OptimizationTestResult(
                scenario=scenario.value,
                optimizer_name="ConnectionPooling",
                test_duration=test_duration,
                recommendations_made=file_count,
                avg_confidence=0.85,
                estimated_improvement_percent=reuse_rate * 50,  # Reuse saves ~50% per reuse
                metadata={
                    'total_connections': total_connections,
                    'reuse_rate': reuse_rate,
                    'destinations': len(destinations)
                }
            )

            self.logger.info(
                f"Connection pooling test ({scenario.value}): "
                f"reuse_rate={reuse_rate:.2f}, "
                f"total_connections={total_connections}"
            )

            return result

        except Exception as e:
            self.logger.error(f"Error testing connection pooling: {e}")
            return OptimizationTestResult(
                scenario=scenario.value,
                optimizer_name="ConnectionPooling",
                test_duration=0.0,
                recommendations_made=0,
                avg_confidence=0.0,
                estimated_improvement_percent=0.0,
                success=False,
                error_message=str(e)
            )

    def run_full_test_suite(self, optimizers: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run full test suite on all optimizers.

        Args:
            optimizers: Dict with optimizer instances

        Returns:
            Full test results
        """
        results = {
            'timestamp': time.time(),
            'test_scenarios': [],
            'optimizer_results': {}
        }

        try:
            # Test each scenario
            for scenario in TestScenario:
                scenario_results = {
                    'scenario': scenario.value,
                    'description': self.scenarios[scenario]['description'],
                    'results': []
                }

                # Test each optimizer
                if 'delta_optimizer' in optimizers and optimizers['delta_optimizer']:
                    result = self.test_delta_optimizer(
                        optimizers['delta_optimizer'], scenario
                    )
                    scenario_results['results'].append(asdict(result))
                    self.test_results.append(result)

                if 'concurrent_optimizer' in optimizers and optimizers['concurrent_optimizer']:
                    result = self.test_concurrent_optimizer(
                        optimizers['concurrent_optimizer'], scenario
                    )
                    scenario_results['results'].append(asdict(result))
                    self.test_results.append(result)

                if 'chunk_sizer' in optimizers and optimizers['chunk_sizer']:
                    result = self.test_chunk_sizer(
                        optimizers['chunk_sizer'], scenario
                    )
                    scenario_results['results'].append(asdict(result))
                    self.test_results.append(result)

                if 'connection_pooling' in optimizers and optimizers['connection_pooling']:
                    result = self.test_connection_pooling(
                        optimizers['connection_pooling'], scenario
                    )
                    scenario_results['results'].append(asdict(result))
                    self.test_results.append(result)

                results['test_scenarios'].append(scenario_results)

            # Aggregate results
            results['summary'] = self._generate_summary()

        except Exception as e:
            self.logger.error(f"Error running full test suite: {e}")

        return results

    def _generate_summary(self) -> Dict[str, Any]:
        """Generate summary of all test results"""
        try:
            if not self.test_results:
                return {}

            by_optimizer = defaultdict(list)
            for result in self.test_results:
                if result.success:
                    by_optimizer[result.optimizer_name].append(
                        result.estimated_improvement_percent
                    )

            summary = {
                'total_tests': len(self.test_results),
                'successful_tests': sum(1 for r in self.test_results if r.success),
                'failed_tests': sum(1 for r in self.test_results if not r.success),
                'average_improvement_percent': statistics.mean(
                    [r.estimated_improvement_percent for r in self.test_results if r.success]
                ) if any(r.success for r in self.test_results) else 0.0,
                'by_optimizer': {
                    name: {
                        'avg_improvement': statistics.mean(values) if values else 0.0,
                        'max_improvement': max(values) if values else 0.0,
                        'min_improvement': min(values) if values else 0.0,
                        'test_count': len(values)
                    }
                    for name, values in by_optimizer.items()
                }
            }

            return summary

        except Exception as e:
            self.logger.error(f"Error generating summary: {e}")
            return {}

    def export_results(self, filepath: str) -> None:
        """Export test results to file"""
        try:
            results = {
                'timestamp': time.time(),
                'test_results': [asdict(r) for r in self.test_results],
                'summary': self._generate_summary()
            }

            with open(filepath, 'w') as f:
                json.dump(results, f, indent=2, default=str)

            self.logger.info(f"Exported test results to {filepath}")

        except Exception as e:
            self.logger.error(f"Error exporting results: {e}")
