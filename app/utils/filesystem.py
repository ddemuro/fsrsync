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


class LockedFile:
    """Class to represent a locked file"""

    def __init__(self, path, logger):
        self.path = path
        self.logger = logger
        self.start_time = time.time()

    def how_long_locked(self):
        """Return the time in seconds since the file was locked"""
        return time.time() - self.start_time

    def __str__(self):
        return f"LockedFile(path={self.path})"


class FilesystemMonitor:
    """Class to monitor filesystem events using inotify"""

    def __init__(self):
        """Initialize the filesystem monitor"""
        self.inotify_watcher = INotify()
        self.watches = {}  # Keep track of paths being watched
        self.open_files = set()  # Track files that are open for writing
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

        # Track open files for writing
        if "OPEN" in type_names:
            self.logger.info(f"File opened: {full_path}")
            self.open_files.add(LockedFile(full_path, self.logger))
        elif "CLOSE_WRITE" in type_names:
            self.logger.info(f"File closed: {full_path}")
            self.open_files = {f for f in self.open_files if f.path != full_path}

        return type_names, path, filename

    def has_open_files(self):
        """Check if there are open files for writing"""
        return len(self.open_files) > 0

    def check_if_locked_files_in_path_exceeded_wait(self, path,
                                                    max_wait_locked):
        """Check if a file has been locked for too long"""
        for file in self.open_files:
            if file.path == path and file.how_long_locked() > max_wait_locked:
                return False
        return True

    def get_locked_files_for_path(self, path):
        """Return locked files in a given path"""
        return [file for file in self.open_files if file.path.startswith(path)]
