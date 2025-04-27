import time
from .logs import Logger
from .utils import fix_path_slashes, is_file_open
from inotify_simple import INotify, flags
import threading
from threading import Lock

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
    max_tracked_files = 500000

    def __init__(self, time_between_events=5, max_tracked_files=500000):
        """Initialize the filesystem monitor"""
        self.inotify_watcher = INotify()
        self.watches = {}  # Keep track of paths being watched
        self.open_files = set()  # Track files that are open for writing
        self.immediate_sync = set()  # Track files that need immediate sync
        self.regular_sync = set()  # Track files that need regular sync
        self.logger = Logger()
        self.time_between_events = time_between_events  # Time between events in seconds
        self.max_tracked_files = max_tracked_files
        self.open_files_lock = Lock()
        self.immediate_sync_lock = Lock()
        self.regular_sync_lock = Lock()

    def __del__(self):
        """Destructor to close inotify watcher"""
        try:
            if hasattr(self, 'inotify_watcher'):
                self.inotify_watcher.close()
        except Exception as e:
            # Log the error but don't raise it
            if hasattr(self, 'logger'):
                self.logger.error(f"Error closing inotify_watcher: {e}")

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
            events = self.inotify_watcher.read(timeout=5000,
                                               read_delay=self.time_between_events)
            for event in events:
                yield event

    def handle_event(self, event):
        """Handle a filesystem event with improved handling of complex sequences"""
        wd = event.wd
        path = self.watches.get(wd, "Unknown path")
        event_mask = event.mask
        type_names = [str(flag) for flag in flags.from_mask(event_mask)]
        filename = event.name or ""
        full_path = f"{path}/{filename}" if filename else path
        full_path = fix_path_slashes(full_path)

        # Track specific types of events for this file path
        event_types = []
        
        # Check for specific event types
        if event_mask & EVENT_MAP["IN_CREATE"]:
            event_types.append("CREATE")
            
        if event_mask & EVENT_MAP["IN_OPEN"] and not event_mask & EVENT_MAP["IN_ISDIR"]:
            event_types.append("OPEN")
            
        if event_mask & EVENT_MAP["IN_CLOSE_WRITE"]:
            event_types.append("CLOSE_WRITE")
            
        if event_mask & EVENT_MAP["IN_CLOSE_NOWRITE"]:
            event_types.append("CLOSE_NOWRITE")
            
        if event_mask & EVENT_MAP["IN_DELETE"]:
            event_types.append("DELETE")
            
        if event_mask & EVENT_MAP["IN_MOVED_FROM"]:
            event_types.append("MOVED_FROM")
            
        if event_mask & EVENT_MAP["IN_MOVED_TO"]:
            event_types.append("MOVED_TO")
            
        # Log all events
        self.logger.info(f"Events detected: {event_types} on {full_path}")
        
        # Handle complex sequences more robustly
        
        # Handle creation - add to immediate sync unless explicitly deleted
        if "CREATE" in event_types and "DELETE" not in event_types:
            self.logger.debug(f"File created: {full_path}, added to immediate sync")
            with self.immediate_sync_lock:
                self.add_immediate_sync_file(File(full_path, self.logger))
        
        # Handle file opening - add to locked files
        if "OPEN" in event_types and "IN_ISDIR" not in type_names:
            self.logger.debug(f"File opened: {full_path}")
            with self.open_files_lock:
                self.add_to_locked_files(File(full_path, self.logger))
        
        # Handle file closing - remove from locked and add to appropriate sync
        if "CLOSE_WRITE" in event_types or "CLOSE_NOWRITE" in event_types:
            with self.open_files_lock:
                was_open = False
                for file in self.open_files:
                    if file.path == full_path:
                        was_open = True
                        break
                        
                if was_open:
                    self.logger.debug(f"File closed: {full_path}")
                    self.delete_locked_file(full_path)
                    
                    # Only add to immediate sync if it was closed with writing
                    if "CLOSE_WRITE" in event_types and "DELETE" not in event_types:
                        with self.immediate_sync_lock:
                            self.add_immediate_sync_file(File(full_path, self.logger))
        
        # Handle deletions - remove from all tracking
        if "DELETE" in event_types or "MOVED_FROM" in event_types:
            self.logger.debug(f"File deleted or moved from: {full_path}")
            with self.open_files_lock:
                self.delete_locked_file(full_path)
            with self.immediate_sync_lock:
                self.delete_immediate_sync_file(full_path)
            with self.regular_sync_lock:
                self.delete_regular_sync_file(full_path)
        
        # Handle moves - track as regular sync for destination
        if "MOVED_TO" in event_types:
            self.logger.debug(f"File moved to: {full_path}")
            with self.regular_sync_lock:
                self.add_regular_sync_file(File(full_path, self.logger))
        
        # Perform periodic maintenance
        self.log_files_opened_for_too_long()
        self.check_if_file_still_locked()

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

    def check_if_file_still_locked(self):
        """Check if a file is still locked"""
        files_to_remove = []
        for file in self.open_files:
            if not is_file_open(file.path):
                files_to_remove.append(file)
        for file in files_to_remove:
            self.open_files.discard(file)
            self.logger.debug(f"File {file.path} removed from locked files, it is no longer open")

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
        locked_files = []
        for file in self.open_files:
            if path:
                if file.path.startswith(path):
                    locked_files.append(file)
            else:
                locked_files.append(file)
        return locked_files

    def get_locked_files(self):
        """Return locked files"""
        return self.open_files

    def get_immediate_sync_files(self, path_filter=None):
        """Return files that need immediate sync"""
        imm_sync = []
        for f in self.immediate_sync:
            if path_filter:
                if f.path.startswith(path_filter):
                    imm_sync.append(f)
            else:
                imm_sync.append(f)
        return imm_sync

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
        reg_sync = []
        for f in self.regular_sync:
            if path_filter:
                if f.path.startswith(path_filter):
                    reg_sync.append(f)
            else:
                reg_sync.append(f)
        return reg_sync

    def clear_regular_sync_files(self, path_filter=None):
        """Clear files that need regular sync"""
        if path_filter:
            files_to_clear = []
            for f in self.regular_sync:
                if path_filter:
                    if f.path.startswith(path_filter):
                        files_to_clear.append(f)
                else:
                    files_to_clear.append(f)
            for f in files_to_clear:
                self.regular_sync.discard(f)
        else:
            self.regular_sync.clear()

    def delete_fs_event_for_path(self, path):
        """Delete filesystem events for a given path"""
        self.delete_regular_sync_files_for_path(path)
        self.delete_immediate_sync_files_for_path(path)

    def delete_regular_sync_files_for_path(self, path, delete_up_to_time=None):
        """Delete files that need regular sync in a given path"""
        self.logger.debug(f"Deleting files in {path} from regular sync, with delete_up_to_time={delete_up_to_time}")
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
        self.logger.debug(f"Deleting files in {path} from immediate sync, with delete_up_to_time={delete_up_to_time}")
        to_remove = []
        for f in self.immediate_sync:
            if f.path.startswith(path):
                if delete_up_to_time is None:
                    self.logger.debug(f"File {f} has no delete_up_to_time")
                    to_remove.append(f)
                elif f.start_time < delete_up_to_time:
                    self.logger.debug(f"File {f} has start time {f.start_time} and delete_up_to_time {delete_up_to_time}")
                    to_remove.append(f)
        for f in to_remove:
            self.immediate_sync.discard(f)
        self.logger.debug(f"Files in {path} removed from immediate sync")

    def delete_regular_sync_file(self, path, delete_up_to_time=None):
        """Delete file from regular sync"""
        self.logger.debug(f"Deleting file {path} from regular sync, with delete_up_to_time={delete_up_to_time}")
        to_remove = []
        for f in self.regular_sync:
            if f.path == path:
                if delete_up_to_time is None:
                    self.logger.debug(f"File {f} has no delete_up_to_time")
                    to_remove.append(f)
                elif f.start_time < delete_up_to_time:
                    self.logger.debug(f"File {f} has start time {f.start_time} and delete_up_to_time {delete_up_to_time}")
                    to_remove.append(f)
        for f in to_remove:
            self.regular_sync.discard(f)
        self.logger.debug(f"File {path} removed from regular sync")

    def add_regular_sync_file(self, file):
        """Add file to regular sync with size limit"""
        with self.regular_sync_lock:
            # Check size limit before adding
            if len(self.regular_sync) >= self.max_tracked_files:
                # Remove oldest file (based on start_time)
                oldest_file = min(self.regular_sync, key=lambda f: f.start_time, default=None)
                if oldest_file:
                    self.regular_sync.discard(oldest_file)
                    self.logger.warning(f"Removed oldest file {oldest_file.path} from regular sync due to size limit")
            
            # Now add the new file (after checking if it already exists)
            for f in self.regular_sync:
                if f.path == file.path:
                    self.logger.debug(f"File {file} already in regular sync")
                    return
            self.regular_sync.add(file)
            self.logger.debug(f"File {file} added to regular sync")

    def add_immediate_sync_file(self, file):
        """Add file to immediate sync"""
        # Check if path already in immediate sync files
        for f in self.immediate_sync:
            if f.path == file.path:
                self.logger.debug(f"File {file} already in immediate sync")
                return
        self.immediate_sync.add(file)
        self.logger.debug(f"File {file} added to immediate sync")

    def add_to_locked_files(self, file):
        """Add file to locked files"""
        # Return if file already exists
        for f in self.open_files:
            if f.path == file.path:
                self.logger.debug(f"File {file} already in locked files")
                return
        self.open_files.add(file)
        self.logger.debug(f"File {file} added to locked files")

    def get_all_events_for_path(self, path):
        """Return all events for a given path"""
        return self.get_immediate_sync_files(
            path
        ) + self.get_regular_sync_files(path)

    def clear_all_sync_files(self):
        """Clear all files that need sync"""
        self.clear_immediate_sync_files()
        self.clear_regular_sync_files()
        self.clear_locked_files()
        self.logger.info("All sync files cleared")
