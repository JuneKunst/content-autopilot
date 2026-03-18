from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml

from content_autopilot.common.logger import get_logger
from content_autopilot.orchestrator.pipeline import Pipeline

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
