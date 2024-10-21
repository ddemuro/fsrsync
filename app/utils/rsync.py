import subprocess
from .logs import Logger
from .utils import run_command, pipe_processes


class RsyncManager:
    """Class to manage rsync operations"""

    def __init__(
        self,
        destination,
        options,
        ssh_key=None,
        ssh_port=None,
        pre_sync_commands=None,
        post_sync_commands=None,
    ):
        """Initialize the rsync manager with destination and options"""
        self.destination = destination
        self.options = options
        self.ssh_key = None
        self.ssh_port = None
        self.paths_to_monitor = []
        self.pre_sync_commands = pre_sync_commands or []
        self.post_sync_commands = post_sync_commands or []
        self.logger = Logger()

    def add_path(self, path):
        """Add a path to monitor for rsync"""
        self.paths_to_monitor.append(path)

    def run(self, exclude_list=None, include_list=None):
        """Run rsync with the specified options, paths, and destination"""
        # Run pre-sync commands
        if self.pre_sync_commands:
            print("Running pre-sync commands...")
            run_command(self.pre_sync_commands)

        paths_str = " ".join(self.paths_to_monitor)
        # Add SSH key and port options if provided
        if self.ssh_key and self.ssh_port:
            self.options += f" -e 'ssh -i {self.ssh_key} -p {self.ssh_port}'"
        # Add SSH port option if provided
        if self.ssh_port:
            self.options += f" -e 'ssh -p {self.ssh_port}'"
        # Add SSH key option if provided
        if self.ssh_key:
            self.options += f" -e 'ssh -i {self.ssh_key}'"
        if exclude_list:
            self.options += f" {exclude_list}"
        if include_list:
            self.options += f" {include_list}"
        # Construct rsync command
        rsync_command = f"rsync {self.options} {paths_str} {self.destination}"
        try:
            subprocess.run(rsync_command, shell=True, check=True)
            self.logger.info(f"Synced with rsync: {rsync_command}")
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Rsync failed: {e}")

        # Run post-sync commands
        if self.post_sync_commands:
            print("Running post-sync commands...")
            run_command(self.post_sync_commands)
