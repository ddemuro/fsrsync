import os
import sys
import shutil
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
    if not os.path.exists(DEFAULT_CONFIG_FILE):
        shutil.copyfile("config/config.json", DEFAULT_CONFIG_FILE)
    # Print a message to the user
    print("FSRsync setup complete")

""" Main entry point for the application """
if __name__ == "__main__":
    main()
