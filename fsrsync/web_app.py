import os
import uvicorn
import threading
import logging
from typing import Optional, Dict, Any, List
from fastapi import FastAPI, Request, HTTPException, Depends, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

# Define request models for better validation
class ServerLockRequest(BaseModel):
    server: str
    path: Optional[str] = None

class FilePathRequest(BaseModel):
    path: str

class WebControl:
    """Web control for the application with improved design and security"""

    _instance = None
    _lock = threading.Lock()  # Thread safety lock
    scriptdir = os.path.dirname(os.path.realpath(__file__))
    
    def __new__(cls, *args, **kwargs):
        """Ensure that only one instance of WebControl exists (thread-safe)"""
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(WebControl, cls).__new__(cls)
            return cls._instance

    def __init__(self, sync_state, host="0.0.0.0", port=8080, secret="secret", logger=None):
        """Initialize the web control with improved error handling"""
        with self._lock:
            if not hasattr(self, "initialized"):  # Prevent re-initialization
                self.sync_state = sync_state
                self.port = port
                self.host = host
                self.secret = secret
                self.app = FastAPI(title="Sync Application API", 
                                  description="API for monitoring and controlling sync operations")
                self.templates = Jinja2Templates(directory=os.path.join(self.scriptdir, "templates"))
                
                # Set up proper logging
                if logger:
                    self.logger = logger
                else:
                    self.logger = logging.getLogger("webcontrol")
                    handler = logging.StreamHandler()
                    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
                    handler.setFormatter(formatter)
                    self.logger.addHandler(handler)
                    self.logger.setLevel(logging.INFO)
                
                self.setup_routes()
                self.initialized = True
                self.logger.info(f"Web control initialized. Host: {host}, Port: {port}")

    def setup_routes(self):
        """Configure all routes for the FastAPI app"""
        
        # Dependency for validating secret in header
        async def verify_secret_header(request: Request):
            if request.headers.get("secret") != self.secret:
                raise HTTPException(status_code=401, detail="Unauthorized: Invalid or missing secret in header")
            return True
        
        # Dependency for validating secret in query params
        async def verify_secret_query(secret: str = Query(...)):
            if secret != self.secret:
                raise HTTPException(status_code=401, detail="Unauthorized: Invalid secret")
            return True
        
        @self.app.get("/")
        async def list_routes():
            """List all available API routes"""
            routes = [{"path": route.path, "methods": route.methods,
                    "name": route.name} for route in self.app.routes]
            return {"routes": routes}
        
        @self.app.post("/add_to_global_server_lock")
        async def add_to_global_server_lock(request: ServerLockRequest, _: bool = Depends(verify_secret_header)):
            """Add a server to the global server locks"""
            try:
                with self._lock:
                    result = self.sync_state.add_to_global_server_locks(request.server, request.path)
                self.logger.info(f"Added server {request.server} to global locks. Path: {request.path}, Result: {result}")
                return {"status": result}
            except Exception as e:
                self.logger.error(f"Error adding to global server lock: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
        
        @self.app.post("/remove_from_global_server_lock")
        async def remove_from_global_server_lock(request: ServerLockRequest, _: bool = Depends(verify_secret_header)):
            """Remove a server from the global server locks"""
            try:
                with self._lock:
                    result = self.sync_state.remove_from_global_server_locks(request.server, request.path)
                self.logger.info(f"Removed server {request.server} from global locks. Path: {request.path}, Result: {result}")
                return {"status": result}
            except Exception as e:
                self.logger.error(f"Error removing from global server lock: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
        
        @self.app.post("/check_if_server_locked")
        async def check_if_server_locked(request: ServerLockRequest, _: bool = Depends(verify_secret_header)):
            """Check if a server is locked"""
            try:
                with self._lock:
                    result = self.sync_state.check_if_server_is_locked(request.server, request.path)
                return {"status": result}
            except Exception as e:
                self.logger.error(f"Error checking if server locked: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
        
        @self.app.get("/regular_pending")
        async def regular_pending(_: bool = Depends(verify_secret_header)):
            """Get regular pending files"""
            try:
                with self._lock:
                    files = self.sync_state.fs_monitor.get_regular_sync_files()
                return {"files": [str(f.path) for f in files]}
            except Exception as e:
                self.logger.error(f"Error getting regular pending files: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
        
        @self.app.get("/immediate_pending")
        async def immediate_pending(_: bool = Depends(verify_secret_header)):
            """Get immediate pending files"""
            try:
                with self._lock:
                    files = self.sync_state.fs_monitor.get_immediate_sync_files()
                return {"files": [str(f.path) for f in files]}
            except Exception as e:
                self.logger.error(f"Error getting immediate pending files: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
        
        @self.app.post("/delete_file_pending_for_path")
        async def delete_file_pending_for_path(request: FilePathRequest, _: bool = Depends(verify_secret_header)):
            """Delete file pending for path"""
            try:
                with self._lock:
                    self.sync_state.fs_monitor.delete_fs_event_for_path(request.path)
                self.logger.info(f"Deleted pending file for path: {request.path}")
                return {"status": "success"}
            except Exception as e:
                self.logger.error(f"Error deleting file pending for path: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
        
        @self.app.get("/locked_files")
        async def locked_files(_: bool = Depends(verify_secret_header)):
            """Get locked files"""
            try:
                with self._lock:
                    files = self.sync_state.fs_monitor.get_locked_files()
                return {"files": [str(f.path) for f in files]}
            except Exception as e:
                self.logger.error(f"Error getting locked files: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
        
        @self.app.get("/dashboard", response_class=HTMLResponse)
        async def dashboard(request: Request, secret: str = Query(None)):
            """Dashboard view with authentication and error handling"""
            try:
                if not secret or secret != self.secret:
                    # If secret is not provided or invalid, return template with `secret_provided` set to `False`
                    return self.templates.TemplateResponse("dashboard.html", {
                        "request": request,
                        "secret_provided": False
                    })
                
                result = []
                with self._lock:
                    for destination in self.sync_state.destinations:
                        result.append({
                            "destination": destination.get("path", ""),
                            "statistics": destination.get("statistics", {}),
                        })
                
                # Return template with data when secret is valid
                return self.templates.TemplateResponse("dashboard.html", {
                    "request": request,
                    "result": result,
                    "secret_provided": True,
                    "secret": secret
                })
            except Exception as e:
                self.logger.error(f"Error rendering dashboard: {str(e)}")
                return HTMLResponse(content=f"<html><body><h1>Error</h1><p>{str(e)}</p></body></html>", status_code=500)
        
        @self.app.get("/stats")
        async def stats(_: bool = Depends(verify_secret_query)):
            """Get statistics for all destinations"""
            try:
                result = []
                with self._lock:
                    for destination in self.sync_state.destinations:
                        result.append({
                            "destination": destination.get("path", ""),
                            "statistics": destination.get("statistics", {}),
                        })
                return {"result": result}  # Fixed: Now properly returns the result
            except Exception as e:
                self.logger.error(f"Error getting stats: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
        
        @self.app.get("/stats-running")
        async def stats_running(_: bool = Depends(verify_secret_query)):
            """Get detailed runtime statistics"""
            try:
                result = []
                
                with self._lock:
                    for destination in self.sync_state.destinations:
                        # Create a clean copy without circular references
                        dest_info = {
                            "destination": destination.get("path", ""),
                            "event_queue_limit": destination.get("event_queue_limit"),
                            "locked_on_sync": destination.get("locked_on_sync", False),
                            "use_global_server_lock": destination.get("use_global_server_lock", False),
                            "notify_file_locks": destination.get("notify_file_locks", False),
                            "remote_hostname": destination.get("remote_hostname"),
                            "max_wait_locked": destination.get("max_wait_locked"),
                        }
                        result.append(dest_info)
                    
                    # Get aggregate events in a clean format
                    aggregate_events = self.sync_state.fs_monitor.get_aggregated_events()
                    
                    # Convert complex objects to serializable strings where needed
                    server_locks = [
                        {
                            "server_name": lock.server_name,
                            "locked": lock.locked,
                            "server_initiated_lock": lock.server_initiated_lock,
                            "locked_date": str(lock.locked_date) if lock.locked_date else None,
                            "is_self": lock.is_self,
                            "path": lock.path
                        }
                        for lock in self.sync_state.global_server_locks
                    ]
                    
                    # Format other data for clean JSON output
                    return {
                        "result": result,
                        "remote_hosts": self.sync_state.remote_hosts,
                        "global_server_locks": server_locks,
                        "files_pending_regular": len(self.sync_state.files_to_delete_after_sync_regular),
                        "files_pending_immediate": len(self.sync_state.files_to_delete_after_sync_immediate),
                        "syncs_running_currently": self.sync_state.syncs_running_currently,
                        "max_stats": self.sync_state.max_stats,
                        "full_sync": self.sync_state.full_sync,
                        "aggregated_events": aggregate_events,
                    }
            except Exception as e:
                self.logger.error(f"Error getting runtime stats: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

    def run(self):
        """Run the web application with improved error handling"""
        try:
            self.logger.info(f"Starting web server on {self.host}:{self.port}")
            uvicorn.run(self.app, host=self.host, port=self.port)
        except Exception as e:
            self.logger.error(f"Error running web server: {str(e)}")
            raise

    def start(self):
        """Start the FastAPI app in a separate thread with improved logging"""
        thread = threading.Thread(target=self.run, daemon=True)
        thread.start()
        self.logger.info(f"FastAPI app is running in a thread on {self.host}:{self.port}")
        return thread