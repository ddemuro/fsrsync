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

    # Post to add a string to add_to_global_server_locks in instance.sync_state.add_to_global_server_locks format of post {"server": "server_name"}
    @app.post("/add_to_global_server_lock")
    async def add_to_global_server_lock(request: Request):  # pylint: disable=no-self-argument
        """Add a server to the global server locks"""
        instance = WebControl._instance
        if not instance.check_if_secret_in_header(request.headers):
            raise HTTPException(status_code=401, detail="Unauthorized")
        request_body = await request.json()
        server = request_body.get("server")
        path = request_body.get("path", None)
        result = instance.sync_state.add_to_global_server_locks(server, path)
        return {"status": result}

    # Post to remove a string to remove_from_global_server_locks in instance.sync_state.remove_from_global_server_locks format of post {"server": "server_name"}
    @app.post("/remove_from_global_server_lock")
    async def remove_from_global_server_lock(request: Request):  # pylint: disable=no-self-argument
        """Remove a server from the global server locks"""
        instance = WebControl._instance
        if not instance.check_if_secret_in_header(request.headers):
            raise HTTPException(status_code=401, detail="Unauthorized")
        request_body = await request.json()
        server = request_body.get("server")
        path = request_body.get("path", None)
        result = instance.sync_state.remove_from_global_server_locks(server, path)
        return {"status": result}

    @app.post("/check_if_server_locked")
    async def check_if_server_locked(request: Request):  # pylint: disable=no-self-argument
        """Check if a server is locked"""
        instance = WebControl._instance
        if not instance.check_if_secret_in_header(request.headers):
            raise HTTPException(status_code=401, detail="Unauthorized")
        request_body = await request.json()
        server = request_body.get("server")
        result = instance.sync_state.check_if_server_is_locked(server)
        return {"status": result}

    # Post to add a file to files_to_delete_after_sync_regular in instance.sync_state.add_to_files_to_delete_after_sync_regular format of post {"file": "file_name"}
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

    @app.post("/delete_file_pending_for_path")
    async def delete_file_pending_for_path(request: Request):  # pylint: disable=no-self-argument
        """Delete file pending for path"""
        instance = WebControl._instance
        if not instance.check_if_secret_in_header(request.headers):
            raise HTTPException(status_code=401, detail="Unauthorized")
        request_body = await request.json()
        path = request_body.get("path")
        result = instance.sync_state.fs_monitor.delete_fs_event_for_path(path)
        return {"status": result}

    @app.get("/locked_files")
    async def locked_files(request: Request):  # pylint: disable=no-self-argument
        """Get locked files"""
        instance = WebControl._instance
        if not instance.check_if_secret_in_header(request.headers):
            raise HTTPException(status_code=401, detail="Unauthorized")
        return instance.sync_state.fs_monitor.get_locked_files()

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

    @app.get("/stats-running")
    async def stats_running(request: Request):
        instance = WebControl._instance
        secret = request.query_params.get("secret")

        if not secret or secret != instance.secret:
            # If secret is not provided or invalid, return json with error
            return {"error": "Unauthorized, secret in query string not provided or invalid. example: /stats-running?secret=your_secret_here"}
        result = []
        for destination in instance.sync_state.destinations:
            result.append({
                "destination": destination.get("path", ""),
                "destination_config": destination,
            })
        # instance remote hosts
        rh = instance.sync_state.remote_hosts
        gsl = instance.sync_state.global_server_locks
        frs = instance.sync_state.files_to_delete_after_sync_regular
        fia = instance.sync_state.files_to_delete_after_sync_immediate
        src = instance.sync_state.syncs_running_currently
        maxstats = instance.sync_state.max_stats
        fse = instance.sync_state.full_sync
        aggregate_cel = instance.sync_state.fs_monitor.get_aggregated_events()
        return {
            "result": result,
            "remote_hosts": rh,
            "global_server_locks": gsl,
            "files_to_delete_after_sync_regular": frs,
            "files_to_delete_after_sync_immediate": fia,
            "syncs_running_currently": src,
            "max_stats": maxstats,
            "full_sync": fse,
            "aggregated_events": aggregate_cel,
        }
        

    def run(self):
        """Run the web application"""
        uvicorn.run(self.app, host=self.host, port=self.port)

    def start(self):
        """Start the FastAPI app in a separate thread"""
        thread = threading.Thread(target=self.run, daemon=True)
        thread.start()
        print("FastAPI app is running in a thread.")
