import json


class ConfigurationManager:
    """Class to manage configuration file"""

    def __init__(self, config_file):
        self.config_file = config_file
        self.config = None

    def load(self):
        """Load configuration from JSON file"""
        with open(self.config_file, "r", encoding="utf-8") as file:
            self.config = json.load(file)

    def get_destinations(self):
        """Get paths from destinations in configuration"""
        return self.config.get("destinations", [])
