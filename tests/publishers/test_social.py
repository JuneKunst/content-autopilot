"""Tests for Mastodon and Bluesky social publishers."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx

from content_autopilot.publishers.social import MastodonPublisher, BlueskyPublisher
from content_autopilot.schemas import ArticleDraft, PublishResult


# --- Fixtures ---

def make_draft(
    title_ko: str = "테스트 제목",
    content_ko: str = "테스트 콘텐츠",
    summary_ko: str = "테스트 요약입니다",
    source_attribution: str = "https://example.com/article",
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


def make_mock_client(
    status_code: int = 200,
    json_data: dict | None = None,
    raise_error: bool = False,
    auth_json: dict | None = None,
):
    """Create a mock httpx.AsyncClient with configurable responses."""
    call_count = 0

    async def mock_post(url, **kwargs):
        nonlocal call_count
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = status_code

        # For Bluesky: first call is auth, second is createRecord
        if auth_json is not None and call_count == 0:
            resp.status_code = 200
            resp.json = MagicMock(return_value=auth_json)
            resp.raise_for_status = MagicMock()
        else:
            resp.json = MagicMock(return_value=json_data or {})
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

        call_count += 1
        return resp

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post = AsyncMock(side_effect=mock_post)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


# --- MastodonPublisher._format_status() tests ---

def test_mastodon_format_status_within_limit():
    """_format_status() produces text ≤ 500 chars."""
    publisher = MastodonPublisher(access_token="tok", instance="https://mastodon.social")
    draft = make_draft(
        title_ko="A" * 100,
        summary_ko="B" * 300,
        source_attribution="https://example.com/very-long-article-url",
    )
    text = publisher._format_status(draft)
    assert len(text) <= 500


def test_mastodon_format_status_includes_title():
    """_format_status() includes title_ko."""
    publisher = MastodonPublisher(access_token="tok", instance="https://mastodon.social")
    draft = make_draft(title_ko="파이썬 튜토리얼")
    text = publisher._format_status(draft)
    assert "파이썬 튜토리얼" in text


def test_mastodon_format_status_includes_source_url():
    """_format_status() includes source URL."""
    publisher = MastodonPublisher(access_token="tok", instance="https://mastodon.social")
    draft = make_draft(source_attribution="https://example.com/article")
    text = publisher._format_status(draft)
    assert "https://example.com/article" in text


def test_mastodon_format_status_uses_ghost_url_when_provided():
    """_format_status() uses ghost_url over source_attribution."""
    publisher = MastodonPublisher(access_token="tok", instance="https://mastodon.social")
    draft = make_draft(source_attribution="https://source.com")
    text = publisher._format_status(draft, ghost_url="https://blog.example.com/post")
    assert "https://blog.example.com/post" in text
    assert "https://source.com" not in text


def test_mastodon_format_status_includes_hashtags():
    """_format_status() includes hashtags from tags."""
    publisher = MastodonPublisher(access_token="tok", instance="https://mastodon.social")
    draft = make_draft(tags=["python", "tutorial"])
    text = publisher._format_status(draft)
    assert "#python" in text
    assert "#tutorial" in text


def test_mastodon_format_status_limits_hashtags_to_3():
    """_format_status() limits hashtags to first 3 tags."""
    publisher = MastodonPublisher(access_token="tok", instance="https://mastodon.social")
    draft = make_draft(tags=["a", "b", "c", "d", "e"])
    text = publisher._format_status(draft)
    assert "#a" in text
    assert "#c" in text
    assert "#d" not in text


def test_mastodon_format_status_long_text_truncated():
    """_format_status() truncates to exactly 500 chars."""
    publisher = MastodonPublisher(access_token="tok", instance="https://mastodon.social")
    draft = make_draft(
        title_ko="T" * 200,
        summary_ko="S" * 300,
        source_attribution="https://example.com/" + "x" * 100,
    )
    text = publisher._format_status(draft)
    assert len(text) == 500


# --- MastodonPublisher.publish_text() tests ---

@pytest.mark.asyncio
async def test_mastodon_publish_text_success():
    """publish_text() returns success with external_url."""
    publisher = MastodonPublisher(access_token="test-token", instance="https://mastodon.social")

    with patch("content_autopilot.publishers.social.create_client") as mock_create:
        mock_client = make_mock_client(
            status_code=200,
            json_data={"url": "https://mastodon.social/@user/1234"},
        )
        mock_create.return_value = mock_client

        result = await publisher.publish_text("Hello Mastodon!")

    assert result.channel == "mastodon"
    assert result.status == "success"
    assert result.external_url == "https://mastodon.social/@user/1234"
    assert result.error is None


@pytest.mark.asyncio
async def test_mastodon_publish_text_skipped_no_token():
    """publish_text() returns skipped when no access token."""
    publisher = MastodonPublisher(access_token="", instance="https://mastodon.social")
    result = await publisher.publish_text("Hello!")
    assert result.channel == "mastodon"
    assert result.status == "skipped"
    assert result.error == "No access token"


@pytest.mark.asyncio
async def test_mastodon_publish_text_skipped_none_token():
    """publish_text() returns skipped when access_token is None."""
    publisher = MastodonPublisher(access_token=None, instance="https://mastodon.social")
    # Override _token to ensure it's falsy (settings may have default)
    publisher._token = None
    result = await publisher.publish_text("Hello!")
    assert result.status == "skipped"


@pytest.mark.asyncio
async def test_mastodon_publish_text_failed_on_http_error():
    """publish_text() returns failed on HTTP error."""
    publisher = MastodonPublisher(access_token="test-token", instance="https://mastodon.social")

    with patch("content_autopilot.publishers.social.create_client") as mock_create:
        mock_client = make_mock_client(status_code=422, raise_error=True)
        mock_create.return_value = mock_client

        result = await publisher.publish_text("Hello!")

    assert result.channel == "mastodon"
    assert result.status == "failed"
    assert result.error is not None


@pytest.mark.asyncio
async def test_mastodon_publish_text_failed_on_exception():
    """publish_text() returns failed on generic exception."""
    publisher = MastodonPublisher(access_token="test-token", instance="https://mastodon.social")

    with patch("content_autopilot.publishers.social.create_client") as mock_create:
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=Exception("Network error"))
        mock_create.return_value = mock_client

        result = await publisher.publish_text("Hello!")

    assert result.channel == "mastodon"
    assert result.status == "failed"
    assert "Network error" in result.error


@pytest.mark.asyncio
async def test_mastodon_publish_sends_correct_payload():
    """publish_text() sends correct Authorization header and JSON body."""
    publisher = MastodonPublisher(access_token="my-token", instance="https://mastodon.social")

    with patch("content_autopilot.publishers.social.create_client") as mock_create:
        mock_client = make_mock_client(
            status_code=200,
            json_data={"url": "https://mastodon.social/@user/999"},
        )
        mock_create.return_value = mock_client

        await publisher.publish_text("Test status")

    call_args = mock_client.post.call_args
    assert call_args is not None
    assert "json" in call_args.kwargs
    assert call_args.kwargs["json"]["status"] == "Test status"
    assert call_args.kwargs["json"]["visibility"] == "public"
    assert call_args.kwargs["headers"]["Authorization"] == "Bearer my-token"


@pytest.mark.asyncio
async def test_mastodon_publish_draft():
    """publish() formats draft and posts to Mastodon."""
    publisher = MastodonPublisher(access_token="test-token", instance="https://mastodon.social")
    draft = make_draft(title_ko="테스트 기사", tags=["python"])

    with patch("content_autopilot.publishers.social.create_client") as mock_create:
        mock_client = make_mock_client(
            status_code=200,
            json_data={"url": "https://mastodon.social/@user/5678"},
        )
        mock_create.return_value = mock_client

        result = await publisher.publish(draft)

    assert result.status == "success"
    # Verify the posted text contains the title
    call_args = mock_client.post.call_args
    assert "테스트 기사" in call_args.kwargs["json"]["status"]


# --- BlueskyPublisher._format_post() tests ---

def test_bluesky_format_post_within_limit():
    """_format_post() produces text ≤ 300 chars."""
    publisher = BlueskyPublisher(identifier="user.bsky.social", app_password="pass")
    draft = make_draft(
        title_ko="T" * 100,
        summary_ko="S" * 200,
        source_attribution="https://example.com/" + "x" * 100,
    )
    text = publisher._format_post(draft)
    assert len(text) <= 300


def test_bluesky_format_post_includes_title():
    """_format_post() includes title_ko."""
    publisher = BlueskyPublisher(identifier="user.bsky.social", app_password="pass")
    draft = make_draft(title_ko="블루스카이 테스트")
    text = publisher._format_post(draft)
    assert "블루스카이 테스트" in text


def test_bluesky_format_post_includes_url():
    """_format_post() includes source URL."""
    publisher = BlueskyPublisher(identifier="user.bsky.social", app_password="pass")
    draft = make_draft(source_attribution="https://example.com/article")
    text = publisher._format_post(draft)
    assert "https://example.com/article" in text


def test_bluesky_format_post_uses_ghost_url():
    """_format_post() uses ghost_url when provided."""
    publisher = BlueskyPublisher(identifier="user.bsky.social", app_password="pass")
    draft = make_draft(source_attribution="https://source.com")
    text = publisher._format_post(draft, ghost_url="https://blog.example.com/post")
    assert "https://blog.example.com/post" in text


def test_bluesky_format_post_long_text_truncated():
    """_format_post() truncates to exactly 300 chars."""
    publisher = BlueskyPublisher(identifier="user.bsky.social", app_password="pass")
    draft = make_draft(
        title_ko="T" * 150,
        summary_ko="S" * 200,
        source_attribution="https://example.com/" + "x" * 100,
    )
    text = publisher._format_post(draft)
    assert len(text) == 300


# --- BlueskyPublisher.publish() tests ---

@pytest.mark.asyncio
async def test_bluesky_publish_skipped_no_credentials():
    """publish() returns skipped when no credentials."""
    publisher = BlueskyPublisher(identifier="", app_password="")
    draft = make_draft()
    result = await publisher.publish(draft)
    assert result.channel == "bluesky"
    assert result.status == "skipped"
    assert result.error == "No credentials"


@pytest.mark.asyncio
async def test_bluesky_publish_skipped_none_credentials():
    """publish() returns skipped when credentials are None."""
    publisher = BlueskyPublisher(identifier=None, app_password=None)
    publisher._identifier = None
    publisher._app_password = None
    draft = make_draft()
    result = await publisher.publish(draft)
    assert result.status == "skipped"


@pytest.mark.asyncio
async def test_bluesky_publish_success():
    """publish() authenticates then posts, returns success."""
    publisher = BlueskyPublisher(identifier="user.bsky.social", app_password="app-pass")
    draft = make_draft(title_ko="블루스카이 포스트")

    with patch("content_autopilot.publishers.social.create_client") as mock_create:
        mock_client = make_mock_client(
            status_code=200,
            json_data={"uri": "at://user.bsky.social/app.bsky.feed.post/abc123"},
            auth_json={"accessJwt": "jwt-token-here"},
        )
        mock_create.return_value = mock_client

        result = await publisher.publish(draft)

    assert result.channel == "bluesky"
    assert result.status == "success"
    assert result.external_url == "at://user.bsky.social/app.bsky.feed.post/abc123"


@pytest.mark.asyncio
async def test_bluesky_publish_auth_failed():
    """publish() returns failed when auth returns no token."""
    publisher = BlueskyPublisher(identifier="user.bsky.social", app_password="wrong-pass")
    draft = make_draft()

    with patch("content_autopilot.publishers.social.create_client") as mock_create:
        # Auth returns 401, no accessJwt
        async def mock_post(url, **kwargs):
            resp = MagicMock(spec=httpx.Response)
            resp.status_code = 401
            resp.json = MagicMock(return_value={"error": "Unauthorized"})
            resp.raise_for_status = MagicMock()
            return resp

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post = AsyncMock(side_effect=mock_post)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_create.return_value = mock_client

        result = await publisher.publish(draft)

    assert result.channel == "bluesky"
    assert result.status == "failed"
    assert result.error == "Auth failed"


@pytest.mark.asyncio
async def test_bluesky_publish_failed_on_http_error():
    """publish() returns failed when createRecord returns HTTP error."""
    publisher = BlueskyPublisher(identifier="user.bsky.social", app_password="app-pass")
    draft = make_draft()

    with patch("content_autopilot.publishers.social.create_client") as mock_create:
        call_count = 0

        async def mock_post(url, **kwargs):
            nonlocal call_count
            resp = MagicMock(spec=httpx.Response)
            if call_count == 0:
                # Auth succeeds
                resp.status_code = 200
                resp.json = MagicMock(return_value={"accessJwt": "token"})
                resp.raise_for_status = MagicMock()
            else:
                # createRecord fails
                resp.status_code = 400
                resp.json = MagicMock(return_value={})
                resp.raise_for_status = MagicMock(
                    side_effect=httpx.HTTPStatusError(
                        "HTTP 400",
                        request=MagicMock(),
                        response=resp,
                    )
                )
            call_count += 1
            return resp

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post = AsyncMock(side_effect=mock_post)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_create.return_value = mock_client

        result = await publisher.publish(draft)

    assert result.channel == "bluesky"
    assert result.status == "failed"
    assert result.error is not None


@pytest.mark.asyncio
async def test_bluesky_publish_sends_correct_record():
    """publish() sends correct record structure to Bluesky."""
    publisher = BlueskyPublisher(identifier="user.bsky.social", app_password="app-pass")
    draft = make_draft(title_ko="테스트 포스트")

    with patch("content_autopilot.publishers.social.create_client") as mock_create:
        mock_client = make_mock_client(
            status_code=200,
            json_data={"uri": "at://user.bsky.social/app.bsky.feed.post/xyz"},
            auth_json={"accessJwt": "jwt-token"},
        )
        mock_create.return_value = mock_client

        await publisher.publish(draft)

    # Second call is createRecord
    calls = mock_client.post.call_args_list
    assert len(calls) == 2

    create_record_call = calls[1]
    payload = create_record_call.kwargs["json"]
    assert payload["repo"] == "user.bsky.social"
    assert payload["collection"] == "app.bsky.feed.post"
    assert payload["record"]["$type"] == "app.bsky.feed.post"
    assert "테스트 포스트" in payload["record"]["text"]
    assert "createdAt" in payload["record"]
    assert create_record_call.kwargs["headers"]["Authorization"] == "Bearer jwt-token"
