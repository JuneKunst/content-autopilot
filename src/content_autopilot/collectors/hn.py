"""HN (Hacker News) collector using Firebase API."""
import asyncio
import httpx
from content_autopilot.schemas import RawItem
from content_autopilot.common.logger import get_logger
from content_autopilot.common.rate_limiter import RateLimiter
from content_autopilot.common.http_client import create_client

HN_BASE_URL = "https://hacker-news.firebaseio.com/v0"
log = get_logger("collectors.hn")


class HNCollector:
    def __init__(self, min_score: int = 10, fetch_count: int = 30):
        self.min_score = min_score
        self.fetch_count = fetch_count
        self._seen_ids: set[int] = set()  # in-memory dedup for current session
        self._rate_limiter = RateLimiter(requests_per_minute=60)

    async def collect(self, limit: int = 30) -> list[RawItem]:
        """Fetch top HN stories and return as RawItems."""
        async with create_client() as client:
            # 1. Fetch top story IDs
            story_ids = await self._fetch_story_ids(client)
            # 2. Fetch item details in parallel (max 10 concurrent)
            items = await self._fetch_items_parallel(client, story_ids[:limit])
            # 3. Filter and convert to RawItem
            return [self._to_raw_item(item) for item in items if self._is_valid(item)]

    async def _fetch_story_ids(self, client: httpx.AsyncClient) -> list[int]:
        resp = await client.get(f"{HN_BASE_URL}/topstories.json")
        resp.raise_for_status()
        return resp.json()[:self.fetch_count]

    async def _fetch_items_parallel(self, client: httpx.AsyncClient, ids: list[int]) -> list[dict]:
        semaphore = asyncio.Semaphore(10)  # max 10 concurrent

        async def fetch_one(id: int) -> dict | None:
            async with semaphore:
                await self._rate_limiter.acquire()
                try:
                    resp = await client.get(f"{HN_BASE_URL}/item/{id}.json")
                    if resp.status_code == 200:
                        return resp.json()
                except Exception as e:
                    log.warning("hn_item_fetch_error", item_id=id, error=str(e))
                    return None

        results = await asyncio.gather(*[fetch_one(id) for id in ids])
        return [r for r in results if r]

    def _is_valid(self, item: dict) -> bool:
        if not item:
            return False
        if item.get("type") not in ("story",):
            return False
        if item.get("score", 0) < self.min_score:
            return False
        if item.get("id") in self._seen_ids:
            return False  # dedup
        return True

    def _to_raw_item(self, item: dict) -> RawItem:
        self._seen_ids.add(item["id"])
        return RawItem(
            source="hn",
            title=item.get("title", ""),
            url=item.get("url", f"https://news.ycombinator.com/item?id={item['id']}"),
            content_preview=item.get("text", "")[:500] if item.get("text") else "",
            engagement={"upvotes": item.get("score", 0), "comments": item.get("descendants", 0)},
            metadata={
                "hn_id": item.get("id"),
                "author": item.get("by", ""),
                "time": item.get("time", 0),
            },
            external_id=f"hn_{item.get('id', '')}",
            source_lang="en",
        )
