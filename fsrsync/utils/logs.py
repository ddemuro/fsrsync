import os
import enum
import logging
from .constants import MAX_LOG_SIZE, DEFAULT_LOGS


class LogLevel(enum.Enum):
    """Log levels."""
    DEBUG = logging.DEBUG
    INFO = logging.INFO
    WARNING = logging.WARNING
    ERROR = logging.ERROR
    CRITICAL = logging.CRITICAL


class Logger:
    """Custom logger class."""

    _instance = None  # Initialize the class attribute to store the instance
    _min_level = logging.DEBUG

    def __new__(cls, filename=DEFAULT_LOGS):
        """Create a new instance or return an existing one."""
        if cls._instance is None:
            cls._instance = super(Logger, cls).__new__(cls)
            cls._init_instance(filename)  # Initialize the instance
            cls._filename = filename  # Store filename for file size checks
        return cls._instance  # Return the instance

    @classmethod
    def _init_instance(cls, filename):
        """Initialize the logger instance with a name."""
        cls.logger = logging.getLogger(__name__)
        cls.logger.setLevel(logging.DEBUG)

        # Create console handler and set level to debug
        ch = logging.StreamHandler()
        ch.setLevel(logging.DEBUG)

        # Create file handler and set level to info
        fh = logging.FileHandler(filename)
        fh.setLevel(logging.INFO)

        # Create formatter and add it to the handlers
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        ch.setFormatter(formatter)
        fh.setFormatter(formatter)

        # Add the handlers to the logger
        cls.logger.addHandler(ch)
        cls.logger.addHandler(fh)

    def debug(self, message):
        """Log a debug message."""
        if self.check_message_level_greater_than_min(LogLevel.DEBUG.value):
            self._check_log_size()
            self.logger.debug(message)

    def info(self, message):
        """Log an info message."""
        if self.check_message_level_greater_than_min(LogLevel.INFO.value):
            self._check_log_size()
            self.logger.info(message)

    def warning(self, message):
        """Log a warning message."""
        if self.check_message_level_greater_than_min(LogLevel.WARNING.value):
            self._check_log_size()
            self.logger.warning(message)

    def error(self, message):
        """Log an error message."""
        if self.check_message_level_greater_than_min(LogLevel.ERROR.value):
            self._check_log_size()
            self.logger.error(message)

    def critical(self, message):
        """Log a critical message."""
        if self.check_message_level_greater_than_min(LogLevel.CRITICAL.value):
            self._check_log_size()
            self.logger.critical(message)

    def set_level(self, level):
        """Set the minimum logging level."""
        self.logger.setLevel(level)
        # Convert to enum value
        self._min_level = LogLevel[level].value

    def get_level(self):
        """Get the minimum logging level."""
        return self._min_level

    def check_message_level_greater_than_min(self, level):
        """Check if the message level is greater than the minimum level."""
        # Compare with the enum value
        return level >= self._min_level

    def _check_log_size(self):
        """Check if the log file size exceeds MAX_LOG_SIZE and clear it if necessary."""
        if os.path.exists(self._filename) and os.path.getsize(self._filename) > MAX_LOG_SIZE:
            with open(self._filename, 'w', encoding="utf-8") as file:
                file.truncate(0)
            self.logger.info("Log file cleared due to exceeding maximum size.")
