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
fi
if [ $HOSTNAME = "server" ]; then
    echo "Setting server keys"
    cp /root/keys/server/* /root/.ssh/
    chmod 600 /root/.ssh/id_rsa
    chmod 644 /root/.ssh/id_rsa.pub
fi
# Start SSH server in the background
/usr/sbin/sshd -D &disown
# Wait for SSH server to start
sleep 3

if [ "$OPERATION" == "sync" ]; then
    echo "Running the container as sync operation"
    virtualenv -p python3 .venv &>> /dev/null
    source .venv/bin/activate
    pip install -r requirements.txt &>> /dev/null
    echo "Starting the application... with sync operation"
    echo "ENVFILE: $ENVFILE"
    python3 /app/app.py --config_file $ENVFILE
fi

if [ "$OPERATION" == "fullsync" ]; then
    echo "Running the container as fullsync operation"
    virtualenv -p python3 .venv &>> /dev/null
    source .venv/bin/activate
    pip install -r requirements.txt &>> /dev/null
    echo "Starting the application... with fullsync operation"
    echo "ENVFILE: $ENVFILE"
    python3 /app/app.py --config_file $ENVFILE --fullsync
fi

# Keep the container running
while true; do sleep 10; done
