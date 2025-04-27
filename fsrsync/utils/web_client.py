"""Library to make secure, reliable HTTP/HTTPS requests to the web server."""
import time
import logging
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from typing import Dict, Any, Optional, Union


class WebClient:
    """Enhanced client for making reliable HTTP/HTTPS requests to the web server."""

    def __init__(
        self,
        host: str,
        port: Union[int, str],
        secret: str,
        use_locks: bool = False,
        use_https: bool = False,
        logger: Optional[logging.Logger] = None,
        timeout: int = 30,
        max_retries: int = 3,
        retry_backoff: float = 0.5,
    ):
        """Initialize the web client with enhanced configuration options.
        
        Args:
            host: Server hostname
            port: Server port
            secret: Authentication secret
            use_locks: Whether to use server locks
            use_https: Whether to use HTTPS instead of HTTP
            logger: Logger instance
            timeout: Request timeout in seconds
            max_retries: Maximum number of retries for failed requests
            retry_backoff: Backoff factor for retries
        """
        # Validate inputs
        if not host and use_locks:
            raise ValueError("Host cannot be empty when use_locks is True")
        if not port and use_locks:
            raise ValueError("Port cannot be empty when use_locks is True")
        if not secret and use_locks:
            raise ValueError("Secret cannot be empty when use_locks is True")
            
        # Initialize properties
        self.host = host
        self.port = port
        self.secret = secret
        self.use_locks = use_locks
        self.protocol = "https" if use_https else "http"
        self.timeout = timeout
        self.base_url = f"{self.protocol}://{self.host}:{self.port}"
        
        # Set up logging
        self.logger = logger or logging.getLogger(__name__)
        
        # Configure session with retries
        self.session = requests.Session()
        retry_strategy = Retry(
            total=max_retries,
            backoff_factor=retry_backoff,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        self.session.headers.update({"secret": self.secret})
        
        self.logger.debug(f"WebClient initialized for {self.base_url}")

    def _log_request(self, method: str, url: str, data: Optional[Dict[str, Any]] = None, level: str = "debug") -> None:
        """Log request details at the specified level.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            url: Request URL
            data: Request data
            level: Log level (debug, info, warning, error)
        """
        log_message = f"{method} request to {url}"
        if data:
            log_message += f" with data: {data}"
            
        log_func = getattr(self.logger, level.lower())
        log_func(log_message)

    def _log_response(self, url: str, response: requests.Response, level: str = "debug") -> None:
        """Log response details at the specified level.
        
        Args:
            url: Request URL
            response: Response object
            level: Log level (debug, info, warning, error)
        """
        log_message = f"Response from {url}: Status {response.status_code}"
        log_func = getattr(self.logger, level.lower())
        log_func(log_message)
        
        # Log response content at trace level if available
        if hasattr(self.logger, 'trace'):
            try:
                self.logger.trace(f"Response content: {response.json()}")
            except ValueError:
                self.logger.trace(f"Response content (not JSON): {response.text[:100]}...")

    def _make_request(
        self, 
        method: str, 
        path: str, 
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Make an HTTP request with robust error handling.
        
        Args:
            method: HTTP method (GET, POST)
            path: API endpoint path
            data: Request body for POST requests
            params: Query parameters for GET requests
            
        Returns:
            Processed response data
        """
        url = f"{self.base_url}{path}"
        start_time = time.time()
        
        try:
            self._log_request(method, url, data)
            
            if method.upper() == "GET":
                response = self.session.get(url, params=params, timeout=self.timeout)
            elif method.upper() == "POST":
                response = self.session.post(url, json=data, timeout=self.timeout)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
                
            elapsed = time.time() - start_time
            self._log_response(url, response)
            self.logger.debug(f"Request completed in {elapsed:.2f}s")
            
            # Handle response
            response.raise_for_status()
            
            try:
                return response.json()
            except ValueError:
                self.logger.warning(f"Response is not valid JSON: {response.text[:100]}...")
                return {"status": "error", "message": "Invalid JSON response", "raw": response.text}
                
        except requests.exceptions.ConnectionError as e:
            self.logger.error(f"Connection error when connecting to {url}: {e}")
            return {"status": "error", "error_type": "connection_error", "message": str(e)}
            
        except requests.exceptions.Timeout as e:
            self.logger.error(f"Timeout error when connecting to {url}: {e}")
            return {"status": "error", "error_type": "timeout", "message": str(e)}
            
        except requests.exceptions.HTTPError as e:
            status_code = e.response.status_code if e.response else "unknown"
            self.logger.error(f"HTTP error {status_code} when connecting to {url}: {e}")
            
            error_data = {"status": "error", "error_type": "http_error", "status_code": status_code, "message": str(e)}
            
            # Try to parse error response
            try:
                error_content = e.response.json() if e.response else {}
                error_data["detail"] = error_content
            except ValueError:
                error_data["raw_response"] = e.response.text[:200] if e.response else "No response"
                
            return error_data
            
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Request error when connecting to {url}: {e}")
            return {"status": "error", "error_type": "request_error", "message": str(e)}
            
        except Exception as e:
            self.logger.error(f"Unexpected error when connecting to {url}: {e}", exc_info=True)
            return {"status": "error", "error_type": "unexpected", "message": str(e)}
            
        finally:
            total_time = time.time() - start_time
            if total_time > self.timeout / 2:
                self.logger.warning(f"Request to {url} took {total_time:.2f}s (longer than half timeout)")

    def get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Make a GET request to the web server with enhanced error handling.
        
        Args:
            path: API endpoint path
            params: Query parameters
            
        Returns:
            Response data
        """
        return self._make_request("GET", path, params=params)

    def post(self, path: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Make a POST request to the web server with enhanced error handling.
        
        Args:
            path: API endpoint path
            data: Request data
            
        Returns:
            Response data
        """
        return self._make_request("POST", path, data=data)

    def is_successful_response(self, response: Dict[str, Any]) -> bool:
        """Check if a response indicates success.
        
        Args:
            response: Response data
            
        Returns:
            True if successful, False otherwise
        """
        if not isinstance(response, dict):
            return False
            
        # Check for error status
        if response.get("status") == "error":
            return False
            
        # Check for HTTP error status code
        if "status_code" in response and response["status_code"] >= 400:
            return False
            
        return True

    # Enhanced API methods with result checking and type hints
    def add_file_to_locked_file(self, file: str) -> Dict[str, Any]:
        """Add a file to the locked files list.
        
        Args:
            file: Path to the file
            
        Returns:
            Response data
        """
        self.logger.info(f"Adding file to locked files: {file}")
        return self.post("/add_file_to_locked_files", {"files": [file]})

    def add_file_to_locked_files(self, files: list) -> Dict[str, Any]:
        """Add multiple files to the locked files list.
        
        Args:
            files: List of file paths
            
        Returns:
            Response data
        """
        if not files:
            self.logger.warning("No files provided to add_file_to_locked_files")
            return {"status": "warning", "message": "No files provided"}
            
        self.logger.info(f"Adding {len(files)} files to locked files")
        return self.post("/add_file_to_locked_files", {"files": files})

    def delete_file_pending_for_path(self, path: str) -> Dict[str, Any]:
        """Delete a file pending for a path.
        
        Args:
            path: File path
            
        Returns:
            Response data
        """
        if not path:
            self.logger.warning("No path provided to delete_file_pending_for_path")
            return {"status": "warning", "message": "No path provided"}
            
        self.logger.info(f"Deleting file pending for path: {path}")
        return self.post("/delete_file_pending_for_path", {"path": path})

    def check_if_server_locked(self, server: str, path: Optional[str] = None) -> Dict[str, Any]:
        """Check if a server is locked.
        
        Args:
            server: Server name
            path: Optional path
            
        Returns:
            Response with status indicating if server is locked
        """
        if not server:
            self.logger.warning("No server provided to check_if_server_locked")
            return {"status": "warning", "message": "No server provided"}
            
        self.logger.info(f"Checking if server is locked: {server}, path: {path}")
        return self.post("/check_if_server_locked", {"server": server, "path": path})

    def add_to_global_server_lock(self, server: str, path: Optional[str] = None) -> Dict[str, Any]:
        """Add a server to the global server lock.
        
        Args:
            server: Server name
            path: Optional path
            
        Returns:
            Response data
        """
        if not server:
            self.logger.warning("No server provided to add_to_global_server_lock")
            return {"status": "warning", "message": "No server provided"}
            
        self.logger.info(f"Adding server to global server lock: {server}, path: {path}")
        return self.post("/add_to_global_server_lock", {"server": server, "path": path})

    def remove_from_global_server_lock(self, server: str, path: Optional[str] = None) -> Dict[str, Any]:
        """Remove a server from the global server lock.
        
        Args:
            server: Server name
            path: Optional path
            
        Returns:
            Response data
        """
        if not server:
            self.logger.warning("No server provided to remove_from_global_server_lock")
            return {"status": "warning", "message": "No server provided"}
            
        self.logger.info(f"Removing server from global server lock: {server}, path: {path}")
        return self.post("/remove_from_global_server_lock", {"server": server, "path": path})

    def remove_locked_files(self, files: list) -> Dict[str, Any]:
        """Remove files from the locked files list.
        
        Args:
            files: List of file paths
            
        Returns:
            Response data
        """
        if not files:
            self.logger.warning("No files provided to remove_locked_files")
            return {"status": "warning", "message": "No files provided"}
            
        self.logger.info(f"Removing {len(files)} files from locked files")
        return self.post("/remove_locked_files", {"files": files})

    def set_locked_files(self, files: list) -> Dict[str, Any]:
        """Set the locked files list.
        
        Args:
            files: List of file paths
            
        Returns:
            Response data
        """
        self.logger.info(f"Setting locked files: {len(files)} files")
        return self.post("/set_locked_files", {"files": files})

    def regular_pending(self) -> Dict[str, Any]:
        """Get regular pending files.
        
        Returns:
            List of regular pending files
        """
        self.logger.info("Getting regular pending files")
        return self.get("/regular_pending")

    def immediate_pending(self) -> Dict[str, Any]:
        """Get immediate pending files.
        
        Returns:
            List of immediate pending files
        """
        self.logger.info("Getting immediate pending files")
        return self.get("/immediate_pending")

    def locked_files(self) -> Dict[str, Any]:
        """Get locked files.
        
        Returns:
            List of locked files
        """
        self.logger.info("Getting locked files")
        return self.get("/locked_files")

    def health_check(self) -> bool:
        """Check if the server is healthy.
        
        Returns:
            True if server is healthy, False otherwise
        """
        self.logger.info("Performing health check")
        try:
            response = self.get("/")
            return self.is_successful_response(response)
        except Exception as e:
            self.logger.error(f"Health check failed: {e}")
            return False