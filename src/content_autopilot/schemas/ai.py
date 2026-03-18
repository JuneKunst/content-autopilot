"""Data models for AI processing (summarization, drafting)."""

from pydantic import BaseModel, ConfigDict


class SummaryResult(BaseModel):
    """Result from summarization task (T15→T16 contract)."""

    summary_ko: str
    source_url: str
    source_title: str
    source_lang: str = "en"
    key_points: list[str] = []
    token_usage: dict[str, int] = {}  # {input_tokens, output_tokens}


class ArticleDraft(BaseModel):
    """Draft article ready for publishing."""

    title_ko: str
    content_ko: str
    summary_ko: str
    source_attribution: str  # source URL
    persona_id: str = "default"
    tags: list[str] = []
    style_metadata: dict = {}

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "title_ko": "Pydantic v2 소개",
                "content_ko": "Pydantic v2는 주요 개선사항을 제공합니다...",
                "summary_ko": "Pydantic v2의 새로운 기능들을 소개합니다.",
                "source_attribution": "https://example.com/pydantic-v2",
                "persona_id": "tech_writer",
                "tags": ["python", "pydantic", "개발"],
                "style_metadata": {"tone": "informative", "length": "medium"},
            }
        }
    )
