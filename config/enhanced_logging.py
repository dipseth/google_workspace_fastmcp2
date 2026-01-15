"""
Enhanced Logging Utility Module
Provides rich colored logging with file path tracking, line numbers,
and automatically truncated long messages.
"""

import datetime
import logging
import os
import sys
import time
from functools import wraps
from pathlib import Path

# ======== Color Configuration ========
COLORS = {
    # Log levels
    "DEBUG": "\033[38;5;39m",  # Blue
    "INFO": "\033[38;5;34m",  # Green
    "WARNING": "\033[38;5;214m",  # Orange
    "ERROR": "\033[38;5;196m",  # Red
    "CRITICAL": "\033[48;5;196;38;5;231m",  # White on Red
    # Components
    "TIMESTAMP": "\033[38;5;246m",  # Dark Gray
    "PATH": "\033[1;38;5;93m",  # Bold Purple
    "FILE": "\033[1;38;5;63m",  # Bold Blue
    "FUNCTION": "\033[38;5;220m",  # Yellow
    "LINE": "\033[38;5;69m",  # Light Blue
    "MSG_CONTENT": "\033[38;5;255m",  # White
    "RESET": "\033[0m",
}

# Maximum log message length before truncation
MAX_MSG_LENGTH = 3000

# Global logger instance to avoid re-initialization
_root_logger_initialized = False


def get_log_directory():
    """
    Get the log directory from environment variable or fall back to system temp.
    This ensures we have a writable location even in restricted environments.
    """
    # Try environment variable first
    log_path = os.getenv("LOG_PATH")
    if log_path:
        return Path(log_path)

    # Try user's home directory
    try:
        home_logs = Path.home() / "logs" / "fastmcp"
        return home_logs
    except:
        pass

    # Fall back to system temp directory
    import tempfile

    temp_logs = Path(tempfile.gettempdir()) / "fastmcp_logs"
    return temp_logs


class ColoredLogRecord(logging.LogRecord):
    """Enhanced LogRecord with colored components and path information."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Extract relative path (if possible)
        try:
            cwd = os.getcwd()
            if self.pathname.startswith(cwd):
                self.rel_pathname = self.pathname[len(cwd) + 1 :]
            else:
                self.rel_pathname = self.pathname
        except:
            self.rel_pathname = self.pathname

        # Extract directory and filename separately
        self.directory = os.path.dirname(self.rel_pathname)
        self.filename = os.path.basename(self.pathname)

        # Add color attributes
        for color_name, color_code in COLORS.items():
            setattr(self, f"color_{color_name.lower()}", color_code)

        # Set level-specific color
        self.color_level = COLORS.get(self.levelname, COLORS.get("INFO"))

        # Truncate message if needed
        if isinstance(self.msg, str) and len(self.msg) > MAX_MSG_LENGTH:
            self.msg = self.msg[: MAX_MSG_LENGTH - 3] + "..."


class ColoredFormatter(logging.Formatter):
    """Formatter that applies colors and custom formatting to log records."""

    def __init__(self, fmt=None, datefmt=None, use_colors=True):
        super().__init__(fmt, datefmt)
        self.use_colors = use_colors and self._should_use_colors()

    def _should_use_colors(self):
        """Check if the terminal supports colors"""
        try:
            return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()
        except:
            return False

    def format(self, record):
        # Make sure all color attributes exist
        if not hasattr(record, "color_reset"):
            for color_name, color_code in COLORS.items():
                attr_name = f"color_{color_name.lower()}"
                if not hasattr(record, attr_name):
                    setattr(record, attr_name, color_code)

        # Format the log message
        result = super().format(record)

        # Strip color codes if colors are disabled
        if not self.use_colors:
            for color_code in COLORS.values():
                result = result.replace(color_code, "")

        return result


def setup_logger(level=None):
    """
    Set up enhanced logging with colored output and timestamped directories.
    This function sets up the root logger and returns it for convenience.

    Args:
        level: Logging level (defaults to LOG_LEVEL env var or INFO)

    Returns:
        logging.Logger: The root logger instance
    """
    global _root_logger_initialized

    # Avoid re-initializing if already done
    if _root_logger_initialized:
        return logging.getLogger()

    # Determine log level
    if level is None:
        log_level_str = os.getenv("LOG_LEVEL", "INFO").upper()
        level = getattr(logging, log_level_str, logging.INFO)

    # Override standard LogRecord factory with our enhanced version
    logging.setLogRecordFactory(ColoredLogRecord)

    # Get log directory (with fallback for restricted environments)
    log_dir = get_log_directory()

    # Create log directory structure with error handling
    try:
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        daily_log_dir = log_dir / today
        daily_log_dir.mkdir(parents=True, exist_ok=True)

        # Create timestamped log file
        timestamp = datetime.datetime.now().strftime("%H-%M-%S")
        log_file = daily_log_dir / f"app_log_{timestamp}.log"

        # Test if we can write to the directory
        test_file = daily_log_dir / "test_write.tmp"
        test_file.touch()
        test_file.unlink()

    except (OSError, PermissionError) as e:
        # If we can't create files, fall back to console-only logging
        print(
            f"Warning: Cannot create log files ({e}). Using console logging only.",
            file=sys.stderr,
        )
        log_file = None

    # Define log format with colors
    console_format = (
        "%(color_timestamp)s%(asctime)s%(color_reset)s "
        "%(color_path)s%(directory)s/%(color_reset)s"
        "%(color_file)s%(filename)s:%(lineno)d%(color_reset)s "
        "%(color_level)s[%(levelname).1s]%(color_reset)s "
        "%(color_msg_content)s%(message)s%(color_reset)s"
    )

    # Plain format for file logs (no colors)
    file_format = "%(asctime)s %(directory)s/%(filename)s:%(lineno)d [%(levelname).1s] %(message)s"

    # Get the root logger and configure it
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Remove any existing handlers to avoid duplicates
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Configure file handler (only if we can write files)
    if log_file:
        try:
            file_handler = logging.FileHandler(log_file)
            file_handler.setLevel(level)
            file_formatter = logging.Formatter(file_format, datefmt="%Y-%m-%d %H:%M:%S")
            file_handler.setFormatter(file_formatter)
            root_logger.addHandler(file_handler)
        except (OSError, PermissionError):
            print(
                "Warning: Cannot create file handler. Using console logging only.",
                file=sys.stderr,
            )

    # Configure console handler with colors
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_formatter = ColoredFormatter(console_format, datefmt="%Y-%m-%d %H:%M:%S")
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    # Mark as initialized
    _root_logger_initialized = True

    root_logger.debug("Enhanced logger initialized")
    return root_logger


def get_logger(name=None):
    """
    Get a named logger instance.
    Ensures the root logger is set up if not already done.

    Args:
        name (str, optional): Name for the logger. Defaults to None.

    Returns:
        logging.Logger: Named logger instance
    """
    # Ensure root logger is set up
    if not _root_logger_initialized:
        setup_logger()

    return logging.getLogger(name)


def log_execution_time(func):
    """
    Decorator that logs function execution time.
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        logger = get_logger(func.__module__)
        start_time = time.time()

        logger.debug(f"Starting {func.__name__}")

        try:
            result = func(*args, **kwargs)
            execution_time = time.time() - start_time
            logger.debug(f"Completed {func.__name__} in {execution_time:.3f}s")
            return result
        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(
                f"Failed {func.__name__} after {execution_time:.3f}s: {str(e)}"
            )
            raise

    return wrapper
