"""Data models for publishing operations."""

from datetime import datetime

from pydantic import BaseModel

from .ai import ArticleDraft


class PublishRequest(BaseModel):
    """Request to publish an article draft."""

    article_draft: ArticleDraft
    channels: list[str] = ["ghost"]  # ghost, telegram, discord
    scheduled_at: datetime | None = None


class PublishResult(BaseModel):
    """Result of a publishing operation."""

    channel: str
    status: str  # success, failed
    external_url: str | None = None
    error: str | None = None
