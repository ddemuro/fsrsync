import sys
import json
from .logs import Logger


class ConfigurationManager:
    """Class to manage configuration file"""

    _instance = None  # Initialize the class attribute to store the instance

    def __init__(self, config_file):
        self.config_file = config_file
        self.logger = Logger()
        self.config = None

    @classmethod
    def get_instance(cls, config_file):
        """Get the singleton instance."""
        if not cls._instance:
            cls._instance = ConfigurationManager(config_file)
        return cls._instance

    def load(self):
        """Load configuration from JSON file"""
        self.logger.debug("Loading configuration")
        try:
            with open(self.config_file, "r", encoding="utf-8") as file:
                self.config = json.load(file)
                self.logger.debug("Loaded configuration...")
        except FileNotFoundError:
            self.logger.error(f"Configuration file not found: {self.config_file}")
            # Exit the program if the configuration file is not found
            sys.exit(1)
        except json.JSONDecodeError as e:
            self.logger.error(f"Error loading configuration: {e}")
            # Exit the program if there is an error loading the configuration file
            sys.exit(2)

    def get_destinations(self):
        """Get paths from destinations in configuration"""
        # self.logger.debug(f"Getting destinations from config: {self.config}")
        return self.config.get("destinations", [])

    def get_hostname(self):
        """Get the hostname from the configuration"""
        return self.config.get("hostname", None)

    def get_webcontrol_port(self):
        """Get the port from the configuration"""
        return self.config.get("control_server_port", 8080)

    def get_webcontrol_host(self):
        """Get the host from the configuration"""
        return self.config.get("control_server_host", "127.0.0.1")

    def get_webcontrol_secret(self):
        """Get the secret from the configuration"""
        return self.config.get("control_server_secret", "secret")
