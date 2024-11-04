**FSRsync**
================

![Logo](https://github.com/ddemuro/fsrsync/blob/main/logo.jpg?raw=true)

Monitor filesystem changes and keep two systems in sync with FSRsync!

**Temporary Setup Server**
--------------------------

We are currently using my company's pypy server to host the setup files. This is a temporary solution until we have a more permanent setup. The server is located at `http://pypy.takelan.com/takelan/fsrsync/`.

**Installation**
----------------

```bash
pipx install --index-url="https://pypy.takelan.com/root/takelan/+simple" fsrsync
```

That should install the latest version of FSRsync on your system. If you encounter any issues, please let us know!

How to run:
```bash
/root/.local/bin/fsrsync --setup # To setup the configuration file in /etc/fsrsync/config.json
/root/.local/bin/fsrsync # To run the application
```

**Overview**
-----------

FSRsync is a powerful tool that leverages the strengths of rsync, inotify, and Python to monitor changes in a local filesystem and synchronize them with a remote system. With FSRsync, you can keep your data consistent across multiple machines, making it an essential tool for developers, administrators, and power users alike.

**Features**
------------

* **Real-time monitoring**: FSRsync uses inotify to detect changes in the local filesystem and triggers rsync transfers when needed.
* **Intelligent syncing**: Our Python implementation intelligently decides which files to transfer, minimizing unnecessary data transfers and reducing sync times.
* **Remote syncing**: Send your updated filesystem to a remote system with ease, making it perfect for collaborations, backups, or deployments.

**Getting Started**
-------------------

1. Clone this repository: `git clone https://github.com/ddemuro/fsrsync.git`
2. Install dependencies: `pip install -r requirements.txt` (see [dependencies](#dependencies) below)
3. Configure your remote sync destination: Update the `config.json` file with your preferences

**Usage**
--------

FSRsync can be used in a variety of scenarios, such as:

* **Development**: Keep your local and remote development environments in sync.
* **Backup**: Regularly backup your data to a remote system for disaster recovery.
* **Deployment**: Sync your application code between machines.

**Dependencies**
----------------

* Python 3.6+
* rsync
* inotify (Linux only)

**Running full sync from crontab**
----------------------------------

To run a full sync from crontab, you can use the following command:

```bash
0 0 * * * /usr/bin/python3 /path/to/fsrsync.py full-sync
```

This will run a full sync every day at midnight, ensuring that your data is always up-to-date.

**Documentation**

# Configuration File Fields Explained

This configuration file consists of global settings and specific configurations for syncing destinations. Below is a detailed breakdown of each field:

## Global Fields

- **`log_level`**: The logging level of the application. Common values include `DEBUG`, `INFO`, `WARNING`, `ERROR`, and `CRITICAL`. `DEBUG` provides detailed logs useful for debugging.

- **`hostname`**: The name of the server running the application. Used for identification purposes.

- **`control_server_port`**: The port number on which the control server listens for connections. 

- **`control_server_host`**: The host address the control server binds to. `0.0.0.0` allows the server to accept connections from any IP address.

- **`control_server_secret`**: A secret key used for authenticating control server communications to ensure security.

## `destinations` Array

Each entry in the `destinations` array represents a configuration for a specific destination to sync to. Below are the fields explained:

- **`destination`**: The remote user and host (e.g., `root@client`) to which data will be synced.

- **`destination_path`**: The path on the remote system where data will be transferred.

- **`options`**: Additional options for the `rsync` command (e.g., `-avPrl --delete`). These specify flags such as archive mode (`-a`), verbose output (`-v`), preserving permissions (`-P`), and deleting extra files on the destination (`--delete`).

- **`ssh_port`**: The port used for SSH connections to the remote destination. Default is usually `22`.

- **`enabled`**: A Boolean (`true`/`false`) indicating if the destination is active for syncing.

- **`event_queue_limit`**: The maximum number of events that can be queued before processing. This limits the size of the event buffer.

- **`max_wait_locked`**: The maximum time (in seconds) to wait if the global server lock is in place before proceeding with the sync.

- **`use_global_server_lock`**: A Boolean indicating if a global lock should be used to prevent simultaneous syncs.

- **`notify_file_locks`**: A Boolean indicating if notifications should be given when file locks occur.

- **`control_server_secret`**: The secret key specific to the destination for secure communication with the control server.

- **`control_server_port`**: The port used by the control server for this specific destination (typically the same as the global `control_server_port`).
- **`control_server_host`**: The host address the control server binds to for this specific destination (typically the same as the global `control_server_host`).
- **`extensions_to_ignore`**: A list of file extensions to ignore during syncing. For example, `[".log", ".tmp"]` would ignore log and temporary files.
- **`path`**: The source path on the local system from where files will be synced.

- **`events`**: A list of filesystem events that trigger the sync. Examples include:
  - `IN_MODIFY`: A file is modified.
  - `IN_DELETE`: A file is deleted.
  - `IN_CREATE`: A new file is created.

- **`pre_sync_commands_local`**: A list of shell commands to be run locally before the sync process begins.

- **`post_sync_commands_local`**: A list of shell commands to be run locally after the sync process completes.

- **`pre_sync_commands_remote`**: A list of shell commands to be run on the remote system before the sync starts.

- **`post_sync_commands_remote`**: A list of shell commands to be run on the remote system after the sync finishes.

- **`warning_file_open_time`**: The time (in seconds) that triggers a warning if a file remains open for this duration. A high value, like `86400`, represents 24 hours.

---

This structure ensures detailed control over syncing operations, specifying both global and destination-specific configurations. By customizing these settings, users can tailor the application to their specific needs and requirements.


**Contribution**
----------------

Contributions to FSRsync are welcome and encouraged! Please submit any issues or pull requests through the GitHub repository. We're looking forward to collaborating with you!

**License**
----------

FSRsync is released under the MIT License. See [LICENSE](LICENSE) for details.
