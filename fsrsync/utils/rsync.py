"""Module for managing rsync operations securely and efficiently."""
import os
import shlex
import tempfile
from typing import List, Tuple, Optional, Dict, Any, Union
from .logs import Logger
from .utils import run_command
from .ssh_lib import run_ssh_command


class RsyncManager:
    """Class to manage rsync operations with improved security and error handling."""

    def __init__(
        self,
        destination: str,
        destination_path: str,
        path: str,
        options: str,
        ssh_user: Optional[str] = None,
        ssh_key: Optional[str] = None,
        ssh_port: Optional[int] = None,
        pre_sync_commands_local: Optional[List[str]] = None,
        post_sync_commands_local: Optional[List[str]] = None,
        pre_sync_commands_remote: Optional[List[str]] = None,
        post_sync_commands_remote: Optional[List[str]] = None,
        pre_sync_commands_checkexit_local: Optional[List[str]] = None,
        post_sync_commands_checkexit_local: Optional[List[str]] = None,
        pre_sync_commands_checkexit_remote: Optional[List[str]] = None,
        post_sync_commands_checkexit_remote: Optional[List[str]] = None,
        logger: Optional[Logger] = None,
    ):
        """Initialize the rsync manager with validated parameters.
        
        Args:
            destination: Remote destination in format user@host
            destination_path: Remote path to sync to
            path: Local path to sync from
            options: Rsync options
            ssh_user: SSH username (optional, can be extracted from destination)
            ssh_key: Path to SSH private key
            ssh_port: SSH port
            pre_sync_commands_local: Commands to run locally before sync
            post_sync_commands_local: Commands to run locally after sync
            pre_sync_commands_remote: Commands to run remotely before sync
            post_sync_commands_remote: Commands to run remotely after sync
            pre_sync_commands_checkexit_local: Local commands to run and check exit code before sync
            post_sync_commands_checkexit_local: Local commands to run and check exit code after sync
            pre_sync_commands_checkexit_remote: Remote commands to run and check exit code before sync
            post_sync_commands_checkexit_remote: Remote commands to run and check exit code after sync
            logger: Logger instance
        """
        # Validate required inputs
        if not destination:
            raise ValueError("Destination is required")
        if not destination_path:
            raise ValueError("Destination path is required")
        if not path:
            raise ValueError("Path is required")
        if not os.path.exists(path):
            raise ValueError(f"Path '{path}' does not exist")
            
        # Initialize properties
        self.destination = destination
        self.destination_path = destination_path
        self.path = path
        self.options = options
        self.ssh_key = ssh_key
        self.ssh_port = ssh_port
        
        # Parse destination to extract user and host
        try:
            self.user, self.host = destination.split('@', 1)
        except ValueError:
            self.user = ssh_user if ssh_user else "root"
            self.host = destination
            # Reconstruct destination with user
            self.destination = f"{self.user}@{self.host}"
            
        # Initialize command lists
        self.pre_sync_commands_local = pre_sync_commands_local or []
        self.post_sync_commands_local = post_sync_commands_local or []
        self.pre_sync_commands_remote = pre_sync_commands_remote or []
        self.post_sync_commands_remote = post_sync_commands_remote or []
        self.pre_sync_commands_checkexit_local = pre_sync_commands_checkexit_local or []
        self.post_sync_commands_checkexit_local = post_sync_commands_checkexit_local or []
        self.pre_sync_commands_checkexit_remote = pre_sync_commands_checkexit_remote or []
        self.post_sync_commands_checkexit_remote = post_sync_commands_checkexit_remote or []
        
        # Set up logger
        self.logger = logger or Logger()
        
        # Initialize sync state
        self.rsync_output = ""
        self.last_exit_code = None
        
    def dedupe_list(self, items: List[str]) -> List[str]:
        """Deduplicate a list efficiently while preserving order.
        
        Args:
            items: List of items to deduplicate
            
        Returns:
            Deduplicated list
        """
        if not items:
            return []
            
        seen = set()
        result = []
        
        for item in items:
            if item not in seen:
                seen.add(item)
                result.append(item)
                
        return result
        
    def create_exclude_include_files(
        self, exclude_list: Optional[List[str]], include_list: Optional[List[str]]
    ) -> Tuple[Optional[str], Optional[str]]:
        """Create temporary files for exclude and include patterns.
        
        Args:
            exclude_list: List of patterns to exclude
            include_list: List of patterns to include
            
        Returns:
            Tuple of (exclude_file_path, include_file_path)
        """
        exclude_file = None
        include_file = None
        
        if exclude_list and len(exclude_list) > 0:
            exclude_file = tempfile.NamedTemporaryFile(mode='w', delete=False)
            for pattern in exclude_list:
                exclude_file.write(f"{pattern}\n")
            exclude_file.close()
            
        if include_list and len(include_list) > 0:
            include_file = tempfile.NamedTemporaryFile(mode='w', delete=False)
            for pattern in include_list:
                include_file.write(f"{pattern}\n")
            include_file.close()
            
        return (exclude_file.name if exclude_file else None, 
                include_file.name if include_file else None)
                
    def get_ssh_options(self) -> str:
        """Build SSH options string.
        
        Returns:
            SSH options string for rsync's -e parameter
        """
        ssh_options = []
        
        if self.ssh_port:
            ssh_options.append(f"-p {self.ssh_port}")
            
        if self.ssh_key:
            ssh_options.append(f"-i {shlex.quote(self.ssh_key)}")
            
        if ssh_options:
            return f"-e 'ssh {' '.join(ssh_options)}'"
        else:
            return ""
            
    def run_commands(
        self, 
        commands: List[str], 
        check_exit: bool = False, 
        is_remote: bool = False
    ) -> bool:
        """Run a list of commands with proper error handling.
        
        Args:
            commands: List of commands to run
            check_exit: Whether to check exit code
            is_remote: Whether to run commands remotely
            
        Returns:
            True if all commands succeeded, False otherwise
        """
        if not commands:
            return True
            
        command_type = "remote" if is_remote else "local"
        exit_check = "with exit code check" if check_exit else ""
        self.logger.info(f"Running {command_type} {exit_check} commands: {len(commands)}")
        
        for command in commands:
            if not command or command.strip() == "":
                continue
                
            self.logger.debug(f"Running {command_type} command: {command}")
            
            if is_remote:
                success, exit_code, stdout, stderr = run_ssh_command(
                    command,
                    self.host,
                    self.user,
                    self.ssh_key,
                    port=self.ssh_port,
                    logger=self.logger,
                )
            else:
                success, exit_code, stdout, stderr = run_command(command)
                
            if stdout:
                self.logger.debug(f"Command stdout: {stdout}")
            if stderr:
                self.logger.debug(f"Command stderr: {stderr}")
                
            if check_exit and not success:
                self.logger.error(
                    f"{command_type.capitalize()} command failed with exit code {exit_code}: {command}"
                )
                return False
                
        return True
        
    def build_rsync_command(
        self, 
        exclude_file: Optional[str] = None, 
        include_file: Optional[str] = None
    ) -> str:
        """Build a secure rsync command string.
        
        Args:
            exclude_file: Path to temporary file with exclude patterns
            include_file: Path to temporary file with include patterns
            
        Returns:
            Rsync command string
        """
        # Start with base options, always add stats
        rsync_options = f"{self.options} --stats"
        
        # Add SSH options if any
        ssh_opts = self.get_ssh_options()
        if ssh_opts:
            rsync_options = f"{rsync_options} {ssh_opts}"
            
        # Add exclude file if any
        if exclude_file:
            rsync_options = f"{rsync_options} --exclude-from={shlex.quote(exclude_file)}"
            
        # Add include file if any
        if include_file:
            rsync_options = f"{rsync_options} --include-from={shlex.quote(include_file)}"
            
        # Build final command with properly quoted paths
        source_path = shlex.quote(self.path)
        dest = shlex.quote(f"{self.destination}:{self.destination_path}")
        
        return f"rsync {rsync_options} {source_path} {dest}"
        
    def parse_rsync_output(self, stdout: str, stderr: str) -> Dict[str, Any]:
        """Parse rsync output to extract useful statistics.
        
        Args:
            stdout: Rsync standard output
            stderr: Rsync standard error
            
        Returns:
            Dictionary of statistics
        """
        stats = {
            "files_transferred": 0,
            "total_file_size": 0,
            "total_transferred_size": 0,
            "literal_data": 0,
            "matched_data": 0,
            "file_list_size": 0,
            "file_list_generation_time": 0,
            "file_list_transfer_time": 0,
            "total_bytes_sent": 0,
            "total_bytes_received": 0,
        }
        
        if not stdout:
            return stats
            
        # Store the full output
        self.rsync_output = stdout
        
        # Parse stats from output
        for line in stdout.splitlines():
            line = line.strip()
            
            if "Number of files transferred:" in line:
                try:
                    stats["files_transferred"] = int(line.split(":", 1)[1].strip())
                except (ValueError, IndexError):
                    pass
                    
            elif "Total file size:" in line:
                try:
                    size_str = line.split(":", 1)[1].strip().split()[0]
                    stats["total_file_size"] = int(size_str.replace(",", ""))
                except (ValueError, IndexError):
                    pass
                    
            elif "Total transferred file size:" in line:
                try:
                    size_str = line.split(":", 1)[1].strip().split()[0]
                    stats["total_transferred_size"] = int(size_str.replace(",", ""))
                except (ValueError, IndexError):
                    pass
                    
            elif "Total bytes sent:" in line:
                try:
                    size_str = line.split(":", 1)[1].strip().split()[0]
                    stats["total_bytes_sent"] = int(size_str.replace(",", ""))
                except (ValueError, IndexError):
                    pass
                    
            elif "Total bytes received:" in line:
                try:
                    size_str = line.split(":", 1)[1].strip().split()[0]
                    stats["total_bytes_received"] = int(size_str.replace(",", ""))
                except (ValueError, IndexError):
                    pass
                    
        return stats
        
    def run(
        self, 
        exclude_list: Optional[List[str]] = None, 
        include_list: Optional[List[str]] = None
    ) -> Tuple[bool, bool]:
        """Run rsync with the specified options, paths, and destination.
        
        Args:
            exclude_list: List of patterns to exclude
            include_list: List of patterns to include
            
        Returns:
            Tuple of (rsync_success, commands_success)
        """
        exclude_file = None
        include_file = None
        
        try:
            # Dedupe and filter lists
            if exclude_list:
                exclude_list = self.dedupe_list(exclude_list)
                
            if include_list:
                include_list = self.dedupe_list(include_list)
                
                # Remove excluded items from include list
                if exclude_list:
                    include_list = [item for item in include_list if item not in exclude_list]
                    
            # Check if include list is empty after filtering
            if include_list is not None and len(include_list) == 0:
                self.logger.info("Include list is empty after filtering, skipping rsync.")
                return True, True
                
            # Run pre-sync local commands
            if not self.run_commands(self.pre_sync_commands_local):
                self.logger.warning("Some pre-sync local commands failed, continuing anyway")
                
            # Run pre-sync local commands with exit code check
            if not self.run_commands(self.pre_sync_commands_checkexit_local, check_exit=True):
                self.logger.error("Pre-sync local commands with exit check failed, aborting")
                return False, False
                
            # Run pre-sync remote commands
            if not self.run_commands(self.pre_sync_commands_remote, is_remote=True):
                self.logger.warning("Some pre-sync remote commands failed, continuing anyway")
                
            # Run pre-sync remote commands with exit code check
            if not self.run_commands(self.pre_sync_commands_checkexit_remote, check_exit=True, is_remote=True):
                self.logger.error("Pre-sync remote commands with exit check failed, aborting")
                return False, False
                
            # Create temporary files for exclude and include lists
            exclude_file, include_file = self.create_exclude_include_files(exclude_list, include_list)
            
            # Build rsync command
            rsync_command = self.build_rsync_command(exclude_file, include_file)
            
            # Log what we're doing
            if include_list:
                self.logger.info(f"Running selective sync with {len(include_list)} included patterns")
            else:
                self.logger.info("Running full directory sync")
                
            self.logger.debug(f"Rsync command: {rsync_command}")
            
            # Run rsync
            rsync_success, exit_code, stdout, stderr = run_command(rsync_command)
            self.last_exit_code = exit_code
            
            # Parse output
            stats = self.parse_rsync_output(stdout, stderr)
            
            # Log results
            if rsync_success:
                self.logger.info(
                    f"Rsync completed successfully. Files transferred: {stats['files_transferred']}, "
                    f"Bytes sent: {stats['total_bytes_sent']}, Bytes received: {stats['total_bytes_received']}"
                )
            else:
                self.logger.error(
                    f"Rsync failed with exit code {exit_code}. "
                    f"Stdout: {stdout[:200]}{'...' if len(stdout) > 200 else ''}, "
                    f"Stderr: {stderr[:200]}{'...' if len(stderr) > 200 else ''}"
                )
                
            # Run post-sync local commands
            if not self.run_commands(self.post_sync_commands_local):
                self.logger.warning("Some post-sync local commands failed, continuing anyway")
                
            # Run post-sync local commands with exit code check
            if not self.run_commands(self.post_sync_commands_checkexit_local, check_exit=True):
                self.logger.error("Post-sync local commands with exit check failed")
                return rsync_success, False
                
            # Run post-sync remote commands
            if not self.run_commands(self.post_sync_commands_remote, is_remote=True):
                self.logger.warning("Some post-sync remote commands failed, continuing anyway")
                
            # Run post-sync remote commands with exit code check
            if not self.run_commands(self.post_sync_commands_checkexit_remote, check_exit=True, is_remote=True):
                self.logger.error("Post-sync remote commands with exit check failed")
                return rsync_success, False
                
            return rsync_success, True
            
        except Exception as e:
            self.logger.error(f"Error running rsync: {str(e)}", exc_info=True)
            return False, False
            
        finally:
            # Clean up temporary files
            if exclude_file and os.path.exists(exclude_file):
                try:
                    os.unlink(exclude_file)
                except OSError as e:
                    self.logger.warning(f"Failed to remove temporary exclude file: {e}")
                    
            if include_file and os.path.exists(include_file):
                try:
                    os.unlink(include_file)
                except OSError as e:
                    self.logger.warning(f"Failed to remove temporary include file: {e}")
                    
    def get_last_rsync_output(self) -> str:
        """Get the output from the last rsync command.
        
        Returns:
            Output string from last rsync command
        """
        return self.rsync_output
        
    def get_last_exit_code(self) -> Optional[int]:
        """Get the exit code from the last rsync command.
        
        Returns:
            Exit code or None if rsync hasn't been run
        """
        return self.last_exit_code