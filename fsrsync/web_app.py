import os
import uvicorn
import threading
from fastapi import FastAPI, Request, HTTPException, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates


class WebControl:
    """Web control for the application"""

    _instance = None
    app = FastAPI()
    scriptdir = os.path.dirname(os.path.realpath(__file__))
    templates = Jinja2Templates(directory=os.path.join(scriptdir, "templates"))

    def __new__(cls, *args, **kwargs):
        """Ensure that only one instance of WebControl exists"""
        if cls._instance is None:
            cls._instance = super(WebControl, cls).__new__(cls)
        return cls._instance

    def __init__(self, sync_state, host="0.0.0.0", port=8080, secret="secret", logger=None):
        """Initialize the web control"""
        if not hasattr(self, "initialized"):  # Prevent re-initialization
            self.sync_state = sync_state
            self.port = port
            self.host = host
            self.secret = secret
            self.logger = logger or print  # Use `print` as a fallback logger
            self.initialized = True  # Flag to indicate initialization
            if logger:
                self.logger.info(f"Web control initialized. Host: {host}, Port: {port}")

    def check_if_secret_in_header(self, headers):
        """Check if secret is in the header"""
        return headers.get("secret") == self.secret

    @app.get("/")
    async def list_routes():  # pylint: disable=no-self-argument, no-method-argument
        """List the routes"""
        routes = [{"path": route.path, "methods": route.methods,
                   "name": route.name} for route in WebControl.app.routes]
        return {"routes": routes}

    @app.get("/regular_pending")
    async def regular_pending(request: Request):  # pylint: disable=no-self-argument
        """Get regular pending files"""
        instance = WebControl._instance
        if not instance.check_if_secret_in_header(request.headers):
            raise HTTPException(status_code=401, detail="Unauthorized")
        return instance.sync_state.fs_monitor.get_regular_sync_files()

    @app.get("/immediate_pending")
    async def immediate_pending(request: Request):  # pylint: disable=no-self-argument
        """Get immediate pending files"""
        instance = WebControl._instance
        if not instance.check_if_secret_in_header(request.headers):
            raise HTTPException(status_code=401, detail="Unauthorized")
        return instance.sync_state.fs_monitor.get_immediate_sync_files()

    @app.get("/locked_files")
    async def locked_files(request: Request):  # pylint: disable=no-self-argument
        """Get locked files"""
        instance = WebControl._instance
        if not instance.check_if_secret_in_header(request.headers):
            raise HTTPException(status_code=401, detail="Unauthorized")
        return instance.sync_state.fs_monitor.get_locked_files()

    @app.post("/add_locked_files")
    async def add_locked_files(request: Request):  # pylint: disable=no-self-argument
        """Set locked files"""
        instance = WebControl._instance
        if not instance.check_if_secret_in_header(request.headers):
            raise HTTPException(status_code=401, detail="Unauthorized")
        request_body = await request.json()
        files = request_body.get("files", [])
        for file in files:
            instance.sync_state.fs_monitor.add_file_to_locked_files(file)
        return {"status": "success"}

    @app.post("/remove_locked_files")
    async def remove_locked_files(request: Request):  # pylint: disable=no-self-argument
        """Remove a file from the locked files"""
        instance = WebControl._instance
        if not instance.check_if_secret_in_header(request.headers):
            raise HTTPException(status_code=401, detail="Unauthorized")
        request_body = await request.json()
        files = request_body.get("files", [])
        for file in files:
            instance.sync_state.fs_monitor.delete_locked_file(file)
        return {"status": "success"}

    @app.get("/dashboard", response_class=HTMLResponse)
    async def dashboard(request: Request):  # pylint: disable=no-self-argument
        instance = WebControl._instance
        secret = request.query_params.get("secret")

        if not secret or secret != instance.secret:
            # If secret is not provided or invalid, return template with `secret_provided` set to `False`
            return instance.templates.TemplateResponse("dashboard.html", {
                "request": request,
                "secret_provided": False
            })

        result = []
        for destination in instance.sync_state.destinations:
            result.append({
                "destination": destination.get("path", ""),
                "statistics": destination.get("statistics", {}),
            })

        # Return template with data when secret is valid
        return instance.templates.TemplateResponse("dashboard.html", {
            "request": request,
            "result": result,
            "secret_provided": True,
            "secret": secret
        })

    @app.get("/stats")
    async def stats(request: Request):  # pylint: disable=no-self-argument
        instance = WebControl._instance
        secret = request.query_params.get("secret")

        if not secret or secret != instance.secret:
            # If secret is not provided or invalid, return json with error
            return {"error": "Unauthorized, secret in query string not provided or invalid. example: /stats?secret=your_secret_here"}

        result = []
        for destination in instance.sync_state.destinations:
            result.append({
                "destination": destination.get("path", ""),
                "statistics": destination.get("statistics", {}),
            })

    def run(self):
        """Run the web application"""
        uvicorn.run(self.app, host=self.host, port=self.port)

    def start(self):
        """Start the FastAPI app in a separate thread"""
        thread = threading.Thread(target=self.run, daemon=True)
        thread.start()
        print("FastAPI app is running in a thread.")
