#!/usr/bin/env python3
"""
Performance Test Report Generator

Runs performance tests and generates a detailed report.
"""
import subprocess
import json
import time
from datetime import datetime
import os


def run_command(cmd, timeout=60):
    """Run a command and return output"""
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "Command timed out"
    except Exception as e:
        return -1, "", str(e)


def extract_performance_metrics(output):
    """Extract performance metrics from test output"""
    metrics = {}

    # Look for timing information in output
    lines = output.split('\n')
    for line in lines:
        if 'PASSED' in line or 'passed' in line:
            # Extract test name and timing if available
            if '::' in line:
                test_name = line.split('::')[-1].split()[0]
                metrics[test_name] = 'PASSED'

    return metrics


def generate_report():
    """Generate performance test report"""
    print("=" * 80)
    print("FSRsync Performance Test Report")
    print("=" * 80)
    print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    report = {
        'timestamp': datetime.now().isoformat(),
        'tests': {},
        'summary': {}
    }

    # Test 1: File Tracking Performance
    print("Running: File Tracking Performance Test...")
    start = time.time()
    code, out, err = run_command(
        "python3 -c \"from test.test_docker_sync import *; import pytest; pytest.main(['-v', 'test/test_docker_sync.py::TestPerformance::test_file_tracking_performance'])\"",
        timeout=30
    )
    elapsed = time.time() - start

    report['tests']['file_tracking'] = {
        'status': 'PASSED' if code == 0 else 'FAILED',
        'duration': elapsed,
        'expected': '< 2 seconds for 1000 files',
        'description': 'Add 1000 files to tracking system'
    }

    if code == 0:
        print(f"  ✓ PASSED ({elapsed:.2f}s)")
    else:
        print(f"  ✗ FAILED ({elapsed:.2f}s)")
        if err:
            print(f"  Error: {err[:200]}")

    # Test 2: File Retrieval Performance
    print("Running: File Retrieval Performance Test...")
    start = time.time()
    code, out, err = run_command(
        "python3 -c \"from test.test_docker_sync import *; import pytest; pytest.main(['-v', 'test/test_docker_sync.py::TestPerformance::test_file_retrieval_performance'])\"",
        timeout=30
    )
    elapsed = time.time() - start

    report['tests']['file_retrieval'] = {
        'status': 'PASSED' if code == 0 else 'FAILED',
        'duration': elapsed,
        'expected': '< 1 second for 5000 files with filtering',
        'description': 'Retrieve filtered files from 5000 total'
    }

    if code == 0:
        print(f"  ✓ PASSED ({elapsed:.2f}s)")
    else:
        print(f"  ✗ FAILED ({elapsed:.2f}s)")

    # Test 3: Concurrent Operations Performance
    print("Running: Concurrent Operations Performance Test...")
    start = time.time()
    code, out, err = run_command(
        "python3 -c \"from test.test_docker_sync import *; import pytest; pytest.main(['-v', 'test/test_docker_sync.py::TestPerformance::test_concurrent_operations_performance'])\"",
        timeout=30
    )
    elapsed = time.time() - start

    report['tests']['concurrent_ops'] = {
        'status': 'PASSED' if code == 0 else 'FAILED',
        'duration': elapsed,
        'expected': '< 5 seconds for 10 threads × 100 files',
        'description': 'Concurrent file additions from multiple threads'
    }

    if code == 0:
        print(f"  ✓ PASSED ({elapsed:.2f}s)")
    else:
        print(f"  ✗ FAILED ({elapsed:.2f}s)")

    # Calculate summary
    passed = sum(1 for t in report['tests'].values() if t['status'] == 'PASSED')
    total = len(report['tests'])

    report['summary'] = {
        'total_tests': total,
        'passed': passed,
        'failed': total - passed,
        'pass_rate': f"{(passed/total*100):.1f}%"
    }

    # Print summary
    print()
    print("=" * 80)
    print("Summary")
    print("=" * 80)
    print(f"Total Tests: {total}")
    print(f"Passed: {passed}")
    print(f"Failed: {total - passed}")
    print(f"Pass Rate: {report['summary']['pass_rate']}")
    print()

    # Save detailed report
    report_file = 'PERFORMANCE_REPORT.json'
    with open(report_file, 'w') as f:
        json.dump(report, f, indent=2)

    # Generate markdown report
    generate_markdown_report(report)

    print(f"Detailed report saved to: {report_file}")
    print(f"Markdown report saved to: PERFORMANCE_REPORT.md")

    return passed == total


def generate_markdown_report(report):
    """Generate markdown performance report"""
    with open('PERFORMANCE_REPORT.md', 'w') as f:
        f.write("# FSRsync Performance Test Report\n\n")
        f.write(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

        f.write("## Summary\n\n")
        f.write(f"- **Total Tests:** {report['summary']['total_tests']}\n")
        f.write(f"- **Passed:** {report['summary']['passed']}\n")
        f.write(f"- **Failed:** {report['summary']['failed']}\n")
        f.write(f"- **Pass Rate:** {report['summary']['pass_rate']}\n\n")

        f.write("## Test Results\n\n")
        f.write("| Test | Status | Duration | Expected | Description |\n")
        f.write("|------|--------|----------|----------|-------------|\n")

        for test_name, test_data in report['tests'].items():
            status_icon = "✅" if test_data['status'] == 'PASSED' else "❌"
            f.write(f"| {test_name} | {status_icon} {test_data['status']} | "
                   f"{test_data['duration']:.2f}s | {test_data['expected']} | "
                   f"{test_data['description']} |\n")

        f.write("\n## Performance Benchmarks\n\n")
        f.write("### File Tracking\n")
        f.write("- **Metric:** Add 1000 files to tracking system\n")
        if 'file_tracking' in report['tests']:
            ft = report['tests']['file_tracking']
            f.write(f"- **Result:** {ft['duration']:.2f} seconds\n")
            f.write(f"- **Status:** {ft['status']}\n")
            f.write(f"- **Expected:** {ft['expected']}\n\n")

        f.write("### File Retrieval\n")
        f.write("- **Metric:** Retrieve with path filtering from 5000 files\n")
        if 'file_retrieval' in report['tests']:
            fr = report['tests']['file_retrieval']
            f.write(f"- **Result:** {fr['duration']:.2f} seconds\n")
            f.write(f"- **Status:** {fr['status']}\n")
            f.write(f"- **Expected:** {fr['expected']}\n\n")

        f.write("### Concurrent Operations\n")
        f.write("- **Metric:** 10 threads × 100 files each (1000 total)\n")
        if 'concurrent_ops' in report['tests']:
            co = report['tests']['concurrent_ops']
            f.write(f"- **Result:** {co['duration']:.2f} seconds\n")
            f.write(f"- **Status:** {co['status']}\n")
            f.write(f"- **Expected:** {co['expected']}\n\n")

        f.write("## Recommendations\n\n")
        f.write("Based on the performance test results:\n\n")

        all_passed = all(t['status'] == 'PASSED' for t in report['tests'].values())

        if all_passed:
            f.write("✅ **All performance benchmarks passed!**\n\n")
            f.write("The system meets all performance requirements:\n")
            f.write("- File tracking is fast and efficient\n")
            f.write("- File retrieval with filtering is performant\n")
            f.write("- Concurrent operations handle well under load\n")
        else:
            f.write("⚠️ **Some performance issues detected**\n\n")
            f.write("Consider the following optimizations:\n")
            f.write("- Use dict-based lookups instead of set iterations\n")
            f.write("- Implement caching for frequently accessed paths\n")
            f.write("- Reduce lock contention with finer-grained locking\n")


if __name__ == '__main__':
    try:
        success = generate_report()
        exit(0 if success else 1)
    except Exception as e:
        print(f"Error generating report: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
