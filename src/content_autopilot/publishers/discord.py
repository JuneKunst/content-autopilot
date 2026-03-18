"""Discord Webhook publisher using Embed format."""
import httpx
from content_autopilot.schemas import ArticleDraft, PublishResult
from content_autopilot.config import settings
from content_autopilot.common.logger import get_logger
from content_autopilot.common.http_client import create_client

log = get_logger("publishers.discord")
EMBED_COLOR_BLUE = 0x5865F2  # Discord Blurple


class DiscordPublisher:
    def __init__(self, webhook_url: str | None = None):
        self._webhook_url = webhook_url or settings.discord_webhook_url

    def _build_embed(self, draft: ArticleDraft, ghost_url: str | None = None) -> dict:
        """Build Discord Embed object from ArticleDraft."""
        fields = []

        if draft.tags:
            fields.append({
                "name": "태그",
                "value": " ".join(f"`{tag}`" for tag in draft.tags[:5]),
                "inline": True,
            })

        if ghost_url:
            fields.append({
                "name": "블로그",
                "value": f"[전체 읽기]({ghost_url})",
                "inline": True,
            })

        embed = {
            "title": draft.title_ko[:256],  # Discord title limit
            "description": (draft.summary_ko or draft.content_ko[:300])[:4096],
            "color": EMBED_COLOR_BLUE,
            "fields": fields,
            "footer": {"text": f"출처: {draft.source_attribution[:100]}"},
            "url": ghost_url or draft.source_attribution,
        }

        return embed

    async def publish(self, draft: ArticleDraft, ghost_url: str | None = None) -> PublishResult:
        """Send Embed message to Discord channel via webhook."""
        if not self._webhook_url:
            log.info("discord_webhook_missing")
            return PublishResult(channel="discord", status="skipped", error="No webhook URL")

        embed = self._build_embed(draft, ghost_url)
        payload = {
            "embeds": [embed],
            "username": "Content Autopilot",
        }

        async with create_client() as client:
            try:
                resp = await client.post(
                    self._webhook_url,
                    json=payload,
                )
                resp.raise_for_status()
                log.info("discord_sent", channel=self._webhook_url[:30])
                return PublishResult(
                    channel="discord",
                    status="success",
                    external_url=self._webhook_url,
                )
            except httpx.HTTPStatusError as e:
                log.error("discord_failed", status=e.response.status_code, error=str(e))
                return PublishResult(channel="discord", status="failed", error=str(e))
            except Exception as e:
                log.error("discord_error", error=str(e))
                return PublishResult(channel="discord", status="failed", error=str(e))
