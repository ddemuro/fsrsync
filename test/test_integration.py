"""Integration tests for FSRsync"""
import pytest
import tempfile
import os
import json
import time
import threading
from fsrsync.sync_app import SyncApplication
from fsrsync.utils.filesystem import FilesystemMonitor, File
from fsrsync.utils.logs import Logger


@pytest.fixture
def temp_config():
    """Create a temporary config file"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        config = {
            "log_level": "DEBUG",
            "hostname": "test-host",
            "control_server_port": 8080,
            "control_server_host": "0.0.0.0",
            "control_server_secret": "test-secret",
            "max_stats": 100,
            "max_server_lock_time": 60,
            "use_global_server_lock": False,
            "full_sync_interval": 60,
            "destinations": []
        }
        json.dump(config, f)
        config_path = f.name

    yield config_path

    # Cleanup
    if os.path.exists(config_path):
        os.unlink(config_path)


@pytest.fixture
def temp_source_dir():
    """Create a temporary source directory"""
    tmpdir = tempfile.mkdtemp()
    yield tmpdir
    # Cleanup is handled by tempfile


@pytest.fixture
def temp_dest_dir():
    """Create a temporary destination directory"""
    tmpdir = tempfile.mkdtemp()
    yield tmpdir
    # Cleanup is handled by tempfile


class TestFilesystemMonitorIntegration:
    """Integration tests for FilesystemMonitor"""

    def test_monitor_file_lifecycle(self):
        """Test complete file lifecycle through the monitor"""
        monitor = FilesystemMonitor(time_between_events=1)
        logger = Logger()

        # Simulate file creation
        file = File("/test/newfile.txt", logger)
        monitor.add_immediate_sync_file(file)

        # Verify file is in immediate sync
        immediate = monitor.get_immediate_sync_files()
        assert len(immediate) == 1

        # Simulate file being synced
        monitor.delete_immediate_sync_file("/test/newfile.txt")

        # Verify file is removed
        immediate = monitor.get_immediate_sync_files()
        assert len(immediate) == 0

    def test_monitor_multiple_destinations(self):
        """Test monitor with multiple destination paths"""
        monitor = FilesystemMonitor(time_between_events=1)
        logger = Logger()

        # Add files for different destinations
        file1 = File("/dest1/file1.txt", logger)
        file2 = File("/dest2/file2.txt", logger)

        monitor.add_immediate_sync_file(file1)
        monitor.add_regular_sync_file(file2)

        # Check path-specific files
        dest1_files = monitor.get_immediate_sync_files("/dest1")
        dest2_files = monitor.get_regular_sync_files("/dest2")

        assert len(dest1_files) == 1
        assert len(dest2_files) == 1
        assert dest1_files[0].path == "/dest1/file1.txt"
        assert dest2_files[0].path == "/dest2/file2.txt"

    def test_monitor_locked_file_handling(self):
        """Test handling of locked files"""
        monitor = FilesystemMonitor(time_between_events=1)
        logger = Logger()

        # Simulate file being opened
        file = File("/test/lockedfile.txt", logger)
        monitor.add_to_locked_files(file)

        # Verify file is locked
        locked = monitor.get_locked_files()
        assert len(locked) == 1

        # Simulate file being closed
        monitor.delete_locked_file("/test/lockedfile.txt")

        # Verify file is unlocked
        locked = monitor.get_locked_files()
        assert len(locked) == 0

    def test_monitor_extension_filtering(self):
        """Test filtering files by extension"""
        monitor = FilesystemMonitor(time_between_events=1)
        logger = Logger()

        # Add files with different extensions
        file1 = File("/test/file1.txt", logger)
        file2 = File("/test/file2.log", logger)
        file3 = File("/test/file3.txt", logger)

        monitor.add_immediate_sync_file(file1)
        monitor.add_immediate_sync_file(file2)
        monitor.add_immediate_sync_file(file3)

        # All files should be present
        all_files = monitor.get_immediate_sync_files()
        assert len(all_files) == 3

        # Extensions should be correctly identified
        txt_files = [f for f in all_files if f.extension == "txt"]
        log_files = [f for f in all_files if f.extension == "log"]
        assert len(txt_files) == 2
        assert len(log_files) == 1


class TestConcurrencyIntegration:
    """Integration tests for concurrent operations"""

    def test_concurrent_file_additions(self):
        """Test adding files concurrently from multiple threads"""
        monitor = FilesystemMonitor(time_between_events=1)
        logger = Logger()
        errors = []

        def add_immediate_files(start, count):
            try:
                for i in range(start, start + count):
                    file = File(f"/test/file{i}.txt", logger)
                    monitor.add_immediate_sync_file(file)
            except Exception as e:
                errors.append(e)

        def add_regular_files(start, count):
            try:
                for i in range(start, start + count):
                    file = File(f"/test/regular{i}.txt", logger)
                    monitor.add_regular_sync_file(file)
            except Exception as e:
                errors.append(e)

        # Create multiple threads
        threads = []
        for i in range(5):
            t1 = threading.Thread(target=add_immediate_files, args=(i * 10, 10))
            t2 = threading.Thread(target=add_regular_files, args=(i * 10, 10))
            threads.extend([t1, t2])

        # Start all threads
        for thread in threads:
            thread.start()

        # Wait for all threads
        for thread in threads:
            thread.join()

        # Verify no errors occurred
        assert len(errors) == 0

        # Verify correct number of files
        immediate = monitor.get_immediate_sync_files()
        regular = monitor.get_regular_sync_files()
        assert len(immediate) == 50
        assert len(regular) == 50

    def test_concurrent_read_write(self):
        """Test concurrent reading and writing"""
        monitor = FilesystemMonitor(time_between_events=1)
        logger = Logger()
        errors = []

        # Pre-populate with some files
        for i in range(100):
            file = File(f"/test/file{i}.txt", logger)
            monitor.add_immediate_sync_file(file)

        def reader():
            try:
                for _ in range(50):
                    files = monitor.get_immediate_sync_files()
                    time.sleep(0.001)
            except Exception as e:
                errors.append(e)

        def writer():
            try:
                for i in range(100, 150):
                    file = File(f"/test/file{i}.txt", logger)
                    monitor.add_immediate_sync_file(file)
                    time.sleep(0.001)
            except Exception as e:
                errors.append(e)

        # Create reader and writer threads
        readers = [threading.Thread(target=reader) for _ in range(3)]
        writers = [threading.Thread(target=writer) for _ in range(2)]

        all_threads = readers + writers

        # Start all threads
        for thread in all_threads:
            thread.start()

        # Wait for all threads
        for thread in all_threads:
            thread.join()

        # Verify no errors occurred
        assert len(errors) == 0


class TestStatisticsIntegration:
    """Integration tests for statistics tracking"""

    def test_statistics_memory_management(self):
        """Test that statistics don't grow unbounded"""
        # This would need a mock sync application
        # Placeholder for future implementation
        pass


class TestPerformance:
    """Performance tests"""

    def test_large_file_set_performance(self):
        """Test performance with large number of files"""
        monitor = FilesystemMonitor(time_between_events=1, max_tracked_files=10000)
        logger = Logger()

        start_time = time.time()

        # Add 5000 files
        for i in range(5000):
            file = File(f"/test/file{i}.txt", logger)
            monitor.add_immediate_sync_file(file)

        add_time = time.time() - start_time

        # Should complete in reasonable time (< 5 seconds)
        assert add_time < 5.0

        # Test retrieval performance
        start_time = time.time()
        files = monitor.get_immediate_sync_files()
        retrieve_time = time.time() - start_time

        assert len(files) == 5000
        assert retrieve_time < 1.0

    def test_path_filter_performance(self):
        """Test performance of path filtering"""
        monitor = FilesystemMonitor(time_between_events=1)
        logger = Logger()

        # Add files across multiple paths
        for i in range(1000):
            path_num = i % 10
            file = File(f"/dest{path_num}/file{i}.txt", logger)
            monitor.add_immediate_sync_file(file)

        # Test filtered retrieval performance
        start_time = time.time()
        filtered = monitor.get_immediate_sync_files("/dest5")
        filter_time = time.time() - start_time

        assert len(filtered) == 100
        assert filter_time < 0.5
