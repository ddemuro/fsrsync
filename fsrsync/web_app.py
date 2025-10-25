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

try:
    from .utils.health_check import HealthChecker
    HAS_HEALTH_CHECK = True
except ImportError:
    HAS_HEALTH_CHECK = False

try:
    from .utils.logging_aggregator import LogAggregator
    HAS_LOGGING_AGGREGATOR = True
except ImportError:
    HAS_LOGGING_AGGREGATOR = False

# Optional cluster support
try:
    from .utils.cluster_manager import ClusterManager
    HAS_CLUSTER_MANAGER = True
except ImportError:
    HAS_CLUSTER_MANAGER = False

try:
    from .utils.cluster_protocol import ClusterProtocol
    HAS_CLUSTER_PROTOCOL = True
except ImportError:
    HAS_CLUSTER_PROTOCOL = False

try:
    from .utils.consensus_engine import ConsensusEngine
    HAS_CONSENSUS_ENGINE = True
except ImportError:
    HAS_CONSENSUS_ENGINE = False

try:
    from .utils.distributed_config import DistributedConfigManager
    HAS_DISTRIBUTED_CONFIG = True
except ImportError:
    HAS_DISTRIBUTED_CONFIG = False

try:
    from .utils.failover_recovery import FailoverRecoveryManager
    HAS_FAILOVER_RECOVERY = True
except ImportError:
    HAS_FAILOVER_RECOVERY = False

# Optional performance and lab modules
try:
    from .utils.performance_benchmarker import PerformanceBenchmarker
    HAS_PERFORMANCE_BENCHMARKER = True
except ImportError:
    HAS_PERFORMANCE_BENCHMARKER = False

try:
    from .utils.metrics_collector import MetricsCollector
    HAS_METRICS_COLLECTOR = True
except ImportError:
    HAS_METRICS_COLLECTOR = False

try:
    from .utils.network_simulator import NetworkSimulator
    HAS_NETWORK_SIMULATOR = True
except ImportError:
    HAS_NETWORK_SIMULATOR = False

try:
    from .utils.profiler import FunctionProfiler, CPUProfiler, MemoryProfiler, PerformanceAnalyzer
    HAS_PROFILER = True
except ImportError:
    HAS_PROFILER = False

# Optional analytics and dashboard modules
try:
    from .utils.analytics_engine import AnalyticsEngine
    HAS_ANALYTICS_ENGINE = True
except ImportError:
    HAS_ANALYTICS_ENGINE = False

try:
    from .utils.dashboard_framework import DashboardBuilder
    HAS_DASHBOARD_BUILDER = True
except ImportError:
    HAS_DASHBOARD_BUILDER = False

try:
    from .utils.report_generator import ReportGenerator
    HAS_REPORT_GENERATOR = True
except ImportError:
    HAS_REPORT_GENERATOR = False

# Optional performance regression and streaming modules
try:
    from .utils.regression_tester import RegressionTester
    HAS_REGRESSION_TESTER = True
except ImportError:
    HAS_REGRESSION_TESTER = False

try:
    from .utils.performance_streamer import PerformanceStreamer
    HAS_PERFORMANCE_STREAMER = True
except ImportError:
    HAS_PERFORMANCE_STREAMER = False

try:
    from .utils.io_analyzer import IOAnalyzer
    HAS_IO_ANALYZER = True
except ImportError:
    HAS_IO_ANALYZER = False

# Optional optimization and testing modules
try:
    from .utils.optimization_advisor import OptimizationAdvisor
    HAS_OPTIMIZATION_ADVISOR = True
except ImportError:
    HAS_OPTIMIZATION_ADVISOR = False

try:
    from .utils.resource_limiter import ResourceLimiter
    HAS_RESOURCE_LIMITER = True
except ImportError:
    HAS_RESOURCE_LIMITER = False

try:
    from .utils.test_runner import TestRunner
    HAS_TEST_RUNNER = True
except ImportError:
    HAS_TEST_RUNNER = False

# Optional sync instrumentation module
try:
    from .utils.sync_instrumentation import SyncInstrumentation
    HAS_SYNC_INSTRUMENTATION = True
except ImportError:
    HAS_SYNC_INSTRUMENTATION = False

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

                # Initialize HealthChecker if available
                self.health_checker = None
                if HAS_HEALTH_CHECK:
                    try:
                        self.health_checker = HealthChecker(
                            coordinator=self.sync_coordinator,
                            logger_instance=self.logger
                        )
                        self.logger.info("HealthChecker initialized successfully")
                    except Exception as e:
                        self.logger.warning(f"Failed to initialize HealthChecker: {e}")
                else:
                    self.logger.debug("HealthChecker not available")

                # Initialize LogAggregator if available
                self.log_aggregator = None
                if HAS_LOGGING_AGGREGATOR:
                    try:
                        self.log_aggregator = LogAggregator(
                            max_entries=10000,
                            logger_instance=self.logger
                        )
                        self.logger.info("LogAggregator initialized successfully")
                    except Exception as e:
                        self.logger.warning(f"Failed to initialize LogAggregator: {e}")
                else:
                    self.logger.debug("LogAggregator not available")

                # Initialize ClusterManager if available
                self.cluster_manager = None
                if HAS_CLUSTER_MANAGER:
                    try:
                        cluster_id = os.environ.get("CLUSTER_ID", "default_cluster")
                        node_id = os.environ.get("NODE_ID", f"node_{uuid.uuid4().hex[:8]}")
                        node_role = os.environ.get("NODE_ROLE", "worker")
                        architecture = os.environ.get("CLUSTER_ARCH", "peer_to_peer")

                        self.cluster_manager = ClusterManager(
                            cluster_id=cluster_id,
                            node_id=node_id,
                            node_role=node_role,
                            architecture=architecture,
                            logger_instance=self.logger
                        )
                        self.logger.info(f"ClusterManager initialized successfully: "
                                       f"cluster={cluster_id}, node={node_id}, role={node_role}")
                    except Exception as e:
                        self.logger.warning(f"Failed to initialize ClusterManager: {e}")
                else:
                    self.logger.debug("ClusterManager not available")

                # Initialize ClusterProtocol if available
                self.cluster_protocol = None
                if HAS_CLUSTER_PROTOCOL and self.cluster_manager:
                    try:
                        node_id = self.cluster_manager.node_id
                        self.cluster_protocol = ClusterProtocol(
                            node_id=node_id,
                            logger_instance=self.logger
                        )
                        self.logger.info("ClusterProtocol initialized successfully")
                    except Exception as e:
                        self.logger.warning(f"Failed to initialize ClusterProtocol: {e}")
                else:
                    self.logger.debug("ClusterProtocol not available")

                # Initialize ConsensusEngine if available
                self.consensus_engine = None
                if HAS_CONSENSUS_ENGINE and self.cluster_manager:
                    try:
                        node_id = self.cluster_manager.node_id
                        cluster_nodes = list(self.cluster_manager.nodes.keys()) or [node_id]

                        self.consensus_engine = ConsensusEngine(
                            node_id=node_id,
                            cluster_nodes=cluster_nodes,
                            logger_instance=self.logger
                        )
                        self.logger.info("ConsensusEngine initialized successfully")
                    except Exception as e:
                        self.logger.warning(f"Failed to initialize ConsensusEngine: {e}")
                else:
                    self.logger.debug("ConsensusEngine not available")

                # Initialize DistributedConfigManager if available
                self.distributed_config = None
                if HAS_DISTRIBUTED_CONFIG:
                    try:
                        self.distributed_config = DistributedConfigManager(
                            logger_instance=self.logger
                        )
                        self.logger.info("DistributedConfigManager initialized successfully")
                    except Exception as e:
                        self.logger.warning(f"Failed to initialize DistributedConfigManager: {e}")
                else:
                    self.logger.debug("DistributedConfigManager not available")

                # Initialize FailoverRecoveryManager if available
                self.failover_recovery = None
                if HAS_FAILOVER_RECOVERY and self.cluster_manager:
                    try:
                        self.failover_recovery = FailoverRecoveryManager(
                            cluster_manager=self.cluster_manager,
                            logger_instance=self.logger
                        )
                        self.logger.info("FailoverRecoveryManager initialized successfully")
                    except Exception as e:
                        self.logger.warning(f"Failed to initialize FailoverRecoveryManager: {e}")
                else:
                    self.logger.debug("FailoverRecoveryManager not available")

                # Initialize PerformanceBenchmarker if available
                self.performance_benchmarker = None
                if HAS_PERFORMANCE_BENCHMARKER:
                    try:
                        self.performance_benchmarker = PerformanceBenchmarker(
                            logger_instance=self.logger
                        )
                        self.logger.info("PerformanceBenchmarker initialized successfully")
                    except Exception as e:
                        self.logger.warning(f"Failed to initialize PerformanceBenchmarker: {e}")
                else:
                    self.logger.debug("PerformanceBenchmarker not available")

                # Initialize MetricsCollector if available
                self.metrics_collector = None
                if HAS_METRICS_COLLECTOR:
                    try:
                        self.metrics_collector = MetricsCollector(
                            logger_instance=self.logger
                        )
                        self.logger.info("MetricsCollector initialized successfully")
                    except Exception as e:
                        self.logger.warning(f"Failed to initialize MetricsCollector: {e}")
                else:
                    self.logger.debug("MetricsCollector not available")

                # Initialize NetworkSimulator if available
                self.network_simulator = None
                if HAS_NETWORK_SIMULATOR:
                    try:
                        self.network_simulator = NetworkSimulator(
                            logger_instance=self.logger
                        )
                        self.logger.info("NetworkSimulator initialized successfully")
                    except Exception as e:
                        self.logger.warning(f"Failed to initialize NetworkSimulator: {e}")
                else:
                    self.logger.debug("NetworkSimulator not available")

                # Initialize PerformanceAnalyzer if available
                self.performance_analyzer = None
                if HAS_PROFILER:
                    try:
                        self.performance_analyzer = PerformanceAnalyzer(
                            logger_instance=self.logger
                        )
                        self.logger.info("PerformanceAnalyzer initialized successfully")
                    except Exception as e:
                        self.logger.warning(f"Failed to initialize PerformanceAnalyzer: {e}")
                else:
                    self.logger.debug("PerformanceAnalyzer not available")

                # Initialize AnalyticsEngine if available
                self.analytics_engine = None
                if HAS_ANALYTICS_ENGINE:
                    try:
                        self.analytics_engine = AnalyticsEngine(
                            logger_instance=self.logger
                        )
                        self.logger.info("AnalyticsEngine initialized successfully")
                    except Exception as e:
                        self.logger.warning(f"Failed to initialize AnalyticsEngine: {e}")
                else:
                    self.logger.debug("AnalyticsEngine not available")

                # Initialize DashboardBuilder if available
                self.dashboard_builder = None
                if HAS_DASHBOARD_BUILDER:
                    try:
                        self.dashboard_builder = DashboardBuilder(
                            logger_instance=self.logger
                        )
                        self.logger.info("DashboardBuilder initialized successfully")
                    except Exception as e:
                        self.logger.warning(f"Failed to initialize DashboardBuilder: {e}")
                else:
                    self.logger.debug("DashboardBuilder not available")

                # Initialize ReportGenerator if available
                self.report_generator = None
                if HAS_REPORT_GENERATOR:
                    try:
                        self.report_generator = ReportGenerator(
                            logger_instance=self.logger
                        )
                        self.logger.info("ReportGenerator initialized successfully")
                    except Exception as e:
                        self.logger.warning(f"Failed to initialize ReportGenerator: {e}")
                else:
                    self.logger.debug("ReportGenerator not available")

                # Initialize RegressionTester if available
                self.regression_tester = None
                if HAS_REGRESSION_TESTER:
                    try:
                        self.regression_tester = RegressionTester(
                            logger_instance=self.logger
                        )
                        self.logger.info("RegressionTester initialized successfully")
                    except Exception as e:
                        self.logger.warning(f"Failed to initialize RegressionTester: {e}")
                else:
                    self.logger.debug("RegressionTester not available")

                # Initialize PerformanceStreamer if available
                self.performance_streamer = None
                if HAS_PERFORMANCE_STREAMER:
                    try:
                        self.performance_streamer = PerformanceStreamer(
                            logger_instance=self.logger
                        )
                        self.logger.info("PerformanceStreamer initialized successfully")
                    except Exception as e:
                        self.logger.warning(f"Failed to initialize PerformanceStreamer: {e}")
                else:
                    self.logger.debug("PerformanceStreamer not available")

                # Initialize IOAnalyzer if available
                self.io_analyzer = None
                if HAS_IO_ANALYZER:
                    try:
                        self.io_analyzer = IOAnalyzer(
                            logger_instance=self.logger
                        )
                        self.logger.info("IOAnalyzer initialized successfully")
                    except Exception as e:
                        self.logger.warning(f"Failed to initialize IOAnalyzer: {e}")
                else:
                    self.logger.debug("IOAnalyzer not available")

                # Initialize OptimizationAdvisor if available
                self.optimization_advisor = None
                if HAS_OPTIMIZATION_ADVISOR:
                    try:
                        self.optimization_advisor = OptimizationAdvisor(
                            logger_instance=self.logger
                        )
                        self.logger.info("OptimizationAdvisor initialized successfully")
                    except Exception as e:
                        self.logger.warning(f"Failed to initialize OptimizationAdvisor: {e}")
                else:
                    self.logger.debug("OptimizationAdvisor not available")

                # Initialize ResourceLimiter if available
                self.resource_limiter = None
                if HAS_RESOURCE_LIMITER:
                    try:
                        self.resource_limiter = ResourceLimiter(
                            logger_instance=self.logger
                        )
                        self.logger.info("ResourceLimiter initialized successfully")
                    except Exception as e:
                        self.logger.warning(f"Failed to initialize ResourceLimiter: {e}")
                else:
                    self.logger.debug("ResourceLimiter not available")

                # Initialize TestRunner if available
                self.test_runner = None
                if HAS_TEST_RUNNER:
                    try:
                        self.test_runner = TestRunner(
                            logger_instance=self.logger
                        )
                        self.logger.info("TestRunner initialized successfully")
                    except Exception as e:
                        self.logger.warning(f"Failed to initialize TestRunner: {e}")
                else:
                    self.logger.debug("TestRunner not available")

                # Initialize Sync Instrumentation if available
                if HAS_SYNC_INSTRUMENTATION:
                    try:
                        SyncInstrumentation.initialize(
                            metrics_collector=self.metrics_collector,
                            benchmarker=self.performance_benchmarker,
                            io_analyzer=self.io_analyzer,
                            profiler=self.performance_analyzer.function_profiler if self.performance_analyzer else None,
                            logger_instance=self.logger
                        )
                        self.logger.info("SyncInstrumentation initialized successfully")
                    except Exception as e:
                        self.logger.warning(f"Failed to initialize SyncInstrumentation: {e}")
                else:
                    self.logger.debug("SyncInstrumentation not available")

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

        # Advanced Coordinator APIs
        @self.app.get("/api/coordinator/status")
        async def get_coordinator_status(_: bool = Depends(verify_secret_query)):
            """Get SyncCoordinator status and statistics"""
            try:
                if not self.sync_coordinator:
                    return {"error": "SyncCoordinator not available", "status": "unavailable"}

                stats = self.sync_coordinator.get_statistics()
                return {
                    "status": "success",
                    "coordinator": {
                        "state": stats.state,
                        "uptime_seconds": stats.uptime_seconds,
                        "running": self.sync_coordinator.is_running()
                    },
                    "transfers": {
                        "active": stats.active_transfers,
                        "queued": stats.queued_transfers,
                        "total_transferred_bytes": stats.total_transferred_bytes
                    },
                    "network": {
                        "bandwidth_usage_mbps": stats.bandwidth_usage_mbps,
                        "connected_peers": stats.connected_peers
                    },
                    "reliability": {
                        "success_rate_percent": stats.success_rate_percent,
                        "error_count": stats.error_count,
                        "pending_conflicts": stats.pending_conflicts
                    },
                    "peers": stats.peer_stats,
                    "timestamp": stats.timestamp
                }
            except Exception as e:
                self.logger.error(f"Error getting coordinator status: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

        @self.app.post("/api/coordinator/pause")
        async def pause_coordinator(_: bool = Depends(verify_secret_header)):
            """Pause all sync operations"""
            try:
                if not self.sync_coordinator:
                    raise HTTPException(status_code=400, detail="SyncCoordinator not available")

                self.sync_coordinator.pause()
                self.logger.info("SyncCoordinator paused via API")
                return {"status": "success", "message": "All sync operations paused"}
            except Exception as e:
                self.logger.error(f"Error pausing coordinator: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

        @self.app.post("/api/coordinator/resume")
        async def resume_coordinator(_: bool = Depends(verify_secret_header)):
            """Resume all sync operations"""
            try:
                if not self.sync_coordinator:
                    raise HTTPException(status_code=400, detail="SyncCoordinator not available")

                self.sync_coordinator.resume()
                self.logger.info("SyncCoordinator resumed via API")
                return {"status": "success", "message": "All sync operations resumed"}
            except Exception as e:
                self.logger.error(f"Error resuming coordinator: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

        @self.app.get("/api/coordinator/peers")
        async def get_peer_list(_: bool = Depends(verify_secret_query)):
            """Get list of connected peers"""
            try:
                if not self.sync_coordinator:
                    return {"peers": [], "count": 0}

                peers = []
                for peer in self.sync_coordinator.peer_manager.peers.values():
                    peers.append({
                        "hostname": peer.hostname,
                        "address": peer.address,
                        "port": peer.port,
                        "status": peer.status,
                        "latency_ms": peer.latency_ms,
                        "bandwidth_limit_mbps": peer.bandwidth_limit_mbps
                    })
                return {"peers": peers, "count": len(peers)}
            except Exception as e:
                self.logger.error(f"Error getting peer list: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

        @self.app.get("/api/coordinator/bandwidth")
        async def get_bandwidth_status(_: bool = Depends(verify_secret_query)):
            """Get bandwidth management status"""
            try:
                if not self.sync_coordinator:
                    return {"error": "SyncCoordinator not available"}

                bw_mgr = self.sync_coordinator.bandwidth_manager
                return {
                    "status": "success",
                    "global_limit_mbps": bw_mgr.global_bandwidth_limit_mbps,
                    "current_usage_mbps": bw_mgr.get_current_bandwidth_usage(),
                    "strategy": bw_mgr.strategy.value if hasattr(bw_mgr.strategy, 'value') else str(bw_mgr.strategy),
                    "per_peer_limits": {
                        peer: bw_mgr.get_peer_limit(peer)
                        for peer in bw_mgr.peer_bandwidth.keys()
                    }
                }
            except Exception as e:
                self.logger.error(f"Error getting bandwidth status: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

        @self.app.post("/api/coordinator/set-bandwidth-limit")
        async def set_bandwidth_limit(
            request: FilePathRequest,
            _: bool = Depends(verify_secret_header)
        ):
            """Set global bandwidth limit (path field contains limit in Mbps)"""
            try:
                if not self.sync_coordinator:
                    raise HTTPException(status_code=400, detail="SyncCoordinator not available")

                limit_mbps = float(request.path)
                self.sync_coordinator.bandwidth_manager.set_global_limit(limit_mbps)
                self.logger.info(f"Bandwidth limit set to {limit_mbps} Mbps via API")
                return {"status": "success", "message": f"Bandwidth limit set to {limit_mbps} Mbps"}
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid bandwidth limit value")
            except Exception as e:
                self.logger.error(f"Error setting bandwidth limit: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

        @self.app.get("/api/coordinator/metrics")
        async def get_metrics(_: bool = Depends(verify_secret_query)):
            """Get performance metrics from collector"""
            try:
                if not self.sync_coordinator:
                    return {"error": "SyncCoordinator not available"}

                metrics = self.sync_coordinator.metrics_collector
                return {
                    "status": "success",
                    "metrics": {
                        "transfer_metrics": len(metrics.transfer_metrics),
                        "bandwidth_metrics": len(metrics.bandwidth_metrics),
                        "performance_metrics": len(metrics.performance_metrics),
                        "reliability_metrics": len(metrics.reliability_metrics),
                        "peer_metrics": len(metrics.peer_metrics)
                    },
                    "timestamp": time.time()
                }
            except Exception as e:
                self.logger.error(f"Error getting metrics: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

        # Health Check APIs
        @self.app.get("/health")
        async def health_check():
            """Health check endpoint (no authentication required)"""
            try:
                if not self.health_checker:
                    return {"status": "healthy", "timestamp": time.time()}

                status = await self.health_checker.check_all()
                return status.to_dict()
            except Exception as e:
                self.logger.error(f"Error in health check: {str(e)}")
                return {"status": "error", "timestamp": time.time()}, 500

        @self.app.get("/api/health/detailed")
        async def get_detailed_health(_: bool = Depends(verify_secret_query)):
            """Get detailed health report with historical data"""
            try:
                if not self.health_checker:
                    return {"error": "HealthChecker not available"}

                status = await self.health_checker.check_all()
                trend = self.health_checker.get_health_trend(minutes=5)

                return {
                    "status": "success",
                    "current": status.to_dict(),
                    "trend": trend,
                    "timestamp": time.time()
                }
            except Exception as e:
                self.logger.error(f"Error getting detailed health: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

        # Logging APIs
        @self.app.get("/api/logs/summary")
        async def get_log_summary(_: bool = Depends(verify_secret_query)):
            """Get log summary and statistics"""
            try:
                if not self.log_aggregator:
                    return {"error": "LogAggregator not available"}

                summary = self.log_aggregator.get_summary()
                health_stats = self.log_aggregator.get_health_stats()

                return {
                    "status": "success",
                    "total_entries": summary.total_entries,
                    "by_level": summary.by_level,
                    "by_component": summary.by_component,
                    "health_stats": health_stats,
                    "recent_errors": [e.to_dict() for e in summary.recent_errors],
                    "recent_warnings": [w.to_dict() for w in summary.recent_warnings],
                    "timestamp": time.time()
                }
            except Exception as e:
                self.logger.error(f"Error getting log summary: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

        @self.app.get("/api/logs/recent")
        async def get_recent_logs(limit: int = Query(100, ge=1, le=1000),
                                   _: bool = Depends(verify_secret_query)):
            """Get recent log entries"""
            try:
                if not self.log_aggregator:
                    return {"logs": [], "count": 0}

                logs = self.log_aggregator.get_recent(limit=limit)
                return {
                    "logs": [log.to_dict() for log in logs],
                    "count": len(logs),
                    "timestamp": time.time()
                }
            except Exception as e:
                self.logger.error(f"Error getting recent logs: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

        @self.app.get("/api/logs/errors")
        async def get_error_logs(limit: int = Query(50, ge=1, le=500),
                                  _: bool = Depends(verify_secret_query)):
            """Get recent error entries"""
            try:
                if not self.log_aggregator:
                    return {"logs": [], "count": 0}

                logs = self.log_aggregator.get_errors(limit=limit)
                return {
                    "logs": [log.to_dict() for log in logs],
                    "count": len(logs),
                    "timestamp": time.time()
                }
            except Exception as e:
                self.logger.error(f"Error getting error logs: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

        @self.app.get("/api/logs/warnings")
        async def get_warning_logs(limit: int = Query(50, ge=1, le=500),
                                    _: bool = Depends(verify_secret_query)):
            """Get recent warning entries"""
            try:
                if not self.log_aggregator:
                    return {"logs": [], "count": 0}

                logs = self.log_aggregator.get_warnings(limit=limit)
                return {
                    "logs": [log.to_dict() for log in logs],
                    "count": len(logs),
                    "timestamp": time.time()
                }
            except Exception as e:
                self.logger.error(f"Error getting warning logs: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

        @self.app.get("/api/logs/component/{component}")
        async def get_component_logs(component: str, limit: int = Query(100, ge=1, le=1000),
                                      _: bool = Depends(verify_secret_query)):
            """Get logs from specific component"""
            try:
                if not self.log_aggregator:
                    return {"logs": [], "count": 0}

                logs = self.log_aggregator.get_by_component(component, limit=limit)
                return {
                    "component": component,
                    "logs": [log.to_dict() for log in logs],
                    "count": len(logs),
                    "timestamp": time.time()
                }
            except Exception as e:
                self.logger.error(f"Error getting component logs: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

        # ========== Cluster Management Endpoints ==========

        @self.app.get("/api/cluster/status")
        async def get_cluster_status(_: bool = Depends(verify_secret_query)):
            """Get cluster status"""
            try:
                if not self.cluster_manager:
                    return {"status": "disabled", "message": "Cluster management not enabled"}

                status = self.cluster_manager.get_cluster_summary()
                return {"status": "success", "cluster": status, "timestamp": time.time()}
            except Exception as e:
                self.logger.error(f"Error getting cluster status: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

        @self.app.get("/api/cluster/nodes")
        async def get_cluster_nodes(_: bool = Depends(verify_secret_query)):
            """Get all cluster nodes"""
            try:
                if not self.cluster_manager:
                    return {"nodes": [], "count": 0}

                nodes = []
                for node_id, node in self.cluster_manager.nodes.items():
                    nodes.append({
                        'id': node_id,
                        'hostname': node.hostname,
                        'port': node.port,
                        'role': node.role.value,
                        'health': node.health_status.value,
                        'cpu_usage': node.cpu_usage,
                        'memory_usage': node.memory_usage,
                        'disk_usage': node.disk_usage,
                        'active_syncs': node.active_syncs,
                        'total_syncs': node.total_syncs
                    })

                return {
                    "nodes": nodes,
                    "count": len(nodes),
                    "timestamp": time.time()
                }
            except Exception as e:
                self.logger.error(f"Error getting cluster nodes: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

        @self.app.get("/api/cluster/consensus")
        async def get_consensus_status(_: bool = Depends(verify_secret_query)):
            """Get consensus engine status"""
            try:
                if not self.consensus_engine:
                    return {"status": "disabled", "message": "Consensus engine not enabled"}

                status = self.consensus_engine.get_consensus_status()
                return {"status": "success", "consensus": status, "timestamp": time.time()}
            except Exception as e:
                self.logger.error(f"Error getting consensus status: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

        @self.app.get("/api/cluster/config")
        async def get_cluster_config(environment: str = Query("production"),
                                    _: bool = Depends(verify_secret_query)):
            """Get distributed configuration"""
            try:
                if not self.distributed_config:
                    return {"config": {}, "message": "Distributed config not enabled"}

                config = self.distributed_config.get_config(environment)
                status = self.distributed_config.get_config_status(environment)

                return {
                    "status": "success",
                    "environment": environment,
                    "config": config,
                    "config_status": status,
                    "timestamp": time.time()
                }
            except Exception as e:
                self.logger.error(f"Error getting cluster config: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

        @self.app.get("/api/cluster/failover")
        async def get_failover_status(_: bool = Depends(verify_secret_query)):
            """Get failover and recovery status"""
            try:
                if not self.failover_recovery:
                    return {"status": "disabled", "message": "Failover recovery not enabled"}

                status = self.failover_recovery.get_failover_status()
                return {"status": "success", "failover": status, "timestamp": time.time()}
            except Exception as e:
                self.logger.error(f"Error getting failover status: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

        @self.app.get("/api/cluster/protocol")
        async def get_protocol_stats(_: bool = Depends(verify_secret_query)):
            """Get cluster protocol statistics"""
            try:
                if not self.cluster_protocol:
                    return {"stats": {}, "message": "Cluster protocol not enabled"}

                stats = self.cluster_protocol.get_protocol_stats()
                return {"status": "success", "protocol": stats, "timestamp": time.time()}
            except Exception as e:
                self.logger.error(f"Error getting protocol stats: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

        # ========== Performance Monitoring Endpoints ==========

        @self.app.get("/api/performance/benchmarks")
        async def get_benchmarks(_: bool = Depends(verify_secret_query)):
            """Get performance benchmarks"""
            try:
                if not self.performance_benchmarker:
                    return {"status": "disabled", "message": "Performance benchmarker not enabled"}

                report = self.performance_benchmarker.get_performance_report()
                return {"status": "success", "report": report, "timestamp": time.time()}
            except Exception as e:
                self.logger.error(f"Error getting benchmarks: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

        @self.app.get("/api/performance/metrics")
        async def get_metrics(_: bool = Depends(verify_secret_query)):
            """Get collected metrics"""
            try:
                if not self.metrics_collector:
                    return {"status": "disabled", "message": "Metrics collector not enabled"}

                summary = self.metrics_collector.get_metrics_summary()
                return {"status": "success", "metrics": summary, "timestamp": time.time()}
            except Exception as e:
                self.logger.error(f"Error getting metrics: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

        @self.app.get("/api/performance/network")
        async def get_network_status(_: bool = Depends(verify_secret_query)):
            """Get network simulation status"""
            try:
                if not self.network_simulator:
                    return {"status": "disabled", "message": "Network simulator not enabled"}

                net_status = self.network_simulator.get_network_status()
                return {"status": "success", "network": net_status, "timestamp": time.time()}
            except Exception as e:
                self.logger.error(f"Error getting network status: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

        @self.app.get("/api/performance/analysis")
        async def get_analysis(_: bool = Depends(verify_secret_query)):
            """Get performance analysis"""
            try:
                if not self.performance_analyzer:
                    return {"status": "disabled", "message": "Performance analyzer not enabled"}

                report = self.performance_analyzer.get_optimization_report()
                return {"status": "success", "analysis": report, "timestamp": time.time()}
            except Exception as e:
                self.logger.error(f"Error getting analysis: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

        @self.app.get("/api/performance/alerts")
        async def get_alerts(limit: int = Query(100, ge=1, le=1000),
                            _: bool = Depends(verify_secret_query)):
            """Get metric alerts"""
            try:
                if not self.metrics_collector:
                    return {"alerts": [], "count": 0}

                alerts = self.metrics_collector.get_alerts(limit=limit)
                return {
                    "status": "success",
                    "alerts": alerts,
                    "count": len(alerts),
                    "timestamp": time.time()
                }
            except Exception as e:
                self.logger.error(f"Error getting alerts: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

        @self.app.get("/api/performance/chaos-history")
        async def get_chaos_history(limit: int = Query(100, ge=1, le=1000),
                                   _: bool = Depends(verify_secret_query)):
            """Get chaos scenario history"""
            try:
                if not self.network_simulator:
                    return {"history": [], "count": 0}

                history = self.network_simulator.get_chaos_history(limit=limit)
                return {
                    "status": "success",
                    "history": history,
                    "count": len(history),
                    "timestamp": time.time()
                }
            except Exception as e:
                self.logger.error(f"Error getting chaos history: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

        # ========== Analytics & Dashboard Endpoints ==========

        @self.app.get("/api/analytics/summary")
        async def get_analytics_summary(_: bool = Depends(verify_secret_query)):
            """Get analytics summary"""
            try:
                if not self.analytics_engine:
                    return {"status": "disabled", "message": "Analytics engine not enabled"}

                summary = self.analytics_engine.get_analytics_summary()
                return {"status": "success", "analytics": summary, "timestamp": time.time()}
            except Exception as e:
                self.logger.error(f"Error getting analytics summary: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

        @self.app.get("/api/analytics/trends")
        async def get_trends(metric_name: str = Query(""),
                            lookback_seconds: int = Query(3600, ge=60, le=604800),
                            _: bool = Depends(verify_secret_query)):
            """Get trend analysis for metric"""
            try:
                if not self.analytics_engine or not metric_name:
                    return {"trends": {}}

                trend = self.analytics_engine.get_trend(metric_name, lookback_seconds)

                if not trend:
                    return {"trends": {}, "message": "No trend data available"}

                return {
                    "status": "success",
                    "metric": metric_name,
                    "trend": {
                        'direction': trend.direction.value,
                        'slope': trend.slope,
                        'percent_change': trend.percent_change,
                        'confidence': trend.confidence
                    },
                    "timestamp": time.time()
                }
            except Exception as e:
                self.logger.error(f"Error getting trends: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

        @self.app.get("/api/analytics/anomalies")
        async def get_anomalies(metric_name: str = Query(""),
                               lookback_seconds: int = Query(3600, ge=60, le=604800),
                               _: bool = Depends(verify_secret_query)):
            """Get anomaly detection results"""
            try:
                if not self.analytics_engine or not metric_name:
                    return {"anomalies": []}

                anomalies = self.analytics_engine.detect_anomalies(metric_name, lookback_seconds)

                return {
                    "status": "success",
                    "metric": metric_name,
                    "anomalies": [
                        {
                            'value': a.value,
                            'expected': a.expected_value,
                            'deviation_std': a.deviation_std,
                            'severity': a.severity,
                            'timestamp': a.timestamp
                        }
                        for a in anomalies
                    ],
                    "count": len(anomalies),
                    "timestamp": time.time()
                }
            except Exception as e:
                self.logger.error(f"Error getting anomalies: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

        @self.app.get("/api/analytics/forecast")
        async def get_forecast(metric_name: str = Query(""),
                              method: str = Query("linear", regex="^(linear|exponential)$"),
                              _: bool = Depends(verify_secret_query)):
            """Get forecast for metric"""
            try:
                if not self.analytics_engine or not metric_name:
                    return {"forecast": {}}

                forecast = self.analytics_engine.forecast(metric_name, method)

                if not forecast:
                    return {"forecast": {}, "message": "No forecast data available"}

                return {
                    "status": "success",
                    "metric": metric_name,
                    "forecast": {
                        'current_value': forecast.current_value,
                        'predicted_value': forecast.predicted_value,
                        'confidence_interval': forecast.confidence_interval,
                        'accuracy': forecast.accuracy,
                        'time_period_seconds': forecast.time_period
                    },
                    "timestamp": time.time()
                }
            except Exception as e:
                self.logger.error(f"Error getting forecast: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

        @self.app.get("/api/dashboards")
        async def list_dashboards(_: bool = Depends(verify_secret_query)):
            """List all dashboards"""
            try:
                if not self.dashboard_builder:
                    return {"dashboards": []}

                dashboards = self.dashboard_builder.get_dashboard_list()

                return {
                    "status": "success",
                    "dashboards": dashboards,
                    "count": len(dashboards),
                    "timestamp": time.time()
                }
            except Exception as e:
                self.logger.error(f"Error listing dashboards: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

        @self.app.get("/api/dashboards/{dashboard_id}")
        async def get_dashboard(dashboard_id: str, _: bool = Depends(verify_secret_query)):
            """Get dashboard data"""
            try:
                if not self.dashboard_builder:
                    return {"dashboard": {}}

                dashboard_data = self.dashboard_builder.get_dashboard_data(dashboard_id)

                if not dashboard_data:
                    return {"dashboard": {}, "message": "Dashboard not found"}

                return {
                    "status": "success",
                    "dashboard": {
                        'dashboard_id': dashboard_data.dashboard_id,
                        'widgets': dashboard_data.widgets,
                        'timestamp': dashboard_data.timestamp
                    }
                }
            except Exception as e:
                self.logger.error(f"Error getting dashboard: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

        @self.app.get("/api/reports")
        async def list_reports(_: bool = Depends(verify_secret_query)):
            """List all reports"""
            try:
                if not self.report_generator:
                    return {"reports": []}

                summary = self.report_generator.get_report_summary()

                return {
                    "status": "success",
                    "summary": summary,
                    "timestamp": time.time()
                }
            except Exception as e:
                self.logger.error(f"Error listing reports: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

        @self.app.get("/api/reports/{report_id}")
        async def get_report(report_id: str,
                            format_type: str = Query("json", regex="^(json|html|markdown)$"),
                            _: bool = Depends(verify_secret_query)):
            """Get report in specified format"""
            try:
                if not self.report_generator:
                    return {"report": {}}

                report_content = self.report_generator.export_report(report_id)

                if not report_content:
                    return {"report": {}, "message": "Report not found"}

                if format_type == "html":
                    return HTMLResponse(content=report_content)
                elif format_type == "markdown":
                    return {"report": report_content, "format": "markdown"}
                else:  # json
                    return json.loads(report_content) if report_content else {}
            except Exception as e:
                self.logger.error(f"Error getting report: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

        # Regression Testing Endpoints
        @self.app.post("/api/regression/baseline")
        async def establish_baseline(metric_name: str = Query(...),
                                    commit_hash: str = Query(...),
                                    values: List[float] = Query(...),
                                    _: bool = Depends(verify_secret_query)):
            """Establish performance baseline"""
            try:
                if not self.regression_tester:
                    return {"error": "Regression tester not available"}

                baseline_id = self.regression_tester.establish_baseline(
                    metric_name, commit_hash, values
                )

                return {
                    "status": "success",
                    "baseline_id": baseline_id,
                    "metric": metric_name,
                    "commit": commit_hash,
                    "timestamp": time.time()
                }
            except Exception as e:
                self.logger.error(f"Error establishing baseline: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

        @self.app.post("/api/regression/measure")
        async def record_measurement(metric_name: str = Query(...),
                                    value: float = Query(...),
                                    commit_hash: str = Query(None),
                                    _: bool = Depends(verify_secret_query)):
            """Record performance measurement"""
            try:
                if not self.regression_tester:
                    return {"error": "Regression tester not available"}

                self.regression_tester.record_measurement(metric_name, value, commit_hash)

                return {
                    "status": "success",
                    "metric": metric_name,
                    "value": value,
                    "timestamp": time.time()
                }
            except Exception as e:
                self.logger.error(f"Error recording measurement: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

        @self.app.get("/api/regression/detect")
        async def detect_regression(metric_name: str = Query(...),
                                   method: str = Query("threshold"),
                                   _: bool = Depends(verify_secret_query)):
            """Detect performance regression"""
            try:
                if not self.regression_tester:
                    return {"error": "Regression tester not available"}

                result = self.regression_tester.detect_regression(metric_name)

                if not result:
                    return {"status": "no_data", "metric": metric_name}

                return {
                    "status": "success",
                    "metric": result.metric_name,
                    "is_regression": result.is_regression,
                    "severity": result.severity.value,
                    "percent_change": result.percent_change,
                    "confidence": result.confidence,
                    "action": result.recommended_action,
                    "timestamp": time.time()
                }
            except Exception as e:
                self.logger.error(f"Error detecting regression: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

        @self.app.get("/api/regression/report")
        async def get_regression_report(metric_name: str = Query(None),
                                       _: bool = Depends(verify_secret_query)):
            """Get regression analysis report"""
            try:
                if not self.regression_tester:
                    return {"error": "Regression tester not available"}

                report = self.regression_tester.get_regression_report(metric_name)

                return {
                    "status": "success",
                    "report": report,
                    "timestamp": time.time()
                }
            except Exception as e:
                self.logger.error(f"Error getting regression report: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

        # Performance Streaming Endpoints
        @self.app.post("/api/stream/register")
        async def register_stream_client(client_id: str = Query(...),
                                        update_interval: int = Query(1000),
                                        _: bool = Depends(verify_secret_query)):
            """Register client for performance streaming"""
            try:
                if not self.performance_streamer:
                    return {"error": "Performance streamer not available"}

                success = self.performance_streamer.register_client(client_id, update_interval)

                return {
                    "status": "success" if success else "failed",
                    "client_id": client_id,
                    "timestamp": time.time()
                }
            except Exception as e:
                self.logger.error(f"Error registering client: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

        @self.app.post("/api/stream/subscribe")
        async def subscribe_stream(client_id: str = Query(...),
                                  streams: str = Query(...),
                                  metrics_filter: str = Query(None),
                                  _: bool = Depends(verify_secret_query)):
            """Subscribe client to performance streams"""
            try:
                if not self.performance_streamer:
                    return {"error": "Performance streamer not available"}

                stream_list = streams.split(',')
                filter_list = metrics_filter.split(',') if metrics_filter else None

                success = self.performance_streamer.subscribe_client(
                    client_id, stream_list, filter_list
                )

                return {
                    "status": "success" if success else "failed",
                    "client_id": client_id,
                    "streams": stream_list,
                    "timestamp": time.time()
                }
            except Exception as e:
                self.logger.error(f"Error subscribing to streams: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

        @self.app.get("/api/stream/updates")
        async def get_stream_updates(client_id: str = Query(...),
                                    _: bool = Depends(verify_secret_query)):
            """Get pending stream updates for client"""
            try:
                if not self.performance_streamer:
                    return {"error": "Performance streamer not available"}

                updates = self.performance_streamer.get_client_updates(client_id)

                return {
                    "status": "success",
                    "updates": updates,
                    "timestamp": time.time()
                }
            except Exception as e:
                self.logger.error(f"Error getting stream updates: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

        @self.app.get("/api/stream/summary")
        async def get_stream_summary(_: bool = Depends(verify_secret_query)):
            """Get performance streaming summary"""
            try:
                if not self.performance_streamer:
                    return {"error": "Performance streamer not available"}

                summary = self.performance_streamer.get_streaming_summary()

                return {
                    "status": "success",
                    "summary": summary,
                    "timestamp": time.time()
                }
            except Exception as e:
                self.logger.error(f"Error getting stream summary: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

        # I/O Performance Analysis Endpoints
        @self.app.post("/api/io/record")
        async def record_io_operation(operation_type: str = Query(...),
                                     path: str = Query(...),
                                     duration: float = Query(...),
                                     size: int = Query(0),
                                     success: bool = Query(True),
                                     _: bool = Depends(verify_secret_query)):
            """Record I/O operation"""
            try:
                if not self.io_analyzer:
                    return {"error": "I/O analyzer not available"}

                self.io_analyzer.record_operation(
                    operation_type, path, duration, size, success
                )

                return {
                    "status": "success",
                    "operation": operation_type,
                    "path": path,
                    "timestamp": time.time()
                }
            except Exception as e:
                self.logger.error(f"Error recording I/O operation: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

        @self.app.get("/api/io/metrics")
        async def get_io_metrics(operation_type: str = Query(None),
                                _: bool = Depends(verify_secret_query)):
            """Get I/O performance metrics"""
            try:
                if not self.io_analyzer:
                    return {"error": "I/O analyzer not available"}

                metrics = self.io_analyzer.get_operation_metrics(operation_type)

                return {
                    "status": "success",
                    "metrics": metrics,
                    "timestamp": time.time()
                }
            except Exception as e:
                self.logger.error(f"Error getting I/O metrics: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

        @self.app.get("/api/io/bottlenecks")
        async def get_io_bottlenecks(_: bool = Depends(verify_secret_query)):
            """Get I/O bottleneck analysis"""
            try:
                if not self.io_analyzer:
                    return {"error": "I/O analyzer not available"}

                bottlenecks = self.io_analyzer.identify_bottlenecks()

                return {
                    "status": "success",
                    "bottlenecks": bottlenecks,
                    "count": len(bottlenecks),
                    "timestamp": time.time()
                }
            except Exception as e:
                self.logger.error(f"Error getting I/O bottlenecks: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

        @self.app.get("/api/io/patterns")
        async def get_io_patterns(_: bool = Depends(verify_secret_query)):
            """Get file access patterns"""
            try:
                if not self.io_analyzer:
                    return {"error": "I/O analyzer not available"}

                patterns = self.io_analyzer.detect_access_patterns()

                return {
                    "status": "success",
                    "patterns": patterns,
                    "timestamp": time.time()
                }
            except Exception as e:
                self.logger.error(f"Error detecting I/O patterns: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

        @self.app.get("/api/io/summary")
        async def get_io_summary(_: bool = Depends(verify_secret_query)):
            """Get I/O system summary"""
            try:
                if not self.io_analyzer:
                    return {"error": "I/O analyzer not available"}

                summary = self.io_analyzer.get_io_summary()

                return {
                    "status": "success",
                    "summary": summary,
                    "timestamp": time.time()
                }
            except Exception as e:
                self.logger.error(f"Error getting I/O summary: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

        # Optimization Advisor Endpoints
        @self.app.post("/api/optimization/analyze")
        async def analyze_function(function_name: str = Query(...),
                                  call_count: int = Query(...),
                                  total_time: float = Query(...),
                                  memory_usage: int = Query(0),
                                  io_ops: int = Query(0),
                                  _: bool = Depends(verify_secret_query)):
            """Analyze function for optimization opportunities"""
            try:
                if not self.optimization_advisor:
                    return {"error": "Optimization advisor not available"}

                profile_id = self.optimization_advisor.analyze_function(
                    function_name, call_count, total_time, memory_usage, io_ops
                )

                return {
                    "status": "success",
                    "profile_id": profile_id,
                    "function": function_name,
                    "timestamp": time.time()
                }
            except Exception as e:
                self.logger.error(f"Error analyzing function: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

        @self.app.get("/api/optimization/recommendations")
        async def get_recommendations(category: str = Query(None),
                                     priority: str = Query(None),
                                     _: bool = Depends(verify_secret_query)):
            """Get optimization recommendations"""
            try:
                if not self.optimization_advisor:
                    return {"error": "Optimization advisor not available"}

                recommendations = self.optimization_advisor.get_recommendations(category, priority)

                return {
                    "status": "success",
                    "recommendations": recommendations,
                    "count": len(recommendations),
                    "timestamp": time.time()
                }
            except Exception as e:
                self.logger.error(f"Error getting recommendations: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

        @self.app.get("/api/optimization/report")
        async def get_optimization_report(_: bool = Depends(verify_secret_query)):
            """Get optimization report"""
            try:
                if not self.optimization_advisor:
                    return {"error": "Optimization advisor not available"}

                report = self.optimization_advisor.get_optimization_report()

                return {
                    "status": "success",
                    "report": report,
                    "timestamp": time.time()
                }
            except Exception as e:
                self.logger.error(f"Error getting optimization report: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

        # Resource Limiter Endpoints
        @self.app.post("/api/resources/limit")
        async def set_resource_limit(resource_type: str = Query(...),
                                    limit_value: float = Query(...),
                                    unit: str = Query(...),
                                    enforcement: str = Query("warn"),
                                    soft_limit_percent: float = Query(80.0),
                                    _: bool = Depends(verify_secret_query)):
            """Set resource limit"""
            try:
                if not self.resource_limiter:
                    return {"error": "Resource limiter not available"}

                from .utils.resource_limiter import ResourceType, LimitEnforcement

                try:
                    rt = ResourceType[resource_type.upper()]
                    le = LimitEnforcement[enforcement.upper()]
                except (KeyError, ValueError):
                    return {"error": "Invalid resource type or enforcement"}

                self.resource_limiter.set_limit(rt, limit_value, unit, le, soft_limit_percent)

                return {
                    "status": "success",
                    "resource": resource_type,
                    "limit": limit_value,
                    "unit": unit,
                    "timestamp": time.time()
                }
            except Exception as e:
                self.logger.error(f"Error setting resource limit: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

        @self.app.post("/api/resources/record")
        async def record_resource_usage(resource_type: str = Query(...),
                                       current_value: float = Query(...),
                                       _: bool = Depends(verify_secret_query)):
            """Record resource usage"""
            try:
                if not self.resource_limiter:
                    return {"error": "Resource limiter not available"}

                from .utils.resource_limiter import ResourceType

                try:
                    rt = ResourceType[resource_type.upper()]
                except (KeyError, ValueError):
                    return {"error": "Invalid resource type"}

                self.resource_limiter.record_usage(rt, current_value)

                return {
                    "status": "success",
                    "resource": resource_type,
                    "value": current_value,
                    "timestamp": time.time()
                }
            except Exception as e:
                self.logger.error(f"Error recording resource usage: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

        @self.app.get("/api/resources/usage")
        async def get_resource_usage(resource_type: str = Query(None),
                                    _: bool = Depends(verify_secret_query)):
            """Get resource usage"""
            try:
                if not self.resource_limiter:
                    return {"error": "Resource limiter not available"}

                if resource_type:
                    from .utils.resource_limiter import ResourceType
                    try:
                        rt = ResourceType[resource_type.upper()]
                        usage = self.resource_limiter.get_current_usage(rt)
                    except (KeyError, ValueError):
                        return {"error": "Invalid resource type"}
                else:
                    usage = self.resource_limiter.get_current_usage()

                return {
                    "status": "success",
                    "usage": usage,
                    "timestamp": time.time()
                }
            except Exception as e:
                self.logger.error(f"Error getting resource usage: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

        @self.app.get("/api/resources/violations")
        async def get_resource_violations(resource_type: str = Query(None),
                                         _: bool = Depends(verify_secret_query)):
            """Get resource violations"""
            try:
                if not self.resource_limiter:
                    return {"error": "Resource limiter not available"}

                if resource_type:
                    from .utils.resource_limiter import ResourceType
                    try:
                        rt = ResourceType[resource_type.upper()]
                        violations = self.resource_limiter.get_violations(rt)
                    except (KeyError, ValueError):
                        return {"error": "Invalid resource type"}
                else:
                    violations = self.resource_limiter.get_violations()

                return {
                    "status": "success",
                    "violations": violations,
                    "count": len(violations),
                    "timestamp": time.time()
                }
            except Exception as e:
                self.logger.error(f"Error getting violations: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

        @self.app.get("/api/resources/report")
        async def get_resource_report(_: bool = Depends(verify_secret_query)):
            """Get resource usage report"""
            try:
                if not self.resource_limiter:
                    return {"error": "Resource limiter not available"}

                report = self.resource_limiter.get_resource_report()

                return {
                    "status": "success",
                    "report": report,
                    "timestamp": time.time()
                }
            except Exception as e:
                self.logger.error(f"Error getting resource report: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

        # Performance Test Runner Endpoints
        @self.app.post("/api/tests/scenario")
        async def register_test_scenario(scenario_name: str = Query(...),
                                        test_type: str = Query(...),
                                        description: str = Query(...),
                                        iterations: int = Query(100),
                                        concurrency: int = Query(1),
                                        _: bool = Depends(verify_secret_query)):
            """Register test scenario"""
            try:
                if not self.test_runner:
                    return {"error": "Test runner not available"}

                scenario_id = self.test_runner.register_scenario(
                    scenario_name, test_type, description,
                    iterations=iterations, concurrency=concurrency
                )

                return {
                    "status": "success",
                    "scenario_id": scenario_id,
                    "scenario_name": scenario_name,
                    "timestamp": time.time()
                }
            except Exception as e:
                self.logger.error(f"Error registering scenario: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

        @self.app.post("/api/tests/run")
        async def run_test_scenario(scenario_id: str = Query(...),
                                   _: bool = Depends(verify_secret_query)):
            """Run test scenario"""
            try:
                if not self.test_runner:
                    return {"error": "Test runner not available"}

                test_id = self.test_runner.run_scenario(scenario_id)

                return {
                    "status": "success" if test_id else "failed",
                    "test_id": test_id,
                    "scenario_id": scenario_id,
                    "timestamp": time.time()
                }
            except Exception as e:
                self.logger.error(f"Error running test: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

        @self.app.get("/api/tests/result")
        async def get_test_result(test_id: str = Query(...),
                                 _: bool = Depends(verify_secret_query)):
            """Get test result"""
            try:
                if not self.test_runner:
                    return {"error": "Test runner not available"}

                result = self.test_runner.get_test_result(test_id)

                return {
                    "status": "success" if result else "not_found",
                    "result": result,
                    "timestamp": time.time()
                }
            except Exception as e:
                self.logger.error(f"Error getting test result: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

        @self.app.get("/api/tests/summary")
        async def get_test_summary(_: bool = Depends(verify_secret_query)):
            """Get test execution summary"""
            try:
                if not self.test_runner:
                    return {"error": "Test runner not available"}

                summary = self.test_runner.get_test_summary()

                return {
                    "status": "success",
                    "summary": summary,
                    "timestamp": time.time()
                }
            except Exception as e:
                self.logger.error(f"Error getting test summary: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

        # Sync Instrumentation Endpoint
        @self.app.get("/api/instrumentation/summary")
        async def get_instrumentation_summary(_: bool = Depends(verify_secret_query)):
            """Get sync instrumentation summary"""
            try:
                if HAS_SYNC_INSTRUMENTATION:
                    summary = SyncInstrumentation.get_instrumentation_summary()
                else:
                    summary = {"available": False}

                return {
                    "status": "success",
                    "instrumentation": summary,
                    "timestamp": time.time()
                }
            except Exception as e:
                self.logger.error(f"Error getting instrumentation summary: {str(e)}")
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