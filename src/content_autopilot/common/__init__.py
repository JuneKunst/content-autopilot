"""Common utilities for content-autopilot."""

from content_autopilot.common.config_loader import (
    load_persona_config,
    load_source_config,
    load_yaml_config,
)
from content_autopilot.common.http_client import USER_AGENT, create_client
from content_autopilot.common.logger import get_logger, log
from content_autopilot.common.rate_limiter import RateLimiter
from content_autopilot.common.retry import with_api_retry, with_retry
from content_autopilot.common.text_utils import (
    extract_urls,
    normalize_whitespace,
    strip_html,
    truncate,
)

__all__ = [
    "get_logger",
    "log",
    "with_retry",
    "with_api_retry",
    "RateLimiter",
    "load_yaml_config",
    "load_source_config",
    "load_persona_config",
    "create_client",
    "USER_AGENT",
    "strip_html",
    "truncate",
    "extract_urls",
    "normalize_whitespace",
]
