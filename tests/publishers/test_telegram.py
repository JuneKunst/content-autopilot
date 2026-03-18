"""Tests for Telegram publisher."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx

from content_autopilot.publishers.telegram import TelegramPublisher
from content_autopilot.schemas.ai import ArticleDraft
from content_autopilot.schemas.publishing import PublishResult


@pytest.fixture
def article_draft():
    """Create a sample ArticleDraft for testing."""
    return ArticleDraft(
        title_ko="Pydantic v2 소개",
        content_ko="Pydantic v2는 주요 개선사항을 제공합니다. " * 50,
        summary_ko="Pydantic v2의 새로운 기능들을 소개합니다.",
        source_attribution="https://example.com/pydantic-v2",
        tags=["python", "pydantic", "개발", "웹", "프레임워크"],
    )


@pytest.fixture
def telegram_publisher():
    """Create a TelegramPublisher instance with test credentials."""
    return TelegramPublisher(
        bot_token="test_token_123",
        channel_id="@test_channel",
    )


class TestTelegramPublisherFormatMessage:
    """Test message formatting."""

    def test_format_message_with_all_fields(self, telegram_publisher, article_draft):
        """Test formatting with all fields present."""
        message = telegram_publisher._format_message(
            article_draft,
            ghost_url="https://ghost.example.com/article",
        )

        # Check title is in bold
        assert "<b>Pydantic v2 소개</b>" in message

        # Check summary is included (first 200 chars)
        assert "Pydantic v2의 새로운 기능들을 소개합니다." in message

        # Check ghost URL is included
        assert '🔗 <a href="https://ghost.example.com/article">전체 읽기</a>' in message

        # Check source attribution
        assert '📌 출처: <a href="https://example.com/pydantic-v2">https://example.com/pydantic-v2</a>' in message

        # Check hashtags (first 5 tags)
        assert "#python" in message
        assert "#pydantic" in message
        assert "#개발" in message
        assert "#웹" in message
        assert "#프레임워크" in message

    def test_format_message_without_ghost_url(self, telegram_publisher, article_draft):
        """Test formatting without ghost URL."""
        message = telegram_publisher._format_message(article_draft, ghost_url=None)

        # Ghost URL should not be present
        assert "전체 읽기" not in message

        # But source attribution should still be there
        assert "출처:" in message

    def test_format_message_without_tags(self, telegram_publisher):
        """Test formatting without tags."""
        draft = ArticleDraft(
            title_ko="Test Title",
            content_ko="Test content",
            summary_ko="Test summary",
            source_attribution="https://example.com",
            tags=[],
        )
        message = telegram_publisher._format_message(draft)

        # Should not have hashtags
        assert "#" not in message

    def test_format_message_summary_truncation(self, telegram_publisher):
        """Test that summary is truncated to 200 chars."""
        long_summary = "A" * 100 + "B" * 100 + "C" * 100
        draft = ArticleDraft(
            title_ko="Test",
            content_ko="Content",
            summary_ko=long_summary,
            source_attribution="https://example.com",
        )
        message = telegram_publisher._format_message(draft)

        # Summary should be truncated to 200 chars
        assert long_summary[:200] in message
        # The C's (chars 200+) should not be in the message
        assert "C" not in message

    def test_format_message_content_fallback(self, telegram_publisher):
        """Test that content is used when summary is empty."""
        draft = ArticleDraft(
            title_ko="Test",
            content_ko="This is the content",
            summary_ko="",
            source_attribution="https://example.com",
        )
        message = telegram_publisher._format_message(draft)

        # Content should be used
        assert "This is the content" in message

    def test_format_message_tag_space_replacement(self, telegram_publisher):
        """Test that spaces in tags are replaced with underscores."""
        draft = ArticleDraft(
            title_ko="Test",
            content_ko="Content",
            summary_ko="Summary",
            source_attribution="https://example.com",
            tags=["machine learning", "deep learning"],
        )
        message = telegram_publisher._format_message(draft)

        # Spaces should be replaced with underscores
        assert "#machine_learning" in message
        assert "#deep_learning" in message


class TestTelegramPublisherPublish:
    """Test publish method."""

    @pytest.mark.asyncio
    async def test_publish_success(self, telegram_publisher, article_draft):
        """Test successful publish."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "ok": True,
            "result": {"message_id": 12345},
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with patch("content_autopilot.publishers.telegram.create_client", return_value=mock_client):
            result = await telegram_publisher.publish(
                article_draft,
                ghost_url="https://ghost.example.com/article",
            )

        assert result.channel == "telegram"
        assert result.status == "success"
        assert result.external_url == "12345"
        assert result.error is None

        # Verify the API call was made correctly
        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        assert "https://api.telegram.org/bot" in call_args[0][0]
        assert call_args[1]["json"]["chat_id"] == "@test_channel"
        assert call_args[1]["json"]["parse_mode"] == "HTML"

    @pytest.mark.asyncio
    async def test_publish_no_credentials(self, article_draft):
        """Test publish with no credentials."""
        publisher = TelegramPublisher(bot_token="", channel_id="")
        result = await publisher.publish(article_draft)

        assert result.channel == "telegram"
        assert result.status == "skipped"
        assert result.error == "No credentials"

    @pytest.mark.asyncio
    async def test_publish_http_error(self, telegram_publisher, article_draft):
        """Test publish with HTTP error."""
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Unauthorized",
            request=MagicMock(),
            response=mock_response,
        )

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with patch("content_autopilot.publishers.telegram.create_client", return_value=mock_client):
            result = await telegram_publisher.publish(article_draft)

        assert result.channel == "telegram"
        assert result.status == "failed"
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_publish_generic_exception(self, telegram_publisher, article_draft):
        """Test publish with generic exception."""
        mock_client = AsyncMock()
        mock_client.post.side_effect = Exception("Network error")
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with patch("content_autopilot.publishers.telegram.create_client", return_value=mock_client):
            result = await telegram_publisher.publish(article_draft)

        assert result.channel == "telegram"
        assert result.status == "failed"
        assert "Network error" in result.error

    @pytest.mark.asyncio
    async def test_publish_without_ghost_url(self, telegram_publisher, article_draft):
        """Test publish without ghost URL."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "ok": True,
            "result": {"message_id": 67890},
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with patch("content_autopilot.publishers.telegram.create_client", return_value=mock_client):
            result = await telegram_publisher.publish(article_draft, ghost_url=None)

        assert result.status == "success"
        assert result.external_url == "67890"

        # Verify the message doesn't contain ghost URL
        call_args = mock_client.post.call_args
        message = call_args[1]["json"]["text"]
        assert "전체 읽기" not in message
