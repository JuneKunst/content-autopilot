"""YouTube Data API v3 collector."""
import httpx
from datetime import datetime, timedelta, timezone
from content_autopilot.schemas import RawItem
from content_autopilot.common.logger import get_logger
from content_autopilot.common.rate_limiter import RateLimiter
from content_autopilot.common.http_client import create_client
from content_autopilot.config import settings

log = get_logger("collectors.youtube")
YOUTUBE_API_URL = "https://www.googleapis.com/youtube/v3"
DAILY_QUOTA_LIMIT = 9500  # leave buffer from 10000 limit
SEARCH_QUOTA_COST = 100   # search.list costs 100 units
VIDEOS_QUOTA_COST = 1     # videos.list costs 1 unit per video


class YouTubeCollector:
    def __init__(self, search_queries: list[str] | None = None):
        self.search_queries = search_queries or ["AI technology 2024", "programming tutorial", "tech news"]
        self._api_key = settings.youtube_api_key
        self.quota_used = 0
        self.quota_limit = DAILY_QUOTA_LIMIT
        self._rate_limiter = RateLimiter(requests_per_minute=30)

    @property
    def quota_remaining(self) -> int:
        return max(0, self.quota_limit - self.quota_used)

    async def collect(self, limit: int = 10) -> list[RawItem]:
        """Collect trending YouTube videos."""
        if not self._api_key:
            log.info("youtube_api_key_missing", msg="No YouTube API key, returning empty")
            return []

        async with create_client() as client:
            items = []
            # Strategy 1: Most popular videos by region
            if self.quota_remaining >= SEARCH_QUOTA_COST:
                popular = await self._get_most_popular(client, min(limit // 2, 5))
                items.extend(popular)

            # Strategy 2: Search by query
            for query in self.search_queries[:2]:
                if self.quota_remaining < SEARCH_QUOTA_COST:
                    log.warning("youtube_quota_low", remaining=self.quota_remaining)
                    break
                await self._rate_limiter.acquire()
                results = await self._search_videos(client, query, 5)
                items.extend(results)

            log.info("youtube_quota_used", used=self.quota_used, limit=self.quota_limit)
            # Dedup by video ID
            seen_ids = set()
            unique_items = []
            for item in items:
                if item.external_id not in seen_ids:
                    seen_ids.add(item.external_id)
                    unique_items.append(item)
            return unique_items[:limit]

    async def _get_most_popular(self, client: httpx.AsyncClient, max_results: int = 5) -> list[RawItem]:
        """Get most popular videos in Korea."""
        await self._rate_limiter.acquire()
        resp = await client.get(
            f"{YOUTUBE_API_URL}/videos",
            params={
                "key": self._api_key,
                "part": "snippet,statistics",
                "chart": "mostPopular",
                "regionCode": "KR",
                "maxResults": max_results,
            }
        )
        if resp.status_code != 200:
            log.warning("youtube_api_error", status=resp.status_code, endpoint="mostPopular")
            return []
        self.quota_used += VIDEOS_QUOTA_COST * max_results
        return [self._video_to_raw_item(v) for v in resp.json().get("items", [])]

    async def _search_videos(self, client, query: str, max_results: int = 5) -> list[RawItem]:
        """Search for videos by query."""
        yesterday = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")
        resp = await client.get(
            f"{YOUTUBE_API_URL}/search",
            params={
                "key": self._api_key,
                "part": "snippet",
                "q": query,
                "type": "video",
                "order": "viewCount",
                "publishedAfter": yesterday,
                "maxResults": max_results,
            }
        )
        if resp.status_code != 200:
            return []
        self.quota_used += SEARCH_QUOTA_COST
        items = resp.json().get("items", [])
        return [self._search_result_to_raw_item(v) for v in items]

    def _video_to_raw_item(self, video: dict) -> RawItem:
        stats = video.get("statistics", {})
        snippet = video.get("snippet", {})
        video_id = video.get("id", "")
        return RawItem(
            source="youtube",
            title=snippet.get("title", ""),
            url=f"https://www.youtube.com/watch?v={video_id}",
            content_preview=snippet.get("description", "")[:500],
            engagement={
                "upvotes": int(stats.get("likeCount", 0) or 0),
                "comments": int(stats.get("commentCount", 0) or 0),
                "views": int(stats.get("viewCount", 0) or 0),
            },
            metadata={"channel": snippet.get("channelTitle", ""), "video_id": video_id},
            external_id=f"youtube_{video_id}",
            source_lang="ko",  # mostPopular in KR region
        )

    def _search_result_to_raw_item(self, item: dict) -> RawItem:
        snippet = item.get("snippet", {})
        video_id = item.get("id", {}).get("videoId", "")
        return RawItem(
            source="youtube",
            title=snippet.get("title", ""),
            url=f"https://www.youtube.com/watch?v={video_id}",
            content_preview=snippet.get("description", "")[:500],
            engagement={"upvotes": 0, "comments": 0, "views": 0},  # search doesn't include stats
            metadata={"channel": snippet.get("channelTitle", ""), "video_id": video_id},
            external_id=f"youtube_{video_id}",
            source_lang="en",
        )
