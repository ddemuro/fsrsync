import inotify.adapters
from inotify.constants import IN_CREATE, IN_MODIFY, IN_DELETE

# Map human-readable event names to inotify constants
EVENT_MAP = {
    'IN_CREATE': IN_CREATE,
    'IN_MODIFY': IN_MODIFY,
    'IN_DELETE': IN_DELETE,
    'IN_OPEN': IN_OPEN,
    'IN_CLOSE_WRITE': IN_CLOSE_WRITE
}


class FilesystemMonitor:
    """Class to monitor filesystem events using inotify"""

    def __init__(self):
        """Initialize the filesystem monitor"""
        self.inotify_watcher = inotify.adapters.Inotify()
        self.open_files = set()  # Track files that are open for writing

    def add_watch(self, path, events):
        """Add a watch for events on a given path"""
        event_mask = sum([EVENT_MAP[event] for event in events if event in EVENT_MAP])
        self.inotify_watcher.add_watch(path, mask=event_mask)
        print(f"Monitoring {path} for events: {events}")

    def event_generator(self):
        """Generator to yield filesystem events"""
        return self.inotify_watcher.event_gen(yield_nones=False)

    def handle_event(self, event):
        """Handle a filesystem event and return the event type, path, and filename"""
        (_, type_names, path, filename) = event
        full_path = f"{path}/{filename}"

        # Track open files for writing
        if 'IN_OPEN' in type_names:
            print(f"File opened: {full_path}")
            self.open_files.add(full_path)
        elif 'IN_CLOSE_WRITE' in type_names:
            print(f"File closed: {full_path}")
            self.open_files.discard(full_path)
        return type_names, path, filename

    def has_open_files(self):
        """Check if there are open files for writing"""
        return len(self.open_files) > 0