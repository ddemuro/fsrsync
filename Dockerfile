FROM python:3.10.15-slim-bullseye as base

ARG OPERATION
ARG ENVFILE

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=America/New_York
ENV OPERATION=${OPERATION}

USER root

WORKDIR /fsrsync

# Set root password
RUN echo 'root:test' | chpasswd

# Fix run
RUN mkdir /var/run/sshd && \
    chmod 0755 /var/run/sshd && \
    mkdir -p /etc/fsrsync

# Install rsync, ssh-server, and other dependencies
RUN apt-get update && \
    apt-get install -y \
    rsync \
    openssh-server \
    sshpass \
    python3-virtualenv \
    curl \
    sshpass \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Expose port 22 (SSH default)
EXPOSE 22

# Copy keys
COPY setup/keys/ /root/keys/

# Copy the setup files
COPY setup/ /fsrsync/setup/
COPY requirements.txt /fsrsync/

# Copy SSH server configuration file
COPY setup/sshd_config /etc/ssh/sshd_config

# Copy fsrsync files
COPY fsrsync/ /fsrsync/
COPY config/ /fsrsync/config/

VOLUME /root/destination
VOLUME /root/source

# Define a custom command to start SSH server and run the script
CMD ["/bin/bash", "./setup/run.sh"]
