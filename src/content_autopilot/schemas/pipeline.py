"""Data models for pipeline status and orchestration."""

from datetime import datetime

from pydantic import BaseModel


class PipelineStatus(BaseModel):
    """Current status of the content pipeline."""

    run_id: int | None = None
    stage: str  # collecting, scoring, processing, publishing, idle
    items_count: int = 0
    errors: list[str] = []
    started_at: datetime | None = None
