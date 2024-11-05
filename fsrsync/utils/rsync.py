from .logs import Logger
from .utils import run_command
from .ssh_lib import run_ssh_command


class RsyncManager:
    """Class to manage rsync operations"""

    def __init__(
        self,
        destination,
        destination_path,
        path,
        options,
        ssh_user=None,
        ssh_key=None,
        ssh_port=None,
        pre_sync_commands_local=None,
        post_sync_commands_local=None,
        pre_sync_commands_remote=None,
        post_sync_commands_remote=None,
        pre_sync_commands_checkexit_local=None,
        post_sync_commands_checkexit_local=None,
        pre_sync_commands_checkexit_remote=None,
        post_sync_commands_checkexit_remote=None,
    ):
        """Initialize the rsync manager with destination and options"""
        self.destination = destination
        self.destination_path = destination_path
        self.path = path
        self.options = options
        self.ssh_key = ssh_key
        self.ssh_port = ssh_port
        self.paths_to_monitor = []
        self.pre_sync_commands_local = pre_sync_commands_local or []
        self.post_sync_commands_local = post_sync_commands_local or []
        self.pre_sync_commands_remote = pre_sync_commands_remote or []
        self.post_sync_commands_remote = post_sync_commands_remote or []
        self.pre_sync_commands_checkexit_local = pre_sync_commands_checkexit_local or []
        self.post_sync_commands_checkexit_local = post_sync_commands_checkexit_local or []
        self.pre_sync_commands_checkexit_remote = pre_sync_commands_checkexit_remote or []
        self.post_sync_commands_checkexit_remote = post_sync_commands_checkexit_remote or []
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
        if not a_list:
            return []
        new_list = []
        for item in a_list:
            if item not in new_list:
                new_list.append(item)
        return new_list

    def format_option(self, options):
        """Return a formatted string of options"""
        string_cmd = "{"
        if len(options) == 1:
            string_cmd += f"'{options[0]}'"
        else:
            # Format as a comma-separated list except for the last item
            for option in options[:-1]:
                string_cmd += f"'{option}',"
            string_cmd += f"'{options[-1]}'"
        string_cmd += "}"
        return string_cmd

    def run(self, exclude_list=None, include_list=None):
        """Run rsync with the specified options, paths, and destination"""

        # Ensure no excluded files are included in the include list
        if exclude_list and include_list:
            exclude_list = self.dedupe_a_list(exclude_list)
            include_list = self.dedupe_a_list(include_list)
            for exclude_item in exclude_list:
                if exclude_item in include_list:
                    include_list.remove(exclude_item)

        # Don't run if include list is empty
        if include_list and len(include_list) == 0:
            self.logger.debug("Include list is empty, skipping rsync.")
            return

        # Run pre-sync commands
        if len(self.pre_sync_commands_local) > 0:
            print("Running pre-sync commands...")
            for command in self.pre_sync_commands_local:
                if not command:
                    continue
                run_command(command)

        # Run pre-sync checkexit commands
        if len(self.pre_sync_commands_checkexit_local) > 0:
            print("Running pre-sync checkexit commands...")
            for command in self.pre_sync_commands_checkexit_local:
                if not command:
                    continue
                success, exit_code, stdout, stderr = run_command(command)
                if not success:
                    self.logger.error(
                        f"Pre-sync checkexit command failed with exit code {exit_code}: {stdout} {stderr}"
                    )
                    return False, False

        # Run pre-sync remote commands
        if len(self.pre_sync_commands_remote) > 0:
            print("Running pre-sync commands...")
            for command in self.pre_sync_commands_remote:
                if not command:
                    continue
                run_ssh_command(
                    command,
                    self.destination.split("@")[1],
                    self.destination.split("@")[0],
                    self.ssh_key,
                    logger=self.logger,
                )

        # Run pre-sync remote checkexit commands
        if len(self.pre_sync_commands_checkexit_remote) > 0:
            print("Running pre-sync checkexit commands...")
            for command in self.pre_sync_commands_checkexit_remote:
                if not command:
                    continue
                success, exit_code, stdout, stderr = run_ssh_command(
                    command,
                    self.destination.split("@")[1],
                    self.destination.split("@")[0],
                    self.ssh_key,
                    logger=self.logger,
                )
                # If the command fails, log the error and return
                if not success:
                    self.logger.error(
                        f"Pre-sync checkexit command failed with exit code {exit_code}: {stdout} {stderr}"
                    )
                    return False, False

        # Construct paths string
        paths_str = " ".join(self.paths_to_monitor)

        # Pre-set options from the configuration file
        options = f"{self.options} --stats"

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
            rsync_command = (
                f"rsync {options} {self.destination}:{self.destination_path}"
            )
            self.logger.info(
                f"Only syncing files in include list: {include_list}, rsync command: {rsync_command}"
            )
        else:
            rsync_command = f"rsync {options} {paths_str} {self.path} {self.destination}:{self.destination_path}"
            self.logger.info(f"Running regular rsync command: {rsync_command}")
        rsync_success, exit_code, stdout, stderr = run_command(rsync_command)
        if stdout:
            self.logger.info(
                f"Rsync return code: {exit_code}, stdout: {stdout}, stderr: {stderr}"
            )

        # Run post-sync commands
        if len(self.post_sync_commands_local) > 0:
            print("Running post-sync commands...")
            for command in self.post_sync_commands_local:
                if not command:
                    continue
                run_command(command)

        # Run post-sync checkexit commands
        if len(self.post_sync_commands_checkexit_local) > 0:
            print("Running post-sync checkexit commands...")
            for command in self.post_sync_commands_checkexit_local:
                if not command:
                    continue
                success, exit_code, stdout, stderr = run_command(command)
                if not success:
                    self.logger.error(
                        f"Post-sync checkexit command failed with exit code {exit_code}: {stdout} {stderr}"
                    )
                    return rsync_success, False

        # Run post-sync checkexit commands
        if len(self.post_sync_commands_remote) > 0:
            print("Running post-sync commands...")
            for command in self.post_sync_commands_remote:
                if not command:
                    continue
                run_ssh_command(
                    command,
                    self.destination.split("@")[1],
                    self.destination.split("@")[0],
                    self.ssh_key,
                    logger=self.logger,
                )

        # Run post-sync checkexit remote commands
        if len(self.post_sync_commands_checkexit_remote) > 0:
            print("Running post-sync checkexit commands...")
            for command in self.post_sync_commands_checkexit_remote:
                if not command:
                    continue
                success, exit_code, stdout, stderr = run_ssh_command(
                    command,
                    self.destination.split("@")[1],
                    self.destination.split("@")[0],
                    self.ssh_key,
                    logger=self.logger,
                )
                # If the command fails, log the error and return
                if not success:
                    self.logger.error(
                        f"Post-sync checkexit command failed with exit code {exit_code}: {stdout} {stderr}"
                    )
                    return rsync_success, False

        # Return the success status of the rsync command
        return rsync_success, True
