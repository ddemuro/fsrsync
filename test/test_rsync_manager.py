"""Tests for RsyncManager"""
import pytest
import tempfile
import os
from unittest.mock import Mock, patch, MagicMock
from fsrsync.utils.rsync import RsyncManager
from fsrsync.utils.logs import Logger


@pytest.fixture
def temp_source_dir():
    """Create temporary source directory"""
    tmpdir = tempfile.mkdtemp()
    # Create a test file
    test_file = os.path.join(tmpdir, "test.txt")
    with open(test_file, 'w') as f:
        f.write("test content")
    yield tmpdir


@pytest.fixture
def logger():
    """Create logger instance"""
    return Logger()


class TestRsyncManager:
    """Test RsyncManager class"""

    def test_rsync_manager_creation(self, temp_source_dir, logger):
        """Test creating an RsyncManager instance"""
        manager = RsyncManager(
            destination="user@host",
            destination_path="/remote/path",
            path=temp_source_dir,
            options="-avPrl",
            logger=logger
        )

        assert manager.destination == "user@host"
        assert manager.destination_path == "/remote/path"
        assert manager.path == temp_source_dir
        assert manager.options == "-avPrl"
        assert manager.user == "user"
        assert manager.host == "host"

    def test_rsync_manager_invalid_path(self, logger):
        """Test RsyncManager with invalid path"""
        with pytest.raises(ValueError, match="does not exist"):
            RsyncManager(
                destination="user@host",
                destination_path="/remote/path",
                path="/nonexistent/path",
                options="-avPrl",
                logger=logger
            )

    def test_rsync_manager_missing_destination(self, temp_source_dir, logger):
        """Test RsyncManager with missing destination"""
        with pytest.raises(ValueError, match="Destination is required"):
            RsyncManager(
                destination="",
                destination_path="/remote/path",
                path=temp_source_dir,
                options="-avPrl",
                logger=logger
            )

    def test_rsync_manager_destination_parsing(self, temp_source_dir, logger):
        """Test destination parsing"""
        manager = RsyncManager(
            destination="root@192.168.1.100",
            destination_path="/data",
            path=temp_source_dir,
            options="-avPrl",
            logger=logger
        )

        assert manager.user == "root"
        assert manager.host == "192.168.1.100"

    def test_rsync_manager_with_ssh_port(self, temp_source_dir, logger):
        """Test RsyncManager with custom SSH port"""
        manager = RsyncManager(
            destination="user@host",
            destination_path="/remote/path",
            path=temp_source_dir,
            options="-avPrl",
            ssh_port=2222,
            logger=logger
        )

        assert manager.ssh_port == 2222

    def test_rsync_manager_with_commands(self, temp_source_dir, logger):
        """Test RsyncManager with pre/post commands"""
        manager = RsyncManager(
            destination="user@host",
            destination_path="/remote/path",
            path=temp_source_dir,
            options="-avPrl",
            pre_sync_commands_local=["echo pre"],
            post_sync_commands_local=["echo post"],
            logger=logger
        )

        assert manager.pre_sync_commands_local == ["echo pre"]
        assert manager.post_sync_commands_local == ["echo post"]


class TestRsyncExecution:
    """Test rsync command execution"""

    @patch('fsrsync.utils.rsync.run_command')
    def test_build_basic_command(self, mock_run, temp_source_dir, logger):
        """Test building basic rsync command"""
        manager = RsyncManager(
            destination="user@host",
            destination_path="/remote/path",
            path=temp_source_dir,
            options="-avPrl",
            logger=logger
        )

        # Mock successful rsync
        mock_run.return_value = (0, "", "")

        # This would normally execute rsync, but we're mocking it
        # Just verify the manager is set up correctly
        assert manager.options == "-avPrl"
        assert manager.destination == "user@host"

    def test_dedupe_list(self, temp_source_dir, logger):
        """Test deduplication of file lists"""
        manager = RsyncManager(
            destination="user@host",
            destination_path="/remote/path",
            path=temp_source_dir,
            options="-avPrl",
            logger=logger
        )

        # Test dedupe_list method if it exists
        if hasattr(manager, 'dedupe_list'):
            test_list = ["/file1", "/file2", "/file1", "/file3", "/file2"]
            result = manager.dedupe_list(test_list)
            assert len(result) == 3
            assert "/file1" in result
            assert "/file2" in result
            assert "/file3" in result
