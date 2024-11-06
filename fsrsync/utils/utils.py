import os
import subprocess
import psutil

from .logs import Logger

logger = Logger()


def run_command(command, **kwargs):
    """
    Run a single command with optional kwargs for more control.

    :param command: The command to be executed.
    :return: Completed process object.
    captured_output = runner.run_command('ls -l', stdout='output.txt')
    print(captured_output)
    """
    try:
        result = subprocess.run(command, shell=True,
                                text=True, check=False, **kwargs)
        return True, result.returncode, result.stdout, result.stderr
    except subprocess.CalledProcessError as e:
        logger.error(f"Command failed with return code {e.returncode}")
        return False, e.returncode, e.output, e.stderr
    except Exception as e:  # pylint: disable=broad-except
        logger.error(f"Command failed with error: {e}")
        return False, None, str(e), None


def pipe_processes(read_process, write_process, input_file=None, output_file=None):
    """
    Pipe output from one process to another.

    :param read_process: The command for the reader process.
    :param write_process: The command for the writer process.
    :param input_file: Input file for writer process. Defaults to None.
    :param output_file: Output file for reader process. Defaults to None.
    :return: Tuple of CompletedProcess objects for both processes.

    Code sample usage:
    reader_process, writer_process = runner.pipe_processes(
        read_process="cat",
        write_process="grep keyword",
        input_file="path/to/input/file",
        output_file=None  # Capture output, default behavior
    )

    print(writer_process.returncode)  # Print the return code of the cat process

    reader_output = writer_process.stdout
    if reader_output:
        print(reader_output.decode('utf-8'))  # Decode and print captured output (if any)

    """

    # Run writer process first
    if input_file:
        writer_kwargs = {"stdin": input_file, "stdout": subprocess.PIPE}
    else:
        writer_kwargs = {}

    writer_process = run_command(write_process, **writer_kwargs)
    # Capture writer's stdout to feed into reader
    writer_output = writer_process.stdout

    # Run reader process with captured output as stdin
    if output_file:
        read_kwargs = {"stdin": writer_output, "stdout": output_file}
    else:
        read_kwargs = {}

    read_process = run_command(read_process, **read_kwargs)

    return (writer_process, read_process)


def validate_path(path):
    """
    Validate a path exists and is accessible.

    :param path: The path to validate.
    :return: True if path exists and is accessible, False otherwise.
    """
    try:
        return os.path.exists(path)
    except Exception as e:
        logger.error(f"Path validation failed: {e}")
        return False


def is_file_open(file_path):
    """ Check if a file is open by any process

    :param file_path: The path to the file
    :type file_path: str
    :return: True if file is open, False otherwise
    :rtype: bool
    """
    try:
        for proc in psutil.process_iter():
            try:
                if file_path in [f.path for f in proc.open_files()]:
                    return True  # File is open by this process
            except (psutil.NoSuchFile, psutil.AccessDenied, psutil.Error):
                pass  # Ignore errors
    except Exception as e:
        print(f"Error: {e}")

    return False  # File not open


def fix_path_slashes(path):
    """Fix path slashes"""
    # Check if it's a folder or file using os.path.isdir if it's a folder finish with / if it's a file remove /
    if os.path.isdir(path):
        if path[-1] != "/":
            path += "/"
    else:
        if path[-1] == "/":
            path = path[:-1]
    # Ensure we never ship a path with double slashes
    if "//" in path:
        path = path.replace("//", "/")
    return path
