import os
import time
import threading
from .wrappers import singleton
from .utils import is_file_open
from .constants import WAIT_5_SEC


class LockedFile:
    """Class to represent a locked file"""

    def __init__(self, path, max_wait_locked, logger):
        self.path = path
        self.max_wait_locked = max_wait_locked
        self.logger = logger
        self.start_time = time.time()

    def has_exceeded_wait(self):
        """Check if the file has exceeded the max wait time"""
        return time.time() - self.start_time > self.max_wait_locked

    def is_open(self):
        """Check if the file is open"""
        return is_file_open(f"{self.path}")

    def __str__(self):
        return f"LockedFile(path={self.path}, max_wait_locked={self.max_wait_locked})"


@singleton
class PendingLocked:
    """Class to keep track of pending locked files"""

    def __init__(self, logger):
        self.locked_files = []
        self.exceeded_wait = []
        self.logger = logger

    def create_thread_to_check_locked_files_exceeded_wait(self):
        """Create a thread to check if locked files have exceeded the max wait time"""
        thread = threading.Thread(target=self.check_locked_files)
        thread.daemon = True
        thread.start()

    def add_locked_file(self, path, max_wait_locked):
        """Add a locked file to the list"""
        self.locked_files.append(LockedFile(
            path, max_wait_locked, self.logger))

    def remove_locked_file(self, path):
        """Remove a locked file from the list"""
        self.locked_files = []
        for locked_file in self.locked_files:
            if locked_file.path != path:
                self.locked_files.append(locked_file)

    def has_locked_files(self):
        """Check if there are locked files"""
        return len(self.locked_files) > 0

    def add_exceeded_wait(self, file):
        """Add a file that has exceeded the max wait time"""
        # If file is string, look for the LockedFile object in the list of locked files
        if isinstance(file, str):
            for locked_file in self.locked_files:
                if locked_file.path == file:
                    self.exceeded_wait.append(locked_file)
        # Remove the LockedFile object from the list of locked files
        self.locked_files = [
            locked_file for locked_file in self.locked_files if locked_file.path != file]

    def has_exceeded_wait(self):
        """Check if there are files that have exceeded the max wait time"""
        return len(self.exceeded_wait) > 0

    def check_locked_files(self):
        """Check if any locked files have exceeded the max wait time"""
        for file in self.locked_files:
            exceeded_wait = time.time() - \
                os.path.getmtime(f"{file.path}") > file.max_wait_locked
            if is_file_open(f"{file.path}") and not exceeded_wait:
                continue
            if file not in self.exceeded_wait and exceeded_wait:
                self.logger.debug(
                    f"File {file.path} has exceeded max wait time")
                self.add_exceeded_wait(file)
                self.remove_locked_file(file)

    def check_locked_files_threaded(self):
        """Check if any locked files have exceeded the max wait time"""
        while True:
            self.check_locked_files()
            # Sleep 5 seconds before checking again
            time.sleep(WAIT_5_SEC)

    def is_file_in_exceeded_wait(self, path):
        """Check if a file is in the exceeded wait list"""
        return path in [file.path for file in self.exceeded_wait]

    def is_file_in_locked_files(self, filename):
        """Check if a file is in the locked files list"""
        return filename in [file.path for file in self.locked_files]

    def clear_lockedfiles(self):
        """Clear the list of locked files"""
        self.locked_files.clear()

    def clear_exceeded_wait(self):
        """Clear the list of files that have exceeded the max wait time"""
        self.exceeded_wait.clear()

    def __str__(self):
        return f"PendingLocked(locked_files={self.locked_files}, exceeded_wait={self.exceeded_wait})"
