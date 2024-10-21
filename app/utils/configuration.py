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
        with open(self.config_file, "r", encoding="utf-8") as file:
            self.config = json.load(file)
            # self.logger.debug(f"Loaded configuration: {self.config}")

    def get_destinations(self):
        """Get paths from destinations in configuration"""
        # self.logger.debug(f"Getting destinations from config: {self.config}")
        return self.config.get("destinations", [])
