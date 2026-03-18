import importlib
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

def make_publisher(**kwargs):
    publisher_module = importlib.import_module("content_autopilot.publishers.tistory")
    return publisher_module.TistoryPublisher(**kwargs)


def make_draft() -> Any:
    schemas_module = importlib.import_module("content_autopilot.schemas")
    return schemas_module.ArticleDraft(
        title_ko="티스토리 테스트 제목",
        content_ko="티스토리 테스트 본문",
        summary_ko="티스토리 테스트 요약",
        source_attribution="https://example.com/source",
        tags=["tistory", "automation"],
    )


@pytest.mark.asyncio
async def test_publish_skipped_without_credentials():
    publisher = make_publisher(email="", password="", blog_name="")
    result = await publisher.publish(make_draft())

    assert result.channel == "tistory"
    assert result.status == "skipped"
    assert result.error == "No credentials"


@pytest.mark.asyncio
async def test_publish_skipped_when_playwright_not_installed():
    publisher = make_publisher(
        email="user@example.com",
        password="password",
        blog_name="myblog",
    )
    original_import_module = importlib.import_module

    def fake_import_module(name: str, package=None):
        if name == "playwright.async_api":
            raise ImportError("playwright not installed")
        return original_import_module(name, package=package)

    with patch("importlib.import_module", side_effect=fake_import_module):
        result = await publisher.publish(make_draft())

    assert result.channel == "tistory"
    assert result.status == "skipped"
    assert result.error == "playwright not installed"


@pytest.mark.asyncio
async def test_publish_success_with_mocked_browser_posting():
    publisher = make_publisher(
        email="user@example.com",
        password="password",
        blog_name="myblog",
    )

    with patch(
        "content_autopilot.publishers.tistory.TistoryPublisher._post_via_browser",
        new=AsyncMock(return_value="https://myblog.tistory.com/123"),
    ):
        result = await publisher.publish(make_draft())

    assert result.channel == "tistory"
    assert result.status == "success"
    assert result.external_url == "https://myblog.tistory.com/123"
    assert result.error is None


@pytest.mark.asyncio
async def test_publish_failed_when_browser_posting_raises():
    publisher = make_publisher(
        email="user@example.com",
        password="password",
        blog_name="myblog",
    )

    with patch(
        "content_autopilot.publishers.tistory.TistoryPublisher._post_via_browser",
        new=AsyncMock(side_effect=RuntimeError("publish modal failed")),
    ):
        result = await publisher.publish(make_draft())

    assert result.channel == "tistory"
    assert result.status == "failed"
    assert "publish modal failed" in result.error
