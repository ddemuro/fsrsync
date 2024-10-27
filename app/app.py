import sys
import argparse
from sync_app import SyncApplication
from utils.utils import validate_path

DEFAULT_CONFIG_FILE = "/etc/fsrsync/config.json"

""" Main entry point for the application """
if __name__ == "__main__":
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

    # Parse arguments
    args = parser.parse_args()

    full_sync = False
    if args.fullsync:
        full_sync = True

    # Print the arguments
    print(args)

    # Determine the configuration file
    if not validate_path(args.config_file):
        print(f"Invalid configuration file: {args.config_file}")
        sys.exit(1)

    # Initialize and run the application
    app = SyncApplication(args.config_file, full_sync)
    app.setup()
    app.run()
