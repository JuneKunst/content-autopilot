"""Ghost CMS publisher using Admin API with JWT authentication."""
import time

import httpx
import jwt
import markdown

from content_autopilot.common.http_client import create_client
from content_autopilot.common.logger import get_logger
from content_autopilot.config import settings
from content_autopilot.schemas import ArticleDraft, PublishResult

log = get_logger("publishers.ghost")


class GhostPublisher:
    def __init__(
        self,
        ghost_url: str | None = None,
        admin_key: str | None = None,
        newsletter_enabled: bool = False,
    ):
        self.ghost_url = (ghost_url or settings.ghost_url).rstrip("/")
        self._admin_key = admin_key or settings.ghost_admin_key
        self.newsletter_enabled = newsletter_enabled

    def _make_jwt(self) -> str:
        """Generate Ghost Admin API JWT token from admin key.

        Ghost Admin API key format: "{id}:{secret}"
        where id is 24 hex chars and secret is 64 hex chars.
        """
        if not self._admin_key or ":" not in self._admin_key:
            raise ValueError("Invalid Ghost admin key format. Expected: id:secret")
        key_id, secret = self._admin_key.split(":", 1)
        iat = int(time.time())
        payload = {"iat": iat, "exp": iat + 5 * 60, "aud": "/admin/"}
        token = jwt.encode(
            payload,
            bytes.fromhex(secret),
            algorithm="HS256",
            headers={"kid": key_id},
        )
        return token

    def _get_headers(self) -> dict:
        return {
            "Authorization": f"Ghost {self._make_jwt()}",
            "Content-Type": "application/json",
        }

    def _draft_to_post(self, draft: ArticleDraft) -> dict:
        """Convert ArticleDraft to Ghost post payload."""
        # Convert markdown content to HTML
        html_content = markdown.markdown(draft.content_ko)

        # Add source attribution footer
        if draft.source_attribution and draft.source_attribution not in html_content:
            html_content += (
                f'\n<p>📌 출처: <a href="{draft.source_attribution}">'
                f"{draft.source_attribution}</a></p>"
            )

        # Build tags list
        tags = [{"name": tag} for tag in (draft.tags or [])]

        post_payload = {
            "title": draft.title_ko,
            "html": html_content,
            "status": "published",
            "tags": tags,
            "custom_excerpt": draft.summary_ko[:300] if draft.summary_ko else "",
        }

        if self.newsletter_enabled:
            post_payload["newsletter"] = {"id": "default"}
            post_payload["email_segment"] = "all"

        return post_payload

    async def publish(self, draft: ArticleDraft, send_newsletter: bool = False) -> PublishResult:
        """Publish an ArticleDraft to Ghost CMS."""
        if send_newsletter:
            self.newsletter_enabled = True

        post_data = {"posts": [self._draft_to_post(draft)]}

        async with create_client() as client:
            try:
                resp = await client.post(
                    f"{self.ghost_url}/ghost/api/admin/posts/",
                    json=post_data,
                    headers=self._get_headers(),
                )
                resp.raise_for_status()
                post = resp.json()["posts"][0]
                post_url = post.get("url", "")
                log.info("ghost_published", title=draft.title_ko, url=post_url)
                return PublishResult(
                    channel="ghost",
                    status="success",
                    external_url=post_url,
                )
            except httpx.HTTPStatusError as e:
                log.error("ghost_publish_failed", status=e.response.status_code, error=str(e))
                return PublishResult(channel="ghost", status="failed", error=str(e))
            except Exception as e:
                log.error("ghost_publish_error", error=str(e))
                return PublishResult(channel="ghost", status="failed", error=str(e))

    async def get_members_count(self) -> int:
        """Get total members count from Ghost Admin API."""
        async with create_client() as client:
            try:
                resp = await client.get(
                    f"{self.ghost_url}/ghost/api/admin/members/",
                    headers=self._get_headers(),
                    params={"limit": 1},
                )
                resp.raise_for_status()
                data = resp.json()
                return data.get("meta", {}).get("pagination", {}).get("total", 0)
            except Exception as e:
                log.error("ghost_members_error", error=str(e))
                return 0
