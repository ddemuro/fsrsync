"""Test various sync scenarios"""
import pytest
import time
import threading
from fsrsync.utils.filesystem import FilesystemMonitor, File
from fsrsync.utils.logs import Logger


class TestSyncScenarios:
    """Test real-world sync scenarios"""

    @pytest.fixture
    def monitor(self):
        """Create filesystem monitor"""
        return FilesystemMonitor(time_between_events=1)

    @pytest.fixture
    def logger(self):
        """Create logger"""
        return Logger()

    def test_rapid_file_creation(self, monitor, logger):
        """Test rapid creation of many files"""
        # Simulate rapid file creation
        for i in range(100):
            file = File(f"/test/rapid/file{i}.txt", logger)
            monitor.add_immediate_sync_file(file)

        # All files should be tracked
        immediate_files = monitor.get_immediate_sync_files()
        assert len(immediate_files) == 100

    def test_file_open_close_sequence(self, monitor, logger):
        """Test file open/close sequence"""
        file_path = "/test/sequence/file.txt"

        # Simulate file open
        file_open = File(file_path, logger)
        monitor.add_to_locked_files(file_open)

        locked = monitor.get_locked_files()
        assert len(locked) == 1

        # Simulate file close
        monitor.delete_locked_file(file_path)

        # Should be unlocked
        locked = monitor.get_locked_files()
        assert len(locked) == 0

        # Should be in immediate sync
        file_closed = File(file_path, logger)
        monitor.add_immediate_sync_file(file_closed)

        immediate = monitor.get_immediate_sync_files()
        assert len(immediate) == 1

    def test_file_modification_sequence(self, monitor, logger):
        """Test file modification sequence"""
        file_path = "/test/modify/file.txt"

        # Multiple modifications should only create one entry
        for _ in range(5):
            file = File(file_path, logger)
            monitor.add_regular_sync_file(file)

        regular = monitor.get_regular_sync_files()
        assert len(regular) == 1

    def test_file_delete_during_sync(self, monitor, logger):
        """Test file deleted while in sync queue"""
        file_path = "/test/delete/file.txt"

        # Add to immediate sync
        file = File(file_path, logger)
        monitor.add_immediate_sync_file(file)

        immediate = monitor.get_immediate_sync_files()
        assert len(immediate) == 1

        # Simulate delete
        monitor.delete_immediate_sync_file(file_path)
        monitor.delete_regular_sync_file(file_path)
        monitor.delete_locked_file(file_path)

        # Should be removed from all queues
        immediate = monitor.get_immediate_sync_files()
        regular = monitor.get_regular_sync_files()
        locked = monitor.get_locked_files()

        assert len(immediate) == 0
        assert len(regular) == 0
        assert len(locked) == 0

    def test_locked_file_timeout(self, monitor, logger):
        """Test locked file timeout clearing"""
        file_path = "/test/locked/file.txt"

        # Create a file with old timestamp
        file = File(file_path, logger)
        file.start_time = time.time() - 200  # 200 seconds ago

        monitor.add_to_locked_files(file)

        # Clear locks older than 100 seconds
        non_exceeded = monitor.clear_locks_exceeded_wait("/test/locked", 100)

        # File should be removed (it's 200 seconds old)
        assert len(non_exceeded) == 0

        locked = monitor.get_locked_files()
        assert len(locked) == 0

    def test_extension_filtering_scenario(self, monitor, logger):
        """Test filtering files by extension"""
        # Add various files
        files = [
            File("/test/file1.txt", logger),
            File("/test/file2.log", logger),
            File("/test/file3.tmp", logger),
            File("/test/file4.txt", logger),
        ]

        for file in files:
            monitor.add_immediate_sync_file(file)

        all_files = monitor.get_immediate_sync_files()

        # Filter by extension manually
        txt_files = [f for f in all_files if f.extension == "txt"]
        log_files = [f for f in all_files if f.extension == "log"]
        tmp_files = [f for f in all_files if f.extension == "tmp"]

        assert len(txt_files) == 2
        assert len(log_files) == 1
        assert len(tmp_files) == 1

    def test_path_based_destination_filtering(self, monitor, logger):
        """Test filtering files by destination path"""
        # Add files for different destinations
        dest1_files = [File(f"/dest1/file{i}.txt", logger) for i in range(10)]
        dest2_files = [File(f"/dest2/file{i}.txt", logger) for i in range(15)]

        for file in dest1_files + dest2_files:
            monitor.add_immediate_sync_file(file)

        # Get files for each destination
        dest1_filtered = monitor.get_immediate_sync_files("/dest1")
        dest2_filtered = monitor.get_immediate_sync_files("/dest2")

        assert len(dest1_filtered) == 10
        assert len(dest2_filtered) == 15

    def test_concurrent_file_operations(self, monitor, logger):
        """Test concurrent add/remove operations"""
        errors = []

        def add_files(start, count):
            try:
                for i in range(start, start + count):
                    file = File(f"/test/concurrent/file{i}.txt", logger)
                    monitor.add_immediate_sync_file(file)
            except Exception as e:
                errors.append(e)

        def remove_files(start, count):
            try:
                time.sleep(0.1)  # Let some files be added first
                for i in range(start, start + count):
                    monitor.delete_immediate_sync_file(f"/test/concurrent/file{i}.txt")
            except Exception as e:
                errors.append(e)

        # Create threads
        add_thread1 = threading.Thread(target=add_files, args=(0, 50))
        add_thread2 = threading.Thread(target=add_files, args=(50, 50))
        remove_thread = threading.Thread(target=remove_files, args=(0, 25))

        # Start threads
        add_thread1.start()
        add_thread2.start()
        remove_thread.start()

        # Wait for completion
        add_thread1.join()
        add_thread2.join()
        remove_thread.join()

        # No errors should occur
        assert len(errors) == 0

        # Should have 75 files (100 added - 25 removed)
        immediate = monitor.get_immediate_sync_files()
        assert len(immediate) == 75

    def test_immediate_vs_regular_sync_priority(self, monitor, logger):
        """Test that immediate and regular syncs are properly separated"""
        # Add files to both queues
        immediate_file = File("/test/priority/immediate.txt", logger)
        regular_file = File("/test/priority/regular.txt", logger)

        monitor.add_immediate_sync_file(immediate_file)
        monitor.add_regular_sync_file(regular_file)

        # Should be in separate queues
        immediate = monitor.get_immediate_sync_files()
        regular = monitor.get_regular_sync_files()

        assert len(immediate) == 1
        assert len(regular) == 1
        assert immediate[0].path == "/test/priority/immediate.txt"
        assert regular[0].path == "/test/priority/regular.txt"

    def test_cleanup_after_sync(self, monitor, logger):
        """Test cleanup of files after successful sync"""
        # Add files to sync
        files = [File(f"/test/cleanup/file{i}.txt", logger) for i in range(10)]

        for file in files:
            monitor.add_immediate_sync_file(file)

        # Simulate successful sync - remove all files
        for file in files:
            monitor.delete_immediate_sync_file(file.path)

        # Queue should be empty
        immediate = monitor.get_immediate_sync_files()
        assert len(immediate) == 0

    def test_max_tracked_files_enforcement(self, logger):
        """Test that max_tracked_files limit is enforced"""
        monitor = FilesystemMonitor(max_tracked_files=50)

        # Try to add more than the limit
        for i in range(100):
            file = File(f"/test/limit/file{i}.txt", logger)
            monitor.add_regular_sync_file(file)

        # Should not exceed limit
        regular = monitor.get_regular_sync_files()
        assert len(regular) <= 50

    def test_aggregated_events_accuracy(self, monitor, logger):
        """Test that aggregated events are accurate"""
        # Add files to different queues
        for i in range(5):
            monitor.add_immediate_sync_file(File(f"/test/agg/imm{i}.txt", logger))

        for i in range(10):
            monitor.add_regular_sync_file(File(f"/test/agg/reg{i}.txt", logger))

        for i in range(3):
            monitor.add_to_locked_files(File(f"/test/agg/lock{i}.txt", logger))

        # Get aggregated events
        aggregated = monitor.get_aggregated_events()

        assert len(aggregated["immediate"]) == 5
        assert len(aggregated["regular"]) == 10
        assert len(aggregated["locked"]) == 3
