"""Tests for WordPress REST API publisher."""
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from content_autopilot.publishers.wordpress import WordPressPublisher
from content_autopilot.schemas import ArticleDraft, PublishResult


def make_draft(**kwargs) -> ArticleDraft:
    defaults = {
        "title_ko": "테스트 제목",
        "content_ko": "# 테스트\n\n본문 내용입니다.",
        "summary_ko": "요약 내용입니다.",
        "source_attribution": "https://example.com/article",
        "tags": ["python", "테스트"],
    }
    defaults.update(kwargs)
    return ArticleDraft(**defaults)


# ---------------------------------------------------------------------------
# _get_auth_header tests
# ---------------------------------------------------------------------------


class TestGetAuthHeader:
    def test_returns_basic_auth_header(self):
        publisher = WordPressPublisher(
            site_url="https://example.com",
            username="admin",
            app_password="test_password",
        )
        header = publisher._get_auth_header()
        assert "Authorization" in header
        assert header["Authorization"].startswith("Basic ")

    def test_basic_auth_encoding(self):
        publisher = WordPressPublisher(
            site_url="https://example.com",
            username="admin",
            app_password="secret",
        )
        header = publisher._get_auth_header()
        # Decode and verify
        import base64

        encoded = header["Authorization"].replace("Basic ", "")
        decoded = base64.b64decode(encoded).decode()
        assert decoded == "admin:secret"

    def test_special_characters_in_password(self):
        publisher = WordPressPublisher(
            site_url="https://example.com",
            username="user@example.com",
            app_password="pass:word:with:colons",
        )
        header = publisher._get_auth_header()
        import base64

        encoded = header["Authorization"].replace("Basic ", "")
        decoded = base64.b64decode(encoded).decode()
        assert decoded == "user@example.com:pass:word:with:colons"


# ---------------------------------------------------------------------------
# _draft_to_post tests
# ---------------------------------------------------------------------------


class TestDraftToPost:
    def test_converts_markdown_to_html(self):
        draft = make_draft(
            content_ko="# 제목\n\n본문 **굵은** 텍스트",
        )
        publisher = WordPressPublisher(
            site_url="https://example.com",
            username="admin",
            app_password="secret",
        )
        post = publisher._draft_to_post(draft)
        assert "<h1>" in post["content"]
        assert "<strong>" in post["content"]

    def test_includes_source_attribution(self):
        draft = make_draft(
            content_ko="본문 내용",
            source_attribution="https://example.com/source",
        )
        publisher = WordPressPublisher(
            site_url="https://example.com",
            username="admin",
            app_password="secret",
        )
        post = publisher._draft_to_post(draft)
        assert "출처:" in post["content"]
        assert "https://example.com/source" in post["content"]

    def test_does_not_duplicate_attribution(self):
        draft = make_draft(
            content_ko="본문 내용 https://example.com/source",
            source_attribution="https://example.com/source",
        )
        publisher = WordPressPublisher(
            site_url="https://example.com",
            username="admin",
            app_password="secret",
        )
        post = publisher._draft_to_post(draft)
        # Count occurrences of the URL
        count = post["content"].count("https://example.com/source")
        assert count == 1

    def test_sets_correct_post_fields(self):
        draft = make_draft(
            title_ko="테스트 제목",
            summary_ko="요약 내용",
        )
        publisher = WordPressPublisher(
            site_url="https://example.com",
            username="admin",
            app_password="secret",
        )
        post = publisher._draft_to_post(draft)
        assert post["title"] == "테스트 제목"
        assert post["excerpt"] == "요약 내용"
        assert post["status"] == "publish"
        assert post["tags"] == []
        assert post["categories"] == []

    def test_truncates_excerpt_to_300_chars(self):
        long_summary = "a" * 500
        draft = make_draft(summary_ko=long_summary)
        publisher = WordPressPublisher(
            site_url="https://example.com",
            username="admin",
            app_password="secret",
        )
        post = publisher._draft_to_post(draft)
        assert len(post["excerpt"]) == 300

    def test_empty_summary_results_in_empty_excerpt(self):
        draft = make_draft(summary_ko="")
        publisher = WordPressPublisher(
            site_url="https://example.com",
            username="admin",
            app_password="secret",
        )
        post = publisher._draft_to_post(draft)
        assert post["excerpt"] == ""


# ---------------------------------------------------------------------------
# publish tests
# ---------------------------------------------------------------------------


class TestPublish:
    @pytest.mark.asyncio
    async def test_publish_success_returns_url(self):
        draft = make_draft()
        publisher = WordPressPublisher(
            site_url="https://example.com",
            username="admin",
            app_password="secret",
        )

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "id": 123,
            "link": "https://example.com/posts/test-title/",
            "status": "publish",
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "content_autopilot.publishers.wordpress.create_client",
            return_value=mock_client,
        ):
            result = await publisher.publish(draft)

        assert result.channel == "wordpress"
        assert result.status == "success"
        assert result.external_url == "https://example.com/posts/test-title/"
        assert result.error is None

    @pytest.mark.asyncio
    async def test_publish_http_error_returns_failed(self):
        draft = make_draft()
        publisher = WordPressPublisher(
            site_url="https://example.com",
            username="admin",
            app_password="secret",
        )

        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Unauthorized", request=MagicMock(), response=mock_response
        )

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "content_autopilot.publishers.wordpress.create_client",
            return_value=mock_client,
        ):
            result = await publisher.publish(draft)

        assert result.channel == "wordpress"
        assert result.status == "failed"
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_publish_generic_exception_returns_failed(self):
        draft = make_draft()
        publisher = WordPressPublisher(
            site_url="https://example.com",
            username="admin",
            app_password="secret",
        )

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=Exception("Network error"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "content_autopilot.publishers.wordpress.create_client",
            return_value=mock_client,
        ):
            result = await publisher.publish(draft)

        assert result.channel == "wordpress"
        assert result.status == "failed"
        assert "Network error" in result.error

    @pytest.mark.asyncio
    async def test_publish_no_credentials_returns_skipped(self):
        draft = make_draft()
        publisher = WordPressPublisher(
            site_url="https://example.com",
            username="",
            app_password="",
        )

        result = await publisher.publish(draft)

        assert result.channel == "wordpress"
        assert result.status == "skipped"
        assert result.error == "No credentials"

    @pytest.mark.asyncio
    async def test_publish_missing_username_returns_skipped(self):
        draft = make_draft()
        publisher = WordPressPublisher(
            site_url="https://example.com",
            username="",
            app_password="secret",
        )

        result = await publisher.publish(draft)

        assert result.channel == "wordpress"
        assert result.status == "skipped"

    @pytest.mark.asyncio
    async def test_publish_missing_password_returns_skipped(self):
        draft = make_draft()
        publisher = WordPressPublisher(
            site_url="https://example.com",
            username="admin",
            app_password="",
        )

        result = await publisher.publish(draft)

        assert result.channel == "wordpress"
        assert result.status == "skipped"

    @pytest.mark.asyncio
    async def test_publish_sends_correct_endpoint(self):
        draft = make_draft()
        publisher = WordPressPublisher(
            site_url="https://example.com",
            username="admin",
            app_password="secret",
        )

        mock_response = MagicMock()
        mock_response.json.return_value = {"link": "https://example.com/post/"}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "content_autopilot.publishers.wordpress.create_client",
            return_value=mock_client,
        ):
            await publisher.publish(draft)

        # Verify the endpoint was called correctly
        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        assert "https://example.com/wp-json/wp/v2/posts" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_publish_sends_auth_header(self):
        draft = make_draft()
        publisher = WordPressPublisher(
            site_url="https://example.com",
            username="admin",
            app_password="secret",
        )

        mock_response = MagicMock()
        mock_response.json.return_value = {"link": "https://example.com/post/"}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "content_autopilot.publishers.wordpress.create_client",
            return_value=mock_client,
        ):
            await publisher.publish(draft)

        # Verify auth header was sent
        call_args = mock_client.post.call_args
        headers = call_args[1]["headers"]
        assert "Authorization" in headers
        assert headers["Authorization"].startswith("Basic ")

    @pytest.mark.asyncio
    async def test_publish_sends_json_content_type(self):
        draft = make_draft()
        publisher = WordPressPublisher(
            site_url="https://example.com",
            username="admin",
            app_password="secret",
        )

        mock_response = MagicMock()
        mock_response.json.return_value = {"link": "https://example.com/post/"}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "content_autopilot.publishers.wordpress.create_client",
            return_value=mock_client,
        ):
            await publisher.publish(draft)

        # Verify content-type header
        call_args = mock_client.post.call_args
        headers = call_args[1]["headers"]
        assert headers["Content-Type"] == "application/json"


# ---------------------------------------------------------------------------
# Initialization tests
# ---------------------------------------------------------------------------


class TestInitialization:
    def test_init_with_explicit_params(self):
        publisher = WordPressPublisher(
            site_url="https://example.com",
            username="admin",
            app_password="secret",
        )
        assert publisher.site_url == "https://example.com"
        assert publisher._username == "admin"
        assert publisher._app_password == "secret"

    def test_init_strips_trailing_slash_from_site_url(self):
        publisher = WordPressPublisher(
            site_url="https://example.com/",
            username="admin",
            app_password="secret",
        )
        assert publisher.site_url == "https://example.com"

    def test_init_with_settings_defaults(self):
        with patch("content_autopilot.publishers.wordpress.settings") as mock_settings:
            mock_settings.wp_site_url = "https://default.com"
            mock_settings.wp_username = "default_user"
            mock_settings.wp_app_password = "default_pass"

            publisher = WordPressPublisher()
            assert publisher.site_url == "https://default.com"
            assert publisher._username == "default_user"
            assert publisher._app_password == "default_pass"
