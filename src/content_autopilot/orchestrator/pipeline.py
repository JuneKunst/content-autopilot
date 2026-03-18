from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import cast

from content_autopilot.collectors.github import GitHubCollector
from content_autopilot.collectors.hn import HNCollector
from content_autopilot.collectors.reddit import RedditCollector
from content_autopilot.collectors.rss import RSSCollector
from content_autopilot.collectors.youtube import YouTubeCollector
from content_autopilot.common.logger import get_logger
from content_autopilot.processing.dedup import DedupService
from content_autopilot.processing.humanizer import Humanizer
from content_autopilot.processing.scorer import ScoringEngine
from content_autopilot.processing.summarizer import Summarizer
from content_autopilot.publishers.discord import DiscordPublisher
from content_autopilot.publishers.ghost import GhostPublisher
from content_autopilot.publishers.telegram import TelegramPublisher
from content_autopilot.schemas import ArticleDraft, RawItem

log = get_logger("orchestrator.pipeline")


class PipelineResult:
    def __init__(self) -> None:
        self.collected: int = 0
        self.deduped: int = 0
        self.scored: int = 0
        self.published: int = 0
        self.errors: list[str] = []
        self.started_at: datetime = datetime.now(timezone.utc)
        self.completed_at: datetime | None = None

    @property
    def status(self) -> str:
        if self.errors and self.published == 0:
            return "failed"
        if self.errors:
            return "partial_failure"
        return "success"


class Pipeline:
    def __init__(self, dry_run: bool = False) -> None:
        self.dry_run: bool = dry_run
        self._dedup: DedupService = DedupService()
        self._scorer: ScoringEngine = ScoringEngine()
        self._summarizer: Summarizer = Summarizer()
        self._humanizer: Humanizer = Humanizer()
        self._ghost: GhostPublisher = GhostPublisher()
        self._telegram: TelegramPublisher = TelegramPublisher()
        self._discord: DiscordPublisher = DiscordPublisher()

    async def run(self) -> PipelineResult:
        result = PipelineResult()

        log.info("pipeline_stage", stage="collecting")
        raw_items = await self._collect_all()
        result.collected = len(raw_items)
        log.info("pipeline_collected", count=result.collected)

        if not raw_items:
            result.errors.append("No items collected")
            result.completed_at = datetime.now(timezone.utc)
            return result

        log.info("pipeline_stage", stage="deduplicating")
        unique_items = self._dedup.deduplicate(raw_items)
        result.deduped = len(unique_items)
        log.info("pipeline_deduped", before=result.collected, after=result.deduped)

        log.info("pipeline_stage", stage="scoring")
        scored_items = self._scorer.score_batch(unique_items)
        top_items = self._scorer.select_top_n(scored_items)
        result.scored = len(top_items)
        log.info("pipeline_scored", top_n=result.scored)

        log.info("pipeline_stage", stage="processing")
        drafts: list[ArticleDraft] = []
        for scored_item in top_items:
            try:
                summary = await self._summarizer.process(
                    content=scored_item.raw_item.content_preview or scored_item.raw_item.title,
                    source_url=scored_item.raw_item.url,
                    source_lang=scored_item.raw_item.source_lang,
                    source_title=scored_item.raw_item.title,
                )
                draft = await self._humanizer.humanize(
                    summary_ko=summary.summary_ko,
                    source_url=summary.source_url,
                    source_title=summary.source_title,
                )
                drafts.append(draft)
            except Exception as exc:
                title = scored_item.raw_item.title[:50]
                log.error("pipeline_ai_error", title=title, error=str(exc))
                result.errors.append(f"AI error for '{title}': {str(exc)[:100]}")

        log.info("pipeline_ai_processed", drafts=len(drafts))

        if self.dry_run:
            log.info("pipeline_dry_run", msg="Dry run - skipping publish")
            result.completed_at = datetime.now(timezone.utc)
            return result

        log.info("pipeline_stage", stage="publishing")
        for draft in drafts:
            try:
                ghost_result = await self._ghost.publish(draft)
                ghost_url = (
                    ghost_result.external_url if ghost_result.status == "success" else None
                )

                _ = await self._telegram.publish(draft, ghost_url=ghost_url)
                _ = await self._discord.publish(draft, ghost_url=ghost_url)

                if ghost_result.status == "success":
                    result.published += 1
                else:
                    result.errors.append(f"Ghost publish failed: {ghost_result.error}")
            except Exception as exc:
                log.error("pipeline_publish_error", error=str(exc))
                result.errors.append(f"Publish error: {str(exc)[:100]}")

        log.info("pipeline_published", count=result.published, errors=len(result.errors))
        result.completed_at = datetime.now(timezone.utc)
        return result

    async def _collect_all(self) -> list[RawItem]:
        collectors = [
            HNCollector().collect(limit=10),
            RedditCollector().collect(limit=10),
            GitHubCollector().collect(limit=5),
            RSSCollector().collect(limit=10),
            YouTubeCollector().collect(limit=5),
        ]
        results = await asyncio.gather(*collectors, return_exceptions=True)

        all_items: list[RawItem] = []
        for idx, result in enumerate(results):
            if isinstance(result, BaseException):
                log.warning("collector_error", collector=idx, error=str(result))
            elif isinstance(result, list):
                all_items.extend(cast(list[RawItem], result))
        return all_items
