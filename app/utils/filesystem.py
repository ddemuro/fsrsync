import time
from .logs import Logger
from inotify_simple import INotify, flags
from utils.lockedmanager import PendingLocked


# Map human-readable event names to inotify constants
EVENT_MAP = {
    "IN_CREATE": flags.CREATE,
    "IN_MODIFY": flags.MODIFY,
    "IN_DELETE": flags.DELETE,
    "IN_OPEN": flags.OPEN,
    "IN_CLOSE_WRITE": flags.CLOSE_WRITE,
}


class File:
    """Class to represent a locked file"""

    def __init__(self, path, logger):
        self.path = path
        self.logger = logger
        self.start_time = time.time()

    def how_long_locked(self):
        """Return the time in seconds since the file was locked"""
        return time.time() - self.start_time

    def __str__(self):
        return f"File(path={self.path})"


class FilesystemMonitor:
    """Class to monitor filesystem events using inotify"""

    def __init__(self):
        """Initialize the filesystem monitor"""
        self.inotify_watcher = INotify()
        self.watches = {}  # Keep track of paths being watched
        self.open_files = set()  # Track files that are open for writing
        self.immediate_sync = set()  # Track files that need immediate sync
        self.regular_sync = set()  # Track files that need regular sync
        self.logger = Logger()

    def add_watch(self, path, events):
        """Add a watch for events on a given path"""
        event_mask = 0
        for event in events:
            if event in EVENT_MAP:
                event_mask |= EVENT_MAP[event]

        wd = self.inotify_watcher.add_watch(path, event_mask)
        self.watches[wd] = path
        self.logger.info(f"Monitoring {path} for events: {events}")

    def event_generator(self):
        """Generator to yield filesystem events"""
        while True:
            events = self.inotify_watcher.read(timeout=1000)
            for event in events:
                yield event

    def handle_event(self, event):
        """Handle a filesystem event and return the event type, path, and filename"""
        wd = event.wd
        path = self.watches.get(wd, "Unknown path")
        type_names = [str(flag) for flag in flags.from_mask(event.mask)]
        filename = event.name or ""

        full_path = f"{path}/{filename}" if filename else path

        self.logger.info(f"Event detected: {type_names} on {path}/{filename}")

        # Track open files for writing
        if "OPEN" in type_names:
            self.logger.info(f"File opened: {full_path}")
        elif "CLOSE_WRITE" in type_names:
            self.logger.info(f"File closed: {full_path}")
            # Remove file from open files
            self.open_files = {f for f in self.open_files if f.path != full_path}
            self.add_immediate_sync_file(File(full_path, self.logger))
        self.add_regular_sync_file(File(full_path, self.logger))

    def has_open_files(self):
        """Check if there are open files for writing"""
        return len(self.open_files) > 0

    def check_if_locked_files_in_path_exceeded_wait(self, path, max_wait_locked):
        """Check if a file has been locked for too long"""
        for file in self.open_files:
            if file.path == path and file.how_long_locked() > max_wait_locked:
                return False
        return True

    def get_locked_files_for_path(self, path):
        """Return locked files in a given path"""
        return [file for file in self.open_files if file.path.startswith(path)]

    def get_immediate_sync_files(self):
        """Return files that need immediate sync"""
        return self.immediate_sync

    def get_immediate_sync_files_for_path(self, path):
        """Return files that need immediate sync in a given path"""
        return [file for file in self.immediate_sync if file.startswith(path)]

    def clear_immediate_sync_files(self):
        """Clear files that need immediate sync"""
        self.immediate_sync.clear()

    def detete_immidiate_sync_file(self, file):
        """Delete file from immediate sync"""
        self.immediate_sync = {f for f in self.immediate_sync if f != file}
        self.logger.info(f"File {file} removed from immediate sync")

    def delete_locked_file(self, file):
        """Delete file from locked files using path"""
        self.open_files = {f for f in self.open_files if f.path != file}
        self.logger.info(f"File {file} removed from locked files")

    def clear_locked_files(self):
        """Clear locked files"""
        self.open_files.clear()
        self.logger.info("Locked files cleared")

    def get_regular_sync_files(self):
        """Return files that need regular sync"""
        return self.regular_sync

    def get_regular_sync_files_for_path(self, path):
        """Return files that need regular sync in a given path"""
        return [file for file in self.regular_sync if file.path.startswith(path)]

    def clear_regular_sync_files(self):
        """Clear files that need regular sync"""
        self.regular_sync.clear()

    def delete_regular_sync_file(self, file):
        """Delete file from regular sync"""
        self.regular_sync = {f for f in self.regular_sync if f != file}
        self.logger.info(f"File {file} removed from regular sync")

    def add_regular_sync_file(self, file):
        """Add file to regular sync"""
        # Return if file already exists
        if file in self.regular_sync:
            return
        self.regular_sync.add(file)
        self.logger.info(f"File {file} added to regular sync")

    def add_immediate_sync_file(self, file):
        """Add file to immediate sync"""
        # Return if file already exists
        if file in self.immediate_sync:
            return
        self.immediate_sync.add(file)
        self.logger.info(f"File {file} added to immediate sync")

    def add_to_locked_files(self, file):
        """Add file to locked files"""
        # Return if file already exists
        if file in self.open_files:
            return
        self.open_files.add(file)
        self.logger.info(f"File {file} added to locked files")

    def get_all_events_for_path(self, path):
        """Return all events for a given path"""
        return self.get_immediate_sync_files_for_path(
            path
        ) + self.get_regular_sync_files_for_path(path)

    def clear_all_sync_files(self):
        """Clear all files that need sync"""
        self.clear_immediate_sync_files()
        self.clear_regular_sync_files()
        self.clear_locked_files()
        self.logger.info("All sync files cleared")
