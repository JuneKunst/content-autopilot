"""Protocol interfaces for AI pipeline operations."""

from typing import Protocol

from content_autopilot.schemas import ArticleDraft, SummaryResult


class AISummarizer(Protocol):
    """Protocol for AI summarization step.

    Implementations receive raw source content and return a Korean summary.
    """

    async def process(
        self,
        content: str,
        source_url: str,
        source_lang: str,
    ) -> SummaryResult:
        """Summarize content and return a structured result.

        Args:
            content: Raw source text to summarize.
            source_url: Original URL of the source.
            source_lang: Language code of the source (e.g. "en").

        Returns:
            SummaryResult with Korean summary and metadata.
        """
        ...


class AIHumanizer(Protocol):
    """Protocol for AI humanization / article drafting step.

    Implementations receive a Korean summary and return a persona-styled draft.
    """

    async def humanize(
        self,
        summary_ko: str,
        source_url: str,
        source_title: str,
    ) -> ArticleDraft:
        """Transform a Korean summary into a persona-styled article draft.

        Args:
            summary_ko: Korean summary text.
            source_url: Original source URL for attribution.
            source_title: Title of the original source.

        Returns:
            ArticleDraft ready for publishing.
        """
        ...
