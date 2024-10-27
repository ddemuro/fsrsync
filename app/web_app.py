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

    def __init__(self, sync_state, host="0.0.0.0", port=8080, logger=None):
        """Initialize the web control"""
        if not hasattr(self, 'initialized'):  # Prevent re-initialization
            self.app = FastAPI()
            self.sync_state = sync_state
            self.port = port
            self.host = host
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
            self.app.add_api_route("/set_locked_files", self.set_locked_files, methods=["POST"])
            self.logger.info("Web control routes defined.")

    async def regular_pending(self):
        """Get regular pending files"""
        return self.sync_state.fs_monitor.get_regular_sync_files()

    async def immediate_pending(self):
        """Get immediate pending files"""
        return self.sync_state.fs_monitor.get_immediate_sync_files()

    async def locked_files(self):
        """Get locked files"""
        return self.sync_state.fs_monitor.get_locked_files()

    async def set_locked_files(self, files: list):
        """Set locked files"""
        self.sync_state.fs_monitor.set_locked_files(files)
        return {"status": "success"}

    def run(self):
        """Run the web application"""
        uvicorn.run(self.app, host=self.host, port=self.port, reload=True)

    def start(self):
        """Start the FastAPI app in a separate thread"""
        # self.run()
        # thread = threading.Thread(target=self.run, daemon=True)
        # thread.start()
        # print("FastAPI app is running in a thread.")
