import os
import sys
import time
import threading
from .utils.logs import Logger
from .web_app import WebControl
from .utils.rsync import RsyncManager
from .utils.sentry import setup_sentry
from .utils.utils import validate_path
from .utils.filesystem import FilesystemMonitor
from .utils.configuration import ConfigurationManager
from .utils.web_client import WebClient


class SyncApplication:
    """Main application class to monitor filesystem events and trigger rsync"""

    def __init__(self, config_file, full_sync=False):
        """Initialize the application with a configuration file"""
        self.config_manager = ConfigurationManager(config_file)
        self.fs_monitor = FilesystemMonitor()
        self.remote_hosts = []
        self.global_server_locks = []
        self.destinations = []
        self.config_manager.get_instance(config_file).load()
        self.logger = Logger()
        self.logger.set_level(
            self.config_manager.get_instance(config_file)
            .config.get("loglevel", "INFO")
            .upper()
        )
        # Set up Sentry for error logging
        setup_sentry(
            self.logger,
            self.config_manager.get_instance(config_file).config.get(
                "SENTRY_DSN", None
            ),
        )
        self.full_sync = full_sync  # Full sync flag
        self.web_control = None

    def add_to_global_server_locks(self, server):
        """Add a lock to the global server locks"""
        # Only add the lock if it doesn't already exist
        if server not in self.global_server_locks:
            self.global_server_locks.append(server)

    def remove_from_global_server_locks(self, server):
        """Remove a lock from the global server locks"""
        # Only remove the lock if it exists
        if server in self.global_server_locks:
            self.global_server_locks.remove(server)

    def setup(self):
        """Set up the application by loading configuration and setting up rsync managers"""
        self.config_manager.load()
        destinations = self.config_manager.get_destinations()

        # Ensure hostname matches the hostname in the configuration file
        self.validate_hostname_config()

        # Set up web control if enabled
        if not self.full_sync:
            host = self.config_manager.get_webcontrol_host()
            port = self.config_manager.get_webcontrol_port()
            secret = self.config_manager.get_webcontrol_secret()
            self.logger.info(f"Setting up web control... at: {host}:{port}")
            self.web_control = WebControl(
                self, host=host, port=port, secret=secret, logger=self.logger
            )
            self.web_control.start()

        # Set up rsync managers and inotify watchers for each destination
        for dest_config in destinations:
            if not dest_config.get("enabled", True):
                self.logger.info(
                    f"Destination {dest_config['destination']} is disabled. Skipping..."
                )
                continue
            # Check if the destination path is already in self.destinations
            for destination in self.destinations:
                if destination.get("path") == dest_config.get("path"):
                    self.logger.error(
                        f"Destination path {dest_config.get('path')} already exists in another destination. Skipping..."
                    )
                    continue
            self.setup_destination(dest_config)

        # If full sync is enabled, sync all files for each destination and exit
        if self.full_sync:
            self.logger.info("Full sync enabled. Syncing all files...")
            for destination in self.destinations:
                self.logger.info(
                    f"Running full sync for destination: {destination['rsync_manager'].destination}"
                )
                destination["rsync_manager"].run()
            sys.exit(0)

    def run(self):
        """Run the application to monitor filesystem events and trigger rsync"""
        for event in self.fs_monitor.event_generator():
            self.fs_monitor.handle_event(event)

            # Check if there are files pending immediate sync
            pending_immediate = len(self.fs_monitor.get_immediate_sync_files())
            pending_regular = len(self.fs_monitor.get_regular_sync_files())
            self.logger.debug(
                f"Pending immediate sync files:  {pending_immediate}, pending regular sync files: {pending_regular}"
            )

            # Update event counts and check queue limits for each destination
            if pending_immediate > 0 or pending_regular > 0:
                self.logger.debug("Checking event queue limits for destinations...")
                for destination in self.destinations:
                    # Call self.manage_destination_event(destination) in a separate thread
                    thread = threading.Thread(
                        target=self.manage_destination_event, args=(destination,)
                    )
                    thread.start()

    def setup_destination(self, dest_config):
        """Set up a destination with an rsync manager and inotify watcher"""
        # Validate path
        path = dest_config.get("path", None)
        self.logger.info(f"Setting up destination: {path}")
        if not validate_path(path):
            self.logger.error(f"Invalid path: {path}, skipping destination...")
            return

        # Validate remote server format
        if "@" not in dest_config.get("destination", ""):
            self.logger.error(
                f"Invalid destination format: {dest_config.get('destination')}, skipping destination..."
            )
            return

        rsync_manager = RsyncManager(
            destination=dest_config.get("destination", ""),
            destination_path=dest_config.get("destination_path", ""),
            options=dest_config.get("options", ""),
            ssh_user=dest_config.get("ssh_user", "root"),
            ssh_key=dest_config.get("ssh_key", None),
            ssh_port=dest_config.get("ssh_port", 22),
            pre_sync_commands_local=dest_config.get("pre_sync_commands_local", []),
            post_sync_commands_local=dest_config.get("post_sync_commands_local", []),
            pre_sync_commands_remote=dest_config.get("pre_sync_commands_remote", []),
            post_sync_commands_remote=dest_config.get("post_sync_commands_remote", []),
        )
        event_queue_limit = dest_config["event_queue_limit"]
        destination_config = {
            "rsync_manager": rsync_manager,
            "event_queue_limit": event_queue_limit,
            "event_count": 0,
            "path": path,
            "control_server_secret": dest_config.get("control_server_secret", None),
            "notify_file_locks": dest_config.get("notify_file_locks", False),
            "use_global_server_lock": dest_config.get("use_global_server_lock", False),
            "web_client": WebClient(
                dest_config.get("destination", "").split("@")[1],
                dest_config.get("control_server_port", 8080),
                dest_config.get("control_server_secret", "secret"),
            ),
            "max_wait_locked": dest_config.get("max_wait_locked", 60),
        }

        # Set filesystem warning time
        self.logger.debug(
            f"Setting warning file open time for {path} to {dest_config.get('warning_file_open_time', 86400)}"
        )
        self.fs_monitor.warning_file_open_time = dest_config.get(
            "warning_file_open_time", 86400
        )

        events = dest_config["events"]
        # Ensure we always monitor IN_OPEN and IN_CLOSE_WRITE
        if "IN_CLOSE_WRITE" not in events:
            events.append("IN_CLOSE_WRITE")
        if "IN_OPEN" not in events:
            events.append("IN_OPEN")
        # If full sync is not enabled, add the path to the inotify watcher since its not needed for full sync
        if not self.full_sync:
            self.fs_monitor.add_watch(path, events)

        # Add the path to the rsync manager
        rsync_manager.add_path(path)

        # Add destination to the list of destinations
        self.remote_hosts.append(dest_config.get("destination").split("@")[1])
        self.destinations.append(destination_config)

    def validate_hostname_config(self):
        """Validate the hostname in the configuration file"""
        hostname = self.config_manager.get_hostname()
        if hostname != os.uname().nodename:
            self.logger.error(
                f"Hostname mismatch: {hostname} in configuration file does not match {os.uname().nodename}"
            )
            sys.exit(1)

    def immediate_sync_files_for_destination(
        self, destination, immediate_sync_files_for_path
    ):
        """Check if we have immedeate sync files for a destination"""
        # Check if we have immedeate sync files
        files_to_sync_paths = [file.path for file in immediate_sync_files_for_path]
        if immediate_sync_files_for_path:
            # Only sync the immediate sync files
            include = "{'" + "','".join(files_to_sync_paths) + "'}"
            destination["rsync_manager"].run(include_list=include)
            self.logger.info(
                f"Immediate sync files detected for destination {destination['rsync_manager'].destination}. Running rsync..."
            )
            # Remove these files from the immediate sync list
            for file in self.fs_monitor.get_immediate_sync_files():
                self.fs_monitor.delete_immediate_sync_file(file)

    def process_regular_sync(self, destination, events):
        """Process regular sync for a destination"""
        # Trigger rsync when event count reaches the limit
        if len(events) >= destination["event_queue_limit"]:
            # Get locked files in the path that have exceeded the max wait time
            should_exclude = self.fs_monitor.check_if_locked_files_exceeded_wait(
                destination.get("path"), destination["max_wait_locked"]
            )
            # Delay rsync if there are open files
            self.logger.info(
                f"Event queue limit reached for destination {destination['rsync_manager'].destination}. Running rsync..."
            )
            # Add files in events to the include list
            include = [event.path for event in events]
            # Should exclude
            exclude = None
            if not should_exclude:
                # Create a list in the format of --exclude={'/path/to/file1','/path/to/file2'}
                exclude = [
                    file.path
                    for file in self.fs_monitor.get_locked_files_for_path(
                        destination.get("path")
                    )
                ]

            # Check if we should notify of remote locks
            webc = destination.get("web_client", None)
            if destination.get("notify_file_locks", False):
                # Notify remote server of locked files
                if webc is not None:
                    webc.add_file_to_locked_files(include)
            
            destination["rsync_manager"].run(exclude_list=exclude, include_list=include)
            # Remove these files from the regular sync list
            for file in events:
                self.fs_monitor.delete_regular_sync_file(file.path)

            # Clear locked files
            if destination.get("notify_file_locks", False):
                if webc is not None:
                    webc.remove_locked_files(include)

    def manage_destination_event(self, destination):
        """Manage events for a destination"""
        # Check if the path is a subdirectory of the destination
        if destination is None:
            self.logger.error("Destination is None, skipping...")
            return
        # While destination server is in global server locks, wait
        waited_for = 0
        while (
            destination["rsync_manager"].destination.split("@")[1]
            in self.global_server_locks
        ):
            self.logger.info(
                f"Destination {destination['rsync_manager'].destination} is locked. Waiting..."
            )
            time.sleep(30)
            waited_for += 30
            if waited_for >= 3600:
                self.logger.error(
                    f"Destination {destination['rsync_manager'].destination} has been locked for too long. Skipping..."
                )
                return

        # Add destination to global server locks if needed
        if destination.get("use_global_server_lock", False):
            # Add destination to global server locks
            destination.get("web_client").add_to_global_server_lock(
                self.config_manager.get_hostname()
            )
            self.add_to_global_server_locks(
                destination["rsync_manager"].destination.split("@")[1]
            )

        # Check destination
        self.logger.debug(f"Checking destination: {destination}")

        # Check if we have immedeate sync files
        self.immediate_sync_files_for_destination(
            destination, self.fs_monitor.get_immediate_sync_files()
        )
        # Process regular sync
        self.process_regular_sync(destination, self.fs_monitor.get_regular_sync_files())
