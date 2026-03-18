"""Article model for processed articles."""

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from content_autopilot.db import Base


class Article(Base):
    """Represents a processed article ready for publication."""

    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(primary_key=True)
    scored_item_id: Mapped[int] = mapped_column(
        ForeignKey("scored_items.id", ondelete="CASCADE"), nullable=False
    )
    title_ko: Mapped[str] = mapped_column(String(500), nullable=False)
    content_ko: Mapped[str] = mapped_column(Text, nullable=False)
    summary_ko: Mapped[str] = mapped_column(Text, nullable=False)
    persona_id: Mapped[str] = mapped_column(String(100), nullable=False)
    style_metadata: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    source_attribution: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<Article(id={self.id}, scored_item_id={self.scored_item_id}, persona_id={self.persona_id})>"
