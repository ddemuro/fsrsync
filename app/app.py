import os
import sys
from app.config_manager import ConfigurationManager
from app.utils.filesystem_monitor import FilesystemMonitor
from app.utils.rsync_manager import RsyncManager


class Application:
    """Main application class to monitor filesystem events and trigger rsync"""

    def __init__(self, config_file):
        """Initialize the application with a configuration file"""
        self.config_manager = ConfigurationManager(config_file)
        self.fs_monitor = FilesystemMonitor()
        self.destinations = []

    def setup(self):
        """Set up the application by loading configuration and setting up rsync managers"""
        self.config_manager.load()
        destinations = self.config_manager.get_destinations()

        # Set up rsync managers and inotify watchers for each destination
        for dest_config in destinations:
            rsync_manager = RsyncManager(
                destination=dest_config["destination"], options=dest_config["options"]
            )
            event_queue_limit = dest_config["event_queue_limit"]
            paths = dest_config["paths"]
            self.destinations.append(
                {
                    "rsync_manager": rsync_manager,
                    "event_queue_limit": event_queue_limit,
                    "event_count": 0,
                }
            )

            for path_config in paths:
                path = path_config["path"]
                events = path_config["events"]
                # Ensure we always monitor IN_OPEN and IN_CLOSE_WRITE
                if "IN_CLOSE_WRITE" not in events:
                    events.append("IN_CLOSE_WRITE")
                if "IN_OPEN" not in events:
                    events.append("IN_OPEN")
                self.fs_monitor.add_watch(path, events)
                rsync_manager.add_path(path)

    def run(self):
        """Run the application to monitor filesystem events and trigger rsync"""
        for event in self.fs_monitor.event_generator():
            type_names, path, filename = self.fs_monitor.handle_event(event)
            print(f"Event detected: {type_names} on {path}/{filename}")

            # Update event counts and check queue limits for each destination
            for destination in self.destinations:
                destination["event_count"] += 1

                # Trigger rsync when event count reaches the limit
                if destination["event_count"] >= destination["event_queue_limit"]:
                    # Delay rsync if there are open files
                    if self.fs_monitor.has_open_files():
                        print("Open files detected, delaying rsync...")
                    else:
                        print(
                            f"Event queue limit reached for destination {destination['rsync_manager'].destination}. Running rsync..."
                        )
                        destination["rsync_manager"].run()
                        destination["event_count"] = 0


""" Main entry point for the application """
if __name__ == "__main__":
    config_file = "config.json"
    app = Application(config_file)
    app.setup()
    app.run()
