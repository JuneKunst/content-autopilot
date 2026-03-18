"""PipelineRun model for tracking pipeline executions."""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from content_autopilot.db import Base


class PipelineRun(Base):
    """Represents a single execution of the content pipeline."""

    __tablename__ = "pipeline_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    items_collected: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    items_scored: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    items_published: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_log: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<PipelineRun(id={self.id}, status={self.status}, started_at={self.started_at})>"
