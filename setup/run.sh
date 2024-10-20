#!/bin/bash

# Setup ssh password
echo "root:test" | chpasswd

# Set app to the working directory
cd /app

# Start SSH server in the background
/usr/sbin/sshd -D &

if [ "$OPERATION" = "sync" ]; then
    echo "Running the container, starting ssh and if parameter 'sync' is privided, starting syncapp"
    virtualenv -p python3 .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    python3 /app/app.py
else
    echo "We are not starting syncapp as the parameter 'sync' is not provided"
fi

# Keep the container running
while true; do sleep 10; done
