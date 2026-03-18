"""RawItem model for raw collected content."""

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from content_autopilot.db import Base


class RawItem(Base):
    """Represents raw content collected from a source."""

    __tablename__ = "raw_items"
    __table_args__ = (
        UniqueConstraint("source_id", "external_id", name="uq_source_external_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(
        ForeignKey("sources.id", ondelete="CASCADE"), nullable=False
    )
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    content_preview: Mapped[str] = mapped_column(Text, nullable=False)
    item_metadata: Mapped[dict] = mapped_column("metadata", JSON, nullable=False, default=dict)
    engagement_metrics: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<RawItem(id={self.id}, source_id={self.source_id}, title={self.title[:50]})>"
