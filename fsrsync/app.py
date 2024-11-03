import os
import sys
import json
import argparse
# Fix path so that we can import the sync_app module
sys.path.append('..')
from fsrsync.sync_app import SyncApplication

DEFAULT_CONFIG_FILE = "/etc/fsrsync/config.json"


def main():
    """Main function for the application"""
    parser = argparse.ArgumentParser(description="FSRsync: Filesystem to Rsync")
    # Add arguments
    parser.add_argument(
        "--config_file", nargs="?", default=DEFAULT_CONFIG_FILE,
        help="Path to the configuration file"
    )
    parser.add_argument(
        "--fullsync", action="store_true",
        help="Enable full sync mode"
    )
    # Add "setup" argument
    parser.add_argument(
        "--setup", action="store_true",
        help="Run the setup wizard to create a configuration file"
    )

    # Parse arguments
    args = parser.parse_args()

    full_sync = False
    if args.fullsync:
        full_sync = True

    # Print the arguments
    print(args)

    if args.setup:
        setup()
        print("Exiting...")
        sys.exit(0)

    # Initialize and run the application
    app = SyncApplication(args.config_file, full_sync)
    app.setup()
    app.run()


def setup():
    """Run the setup wizard"""
    # Copy the default configuration file to the default location
    # Create /etc/fsrsync directory if it does not exist
    # Create /etc/fsrsync/config.json if it does not exist
    if not os.path.exists("/etc/fsrsync"):
        os.makedirs("/etc/fsrsync")
        print("Created /etc/fsrsync directory")
    if not os.path.exists(DEFAULT_CONFIG_FILE):
        config_dict = {
            "log_level": "DEBUG",
            "hostname": "client",
            "control_server_port": 8080,
            "control_server_host": "0.0.0.0",
            "control_server_secret": "secret",
            "destinations": []
        }
        CONFIG_TO_WRITE = json.dumps(config_dict, indent=4)
        with open(DEFAULT_CONFIG_FILE, "w", encoding="utf-8") as f:
            f.write(CONFIG_TO_WRITE)
        print("Created /etc/fsrsync/config.json")
    # Print a message to the user
    print("FSRsync setup complete")


""" Main entry point for the application """
if __name__ == "__main__":
    main()
