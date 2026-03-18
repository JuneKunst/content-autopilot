"""Shared HTTP client configuration using httpx."""

import httpx
from typing import Optional, Dict, Any

USER_AGENT = "ContentAutopilot/0.1.0 (https://github.com/user/content-autopilot)"


def create_client(
    timeout: float = 30.0,
    headers: Optional[Dict[str, str]] = None,
) -> httpx.AsyncClient:
    """Create a configured async httpx client.
    
    Args:
        timeout: Request timeout in seconds
        headers: Additional headers to include (merged with defaults)
        
    Returns:
        Configured httpx.AsyncClient instance
    """
    default_headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    }
    
    if headers:
        default_headers.update(headers)
    
    return httpx.AsyncClient(
        timeout=timeout,
        headers=default_headers,
        follow_redirects=True,
    )
