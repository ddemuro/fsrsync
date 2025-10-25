"""
Performance Test Runner for FSRsync

Provides automated performance testing with:
- Predefined test scenarios
- Custom test execution
- Performance comparison
- Load testing capabilities
- Stress testing scenarios
- Test result analysis
- Performance trending

## Test Types

UNIT: Unit performance tests
LOAD: Load testing scenarios
STRESS: Stress testing scenarios
ENDURANCE: Long-running endurance tests
COMPARISON: Comparative performance tests
"""

import time
import logging
import threading
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict, deque
import statistics


class TestType(Enum):
    """Type of performance test"""
    UNIT = "unit"
    LOAD = "load"
    STRESS = "stress"
    ENDURANCE = "endurance"
    COMPARISON = "comparison"


class TestStatus(Enum):
    """Status of test execution"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class TestMetric:
    """Test result metric"""
    metric_name: str
    value: float
    unit: str
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TestResult:
    """Performance test result"""
    test_id: str
    test_name: str
    test_type: TestType
    status: TestStatus
    start_time: float
    end_time: Optional[float] = None
    duration: float = 0.0
    iterations: int = 0
    metrics: List[TestMetric] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    success_rate: float = 100.0
    baseline_comparison: Optional[float] = None  # % change from baseline


@dataclass
class TestScenario:
    """Performance test scenario definition"""
    scenario_id: str
    scenario_name: str
    test_type: TestType
    description: str
    test_function: Optional[Callable] = None
    iterations: int = 100
    duration_seconds: int = 60
    concurrency: int = 1
    parameters: Dict[str, Any] = field(default_factory=dict)
    expected_metrics: Dict[str, float] = field(default_factory=dict)


class TestRunner:
    """
    Performance test runner.

    Executes performance tests and collects results
    for analysis and comparison.
    """

    def __init__(self, logger_instance=None):
        """
        Initialize test runner.

        Args:
            logger_instance: Logger instance
        """
        self.logger = logger_instance or logging.getLogger(__name__)

        # Test scenarios (scenario_id -> TestScenario)
        self.scenarios: Dict[str, TestScenario] = {}

        # Test results (test_id -> TestResult)
        self.results: Dict[str, TestResult] = {}

        # Result history (scenario_id -> deque of TestResult)
        self.history: Dict[str, deque] = defaultdict(lambda: deque(maxlen=100))

        # Baselines for comparison (scenario_id -> baseline_metrics)
        self.baselines: Dict[str, Dict[str, float]] = {}

        # Running tests (test_id -> TestResult)
        self.running_tests: Dict[str, TestResult] = {}

        self.logger.info("TestRunner initialized")

    def register_scenario(self, scenario_name: str, test_type: str,
                         description: str, test_function: Optional[Callable] = None,
                         iterations: int = 100, concurrency: int = 1,
                         parameters: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """
        Register a test scenario.

        Args:
            scenario_name: Name of scenario
            test_type: Type of test
            description: Test description
            test_function: Optional test function
            iterations: Number of iterations
            concurrency: Concurrency level
            parameters: Optional parameters

        Returns:
            Scenario ID if successful
        """
        try:
            import uuid

            scenario_id = str(uuid.uuid4())

            try:
                tt = TestType[test_type.upper()]
            except (KeyError, ValueError):
                self.logger.warning(f"Invalid test type: {test_type}")
                return None

            scenario = TestScenario(
                scenario_id=scenario_id,
                scenario_name=scenario_name,
                test_type=tt,
                description=description,
                test_function=test_function,
                iterations=iterations,
                concurrency=concurrency,
                parameters=parameters or {}
            )

            self.scenarios[scenario_id] = scenario

            self.logger.info(f"Registered scenario: {scenario_name}")
            return scenario_id

        except Exception as e:
            self.logger.error(f"Error registering scenario: {e}")
            return None

    def run_scenario(self, scenario_id: str) -> Optional[str]:
        """
        Run a test scenario.

        Args:
            scenario_id: ID of scenario to run

        Returns:
            Test ID if successful
        """
        try:
            if scenario_id not in self.scenarios:
                self.logger.warning(f"Scenario not found: {scenario_id}")
                return None

            scenario = self.scenarios[scenario_id]
            import uuid

            test_id = str(uuid.uuid4())
            start_time = time.time()

            result = TestResult(
                test_id=test_id,
                test_name=scenario.scenario_name,
                test_type=scenario.test_type,
                status=TestStatus.RUNNING,
                start_time=start_time,
                iterations=scenario.iterations
            )

            self.results[test_id] = result
            self.running_tests[test_id] = result

            # Run test in background
            thread = threading.Thread(
                target=self._execute_test,
                args=(test_id, scenario),
                daemon=True
            )
            thread.start()

            self.logger.info(f"Started test {test_id} for scenario {scenario.scenario_name}")
            return test_id

        except Exception as e:
            self.logger.error(f"Error running scenario: {e}")
            return None

    def _execute_test(self, test_id: str, scenario: TestScenario) -> None:
        """Execute test scenario"""
        try:
            result = self.results[test_id]

            if not scenario.test_function:
                result.status = TestStatus.FAILED
                result.errors.append("No test function provided")
                return

            success_count = 0
            times = []

            for i in range(scenario.iterations):
                try:
                    start = time.time()
                    output = scenario.test_function(**scenario.parameters)
                    elapsed = time.time() - start

                    times.append(elapsed)
                    success_count += 1

                    # Record metrics if test function returns them
                    if isinstance(output, dict):
                        for metric_name, value in output.items():
                            result.metrics.append(TestMetric(
                                metric_name=metric_name,
                                value=value,
                                unit="ms"
                            ))

                except Exception as e:
                    result.errors.append(f"Iteration {i}: {str(e)}")
                    self.logger.debug(f"Test iteration error: {e}")

            # Calculate metrics
            result.status = TestStatus.COMPLETED
            result.end_time = time.time()
            result.duration = result.end_time - result.start_time
            result.success_rate = (success_count / scenario.iterations * 100) if scenario.iterations > 0 else 0

            # Add timing metrics
            if times:
                result.metrics.append(TestMetric(
                    metric_name="avg_time",
                    value=statistics.mean(times),
                    unit="s"
                ))
                result.metrics.append(TestMetric(
                    metric_name="min_time",
                    value=min(times),
                    unit="s"
                ))
                result.metrics.append(TestMetric(
                    metric_name="max_time",
                    value=max(times),
                    unit="s"
                ))
                if len(times) > 1:
                    result.metrics.append(TestMetric(
                        metric_name="std_dev",
                        value=statistics.stdev(times),
                        unit="s"
                    ))

            # Compare to baseline
            if scenario.scenario_id in self.baselines:
                baseline = self.baselines[scenario.scenario_id]
                avg_metric = next((m for m in result.metrics if m.metric_name == "avg_time"), None)
                if avg_metric and "avg_time" in baseline:
                    percent_change = ((avg_metric.value - baseline["avg_time"]) / baseline["avg_time"]) * 100
                    result.baseline_comparison = percent_change

            # Store in history
            self.history[scenario.scenario_id].append(result)

            self.logger.info(
                f"Test {result.test_id} completed: "
                f"{success_count}/{scenario.iterations} successful, "
                f"{result.duration:.2f}s duration"
            )

        except Exception as e:
            self.logger.error(f"Error executing test: {e}")
            result.status = TestStatus.FAILED
            result.errors.append(str(e))

        finally:
            if test_id in self.running_tests:
                del self.running_tests[test_id]

    def set_baseline(self, scenario_id: str) -> bool:
        """
        Set current results as baseline for scenario.

        Args:
            scenario_id: Scenario ID

        Returns:
            True if successful
        """
        try:
            # Get latest result for scenario
            history = self.history.get(scenario_id, deque())

            if not history:
                self.logger.warning(f"No results for scenario: {scenario_id}")
                return False

            latest_result = list(history)[-1]

            # Extract metrics as baseline
            baseline = {}
            for metric in latest_result.metrics:
                baseline[metric.metric_name] = metric.value

            self.baselines[scenario_id] = baseline

            self.logger.info(f"Set baseline for scenario {scenario_id}")
            return True

        except Exception as e:
            self.logger.error(f"Error setting baseline: {e}")
            return False

    def get_test_result(self, test_id: str) -> Optional[Dict[str, Any]]:
        """Get test result"""
        try:
            result = self.results.get(test_id)

            if not result:
                return None

            return {
                'test_id': result.test_id,
                'name': result.test_name,
                'type': result.test_type.value,
                'status': result.status.value,
                'duration': result.duration,
                'iterations': result.iterations,
                'success_rate': result.success_rate,
                'metrics': [
                    {
                        'name': m.metric_name,
                        'value': m.value,
                        'unit': m.unit
                    }
                    for m in result.metrics
                ],
                'baseline_comparison': result.baseline_comparison,
                'errors': result.errors
            }

        except Exception as e:
            self.logger.error(f"Error getting result: {e}")
            return None

    def get_scenario_history(self, scenario_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Get test history for scenario"""
        try:
            history = self.history.get(scenario_id, deque())

            results = []
            for result in list(history)[-limit:]:
                results.append({
                    'test_id': result.test_id,
                    'status': result.status.value,
                    'duration': result.duration,
                    'success_rate': result.success_rate,
                    'timestamp': result.start_time,
                    'baseline_comparison': result.baseline_comparison
                })

            return results

        except Exception as e:
            self.logger.error(f"Error getting history: {e}")
            return []

    def compare_results(self, test_id_1: str, test_id_2: str) -> Optional[Dict[str, Any]]:
        """Compare two test results"""
        try:
            result1 = self.results.get(test_id_1)
            result2 = self.results.get(test_id_2)

            if not result1 or not result2:
                return None

            comparison = {
                'test_1': result1.test_name,
                'test_2': result2.test_name,
                'metric_comparison': []
            }

            # Compare metrics
            metrics1 = {m.metric_name: m.value for m in result1.metrics}
            metrics2 = {m.metric_name: m.value for m in result2.metrics}

            for metric_name in set(list(metrics1.keys()) + list(metrics2.keys())):
                if metric_name in metrics1 and metric_name in metrics2:
                    val1 = metrics1[metric_name]
                    val2 = metrics2[metric_name]
                    percent_change = ((val2 - val1) / val1 * 100) if val1 != 0 else 0

                    comparison['metric_comparison'].append({
                        'metric': metric_name,
                        'test_1_value': val1,
                        'test_2_value': val2,
                        'percent_change': percent_change
                    })

            return comparison

        except Exception as e:
            self.logger.error(f"Error comparing results: {e}")
            return None

    def get_test_summary(self) -> Dict[str, Any]:
        """Get test execution summary"""
        try:
            completed = sum(1 for r in self.results.values() if r.status == TestStatus.COMPLETED)
            failed = sum(1 for r in self.results.values() if r.status == TestStatus.FAILED)
            running = len(self.running_tests)

            avg_success_rate = (
                statistics.mean([r.success_rate for r in self.results.values() if r.status == TestStatus.COMPLETED])
                if completed > 0 else 0
            )

            return {
                'timestamp': time.time(),
                'total_tests': len(self.results),
                'completed': completed,
                'failed': failed,
                'running': running,
                'average_success_rate': avg_success_rate,
                'scenarios_registered': len(self.scenarios),
                'scenarios_with_baselines': len(self.baselines)
            }

        except Exception as e:
            self.logger.error(f"Error getting summary: {e}")
            return {}

    def get_runner_summary(self) -> Dict[str, Any]:
        """Get test runner system summary"""
        try:
            return {
                'timestamp': time.time(),
                'total_scenarios': len(self.scenarios),
                'total_results': len(self.results),
                'total_baselines': len(self.baselines),
                'running_tests': len(self.running_tests),
                'test_types': {
                    tt.value: len([s for s in self.scenarios.values() if s.test_type == tt])
                    for tt in TestType
                },
                'result_statuses': {
                    ts.value: len([r for r in self.results.values() if r.status == ts])
                    for ts in TestStatus
                }
            }

        except Exception as e:
            self.logger.error(f"Error getting summary: {e}")
            return {}
