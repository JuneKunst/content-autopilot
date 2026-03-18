"""Structured logging using structlog with JSON output."""

import structlog
import logging
from typing import Any


def get_logger(name: str = "content-autopilot") -> structlog.BoundLogger:
    """Get a configured structlog logger instance.
    
    Args:
        name: Logger name (typically module name)
        
    Returns:
        Configured structlog BoundLogger instance
    """
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    return structlog.get_logger(name)


# Module-level logger for convenience
log = get_logger()
