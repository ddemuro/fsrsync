# FSRsync Interactive Setup Wizard Guide

## Overview

The FSRsync Setup Wizard provides an interactive, step-by-step configuration experience for users setting up FSRsync for the first time. It guides you through all necessary configuration without requiring knowledge of JSON files or command-line tools.

## Quick Start

```bash
# Run the interactive setup wizard
fsrsync --setup

# Or with custom configuration folder
fsrsync --setup --setupfolder /path/to/config
```

## What the Setup Wizard Does

### 1. **Local System Configuration**
Sets up your local FSRsync installation:
- System hostname identification
- Web interface port and binding address
- API security secret (for accessing the web interface)
- Logging level (DEBUG, INFO, WARNING, ERROR)
- Log file location

### 2. **Remote Server Configuration**
Guides you through adding remote servers:
- Server identification and naming
- SSH connection details (host, port, username)
- Authentication setup (SSH keys or password)
- SSH key generation (if needed)
- Local and remote directory paths
- Automatic SSH connectivity verification

### 3. **Synchronization Preferences**
Configures how files are synchronized:
- Synchronization strategy (Delta, Full, Adaptive)
- Bandwidth limits
- Sync intervals

### 4. **System Preparation**
Automatically prepares your system:
- Creates necessary directories
- Sets proper file permissions
- Tests SSH connections
- Verifies all prerequisites

## Interactive Setup Process

### Starting the Wizard

```bash
fsrsync --setup
```

You'll see a welcome screen and be asked to confirm you want to continue.

### Local System Configuration

```
► Local System Configuration
────────────────────────────

System hostname [my-server]:
Control server port (web interface) [8080]:
Control server bind address [0.0.0.0]:
Control server API secret: ••••••••••
Log level
  1. DEBUG
  2. INFO (default)
  3. WARNING
  4. ERROR
Choose [1-4]: 2
Logs folder [/etc/fsrsync/logs]:
```

**Configuration Details:**

- **System Hostname**: Used to identify your FSRsync instance
- **Control Server Port**: Web interface port (default: 8080)
- **Control Server Address**: Bind address for web interface (0.0.0.0 = all interfaces)
- **API Secret**: Password/token for accessing the API (keep this secure!)
- **Log Level**: How much detail to log
  - DEBUG: Very verbose, for troubleshooting
  - INFO: Normal operation details
  - WARNING: Only important messages
  - ERROR: Only errors

### Remote Server Configuration

```
► Remote Server Configuration
────────────────────────────

ℹ You can add multiple remote servers for synchronization

Add a remote server? [Y/n]: y

Remote server name (e.g., 'backup-server'): backup-1
Remote server address/IP: backup.example.com
SSH port [22]: 22
SSH username: user
Authentication method
  1. SSH Key (recommended)
  2. Password
Choose [1-2]: 1
Path to SSH private key [~/.ssh/id_rsa]:
ℹ SSH key not found at ~/.ssh/id_rsa
Generate SSH key pair? [Y/n]: y

ℹ Generating SSH key pair at ~/.ssh/id_rsa...
✓ SSH key pair generated
Public key: ~/.ssh/id_rsa.pub
Copy public key to remote server now? [y/N]: y
```

**Adding Remote Servers:**

1. **Server Name**: Friendly name for your reference
2. **Server Address**: Hostname or IP address
3. **SSH Port**: Usually 22 (standard SSH)
4. **Username**: SSH username on remote server
5. **Authentication**:
   - **SSH Key** (recommended): More secure, passwordless
   - **Password**: Less secure but simpler setup

**SSH Key Generation:**

If you don't have an SSH key, the wizard can generate one automatically:
- Generates a 4096-bit RSA key
- Optionally copies the public key to the remote server
- Requires `ssh-copy-id` to be installed

**Sync Paths:**

```
Local directory to sync [~/documents]: /home/user/data
Remote directory to sync [/home/user/documents]: /data/sync
```

### Synchronization Preferences

```
► Synchronization Preferences
────────────────────────────

Synchronization strategy
  1. Delta (transfer only changes) - Recommended
  2. Full (transfer complete files)
  3. Adaptive (auto-select)
Choose [1-3]: 1

Bandwidth limit (MB/s, 0 for unlimited) [0]: 10
Full sync interval (seconds) [60]: 300
```

**Configuration Options:**

- **Sync Strategy**:
  - **Delta** (Recommended): Only transfers changed bytes (saves bandwidth)
  - **Full**: Transfers entire files (simpler, slower)
  - **Adaptive**: Automatically chooses based on file types

- **Bandwidth Limit**: Cap transfer speed
  - 0 = unlimited
  - >0 = limit in MB/s (e.g., 10 for 10 MB/s)

- **Sync Interval**: How often to do full sync (in seconds)
  - 60 = every 1 minute
  - 300 = every 5 minutes
  - 3600 = every hour

### System Preparation

```
► System Preparation
──────────────────

ℹ Configuration folder exists: /etc/fsrsync
✓ Created /etc/fsrsync/logs
ℹ Checking SSH connectivity to remote servers...
✓ SSH connection verified: user@backup.example.com:22

✓ System preparation completed
```

The wizard automatically:
- Creates necessary directories
- Sets appropriate file permissions
- Tests connectivity to remote servers
- Verifies prerequisites are met

### Setup Complete

```
============================================================
                    Setup Complete!
============================================================

Configuration saved to: /etc/fsrsync/config.json

System Configuration:
  Hostname: my-server
  Log Level: INFO
  Control Server: 0.0.0.0:8080
  Logs: /etc/fsrsync/logs/fsrsync.log

Remote Servers (1):

  1. backup-1
     Address: user@backup.example.com:22
     Local: /home/user/data
     Remote: /data/sync

Next Steps:
  1. Start FSRsync: fsrsync
  2. Open web interface: http://localhost:8080
  3. API key: your-secret-key

✓ FSRsync is ready to run!
```

## Configuration File

The wizard creates a `config.json` file containing all your settings:

```json
{
    "hostname": "my-server",
    "log_level": "INFO",
    "control_server_port": 8080,
    "control_server_host": "0.0.0.0",
    "control_server_secret": "your-secure-secret",
    "full_sync_interval": 60,
    "bandwidth_limit_mbps": 0,
    "logs": "/etc/fsrsync/logs/fsrsync.log",
    "destinations": [
        {
            "hostname": "backup-1",
            "host": "backup.example.com",
            "port": 22,
            "username": "user",
            "ssh_key_path": "/home/user/.ssh/id_rsa",
            "local_path": "/home/user/data",
            "remote_path": "/data/sync",
            "strategy": "delta",
            "enabled": true
        }
    ]
}
```

## Advanced: Running Without Wizard

If you prefer to use the old method without the interactive wizard, you can manually create the config file:

```bash
# Create the configuration folder
mkdir -p /etc/fsrsync

# Create config.json manually
cat > /etc/fsrsync/config.json << EOF
{
    "hostname": "my-server",
    "log_level": "INFO",
    "control_server_port": 8080,
    "control_server_host": "0.0.0.0",
    "control_server_secret": "your-secret",
    "full_sync_interval": 60,
    "destinations": []
}
EOF

# Set secure permissions
chmod 600 /etc/fsrsync/config.json
```

## Modifying Configuration After Setup

### Using the Web Interface

1. Open http://localhost:8080 (or your configured port)
2. Authenticate with your API secret
3. Use the Settings panel to modify configuration
4. Changes take effect after restart

### Manual Editing

1. Edit `/etc/fsrsync/config.json` directly
2. Restart FSRsync for changes to take effect

## Troubleshooting Setup

### SSH Connection Fails

**Problem**: "SSH connection failed: user@host:22"

**Solutions**:
1. Verify SSH is running on remote server: `ssh -p 22 user@host`
2. Check username and hostname are correct
3. Verify firewall allows SSH (port 22 by default)
4. Ensure SSH keys or password are configured correctly
5. Try manually with verbose output: `ssh -vvv user@host`

### Cannot Generate SSH Key

**Problem**: "Failed to generate SSH key"

**Solutions**:
1. Ensure `ssh-keygen` is installed (usually included with SSH)
2. Check permissions on `.ssh` folder
3. Ensure you have write permissions in the folder
4. Check available disk space

### Cannot Copy SSH Key

**Problem**: "Failed to copy public key to remote server"

**Solutions**:
1. Ensure `ssh-copy-id` is installed
2. Verify SSH access works first: `ssh user@host`
3. Ensure you can authenticate to the remote server
4. Check remote server's SSH configuration

### Configuration Not Found After Setup

**Problem**: "Configuration file not found"

**Solutions**:
1. Verify setup completed successfully
2. Check file exists: `ls -la /etc/fsrsync/config.json`
3. Verify file permissions: `chmod 600 /etc/fsrsync/config.json`
4. Try setup again: `fsrsync --setup`

## Best Practices

### Security

1. **API Secret**: Use a strong, random secret
   - Minimum 16 characters
   - Mix uppercase, lowercase, numbers, symbols
   - Example: `K#9$mP@2xL!qR8vN`

2. **SSH Keys**: Preferred over passwords
   - Generates unique 4096-bit RSA keys
   - No passwords transmitted over network
   - Passwordless authentication possible

3. **Permissions**: Wizard sets secure defaults
   - Config file: 600 (readable only by owner)
   - Directories: 755 (standard permissions)

### Performance

1. **Sync Interval**: Balance between freshness and load
   - Fast changes: 30-60 seconds
   - Normal use: 300 seconds (5 minutes)
   - Slow sync: 3600+ seconds

2. **Bandwidth Limit**: Prevent network congestion
   - Unlimited for LAN
   - 10-50 MB/s for corporate networks
   - <10 MB/s for internet connections

3. **Sync Strategy**:
   - **Delta**: Best for text files, code, documents
   - **Full**: Better for binary files, already compressed
   - **Adaptive**: Let FSRsync choose

### Multiple Servers

You can synchronize with multiple remote servers:
1. Run setup multiple times to add more destinations
2. Or manually edit config.json and add destinations
3. Each destination syncs independently
4. Resources are shared across all syncs

## Uninstalling/Resetting

### To Reset Configuration

```bash
# Reset to defaults
rm -rf /etc/fsrsync
fsrsync --setup
```

### To Remove Completely

```bash
# Remove FSRsync package
pip uninstall fsrsync

# Remove configuration
sudo rm -rf /etc/fsrsync
```

## Next Steps After Setup

1. **Start FSRsync**:
   ```bash
   fsrsync
   ```

2. **Check Status**:
   ```bash
   # Open web interface
   http://localhost:8080
   ```

3. **Monitor Logs**:
   ```bash
   tail -f /etc/fsrsync/logs/fsrsync.log
   ```

4. **Verify Synchronization**:
   - Add a file to local directory
   - Check if it appears on remote server
   - Check logs for sync details

5. **Configure Scheduling** (optional):
   ```bash
   # Add to crontab for automatic startup
   @reboot /root/.local/bin/fsrsync
   ```

## Support

For issues or questions:
1. Check logs: `/etc/fsrsync/logs/fsrsync.log`
2. Review this guide
3. Test SSH manually: `ssh -v user@host`
4. Check GitHub issues: https://github.com/ddemuro/fsrsync
