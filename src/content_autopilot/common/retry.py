"""Retry decorators using tenacity for resilient API calls."""

from typing import Any, Callable, TypeVar

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    retry_if_result,
    stop_after_attempt,
    wait_exponential,
)

F = TypeVar("F", bound=Callable[..., Any])


def with_retry(
    max_attempts: int = 3,
    min_wait: float = 1.0,
    max_wait: float = 60.0,
) -> Callable[[F], F]:
    """Decorator for exponential backoff retry on HTTP errors.

    Args:
        max_attempts: Maximum number of retry attempts
        min_wait: Minimum wait time between retries (seconds)
        max_wait: Maximum wait time between retries (seconds)

    Returns:
        Decorated function that retries on HTTP errors
    """
    return retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=1, min=min_wait, max=max_wait),
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
        reraise=True,
    )


def with_api_retry(max_attempts: int = 3) -> Callable[[F], F]:
    """Retry decorator that handles HTTP errors and 429 rate limit responses.

    Args:
        max_attempts: Maximum number of retry attempts

    Returns:
        Decorated function that retries on HTTP errors and rate limits
    """
    def should_retry(result: Any) -> bool:
        """Check if response indicates rate limiting (429)."""
        if isinstance(result, httpx.Response):
            return result.status_code == 429
        return False

    return retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=1, min=1.0, max=60.0),
        retry=(
            retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException))
            | retry_if_result(should_retry)
        ),
        reraise=True,
    )
