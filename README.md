**FSRsync**
================

Monitor filesystem changes and keep two systems in sync with FSRsync!

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
* `config.json` file with the following structure:
```json
{
    "log_level": "INFO",
    "destinations": [
        {
            "destination": "user1@remote:/path/to/destination1",
            "options": "-avz --no-whole-file --delete --inplace",
            "event_queue_limit": 10,
            "path": "/path/to/directory1",
            "events": [
                "IN_CREATE",
                "IN_MODIFY"
            ],
            "warning_file_open_time": 86400
        },
        {
            "destination": "user2@remote:/path/to/destination2",
            "options": "-avz --no-whole-file --delete --inplace",
            "ssh_key": "/path/to/ssh/key",
            "ssh_port": 22,
            "event_queue_limit": 5,
            "path": "/path/to/directory3",
            "events": [
                "IN_MODIFY",
                "IN_DELETE"
            ],
            "pre_sync_commands": [
                "echo 'Hello World!'"
            ],
            "post_sync_commands": [
                "echo 'Goodbye World!'"
            ],
            "warning_file_open_time": 86400
        }
    ]
}
```

**Contribution**
----------------

Contributions to FSRsync are welcome and encouraged! Please submit any issues or pull requests through the GitHub repository. We're looking forward to collaborating with you!

**License**
----------

FSRsync is released under the MIT License. See [LICENSE](LICENSE) for details.
