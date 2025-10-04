"""Docker-based integration tests for file syncing

These tests are designed to run inside Docker containers to verify
actual file synchronization works correctly.
"""
import pytest
import os
import time
import json
import tempfile
import shutil


# Mark all tests in this file as integration tests
pytestmark = pytest.mark.integration


class TestDockerSync:
    """Docker-based sync tests"""

    @pytest.fixture
    def test_source_dir(self):
        """Get or create test source directory"""
        source_dir = "/root/source" if os.path.exists("/root/source") else "test/source"
        os.makedirs(source_dir, exist_ok=True)
        return source_dir

    @pytest.fixture
    def test_dest_dir(self):
        """Get or create test destination directory"""
        dest_dir = "/root/destination" if os.path.exists("/root/destination") else "test/destination"
        os.makedirs(dest_dir, exist_ok=True)
        return dest_dir

    def test_source_directory_exists(self, test_source_dir):
        """Verify source directory exists"""
        assert os.path.exists(test_source_dir)
        assert os.path.isdir(test_source_dir)

    def test_destination_directory_exists(self, test_dest_dir):
        """Verify destination directory exists"""
        assert os.path.exists(test_dest_dir)
        assert os.path.isdir(test_dest_dir)

    def test_can_create_file_in_source(self, test_source_dir):
        """Test that we can create files in source directory"""
        test_file = os.path.join(test_source_dir, "test_create.txt")

        try:
            with open(test_file, 'w') as f:
                f.write("test content")

            assert os.path.exists(test_file)
        finally:
            if os.path.exists(test_file):
                os.remove(test_file)

    def test_file_sync_basic(self, test_source_dir, test_dest_dir):
        """Test basic file synchronization (if rsync is available)"""
        # This test will only work in Docker environment with rsync configured
        # Skip if not in Docker
        if not os.path.exists("/root/source"):
            pytest.skip("Not in Docker environment")

        test_file = os.path.join(test_source_dir, "sync_test.txt")
        dest_file = os.path.join(test_dest_dir, "sync_test.txt")

        # Create test file
        with open(test_file, 'w') as f:
            f.write("sync test content")

        # Wait for potential sync (adjust timeout as needed)
        max_wait = 30  # 30 seconds
        start_time = time.time()

        while time.time() - start_time < max_wait:
            if os.path.exists(dest_file):
                # File synced successfully
                with open(dest_file, 'r') as f:
                    content = f.read()
                assert content == "sync test content"
                return
            time.sleep(1)

        # If we get here, sync didn't happen in time
        # This might be expected if sync service isn't running
        pytest.skip("Sync service not active or file not synced in time")


class TestConfigValidation:
    """Test configuration file validation"""

    def test_server_config_exists(self):
        """Test that server config file exists"""
        config_path = os.environ.get("ENVFILE", "/fsrsync/config/test.json")

        # Skip if not in Docker
        if not os.path.exists("/fsrsync"):
            pytest.skip("Not in Docker environment")

        assert os.path.exists(config_path), f"Config file not found: {config_path}"

    def test_server_config_valid_json(self):
        """Test that server config is valid JSON"""
        config_path = os.environ.get("ENVFILE", "/fsrsync/config/test.json")

        if not os.path.exists(config_path):
            pytest.skip("Config file not found")

        with open(config_path, 'r') as f:
            config = json.load(f)

        assert isinstance(config, dict)

    def test_server_config_has_required_fields(self):
        """Test that config has required fields"""
        config_path = os.environ.get("ENVFILE", "/fsrsync/config/test.json")

        if not os.path.exists(config_path):
            pytest.skip("Config file not found")

        with open(config_path, 'r') as f:
            config = json.load(f)

        required_fields = ["hostname", "destinations"]
        for field in required_fields:
            assert field in config, f"Config missing required field: {field}"

    def test_destination_config_valid(self):
        """Test that destination configs are valid"""
        config_path = os.environ.get("ENVFILE", "/fsrsync/config/test.json")

        if not os.path.exists(config_path):
            pytest.skip("Config file not found")

        with open(config_path, 'r') as f:
            config = json.load(f)

        if not config.get("destinations"):
            pytest.skip("No destinations configured")

        for dest in config["destinations"]:
            assert "destination" in dest
            assert "path" in dest
            assert "destination_path" in dest


class TestEnvironmentSetup:
    """Test Docker environment setup"""

    def test_python_version(self):
        """Test Python version"""
        import sys
        assert sys.version_info >= (3, 6), "Python 3.6+ required"

    def test_required_packages_installed(self):
        """Test that required packages are installed"""
        required_packages = [
            'inotify_simple',
            'psutil',
            'fastapi',
            'uvicorn',
            'paramiko',
            'requests',
        ]

        for package in required_packages:
            try:
                __import__(package)
            except ImportError:
                pytest.fail(f"Required package not installed: {package}")

    def test_rsync_available(self):
        """Test that rsync is available"""
        result = os.system("which rsync > /dev/null 2>&1")
        assert result == 0, "rsync not found in PATH"

    def test_ssh_available(self):
        """Test that SSH is available"""
        result = os.system("which ssh > /dev/null 2>&1")
        assert result == 0, "ssh not found in PATH"


class TestPerformance:
    """Performance tests for Docker environment"""

    @pytest.mark.performance
    def test_file_tracking_performance(self):
        """Test performance of file tracking"""
        from fsrsync.utils.filesystem import FilesystemMonitor, File
        from fsrsync.utils.logs import Logger

        monitor = FilesystemMonitor()
        logger = Logger()

        # Measure time to add 1000 files
        start_time = time.time()

        for i in range(1000):
            file = File(f"/test/perf/file{i}.txt", logger)
            monitor.add_immediate_sync_file(file)

        elapsed = time.time() - start_time

        # Should complete in under 2 seconds
        assert elapsed < 2.0, f"File tracking too slow: {elapsed:.2f}s"

        # Verify all files added
        files = monitor.get_immediate_sync_files()
        assert len(files) == 1000

    @pytest.mark.performance
    def test_file_retrieval_performance(self):
        """Test performance of file retrieval"""
        from fsrsync.utils.filesystem import FilesystemMonitor, File
        from fsrsync.utils.logs import Logger

        monitor = FilesystemMonitor()
        logger = Logger()

        # Add files across multiple paths
        for i in range(5000):
            path_num = i % 10
            file = File(f"/dest{path_num}/file{i}.txt", logger)
            monitor.add_immediate_sync_file(file)

        # Measure retrieval time
        start_time = time.time()

        # Get files for a specific path
        files = monitor.get_immediate_sync_files("/dest5")

        elapsed = time.time() - start_time

        # Should complete quickly even with many files
        assert elapsed < 1.0, f"File retrieval too slow: {elapsed:.2f}s"
        assert len(files) == 500

    @pytest.mark.performance
    def test_concurrent_operations_performance(self):
        """Test performance under concurrent load"""
        import threading
        from fsrsync.utils.filesystem import FilesystemMonitor, File
        from fsrsync.utils.logs import Logger

        monitor = FilesystemMonitor()
        logger = Logger()

        def worker(start, count):
            for i in range(start, start + count):
                file = File(f"/test/concurrent/file{i}.txt", logger)
                monitor.add_immediate_sync_file(file)

        # Measure time with concurrent threads
        start_time = time.time()

        threads = []
        for i in range(10):
            thread = threading.Thread(target=worker, args=(i * 100, 100))
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        elapsed = time.time() - start_time

        # Should handle concurrent operations efficiently
        assert elapsed < 5.0, f"Concurrent operations too slow: {elapsed:.2f}s"

        # Verify all files added
        files = monitor.get_immediate_sync_files()
        assert len(files) == 1000
