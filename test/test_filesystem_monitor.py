"""Tests for the FilesystemMonitor class"""
import pytest
import time
import tempfile
import os
from fsrsync.utils.filesystem import FilesystemMonitor, File
from fsrsync.utils.logs import Logger


class TestFile:
    """Test File class"""

    def test_file_creation(self):
        """Test creating a File object"""
        logger = Logger()
        file = File("/test/path/file.txt", logger)
        assert file.path == "/test/path/file.txt"
        assert file.extension == "txt"
        assert file.successfully_synced == False
        assert file.synced_time is None

    def test_file_without_extension(self):
        """Test File without extension"""
        logger = Logger()
        file = File("/test/path/file", logger)
        assert file.path == "/test/path/file"
        assert file.extension is None

    def test_file_how_long_locked(self):
        """Test how_long_locked method"""
        logger = Logger()
        file = File("/test/path/file.txt", logger)
        time.sleep(0.1)
        assert file.how_long_locked() >= 0.1


class TestFilesystemMonitor:
    """Test FilesystemMonitor class"""

    @pytest.fixture
    def monitor(self):
        """Create a FilesystemMonitor instance"""
        return FilesystemMonitor(time_between_events=1)

    @pytest.fixture
    def logger(self):
        """Create a Logger instance"""
        return Logger()

    def test_monitor_creation(self, monitor):
        """Test creating a FilesystemMonitor"""
        assert monitor is not None
        assert monitor.time_between_events == 1
        assert len(monitor.open_files) == 0
        assert len(monitor.immediate_sync) == 0
        assert len(monitor.regular_sync) == 0

    def test_add_immediate_sync_file(self, monitor, logger):
        """Test adding file to immediate sync"""
        file = File("/test/file.txt", logger)
        monitor.add_immediate_sync_file(file)

        immediate_files = monitor.get_immediate_sync_files()
        assert len(immediate_files) == 1
        assert immediate_files[0].path == "/test/file.txt"

    def test_add_immediate_sync_file_duplicate(self, monitor, logger):
        """Test adding duplicate file to immediate sync"""
        file1 = File("/test/file.txt", logger)
        file2 = File("/test/file.txt", logger)

        monitor.add_immediate_sync_file(file1)
        monitor.add_immediate_sync_file(file2)

        immediate_files = monitor.get_immediate_sync_files()
        assert len(immediate_files) == 1

    def test_add_regular_sync_file(self, monitor, logger):
        """Test adding file to regular sync"""
        file = File("/test/file.txt", logger)
        monitor.add_regular_sync_file(file)

        regular_files = monitor.get_regular_sync_files()
        assert len(regular_files) == 1
        assert regular_files[0].path == "/test/file.txt"

    def test_add_locked_file(self, monitor, logger):
        """Test adding file to locked files"""
        file = File("/test/file.txt", logger)
        monitor.add_to_locked_files(file)

        locked_files = monitor.get_locked_files()
        assert len(locked_files) == 1
        assert locked_files[0].path == "/test/file.txt"

    def test_delete_immediate_sync_file(self, monitor, logger):
        """Test deleting file from immediate sync"""
        file = File("/test/file.txt", logger)
        monitor.add_immediate_sync_file(file)

        immediate_files = monitor.get_immediate_sync_files()
        assert len(immediate_files) == 1

        monitor.delete_immediate_sync_file("/test/file.txt")
        immediate_files = monitor.get_immediate_sync_files()
        assert len(immediate_files) == 0

    def test_delete_regular_sync_file(self, monitor, logger):
        """Test deleting file from regular sync"""
        file = File("/test/file.txt", logger)
        monitor.add_regular_sync_file(file)

        regular_files = monitor.get_regular_sync_files()
        assert len(regular_files) == 1

        monitor.delete_regular_sync_file("/test/file.txt")
        regular_files = monitor.get_regular_sync_files()
        assert len(regular_files) == 0

    def test_get_immediate_sync_files_with_path_filter(self, monitor, logger):
        """Test getting immediate sync files with path filter"""
        file1 = File("/test/path1/file.txt", logger)
        file2 = File("/test/path2/file.txt", logger)

        monitor.add_immediate_sync_file(file1)
        monitor.add_immediate_sync_file(file2)

        filtered_files = monitor.get_immediate_sync_files("/test/path1")
        assert len(filtered_files) == 1
        assert filtered_files[0].path == "/test/path1/file.txt"

    def test_get_regular_sync_files_with_path_filter(self, monitor, logger):
        """Test getting regular sync files with path filter"""
        file1 = File("/test/path1/file.txt", logger)
        file2 = File("/test/path2/file.txt", logger)

        monitor.add_regular_sync_file(file1)
        monitor.add_regular_sync_file(file2)

        filtered_files = monitor.get_regular_sync_files("/test/path1")
        assert len(filtered_files) == 1
        assert filtered_files[0].path == "/test/path1/file.txt"

    def test_delete_immediate_sync_files_for_path(self, monitor, logger):
        """Test deleting immediate sync files for a specific path"""
        file1 = File("/test/path1/file1.txt", logger)
        file2 = File("/test/path1/file2.txt", logger)
        file3 = File("/test/path2/file3.txt", logger)

        monitor.add_immediate_sync_file(file1)
        monitor.add_immediate_sync_file(file2)
        monitor.add_immediate_sync_file(file3)

        monitor.delete_immediate_sync_files_for_path("/test/path1")

        immediate_files = monitor.get_immediate_sync_files()
        assert len(immediate_files) == 1
        assert immediate_files[0].path == "/test/path2/file3.txt"

    def test_delete_regular_sync_files_for_path(self, monitor, logger):
        """Test deleting regular sync files for a specific path"""
        file1 = File("/test/path1/file1.txt", logger)
        file2 = File("/test/path1/file2.txt", logger)
        file3 = File("/test/path2/file3.txt", logger)

        monitor.add_regular_sync_file(file1)
        monitor.add_regular_sync_file(file2)
        monitor.add_regular_sync_file(file3)

        monitor.delete_regular_sync_files_for_path("/test/path1")

        regular_files = monitor.get_regular_sync_files()
        assert len(regular_files) == 1
        assert regular_files[0].path == "/test/path2/file3.txt"

    def test_clear_locks_exceeded_wait(self, monitor, logger):
        """Test clearing locks that exceeded wait time"""
        file1 = File("/test/path/file1.txt", logger)
        file2 = File("/test/path/file2.txt", logger)

        # Manually set start time to simulate old lock
        file1.start_time = time.time() - 100
        file2.start_time = time.time()

        monitor.add_to_locked_files(file1)
        monitor.add_to_locked_files(file2)

        # Clear locks older than 50 seconds
        non_exceeded = monitor.clear_locks_exceeded_wait("/test/path", 50)

        # Only file2 should remain
        assert len(non_exceeded) == 1
        assert non_exceeded[0].path == "/test/path/file2.txt"

    def test_get_aggregated_events(self, monitor, logger):
        """Test getting aggregated events"""
        file1 = File("/test/immediate.txt", logger)
        file2 = File("/test/regular.txt", logger)
        file3 = File("/test/locked.txt", logger)

        monitor.add_immediate_sync_file(file1)
        monitor.add_regular_sync_file(file2)
        monitor.add_to_locked_files(file3)

        aggregated = monitor.get_aggregated_events()

        assert len(aggregated["immediate"]) == 1
        assert len(aggregated["regular"]) == 1
        assert len(aggregated["locked"]) == 1
        assert "/test/immediate.txt" in aggregated["immediate"]
        assert "/test/regular.txt" in aggregated["regular"]
        assert "/test/locked.txt" in aggregated["locked"]

    def test_thread_safety_immediate_sync(self, monitor, logger):
        """Test thread safety for immediate sync operations"""
        import threading

        def add_files():
            for i in range(100):
                file = File(f"/test/file{i}.txt", logger)
                monitor.add_immediate_sync_file(file)

        threads = [threading.Thread(target=add_files) for _ in range(5)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        # Should have exactly 100 unique files (no duplicates due to threading)
        immediate_files = monitor.get_immediate_sync_files()
        assert len(immediate_files) == 100

    def test_max_tracked_files_limit(self, logger):
        """Test that max tracked files limit is enforced"""
        monitor = FilesystemMonitor(max_tracked_files=10)

        # Add more files than the limit
        for i in range(15):
            file = File(f"/test/file{i}.txt", logger)
            monitor.add_regular_sync_file(file)

        regular_files = monitor.get_regular_sync_files()
        # Should not exceed max_tracked_files
        assert len(regular_files) <= 10
