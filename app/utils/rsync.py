import subprocess


class RsyncManager:
    """Class to manage rsync operations"""

    def __init__(self, destination, options, ssh_key=None, ssh_port=None):
        """Initialize the rsync manager with destination and options"""
        self.destination = destination
        self.options = options
        self.ssh_key = None
        self.ssh_port = None
        self.paths_to_monitor = []

    def add_path(self, path):
        """Add a path to monitor for rsync"""
        self.paths_to_monitor.append(path)

    def run(self):
        """Run rsync with the specified options, paths, and destination""" 
        paths_str = ' '.join(self.paths_to_monitor)
        # Add SSH key and port options if provided
        if self.ssh_key and self.ssh_port:
            self.options += f" -e 'ssh -i {self.ssh_key} -p {self.ssh_port}'"
        # Add SSH port option if provided
        if self.ssh_port:
            self.options += f" -e 'ssh -p {self.ssh_port}'"
        # Add SSH key option if provided
        if self.ssh_key:
            self.options += f" -e 'ssh -i {self.ssh_key}'"
        # Construct rsync command
        rsync_command = f"rsync {self.options} {paths_str} {self.destination}"
        try:
            subprocess.run(rsync_command, shell=True, check=True)
            print(f"Synced with rsync: {rsync_command}")
        except subprocess.CalledProcessError as e:
            print(f"Rsync failed: {e}")""