"""Content collectors for various sources."""

from .hn import HNCollector
from .reddit import RedditCollector

__all__ = [
    "HNCollector",
    "RedditCollector",
]
