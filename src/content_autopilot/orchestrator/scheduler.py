from __future__ import annotations

import heapq
import importlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml

from content_autopilot.common.logger import get_logger
from content_autopilot.orchestrator.pipeline import Pipeline
from content_autopilot.schemas import ArticleDraft

log = get_logger("orchestrator.scheduler")

AsyncIOScheduler: Any = importlib.import_module(
    "apscheduler.schedulers.asyncio"
).AsyncIOScheduler
CronTrigger: Any = importlib.import_module("apscheduler.triggers.cron").CronTrigger


class PipelineScheduler:
    def __init__(self, config_path: str = "config/schedule.yaml") -> None:
        self._config = self._load_config(config_path)
        timezone_name = str(self._config.get("timezone", "Asia/Seoul"))
        self._timezone = ZoneInfo(timezone_name)
        self._scheduler = AsyncIOScheduler(timezone=self._timezone)

    def _load_config(self, path: str) -> dict[str, object]:
        config_path = Path(path)
        if config_path.exists():
            with config_path.open(encoding="utf-8") as handle:
                loaded = yaml.safe_load(handle) or {}
            return loaded if isinstance(loaded, dict) else {}

        return {
            "schedules": [
                {"cron": "0 7 * * *"},
                {"cron": "0 12 * * *"},
                {"cron": "0 18 * * *"},
            ],
            "timezone": "Asia/Seoul",
        }

    def start(self) -> None:
        schedules = self._config.get("schedules", [])
        schedule_list = schedules if isinstance(schedules, list) else []

        for schedule in schedule_list:
            if not isinstance(schedule, dict):
                continue

            cron = str(schedule.get("cron", "0 7 * * *"))
            self._scheduler.add_job(
                self._run_pipeline,
                CronTrigger.from_crontab(cron, timezone=self._timezone),
                misfire_grace_time=300,
            )
            log.info("scheduler_job_added", cron=cron)

        self._scheduler.start()
        log.info("scheduler_started", job_count=len(schedule_list))

    def stop(self) -> None:
        self._scheduler.shutdown()

    async def _run_pipeline(self) -> None:
        log.info("scheduler_triggered")
        pipeline = Pipeline()
        result = await pipeline.run()
        log.info(
            "scheduler_pipeline_done",
            status=result.status,
            published=result.published,
            errors=len(result.errors),
        )


# ---------------------------------------------------------------------------
# ContentScheduler — priority queue with minimum interval enforcement
# ---------------------------------------------------------------------------


@dataclass(order=True)
class ScheduledItem:
    scheduled_at: datetime
    score: float = field(compare=False)
    article: ArticleDraft = field(compare=False)
    retry_count: int = field(compare=False, default=0)
    max_retries: int = field(compare=False, default=3)


class ContentScheduler:
    """Priority queue scheduler for content publishing with minimum interval enforcement."""

    MIN_INTERVAL_HOURS = 2

    def __init__(self) -> None:
        self._queue: list[ScheduledItem] = []
        self._failed: list[ScheduledItem] = []

    def add_item(
        self,
        article: ArticleDraft,
        score: float,
        preferred_time: datetime | None = None,
    ) -> datetime:
        """Add article to queue, respecting minimum interval."""
        scheduled_at = self._find_next_slot(preferred_time or datetime.now(timezone.utc))
        item = ScheduledItem(scheduled_at=scheduled_at, score=score, article=article)
        heapq.heappush(self._queue, item)
        return scheduled_at

    def _find_next_slot(self, desired_time: datetime) -> datetime:
        """Find next available slot that respects MIN_INTERVAL_HOURS."""
        if not self._queue:
            return desired_time

        latest = max(item.scheduled_at for item in self._queue)
        min_next = latest + timedelta(hours=self.MIN_INTERVAL_HOURS)

        return max(desired_time, min_next)

    def get_queue(self) -> list[ScheduledItem]:
        """Return queue sorted by scheduled_at."""
        return sorted(self._queue, key=lambda x: x.scheduled_at)

    def pop_due(self) -> list[ScheduledItem]:
        """Pop all items due for publishing (scheduled_at <= now)."""
        now = datetime.now(timezone.utc)
        due = []
        while self._queue and self._queue[0].scheduled_at <= now:
            due.append(heapq.heappop(self._queue))
        return due

    def add_retry(self, item: ScheduledItem) -> bool:
        """Schedule a failed item for retry.

        Returns True if retry scheduled, False if max retries exceeded.
        """
        if item.retry_count >= item.max_retries:
            self._failed.append(item)
            return False
        retry_item = ScheduledItem(
            scheduled_at=datetime.now(timezone.utc) + timedelta(hours=self.MIN_INTERVAL_HOURS),
            score=item.score,
            article=item.article,
            retry_count=item.retry_count + 1,
            max_retries=item.max_retries,
        )
        heapq.heappush(self._queue, retry_item)
        return True

    def queue_size(self) -> int:
        return len(self._queue)

    def failed_count(self) -> int:
        return len(self._failed)
