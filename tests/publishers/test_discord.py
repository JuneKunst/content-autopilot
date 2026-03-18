"""Tests for Discord Webhook publisher."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx

from content_autopilot.publishers.discord import DiscordPublisher, EMBED_COLOR_BLUE
from content_autopilot.schemas import ArticleDraft, PublishResult


# --- Fixtures ---

def make_draft(
    title_ko: str = "테스트 제목",
    content_ko: str = "테스트 콘텐츠",
    summary_ko: str = "테스트 요약",
    source_attribution: str = "https://example.com",
    tags: list[str] | None = None,
) -> ArticleDraft:
    """Create a test ArticleDraft."""
    return ArticleDraft(
        title_ko=title_ko,
        content_ko=content_ko,
        summary_ko=summary_ko,
        source_attribution=source_attribution,
        tags=tags or [],
    )


def make_mock_client(status_code: int = 204, raise_error: bool = False):
    """Create a mock httpx.AsyncClient that returns configured responses."""
    async def mock_post(url, **kwargs):
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = status_code
        
        if raise_error:
            resp.raise_for_status = MagicMock(
                side_effect=httpx.HTTPStatusError(
                    f"HTTP {status_code}",
                    request=MagicMock(),
                    response=resp,
                )
            )
        else:
            resp.raise_for_status = MagicMock()
        
        return resp

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post = AsyncMock(side_effect=mock_post)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


# --- _build_embed() tests ---

def test_build_embed_basic():
    """_build_embed() creates embed with title and description."""
    publisher = DiscordPublisher(webhook_url="https://discord.com/api/webhooks/123/abc")
    draft = make_draft(
        title_ko="Python 튜토리얼",
        summary_ko="Python 기초 학습",
    )
    
    embed = publisher._build_embed(draft)
    
    assert embed["title"] == "Python 튜토리얼"
    assert embed["description"] == "Python 기초 학습"
    assert embed["color"] == EMBED_COLOR_BLUE
    assert embed["url"] == "https://example.com"


def test_build_embed_title_truncated_at_256():
    """_build_embed() truncates title to 256 characters."""
    publisher = DiscordPublisher(webhook_url="https://discord.com/api/webhooks/123/abc")
    long_title = "A" * 300
    draft = make_draft(title_ko=long_title)
    
    embed = publisher._build_embed(draft)
    
    assert len(embed["title"]) == 256
    assert embed["title"] == "A" * 256


def test_build_embed_description_uses_summary():
    """_build_embed() uses summary_ko for description."""
    publisher = DiscordPublisher(webhook_url="https://discord.com/api/webhooks/123/abc")
    draft = make_draft(
        summary_ko="요약 텍스트",
        content_ko="긴 콘텐츠 텍스트",
    )
    
    embed = publisher._build_embed(draft)
    
    assert embed["description"] == "요약 텍스트"


def test_build_embed_description_falls_back_to_content():
    """_build_embed() falls back to content_ko when summary_ko is empty."""
    publisher = DiscordPublisher(webhook_url="https://discord.com/api/webhooks/123/abc")
    draft = make_draft(
        summary_ko="",
        content_ko="콘텐츠 텍스트",
    )
    
    embed = publisher._build_embed(draft)
    
    assert embed["description"] == "콘텐츠 텍스트"


def test_build_embed_description_truncated_at_4096():
    """_build_embed() truncates description to 4096 characters."""
    publisher = DiscordPublisher(webhook_url="https://discord.com/api/webhooks/123/abc")
    long_summary = "B" * 5000
    draft = make_draft(summary_ko=long_summary)
    
    embed = publisher._build_embed(draft)
    
    assert len(embed["description"]) == 4096
    assert embed["description"] == "B" * 4096


def test_build_embed_includes_tags():
    """_build_embed() includes tags in fields."""
    publisher = DiscordPublisher(webhook_url="https://discord.com/api/webhooks/123/abc")
    draft = make_draft(tags=["python", "tutorial", "beginner"])
    
    embed = publisher._build_embed(draft)
    
    assert len(embed["fields"]) == 1
    assert embed["fields"][0]["name"] == "태그"
    assert "`python`" in embed["fields"][0]["value"]
    assert "`tutorial`" in embed["fields"][0]["value"]
    assert "`beginner`" in embed["fields"][0]["value"]
    assert embed["fields"][0]["inline"] is True


def test_build_embed_tags_limited_to_5():
    """_build_embed() limits tags to first 5."""
    publisher = DiscordPublisher(webhook_url="https://discord.com/api/webhooks/123/abc")
    draft = make_draft(tags=["a", "b", "c", "d", "e", "f", "g"])
    
    embed = publisher._build_embed(draft)
    
    tag_value = embed["fields"][0]["value"]
    assert "`a`" in tag_value
    assert "`e`" in tag_value
    assert "`f`" not in tag_value


def test_build_embed_no_tags_no_field():
    """_build_embed() omits tags field when tags list is empty."""
    publisher = DiscordPublisher(webhook_url="https://discord.com/api/webhooks/123/abc")
    draft = make_draft(tags=[])
    
    embed = publisher._build_embed(draft)
    
    assert len(embed["fields"]) == 0


def test_build_embed_includes_ghost_url():
    """_build_embed() includes ghost_url in fields and url."""
    publisher = DiscordPublisher(webhook_url="https://discord.com/api/webhooks/123/abc")
    draft = make_draft()
    ghost_url = "https://blog.example.com/article-slug"
    
    embed = publisher._build_embed(draft, ghost_url=ghost_url)
    
    assert embed["url"] == ghost_url
    assert any(f["name"] == "블로그" for f in embed["fields"])
    blog_field = next(f for f in embed["fields"] if f["name"] == "블로그")
    assert "[전체 읽기]" in blog_field["value"]
    assert ghost_url in blog_field["value"]


def test_build_embed_footer_has_source():
    """_build_embed() includes source_attribution in footer."""
    publisher = DiscordPublisher(webhook_url="https://discord.com/api/webhooks/123/abc")
    draft = make_draft(source_attribution="https://source.example.com/article")
    
    embed = publisher._build_embed(draft)
    
    assert "출처:" in embed["footer"]["text"]
    assert "https://source.example.com/article" in embed["footer"]["text"]


def test_build_embed_footer_truncated_at_100():
    """_build_embed() truncates source_attribution to 100 chars in footer."""
    publisher = DiscordPublisher(webhook_url="https://discord.com/api/webhooks/123/abc")
    long_source = "https://example.com/" + "a" * 100
    draft = make_draft(source_attribution=long_source)
    
    embed = publisher._build_embed(draft)
    
    footer_text = embed["footer"]["text"]
    assert len(footer_text) <= 110  # "출처: " + 100 chars


# --- publish() tests ---

@pytest.mark.asyncio
async def test_publish_success():
    """publish() returns success when webhook returns 204."""
    publisher = DiscordPublisher(webhook_url="https://discord.com/api/webhooks/123/abc")
    draft = make_draft()
    
    with patch("content_autopilot.publishers.discord.create_client") as mock_create:
        mock_client = make_mock_client(status_code=204)
        mock_create.return_value = mock_client
        
        result = await publisher.publish(draft)
    
    assert result.channel == "discord"
    assert result.status == "success"
    assert result.external_url == "https://discord.com/api/webhooks/123/abc"
    assert result.error is None


@pytest.mark.asyncio
async def test_publish_skipped_when_no_webhook():
    """publish() returns skipped when webhook_url is not set."""
    publisher = DiscordPublisher(webhook_url="")
    draft = make_draft()
    
    result = await publisher.publish(draft)
    
    assert result.channel == "discord"
    assert result.status == "skipped"
    assert result.error == "No webhook URL"


@pytest.mark.asyncio
async def test_publish_skipped_when_webhook_none():
    """publish() returns skipped when webhook_url is None."""
    publisher = DiscordPublisher(webhook_url=None)
    draft = make_draft()
    
    result = await publisher.publish(draft)
    
    assert result.channel == "discord"
    assert result.status == "skipped"


@pytest.mark.asyncio
async def test_publish_failed_on_http_error():
    """publish() returns failed when webhook returns HTTP error."""
    publisher = DiscordPublisher(webhook_url="https://discord.com/api/webhooks/123/abc")
    draft = make_draft()
    
    with patch("content_autopilot.publishers.discord.create_client") as mock_create:
        mock_client = make_mock_client(status_code=400, raise_error=True)
        mock_create.return_value = mock_client
        
        result = await publisher.publish(draft)
    
    assert result.channel == "discord"
    assert result.status == "failed"
    assert result.error is not None


@pytest.mark.asyncio
async def test_publish_failed_on_exception():
    """publish() returns failed when exception occurs."""
    publisher = DiscordPublisher(webhook_url="https://discord.com/api/webhooks/123/abc")
    draft = make_draft()
    
    with patch("content_autopilot.publishers.discord.create_client") as mock_create:
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=Exception("Network error"))
        mock_create.return_value = mock_client
        
        result = await publisher.publish(draft)
    
    assert result.channel == "discord"
    assert result.status == "failed"
    assert "Network error" in result.error


@pytest.mark.asyncio
async def test_publish_sends_correct_payload():
    """publish() sends payload with embeds and username."""
    publisher = DiscordPublisher(webhook_url="https://discord.com/api/webhooks/123/abc")
    draft = make_draft(title_ko="테스트", tags=["tag1"])
    
    with patch("content_autopilot.publishers.discord.create_client") as mock_create:
        mock_client = make_mock_client(status_code=204)
        mock_create.return_value = mock_client
        
        await publisher.publish(draft)
    
    # Verify post was called with correct structure
    call_args = mock_client.post.call_args
    assert call_args is not None
    assert "json" in call_args.kwargs
    payload = call_args.kwargs["json"]
    assert "embeds" in payload
    assert len(payload["embeds"]) == 1
    assert payload["username"] == "Content Autopilot"
    assert payload["embeds"][0]["title"] == "테스트"


@pytest.mark.asyncio
async def test_publish_with_ghost_url():
    """publish() includes ghost_url in embed when provided."""
    publisher = DiscordPublisher(webhook_url="https://discord.com/api/webhooks/123/abc")
    draft = make_draft()
    ghost_url = "https://blog.example.com/article"
    
    with patch("content_autopilot.publishers.discord.create_client") as mock_create:
        mock_client = make_mock_client(status_code=204)
        mock_create.return_value = mock_client
        
        result = await publisher.publish(draft, ghost_url=ghost_url)
    
    assert result.status == "success"
    call_args = mock_client.post.call_args
    embed = call_args.kwargs["json"]["embeds"][0]
    assert embed["url"] == ghost_url
