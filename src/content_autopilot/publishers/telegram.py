"""Telegram Bot publisher for channel posting."""
import httpx
from content_autopilot.schemas.ai import ArticleDraft
from content_autopilot.schemas.publishing import PublishResult
from content_autopilot.config import settings
from content_autopilot.common.logger import get_logger
from content_autopilot.common.http_client import create_client

log = get_logger("publishers.telegram")


class TelegramPublisher:
    def __init__(self, bot_token: str | None = None, channel_id: str | None = None):
        self._token = bot_token or settings.tg_bot_token
        self._channel_id = channel_id or settings.tg_channel_id

    def _format_message(self, draft: ArticleDraft, ghost_url: str | None = None) -> str:
        """Format ArticleDraft as Telegram HTML message."""
        # Telegram HTML: <b>, <i>, <a href="...">
        msg_parts = [
            f"<b>{draft.title_ko}</b>",
            "",
            draft.summary_ko[:200] if draft.summary_ko else draft.content_ko[:200],
            "",
        ]
        if ghost_url:
            msg_parts.append(f'🔗 <a href="{ghost_url}">전체 읽기</a>')
        msg_parts.append(f'📌 출처: <a href="{draft.source_attribution}">{draft.source_attribution}</a>')

        if draft.tags:
            hashtags = " ".join(f"#{tag.replace(' ', '_')}" for tag in draft.tags[:5])
            msg_parts.append(hashtags)

        return "\n".join(msg_parts)

    async def publish(self, draft: ArticleDraft, ghost_url: str | None = None) -> PublishResult:
        """Send message to Telegram channel."""
        if not self._token or not self._channel_id:
            log.info("telegram_creds_missing")
            return PublishResult(channel="telegram", status="skipped", error="No credentials")

        message = self._format_message(draft, ghost_url)

        async with create_client() as client:
            try:
                resp = await client.post(
                    f"https://api.telegram.org/bot{self._token}/sendMessage",
                    json={
                        "chat_id": self._channel_id,
                        "text": message,
                        "parse_mode": "HTML",
                        "disable_web_page_preview": False,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                msg_id = data.get("result", {}).get("message_id", "")
                log.info("telegram_sent", message_id=msg_id, channel=self._channel_id)
                return PublishResult(
                    channel="telegram",
                    status="success",
                    external_url=str(msg_id),
                )
            except httpx.HTTPStatusError as e:
                log.error("telegram_failed", status=e.response.status_code, error=str(e))
                return PublishResult(channel="telegram", status="failed", error=str(e))
            except Exception as e:
                log.error("telegram_error", error=str(e))
                return PublishResult(channel="telegram", status="failed", error=str(e))
