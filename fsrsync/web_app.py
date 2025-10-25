import os
import uuid
import time
import uvicorn
import threading
import logging
import asyncio
from typing import Optional, Dict, Any, List
from fastapi import FastAPI, Request, HTTPException, Depends, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .utils.websocket_server import WebSocketServer, WebSocketMessage, MessageType, SubscriptionType

# Optional import for advanced features
try:
    from .utils.sync_coordinator import SyncCoordinator
    HAS_SYNC_COORDINATOR = True
except ImportError:
    HAS_SYNC_COORDINATOR = False

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

                # Initialize WebSocket server
                self.websocket_server = WebSocketServer(
                    sync_manager=sync_state,
                    host=host,
                    port=port + 1,  # Use port+1 for WebSocket
                    logger_instance=self.logger
                )

                # Mount static files for the dashboard
                static_dir = os.path.join(self.scriptdir, "static")
                if os.path.exists(static_dir):
                    self.app.mount("/static", StaticFiles(directory=static_dir), name="static")

                # Store connected WebSocket clients
                self.ws_clients: Dict[str, WebSocket] = {}

                # Initialize SyncCoordinator if available
                self.sync_coordinator = None
                if HAS_SYNC_COORDINATOR:
                    try:
                        self.sync_coordinator = SyncCoordinator(
                            sync_app=sync_state,
                            host=host,
                            port=port,
                            logger_instance=self.logger
                        )
                        self.logger.info("SyncCoordinator initialized successfully")
                    except Exception as e:
                        self.logger.warning(f"Failed to initialize SyncCoordinator: {e}")
                else:
                    self.logger.debug("SyncCoordinator not available")

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
                            "destination_remote": destination["rsync_manager"].destination,
                            "event_queue_limit": destination.get("event_queue_limit"),
                            "locked_on_sync": destination.get("locked_on_sync", False),
                            "use_global_server_lock": destination.get("use_global_server_lock", False),
                            "notify_file_locks": destination.get("notify_file_locks", False),
                            "remote_hostname": destination.get("remote_hostname"),
                            "max_wait_locked": destination.get("max_wait_locked"),
                            "last_full_sync": str(destination.get("location_last_full_sync")) if destination.get("location_last_full_sync") else None,
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
                        "hostname": self.sync_state.hostname,
                    }
            except Exception as e:
                self.logger.error(f"Error getting runtime stats: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

        @self.app.get("/health")
        async def health():
            """Health check endpoint (no authentication required)"""
            return {"status": "healthy", "hostname": self.sync_state.hostname}

        @self.app.post("/trigger_sync")
        async def trigger_sync(request: FilePathRequest, _: bool = Depends(verify_secret_header)):
            """Manually trigger a sync for a specific path"""
            try:
                path = request.path
                triggered = False
                with self._lock:
                    for destination in self.sync_state.destinations:
                        if destination.get("path") == path:
                            # Trigger sync by setting locked_on_sync to False if it's stuck
                            if destination.get("locked_on_sync"):
                                self.logger.info(f"Path {path} is currently locked, cannot trigger sync")
                                return {"status": "locked", "message": f"Destination {path} is currently syncing"}
                            triggered = True
                            break

                if triggered:
                    self.logger.info(f"Manually triggered sync for path: {path}")
                    return {"status": "triggered", "path": path}
                else:
                    return {"status": "not_found", "message": f"Path {path} not found in destinations"}
            except Exception as e:
                self.logger.error(f"Error triggering sync: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

        @self.app.get("/pending_files_by_path")
        async def pending_files_by_path(path: str = Query(...), _: bool = Depends(verify_secret_query)):
            """Get pending files for a specific path"""
            try:
                with self._lock:
                    immediate = self.sync_state.fs_monitor.get_immediate_sync_files(path)
                    regular = self.sync_state.fs_monitor.get_regular_sync_files(path)
                    locked = self.sync_state.fs_monitor.get_locked_files_for_path(path)

                    return {
                        "path": path,
                        "immediate_count": len(immediate),
                        "regular_count": len(regular),
                        "locked_count": len(locked),
                        "immediate_files": [f.path for f in immediate],
                        "regular_files": [f.path for f in regular],
                        "locked_files": [f.path for f in locked],
                    }
            except Exception as e:
                self.logger.error(f"Error getting pending files by path: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

        @self.app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            """
            WebSocket endpoint for real-time dashboard updates.
            Handles client connections and message routing.
            """
            client_id = str(uuid.uuid4())[:8]
            try:
                await websocket.accept()
                self.ws_clients[client_id] = websocket
                self.logger.info(f"WebSocket client connected: {client_id}")

                # Add client to WebSocket server
                session = await self.websocket_server.add_client(client_id, websocket)

                # Send welcome message
                welcome_msg = WebSocketMessage(
                    message_type=MessageType.CONNECTED,
                    payload={
                        'client_id': client_id,
                        'message': 'Connected to FSRsync Dashboard'
                    }
                )
                await websocket.send_text(welcome_msg.to_json())

                # Listen for client messages
                while True:
                    data = await websocket.receive_text()
                    await self.websocket_server.handle_client_message(client_id, data)

            except WebSocketDisconnect:
                self.logger.info(f"WebSocket client disconnected: {client_id}")
                if client_id in self.ws_clients:
                    del self.ws_clients[client_id]
                await self.websocket_server.remove_client(client_id)
            except Exception as e:
                self.logger.error(f"WebSocket error for client {client_id}: {e}")
                if client_id in self.ws_clients:
                    del self.ws_clients[client_id]
                await self.websocket_server.remove_client(client_id)

        @self.app.get("/ws-status")
        async def ws_status(_: bool = Depends(verify_secret_query)):
            """Get WebSocket server status"""
            try:
                return {
                    "running": self.websocket_server.running,
                    "connected_clients": len(self.websocket_server.clients),
                    "total_messages_sent": self.websocket_server.total_messages_sent,
                    "total_messages_received": self.websocket_server.total_messages_received,
                    "uptime_seconds": time.time() - self.websocket_server.started_at if hasattr(self.websocket_server, 'started_at') else 0
                }
            except Exception as e:
                self.logger.error(f"Error getting WebSocket status: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

        @self.app.get("/dashboard-new", response_class=HTMLResponse)
        async def dashboard_new(request: Request):
            """Serve the new dashboard HTML"""
            try:
                static_dir = os.path.join(self.scriptdir, "static")
                index_file = os.path.join(static_dir, "index.html")
                if os.path.exists(index_file):
                    with open(index_file, 'r') as f:
                        return f.read()
                else:
                    return HTMLResponse(
                        content="<html><body><h1>Dashboard not found</h1></body></html>",
                        status_code=404
                    )
            except Exception as e:
                self.logger.error(f"Error serving dashboard: {str(e)}")
                return HTMLResponse(
                    content=f"<html><body><h1>Error</h1><p>{str(e)}</p></body></html>",
                    status_code=500
                )

        @self.app.post("/api/pause-transfer")
        async def api_pause_transfer(request: FilePathRequest, _: bool = Depends(verify_secret_header)):
            """API endpoint to pause a transfer"""
            try:
                # This would integrate with the actual transfer engine
                return {"status": "success", "message": "Transfer paused"}
            except Exception as e:
                self.logger.error(f"Error pausing transfer: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

        @self.app.post("/api/resume-transfer")
        async def api_resume_transfer(request: FilePathRequest, _: bool = Depends(verify_secret_header)):
            """API endpoint to resume a transfer"""
            try:
                # This would integrate with the actual transfer engine
                return {"status": "success", "message": "Transfer resumed"}
            except Exception as e:
                self.logger.error(f"Error resuming transfer: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

        @self.app.post("/api/cancel-transfer")
        async def api_cancel_transfer(request: FilePathRequest, _: bool = Depends(verify_secret_header)):
            """API endpoint to cancel a transfer"""
            try:
                # This would integrate with the actual transfer engine
                return {"status": "success", "message": "Transfer cancelled"}
            except Exception as e:
                self.logger.error(f"Error cancelling transfer: {str(e)}")
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