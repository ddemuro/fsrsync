from .logs import Logger
from .utils import run_command
from .ssh_lib import run_ssh_command

class RsyncManager:
    """Class to manage rsync operations"""

    def __init__(
        self,
        destination,
        destination_path,
        options,
        ssh_user=None,
        ssh_key=None,
        ssh_port=None,
        pre_sync_commands_local=None,
        post_sync_commands_local=None,
        pre_sync_commands_remote=None,
        post_sync_commands_remote=None
    ):
        """Initialize the rsync manager with destination and options"""
        self.destination = destination
        self.destination_path = destination_path
        self.options = options
        self.ssh_key = ssh_key
        self.ssh_port = ssh_port
        self.paths_to_monitor = []
        self.pre_sync_commands_local = pre_sync_commands_local or []
        self.post_sync_commands_local = post_sync_commands_local or []
        self.pre_sync_commands_remote = pre_sync_commands_remote or []
        self.post_sync_commands_remote = post_sync_commands_remote or []
        self.logger = Logger()

    def add_path(self, path):
        """Add a path to monitor for rsync"""
        if path not in self.paths_to_monitor:
            self.paths_to_monitor.append(path)

    def clear_paths(self):
        """Clear all paths to monitor"""
        self.paths_to_monitor = []

    def dedupe_a_list(self, a_list):
        """Return a deduplicated list of items"""
        new_list = []
        for item in a_list:
            if item not in new_list:
                new_list.append(item)
        return new_list

    def format_option(self, options):
        """Return a formatted string of options"""
        return (
            "'{"
            + ", ".join(f"'{option}'" for option in options)
            + "}'"
        )

    def run(self, exclude_list=None, include_list=None):
        """Run rsync with the specified options, paths, and destination"""
        # Run pre-sync commands
        if len(self.pre_sync_commands_local) > 0:
            print("Running pre-sync commands...")
            for command in self.pre_sync_commands_local:
                run_command(command)
            run_command(self.pre_sync_commands_local)
        if len(self.pre_sync_commands_remote) > 0:
            print("Running pre-sync commands...")
            for command in self.pre_sync_commands_remote:
                run_ssh_command(command,
                                self.destination.split("@")[1],
                                self.destination.split("@")[0],
                                self.ssh_key,
                                logger=self.logger)

        # Construct paths string
        paths_str = " ".join(self.paths_to_monitor)

        # Pre-set options from the configuration file
        options = f"{self.options}"

        # Add SSH key and port options if provided
        if self.ssh_key and self.ssh_port:
            options += f" -e 'ssh -i {self.ssh_key} -p {self.ssh_port}'"
        # Add SSH port option if provided
        if self.ssh_port:
            options += f" -e 'ssh -p {self.ssh_port}'"
        # Add SSH key option if provided
        if self.ssh_key:
            options += f" -e 'ssh -i {self.ssh_key}'"
        if exclude_list:
            options += f" --exclude={self.format_option(exclude_list)}"
        if include_list:
            options += f" --include={self.format_option(include_list)}"
        # Construct rsync command
        # If include_list is provided, use it to sync only the specified files
        if include_list:
            rsync_command = f"rsync {options} {self.destination}:{self.destination_path}"
            self.logger.info(f"Only syncing files in include list: {include_list}, rsync command: {rsync_command}")
        else:
            rsync_command = f"rsync {options} {paths_str} {self.destination}:{self.destination_path}"
            self.logger.info(f"Running rsync command: {rsync_command}")
        rsync_log = run_command(rsync_command)
        if rsync_log:
            self.logger.info(f"Rsync return code: {rsync_log.returncode}, stdout: {rsync_log.stdout}, stderr: {rsync_log.stderr}")

        # Run post-sync commands
        if len(self.post_sync_commands_local) > 0:
            print("Running post-sync commands...")
            for command in self.post_sync_commands_local:
                run_command(command)
        if len(self.post_sync_commands_remote) > 0:
            print("Running post-sync commands...")
            for command in self.post_sync_commands_remote:
                run_ssh_command(command,
                                self.destination.split("@")[1],
                                self.destination.split("@")[0],
                                self.ssh_key,
                                logger=self.logger)
