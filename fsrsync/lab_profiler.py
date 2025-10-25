"""
Lab Profiler for FSRsync

Integrated profiling runner for Docker lab environment:
- Orchestrates performance tests in lab
- Collects comprehensive metrics
- Generates performance reports
- Creates performance baselines
- Compares performance across runs

Usage:
    python lab_profiler.py --scenario basic --duration 60 --profile
    python lab_profiler.py --scenario all --output report.json
    python lab_profiler.py --baseline --scenario large_file
"""

import os
import sys
import json
import time
import asyncio
import logging
import argparse
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from fsrsync.test_scenarios import TestScenarioRunner
from fsrsync.utils.sync_instrumentation import SyncInstrumentation
from fsrsync.utils.metrics_collector import MetricsCollector
from fsrsync.utils.performance_benchmarker import PerformanceBenchmarker
from fsrsync.utils.io_analyzer import IOAnalyzer
from fsrsync.utils.profiler import FunctionProfiler, PerformanceAnalyzer
from fsrsync.utils.regression_tester import RegressionTester
from fsrsync.utils.report_generator import ReportGenerator


@dataclass
class ProfilingConfig:
    """Lab profiling configuration"""
    scenario: str
    duration: int = 60
    iterations: int = 1
    profile_enabled: bool = True
    io_tracking: bool = True
    streaming_enabled: bool = False
    baseline_mode: bool = False
    output_file: Optional[str] = None
    log_level: str = "INFO"


class LabProfiler:
    """
    Lab profiler for integrated performance testing.

    Orchestrates test scenarios with full performance instrumentation
    and generates comprehensive reports.
    """

    def __init__(self, config: ProfilingConfig):
        """
        Initialize lab profiler.

        Args:
            config: Profiling configuration
        """
        self.config = config
        self.setup_logging()

        # Initialize performance modules
        self.metrics_collector = MetricsCollector(logger_instance=self.logger)
        self.benchmarker = PerformanceBenchmarker(logger_instance=self.logger)
        self.io_analyzer = IOAnalyzer(logger_instance=self.logger)
        self.profiler = FunctionProfiler(logger_instance=self.logger)
        self.perf_analyzer = PerformanceAnalyzer(logger_instance=self.logger)
        self.regression_tester = RegressionTester(logger_instance=self.logger)
        self.report_generator = ReportGenerator(logger_instance=self.logger)

        # Initialize instrumentation
        SyncInstrumentation.initialize(
            metrics_collector=self.metrics_collector,
            benchmarker=self.benchmarker,
            io_analyzer=self.io_analyzer,
            logger_instance=self.logger
        )

        # Test scenario runner
        self.test_runner = TestScenarioRunner(logger_instance=self.logger)

        # Results storage
        self.results: List[Dict[str, Any]] = []
        self.start_time = None
        self.end_time = None

        self.logger.info("LabProfiler initialized")

    def setup_logging(self) -> None:
        """Setup logging configuration"""
        self.logger = logging.getLogger("lab_profiler")
        self.logger.setLevel(getattr(logging, self.config.log_level))

        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)

    async def run_scenario(self, scenario_name: str) -> Dict[str, Any]:
        """
        Run single test scenario with profiling.

        Args:
            scenario_name: Name of scenario to run

        Returns:
            Profiling results
        """
        self.logger.info(f"Running scenario: {scenario_name}")

        scenario_start = time.time()

        try:
            # Run test scenario
            result = await self.test_runner.run_all_scenarios()

            scenario_end = time.time()
            scenario_duration = scenario_end - scenario_start

            # Collect profiling data
            profiling_data = {
                'scenario': scenario_name,
                'timestamp': scenario_start,
                'duration': scenario_duration,
                'test_results': [r.to_dict() for r in result] if result else [],
                'metrics_summary': self.metrics_collector.get_metrics_summary(),
                'benchmark_report': self.benchmarker.get_performance_report(),
                'io_summary': self.io_analyzer.get_io_summary(),
                'bottlenecks': self.perf_analyzer.identify_bottlenecks(),
                'profiler_slowest': dict(self.profiler.get_slowest_functions(limit=10)),
                'profiler_memory': dict(self.profiler.get_memory_hogs(limit=10))
            }

            return profiling_data

        except Exception as e:
            self.logger.error(f"Error running scenario: {e}")
            return {
                'scenario': scenario_name,
                'error': str(e),
                'timestamp': scenario_start
            }

    async def run_all_scenarios(self) -> List[Dict[str, Any]]:
        """
        Run all test scenarios.

        Returns:
            List of profiling results
        """
        self.start_time = time.time()
        results = []

        scenarios = [
            'basic_sync',
            'conflict_resolution',
            'large_file_transfer',
            'network_failure_recovery',
            'multi_peer_sync',
            'bandwidth_throttling',
            'concurrent_operations',
            'data_integrity'
        ]

        for scenario in scenarios:
            self.logger.info(f"Running scenario {scenarios.index(scenario) + 1}/{len(scenarios)}")
            result = await self.run_scenario(scenario)
            results.append(result)

        self.end_time = time.time()
        return results

    async def run_single_scenario(self) -> Dict[str, Any]:
        """
        Run single configured scenario.

        Returns:
            Profiling results
        """
        self.start_time = time.time()
        result = await self.run_scenario(self.config.scenario)
        self.end_time = time.time()
        return result

    def generate_report(self, results: Dict[str, Any] | List[Dict[str, Any]]) -> str:
        """
        Generate comprehensive profiling report.

        Args:
            results: Profiling results

        Returns:
            Report as formatted string
        """
        report = ReportGenerator(logger_instance=self.logger)

        # Create report
        report_id = report.create_report(
            report_type="performance",
            title="Lab Performance Profiling Report",
            description=f"Performance profiling for FSRsync lab test run on {datetime.now().isoformat()}",
            format_type="markdown"
        )

        if not report_id:
            return "Failed to create report"

        # Add executive summary
        if isinstance(results, list):
            total_scenarios = len(results)
            avg_duration = sum(r.get('duration', 0) for r in results) / total_scenarios if results else 0
            summary_data = {
                'key_metrics': {
                    'Total Scenarios': total_scenarios,
                    'Total Duration': f"{sum(r.get('duration', 0) for r in results):.2f}s",
                    'Average Duration': f"{avg_duration:.2f}s"
                },
                'findings': [
                    f"Completed {total_scenarios} test scenarios",
                    f"Total profiling duration: {self.end_time - self.start_time:.2f}s"
                ]
            }
        else:
            summary_data = {
                'key_metrics': {
                    'Scenario': results.get('scenario', 'unknown'),
                    'Duration': f"{results.get('duration', 0):.2f}s"
                }
            }

        report.generate_executive_summary(report_id, summary_data)

        # Add metrics section
        metrics_data = self.metrics_collector.get_metrics_summary()
        report.generate_metrics_section(report_id, metrics_data)

        # Export report
        report_content = report.export_report(report_id)

        return report_content if report_content else "Failed to export report"

    def save_results(self, results: Dict[str, Any] | List[Dict[str, Any]]) -> None:
        """
        Save profiling results to file.

        Args:
            results: Profiling results
        """
        if not self.config.output_file:
            return

        try:
            output_path = Path(self.config.output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            output_data = {
                'timestamp': time.time(),
                'config': asdict(self.config),
                'results': results,
                'duration': (self.end_time - self.start_time) if self.end_time else None
            }

            with open(output_path, 'w') as f:
                json.dump(output_data, f, indent=2, default=str)

            self.logger.info(f"Results saved to {output_path}")

        except Exception as e:
            self.logger.error(f"Error saving results: {e}")

    def print_summary(self, results: Dict[str, Any] | List[Dict[str, Any]]) -> None:
        """
        Print summary of profiling results.

        Args:
            results: Profiling results
        """
        print("\n" + "=" * 80)
        print("LAB PROFILING SUMMARY")
        print("=" * 80)

        if isinstance(results, list):
            print(f"\nScenarios Completed: {len(results)}")
            print(f"Total Duration: {self.end_time - self.start_time:.2f}s")

            for result in results:
                scenario = result.get('scenario', 'unknown')
                duration = result.get('duration', 0)
                error = result.get('error')

                status = "✓ PASS" if not error else "✗ FAIL"
                print(f"  {status} - {scenario}: {duration:.2f}s")

                if error:
                    print(f"    Error: {error}")
        else:
            print(f"\nScenario: {results.get('scenario', 'unknown')}")
            print(f"Duration: {results.get('duration', 0):.2f}s")
            error = results.get('error')
            if error:
                print(f"Status: ✗ FAILED")
                print(f"Error: {error}")
            else:
                print(f"Status: ✓ PASSED")

        print("\n" + "=" * 80)


async def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="FSRsync Lab Profiler - Performance profiling for lab tests"
    )
    parser.add_argument(
        '--scenario',
        choices=['all', 'basic_sync', 'conflict_resolution', 'large_file_transfer',
                'network_failure_recovery', 'multi_peer_sync', 'bandwidth_throttling',
                'concurrent_operations', 'data_integrity'],
        default='all',
        help='Test scenario to run'
    )
    parser.add_argument(
        '--duration',
        type=int,
        default=60,
        help='Test duration in seconds'
    )
    parser.add_argument(
        '--profile',
        action='store_true',
        default=True,
        help='Enable performance profiling'
    )
    parser.add_argument(
        '--baseline',
        action='store_true',
        help='Create performance baseline'
    )
    parser.add_argument(
        '--output',
        help='Output file for results (JSON)'
    )
    parser.add_argument(
        '--log-level',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        default='INFO',
        help='Logging level'
    )

    args = parser.parse_args()

    config = ProfilingConfig(
        scenario=args.scenario,
        duration=args.duration,
        profile_enabled=args.profile,
        baseline_mode=args.baseline,
        output_file=args.output,
        log_level=args.log_level
    )

    profiler = LabProfiler(config)

    # Run profiling
    if config.scenario == 'all':
        results = await profiler.run_all_scenarios()
    else:
        results = await profiler.run_single_scenario()

    # Generate report
    report = profiler.generate_report(results)
    print(report)

    # Save results
    profiler.save_results(results)

    # Print summary
    profiler.print_summary(results)


if __name__ == '__main__':
    asyncio.run(main())
