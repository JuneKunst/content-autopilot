"""Tests for GitHub trending repositories collector."""
import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock, patch
from content_autopilot.collectors.github import GitHubCollector
from content_autopilot.schemas import RawItem


# --- Fixtures ---

def make_repo(
    id: int = 1,
    full_name: str = "owner/repo",
    description: str = "A test repo",
    html_url: str = "https://github.com/owner/repo",
    stargazers_count: int = 100,
    open_issues_count: int = 5,
    language: str = "Python",
    topics: list | None = None,
    forks_count: int = 20,
) -> dict:
    return {
        "id": id,
        "full_name": full_name,
        "description": description,
        "html_url": html_url,
        "stargazers_count": stargazers_count,
        "open_issues_count": open_issues_count,
        "language": language,
        "topics": topics or ["ai", "machine-learning"],
        "forks_count": forks_count,
    }


SAMPLE_REPOS = [
    make_repo(id=1, full_name="org/alpha", description="Alpha project", stargazers_count=500, open_issues_count=10),
    make_repo(id=2, full_name="org/beta", description="Beta project", stargazers_count=300, open_issues_count=3),
    make_repo(id=3, full_name="org/gamma", description="Gamma project", stargazers_count=150, open_issues_count=7),
]

GITHUB_SEARCH_RESPONSE = {
    "total_count": 3,
    "incomplete_results": False,
    "items": SAMPLE_REPOS,
}


# --- Tests ---

@pytest.mark.asyncio
async def test_collect_returns_raw_items():
    """collect() returns a list of RawItem from mocked GitHub API."""
    collector = GitHubCollector(min_stars=50, languages=["python"])

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = GITHUB_SEARCH_RESPONSE

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("content_autopilot.collectors.github.create_client", return_value=mock_client), \
         patch.object(collector._rate_limiter, "acquire", new_callable=AsyncMock):
        items = await collector.collect(limit=10)

    assert len(items) == 3
    assert all(isinstance(item, RawItem) for item in items)
    assert all(item.source == "github" for item in items)


@pytest.mark.asyncio
async def test_collect_respects_limit():
    """collect() respects the limit parameter."""
    collector = GitHubCollector(min_stars=50, languages=["python"])

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = GITHUB_SEARCH_RESPONSE

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("content_autopilot.collectors.github.create_client", return_value=mock_client), \
         patch.object(collector._rate_limiter, "acquire", new_callable=AsyncMock):
        items = await collector.collect(limit=2)

    assert len(items) <= 2


@pytest.mark.asyncio
async def test_to_raw_item_engagement_mapping():
    """_to_raw_item() maps stars → upvotes and open_issues → comments."""
    collector = GitHubCollector()
    repo = make_repo(stargazers_count=999, open_issues_count=42)

    item = collector._to_raw_item(repo)

    assert item.engagement["upvotes"] == 999
    assert item.engagement["comments"] == 42


@pytest.mark.asyncio
async def test_to_raw_item_fields():
    """_to_raw_item() populates all required RawItem fields correctly."""
    collector = GitHubCollector()
    repo = make_repo(
        id=42,
        full_name="myorg/myrepo",
        description="My awesome repo",
        html_url="https://github.com/myorg/myrepo",
        language="Go",
        topics=["cloud", "devops"],
        forks_count=88,
    )

    item = collector._to_raw_item(repo)

    assert item.source == "github"
    assert item.title == "myorg/myrepo: My awesome repo"
    assert item.url == "https://github.com/myorg/myrepo"
    assert item.content_preview == "My awesome repo"
    assert item.external_id == "github_42"
    assert item.source_lang == "en"
    assert item.metadata["language"] == "Go"
    assert item.metadata["topics"] == ["cloud", "devops"]
    assert item.metadata["forks"] == 88
    assert item.metadata["full_name"] == "myorg/myrepo"


@pytest.mark.asyncio
async def test_rate_limit_403_returns_empty():
    """_search_repos() returns empty list gracefully on 403 rate limit."""
    collector = GitHubCollector(min_stars=50, languages=["python"])

    mock_response = MagicMock()
    mock_response.status_code = 403
    mock_response.headers = {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "1700000000"}

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)

    result = await collector._search_repos(mock_client, "2024-01-01", "python", 10)

    assert result == []


@pytest.mark.asyncio
async def test_language_filter_in_query():
    """_search_repos() includes language filter in query string when language is set."""
    collector = GitHubCollector(min_stars=50)

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"total_count": 0, "items": []}

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)

    await collector._search_repos(mock_client, "2024-01-01", "rust", 5)

    call_kwargs = mock_client.get.call_args
    params = call_kwargs[1]["params"] if "params" in call_kwargs[1] else call_kwargs[0][1]
    assert "language:rust" in params["q"]


@pytest.mark.asyncio
async def test_no_language_filter_when_empty_string():
    """_search_repos() omits language filter when language is empty string."""
    collector = GitHubCollector(min_stars=50)

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"total_count": 0, "items": []}

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)

    await collector._search_repos(mock_client, "2024-01-01", "", 5)

    call_kwargs = mock_client.get.call_args
    params = call_kwargs[1]["params"] if "params" in call_kwargs[1] else call_kwargs[0][1]
    assert "language:" not in params["q"]


@pytest.mark.asyncio
async def test_collect_handles_search_error_gracefully():
    """collect() logs warning and continues when one language search fails."""
    collector = GitHubCollector(min_stars=50, languages=["python", "go"])

    good_response = MagicMock()
    good_response.status_code = 200
    good_response.json.return_value = {"total_count": 1, "items": [SAMPLE_REPOS[0]]}

    mock_client = AsyncMock()
    # First call raises, second succeeds
    mock_client.get = AsyncMock(side_effect=[Exception("network error"), good_response])
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("content_autopilot.collectors.github.create_client", return_value=mock_client), \
         patch.object(collector._rate_limiter, "acquire", new_callable=AsyncMock):
        items = await collector.collect(limit=10)

    # Should still return items from the successful language
    assert len(items) == 1
    assert items[0].source == "github"


@pytest.mark.asyncio
async def test_to_raw_item_no_description():
    """_to_raw_item() handles missing description gracefully."""
    collector = GitHubCollector()
    repo = make_repo(description=None)
    repo["description"] = None  # explicitly None

    item = collector._to_raw_item(repo)

    assert "No description" in item.title
    assert item.content_preview == ""
