import os
import sys
from utils.logs import Logger
from utils.rsync import RsyncManager
from utils.filesystem import FilesystemMonitor
from utils.configuration import ConfigurationManager
from utils.utils import validate_path

DEFAULT_CONFIG_FILE = "/etc/fsrsync/config.json"


class Application:
    """Main application class to monitor filesystem events and trigger rsync"""

    def __init__(self, config_file):
        """Initialize the application with a configuration file"""
        self.config_manager = ConfigurationManager(config_file)
        self.fs_monitor = FilesystemMonitor()
        self.destinations = []
        self.config_manager.get_instance(config_file).load()
        self.logger = Logger()
        self.logger.set_level(
            self.config_manager.get_instance(config_file)
            .config.get("loglevel", "INFO")
            .upper()
        )

    def setup(self):
        """Set up the application by loading configuration and setting up rsync managers"""
        self.config_manager.load()
        destinations = self.config_manager.get_destinations()

        # Set up rsync managers and inotify watchers for each destination
        for dest_config in destinations:
            path = dest_config.get("path")
            self.logger.info(f"Setting up destination: {path}")
            if not validate_path(path):
                self.logger.error(f"Invalid path: {path}, skipping destination...")
                continue

            rsync_manager = RsyncManager(
                destination=dest_config["destination"],
                options=dest_config["options"],
                pre_sync_commands=dest_config.get("pre_sync_commands", []),
                post_sync_commands=dest_config.get("post_sync_commands", []),
            )
            event_queue_limit = dest_config["event_queue_limit"]
            destination_config = {
                "rsync_manager": rsync_manager,
                "event_queue_limit": event_queue_limit,
                "event_count": 0,
                "path": path,
                "max_wait_locked": dest_config.get("max_wait_locked", 60),
            }

            events = dest_config["events"]
            # Ensure we always monitor IN_OPEN and IN_CLOSE_WRITE
            if "IN_CLOSE_WRITE" not in events:
                events.append("IN_CLOSE_WRITE")
            if "IN_OPEN" not in events:
                events.append("IN_OPEN")
            self.fs_monitor.add_watch(path, events)
            rsync_manager.add_path(path)
            # Add destination to the list of destinations
            self.destinations.append(destination_config)

    def run(self):
        """Run the application to monitor filesystem events and trigger rsync"""
        for event in self.fs_monitor.event_generator():
            self.fs_monitor.handle_event(event)

            # Check if there are files pending immediate sync
            pending_immediate = len(self.fs_monitor.get_immediate_sync_files())
            pending_regular = len(self.fs_monitor.get_regular_sync_files())
            self.logger.debug(
                f"Pending immediate sync files: {pending_immediate}, pending regular sync files: {pending_regular}"
            )

            # Update event counts and check queue limits for each destination
            if pending_immediate > 0 or pending_regular > 0:
                self.logger.debug("Checking event queue limits for destinations...")
                for destination in self.destinations:
                    self.manage_destination_event(destination)

    def immediate_sync_files_for_destination(
        self, destination, immediate_sync_files_for_path
    ):
        """Check if we have immedeate sync files for a destination"""
        # Check if we have immedeate sync files
        if immediate_sync_files_for_path:
            # Only sync the immediate sync files
            include = (
                "{'"
                + "','".join(
                    self.fs_monitor.get_immediate_sync_files_for_path(destination.path)
                )
                + "'}"
            )
            destination["rsync_manager"].run(include_list=include)
            self.logger.info(
                f"Immediate sync files detected for destination {destination['rsync_manager'].destination}. Running rsync..."
            )
            # Remove these files from the immediate sync list
            for file in self.fs_monitor.get_immediate_sync_files():
                self.fs_monitor.detete_immidiate_sync_file(file)

    def process_regular_sync(self, destination, events):
        """Process regular sync for a destination"""
        # Trigger rsync when event count reaches the limit        
        if len(events) >= destination["event_queue_limit"]:
            # Get locked files in the path that have exceeded the max wait time
            should_exclude = (
                self.fs_monitor.check_if_locked_files_in_path_exceeded_wait(
                    destination.get("path"), destination["max_wait_locked"]
                )
            )
            # Delay rsync if there are open files
            self.logger.info(
                f"Event queue limit reached for destination {destination['rsync_manager'].destination}. Running rsync..."
            )
            # Add files in events to the include list
            include = (
                "{'"
                + "','".join(
                    # Get the paths of files in the events like event.path
                    [event.path for event in events]
                )
                + "'}"
            )
            # Should exclude
            exclude = None
            if not should_exclude:
                # Create a list in the format of --exclude={'/path/to/file1','/path/to/file2'}
                exclude = (
                    "{'"
                    + "','".join(
                        self.fs_monitor.get_locked_files_for_path(
                            destination.get("path")
                        )
                    )
                    + "'}"
                )

            destination["rsync_manager"].run(exclude_list=exclude, include_list=include)
            # Remove these files from the regular sync list
            for file in events:
                self.fs_monitor.delete_regular_sync_file(file)

    def manage_destination_event(self, destination):
        """Manage events for a destination"""
        # Check if the path is a subdirectory of the destination
        if destination is None:
            self.logger.error("Destination is None, skipping...")
            return
        # Check destination
        self.logger.debug(f"Checking destination: {destination}")
        # Check if we have immedeate sync files
        self.immediate_sync_files_for_destination(
            destination, self.fs_monitor.get_immediate_sync_files()
        )
        # Process regular sync
        self.process_regular_sync(destination, self.fs_monitor.get_regular_sync_files())


""" Main entry point for the application """
if __name__ == "__main__":
    # If /etc/fsrsync/config.json exists, use it as the configuration file else use args
    if validate_path(DEFAULT_CONFIG_FILE):
        config_file = DEFAULT_CONFIG_FILE
    else:
        # Check if a configuration file is provided as an argument
        if len(sys.argv) < 2:
            print("Usage: python app.py <config_file>")
            sys.exit(1)
        config_file = sys.argv[1]
    app = Application(config_file)
    app.setup()
    app.run()
