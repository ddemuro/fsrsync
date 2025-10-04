"""Tests for the Web API"""
import pytest
import json
import tempfile
import os
from fastapi.testclient import TestClient
from fsrsync.web_app import WebControl
from fsrsync.sync_app import SyncApplication
from fsrsync.utils.logs import Logger


class MockSyncApplication:
    """Mock SyncApplication for testing"""

    def __init__(self):
        self.hostname = "test-server"
        self.destinations = []
        self.remote_hosts = []
        self.global_server_locks = []
        self.files_to_delete_after_sync_regular = []
        self.files_to_delete_after_sync_immediate = []
        self.syncs_running_currently = []
        self.max_stats = 100
        self.full_sync = False

        # Create a mock fs_monitor
        from fsrsync.utils.filesystem import FilesystemMonitor
        self.fs_monitor = FilesystemMonitor()

    def check_if_server_is_locked(self, server, path=None):
        """Mock method"""
        return False

    def add_to_global_server_locks(self, server, path):
        """Mock method"""
        return True

    def remove_from_global_server_locks(self, server, path):
        """Mock method"""
        return True


@pytest.fixture
def mock_sync_app():
    """Create a mock sync application"""
    return MockSyncApplication()


@pytest.fixture
def web_app(mock_sync_app):
    """Create a WebControl instance"""
    logger = Logger()
    return WebControl(
        mock_sync_app,
        host="127.0.0.1",
        port=8080,
        secret="test-secret",
        logger=logger
    )


@pytest.fixture
def client(web_app):
    """Create a test client"""
    return TestClient(web_app.app)


class TestWebAPI:
    """Test Web API endpoints"""

    def test_list_routes(self, client):
        """Test listing all routes"""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "routes" in data
        assert len(data["routes"]) > 0

    def test_health_endpoint(self, client):
        """Test health check endpoint"""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["hostname"] == "test-server"

    def test_regular_pending_without_auth(self, client):
        """Test regular pending endpoint without authentication"""
        response = client.get("/regular_pending")
        assert response.status_code == 422  # Missing secret header

    def test_regular_pending_with_auth(self, client):
        """Test regular pending endpoint with authentication"""
        response = client.get(
            "/regular_pending",
            headers={"secret": "test-secret"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "files" in data
        assert isinstance(data["files"], list)

    def test_immediate_pending_with_auth(self, client):
        """Test immediate pending endpoint with authentication"""
        response = client.get(
            "/immediate_pending",
            headers={"secret": "test-secret"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "files" in data
        assert isinstance(data["files"], list)

    def test_locked_files_with_auth(self, client):
        """Test locked files endpoint with authentication"""
        response = client.get(
            "/locked_files",
            headers={"secret": "test-secret"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "files" in data
        assert isinstance(data["files"], list)

    def test_stats_with_auth(self, client):
        """Test stats endpoint with authentication"""
        response = client.get(
            "/stats",
            params={"secret": "test-secret"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "result" in data

    def test_stats_running_with_auth(self, client):
        """Test stats-running endpoint with authentication"""
        response = client.get(
            "/stats-running",
            params={"secret": "test-secret"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "result" in data
        assert "aggregated_events" in data
        assert "hostname" in data
        assert data["hostname"] == "test-server"

    def test_add_to_global_server_lock(self, client):
        """Test adding to global server lock"""
        response = client.post(
            "/add_to_global_server_lock",
            json={"server": "test-server", "path": "/test/path"},
            headers={"secret": "test-secret"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "status" in data

    def test_remove_from_global_server_lock(self, client):
        """Test removing from global server lock"""
        response = client.post(
            "/remove_from_global_server_lock",
            json={"server": "test-server", "path": "/test/path"},
            headers={"secret": "test-secret"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "status" in data

    def test_check_if_server_locked(self, client):
        """Test checking if server is locked"""
        response = client.post(
            "/check_if_server_locked",
            json={"server": "test-server", "path": "/test/path"},
            headers={"secret": "test-secret"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert data["status"] == False

    def test_delete_file_pending_for_path(self, client):
        """Test deleting file pending for path"""
        response = client.post(
            "/delete_file_pending_for_path",
            json={"path": "/test/file.txt"},
            headers={"secret": "test-secret"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"

    def test_trigger_sync(self, client):
        """Test triggering a sync"""
        response = client.post(
            "/trigger_sync",
            json={"path": "/test/path"},
            headers={"secret": "test-secret"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "status" in data

    def test_pending_files_by_path(self, client):
        """Test getting pending files by path"""
        response = client.get(
            "/pending_files_by_path",
            params={"path": "/test/path", "secret": "test-secret"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "path" in data
        assert "immediate_count" in data
        assert "regular_count" in data
        assert "locked_count" in data
        assert isinstance(data["immediate_files"], list)
        assert isinstance(data["regular_files"], list)
        assert isinstance(data["locked_files"], list)

    def test_dashboard_without_secret(self, client):
        """Test dashboard without secret"""
        response = client.get("/dashboard")
        assert response.status_code == 200
        # Should return a page asking for secret

    def test_dashboard_with_secret(self, client):
        """Test dashboard with secret"""
        response = client.get("/dashboard?secret=test-secret")
        assert response.status_code == 200

    def test_invalid_secret(self, client):
        """Test with invalid secret"""
        response = client.get(
            "/regular_pending",
            headers={"secret": "wrong-secret"}
        )
        assert response.status_code == 401

    def test_missing_required_fields(self, client):
        """Test endpoints with missing required fields"""
        response = client.post(
            "/add_to_global_server_lock",
            json={},
            headers={"secret": "test-secret"}
        )
        assert response.status_code == 422  # Validation error
