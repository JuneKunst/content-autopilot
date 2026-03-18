import importlib
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest


def make_publisher(**kwargs):
    publisher_module = importlib.import_module("content_autopilot.publishers.naver_blog")
    return publisher_module.NaverBlogPublisher(**kwargs)


def make_draft() -> Any:
    schemas_module = importlib.import_module("content_autopilot.schemas")
    return schemas_module.ArticleDraft(
        title_ko="네이버 테스트 제목",
        content_ko="네이버 테스트 본문",
        summary_ko="네이버 테스트 요약",
        source_attribution="https://example.com/source",
        tags=["naver", "blog"],
    )


@pytest.mark.asyncio
async def test_publish_skipped_without_credentials():
    publisher = make_publisher(naver_id="", naver_password="", blog_id="")
    result = await publisher.publish(make_draft())

    assert result.channel == "naver_blog"
    assert result.status == "skipped"
    assert result.error == "No credentials"


@pytest.mark.asyncio
async def test_publish_skipped_when_playwright_not_installed():
    publisher = make_publisher(
        naver_id="user",
        naver_password="password",
        blog_id="blog-id",
    )
    original_import_module = importlib.import_module

    def fake_import_module(name: str, package=None):
        if name == "playwright.async_api":
            raise ImportError("playwright not installed")
        return original_import_module(name, package=package)

    with patch("importlib.import_module", side_effect=fake_import_module):
        result = await publisher.publish(make_draft())

    assert result.channel == "naver_blog"
    assert result.status == "skipped"
    assert result.error == "playwright not installed"


@pytest.mark.asyncio
async def test_publish_success_with_mocked_browser_posting():
    publisher = make_publisher(
        naver_id="user",
        naver_password="password",
        blog_id="blog-id",
    )

    with patch(
        "content_autopilot.publishers.naver_blog.NaverBlogPublisher._post_via_browser",
        new=AsyncMock(return_value="https://blog.naver.com/blog-id/123"),
    ):
        result = await publisher.publish(make_draft())

    assert result.channel == "naver_blog"
    assert result.status == "success"
    assert result.external_url == "https://blog.naver.com/blog-id/123"
    assert result.error is None


@pytest.mark.asyncio
async def test_publish_failed_when_browser_posting_raises():
    publisher = make_publisher(
        naver_id="user",
        naver_password="password",
        blog_id="blog-id",
    )

    with patch(
        "content_autopilot.publishers.naver_blog.NaverBlogPublisher._post_via_browser",
        new=AsyncMock(side_effect=RuntimeError("editor failed")),
    ):
        result = await publisher.publish(make_draft())

    assert result.channel == "naver_blog"
    assert result.status == "failed"
    assert "editor failed" in result.error
