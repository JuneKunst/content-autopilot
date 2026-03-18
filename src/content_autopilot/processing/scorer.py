import math
from datetime import datetime, timezone
from collections.abc import Mapping

from content_autopilot.common.config_loader import load_yaml_config
from content_autopilot.schemas import RawItem, ScoredItem

DEFAULT_WEIGHTS = {
    "volume": 0.3,
    "velocity": 0.2,
    "comment_ratio": 0.1,
    "cross_platform": 0.2,
    "source_authority": 0.1,
    "time_decay": 0.1,
}

SOURCE_AUTHORITY = {
    "hn": 1.0,
    "reddit": 0.8,
    "github": 0.7,
    "youtube": 0.6,
    "rss": 0.5,
}


class ScoringEngine:
    def __init__(self, config_path: str = "config/scoring.yaml"):
        try:
            raw_config = load_yaml_config(config_path)
            config: dict[str, object]
            if isinstance(raw_config, dict):
                config = {str(key): value for key, value in raw_config.items()}
            else:
                config = {}

            weights = config.get("weights")
            if isinstance(weights, Mapping):
                self.weights: dict[str, float] = {
                    str(key): float(value)
                    for key, value in weights.items()
                    if isinstance(value, int | float)
                }
                if not self.weights:
                    self.weights = DEFAULT_WEIGHTS.copy()
            else:
                self.weights = DEFAULT_WEIGHTS.copy()

            authority = config.get("source_authority")
            if isinstance(authority, Mapping):
                self.source_authority: dict[str, float] = {
                    str(key): float(value)
                    for key, value in authority.items()
                    if isinstance(value, int | float)
                }
                if not self.source_authority:
                    self.source_authority = SOURCE_AUTHORITY.copy()
            else:
                self.source_authority = SOURCE_AUTHORITY.copy()

            time_decay = config.get("time_decay")
            if isinstance(time_decay, Mapping):
                half_life_hours = time_decay.get("half_life_hours")
            else:
                half_life_hours = None

            if isinstance(half_life_hours, int | float):
                self.half_life_hours: float = float(half_life_hours)
            else:
                self.half_life_hours = 24.0

            top_n = config.get("top_n", 3)
            self.top_n: int = int(top_n) if isinstance(top_n, int | float) else 3
        except FileNotFoundError:
            self.weights = DEFAULT_WEIGHTS.copy()
            self.source_authority = SOURCE_AUTHORITY.copy()
            self.half_life_hours = 24.0
            self.top_n = 3

    def score_item(
        self,
        item: RawItem,
        cross_platform_ids: set[str] | None = None,
    ) -> ScoredItem:
        upvotes = max(0, item.engagement.get("upvotes", 0))
        comments = max(0, item.engagement.get("comments", 0))
        volume = min(1.0, math.log10(upvotes + 1) / 4.0)
        age_hours = max(0.1, self._age_hours(item.collected_at))
        velocity = min(1.0, (upvotes / age_hours) / 100.0)
        comment_ratio = min(1.0, comments / (upvotes + 1))

        cross_platform = (
            1.0
            if cross_platform_ids is not None and item.external_id in cross_platform_ids
            else 0.0
        )
        authority = self.source_authority.get(item.source, 0.5)
        decay = self._time_decay(age_hours)

        w = self.weights
        raw_score = (
            w.get("volume", 0.3) * volume
            + w.get("velocity", 0.2) * velocity
            + w.get("comment_ratio", 0.1) * comment_ratio
            + w.get("cross_platform", 0.2) * cross_platform
            + w.get("source_authority", 0.1) * authority
            - w.get("time_decay", 0.1) * decay
        )
        score = max(0.0, min(1.0, raw_score))

        breakdown = {
            "volume": round(volume, 3),
            "velocity": round(velocity, 3),
            "comment_ratio": round(comment_ratio, 3),
            "cross_platform": cross_platform,
            "source_authority": authority,
            "time_decay": round(decay, 3),
            "age_hours": round(age_hours, 1),
        }

        return ScoredItem(raw_item=item, score=round(score, 4), breakdown=breakdown)

    def score_batch(self, items: list[RawItem]) -> list[ScoredItem]:
        if not items:
            return []

        url_sources: dict[str, set[str]] = {}
        for item in items:
            normalized_url = item.url.lower().rstrip("/")
            if normalized_url not in url_sources:
                url_sources[normalized_url] = set()
            url_sources[normalized_url].add(item.source)

        cross_platform_urls = {
            url for url, sources in url_sources.items() if len(sources) > 1
        }
        cross_platform_ids = {
            item.external_id
            for item in items
            if item.url.lower().rstrip("/") in cross_platform_urls
        }

        return [self.score_item(item, cross_platform_ids) for item in items]

    def select_top_n(
        self,
        scored_items: list[ScoredItem],
        n: int | None = None,
    ) -> list[ScoredItem]:
        limit = n or self.top_n
        return sorted(scored_items, key=lambda item: item.score, reverse=True)[:limit]

    def _age_hours(self, collected_at: datetime) -> float:
        now = datetime.now(timezone.utc)
        if collected_at.tzinfo is None:
            collected_at = collected_at.replace(tzinfo=timezone.utc)
        delta = now - collected_at
        return max(0.0, delta.total_seconds() / 3600)

    def _time_decay(self, age_hours: float) -> float:
        if age_hours <= 0:
            return 0.0
        return 1.0 - math.pow(0.5, age_hours / self.half_life_hours)
