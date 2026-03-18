"""Tests for HN (Hacker News) collector."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx

from content_autopilot.collectors.hn import HNCollector
from content_autopilot.schemas import RawItem


# --- Fixtures ---

def make_story(id: int, score: int = 100, type: str = "story", url: str = "https://example.com") -> dict:
    return {
        "id": id,
        "type": type,
        "title": f"Test Story {id}",
        "url": url,
        "score": score,
        "descendants": 42,
        "by": "testuser",
        "time": 1700000000,
        "text": None,
    }


# --- collect() tests ---

@pytest.mark.asyncio
async def test_collect_returns_raw_items():
    """collect() with mocked HTTP returns list of RawItem."""
    story_ids = [1001, 1002, 1003]
    stories = {
        1001: make_story(1001, score=50),
        1002: make_story(1002, score=20),
        1003: make_story(1003, score=5),  # below min_score=10, filtered out
    }

    async def mock_get(url, **kwargs):
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = 200
        resp.raise_for_status = MagicMock()
        if "topstories" in url:
            resp.json.return_value = story_ids
        else:
            # extract id from url like .../item/1001.json
            item_id = int(url.split("/item/")[1].replace(".json", ""))
            resp.json.return_value = stories[item_id]
        return resp

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get = mock_get
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("content_autopilot.collectors.hn.create_client", return_value=mock_client):
        collector = HNCollector(min_score=10, fetch_count=30)
        results = await collector.collect(limit=30)

    assert isinstance(results, list)
    assert len(results) == 2  # 1003 filtered (score=5 < min_score=10)
    assert all(isinstance(r, RawItem) for r in results)
    assert all(r.source == "hn" for r in results)


@pytest.mark.asyncio
async def test_collect_sets_correct_fields():
    """collect() maps HN fields to RawItem correctly."""
    story_ids = [2001]
    story = {
        "id": 2001,
        "type": "story",
        "title": "Amazing Python Article",
        "url": "https://python.org/article",
        "score": 200,
        "descendants": 88,
        "by": "pythonista",
        "time": 1700001234,
        "text": None,
    }

    async def mock_get(url, **kwargs):
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = 200
        resp.raise_for_status = MagicMock()
        if "topstories" in url:
            resp.json.return_value = story_ids
        else:
            resp.json.return_value = story
        return resp

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get = mock_get
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("content_autopilot.collectors.hn.create_client", return_value=mock_client):
        collector = HNCollector(min_score=10)
        results = await collector.collect(limit=10)

    assert len(results) == 1
    item = results[0]
    assert item.title == "Amazing Python Article"
    assert item.url == "https://python.org/article"
    assert item.engagement["upvotes"] == 200
    assert item.engagement["comments"] == 88
    assert item.external_id == "hn_2001"
    assert item.metadata["hn_id"] == 2001
    assert item.metadata["author"] == "pythonista"
    assert item.source_lang == "en"


@pytest.mark.asyncio
async def test_collect_uses_hn_url_fallback_for_ask_hn():
    """Ask HN posts without url field get HN URL fallback."""
    story_ids = [3001]
    story = {
        "id": 3001,
        "type": "story",
        "title": "Ask HN: What is your favorite tool?",
        # no "url" field
        "score": 50,
        "descendants": 10,
        "by": "asker",
        "time": 1700002000,
        "text": "I am curious about tools",
    }

    async def mock_get(url, **kwargs):
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = 200
        resp.raise_for_status = MagicMock()
        if "topstories" in url:
            resp.json.return_value = story_ids
        else:
            resp.json.return_value = story
        return resp

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get = mock_get
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("content_autopilot.collectors.hn.create_client", return_value=mock_client):
        collector = HNCollector(min_score=10)
        results = await collector.collect(limit=10)

    assert len(results) == 1
    assert results[0].url == "https://news.ycombinator.com/item?id=3001"
    assert results[0].content_preview == "I am curious about tools"


# --- _is_valid() tests ---

def test_is_valid_returns_false_below_min_score():
    collector = HNCollector(min_score=10)
    item = make_story(id=100, score=5)
    assert collector._is_valid(item) is False


def test_is_valid_returns_false_for_non_story_type():
    collector = HNCollector(min_score=10)
    comment = {"id": 200, "type": "comment", "score": 100}
    assert collector._is_valid(comment) is False

    job = {"id": 201, "type": "job", "score": 100}
    assert collector._is_valid(job) is False

    poll = {"id": 202, "type": "poll", "score": 100}
    assert collector._is_valid(poll) is False


def test_is_valid_returns_true_for_valid_story():
    collector = HNCollector(min_score=10)
    item = make_story(id=300, score=50)
    assert collector._is_valid(item) is True


def test_is_valid_returns_false_for_empty_item():
    collector = HNCollector(min_score=10)
    assert collector._is_valid({}) is False
    assert collector._is_valid(None) is False  # type: ignore


def test_is_valid_returns_false_at_exact_min_score():
    """Score exactly at min_score should be valid (>= check)."""
    collector = HNCollector(min_score=10)
    item = make_story(id=400, score=10)
    assert collector._is_valid(item) is True


def test_is_valid_returns_false_one_below_min_score():
    collector = HNCollector(min_score=10)
    item = make_story(id=401, score=9)
    assert collector._is_valid(item) is False


# --- Deduplication tests ---

def test_dedup_seen_ids_prevents_duplicate():
    """_to_raw_item adds id to _seen_ids; _is_valid rejects already-seen ids."""
    collector = HNCollector(min_score=10)
    item = make_story(id=500, score=100)

    # First call: valid and converts
    assert collector._is_valid(item) is True
    raw = collector._to_raw_item(item)
    assert raw.external_id == "hn_500"

    # Second call: id is now in _seen_ids → invalid
    assert collector._is_valid(item) is False


def test_dedup_different_ids_both_valid():
    """Two different story IDs are both valid."""
    collector = HNCollector(min_score=10)
    item_a = make_story(id=601, score=100)
    item_b = make_story(id=602, score=100)

    collector._to_raw_item(item_a)
    assert collector._is_valid(item_b) is True


# --- _to_raw_item() tests ---

def test_to_raw_item_truncates_text_preview():
    """content_preview is truncated to 500 chars."""
    collector = HNCollector()
    long_text = "x" * 1000
    item = {
        "id": 700,
        "type": "story",
        "title": "Long text story",
        "score": 50,
        "descendants": 5,
        "by": "author",
        "time": 1700003000,
        "text": long_text,
    }
    raw = collector._to_raw_item(item)
    assert len(raw.content_preview) == 500


def test_to_raw_item_empty_text_gives_empty_preview():
    """No text field → empty content_preview."""
    collector = HNCollector()
    item = make_story(id=800, score=50)
    raw = collector._to_raw_item(item)
    assert raw.content_preview == ""
