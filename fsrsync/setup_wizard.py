"""
FSRsync Interactive Setup Wizard

Comprehensive interactive setup for first-time users to configure FSRsync
for synchronizing with remote servers. This wizard guides users through:
- Local system configuration (hostname, logging)
- Remote server setup (SSH, credentials, paths)
- Synchronization preferences (strategies, bandwidth, scheduling)
- System preparation (SSH keys, directories, permissions)
"""

import os
import sys
import json
import subprocess
import getpass
from pathlib import Path
from typing import Dict, List, Optional, Tuple


class Color:
    """ANSI color codes for terminal output"""
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    END = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


class SetupWizard:
    """Interactive setup wizard for FSRsync"""

    def __init__(self):
        """Initialize the setup wizard"""
        self.config = {
            "log_level": "INFO",
            "hostname": "",
            "control_server_port": 8080,
            "control_server_host": "0.0.0.0",
            "control_server_secret": "",
            "max_stats": 100,
            "max_server_lock_time": 60,
            "use_global_server_lock": True,
            "full_sync_interval": 60,
            "destinations": [],
            "logs": ""
        }
        self.setup_folder = "/etc/fsrsync"

    def print_header(self, title: str) -> None:
        """Print a formatted header"""
        print(f"\n{Color.HEADER}{Color.BOLD}{'='*60}")
        print(f"{title:^60}")
        print(f"{'='*60}{Color.END}\n")

    def print_section(self, title: str) -> None:
        """Print a formatted section"""
        print(f"\n{Color.CYAN}{Color.BOLD}► {title}{Color.END}")
        print(f"{Color.CYAN}{'-'*40}{Color.END}")

    def print_success(self, message: str) -> None:
        """Print success message"""
        print(f"{Color.GREEN}✓ {message}{Color.END}")

    def print_info(self, message: str) -> None:
        """Print info message"""
        print(f"{Color.BLUE}ℹ {message}{Color.END}")

    def print_warning(self, message: str) -> None:
        """Print warning message"""
        print(f"{Color.YELLOW}⚠ {message}{Color.END}")

    def print_error(self, message: str) -> None:
        """Print error message"""
        print(f"{Color.RED}✗ {message}{Color.END}")

    def prompt_yes_no(self, question: str, default: bool = True) -> bool:
        """Prompt user for yes/no answer"""
        default_str = "Y/n" if default else "y/N"
        response = input(f"{Color.BLUE}{question} [{default_str}]: {Color.END}").strip().lower()

        if response == "":
            return default
        return response in ["y", "yes"]

    def prompt_input(self, question: str, default: Optional[str] = None) -> str:
        """Prompt user for text input"""
        if default:
            prompt = f"{Color.BLUE}{question} [{default}]: {Color.END}"
        else:
            prompt = f"{Color.BLUE}{question}: {Color.END}"

        response = input(prompt).strip()
        return response if response else default or ""

    def prompt_password(self, question: str) -> str:
        """Prompt user for password input"""
        return getpass.getpass(f"{Color.BLUE}{question}: {Color.END}")

    def prompt_choice(self, question: str, choices: List[str], default: int = 0) -> str:
        """Prompt user to choose from options"""
        print(f"\n{Color.BLUE}{question}{Color.END}")
        for i, choice in enumerate(choices, 1):
            default_marker = " (default)" if i - 1 == default else ""
            print(f"  {Color.CYAN}{i}{Color.END}. {choice}{default_marker}")

        while True:
            response = input(f"{Color.BLUE}Choose [1-{len(choices)}]: {Color.END}").strip()
            if not response:
                return choices[default]
            try:
                idx = int(response) - 1
                if 0 <= idx < len(choices):
                    return choices[idx]
            except ValueError:
                pass
            self.print_error(f"Invalid choice. Please enter 1-{len(choices)}")

    def run(self, setup_folder: Optional[str] = None) -> bool:
        """Run the complete setup wizard"""
        try:
            self.print_header("FSRsync Setup Wizard")
            print("Welcome to FSRsync! This wizard will help you set up FSRsync")
            print("to synchronize files with remote servers.\n")
            print("We'll configure:")
            print("  • Local system settings")
            print("  • Remote server connections")
            print("  • Synchronization preferences")
            print("  • System preparation\n")

            if not self.prompt_yes_no("Continue with setup?", default=True):
                print("\nSetup cancelled.")
                return False

            # Set custom folder if provided
            if setup_folder:
                self.setup_folder = setup_folder
            else:
                self.setup_folder = self.prompt_input(
                    "Configuration folder",
                    default="/etc/fsrsync"
                )

            # Run setup phases
            self._setup_local_config()
            self._setup_remote_servers()
            self._setup_sync_preferences()
            self._setup_system_preparation()

            # Save configuration
            self._save_configuration()
            self._print_summary()

            return True

        except KeyboardInterrupt:
            self.print_error("\nSetup cancelled by user")
            return False
        except Exception as e:
            self.print_error(f"Setup error: {e}")
            return False

    def _setup_local_config(self) -> None:
        """Setup local system configuration"""
        self.print_section("Local System Configuration")

        # Hostname
        default_hostname = os.uname().nodename
        self.config["hostname"] = self.prompt_input(
            "System hostname",
            default=default_hostname
        )

        # Control server port
        port_str = self.prompt_input(
            "Control server port (web interface)",
            default="8080"
        )
        try:
            self.config["control_server_port"] = int(port_str)
        except ValueError:
            self.config["control_server_port"] = 8080
            self.print_warning("Invalid port, using default 8080")

        # Control server host
        self.config["control_server_host"] = self.prompt_input(
            "Control server bind address",
            default="0.0.0.0"
        )

        # Control server secret (API key)
        secret = self.prompt_password("Control server API secret (for web access)")
        if secret:
            self.config["control_server_secret"] = secret
        else:
            self.config["control_server_secret"] = "your-secure-secret-here"
            self.print_warning("Empty secret - please update before running!")

        # Log level
        log_level = self.prompt_choice(
            "Log level",
            ["DEBUG", "INFO", "WARNING", "ERROR"],
            default=1  # INFO
        )
        self.config["log_level"] = log_level

        # Logs folder
        logs_folder = self.prompt_input(
            "Logs folder",
            default=f"{self.setup_folder}/logs"
        )
        self.config["logs"] = f"{logs_folder}/fsrsync.log"

        self.print_success("Local configuration completed")

    def _setup_remote_servers(self) -> None:
        """Setup remote server connections"""
        self.print_section("Remote Server Configuration")

        self.print_info("You can add multiple remote servers for synchronization")

        while True:
            if self.config["destinations"]:
                self.print_info(f"Configured destinations: {len(self.config['destinations'])}")
                for i, dest in enumerate(self.config["destinations"], 1):
                    print(f"  {i}. {dest.get('hostname')} ({dest.get('username')}@{dest.get('host')})")

            if not self.prompt_yes_no("\nAdd a remote server?", default=True):
                break

            dest = self._add_remote_server()
            if dest:
                self.config["destinations"].append(dest)
                self.print_success(f"Added destination: {dest.get('hostname')}")

        if not self.config["destinations"]:
            self.print_warning("No remote servers configured. You can add them later.")

    def _add_remote_server(self) -> Optional[Dict]:
        """Interactively add a remote server"""
        print()

        # Server identification
        server_name = self.prompt_input("Remote server name (e.g., 'backup-server')")
        if not server_name:
            self.print_error("Server name is required")
            return None

        # Connection details
        host = self.prompt_input("Remote server address/IP")
        if not host:
            self.print_error("Server address is required")
            return None

        port = self.prompt_input("SSH port", default="22")
        try:
            port = int(port)
        except ValueError:
            port = 22

        username = self.prompt_input("SSH username")
        if not username:
            self.print_error("Username is required")
            return None

        # Authentication method
        auth_method = self.prompt_choice(
            "Authentication method",
            ["SSH Key (recommended)", "Password"],
            default=0
        )

        password = None
        ssh_key_path = None

        if auth_method == "SSH Key (recommended)":
            ssh_key_path = self.prompt_input(
                "Path to SSH private key",
                default=f"{os.path.expanduser('~')}/.ssh/id_rsa"
            )
            if not os.path.exists(ssh_key_path):
                self.print_warning(f"SSH key not found at {ssh_key_path}")
                if self.prompt_yes_no("Generate SSH key pair?", default=True):
                    self._generate_ssh_key(ssh_key_path)
        else:
            password = self.prompt_password("SSH password")

        # Synchronization paths
        paths = self._setup_sync_paths()

        return {
            "hostname": server_name,
            "host": host,
            "port": port,
            "username": username,
            "password": password,
            "ssh_key_path": ssh_key_path,
            "local_path": paths["local"],
            "remote_path": paths["remote"],
            "strategy": "delta",  # Default strategy
            "bandwidth_limit_mbps": 0,  # 0 = no limit
            "enabled": True
        }

    def _setup_sync_paths(self) -> Dict[str, str]:
        """Setup local and remote sync paths"""
        print()

        local_path = self.prompt_input(
            "Local directory to sync",
            default=os.path.expanduser("~/documents")
        )

        if not os.path.exists(local_path):
            self.print_warning(f"Directory {local_path} does not exist")
            if self.prompt_yes_no("Create directory?", default=True):
                os.makedirs(local_path, exist_ok=True)
                self.print_success(f"Created {local_path}")

        remote_path = self.prompt_input(
            "Remote directory to sync",
            default="/home/user/documents"
        )

        return {
            "local": local_path,
            "remote": remote_path
        }

    def _generate_ssh_key(self, key_path: str) -> bool:
        """Generate SSH key pair"""
        try:
            key_dir = os.path.dirname(key_path)
            os.makedirs(key_dir, exist_ok=True)

            self.print_info(f"Generating SSH key pair at {key_path}...")

            subprocess.run(
                [
                    "ssh-keygen",
                    "-t", "rsa",
                    "-b", "4096",
                    "-f", key_path,
                    "-N", ""
                ],
                check=True,
                capture_output=True
            )

            self.print_success(f"SSH key pair generated")
            self.print_info(f"Public key: {key_path}.pub")

            if self.prompt_yes_no("Copy public key to remote server now?", default=False):
                return self._copy_ssh_key_to_server(key_path)

            return True

        except subprocess.CalledProcessError as e:
            self.print_error(f"Failed to generate SSH key: {e}")
            return False
        except Exception as e:
            self.print_error(f"SSH key generation error: {e}")
            return False

    def _copy_ssh_key_to_server(self, key_path: str) -> bool:
        """Copy SSH key to remote server"""
        try:
            remote_host = self.config["destinations"][-1]["host"] if self.config["destinations"] else None
            remote_user = self.config["destinations"][-1]["username"] if self.config["destinations"] else None

            if not remote_host or not remote_user:
                return False

            remote_port = self.config["destinations"][-1].get("port", 22)

            self.print_info(f"Copying public key to {remote_user}@{remote_host}...")

            subprocess.run(
                [
                    "ssh-copy-id",
                    "-i", f"{key_path}.pub",
                    "-p", str(remote_port),
                    f"{remote_user}@{remote_host}"
                ],
                check=True
            )

            self.print_success("Public key copied to remote server")
            return True

        except subprocess.CalledProcessError:
            self.print_error("Failed to copy public key")
            return False
        except Exception as e:
            self.print_error(f"Error copying SSH key: {e}")
            return False

    def _setup_sync_preferences(self) -> None:
        """Setup synchronization preferences"""
        self.print_section("Synchronization Preferences")

        # Sync strategy
        strategy = self.prompt_choice(
            "Synchronization strategy",
            [
                "Delta (transfer only changes) - Recommended",
                "Full (transfer complete files)",
                "Adaptive (auto-select)"
            ],
            default=0
        )
        strategies = ["delta", "full", "adaptive"]
        self.config["sync_strategy"] = strategies[[
            "Delta (transfer only changes) - Recommended",
            "Full (transfer complete files)",
            "Adaptive (auto-select)"
        ].index(strategy)]

        # Bandwidth limit
        bandwidth = self.prompt_input(
            "Bandwidth limit (MB/s, 0 for unlimited)",
            default="0"
        )
        try:
            self.config["bandwidth_limit_mbps"] = float(bandwidth)
        except ValueError:
            self.config["bandwidth_limit_mbps"] = 0

        # Full sync interval
        interval = self.prompt_input(
            "Full sync interval (seconds)",
            default="60"
        )
        try:
            self.config["full_sync_interval"] = int(interval)
        except ValueError:
            self.config["full_sync_interval"] = 60

        self.print_success("Synchronization preferences configured")

    def _setup_system_preparation(self) -> None:
        """Prepare system for FSRsync"""
        self.print_section("System Preparation")

        # Create configuration directory
        if not os.path.exists(self.setup_folder):
            os.makedirs(self.setup_folder, exist_ok=True)
            self.print_success(f"Created {self.setup_folder}")
        else:
            self.print_info(f"Configuration folder exists: {self.setup_folder}")

        # Create logs directory
        logs_folder = os.path.dirname(self.config["logs"])
        if not os.path.exists(logs_folder):
            os.makedirs(logs_folder, exist_ok=True)
            self.print_success(f"Created {logs_folder}")
        else:
            self.print_info(f"Logs folder exists: {logs_folder}")

        # Check SSH connectivity for each destination
        if self.config["destinations"]:
            self.print_info("Checking SSH connectivity to remote servers...")
            for dest in self.config["destinations"]:
                self._test_ssh_connection(dest)

        self.print_success("System preparation completed")

    def _test_ssh_connection(self, destination: Dict) -> None:
        """Test SSH connection to remote server"""
        try:
            host = destination["host"]
            port = destination.get("port", 22)
            username = destination["username"]

            # Use timeout of 5 seconds
            result = subprocess.run(
                [
                    "ssh",
                    "-o", "ConnectTimeout=5",
                    "-o", "StrictHostKeyChecking=accept-new",
                    "-p", str(port),
                    f"{username}@{host}",
                    "echo 'Connection successful'"
                ],
                capture_output=True,
                timeout=10
            )

            if result.returncode == 0:
                self.print_success(f"SSH connection verified: {username}@{host}:{port}")
            else:
                self.print_warning(f"SSH connection failed: {username}@{host}:{port}")
                self.print_info("You may need to configure SSH access manually")

        except subprocess.TimeoutExpired:
            self.print_warning(f"SSH connection timeout: {destination['host']}")
        except Exception as e:
            self.print_warning(f"Could not verify SSH: {e}")

    def _save_configuration(self) -> None:
        """Save configuration to file"""
        self.print_section("Saving Configuration")

        config_path = os.path.join(self.setup_folder, "config.json")

        try:
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=4)

            os.chmod(config_path, 0o600)  # Restrict permissions
            self.print_success(f"Configuration saved to {config_path}")

        except Exception as e:
            self.print_error(f"Failed to save configuration: {e}")
            raise

    def _print_summary(self) -> None:
        """Print setup summary"""
        self.print_header("Setup Complete!")

        print(f"Configuration saved to: {self.setup_folder}/config.json\n")

        print(f"{Color.BOLD}System Configuration:{Color.END}")
        print(f"  Hostname: {self.config['hostname']}")
        print(f"  Log Level: {self.config['log_level']}")
        print(f"  Control Server: {self.config['control_server_host']}:{self.config['control_server_port']}")
        print(f"  Logs: {self.config['logs']}\n")

        if self.config["destinations"]:
            print(f"{Color.BOLD}Remote Servers ({len(self.config['destinations'])}):{Color.END}")
            for i, dest in enumerate(self.config["destinations"], 1):
                print(f"\n  {i}. {dest['hostname']}")
                print(f"     Address: {dest['username']}@{dest['host']}:{dest.get('port', 22)}")
                print(f"     Local: {dest['local_path']}")
                print(f"     Remote: {dest['remote_path']}")

        print(f"\n{Color.BOLD}Next Steps:{Color.END}")
        print(f"  1. Start FSRsync: fsrsync")
        print(f"  2. Open web interface: http://localhost:{self.config['control_server_port']}")
        print(f"  3. API key: {self.config['control_server_secret']}\n")

        print(f"{Color.GREEN}{Color.BOLD}✓ FSRsync is ready to run!{Color.END}\n")


def run_setup_wizard(setup_folder: Optional[str] = None) -> bool:
    """Run the setup wizard"""
    wizard = SetupWizard()
    return wizard.run(setup_folder)
