#!/usr/bin/env python3
"""
Validate that all tests can be imported and basic functionality works
This script tests the test infrastructure itself
"""
import sys
import os
import json
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

def test_imports():
    """Test that all modules can be imported"""
    print("Testing imports...")
    errors = []

    try:
        from fsrsync.utils.filesystem import FilesystemMonitor, File
        print("  ✓ FilesystemMonitor imported")
    except Exception as e:
        errors.append(f"Failed to import FilesystemMonitor: {e}")

    try:
        from fsrsync.utils.logs import Logger
        print("  ✓ Logger imported")
    except Exception as e:
        errors.append(f"Failed to import Logger: {e}")

    try:
        from fsrsync.web_app import WebControl
        print("  ✓ WebControl imported")
    except Exception as e:
        errors.append(f"Failed to import WebControl: {e}")

    return errors


def test_basic_functionality():
    """Test basic functionality"""
    print("\nTesting basic functionality...")
    errors = []

    try:
        from fsrsync.utils.filesystem import FilesystemMonitor, File
        from fsrsync.utils.logs import Logger

        # Create instances
        monitor = FilesystemMonitor(time_between_events=1)
        logger = Logger()

        # Test file creation
        file = File("/test/path.txt", logger)
        assert file.path == "/test/path.txt"
        assert file.extension == "txt"
        print("  ✓ File class works")

        # Test adding to immediate sync
        monitor.add_immediate_sync_file(file)
        files = monitor.get_immediate_sync_files()
        assert len(files) == 1
        print("  ✓ Immediate sync works")

        # Test path filtering
        filtered = monitor.get_immediate_sync_files("/test")
        assert len(filtered) == 1
        print("  ✓ Path filtering works")

        # Test deletion
        monitor.delete_immediate_sync_file("/test/path.txt")
        files = monitor.get_immediate_sync_files()
        assert len(files) == 0
        print("  ✓ File deletion works")

        # Test regular sync
        file2 = File("/test/regular.txt", logger)
        monitor.add_regular_sync_file(file2)
        regular_files = monitor.get_regular_sync_files()
        assert len(regular_files) == 1
        print("  ✓ Regular sync works")

        # Test locked files
        file3 = File("/test/locked.txt", logger)
        monitor.add_to_locked_files(file3)
        locked = monitor.get_locked_files()
        assert len(locked) == 1
        print("  ✓ Locked files tracking works")

        # Test aggregated events
        aggregated = monitor.get_aggregated_events()
        assert "immediate" in aggregated
        assert "regular" in aggregated
        assert "locked" in aggregated
        print("  ✓ Aggregated events works")

    except AssertionError as e:
        errors.append(f"Assertion failed: {e}")
    except Exception as e:
        errors.append(f"Functionality test failed: {e}")

    return errors


def test_thread_safety():
    """Test basic thread safety"""
    print("\nTesting thread safety...")
    errors = []

    try:
        import threading
        from fsrsync.utils.filesystem import FilesystemMonitor, File
        from fsrsync.utils.logs import Logger

        monitor = FilesystemMonitor()
        logger = Logger()
        test_errors = []

        def worker(start, count):
            try:
                for i in range(start, start + count):
                    file = File(f"/test/thread/file{i}.txt", logger)
                    monitor.add_immediate_sync_file(file)
            except Exception as e:
                test_errors.append(e)

        # Create threads
        threads = []
        for i in range(5):
            t = threading.Thread(target=worker, args=(i * 20, 20))
            threads.append(t)

        # Start threads
        for t in threads:
            t.start()

        # Wait for completion
        for t in threads:
            t.join()

        # Check for errors
        if test_errors:
            errors.extend([str(e) for e in test_errors])
        else:
            files = monitor.get_immediate_sync_files()
            if len(files) == 100:
                print(f"  ✓ Thread safety works (100 files added)")
            else:
                errors.append(f"Expected 100 files, got {len(files)}")

    except Exception as e:
        errors.append(f"Thread safety test failed: {e}")

    return errors


def test_performance():
    """Test basic performance"""
    print("\nTesting performance...")
    errors = []

    try:
        import time
        from fsrsync.utils.filesystem import FilesystemMonitor, File
        from fsrsync.utils.logs import Logger

        monitor = FilesystemMonitor(max_tracked_files=10000)
        logger = Logger()

        # Test 1: Add 1000 files
        start = time.time()
        for i in range(1000):
            file = File(f"/test/perf/file{i}.txt", logger)
            monitor.add_immediate_sync_file(file)
        elapsed = time.time() - start

        if elapsed < 2.0:
            print(f"  ✓ File tracking: {elapsed:.3f}s (< 2s for 1000 files)")
        else:
            errors.append(f"File tracking too slow: {elapsed:.3f}s (expected < 2s)")

        # Test 2: Retrieve files with filtering
        start = time.time()
        filtered = monitor.get_immediate_sync_files("/test/perf")
        elapsed = time.time() - start

        if elapsed < 1.0:
            print(f"  ✓ File retrieval: {elapsed:.3f}s (< 1s for 1000 files)")
        else:
            errors.append(f"File retrieval too slow: {elapsed:.3f}s (expected < 1s)")

        assert len(filtered) == 1000

    except Exception as e:
        errors.append(f"Performance test failed: {e}")

    return errors


def generate_report(all_errors):
    """Generate validation report"""
    report = {
        'timestamp': datetime.now().isoformat(),
        'summary': {
            'total_errors': len(all_errors),
            'status': 'PASSED' if len(all_errors) == 0 else 'FAILED'
        },
        'errors': all_errors
    }

    # Save JSON report
    with open('TEST_VALIDATION_REPORT.json', 'w') as f:
        json.dump(report, f, indent=2)

    # Generate markdown report
    with open('TEST_VALIDATION_REPORT.md', 'w') as f:
        f.write("# Test Validation Report\n\n")
        f.write(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

        if len(all_errors) == 0:
            f.write("## ✅ Status: PASSED\n\n")
            f.write("All validation tests passed successfully!\n\n")
        else:
            f.write("## ❌ Status: FAILED\n\n")
            f.write(f"**Total Errors:** {len(all_errors)}\n\n")
            f.write("### Errors\n\n")
            for i, error in enumerate(all_errors, 1):
                f.write(f"{i}. {error}\n")

        f.write("\n## Tests Performed\n\n")
        f.write("1. **Import Tests** - Verify all modules can be imported\n")
        f.write("2. **Functionality Tests** - Test basic operations\n")
        f.write("3. **Thread Safety Tests** - Verify concurrent operations\n")
        f.write("4. **Performance Tests** - Validate performance benchmarks\n")

    print(f"\nReport saved to: TEST_VALIDATION_REPORT.md")


def main():
    print("=" * 80)
    print("FSRsync Test Validation")
    print("=" * 80)
    print()

    all_errors = []

    # Run tests
    all_errors.extend(test_imports())
    all_errors.extend(test_basic_functionality())
    all_errors.extend(test_thread_safety())
    all_errors.extend(test_performance())

    print()
    print("=" * 80)

    if len(all_errors) == 0:
        print("✅ All validation tests PASSED!")
        print("=" * 80)
        generate_report(all_errors)
        return 0
    else:
        print("❌ Validation tests FAILED")
        print(f"Total errors: {len(all_errors)}")
        print("=" * 80)
        print("\nErrors:")
        for i, error in enumerate(all_errors, 1):
            print(f"{i}. {error}")
        generate_report(all_errors)
        return 1


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
