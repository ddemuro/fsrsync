# FSRsync Quick Start Guide

Get FSRsync up and running in 5 minutes!

## Installation

```bash
# Install FSRsync
pip install fsrsync

# Or using pipx (recommended for CLI tools)
pipx install fsrsync
```

## Quick Setup (3 Steps)

### Step 1: Run the Setup Wizard

```bash
fsrsync --setup
```

The interactive wizard will ask you:
- 📋 System hostname and settings
- 🔐 Remote server connection details (SSH)
- ⚙️ Synchronization preferences
- ✅ Confirms everything is ready

### Step 2: Start FSRsync

```bash
fsrsync
```

That's it! FSRsync is now running.

### Step 3: Open the Web Dashboard

Open your browser to:
```
http://localhost:8080
```

Login with the API secret you created during setup.

## First Sync

1. **Add files** to your local directory (configured during setup)
2. **Check the dashboard** to see sync progress
3. **Verify files** appear on the remote server

## Common Tasks

### Check Sync Status

```bash
# View logs
tail -f /etc/fsrsync/logs/fsrsync.log

# Open web dashboard
http://localhost:8080
```

### Add Another Remote Server

```bash
# Edit configuration
nano /etc/fsrsync/config.json

# Or run setup again for interactive configuration
fsrsync --setup
```

### Configure to Auto-Start

```bash
# Add to crontab
crontab -e

# Add this line:
@reboot /path/to/fsrsync
```

### Stop FSRsync

```bash
# Press Ctrl+C in the terminal where it's running
# Or kill the process:
pkill fsrsync
```

## System Requirements

- **Python**: 3.7+
- **SSH**: For remote server connections
- **Network**: Access to remote servers

## Troubleshooting

### Setup Issues

1. **SSH connection fails**
   - Verify remote server is accessible: `ssh user@host`
   - Check firewall allows port 22
   - Verify username is correct

2. **SSH key generation fails**
   - Ensure `ssh-keygen` is installed
   - Check disk space and permissions

### Sync Issues

1. **Files not syncing**
   - Check web dashboard for errors
   - Review logs: `tail -f /etc/fsrsync/logs/fsrsync.log`
   - Verify SSH access: `ssh user@host`
   - Check file permissions on both systems

2. **Slow synchronization**
   - Check network speed: `iperf3 -c remote.host`
   - Increase sync interval in config
   - Check system resources: `top` or `htop`

## What's Next?

- **Read the full guide**: See `SETUP_WIZARD_GUIDE.md`
- **Advanced configuration**: Edit `config.json`
- **Monitor performance**: Use the web dashboard
- **Schedule syncs**: Set up cron jobs

## Need Help?

1. Check the logs: `/etc/fsrsync/logs/fsrsync.log`
2. Review this guide
3. Check GitHub: https://github.com/ddemuro/fsrsync
4. Test SSH manually: `ssh -v user@host`

---

**That's it!** You now have FSRsync keeping your systems in sync. 🎉
