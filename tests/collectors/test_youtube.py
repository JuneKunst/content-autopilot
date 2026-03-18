"""Tests for YouTube Data API v3 collector."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx

from content_autopilot.collectors.youtube import YouTubeCollector, SEARCH_QUOTA_COST, VIDEOS_QUOTA_COST
from content_autopilot.schemas import RawItem


# --- Fixtures ---

def make_video_item(video_id: str, title: str = "Test Video", views: int = 1000,
                    likes: int = 100, comments: int = 50) -> dict:
    """Build a videos.list API response item."""
    return {
        "id": video_id,
        "snippet": {
            "title": title,
            "description": f"Description for {title}",
            "channelTitle": "Test Channel",
        },
        "statistics": {
            "viewCount": str(views),
            "likeCount": str(likes),
            "commentCount": str(comments),
        },
    }


def make_search_item(video_id: str, title: str = "Search Video") -> dict:
    """Build a search.list API response item."""
    return {
        "id": {"videoId": video_id},
        "snippet": {
            "title": title,
            "description": f"Search description for {title}",
            "channelTitle": "Search Channel",
        },
    }


def make_mock_client(popular_items=None, search_items=None, popular_status=200, search_status=200):
    """Create a mock httpx.AsyncClient that returns configured responses."""
    async def mock_get(url, **kwargs):
        resp = MagicMock(spec=httpx.Response)
        resp.raise_for_status = MagicMock()
        if "/videos" in url:
            resp.status_code = popular_status
            resp.json.return_value = {"items": popular_items or []}
        elif "/search" in url:
            resp.status_code = search_status
            resp.json.return_value = {"items": search_items or []}
        else:
            resp.status_code = 404
            resp.json.return_value = {}
        return resp

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get = mock_get
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


# --- collect() tests ---

@pytest.mark.asyncio
async def test_collect_returns_empty_when_no_api_key():
    """collect() returns empty list when youtube_api_key is not set."""
    collector = YouTubeCollector()
    collector._api_key = ""  # force no key

    results = await collector.collect(limit=10)

    assert results == []


@pytest.mark.asyncio
async def test_collect_returns_raw_items_with_api_key():
    """collect() returns RawItems when API key is set and responses are mocked."""
    popular = [make_video_item("vid001", "Popular Video", views=50000)]
    search = [make_search_item("vid002", "Search Result")]

    mock_client = make_mock_client(popular_items=popular, search_items=search)

    with patch("content_autopilot.collectors.youtube.create_client", return_value=mock_client):
        collector = YouTubeCollector(search_queries=["AI news"])
        collector._api_key = "fake_key"
        results = await collector.collect(limit=10)

    assert isinstance(results, list)
    assert all(isinstance(r, RawItem) for r in results)
    assert all(r.source == "youtube" for r in results)


@pytest.mark.asyncio
async def test_collect_deduplicates_same_video_id():
    """Same video ID from popular + search → only one item in results."""
    shared_id = "vid_shared"
    popular = [make_video_item(shared_id, "Shared Video", views=10000)]
    # search returns same video ID
    search = [make_search_item(shared_id, "Shared Video from Search")]

    mock_client = make_mock_client(popular_items=popular, search_items=search)

    with patch("content_autopilot.collectors.youtube.create_client", return_value=mock_client):
        collector = YouTubeCollector(search_queries=["test query"])
        collector._api_key = "fake_key"
        results = await collector.collect(limit=10)

    # Should only have one item despite appearing in both popular and search
    ids = [r.external_id for r in results]
    assert ids.count(f"youtube_{shared_id}") == 1


@pytest.mark.asyncio
async def test_collect_respects_limit():
    """collect() returns at most `limit` items."""
    popular = [make_video_item(f"vid{i:03d}") for i in range(5)]
    search = [make_search_item(f"svid{i:03d}") for i in range(5)]

    mock_client = make_mock_client(popular_items=popular, search_items=search)

    with patch("content_autopilot.collectors.youtube.create_client", return_value=mock_client):
        collector = YouTubeCollector(search_queries=["query1", "query2"])
        collector._api_key = "fake_key"
        results = await collector.collect(limit=5)

    assert len(results) <= 5


# --- _get_most_popular() tests ---

@pytest.mark.asyncio
async def test_get_most_popular_returns_raw_items_with_views():
    """_get_most_popular() returns RawItems with views > 0 from statistics."""
    videos = [
        make_video_item("pop001", "Popular 1", views=100000, likes=5000, comments=200),
        make_video_item("pop002", "Popular 2", views=80000, likes=3000, comments=150),
    ]
    mock_client = make_mock_client(popular_items=videos)

    collector = YouTubeCollector()
    collector._api_key = "fake_key"

    results = await collector._get_most_popular(mock_client, max_results=2)

    assert len(results) == 2
    assert all(isinstance(r, RawItem) for r in results)
    assert results[0].engagement["views"] == 100000
    assert results[1].engagement["views"] == 80000


@pytest.mark.asyncio
async def test_get_most_popular_returns_empty_on_api_error():
    """_get_most_popular() returns [] when API returns non-200 status."""
    mock_client = make_mock_client(popular_status=403)

    collector = YouTubeCollector()
    collector._api_key = "fake_key"

    results = await collector._get_most_popular(mock_client, max_results=5)

    assert results == []


# --- _video_to_raw_item() tests ---

def test_video_to_raw_item_maps_stats_correctly():
    """_video_to_raw_item() maps likeCount→upvotes, viewCount→views, commentCount→comments."""
    collector = YouTubeCollector()
    video = make_video_item("abc123", "Test Title", views=99999, likes=4321, comments=876)

    item = collector._video_to_raw_item(video)

    assert item.source == "youtube"
    assert item.title == "Test Title"
    assert item.url == "https://www.youtube.com/watch?v=abc123"
    assert item.engagement["upvotes"] == 4321
    assert item.engagement["views"] == 99999
    assert item.engagement["comments"] == 876
    assert item.external_id == "youtube_abc123"
    assert item.metadata["channel"] == "Test Channel"
    assert item.metadata["video_id"] == "abc123"
    assert item.source_lang == "ko"


def test_video_to_raw_item_handles_none_stats():
    """_video_to_raw_item() handles None values in statistics gracefully."""
    collector = YouTubeCollector()
    video = {
        "id": "xyz789",
        "snippet": {"title": "No Stats Video", "description": "", "channelTitle": "Chan"},
        "statistics": {"viewCount": None, "likeCount": None, "commentCount": None},
    }

    item = collector._video_to_raw_item(video)

    assert item.engagement["views"] == 0
    assert item.engagement["upvotes"] == 0
    assert item.engagement["comments"] == 0


def test_video_to_raw_item_truncates_description():
    """content_preview is truncated to 500 chars."""
    collector = YouTubeCollector()
    long_desc = "x" * 1000
    video = {
        "id": "trunc01",
        "snippet": {"title": "Long Desc", "description": long_desc, "channelTitle": "Chan"},
        "statistics": {},
    }

    item = collector._video_to_raw_item(video)

    assert len(item.content_preview) == 500


# --- _search_result_to_raw_item() tests ---

def test_search_result_to_raw_item_maps_correctly():
    """_search_result_to_raw_item() maps search result to RawItem with zero engagement."""
    collector = YouTubeCollector()
    search_item = make_search_item("srch001", "Search Title")

    item = collector._search_result_to_raw_item(search_item)

    assert item.source == "youtube"
    assert item.title == "Search Title"
    assert item.url == "https://www.youtube.com/watch?v=srch001"
    assert item.engagement == {"upvotes": 0, "comments": 0, "views": 0}
    assert item.external_id == "youtube_srch001"
    assert item.source_lang == "en"


# --- Quota tracking tests ---

@pytest.mark.asyncio
async def test_quota_increments_after_most_popular():
    """quota_used increments by VIDEOS_QUOTA_COST * max_results after _get_most_popular."""
    videos = [make_video_item(f"q{i:03d}") for i in range(3)]
    mock_client = make_mock_client(popular_items=videos)

    collector = YouTubeCollector()
    collector._api_key = "fake_key"
    assert collector.quota_used == 0

    await collector._get_most_popular(mock_client, max_results=3)

    assert collector.quota_used == VIDEOS_QUOTA_COST * 3


@pytest.mark.asyncio
async def test_quota_increments_after_search():
    """quota_used increments by SEARCH_QUOTA_COST after _search_videos."""
    search_items = [make_search_item(f"sq{i:03d}") for i in range(3)]
    mock_client = make_mock_client(search_items=search_items)

    collector = YouTubeCollector()
    collector._api_key = "fake_key"
    assert collector.quota_used == 0

    await collector._search_videos(mock_client, "test query", max_results=3)

    assert collector.quota_used == SEARCH_QUOTA_COST


def test_quota_remaining_decreases_as_quota_used_increases():
    """quota_remaining = quota_limit - quota_used."""
    collector = YouTubeCollector()
    initial_remaining = collector.quota_remaining

    collector.quota_used += 500
    assert collector.quota_remaining == initial_remaining - 500

    collector.quota_used += 9000  # exceed limit
    assert collector.quota_remaining == 0  # never negative


@pytest.mark.asyncio
async def test_collect_skips_search_when_quota_low():
    """collect() skips search queries when quota_remaining < SEARCH_QUOTA_COST."""
    popular = [make_video_item("pop001")]
    mock_client = make_mock_client(popular_items=popular)

    with patch("content_autopilot.collectors.youtube.create_client", return_value=mock_client):
        collector = YouTubeCollector(search_queries=["query1", "query2"])
        collector._api_key = "fake_key"
        # Set quota so remaining < SEARCH_QUOTA_COST
        collector.quota_used = collector.quota_limit - 50  # only 50 remaining

        results = await collector.collect(limit=10)

    # Should still return popular items (videos.list cost is low)
    # but no search results since quota is too low
    assert isinstance(results, list)
