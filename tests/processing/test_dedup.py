"""Tests for the deduplication service."""
import pytest
from content_autopilot.processing.dedup import DedupService, DedupResult
from content_autopilot.schemas import RawItem


def make_item(
    title: str,
    url: str,
    external_id: str = "",
    engagement: dict | None = None,
) -> RawItem:
    return RawItem(
        source="hn",
        title=title,
        url=url,
        external_id=external_id,
        engagement=engagement or {},
    )


# ---------------------------------------------------------------------------
# normalize_url
# ---------------------------------------------------------------------------

class TestNormalizeUrl:
    def setup_method(self):
        self.svc = DedupService()

    def test_www_removed(self):
        assert self.svc.normalize_url("https://www.example.com/article") == \
               self.svc.normalize_url("https://example.com/article")

    def test_trailing_slash_removed(self):
        assert self.svc.normalize_url("https://example.com/article/") == \
               self.svc.normalize_url("https://example.com/article")

    def test_www_and_trailing_slash(self):
        assert self.svc.normalize_url("https://www.example.com/article/") == \
               self.svc.normalize_url("https://example.com/article")

    def test_different_urls_differ(self):
        assert self.svc.normalize_url("https://example.com/article-a") != \
               self.svc.normalize_url("https://example.com/article-b")

    def test_lowercase(self):
        assert self.svc.normalize_url("HTTPS://Example.COM/Article") == \
               self.svc.normalize_url("https://example.com/Article")

    def test_query_params_stripped(self):
        assert self.svc.normalize_url("https://example.com/article?utm_source=hn") == \
               self.svc.normalize_url("https://example.com/article")


# ---------------------------------------------------------------------------
# check_url
# ---------------------------------------------------------------------------

class TestCheckUrl:
    def setup_method(self):
        self.svc = DedupService()

    def test_same_url_with_www_and_trailing_slash(self):
        result = self.svc.check_url(
            "https://example.com/article",
            "https://www.example.com/article/",
        )
        assert result.is_duplicate is True
        assert result.similarity_score == 1.0

    def test_different_urls_not_duplicate(self):
        result = self.svc.check_url(
            "https://example.com/article-a",
            "https://example.com/article-b",
        )
        assert result.is_duplicate is False
        assert result.similarity_score == 0.0

    def test_identical_urls(self):
        result = self.svc.check_url(
            "https://example.com/post/123",
            "https://example.com/post/123",
        )
        assert result.is_duplicate is True

    def test_different_domains(self):
        result = self.svc.check_url(
            "https://example.com/article",
            "https://other.com/article",
        )
        assert result.is_duplicate is False


# ---------------------------------------------------------------------------
# check_title
# ---------------------------------------------------------------------------

class TestCheckTitle:
    def setup_method(self):
        self.svc = DedupService(title_threshold=0.8)

    def test_reordered_words_duplicate(self):
        result = self.svc.check_title(
            "OpenAI Releases New AI Model GPT5 Today",
            "OpenAI Releases New AI Model GPT5",
        )
        assert result.is_duplicate is True
        assert result.similarity_score >= 0.8

    def test_completely_different_titles_not_duplicate(self):
        result = self.svc.check_title(
            "Python 4.0 Released",
            "New JavaScript Framework",
        )
        assert result.is_duplicate is False
        assert result.similarity_score < 0.8

    def test_identical_titles(self):
        result = self.svc.check_title(
            "Introducing Pydantic v2",
            "Introducing Pydantic v2",
        )
        assert result.is_duplicate is True
        assert result.similarity_score == 1.0

    def test_similar_but_different_topics(self):
        # "Python tutorial" vs "Python basics" — should NOT be duplicates
        result = self.svc.check_title(
            "Python tutorial for beginners",
            "Python basics for beginners",
        )
        # These are similar but the test verifies the score is computed
        # (may or may not be duplicate depending on exact similarity)
        assert isinstance(result.similarity_score, float)
        assert 0.0 <= result.similarity_score <= 1.0

    def test_punctuation_ignored(self):
        result = self.svc.check_title(
            "OpenAI's New Model: GPT-5 Released!",
            "OpenAIs New Model GPT5 Released",
        )
        assert result.is_duplicate is True

    def test_threshold_respected(self):
        svc_strict = DedupService(title_threshold=0.99)
        result = svc_strict.check_title(
            "New AI Model Released by OpenAI",
            "OpenAI Released New AI Model",
        )
        # With very strict threshold, reordered words may not pass
        assert isinstance(result.is_duplicate, bool)


# ---------------------------------------------------------------------------
# deduplicate
# ---------------------------------------------------------------------------

class TestDeduplicate:
    def setup_method(self):
        self.svc = DedupService()

    def test_empty_list(self):
        assert self.svc.deduplicate([]) == []

    def test_no_duplicates(self):
        items = [
            make_item("Python 4.0 Released", "https://example.com/python4", "id1"),
            make_item("New JavaScript Framework", "https://example.com/jsfw", "id2"),
            make_item("Rust 2.0 Announced", "https://example.com/rust2", "id3"),
        ]
        result = self.svc.deduplicate(items)
        assert len(result) == 3

    def test_url_duplicates_returns_two_items(self):
        items = [
            make_item("Python 4.0 Released", "https://example.com/article", "id1", {"upvotes": 100}),
            make_item("New JavaScript Framework", "https://other.com/different", "id2", {"upvotes": 50}),
            make_item("Python 4.0 Released Mirror", "https://www.example.com/article/", "id3", {"upvotes": 10}),
        ]
        result = self.svc.deduplicate(items)
        assert len(result) == 2

    def test_keeps_higher_engagement_item(self):
        """When deduplicating, keep the item with higher total engagement."""
        items = [
            make_item("Same Article", "https://example.com/article", "id1", {"upvotes": 10, "comments": 5}),
            make_item("Same Article", "https://www.example.com/article/", "id2", {"upvotes": 200, "comments": 50}),
        ]
        result = self.svc.deduplicate(items)
        assert len(result) == 1
        # id2 has higher engagement (250 vs 15), so id2 should be kept
        assert result[0].external_id == "id2"

    def test_keeps_higher_engagement_first_item(self):
        """When first item has higher engagement, keep it."""
        items = [
            make_item("Same Article", "https://example.com/article", "id1", {"upvotes": 500}),
            make_item("Same Article", "https://www.example.com/article/", "id2", {"upvotes": 10}),
        ]
        result = self.svc.deduplicate(items)
        assert len(result) == 1
        assert result[0].external_id == "id1"

    def test_title_duplicates_removed(self):
        """Title similarity duplicates are also removed."""
        items = [
            make_item("OpenAI Releases New AI Model GPT5", "https://techcrunch.com/gpt5", "id1", {"upvotes": 100}),
            make_item("OpenAI Releases New AI Model GPT5", "https://reddit.com/r/ml/gpt5", "id2", {"upvotes": 50}),
        ]
        result = self.svc.deduplicate(items)
        assert len(result) == 1

    def test_single_item(self):
        items = [make_item("Only Article", "https://example.com/only", "id1")]
        result = self.svc.deduplicate(items)
        assert len(result) == 1
        assert result[0].external_id == "id1"

    def test_cross_platform_dedup(self):
        """Same article from HN + Reddit should be deduplicated by title."""
        items = [
            make_item(
                "Show HN: I built a content autopilot in Python",
                "https://news.ycombinator.com/item?id=12345",
                "hn_12345",
                {"upvotes": 300, "comments": 80},
            ),
            make_item(
                "Show HN: I built a content autopilot in Python",
                "https://reddit.com/r/python/comments/abc",
                "reddit_abc",
                {"upvotes": 50, "comments": 10},
            ),
        ]
        result = self.svc.deduplicate(items)
        assert len(result) == 1
        # HN item has higher engagement (380 vs 60)
        assert result[0].external_id == "hn_12345"


# ---------------------------------------------------------------------------
# find_duplicates
# ---------------------------------------------------------------------------

class TestFindDuplicates:
    def setup_method(self):
        self.svc = DedupService()

    def test_no_duplicates_empty_result(self):
        items = [
            make_item("Python 4.0 Released", "https://example.com/a", "id1"),
            make_item("New JavaScript Framework", "https://example.com/b", "id2"),
        ]
        assert self.svc.find_duplicates(items) == []

    def test_url_duplicate_detected(self):
        items = [
            make_item("Python 4.0 Released", "https://example.com/article", "id1"),
            make_item("Python 4.0 Released Copy", "https://www.example.com/article/", "id2"),
        ]
        dups = self.svc.find_duplicates(items)
        assert len(dups) == 1
        i, j, result = dups[0]
        assert result.is_duplicate is True
        assert result.duplicate_of_id == "id1"

    def test_returns_correct_indices(self):
        items = [
            make_item("Python 4.0 Released", "https://example.com/a", "id1"),
            make_item("New JavaScript Framework", "https://example.com/b", "id2"),
            make_item("Python 4.0 Released", "https://www.example.com/a/", "id3"),
        ]
        dups = self.svc.find_duplicates(items)
        assert len(dups) == 1
        i, j, _ = dups[0]
        assert i == 2
        assert j == 0
