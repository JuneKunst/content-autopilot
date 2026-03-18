"""Tests for Reddit collector."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx

from content_autopilot.collectors.reddit import RedditCollector
from content_autopilot.schemas import RawItem


def make_post(
    id: str = "abc123",
    title: str = "Test Post",
    url: str = "https://example.com/test",
    score: int = 100,
    num_comments: int = 42,
    over_18: bool = False,
    selftext: str = "",
    author: str = "testuser",
) -> dict:
    """Helper to build a Reddit post dict."""
    return {
        "id": id,
        "title": title,
        "url": url,
        "score": score,
        "num_comments": num_comments,
        "over_18": over_18,
        "selftext": selftext,
        "author": author,
    }


def make_listing(posts: list[dict]) -> dict:
    """Wrap posts in Reddit listing format."""
    return {
        "data": {
            "children": [{"kind": "t3", "data": p} for p in posts]
        }
    }


# ── _is_valid ──────────────────────────────────────────────────────────────────

def test_is_valid_nsfw_filtered():
    collector = RedditCollector()
    post = make_post(over_18=True, score=500)
    assert collector._is_valid(post) is False


def test_is_valid_low_score_filtered():
    collector = RedditCollector()
    post = make_post(score=5)
    assert collector._is_valid(post) is False


def test_is_valid_passes():
    collector = RedditCollector()
    post = make_post(score=50)
    assert collector._is_valid(post) is True


def test_is_valid_score_exactly_10():
    collector = RedditCollector()
    post = make_post(score=10)
    assert collector._is_valid(post) is True


def test_is_valid_score_9_filtered():
    collector = RedditCollector()
    post = make_post(score=9)
    assert collector._is_valid(post) is False


# ── _to_raw_item ───────────────────────────────────────────────────────────────

def test_to_raw_item_engagement():
    collector = RedditCollector()
    post = make_post(score=200, num_comments=55)
    item = collector._to_raw_item(post, "technology")
    assert item.engagement == {"upvotes": 200, "comments": 55}


def test_to_raw_item_source():
    collector = RedditCollector()
    post = make_post()
    item = collector._to_raw_item(post, "programming")
    assert item.source == "reddit"


def test_to_raw_item_external_id():
    collector = RedditCollector()
    post = make_post(id="xyz789")
    item = collector._to_raw_item(post, "technology")
    assert item.external_id == "reddit_xyz789"


def test_to_raw_item_self_post_url():
    """Self posts with /r/ prefix should get full reddit.com URL."""
    collector = RedditCollector()
    post = make_post(url="/r/programming/comments/abc/test")
    item = collector._to_raw_item(post, "programming")
    assert item.url.startswith("https://reddit.com")


def test_to_raw_item_metadata():
    collector = RedditCollector()
    post = make_post(id="post1", author="alice")
    item = collector._to_raw_item(post, "startups")
    assert item.metadata["subreddit"] == "startups"
    assert item.metadata["author"] == "alice"
    assert item.metadata["id"] == "post1"


def test_to_raw_item_content_preview_truncated():
    collector = RedditCollector()
    long_text = "x" * 1000
    post = make_post(selftext=long_text)
    item = collector._to_raw_item(post, "technology")
    assert len(item.content_preview) == 500


# ── collect() with mocked HTTP ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_collect_returns_empty_when_no_creds():
    """Graceful empty return when credentials are missing."""
    with patch("content_autopilot.collectors.reddit.settings") as mock_settings:
        mock_settings.reddit_client_id = ""
        mock_settings.reddit_client_secret = ""
        collector = RedditCollector()
        collector._client_id = ""
        collector._client_secret = ""
        result = await collector.collect()
    assert result == []


@pytest.mark.asyncio
async def test_collect_filters_nsfw():
    """collect() should return only valid (non-NSFW, score>=10) posts."""
    posts = [
        make_post(id="p1", title="Valid Post 1", score=100),
        make_post(id="p2", title="NSFW Post", score=200, over_18=True),
        make_post(id="p3", title="Valid Post 2", score=50),
    ]
    listing = make_listing(posts)

    token_response = MagicMock()
    token_response.status_code = 200
    token_response.json.return_value = {"access_token": "test_token"}

    subreddit_response = MagicMock()
    subreddit_response.status_code = 200
    subreddit_response.json.return_value = listing
    subreddit_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=token_response)
    mock_client.get = AsyncMock(return_value=subreddit_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("content_autopilot.collectors.reddit.settings") as mock_settings, \
         patch("content_autopilot.collectors.reddit.create_client", return_value=mock_client):
        mock_settings.reddit_client_id = "test_id"
        mock_settings.reddit_client_secret = "test_secret"

        collector = RedditCollector(subreddits=["technology"])
        collector._client_id = "test_id"
        collector._client_secret = "test_secret"
        collector._rate_limiter = AsyncMock()
        collector._rate_limiter.acquire = AsyncMock()

        result = await collector.collect(limit=25)

    assert len(result) == 2
    titles = [item.title for item in result]
    assert "Valid Post 1" in titles
    assert "Valid Post 2" in titles
    assert "NSFW Post" not in titles


@pytest.mark.asyncio
async def test_collect_token_failure_returns_empty():
    """If token fetch fails, collect() returns empty list."""
    token_response = MagicMock()
    token_response.status_code = 401
    token_response.json.return_value = {}

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=token_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("content_autopilot.collectors.reddit.settings") as mock_settings, \
         patch("content_autopilot.collectors.reddit.create_client", return_value=mock_client):
        mock_settings.reddit_client_id = "test_id"
        mock_settings.reddit_client_secret = "test_secret"

        collector = RedditCollector(subreddits=["technology"])
        collector._client_id = "test_id"
        collector._client_secret = "test_secret"

        result = await collector.collect()

    assert result == []


@pytest.mark.asyncio
async def test_collect_returns_raw_items():
    """collect() returns list of RawItem instances."""
    posts = [
        make_post(id="p1", title="Post 1", score=100),
        make_post(id="p2", title="Post 2", score=200),
    ]
    listing = make_listing(posts)

    token_response = MagicMock()
    token_response.status_code = 200
    token_response.json.return_value = {"access_token": "test_token"}

    subreddit_response = MagicMock()
    subreddit_response.status_code = 200
    subreddit_response.json.return_value = listing
    subreddit_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=token_response)
    mock_client.get = AsyncMock(return_value=subreddit_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("content_autopilot.collectors.reddit.settings") as mock_settings, \
         patch("content_autopilot.collectors.reddit.create_client", return_value=mock_client):
        mock_settings.reddit_client_id = "test_id"
        mock_settings.reddit_client_secret = "test_secret"

        collector = RedditCollector(subreddits=["technology"])
        collector._client_id = "test_id"
        collector._client_secret = "test_secret"
        collector._rate_limiter = AsyncMock()
        collector._rate_limiter.acquire = AsyncMock()

        result = await collector.collect(limit=25)

    assert all(isinstance(item, RawItem) for item in result)
    assert len(result) == 2
