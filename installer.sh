#!/bin/bash
# Install script for FSRsync

# Set variables
FSRSYNC_SERVICE_FILE="/etc/systemd/system/fsrsync.service"
FSRSYNC_SCRIPT="/opt/fsrsync/fsrsync.py"

# Copy the service file to the systemd directory
sudo cp setup/fsrsync.service $FSRSYNC_SERVICE_FILE

# Reload systemd daemon
sudo systemctl daemon-reload

# Enable and start the service
sudo systemctl enable fsrsync
sudo systemctl start fsrsync

# Make sure the script is executable
sudo chmod +x $FSRSYNC_SCRIPT

# Create a backup of the config file (if it exists)
if [ -f "/etc/fsrsync/config.json" ]; then
  echo "Skipping config file backup, already exists."
  exit 0
fi

# Copy the default config file to the system directory
sudo cp config.json.sample /etc/fsrsync/config.json

echo "FSRsync service installed and started."
exit 0