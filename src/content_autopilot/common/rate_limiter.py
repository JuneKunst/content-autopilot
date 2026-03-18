"""Token bucket rate limiter for API calls."""

import asyncio
import time
from typing import Optional


class RateLimiter:
    """Simple token bucket rate limiter for API calls.
    
    Implements a token bucket algorithm to enforce rate limits.
    Tokens are refilled at a constant rate (requests_per_minute).
    """
    
    def __init__(self, requests_per_minute: int = 60):
        """Initialize rate limiter.
        
        Args:
            requests_per_minute: Number of requests allowed per minute
        """
        self.rpm = requests_per_minute
        self._tokens: float = requests_per_minute
        self._last_refill: float = time.monotonic()
        self._lock = asyncio.Lock()
    
    async def acquire(self) -> None:
        """Wait until a token is available, then consume it.
        
        This method is async-safe and will block until a token is available.
        """
        async with self._lock:
            # Refill tokens based on elapsed time
            now = time.monotonic()
            elapsed = now - self._last_refill
            self._tokens = min(
                self.rpm,
                self._tokens + elapsed * (self.rpm / 60.0)
            )
            self._last_refill = now
            
            # Wait if no tokens available
            if self._tokens < 1:
                wait_time = (1 - self._tokens) / (self.rpm / 60.0)
                await asyncio.sleep(wait_time)
                self._tokens = 0
            else:
                self._tokens -= 1
    
    def reset(self) -> None:
        """Reset the rate limiter to initial state."""
        self._tokens = self.rpm
        self._last_refill = time.monotonic()
