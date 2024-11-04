import logging
import enum


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

    def __new__(cls, filename="log.txt"):
        """Create a new instance or return an existing one."""
        if cls._instance is None:
            cls._instance = super(Logger, cls).__new__(cls)
            cls._init_instance(filename)  # Initialize the instance
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
            self.logger.debug(message)

    def info(self, message):
        """Log an info message."""
        if self.check_message_level_greater_than_min(LogLevel.INFO.value):
            self.logger.info(message)

    def warning(self, message):
        """Log a warning message."""
        if self.check_message_level_greater_than_min(LogLevel.WARNING.value):
            self.logger.warning(message)

    def error(self, message):
        """Log an error message."""
        if self.check_message_level_greater_than_min(LogLevel.ERROR.value):
            self.logger.error(message)

    def critical(self, message):
        """Log a critical message."""
        if self.check_message_level_greater_than_min(LogLevel.CRITICAL.value):
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
