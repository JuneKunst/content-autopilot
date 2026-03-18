"""RSS/Atom feed collector."""
import asyncio
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import feedparser

from content_autopilot.common.logger import get_logger
from content_autopilot.common.rate_limiter import RateLimiter
from content_autopilot.common.text_utils import strip_html, truncate
from content_autopilot.schemas import RawItem

log = get_logger("collectors.rss")

DEFAULT_FEEDS = [
    {"url": "https://news.hada.io/rss", "name": "geeknews", "lang": "ko"},
    {"url": "https://techcrunch.com/feed/", "name": "techcrunch", "lang": "en"},
    {"url": "https://feeds.arstechnica.com/arstechnica/index", "name": "arstechnica", "lang": "en"},
    {"url": "https://hnrss.org/frontpage", "name": "hn_rss", "lang": "en"},
]


class RSSCollector:
    def __init__(self, feeds: list[dict] | None = None, max_age_hours: int = 24):
        self.feeds = feeds or DEFAULT_FEEDS
        self.max_age_hours = max_age_hours
        self._rate_limiter = RateLimiter(requests_per_minute=30)

    async def collect(self, limit: int = 20) -> list[RawItem]:
        """Collect recent RSS entries from all configured feeds."""
        loop = asyncio.get_event_loop()
        all_items = []
        for feed_config in self.feeds:
            try:
                # Apply rate limiting before fetching
                await self._rate_limiter.acquire()
                # feedparser is sync, run in thread pool
                items = await loop.run_in_executor(None, self._fetch_feed, feed_config)
                all_items.extend(items)
            except Exception as e:
                log.warning("rss_feed_error", feed=feed_config.get("name"), error=str(e))

        # Sort by date desc, limit
        all_items.sort(key=lambda x: x.collected_at, reverse=True)
        return all_items[:limit]

    def _fetch_feed(self, feed_config: dict) -> list[RawItem]:
        """Synchronous feedparser call (run in thread pool)."""
        parsed = feedparser.parse(feed_config["url"])
        cutoff = datetime.now(timezone.utc) - timedelta(hours=self.max_age_hours)
        items = []
        for entry in parsed.entries:
            pub_date = self._parse_date(entry)
            if pub_date and pub_date < cutoff:
                continue  # too old
            item = self._entry_to_raw_item(entry, feed_config)
            if item:
                items.append(item)
        return items

    def _parse_date(self, entry) -> datetime | None:
        """Parse entry publication date."""
        for field in ("published", "updated"):
            if hasattr(entry, field):
                try:
                    return parsedate_to_datetime(getattr(entry, field)).replace(
                        tzinfo=timezone.utc
                    )
                except Exception as e:
                    log.debug("rss_date_parse_failed", field=field, error=str(e))
        return None

    def _entry_to_raw_item(self, entry, feed_config: dict) -> RawItem | None:
        title = getattr(entry, "title", "").strip()
        link = getattr(entry, "link", "")
        if not title or not link:
            return None

        # Extract content preview (strip HTML)
        content = ""
        if hasattr(entry, "summary"):
            content = strip_html(entry.summary)
        elif hasattr(entry, "content") and entry.content:
            content = strip_html(entry.content[0].value)

        return RawItem(
            source=feed_config.get("name", "rss"),
            title=title,
            url=link,
            content_preview=truncate(content, 500),
            engagement={"upvotes": 0, "comments": 0},  # RSS doesn't have engagement
            metadata={"feed_url": feed_config["url"], "feed_name": feed_config.get("name", "rss")},
            external_id=f"rss_{hash(link)}",
            source_lang=feed_config.get("lang", "en"),
        )
