"""ScoredItem model for scored content items."""

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from content_autopilot.db import Base


class ScoredItem(Base):
    """Represents a raw item after scoring and duplicate detection."""

    __tablename__ = "scored_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    raw_item_id: Mapped[int] = mapped_column(
        ForeignKey("raw_items.id", ondelete="CASCADE"), nullable=False
    )
    score: Mapped[float] = mapped_column(Float, nullable=False)
    score_breakdown: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    is_duplicate: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    scored_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<ScoredItem(id={self.id}, raw_item_id={self.raw_item_id}, score={self.score})>"
