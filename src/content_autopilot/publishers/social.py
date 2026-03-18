"""SNS cross-posting foundation: Mastodon + Bluesky."""
import httpx

from content_autopilot.common.http_client import create_client
from content_autopilot.common.logger import get_logger
from content_autopilot.config import settings
from content_autopilot.schemas import ArticleDraft, PublishResult

log = get_logger("publishers.social")


class MastodonPublisher:
    def __init__(self, access_token: str | None = None, instance: str | None = None):
        self._token = access_token or settings.mastodon_access_token
        self._instance = (instance or settings.mastodon_instance or "https://mastodon.social").rstrip("/")

    def _format_status(self, draft: ArticleDraft, ghost_url: str | None = None) -> str:
        """Format for Mastodon (500 char limit)."""
        url = ghost_url or draft.source_attribution
        hashtags = " ".join(f"#{tag.replace(' ', '_')}" for tag in draft.tags[:3])
        summary = draft.summary_ko[:200] if draft.summary_ko else draft.title_ko
        text = f"{draft.title_ko}\n\n{summary}\n\n{url}"
        if hashtags:
            text += f"\n\n{hashtags}"
        return text[:500]  # Mastodon limit

    async def publish_text(self, text: str) -> PublishResult:
        """Publish text directly to Mastodon."""
        if not self._token:
            return PublishResult(channel="mastodon", status="skipped", error="No access token")
        async with create_client() as client:
            try:
                resp = await client.post(
                    f"{self._instance}/api/v1/statuses",
                    json={"status": text, "visibility": "public"},
                    headers={"Authorization": f"Bearer {self._token}"},
                )
                resp.raise_for_status()
                data = resp.json()
                url = data.get("url", "")
                return PublishResult(
                    channel="mastodon", status="success", external_url=url
                )
            except httpx.HTTPStatusError as e:
                return PublishResult(channel="mastodon", status="failed", error=str(e))
            except Exception as e:
                return PublishResult(channel="mastodon", status="failed", error=str(e))

    async def publish(self, draft: ArticleDraft, ghost_url: str | None = None) -> PublishResult:
        text = self._format_status(draft, ghost_url)
        return await self.publish_text(text)


class BlueskyPublisher:
    def __init__(self, identifier: str | None = None, app_password: str | None = None):
        self._identifier = identifier or settings.bluesky_identifier
        self._app_password = app_password or settings.bluesky_app_password
        self._access_token: str | None = None

    def _format_post(self, draft: ArticleDraft, ghost_url: str | None = None) -> str:
        """Format for Bluesky (300 char limit)."""
        url = ghost_url or draft.source_attribution
        summary = draft.summary_ko[:100] if draft.summary_ko else draft.title_ko[:100]
        text = f"{draft.title_ko}\n\n{summary}\n\n{url}"
        return text[:300]  # Bluesky limit

    async def _get_token(self, client: httpx.AsyncClient) -> str | None:
        if not self._identifier or not self._app_password:
            return None
        resp = await client.post(
            "https://bsky.social/xrpc/com.atproto.server.createSession",
            json={"identifier": self._identifier, "password": self._app_password},
        )
        if resp.status_code == 200:
            return resp.json().get("accessJwt")
        return None

    async def publish(self, draft: ArticleDraft, ghost_url: str | None = None) -> PublishResult:
        if not self._identifier or not self._app_password:
            return PublishResult(channel="bluesky", status="skipped", error="No credentials")
        text = self._format_post(draft, ghost_url)
        async with create_client() as client:
            try:
                token = await self._get_token(client)
                if not token:
                    return PublishResult(channel="bluesky", status="failed", error="Auth failed")
                from datetime import datetime, timezone
                resp = await client.post(
                    "https://bsky.social/xrpc/com.atproto.repo.createRecord",
                    json={
                        "repo": self._identifier,
                        "collection": "app.bsky.feed.post",
                        "record": {
                            "$type": "app.bsky.feed.post",
                            "text": text,
                            "createdAt": datetime.now(timezone.utc).isoformat(),
                        }
                    },
                    headers={"Authorization": f"Bearer {token}"},
                )
                resp.raise_for_status()
                data = resp.json()
                uri = data.get("uri", "")
                return PublishResult(
                    channel="bluesky", status="success", external_url=uri
                )
            except httpx.HTTPStatusError as e:
                return PublishResult(channel="bluesky", status="failed", error=str(e))
            except Exception as e:
                return PublishResult(channel="bluesky", status="failed", error=str(e))
