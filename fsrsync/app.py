import os
import sys
import json
import argparse

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
    """Run the setup wizard"""
    # Copy the default configuration file to the default location
    # Create /etc/fsrsync directory if it does not exist
    # Create /etc/fsrsync/config.json if it does not exist
    logs = None
    default_folder = DEFAULT_CONFIG_FILE
    if not os.path.exists(folder):
        os.makedirs(folder)
        print(f"Created {folder}")
    if folder != "/etc/fsrsync":
        default_folder = f"{folder}/config.json"
        logs = f"{folder}/logs/"
        if not os.path.exists(logs):
            os.makedirs(logs, exist_ok=True)
            print(f"Created {logs}")
    hostname = os.uname().nodename
    if not os.path.exists(default_folder):
        config_dict = {
            "log_level": "DEBUG",
            "hostname": hostname,
            "control_server_port": 8080,
            "control_server_host": "0.0.0.0",
            "control_server_secret": "secret",
            "max_stats": 100,
            "max_server_lock_time": 60,
            "use_global_server_lock": True,
            "full_sync_interval": 60,
            "destinations": []
        }
        if logs:
            config_dict["logs"] = f"{logs}fsrsync.log"
        CONFIG_TO_WRITE = json.dumps(config_dict, indent=4)
        with open(default_folder, "w", encoding="utf-8") as f:
            f.write(CONFIG_TO_WRITE)
        print(f"Created {default_folder} with default configuration")
    # Print a message to the user
    print("FSRsync setup complete")


""" Main entry point for the application """
if __name__ == "__main__":
    main()
