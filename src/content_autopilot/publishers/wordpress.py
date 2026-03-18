"""WordPress publisher using WP REST API."""
import base64

import httpx
import markdown

from content_autopilot.common.http_client import create_client
from content_autopilot.common.logger import get_logger
from content_autopilot.config import settings
from content_autopilot.schemas import ArticleDraft, PublishResult

log = get_logger("publishers.wordpress")


class WordPressPublisher:
    def __init__(
        self,
        site_url: str | None = None,
        username: str | None = None,
        app_password: str | None = None,
    ):
        self.site_url = (site_url or settings.wp_site_url).rstrip("/")
        self._username = username or settings.wp_username
        self._app_password = app_password or settings.wp_app_password

    def _get_auth_header(self) -> dict[str, str]:
        """HTTP Basic Auth with Application Password."""
        creds = f"{self._username}:{self._app_password}"
        encoded = base64.b64encode(creds.encode()).decode()
        return {"Authorization": f"Basic {encoded}"}

    def _draft_to_post(self, draft: ArticleDraft) -> dict[str, str | list[str]]:
        """Convert ArticleDraft to WP REST API post payload."""
        html_content = markdown.markdown(draft.content_ko)
        if draft.source_attribution and draft.source_attribution not in html_content:
            url = draft.source_attribution
            html_content += (
                f'\n<p>출처: <a href="{url}">{url}</a></p>'
            )

        return {
            "title": draft.title_ko,
            "content": html_content,
            "excerpt": draft.summary_ko[:300] if draft.summary_ko else "",
            "status": "publish",
            "tags": [],  # WP tags need IDs, skip for now
            "categories": [],
        }

    async def publish(self, draft: ArticleDraft) -> PublishResult:
        if not self._username or not self._app_password:
            return PublishResult(
                channel="wordpress", status="skipped", error="No credentials"
            )

        post_data = self._draft_to_post(draft)
        headers = {**self._get_auth_header(), "Content-Type": "application/json"}

        async with create_client() as client:
            try:
                resp = await client.post(
                    f"{self.site_url}/wp-json/wp/v2/posts",
                    json=post_data,
                    headers=headers,
                )
                resp.raise_for_status()
                post = resp.json()
                post_url = post.get("link", "")
                log.info(
                    "wordpress_published",
                    title=draft.title_ko[:30],
                    url=post_url,
                )
                return PublishResult(
                    channel="wordpress", status="success", external_url=post_url
                )
            except httpx.HTTPStatusError as e:
                log.error(
                    "wordpress_failed",
                    status=e.response.status_code,
                    error=str(e),
                )
                return PublishResult(
                    channel="wordpress", status="failed", error=str(e)
                )
            except Exception as e:
                log.error("wordpress_error", error=str(e))
                return PublishResult(
                    channel="wordpress", status="failed", error=str(e)
                )
