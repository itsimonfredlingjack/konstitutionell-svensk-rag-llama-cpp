"""
Structured logging configuration
Colored console output with JSON support for production
Auto-includes request_id from middleware context
"""

import logging
import sys
from datetime import datetime, UTC
from typing import Optional


class RequestContextFilter(logging.Filter):
    """
    Filter that automatically adds request_id to log records
    from the request context if available.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        # Try to get request_id from context
        try:
            from ..middleware import get_request_id

            request_id = get_request_id()
            if request_id:
                record.request_id = request_id
        except (ImportError, RuntimeError):
            # Not in request context or middleware not available
            pass

        # Always allow the record through
        return True


class ColoredFormatter(logging.Formatter):
    """Custom formatter with colors for console output"""

    # ANSI color codes
    COLORS = {
        "DEBUG": "\033[36m",  # Cyan
        "INFO": "\033[32m",  # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",  # Red
        "CRITICAL": "\033[35m",  # Magenta
    }
    RESET = "\033[0m"
    BOLD = "\033[1m"

    def format(self, record: logging.LogRecord) -> str:
        # Add color to level name
        level_color = self.COLORS.get(record.levelname, "")
        record.levelname = f"{level_color}{record.levelname}{self.RESET}"

        # Add timestamp (UTC, timezone-aware)
        record.timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")

        # Format module name
        record.module_name = record.name.split(".")[-1]

        # Add request_id prefix if available
        if hasattr(record, "request_id"):
            record.request_prefix = f"[{record.request_id[:8]}] "
        else:
            record.request_prefix = ""

        return super().format(record)


class JSONFormatter(logging.Formatter):
    """JSON formatter for production logging"""

    def format(self, record: logging.LogRecord) -> str:
        import json

        log_data = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add extra fields if present
        if hasattr(record, "request_id"):
            log_data["request_id"] = record.request_id
        if hasattr(record, "profile"):
            log_data["profile"] = record.profile
        if hasattr(record, "model"):
            log_data["model"] = record.model
        if hasattr(record, "user_id"):
            log_data["user_id"] = record.user_id
        if hasattr(record, "endpoint"):
            log_data["endpoint"] = record.endpoint

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data)


def setup_logging(
    level: str = "INFO", json_output: bool = False, log_file: Optional[str] = None
) -> None:
    """
    Configure logging for the application.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR)
        json_output: Use JSON format instead of colored console
        log_file: Optional file path for logging
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper()))

    # Clear existing handlers
    root_logger.handlers.clear()

    # Add request context filter to all handlers
    context_filter = RequestContextFilter()

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)
    console_handler.addFilter(context_filter)

    if json_output:
        console_handler.setFormatter(JSONFormatter())
    else:
        console_handler.setFormatter(
            ColoredFormatter(
                fmt="%(timestamp)s │ %(levelname)-8s │ %(module_name)-15s │ %(request_prefix)s%(message)s"
            )
        )

    root_logger.addHandler(console_handler)

    # File handler (if specified)
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.DEBUG)
        file_handler.addFilter(context_filter)
        file_handler.setFormatter(JSONFormatter())
        root_logger.addHandler(file_handler)

    # Reduce noise from third-party libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance with the given name.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Configured logger instance
    """
    return logging.getLogger(name)


class RequestLogger:
    """Context manager for request-scoped logging"""

    def __init__(self, logger: logging.Logger, request_id: str, **extra):
        self.logger = logger
        self.request_id = request_id
        self.extra = extra

    def _log(self, level: int, msg: str, **kwargs) -> None:
        extra = {"request_id": self.request_id, **self.extra, **kwargs}
        self.logger.log(level, msg, extra=extra)

    def debug(self, msg: str, **kwargs) -> None:
        self._log(logging.DEBUG, msg, **kwargs)

    def info(self, msg: str, **kwargs) -> None:
        self._log(logging.INFO, msg, **kwargs)

    def warning(self, msg: str, **kwargs) -> None:
        self._log(logging.WARNING, msg, **kwargs)

    def error(self, msg: str, **kwargs) -> None:
        self._log(logging.ERROR, msg, **kwargs)
