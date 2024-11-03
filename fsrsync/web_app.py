import uvicorn
import threading
from fastapi import FastAPI


class WebControl:
    """Web control for the application"""

    _instance = None

    def __new__(cls, *args, **kwargs):
        """Ensure that only one instance of WebControl exists"""
        if cls._instance is None:
            cls._instance = super(WebControl, cls).__new__(cls)
        return cls._instance

    def __init__(
        self, sync_state, host="0.0.0.0", port=8080, secret="secret", logger=None
    ):
        """Initialize the web control"""
        if not hasattr(self, "initialized"):  # Prevent re-initialization
            self.app = FastAPI()
            self.sync_state = sync_state
            self.port = port
            self.host = host
            self.secret = secret
            self.logger = logger
            self.initialized = True  # Flag to indicate initialization
            self.logger.info(f"Web control initialized. Host: {host}, Port: {port}")

            # Define routes
            self.app.add_api_route(
                "/regular_pending", self.regular_pending, methods=["GET"]
            )
            self.app.add_api_route(
                "/immediate_pending", self.immediate_pending, methods=["GET"]
            )
            self.app.add_api_route("/locked_files", self.locked_files, methods=["GET"])
            self.app.add_api_route(
                "/add_locked_files", self.add_locked_files, methods=["POST"]
            )
            self.app.add_api_route(
                "/remove_locked_files", self.remove_locked_files, methods=["POST"]
            )
            self.app.add_api_route(
                "/add_file_to_locked_files",
                self.add_file_to_locked_files,
                methods=["POST"],
            )
            self.app.add_api_route(
                "/add_to_global_server_lock",
                self.add_to_global_server_lock,
                methods=["POST"],
            )
            self.app.add_api_route(
                "/remove_from_global_server_lock",
                self.remove_from_global_server_lock,
                methods=["POST"],
            )
            self.logger.info("Web control routes defined.")

    def check_if_secret_in_header(self, headers):
        """Check if secret is in the header"""
        if "secret" not in headers:
            return False
        return headers["secret"] == self.secret

    async def regular_pending(self):
        """Get regular pending files"""
        # Check if secret is in the header
        if not self.check_if_secret_in_header(self.app.state.headers):
            return {"status": "error", "message": "Unauthorized"}
        return self.sync_state.fs_monitor.get_regular_sync_files()

    async def immediate_pending(self):
        """Get immediate pending files"""
        if not self.check_if_secret_in_header(self.app.state.headers):
            return {"status": "error", "message": "Unauthorized"}
        return self.sync_state.fs_monitor.get_immediate_sync_files()

    async def locked_files(self):
        """Get locked files"""
        if not self.check_if_secret_in_header(self.app.state.headers):
            return {"status": "error", "message": "Unauthorized"}
        return self.sync_state.fs_monitor.get_locked_files()

    async def add_locked_files(self):
        """Set locked files"""
        if not self.check_if_secret_in_header(self.app.state.headers):
            return {"status": "error", "message": "Unauthorized"}
        request_body = await self.app.state.request.json()
        files = request_body.get("files", [])
        for file in files:
            self.sync_state.fs_monitor.add_file_to_locked_files(file)
        return {"status": "success"}

    async def remove_locked_files(self):
        """Remove a file from the locked files"""
        if not self.check_if_secret_in_header(self.app.state.headers):
            return {"status": "error", "message": "Unauthorized"}
        request_body = await self.app.state.request.json()
        files = request_body.get("files", [])
        for file in files:
            self.sync_state.fs_monitor.delete_locked_file(file)
        return {"status": "success"}

    async def add_file_to_locked_files(self):
        """Add a file to the locked files"""
        if not self.check_if_secret_in_header(self.app.state.headers):
            return {"status": "error", "message": "Unauthorized"}
        request_body = await self.app.state.request.json()
        file = request_body.get("file", "")
        self.sync_state.fs_monitor.add_to_locked_files(file)
        return {"status": "success"}

    async def add_to_global_server_lock(self):
        """Add a server to the global server lock"""
        if not self.check_if_secret_in_header(self.app.state.headers):
            return {"status": "error", "message": "Unauthorized"}
        request_body = await self.app.state.request.json()
        self.sync_state.add_to_global_server_locks(request_body.get("server", ""))
        return {"status": "success"}

    async def remove_from_global_server_lock(self):
        """Remove a server from the global server lock"""
        if not self.check_if_secret_in_header(self.app.state.headers):
            return {"status": "error", "message": "Unauthorized"}
        # Get the server to remove from the body of the request
        request_body = await self.app.state.request.json()
        self.sync_state.remove_from_global_server_locks(request_body.get("server", ""))
        return {"status": "success"}

    def run(self):
        """Run the web application"""
        uvicorn.run(self.app, host=self.host, port=self.port, reload=True)

    def start(self):
        """Start the FastAPI app in a separate thread"""
        thread = threading.Thread(target=self.run, daemon=True)
        thread.start()
        print("FastAPI app is running in a thread.")
