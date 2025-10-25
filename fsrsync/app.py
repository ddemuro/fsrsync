import os
import sys
import json
import argparse
from fsrsync.setup_wizard import run_setup_wizard

DEFAULT_CONFIG_FILE = "/etc/fsrsync/config.json"


def main():
    """Main function for the application"""
    parser = argparse.ArgumentParser(description="FSRsync: Filesystem to Rsync")
    # Add arguments
    parser.add_argument(
        "--config", nargs="?", default=DEFAULT_CONFIG_FILE,
        help="Path to the configuration file"
    )
    parser.add_argument(
        "--fullsync", action="store_true",
        help="Enable full sync mode"
    )
    # Change setup path
    parser.add_argument(
        "--setupfolder", nargs="?", action="store",
        help="Run the setup wizard to create a configuration file in a specific folder"
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

    # Grab setupfolder argument and pass it to setup function
    if args.setupfolder:
        setup(args.setupfolder)
        print("Exiting...")
        sys.exit(0)

    # Fix path so that we can import the sync_app module
    sys.path.append('..')
    from fsrsync.sync_app import SyncApplication  # DO NOT MOVE!

    # Initialize and run the application
    app = SyncApplication(config_file=args.config, full_sync=full_sync)
    app.setup()
    app.run()


def setup(folder="/etc/fsrsync"):
    """Run the interactive setup wizard"""
    run_setup_wizard(folder)


""" Main entry point for the application """
if __name__ == "__main__":
    main()
