#!/bin/bash

# Setup ssh password
echo "root:test" | chpasswd

# Set app to the working directory
cd /app

# Generate keys
HOSTNAME=$(hostname)
mkdir -p /root/.ssh/
chmod 700 /root/.ssh/
if [ $HOSTNAME = "client" ]; then
    echo "Setting client keys"
    cp /root/keys/client/* /root/.ssh/
    chmod 600 /root/.ssh/id_rsa
    chmod 644 /root/.ssh/id_rsa.pub
else
    echo "Setting server keys"
    cp /root/keys/server/* /root/.ssh/
    chmod 600 /root/.ssh/id_rsa
    chmod 644 /root/.ssh/id_rsa.pub
fi
# Start SSH server in the background
/usr/sbin/sshd -D &

if [ "$OPERATION" == "sync" ]; then
    echo "Running the container, starting ssh and if parameter 'sync' is privided, starting syncapp"
    virtualenv -p python3 .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    python3 /app/app.py
else
    echo "We are not starting syncapp as the parameter 'sync' is not provided"
fi

if [ "$OPERATION" == "fullsync" ]; then
    echo "Running the container, starting ssh and if parameter 'fullsync' is privided, starting syncapp"
    virtualenv -p python3 .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    python3 /app/app.py --fullsync
else
    echo "We are not starting syncapp as the parameter 'fullsync' is not provided"
fi

# Keep the container running
while true; do sleep 10; done
