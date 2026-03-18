from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from content_autopilot.orchestrator.pipeline import Pipeline
from content_autopilot.schemas import ArticleDraft, PublishResult, RawItem, ScoredItem, SummaryResult


def _make_raw_item(source: str, idx: int) -> RawItem:
    return RawItem(
        source=source,
        title=f"{source}-title-{idx}",
        url=f"https://example.com/{source}/{idx}",
        content_preview=f"preview-{source}-{idx}",
        engagement={"upvotes": 10 + idx, "comments": 2},
        external_id=f"{source}-{idx}",
        source_lang="en",
    )


def _make_draft() -> ArticleDraft:
    return ArticleDraft(
        title_ko="테스트 제목",
        content_ko="테스트 본문",
        summary_ko="테스트 요약",
        source_attribution="https://example.com/source",
        tags=["test"],
    )


@pytest.mark.asyncio
async def test_pipeline_run_success_with_all_components_mocked() -> None:
    hn_items = [_make_raw_item("hn", 1), _make_raw_item("hn", 2)]
    github_items = [_make_raw_item("github", 1), _make_raw_item("github", 2)]
    rss_items = [_make_raw_item("rss", 1), _make_raw_item("rss", 2)]
    youtube_items = [_make_raw_item("youtube", 1), _make_raw_item("youtube", 2)]
    all_items = hn_items + github_items + rss_items + youtube_items

    top_scored = [
        ScoredItem(raw_item=all_items[0], score=0.9),
        ScoredItem(raw_item=all_items[1], score=0.8),
        ScoredItem(raw_item=all_items[2], score=0.7),
    ]

    summary_mock = AsyncMock(
        return_value=SummaryResult(
            summary_ko="요약",
            source_url="https://example.com/source",
            source_title="source title",
        )
    )
    humanize_mock = AsyncMock(return_value=_make_draft())
    ghost_publish_mock = AsyncMock(
        return_value=PublishResult(channel="ghost", status="success", external_url="https://ghost/post")
    )
    telegram_publish_mock = AsyncMock(
        return_value=PublishResult(channel="telegram", status="success", external_url="1")
    )
    discord_publish_mock = AsyncMock(
        return_value=PublishResult(channel="discord", status="success", external_url="2")
    )
    wordpress_publish_mock = AsyncMock(
        return_value=PublishResult(channel="wordpress", status="skipped", external_url=None)
    )
    naver_publish_mock = AsyncMock(
        return_value=PublishResult(channel="naver", status="skipped", external_url=None)
    )
    tistory_publish_mock = AsyncMock(
        return_value=PublishResult(channel="tistory", status="skipped", external_url=None)
    )

    with (
        patch("content_autopilot.orchestrator.pipeline.HNCollector.collect", new=AsyncMock(return_value=hn_items)),
        patch(
            "content_autopilot.orchestrator.pipeline.GitHubCollector.collect",
            new=AsyncMock(return_value=github_items),
        ),
        patch("content_autopilot.orchestrator.pipeline.RSSCollector.collect", new=AsyncMock(return_value=rss_items)),
        patch(
            "content_autopilot.orchestrator.pipeline.YouTubeCollector.collect",
            new=AsyncMock(return_value=youtube_items),
        ),
        patch("content_autopilot.orchestrator.pipeline.DedupService.deduplicate", return_value=all_items),
        patch("content_autopilot.orchestrator.pipeline.ScoringEngine.score_batch", return_value=top_scored),
        patch("content_autopilot.orchestrator.pipeline.ScoringEngine.select_top_n", return_value=top_scored),
        patch("content_autopilot.orchestrator.pipeline.Summarizer.process", new=summary_mock),
        patch("content_autopilot.orchestrator.pipeline.Humanizer.humanize", new=humanize_mock),
        patch("content_autopilot.orchestrator.pipeline.GhostPublisher.publish", new=ghost_publish_mock),
        patch("content_autopilot.orchestrator.pipeline.TelegramPublisher.publish", new=telegram_publish_mock),
        patch("content_autopilot.orchestrator.pipeline.DiscordPublisher.publish", new=discord_publish_mock),
        patch("content_autopilot.orchestrator.pipeline.WordPressPublisher.publish", new=wordpress_publish_mock),
        patch("content_autopilot.orchestrator.pipeline.NaverBlogPublisher.publish", new=naver_publish_mock),
        patch("content_autopilot.orchestrator.pipeline.TistoryPublisher.publish", new=tistory_publish_mock),
    ):
        pipeline = Pipeline(dry_run=False)
        result = await pipeline.run()

    assert result.collected == 8
    assert result.scored == 3
    assert result.published == 3
    assert result.status == "success"
    assert summary_mock.await_count == 3
    assert humanize_mock.await_count == 3
    assert ghost_publish_mock.await_count == 3


@pytest.mark.asyncio
async def test_pipeline_run_dry_run_skips_publishers() -> None:
    hn_items = [_make_raw_item("hn", 1), _make_raw_item("hn", 2)]
    github_items = [_make_raw_item("github", 1), _make_raw_item("github", 2)]
    rss_items = [_make_raw_item("rss", 1), _make_raw_item("rss", 2)]
    youtube_items = [_make_raw_item("youtube", 1), _make_raw_item("youtube", 2)]
    all_items = hn_items + github_items + rss_items + youtube_items

    top_scored = [
        ScoredItem(raw_item=all_items[0], score=0.9),
        ScoredItem(raw_item=all_items[1], score=0.8),
        ScoredItem(raw_item=all_items[2], score=0.7),
    ]

    summary_mock = AsyncMock(
        return_value=SummaryResult(
            summary_ko="요약",
            source_url="https://example.com/source",
            source_title="source title",
        )
    )
    humanize_mock = AsyncMock(return_value=_make_draft())
    ghost_publish_mock = AsyncMock(
        return_value=PublishResult(channel="ghost", status="success", external_url="https://ghost/post")
    )
    telegram_publish_mock = AsyncMock(
        return_value=PublishResult(channel="telegram", status="success", external_url="1")
    )
    discord_publish_mock = AsyncMock(
        return_value=PublishResult(channel="discord", status="success", external_url="2")
    )
    wordpress_publish_mock = AsyncMock(
        return_value=PublishResult(channel="wordpress", status="skipped", external_url=None)
    )
    naver_publish_mock = AsyncMock(
        return_value=PublishResult(channel="naver", status="skipped", external_url=None)
    )
    tistory_publish_mock = AsyncMock(
        return_value=PublishResult(channel="tistory", status="skipped", external_url=None)
    )

    with (
        patch("content_autopilot.orchestrator.pipeline.HNCollector.collect", new=AsyncMock(return_value=hn_items)),
        patch(
            "content_autopilot.orchestrator.pipeline.GitHubCollector.collect",
            new=AsyncMock(return_value=github_items),
        ),
        patch("content_autopilot.orchestrator.pipeline.RSSCollector.collect", new=AsyncMock(return_value=rss_items)),
        patch(
            "content_autopilot.orchestrator.pipeline.YouTubeCollector.collect",
            new=AsyncMock(return_value=youtube_items),
        ),
        patch("content_autopilot.orchestrator.pipeline.DedupService.deduplicate", return_value=all_items),
        patch("content_autopilot.orchestrator.pipeline.ScoringEngine.score_batch", return_value=top_scored),
        patch("content_autopilot.orchestrator.pipeline.ScoringEngine.select_top_n", return_value=top_scored),
        patch("content_autopilot.orchestrator.pipeline.Summarizer.process", new=summary_mock),
        patch("content_autopilot.orchestrator.pipeline.Humanizer.humanize", new=humanize_mock),
        patch("content_autopilot.orchestrator.pipeline.GhostPublisher.publish", new=ghost_publish_mock),
        patch("content_autopilot.orchestrator.pipeline.TelegramPublisher.publish", new=telegram_publish_mock),
        patch("content_autopilot.orchestrator.pipeline.DiscordPublisher.publish", new=discord_publish_mock),
        patch("content_autopilot.orchestrator.pipeline.WordPressPublisher.publish", new=wordpress_publish_mock),
        patch("content_autopilot.orchestrator.pipeline.NaverBlogPublisher.publish", new=naver_publish_mock),
        patch("content_autopilot.orchestrator.pipeline.TistoryPublisher.publish", new=tistory_publish_mock),
    ):
        pipeline = Pipeline(dry_run=True)
        result = await pipeline.run()

    assert result.collected == 8
    assert result.scored == 3
    assert result.published == 0
    assert result.status == "success"
    assert ghost_publish_mock.await_count == 0
    assert telegram_publish_mock.await_count == 0
    assert discord_publish_mock.await_count == 0


@pytest.mark.asyncio
async def test_pipeline_handles_collector_and_publish_failures() -> None:
    hn_items = [_make_raw_item("hn", 1), _make_raw_item("hn", 2)]
    github_items = [_make_raw_item("github", 1), _make_raw_item("github", 2)]
    rss_items = [_make_raw_item("rss", 1), _make_raw_item("rss", 2)]
    youtube_items = [_make_raw_item("youtube", 1), _make_raw_item("youtube", 2)]
    all_items = hn_items + github_items + rss_items + youtube_items

    top_scored = [
        ScoredItem(raw_item=all_items[0], score=0.9),
        ScoredItem(raw_item=all_items[1], score=0.8),
        ScoredItem(raw_item=all_items[2], score=0.7),
    ]

    summary_mock = AsyncMock(
        return_value=SummaryResult(
            summary_ko="요약",
            source_url="https://example.com/source",
            source_title="source title",
        )
    )
    humanize_mock = AsyncMock(return_value=_make_draft())
    ghost_publish_mock = AsyncMock(
        side_effect=[
            PublishResult(channel="ghost", status="failed", error="boom"),
            PublishResult(channel="ghost", status="success", external_url="https://ghost/post-1"),
            PublishResult(channel="ghost", status="success", external_url="https://ghost/post-2"),
            PublishResult(channel="ghost", status="success", external_url="https://ghost/post-3"),
        ]
    )
    telegram_publish_mock = AsyncMock(
        return_value=PublishResult(channel="telegram", status="success", external_url="1")
    )
    discord_publish_mock = AsyncMock(
        return_value=PublishResult(channel="discord", status="success", external_url="2")
    )
    wordpress_publish_mock = AsyncMock(
        return_value=PublishResult(channel="wordpress", status="skipped", external_url=None)
    )
    naver_publish_mock = AsyncMock(
        return_value=PublishResult(channel="naver", status="skipped", external_url=None)
    )
    tistory_publish_mock = AsyncMock(
        return_value=PublishResult(channel="tistory", status="skipped", external_url=None)
    )

    with (
        patch("content_autopilot.orchestrator.pipeline.HNCollector.collect", new=AsyncMock(return_value=hn_items)),
        patch(
            "content_autopilot.orchestrator.pipeline.GitHubCollector.collect",
            new=AsyncMock(return_value=github_items),
        ),
        patch("content_autopilot.orchestrator.pipeline.RSSCollector.collect", new=AsyncMock(return_value=rss_items)),
        patch(
            "content_autopilot.orchestrator.pipeline.YouTubeCollector.collect",
            new=AsyncMock(return_value=youtube_items),
        ),
        patch("content_autopilot.orchestrator.pipeline.DedupService.deduplicate", return_value=all_items),
        patch("content_autopilot.orchestrator.pipeline.ScoringEngine.score_batch", return_value=top_scored),
        patch("content_autopilot.orchestrator.pipeline.ScoringEngine.select_top_n", return_value=top_scored),
        patch("content_autopilot.orchestrator.pipeline.Summarizer.process", new=summary_mock),
        patch("content_autopilot.orchestrator.pipeline.Humanizer.humanize", new=humanize_mock),
        patch("content_autopilot.orchestrator.pipeline.GhostPublisher.publish", new=ghost_publish_mock),
        patch("content_autopilot.orchestrator.pipeline.TelegramPublisher.publish", new=telegram_publish_mock),
        patch("content_autopilot.orchestrator.pipeline.DiscordPublisher.publish", new=discord_publish_mock),
        patch("content_autopilot.orchestrator.pipeline.WordPressPublisher.publish", new=wordpress_publish_mock),
        patch("content_autopilot.orchestrator.pipeline.NaverBlogPublisher.publish", new=naver_publish_mock),
        patch("content_autopilot.orchestrator.pipeline.TistoryPublisher.publish", new=tistory_publish_mock),
    ):
        pipeline = Pipeline(dry_run=False)
        result = await pipeline.run()

    assert result.collected == 8
    assert result.scored == 3
    assert result.published == 3
    assert result.status == "success"
