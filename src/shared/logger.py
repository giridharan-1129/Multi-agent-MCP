"""
Structured Logging Module.

WHAT: Centralized logging with correlation IDs
WHY: Track requests across multiple agents and services
HOW: Use structlog with JSON formatting for easy parsing

Example:
    from shared.logger import get_logger
    
    logger = get_logger(__name__)
    logger.info("message", user_id=123, correlation_id="abc-123")
"""

import contextvars
import json
import logging
import sys
import uuid
from typing import Any, Dict, Optional

import structlog

# Context variable for correlation ID
correlation_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar(
    "correlation_id", default=""
)


def get_correlation_id() -> str:
    """
    Get current correlation ID.

    Returns:
        Current correlation ID or empty string
    """
    return correlation_id_ctx.get()


def set_correlation_id(correlation_id: str) -> None:
    """
    Set correlation ID for current context.

    Args:
        correlation_id: ID to set
    """
    correlation_id_ctx.set(correlation_id)


def generate_correlation_id() -> str:
    """
    Generate new correlation ID.

    Returns:
        New unique correlation ID
    """
    return str(uuid.uuid4())


class CorrelationIDFilter(logging.Filter):
    """Add correlation ID to log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        """
        Add correlation ID to record.

        Args:
            record: Log record

        Returns:
            True to process record
        """
        record.correlation_id = get_correlation_id() or "NO_ID"
        return True


def json_renderer(logger: Any, name: str, event_dict: Dict[str, Any]) -> str:
    """
    Render event as JSON.

    Args:
        logger: Logger instance
        name: Logger name
        event_dict: Event dictionary

    Returns:
        JSON string
    """
    # Add correlation ID to every log
    event_dict["correlation_id"] = get_correlation_id() or "NO_ID"
    return json.dumps(event_dict)


def text_renderer(logger: Any, name: str, event_dict: Dict[str, Any]) -> str:
    """
    Render event as text.

    Args:
        logger: Logger instance
        name: Logger name
        event_dict: Event dictionary

    Returns:
        Formatted text string
    """
    correlation_id = get_correlation_id() or "NO_ID"
    message = event_dict.pop("event", "")
    
    # Format extra data
    extra = " | ".join(f"{k}={v}" for k, v in event_dict.items())
    if extra:
        return f"[{correlation_id}] {message} | {extra}"
    return f"[{correlation_id}] {message}"


def configure_logging(log_level: str = "INFO", log_format: str = "json") -> None:
    """
    Configure structlog.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_format: Format type ('json' or 'text')
    """
    # Choose renderer based on format
    if log_format == "json":
        renderer = json_renderer
    else:
        renderer = text_renderer

    # Configure structlog
    structlog.configure(
        processors=[
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Configure standard logging
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(name)s | %(levelname)s | %(correlation_id)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Add correlation ID filter
    handler.addFilter(CorrelationIDFilter())
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    root_logger.setLevel(log_level)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """
    Get logger instance.

    Args:
        name: Logger name (usually __name__)

    Returns:
        Logger instance

    Example:
        logger = get_logger(__name__)
        logger.info("message", extra_data=value)
    """
    return structlog.get_logger(name)


# Initialize logging on module import
configure_logging()