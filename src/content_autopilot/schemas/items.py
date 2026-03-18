"""Data models for content items (raw and scored)."""

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field


class RawItem(BaseModel):
    """Raw content item collected from a source."""

    source: str  # "hn", "reddit", "github", "rss", "youtube"
    title: str
    url: str
    content_preview: str = ""
    engagement: dict[str, int] = {}  # {upvotes, comments, views}
    metadata: dict = {}
    collected_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    external_id: str = ""  # ID from source system
    source_lang: str = "en"  # "en" or "ko"

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "source": "hn",
                "title": "Introducing Pydantic v2",
                "url": "https://example.com/pydantic-v2",
                "content_preview": "Pydantic v2 brings major improvements...",
                "engagement": {"upvotes": 150, "comments": 42},
                "metadata": {"category": "python"},
                "collected_at": "2024-03-18T10:30:00",
                "external_id": "hn_12345",
                "source_lang": "en",
            }
        }
    )


class ScoredItem(BaseModel):
    """Content item with relevance score."""

    raw_item: RawItem
    score: float
    breakdown: dict[str, float] = {}  # {velocity, engagement, etc.}
    is_duplicate: bool = False
