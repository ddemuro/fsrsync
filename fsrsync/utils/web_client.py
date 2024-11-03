"""Library to make GET and POST requests to the web server."""
import requests
from requests.exceptions import ConnectionError, RequestException


class WebClient:
    """Library to make GET and POST requests to the web server."""

    def __init__(self, host, port, secret, logger=None):
        """Initialize the web client"""
        self.host = host
        self.port = port
        self.secret = secret
        self.logger = logger

    def log(self, message):
        """Log a message"""
        if self.logger:
            self.logger.info(message)

    def get(self, path):
        """Make a GET request to the web server"""
        url = f"http://{self.host}:{self.port}{path}"
        try:
            response = requests.get(url, headers={"secret": self.secret})
            response.raise_for_status()
            self.log(f"GET request to {url}, response: {response.json()}")
            return response.json()
        except ConnectionError:
            return {"status": "error", "message": "Connection error"}
        except RequestException as e:
            return {"status": "error", "message": str(e)}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def post(self, path, data):
        """Make a POST request to the web server"""
        url = f"http://{self.host}:{self.port}{path}"
        try:
            response = requests.post(url, headers={"secret": self.secret}, json=data)
            response.raise_for_status()
            self.log(f"POST request to {url} with data {data}, response: {response.json()}")
            return response.json()
        except ConnectionError:
            return {"status": "error", "message": "Connection error"}
        except RequestException as e:
            return {"status": "error", "message": str(e)}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def add_file_to_locked_file(self, file):
        """Add a file to the locked files"""
        return self.post("/add_file_to_locked_files", {"files": [file]})

    def add_file_to_locked_files(self, files):
        """Add files to the locked files"""
        return self.post("/add_file_to_locked_files", {"files": files})

    def add_to_global_server_lock(self, server):
        """Add a server to the global server lock"""
        return self.post("/add_to_global_server_lock", {"server": server})

    def remove_from_global_server_lock(self, server):
        """Remove a server from the global server lock"""
        return self.post("/remove_from_global_server_lock", {"server": server})

    def remove_locked_files(self, files):
        """Remove a file from the locked files"""
        return self.post("/remove_locked_files", {"files": files})

    def set_locked_files(self, files):
        """Set locked files"""
        return self.post("/set_locked_files", {"files": files})

    def regular_pending(self):
        """Get regular pending files"""
        return self.get("/regular_pending")

    def immediate_pending(self):
        """Get immediate pending files"""
        return self.get("/immediate_pending")

    def locked_files(self):
        """Get locked files"""
        return self.get("/locked_files")
