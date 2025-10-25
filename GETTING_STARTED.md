# FSRsync - Getting Started

Welcome to FSRsync! This document will guide you through everything you need to know to get started.

## What is FSRsync?

FSRsync is a powerful, easy-to-use file synchronization tool that:
- 📁 Monitors filesystem changes in real-time
- 🔄 Automatically synchronizes files with remote servers
- ⚡ Uses intelligent delta sync to minimize bandwidth
- 🖥️ Provides a web interface for monitoring and control
- 🔐 Supports SSH key authentication for security

## Quick Start (5 Minutes)

### 1. Install FSRsync

```bash
pip install fsrsync
# or with pipx:
pipx install fsrsync
```

### 2. Run Setup Wizard

```bash
fsrsync --setup
```

The wizard will ask you a few simple questions about:
- Your local system
- Your remote server(s)
- How you want to sync files
- It will set up everything automatically

### 3. Start FSRsync

```bash
fsrsync
```

### 4. Monitor Progress

Open your browser to:
```
http://localhost:8080
```

That's it! Your files are now syncing automatically.

## Documentation

### For New Users
Start here if you're using FSRsync for the first time:
- **[Quick Start Guide](user_docs/QUICK_START.md)** - 5-minute overview
- **[Setup Wizard Guide](user_docs/SETUP_WIZARD_GUIDE.md)** - Detailed setup walkthrough

### For Developers & Technical Users
- **[Setup Wizard Summary](user_docs/SETUP_WIZARD_SUMMARY.md)** - Technical features overview
- **[Phase 17 Implementation](implementation_docs/PHASE_17_SUMMARY.md)** - Performance optimizations
- **[Lab Profiling Guide](implementation_docs/LAB_PROFILING_GUIDE.md)** - Testing and profiling

### Full Documentation Index
- **[User Documentation](user_docs/README.md)** - All user guides and testing info
- **[Implementation Documentation](implementation_docs/README.md)** - Technical details

## Common Tasks

### Add Another Remote Server

Edit your configuration:
```bash
nano /etc/fsrsync/config.json
```

Or run the setup wizard again:
```bash
fsrsync --setup
```

### View Logs

```bash
tail -f /etc/fsrsync/logs/fsrsync.log
```

### Access Web Interface

```
http://localhost:8080
```

Authenticate with your API secret (set during setup)

### Verify SSH Connection

```bash
# Test connection to remote server
ssh -v user@remote.host
```

### Change Configuration

Option 1: Edit JSON directly
```bash
nano /etc/fsrsync/config.json
fsrsync  # Restart to apply changes
```

Option 2: Run setup wizard
```bash
fsrsync --setup
```

## Features

### Local System Configuration
- System hostname
- Web interface port and address
- API security secret
- Logging configuration

### Remote Server Management
- Multiple remote servers
- SSH key or password authentication
- Automatic SSH key generation
- SSH connectivity testing

### Synchronization Options
- **Delta Sync** (recommended): Transfer only changed bytes
- **Full Sync**: Transfer complete files
- **Adaptive**: Automatically choose strategy

### Advanced Features
- Bandwidth limiting
- Real-time file monitoring
- Web dashboard
- Performance profiling
- Conflict resolution
- Multi-peer synchronization

## System Requirements

- **Python**: 3.7 or later
- **SSH**: For remote server connections
- **Network**: Access to remote servers over SSH

## Troubleshooting

### SSH Connection Fails

```bash
# Test SSH manually
ssh -v user@remote.host

# Common issues:
# - Wrong hostname/IP
# - Wrong username
# - SSH not running on remote
# - Firewall blocking port 22
# - Incorrect SSH key permissions
```

### Files Not Syncing

Check the logs:
```bash
tail -f /etc/fsrsync/logs/fsrsync.log
```

Common causes:
- SSH connection issues
- File permission problems
- Incorrect path configuration
- Network connectivity issues

### Slow Synchronization

- Check your network speed: `iperf3 -c remote.host`
- Increase sync interval in config
- Check system resources: `top`

## Command Reference

| Command | Purpose |
|---------|---------|
| `fsrsync --setup` | Run interactive setup wizard |
| `fsrsync --setupfolder PATH` | Setup with custom folder |
| `fsrsync` | Start FSRsync |
| `fsrsync --config PATH` | Use custom config file |
| `fsrsync --fullsync` | Force full synchronization |

## Directory Structure

```
fsrsync/
├── setup_wizard.py          # Interactive setup wizard
├── sync_app.py              # Main application
├── app.py                   # CLI entry point
└── utils/                   # Utility modules
    ├── configuration.py     # Configuration management
    ├── delta_optimizer.py   # Delta sync optimization
    └── ...

/etc/fsrsync/               # Configuration directory
├── config.json             # Configuration file
└── logs/
    └── fsrsync.log        # Log file
```

## Configuration File

Your configuration is stored in JSON format:

```json
{
    "hostname": "my-server",
    "log_level": "INFO",
    "control_server_port": 8080,
    "control_server_host": "0.0.0.0",
    "control_server_secret": "your-secret",
    "full_sync_interval": 60,
    "logs": "/etc/fsrsync/logs/fsrsync.log",
    "destinations": [
        {
            "hostname": "backup-server",
            "host": "backup.example.com",
            "port": 22,
            "username": "user",
            "ssh_key_path": "/home/user/.ssh/id_rsa",
            "local_path": "/home/user/data",
            "remote_path": "/data/sync",
            "strategy": "delta"
        }
    ]
}
```

## Security Best Practices

1. **Use SSH Keys**: More secure than passwords
   ```bash
   # Generate if needed
   ssh-keygen -t rsa -b 4096
   ```

2. **Protect Your API Secret**: Don't share your API secret
   - Change it regularly
   - Use a strong, random value
   - Keep it confidential

3. **Set File Permissions**: Config file should be readable only by owner
   ```bash
   chmod 600 /etc/fsrsync/config.json
   ```

4. **Monitor Logs**: Regularly check logs for errors
   ```bash
   tail -f /etc/fsrsync/logs/fsrsync.log
   ```

## Performance Tips

1. **Use Delta Sync**: Saves bandwidth and time
2. **Set Appropriate Intervals**: Balance between freshness and load
3. **Limit Bandwidth**: Prevent network congestion
4. **Monitor Resources**: Watch CPU, memory, and disk I/O

## Auto-Start on Boot

```bash
# Add to crontab
crontab -e

# Add this line:
@reboot /path/to/fsrsync
```

## Getting Help

1. **Check Documentation**: Start with this file
2. **Review Logs**: Check `/etc/fsrsync/logs/fsrsync.log`
3. **Test SSH**: Verify SSH works manually
4. **Web Dashboard**: Check status at `http://localhost:8080`

## What's Next?

1. ✅ Install FSRsync
2. ✅ Run `fsrsync --setup`
3. ✅ Start with `fsrsync`
4. ✅ Open web interface
5. ✅ Monitor synchronization
6. 📖 Read detailed guides as needed

## Additional Resources

- **Main README**: See `README.md`
- **User Guides**: See `user_docs/`
- **Technical Docs**: See `implementation_docs/`
- **GitHub**: https://github.com/ddemuro/fsrsync

---

**Welcome to FSRsync!** 🎉

You're just 5 minutes away from powerful, automatic file synchronization.

Start with `fsrsync --setup` and follow the interactive guide!
