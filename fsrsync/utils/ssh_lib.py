"""This module contains the functions to run commands on the remote server"""
import os
import paramiko
from io import StringIO
from .utils import validate_path


def log_output(output, logger):
    """Log the output to the logger"""
    if logger:
        logger.info(output)


def read_linux_user_default_ssh_key():
    """Read the default SSH key for the current user"""
    current_user = os.getenv("USER")
    # Check if file exists:
    user = validate_path(f"/home/{current_user}/.ssh/id_rsa")
    root = validate_path("/root/.ssh/id_rsa")
    try:
        if user:
            return f"/home/{current_user}/.ssh/id_rsa"
        if root:
            return "/root/.ssh/id_rsa"
    except FileNotFoundError:
        return None


def read_ssh_key(ssh_key):
    """Read the SSH key from the provided path"""
    try:
        if validate_path(ssh_key):
            with open(ssh_key, "r", encoding="utf-8") as file:
                f = file.read().strip()
                stringiofile = StringIO(f)
                return paramiko.RSAKey.from_private_key(stringiofile)
    except FileNotFoundError:
        return None
    except paramiko.ssh_exception.SSHException as e:
        # Handle invalid key format
        print(f"Invalid SSH key format: {e}")
        return None


def run_ssh_command(command, host, username="root", ssh_key=None, logger=None):
    """Run a command on a remote server using SSH

    :param command: The command to run
    :type command: str
    :param host: The host to connect to
    :type host: str
    :param username: The username to use for the connection, defaults to "root"
    :type username: str, optional
    :param ssh_key: The SSH key to use for the connection, defaults to None
    :type ssh_key: str, optional
    :param logger: The logger to use for logging, defaults to None
    :type logger: logging.Logger, optional
    :return: The output of the command
    :rtype: str
    """
    try:
        if not host or not command:
            log_output("Host and command are required", logger)
            return None
        if not ssh_key:
            ssh_key = read_linux_user_default_ssh_key()
        if not ssh_key:
            log_output("No SSH key provided or found", logger)
            return

        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        # Use the provided key or password
        if ssh_key:
            # Load ssh_key
            log_output(f"Connecting to {host} with key {ssh_key}", logger)
            ssh_key = read_ssh_key(ssh_key)
            ssh.connect(host, username=username, pkey=ssh_key)
        else:
            log_output(f"Connecting to {host} with password", logger)
            ssh.connect(host, username=username)

        stdin, stdout, stderr = ssh.exec_command(
            command, timeout=1000, get_pty=True)
        output = stdout.read().decode('utf-8')
        err = stderr.read().decode('utf-8')
        exit_code = stdout.channel.recv_exit_status()
        log_output(f"Running command: {command}, stdout: {output}, stderr: {err}, exit_code: {exit_code}", logger)
        ssh.close()
        return False, exit_code, output, stderr
    except Exception as e:  # pylint: disable=broad-except
        log_output(f"Error running ssh command: {e}", logger)
