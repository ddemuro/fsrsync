import time
from .logs import Logger
from .utils import fix_path_slashes
from inotify_simple import INotify, flags


# Map human-readable event names to inotify constants
EVENT_MAP = {
    "IN_ACCESS": flags.ACCESS,
    "IN_CREATE": flags.CREATE,
    "IN_MODIFY": flags.MODIFY,
    "IN_DELETE": flags.DELETE,
    "IN_MOVED_FROM": flags.MOVED_FROM,
    "IN_MOVED_TO": flags.MOVED_TO,
    "IN_MOVE_SELF": flags.MOVE_SELF,
    "IN_DELETE_SELF": flags.DELETE_SELF,
    "IN_OPEN": flags.OPEN,
    "IN_ATTRIB": flags.ATTRIB,
    "IN_CLOSE_NOWRITE": flags.CLOSE_NOWRITE,
    "IN_CLOSE_WRITE": flags.CLOSE_WRITE,
    "IN_ISDIR": flags.ISDIR
}


class File:
    """Class to represent a locked file"""

    def __init__(self, path, logger):
        """Initialize the file with a path"""
        self.path = fix_path_slashes(path)
        # Get the extension if it exists
        if "." in path:
            self.extension = path.split(".")[-1]
        else:
            self.extension = None
        self.logger = logger
        self.start_time = time.time()
        self.successfully_synced = False
        self.synced_time = None

    def how_long_locked(self):
        """Return the time in seconds since the file was locked"""
        return time.time() - self.start_time

    def __str__(self):
        return f"File(path={self.path})"


class FilesystemMonitor:
    """Class to monitor filesystem events using inotify"""
    warning_file_open_time = 86400

    def __init__(self):
        """Initialize the filesystem monitor"""
        self.inotify_watcher = INotify()
        self.watches = {}  # Keep track of paths being watched
        self.open_files = set()  # Track files that are open for writing
        self.immediate_sync = set()  # Track files that need immediate sync
        self.regular_sync = set()  # Track files that need regular sync
        self.logger = Logger()

    def get_aggregated_events(self):
        """Return all events"""
        immediate = [f.path for f in self.immediate_sync]
        regular = [f.path for f in self.regular_sync]
        locked = [f.path for f in self.open_files]
        return {"immediate": immediate, "regular": regular, "locked": locked}

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
            events = self.inotify_watcher.read(timeout=1000, read_delay=100)
            for event in events:
                yield event

    def handle_event(self, event):
        """Handle a filesystem event

        :param event: Event to handle
        :type event: inotify_simple.Event
        """
        wd = event.wd
        path = self.watches.get(wd, "Unknown path")
        event_mask = event.mask
        type_names = [str(flag) for flag in flags.from_mask(event_mask)]
        filename = event.name or ""
        full_path = f"{path}/{filename}" if filename else path
        full_path = fix_path_slashes(full_path)

        self.logger.info(f"Event detected: {type_names} on {full_path}")

        self.log_files_opened_for_too_long()

        if event_mask & EVENT_MAP["IN_CREATE"]:
            self.logger.debug(f"File created: {full_path}, added to immediate sync")
            self.add_immediate_sync_file(File(full_path, self.logger))
            return

        # If IN_OPEN and not ISDIR, add to locked files
        if event_mask & EVENT_MAP["IN_OPEN"] and not event_mask & EVENT_MAP["IN_ISDIR"]:
            self.logger.debug(f"File opened: {full_path}")
            self.add_to_locked_files(File(full_path, self.logger))
            return

        # File closed
        FILE_CLOSED_EVENTS = ["IN_CLOSE_WRITE", "IN_CLOSE_NOWRITE"]
        if any(event_mask & EVENT_MAP[event] for event in FILE_CLOSED_EVENTS):
            if full_path in self.open_files:
                self.logger.debug(f"File closed: {full_path}")
                self.delete_locked_file(full_path)
                self.add_immediate_sync_file(File(full_path, self.logger))
                return

        # All other events
        ALL_OTHER_EVENTS = [
            "IN_ACCESS",
            "IN_MODIFY",
            "IN_DELETE",
            "IN_MOVED_FROM",
            "IN_MOVED_TO",
            "IN_MOVE_SELF",
            "IN_DELETE_SELF",
            "IN_ATTRIB",
            "IN_CLOSE_NOWRITE",
        ]
        if any(event_mask & EVENT_MAP[event] for event in ALL_OTHER_EVENTS):
            self.logger.debug(f"File modified: {full_path}")
            self.add_regular_sync_file(File(full_path, self.logger))

    def log_files_opened_for_too_long(self):
        """Log files that have been locked for too long"""
        for file in self.open_files:
            if file.how_long_locked() > self.warning_file_open_time:
                self.logger.warning(
                    f"File {file.path} has been locked for too long")

    def has_open_files(self):
        """Check if there are open files for writing"""
        return len(self.open_files) > 0

    def check_if_locked_files_exceeded_wait(self, path, max_wait_locked):
        """Check if a file has been locked for too long"""
        for file in self.open_files:
            if file.path == path and file.how_long_locked() > max_wait_locked:
                return False
        return True

    def clear_locks_exceeded_wait(self, path, max_wait_locked):
        """Clear locks that have exceeded the wait time"""
        to_remove = []
        non_exceeded_for_path = []
        for file in self.open_files:
            if file.path.startswith(path) and file.how_long_locked() > max_wait_locked:
                to_remove.append(file)
            if file.path.startswith(path) and file.how_long_locked() <= max_wait_locked:
                non_exceeded_for_path.append(file)
        for file in to_remove:
            self.open_files.discard(file)
            self.logger.debug(f"File {file.path} removed from locked files")
        return non_exceeded_for_path

    def get_locked_files_for_path(self, path):
        """Return locked files in a given path"""
        return [file for file in self.open_files if file.path.startswith(path)]

    def get_locked_files(self):
        """Return locked files"""
        return self.open_files

    def get_immediate_sync_files(self, path_filter=None):
        """Return files that need immediate sync"""
        if path_filter:
            return [file for file in self.immediate_sync if file.path.startswith(path_filter)]
        return self.immediate_sync

    def get_immediate_sync_files_for_path(self, path):
        """Return files that need immediate sync in a given path"""
        return [file for file in self.immediate_sync if file.startswith(path)]

    def clear_immediate_sync_files(self):
        """Clear files that need immediate sync"""
        self.immediate_sync.clear()

    def delete_immediate_sync_file(self, path, delete_up_to_time=None):
        """Delete file from immediate sync"""
        to_remove = []
        for f in self.immediate_sync:
            if f.path == path:
                if delete_up_to_time is None:
                    to_remove.append(f)
                elif f.start_time < delete_up_to_time:
                    to_remove.append(f)
        for f in to_remove:
            self.immediate_sync.discard(f)
        self.logger.debug(f"File {path} removed from immediate sync")

    def delete_locked_file(self, path, delete_up_to_time=None):
        """Delete file from locked files using path"""
        to_remove = []
        for f in self.open_files:
            if f.path == path:
                if delete_up_to_time is None:
                    to_remove.append(f)
                elif f.start_time < delete_up_to_time:
                    to_remove.append(f)
        for f in to_remove:
            self.open_files.discard(f)
        self.logger.debug(f"File {path} removed from locked files")

    def clear_locked_files(self):
        """Clear locked files"""
        self.open_files.clear()
        self.logger.info("Locked files cleared")

    def get_regular_sync_files(self, path_filter=None):
        """Return files that need regular sync"""
        if path_filter:
            return [file for file in self.regular_sync if file.path.startswith(path_filter)]
        return self.regular_sync

    def get_regular_sync_files_for_path(self, path):
        """Return files that need regular sync in a given path"""
        return [file for file in self.regular_sync if file.path.startswith(path)]

    def clear_regular_sync_files(self, path_filter=None):
        """Clear files that need regular sync"""
        if path_filter:
            self.regular_sync = {
                f for f in self.regular_sync if not f.path.startswith(path_filter)}
        else:
            self.regular_sync.clear()

    def delete_fs_event_for_path(self, path):
        """Delete filesystem events for a given path"""
        self.delete_regular_sync_files_for_path(path)
        self.delete_immediate_sync_files_for_path(path)

    def delete_regular_sync_files_for_path(self, path, delete_up_to_time=None):
        """Delete files that need regular sync in a given path"""
        to_remove = []
        for f in self.regular_sync:
            if f.path.startswith(path):
                if delete_up_to_time is None:
                    to_remove.append(f)
                elif f.start_time < delete_up_to_time:
                    to_remove.append(f)
        for f in to_remove:
            self.regular_sync.discard(f)
        self.logger.debug(f"Files in {path} removed from regular sync")

    def delete_immediate_sync_files_for_path(self, path, delete_up_to_time=None):
        """Delete files that need immediate sync in a given path"""
        to_remove = []
        for f in self.immediate_sync:
            if f.path.startswith(path):
                if delete_up_to_time is None:
                    to_remove.append(f)
                elif f.start_time < delete_up_to_time:
                    to_remove.append(f)
        for f in to_remove:
            self.immediate_sync.discard(f)
        self.logger.debug(f"Files in {path} removed from immediate sync")

    def delete_regular_sync_file(self, path, delete_up_to_time=None):
        """Delete file from regular sync"""
        to_remove = []
        for f in self.regular_sync:
            if f.path == path:
                if delete_up_to_time is None:
                    to_remove.append(f)
                elif f.start_time < delete_up_to_time:
                    to_remove.append(f)
        for f in to_remove:
            self.regular_sync.discard(f)
        self.logger.debug(f"File {path} removed from regular sync")

    def add_regular_sync_file(self, file):
        """Add file to regular sync"""
        # Return if file already exists
        for f in self.regular_sync:
            if f.path == file.path:
                return
        self.regular_sync.add(file)
        self.logger.debug(f"File {file} added to regular sync")

    def add_immediate_sync_file(self, file):
        """Add file to immediate sync"""
        # Check if path already in immediate sync files
        for f in self.immediate_sync:
            if f.path == file.path:
                return
        self.immediate_sync.add(file)
        self.logger.debug(f"File {file} added to immediate sync")

    def add_to_locked_files(self, file):
        """Add file to locked files"""
        # Return if file already exists
        for f in self.open_files:
            if f.path == file.path:
                return
        self.open_files.add(file)
        self.logger.debug(f"File {file} added to locked files")

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
