import os
import sys
import time
import threading
import datetime
from .utils.logs import Logger
from .web_app import WebControl
from .utils.rsync import RsyncManager
from .utils.sentry import setup_sentry
from .utils.utils import validate_path
from .utils.filesystem import FilesystemMonitor
from .utils.configuration import ConfigurationManager
from .utils.web_client import WebClient
from .utils.constants import (
    WAIT_1H,
    WAIT_30_SEC,
    WAIT_60_SEC,
    DEFAULT_FULL_SYNC,
    ZERO,
    DEFAULT_MAX_STATS,
    EXCLUDE_ALL,
    CHECK_THREADS_SLEEP,
    WARNING_MAX_TIME_FILE_OPEN,
    DEFAULT_SSH_PORT,
    DEFAULT_WEB_SERVER_PORT,
)


class SyncApplication:
    """Main application class to monitor filesystem events and trigger rsync"""

    def __init__(self, config_file, full_sync=False):
        """Initialize the application with a configuration file"""
        self.config_manager = ConfigurationManager(config_file)
        self.fs_monitor = FilesystemMonitor()
        self.remote_hosts = []
        self.global_server_locks = []
        self.destinations = []
        self.files_to_delete_after_sync_regular = []
        self.files_to_delete_after_sync_immediate = []
        self.syncs_running_currently = []
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
        self.max_stats = self.config_manager.get_instance(config_file).config.get(
            "max_stats", DEFAULT_MAX_STATS
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
                self.logger.debug(
                    f"Destination {dest_config['destination']} is disabled. Skipping..."
                )
                continue
            # Check if the destination path is already in self.destinations
            for destination in self.destinations:
                destination_matches_path = destination.get("path") == dest_config.get("path")
                destination_matches_dest = destination.get("destination") == dest_config.get("destination")
                if destination_matches_path and destination_matches_dest:
                    self.logger.error(
                        f"Destination path {dest_config.get('path')} already exists in another destination. Skipping..."
                    )
                    continue
            self.setup_destination(dest_config)

        # If full sync is enabled, sync all files for each destination and exit
        if self.full_sync:
            self.logger.debug("Full sync enabled. Syncing all files...")
            for destination in self.destinations:
                self.logger.debug(
                    f"Running full sync for destination: {destination['rsync_manager'].destination}"
                )
                destination["rsync_manager"].run(exclude_list=destination.get("files_to_exclude", []))
            sys.exit(ZERO)
        # Run check locations that need full sync in a separate thread
        self.run_check_locations_that_need_full_sync_in_thread()

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
                threads = []
                for destination in self.destinations:
                    # Call self.manage_destination_event(destination) in a separate thread
                    # Check if destination is locked, don't run if it is
                    if not destination.get("locked_on_sync"):
                        thread = threading.Thread(
                            target=self.manage_destination_event, args=(destination,)
                        )
                        thread.start()
                        threads.append(thread)
                # Wait for all threads to finish
                for thread in threads:
                    thread.join()

                # Clean all files that need to be deleted after sync
                deleted_files_reg, deleted_files_imm = [], []
                for file in self.files_to_delete_after_sync_regular:
                    if file.synced_successfully:
                        self.fs_monitor.delete_regular_sync_file(file)
                        deleted_files_reg.append(file)
                for file in self.files_to_delete_after_sync_immediate:
                    if file.synced_successfully:
                        self.fs_monitor.delete_immediate_sync_file(file)
                        deleted_files_imm.append(file)

                # Remove files from the list
                for file in deleted_files_reg:
                    self.files_to_delete_after_sync_regular.remove(file)
                for file in deleted_files_imm:
                    self.files_to_delete_after_sync_immediate.remove(file)

    def setup_destination(self, dest_config):
        """Set up a destination with an rsync manager and inotify watcher"""
        # Validate path
        path = dest_config.get("path", None)
        destination_path = dest_config.get("destination", "")
        self.logger.info(f"Setting up destination: {path}")
        if not validate_path(path):
            self.logger.error(f"Invalid path: {path}, skipping destination...")
            return
        # If destination is disabled, skip
        if not dest_config.get("enabled", True):
            self.logger.debug(
                f"Destination {dest_config['destination']} is disabled. Skipping..."
            )
            return

        # Validate remote server format
        if "@" not in destination_path:
            self.logger.error(
                f"Invalid destination format: {destination_path}, skipping destination..."
            )
            return

        rsync_manager = RsyncManager(
            destination=destination_path,
            destination_path=dest_config.get("destination_path", ""),
            options=dest_config.get("options", ""),
            ssh_user=dest_config.get("ssh_user", "root"),
            ssh_key=dest_config.get("ssh_key", None),
            ssh_port=dest_config.get("ssh_port", DEFAULT_SSH_PORT),
            pre_sync_commands_local=dest_config.get("pre_sync_commands_local", []),
            post_sync_commands_local=dest_config.get("post_sync_commands_local", []),
            pre_sync_commands_remote=dest_config.get("pre_sync_commands_remote", []),
            post_sync_commands_remote=dest_config.get("post_sync_commands_remote", []),
            pre_sync_commands_checkexit_local=dest_config.get(
                "pre_sync_commands_checkexit_local", []
            ),
            post_sync_commands_checkexit_local=dest_config.get(
                "post_sync_commands_checkexit_local", []
            ),
            pre_sync_commands_checkexit_remote=dest_config.get(
                "pre_sync_commands_checkexit_remote", []
            ),
            post_sync_commands_checkexit_remote=dest_config.get(
                "post_sync_commands_checkexit_remote", []
            ),
        )
        event_queue_limit = dest_config["event_queue_limit"]
        destination_config = {
            "rsync_manager": rsync_manager,
            "event_queue_limit": event_queue_limit,
            "event_count": 0,
            "path": path,
            "locked_on_sync": False,
            "extensions_to_ignore": dest_config.get("extensions_to_ignore", []),
            "control_server_secret": dest_config.get("control_server_secret", None),
            "notify_file_locks": dest_config.get("notify_file_locks", False),
            "use_global_server_lock": dest_config.get("use_global_server_lock", False),
            "statistics": [],
            "files_to_exclude": dest_config.get("files_to_exclude", []),
            "location_last_full_sync": None,
            "web_client": WebClient(
                destination_path.split("@")[1],
                dest_config.get("control_server_port", DEFAULT_WEB_SERVER_PORT),
                dest_config.get("control_server_secret", "secret"),
            ),
            "max_wait_locked": dest_config.get("max_wait_locked", WAIT_60_SEC),
        }

        # Set filesystem warning time
        self.logger.debug(
            f"Setting warning file open time for {path} to {dest_config.get('warning_file_open_time', WARNING_MAX_TIME_FILE_OPEN)}"
        )
        self.fs_monitor.warning_file_open_time = dest_config.get(
            "warning_file_open_time", WARNING_MAX_TIME_FILE_OPEN
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
        self.remote_hosts.append(destination_path.split("@")[1])
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
        # Grab extensions to ignore
        extensions_to_ignore = destination.get("extensions_to_ignore", [])
        destination_path = destination.get("path")
        # Remove files with extensions to ignore
        filtered_files = []
        for file in immediate_sync_files_for_path:
            if file.path.split(".")[-1] in extensions_to_ignore:
                self.logger.debug(f"Ignoring file {file.path} from immediate sync")
            else:
                self.logger.debug(f"Adding file {file.path} to immediate sync")
                filtered_files.append(file)
        # Check if we have immedeate sync files
        files_to_sync_paths = [file.path for file in filtered_files]
        if immediate_sync_files_for_path:
            # Only sync the immediate sync files
            time_sync_start = time.time()
            self.logger.info(
                f"Immediate sync files detected for destination {destination['rsync_manager'].destination}. Running rsync..."
            )
            # ensure_excludes should be EXCLUDE_ALL + destination.get("files_to_exclude", [])
            ensure_excludes = destination.get("files_to_exclude", [])
            ensure_excludes.extend(EXCLUDE_ALL)
            rsync_result, process_result = destination["rsync_manager"].run(
                exclude_list=EXCLUDE_ALL, include_list=files_to_sync_paths
            )
            if rsync_result:
                self.logger.info(
                    f"Rsync completed successfully for destination {destination['rsync_manager'].destination}"
                )
            else:
                self.logger.error(
                    f"Rsync failed for destination {destination['rsync_manager'].destination}, not clearing pending files..."
                )
                self.statistics_generator(
                    destination,
                    self.fs_monitor.get_regular_sync_files(destination_path),
                    self.fs_monitor.get_immediate_sync_files(destination_path),
                    sync_result=rsync_result,
                    log_type="immediate",
                )
                return
            # Remove these files from the immediate sync list
            for file in self.fs_monitor.get_immediate_sync_files():
                file.synced_successfully = True
                file.synced_time = time_sync_start
                self.files_to_delete_after_sync_immediate.append(file)
            self.statistics_generator(
                destination,
                self.fs_monitor.get_regular_sync_files(destination_path),
                self.fs_monitor.get_immediate_sync_files(destination_path),
                sync_result=rsync_result,
                log_type="regular"
            )

    def process_regular_sync(self, destination, events):
        """Process regular sync for a destination"""
        # Trigger rsync when event count reaches the limit
        time_sync_start = time.time()
        destination_path = destination.get("path")
        if len(events) >= destination["event_queue_limit"]:
            # Get locked files in the path that have exceeded the max wait time
            should_exclude = self.fs_monitor.clear_locks_exceeded_wait(
                destination_path, destination["max_wait_locked"]
            )
            should_exclude_paths = [file.path for file in should_exclude]
            # Delay rsync if there are open files
            self.logger.debug(
                f"Event queue limit reached for destination {destination['rsync_manager'].destination}. Running rsync..."
            )

            # Add files in events to the include list
            include = [event.path for event in events]
            # Include all events except for the ones that are locked
            files_to_sync = []
            for file in events:
                if file.path not in should_exclude_paths:
                    files_to_sync.append(file.path)

            # Check if we should notify of remote locks
            webc = destination.get("web_client", None)
            if destination.get("notify_file_locks", False):
                # Notify remote server of locked files
                if webc is not None:
                    webc.add_file_to_locked_files(include)
            # ensure_excludes should be EXCLUDE_ALL + destination.get("files_to_exclude", [])
            ensure_excludes = destination.get("files_to_exclude", [])
            ensure_excludes.extend(EXCLUDE_ALL)
            rsync_result, app_code_result = destination["rsync_manager"].run(
                exclude_list=ensure_excludes, include_list=include
            )
            if rsync_result:
                self.logger.info(
                    f"Rsync completed successfully for destination {destination['rsync_manager'].destination}"
                )
            else:
                self.logger.error(
                    f"Rsync failed for destination {destination['rsync_manager'].destination}, not clearing pending files..."
                )
                self.statistics_generator(
                    destination,
                    self.fs_monitor.get_regular_sync_files(destination_path),
                    self.fs_monitor.get_immediate_sync_files(destination_path),
                    sync_result=rsync_result,
                    log_type="regular",
                )
                return
            # Remove these files from the regular sync list
            for file in events:
                file.synced_successfully = True
                file.synced_time = time_sync_start
                self.files_to_delete_after_sync_regular.append(file)

            # Clear locked files
            if destination.get("notify_file_locks", False):
                if webc is not None:
                    webc.remove_locked_files(include)
            self.statistics_generator(
                destination,
                self.fs_monitor.get_regular_sync_files(destination_path),
                self.fs_monitor.get_immediate_sync_files(destination_path),
                sync_result=rsync_result,
                log_type="regular",
            )

    def manage_destination_event(self, destination):
        """Manage events for a destination"""
        # Check if the path is a subdirectory of the destination
        if destination is None:
            self.logger.error("Destination is None, skipping...")
            return
        if destination.get("locked_on_sync"):
            self.logger.debug(
                f"Destination {destination['rsync_manager'].destination} is locked. Sleeping 30 seconds until lock is clear..."
            )
            time.sleep(WAIT_30_SEC)
            return

        # While destination server is in global server locks, wait
        waited_for = ZERO
        while (
            destination["rsync_manager"].destination.split("@")[1]
            in self.global_server_locks
        ):
            self.logger.debug(
                f"Destination {destination['rsync_manager'].destination} is locked. Waiting..."
            )
            time.sleep(WAIT_30_SEC)
            waited_for += WAIT_30_SEC
            if waited_for >= WAIT_1H:
                self.logger.error(
                    f"Destination {destination['rsync_manager'].destination} has been locked for too long. Skipping..."
                )
                return

        destination_path = destination.get("path")

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
        # Grab extensions to ignore
        extensions_to_ignore = destination.get("extensions_to_ignore", [])
        self.logger.debug(f"Extensions to ignore: {extensions_to_ignore}")
        # Remove files with those extensions from the regular sync list and immediate sync list
        for file in self.fs_monitor.get_regular_sync_files(destination_path):
            if file.extension in extensions_to_ignore:
                self.logger.debug(
                    f"Removing file {file.path} from regular sync as it has an extension to ignore"
                )
                self.fs_monitor.delete_regular_sync_file(file.path)
        for file in self.fs_monitor.get_immediate_sync_files(destination_path):
            if file.extension in extensions_to_ignore:
                self.logger.debug(
                    f"Removing file {file.path} from immediate sync as it has an extension to ignore"
                )
                self.fs_monitor.delete_immediate_sync_file(file)

        destination["locked_on_sync"] = True
        time_started = time.time()
        # Check if we have immedeate sync files
        self.immediate_sync_files_for_destination(
            destination,
            self.fs_monitor.get_immediate_sync_files(destination_path),
        )
        # Process regular sync
        self.process_regular_sync(
            destination, self.fs_monitor.get_regular_sync_files(destination_path)
        )
        # After every sync clear pending files
        self.fs_monitor.delete_regular_sync_files_for_path(
            destination_path, time_started
        )
        self.fs_monitor.delete_immediate_sync_files_for_path(
            destination_path, time_started
        )
        destination["locked_on_sync"] = False

    def statistics_generator(
        self,
        destination=None,
        regular_sync_files=None,
        immediate_sync_files=None,
        sync_result=False,
        log_type="regular",
    ):
        """Generator to get statistics for each destination"""
        if destination is None:
            return None
        stats = {
            "path": destination.get("path"),
            "regular_sync_files": regular_sync_files,
            "immediate_sync_files": immediate_sync_files,
            "regular_sync_files_count": len(regular_sync_files),
            "immediate_sync_files_count": len(immediate_sync_files),
            "event_queue_limit": destination.get("event_queue_limit"),
            "event_count": len(regular_sync_files) + len(immediate_sync_files),
            # Get current time
            "last_sync": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "last_full_sync": destination.get("location_last_full_sync", None),
            "result": sync_result,
            "log_type": log_type,
        }
        # If we have more than 10 statistics, remove the oldest one
        if len(destination["statistics"]) >= self.max_stats:
            destination["statistics"].pop(ZERO)
        destination["statistics"].append(stats)

    def check_locations_that_need_full_sync(self):
        """Check locations that need full sync"""
        while True:
            for destination in self.destinations:
                path = destination.get("path")
                if destination.get("location_last_full_sync") is None:
                    self.logger.debug(
                        f"Location {path} has not been synced. Running full sync..."
                    )
                    ensure_excludes = destination.get("files_to_exclude", [])
                    destination["rsync_manager"].run(exclude_list=ensure_excludes)
                    destination["location_last_full_sync"] = datetime.datetime.now()
                else:
                    # Check if we need to run a full sync
                    last_full_sync = destination.get("location_last_full_sync")
                    current_time = datetime.datetime.now()
                    time_diff = current_time - last_full_sync
                    full_sync_interval = destination.get("full_sync_interval", DEFAULT_FULL_SYNC)
                    if time_diff.minute >= destination.get(
                        "full_sync_interval", DEFAULT_FULL_SYNC
                    ):  # 60 minutes
                        self.logger.debug(
                            f"Location {path} has not been synced in over {full_sync_interval} minutes. Running full sync..."
                        )
                        destination["rsync_manager"].run(exclude_list=ensure_excludes)
                        destination["location_last_full_sync"] = current_time
            self.logger.debug(
                f"Sleeping for {CHECK_THREADS_SLEEP} seconds before checking locations that need full sync..."
            )
            time.sleep(CHECK_THREADS_SLEEP)

    def run_check_locations_that_need_full_sync_in_thread(self):
        """Run check locations that need full sync in a separate thread"""
        thread = threading.Thread(target=self.check_locations_that_need_full_sync)
        thread.start()
        return thread
