"""Tests for RSS/Atom feed collector."""
import re
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from content_autopilot.collectors.rss import RSSCollector


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_entry(
    title: str = "Test Article",
    link: str = "https://example.com/article",
    summary: str = "<p>This is a <b>summary</b>.</p>",
    published: str | None = "Mon, 17 Mar 2026 12:00:00 +0000",
) -> SimpleNamespace:
    """Build a minimal feedparser-like entry object."""
    entry = SimpleNamespace(
        title=title,
        link=link,
        summary=summary,
    )
    if published is not None:
        entry.published = published
    return entry


def make_parsed_feed(entries: list) -> MagicMock:
    """Build a minimal feedparser parsed-feed object."""
    feed = MagicMock()
    feed.entries = entries
    return feed


FEED_CONFIG = {"url": "https://example.com/rss", "name": "test_feed", "lang": "en"}


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------

class TestEntryToRawItem:
    def setup_method(self):
        self.collector = RSSCollector(feeds=[FEED_CONFIG])

    def test_strips_html_from_summary(self):
        entry = make_entry(summary="<p>Hello <b>world</b>!</p>")
        item = self.collector._entry_to_raw_item(entry, FEED_CONFIG)
        assert item is not None
        # No HTML tags should remain
        assert not re.search(r"<[^>]+>", item.content_preview)
        assert "Hello" in item.content_preview
        assert "world" in item.content_preview

    def test_returns_none_when_no_title(self):
        entry = make_entry(title="")
        item = self.collector._entry_to_raw_item(entry, FEED_CONFIG)
        assert item is None

    def test_returns_none_when_no_link(self):
        entry = make_entry(link="")
        item = self.collector._entry_to_raw_item(entry, FEED_CONFIG)
        assert item is None

    def test_source_set_from_feed_config(self):
        entry = make_entry()
        item = self.collector._entry_to_raw_item(entry, FEED_CONFIG)
        assert item is not None
        assert item.source == "test_feed"

    def test_source_lang_set_from_feed_config(self):
        ko_config = {"url": "https://news.hada.io/rss", "name": "geeknews", "lang": "ko"}
        entry = make_entry()
        item = self.collector._entry_to_raw_item(entry, ko_config)
        assert item is not None
        assert item.source_lang == "ko"

    def test_content_preview_truncated_to_500(self):
        long_summary = "<p>" + "x" * 600 + "</p>"
        entry = make_entry(summary=long_summary)
        item = self.collector._entry_to_raw_item(entry, FEED_CONFIG)
        assert item is not None
        assert len(item.content_preview) <= 500

    def test_uses_content_field_when_no_summary(self):
        entry = SimpleNamespace(
            title="No Summary",
            link="https://example.com/no-summary",
            content=[SimpleNamespace(value="<p>Content field text</p>")],
        )
        item = self.collector._entry_to_raw_item(entry, FEED_CONFIG)
        assert item is not None
        assert "Content field text" in item.content_preview
        assert not re.search(r"<[^>]+>", item.content_preview)

    def test_external_id_uses_link_hash(self):
        entry = make_entry(link="https://example.com/unique-article")
        item = self.collector._entry_to_raw_item(entry, FEED_CONFIG)
        assert item is not None
        assert item.external_id == f"rss_{hash('https://example.com/unique-article')}"

    def test_engagement_defaults_to_zero(self):
        entry = make_entry()
        item = self.collector._entry_to_raw_item(entry, FEED_CONFIG)
        assert item is not None
        assert item.engagement == {"upvotes": 0, "comments": 0}


class TestParseDate:
    def setup_method(self):
        self.collector = RSSCollector(feeds=[FEED_CONFIG])

    def test_parses_rfc2822_published_field(self):
        entry = make_entry(published="Mon, 17 Mar 2026 12:00:00 +0000")
        dt = self.collector._parse_date(entry)
        assert dt is not None
        assert dt.year == 2026
        assert dt.month == 3
        assert dt.day == 17

    def test_returns_none_when_no_date_fields(self):
        entry = SimpleNamespace(title="No date", link="https://example.com")
        dt = self.collector._parse_date(entry)
        assert dt is None

    def test_falls_back_to_updated_field(self):
        entry = SimpleNamespace(
            title="Updated only",
            link="https://example.com",
            updated="Tue, 18 Mar 2026 08:00:00 +0000",
        )
        dt = self.collector._parse_date(entry)
        assert dt is not None
        assert dt.year == 2026
        assert dt.month == 3
        assert dt.day == 18

    def test_returns_none_for_invalid_date(self):
        entry = SimpleNamespace(
            title="Bad date",
            link="https://example.com",
            published="not-a-date",
        )
        dt = self.collector._parse_date(entry)
        assert dt is None


class TestAgeFilter:
    def setup_method(self):
        self.collector = RSSCollector(feeds=[FEED_CONFIG], max_age_hours=24)

    def test_excludes_entries_older_than_max_age(self):
        old_time = datetime.now(timezone.utc) - timedelta(hours=48)
        # Format as RFC 2822
        old_published = old_time.strftime("%a, %d %b %Y %H:%M:%S +0000")
        entry = make_entry(published=old_published)

        with patch("feedparser.parse") as mock_parse:
            mock_parse.return_value = make_parsed_feed([entry])
            items = self.collector._fetch_feed(FEED_CONFIG)

        assert len(items) == 0

    def test_includes_recent_entries(self):
        recent_time = datetime.now(timezone.utc) - timedelta(hours=1)
        recent_published = recent_time.strftime("%a, %d %b %Y %H:%M:%S +0000")
        entry = make_entry(published=recent_published)

        with patch("feedparser.parse") as mock_parse:
            mock_parse.return_value = make_parsed_feed([entry])
            items = self.collector._fetch_feed(FEED_CONFIG)

        assert len(items) == 1

    def test_includes_entries_without_date(self):
        """Entries with no date should not be filtered out."""
        entry = make_entry(published=None)

        with patch("feedparser.parse") as mock_parse:
            mock_parse.return_value = make_parsed_feed([entry])
            items = self.collector._fetch_feed(FEED_CONFIG)

        assert len(items) == 1


class TestCollect:
    @pytest.mark.asyncio
    async def test_collect_returns_items_from_mocked_feed(self):
        recent_time = datetime.now(timezone.utc) - timedelta(hours=1)
        recent_published = recent_time.strftime("%a, %d %b %Y %H:%M:%S +0000")

        entry1 = make_entry(
            title="Article One",
            link="https://example.com/one",
            summary="<p>First article</p>",
            published=recent_published,
        )
        entry2 = make_entry(
            title="Article Two",
            link="https://example.com/two",
            summary="<p>Second article</p>",
            published=recent_published,
        )

        collector = RSSCollector(feeds=[FEED_CONFIG])

        with patch("feedparser.parse") as mock_parse:
            mock_parse.return_value = make_parsed_feed([entry1, entry2])
            items = await collector.collect(limit=10)

        assert len(items) == 2
        titles = {item.title for item in items}
        assert "Article One" in titles
        assert "Article Two" in titles

    @pytest.mark.asyncio
    async def test_collect_respects_limit(self):
        recent_time = datetime.now(timezone.utc) - timedelta(hours=1)
        recent_published = recent_time.strftime("%a, %d %b %Y %H:%M:%S +0000")

        entries = [
            make_entry(
                title=f"Article {i}",
                link=f"https://example.com/{i}",
                published=recent_published,
            )
            for i in range(5)
        ]

        collector = RSSCollector(feeds=[FEED_CONFIG])

        with patch("feedparser.parse") as mock_parse:
            mock_parse.return_value = make_parsed_feed(entries)
            items = await collector.collect(limit=3)

        assert len(items) == 3

    @pytest.mark.asyncio
    async def test_collect_no_html_in_content_preview(self):
        recent_time = datetime.now(timezone.utc) - timedelta(hours=1)
        recent_published = recent_time.strftime("%a, %d %b %Y %H:%M:%S +0000")

        entry1 = make_entry(
            title="HTML Article",
            link="https://example.com/html",
            summary="<div><p>Some <strong>bold</strong> and <em>italic</em> text.</p></div>",
            published=recent_published,
        )
        entry2 = make_entry(
            title="Another HTML Article",
            link="https://example.com/html2",
            summary="<ul><li>Item 1</li><li>Item 2</li></ul>",
            published=recent_published,
        )

        collector = RSSCollector(feeds=[FEED_CONFIG])

        with patch("feedparser.parse") as mock_parse:
            mock_parse.return_value = make_parsed_feed([entry1, entry2])
            items = await collector.collect(limit=10)

        for item in items:
            assert not re.search(r"<[^>]+>", item.content_preview), (
                f"HTML found in content_preview: {item.content_preview!r}"
            )

    @pytest.mark.asyncio
    async def test_collect_handles_feed_error_gracefully(self):
        collector = RSSCollector(feeds=[FEED_CONFIG])

        with patch("feedparser.parse", side_effect=Exception("Network error")):
            items = await collector.collect(limit=10)

        assert items == []

    @pytest.mark.asyncio
    async def test_collect_multiple_feeds(self):
        feeds = [
            {"url": "https://feed1.example.com/rss", "name": "feed1", "lang": "en"},
            {"url": "https://feed2.example.com/rss", "name": "feed2", "lang": "ko"},
        ]
        recent_time = datetime.now(timezone.utc) - timedelta(hours=1)
        recent_published = recent_time.strftime("%a, %d %b %Y %H:%M:%S +0000")

        entry_feed1 = make_entry(title="Feed1 Article", link="https://feed1.example.com/1", published=recent_published)
        entry_feed2 = make_entry(title="Feed2 Article", link="https://feed2.example.com/1", published=recent_published)

        collector = RSSCollector(feeds=feeds)

        call_count = 0

        def mock_parse(url):
            nonlocal call_count
            call_count += 1
            if "feed1" in url:
                return make_parsed_feed([entry_feed1])
            return make_parsed_feed([entry_feed2])

        with patch("feedparser.parse", side_effect=mock_parse):
            items = await collector.collect(limit=10)

        assert call_count == 2
        assert len(items) == 2
        sources = {item.source for item in items}
        assert "feed1" in sources
        assert "feed2" in sources
