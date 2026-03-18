"""GitHub trending repositories collector."""
from datetime import datetime, timedelta
import httpx
from content_autopilot.schemas import RawItem
from content_autopilot.common.logger import get_logger
from content_autopilot.common.rate_limiter import RateLimiter
from content_autopilot.common.http_client import create_client
from content_autopilot.config import settings

log = get_logger("collectors.github")
GITHUB_API_URL = "https://api.github.com"


class GitHubCollector:
    def __init__(self, min_stars: int = 50, languages: list[str] | None = None):
        self.min_stars = min_stars
        self.languages = languages or ["python", "typescript", "go", "rust", ""]  # "" = any
        # GitHub rate limit: 60/hour without token, 5000/hour with token
        self._rate_limiter = RateLimiter(requests_per_minute=10)  # conservative
        self._token = settings.github_token

    async def collect(self, limit: int = 20) -> list[RawItem]:
        """Collect trending GitHub repos from last 24 hours."""
        yesterday = (datetime.utcnow() - timedelta(hours=24)).strftime("%Y-%m-%d")
        headers = {"Accept": "application/vnd.github.v3+json"}
        if self._token:
            headers["Authorization"] = f"token {self._token}"

        async with create_client(headers=headers) as client:
            items = []
            for language in self.languages[:3]:  # limit languages to avoid quota
                await self._rate_limiter.acquire()
                try:
                    repos = await self._search_repos(client, yesterday, language, min(limit, 10))
                    items.extend(repos)
                except Exception as e:
                    log.warning("github_search_error", language=language, error=str(e))
            return items[:limit]

    async def _search_repos(self, client, since_date: str, language: str, limit: int) -> list[RawItem]:
        query = f"created:>{since_date} stars:>{self.min_stars}"
        if language:
            query += f" language:{language}"

        resp = await client.get(
            f"{GITHUB_API_URL}/search/repositories",
            params={"q": query, "sort": "stars", "order": "desc", "per_page": limit},
        )
        if resp.status_code == 403:
            log.warning("github_rate_limit", headers=dict(resp.headers))
            return []
        resp.raise_for_status()
        return [self._to_raw_item(repo) for repo in resp.json()["items"]]

    def _to_raw_item(self, repo: dict) -> RawItem:
        description = repo.get("description") or ""
        return RawItem(
            source="github",
            title=f"{repo['full_name']}: {description or 'No description'}",
            url=repo["html_url"],
            content_preview=description[:500],
            engagement={"upvotes": repo.get("stargazers_count", 0), "comments": repo.get("open_issues_count", 0)},
            metadata={
                "language": repo.get("language", ""),
                "topics": repo.get("topics", []),
                "forks": repo.get("forks_count", 0),
                "full_name": repo.get("full_name", ""),
            },
            external_id=f"github_{repo.get('id', '')}",
            source_lang="en",
        )
