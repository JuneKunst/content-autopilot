"""Reddit collector using OAuth2 API."""
import httpx
from content_autopilot.schemas import RawItem
from content_autopilot.common.logger import get_logger
from content_autopilot.common.rate_limiter import RateLimiter
from content_autopilot.common.http_client import create_client
from content_autopilot.config import settings

log = get_logger("collectors.reddit")
REDDIT_TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
REDDIT_API_URL = "https://oauth.reddit.com"


class RedditCollector:
    def __init__(self, subreddits: list[str] | None = None):
        self.subreddits = subreddits or ["technology", "programming", "MachineLearning", "artificial", "startups", "worldnews"]
        self._rate_limiter = RateLimiter(requests_per_minute=90)  # Reddit: 100 QPM limit
        self._token: str | None = None
        self._client_id = settings.reddit_client_id
        self._client_secret = settings.reddit_client_secret

    async def _get_token(self, client: httpx.AsyncClient) -> str | None:
        """Get OAuth2 bearer token. Returns None if credentials not set."""
        if not self._client_id or not self._client_secret:
            return None
        resp = await client.post(
            REDDIT_TOKEN_URL,
            data={"grant_type": "client_credentials"},
            auth=(self._client_id, self._client_secret),
            headers={"User-Agent": "ContentAutopilot/0.1"},
        )
        if resp.status_code == 200:
            return resp.json().get("access_token")
        log.warning("reddit_auth_failed", status=resp.status_code)
        return None

    async def collect(self, limit: int = 25) -> list[RawItem]:
        """Collect hot posts from configured subreddits."""
        if not self._client_id or not self._client_secret:
            log.info("reddit_creds_missing", msg="Using mock mode - no credentials")
            return []  # graceful: return empty if no creds

        async with create_client() as client:
            token = await self._get_token(client)
            if not token:
                return []
            headers = {"Authorization": f"Bearer {token}", "User-Agent": "ContentAutopilot/0.1"}
            items = []
            per_subreddit = max(5, limit // len(self.subreddits))
            for subreddit in self.subreddits:
                await self._rate_limiter.acquire()
                try:
                    posts = await self._fetch_subreddit(client, headers, subreddit, per_subreddit)
                    items.extend(posts)
                except Exception as e:
                    log.warning("reddit_subreddit_error", subreddit=subreddit, error=str(e))
            return items[:limit]

    async def _fetch_subreddit(self, client, headers, subreddit: str, limit: int) -> list[RawItem]:
        resp = await client.get(
            f"{REDDIT_API_URL}/r/{subreddit}/hot.json",
            headers=headers,
            params={"limit": limit},
        )
        resp.raise_for_status()
        posts = resp.json()["data"]["children"]
        return [self._to_raw_item(p["data"], subreddit) for p in posts if self._is_valid(p["data"])]

    def _is_valid(self, post: dict) -> bool:
        if post.get("over_18", False):  # Filter NSFW
            return False
        if post.get("score", 0) < 10:
            return False
        return True

    def _to_raw_item(self, post: dict, subreddit: str) -> RawItem:
        url = post.get("url", "")
        if url.startswith("/r/"):  # self post
            url = f"https://reddit.com{url}"
        return RawItem(
            source="reddit",
            title=post.get("title", ""),
            url=url,
            content_preview=post.get("selftext", "")[:500],
            engagement={"upvotes": post.get("score", 0), "comments": post.get("num_comments", 0)},
            metadata={"subreddit": subreddit, "author": post.get("author", ""), "id": post.get("id", "")},
            external_id=f"reddit_{post.get('id', '')}",
            source_lang="en",
        )
