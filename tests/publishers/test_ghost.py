"""Tests for Ghost CMS publisher."""
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import jwt
import pytest

from content_autopilot.publishers.ghost import GhostPublisher
from content_autopilot.schemas import ArticleDraft, PublishResult

# Valid test admin key: 24-char hex id + 64-char hex secret
VALID_KEY_ID = "a" * 24
VALID_SECRET = "b" * 64
VALID_ADMIN_KEY = f"{VALID_KEY_ID}:{VALID_SECRET}"


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
# _make_jwt tests
# ---------------------------------------------------------------------------


class TestMakeJwt:
    def test_valid_key_returns_jwt_string(self):
        publisher = GhostPublisher(
            ghost_url="http://localhost:2368",
            admin_key=VALID_ADMIN_KEY,
        )
        token = publisher._make_jwt()
        assert isinstance(token, str)
        assert len(token) > 0

    def test_jwt_has_correct_claims(self):
        publisher = GhostPublisher(
            ghost_url="http://localhost:2368",
            admin_key=VALID_ADMIN_KEY,
        )
        before = int(time.time())
        token = publisher._make_jwt()
        after = int(time.time())

        # Decode without verification to inspect claims
        decoded = jwt.decode(
            token,
            bytes.fromhex(VALID_SECRET),
            algorithms=["HS256"],
            audience="/admin/",
        )
        assert decoded["aud"] == "/admin/"
        assert before <= decoded["iat"] <= after
        assert decoded["exp"] == decoded["iat"] + 300

    def test_jwt_header_has_kid(self):
        publisher = GhostPublisher(
            ghost_url="http://localhost:2368",
            admin_key=VALID_ADMIN_KEY,
        )
        token = publisher._make_jwt()
        header = jwt.get_unverified_header(token)
        assert header["kid"] == VALID_KEY_ID
        assert header["alg"] == "HS256"

    def test_invalid_key_no_colon_raises_value_error(self):
        publisher = GhostPublisher(
            ghost_url="http://localhost:2368",
            admin_key="invalidkeynocodon",
        )
        with pytest.raises(ValueError, match="Invalid Ghost admin key format"):
            publisher._make_jwt()

    def test_empty_key_raises_value_error(self):
        publisher = GhostPublisher(
            ghost_url="http://localhost:2368",
            admin_key="",
        )
        with pytest.raises(ValueError, match="Invalid Ghost admin key format"):
            publisher._make_jwt()

    def test_none_key_raises_value_error(self):
        publisher = GhostPublisher(
            ghost_url="http://localhost:2368",
            admin_key=None,
        )
        # When admin_key is None, it falls back to settings.ghost_admin_key which is ""
        with pytest.raises(ValueError, match="Invalid Ghost admin key format"):
            publisher._make_jwt()


# ---------------------------------------------------------------------------
# _draft_to_post tests
# ---------------------------------------------------------------------------


class TestDraftToPost:
    def setup_method(self):
        self.publisher = GhostPublisher(
            ghost_url="http://localhost:2368",
            admin_key=VALID_ADMIN_KEY,
        )

    def test_tags_converted_to_name_dicts(self):
        draft = make_draft(tags=["python", "ghost", "cms"])
        post = self.publisher._draft_to_post(draft)
        assert post["tags"] == [{"name": "python"}, {"name": "ghost"}, {"name": "cms"}]

    def test_empty_tags(self):
        draft = make_draft(tags=[])
        post = self.publisher._draft_to_post(draft)
        assert post["tags"] == []

    def test_source_attribution_added_to_html(self):
        draft = make_draft(
            content_ko="본문 내용",
            source_attribution="https://example.com/source",
        )
        post = self.publisher._draft_to_post(draft)
        assert "https://example.com/source" in post["html"]
        assert "출처" in post["html"]

    def test_source_attribution_not_duplicated_if_already_present(self):
        url = "https://example.com/source"
        draft = make_draft(
            content_ko=f"본문 내용 {url}",
            source_attribution=url,
        )
        post = self.publisher._draft_to_post(draft)
        # URL should appear only once (already in content)
        assert post["html"].count(url) == 1

    def test_summary_ko_becomes_custom_excerpt(self):
        draft = make_draft(summary_ko="짧은 요약")
        post = self.publisher._draft_to_post(draft)
        assert post["custom_excerpt"] == "짧은 요약"

    def test_summary_ko_truncated_to_300_chars(self):
        long_summary = "가" * 400
        draft = make_draft(summary_ko=long_summary)
        post = self.publisher._draft_to_post(draft)
        assert len(post["custom_excerpt"]) == 300

    def test_markdown_converted_to_html(self):
        draft = make_draft(content_ko="# 제목\n\n**굵은** 텍스트")
        post = self.publisher._draft_to_post(draft)
        assert "<h1>" in post["html"]
        assert "<strong>" in post["html"]

    def test_status_is_published(self):
        draft = make_draft()
        post = self.publisher._draft_to_post(draft)
        assert post["status"] == "published"

    def test_newsletter_fields_added_when_enabled(self):
        publisher = GhostPublisher(
            ghost_url="http://localhost:2368",
            admin_key=VALID_ADMIN_KEY,
            newsletter_enabled=True,
        )
        draft = make_draft()
        post = publisher._draft_to_post(draft)
        assert post["newsletter"] == {"id": "default"}
        assert post["email_segment"] == "all"

    def test_newsletter_fields_absent_when_disabled(self):
        draft = make_draft()
        post = self.publisher._draft_to_post(draft)
        assert "newsletter" not in post
        assert "email_segment" not in post


# ---------------------------------------------------------------------------
# publish() tests
# ---------------------------------------------------------------------------


class TestPublish:
    def setup_method(self):
        self.publisher = GhostPublisher(
            ghost_url="http://blog.example.com",
            admin_key=VALID_ADMIN_KEY,
        )

    def _make_mock_response(self, status_code=200, json_data=None):
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = status_code
        mock_resp.json.return_value = json_data or {
            "posts": [{"id": "abc123", "url": "https://blog.example.com/test"}]
        }
        if status_code >= 400:
            mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
                message=f"HTTP {status_code}",
                request=MagicMock(),
                response=mock_resp,
            )
        else:
            mock_resp.raise_for_status.return_value = None
        return mock_resp

    @pytest.mark.asyncio
    async def test_publish_success_returns_publish_result(self):
        mock_resp = self._make_mock_response(
            json_data={"posts": [{"id": "abc123", "url": "https://blog.example.com/test"}]}
        )
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch(
            "content_autopilot.publishers.ghost.create_client", return_value=mock_client
        ):
            draft = make_draft()
            result = await self.publisher.publish(draft)

        assert isinstance(result, PublishResult)
        assert result.status == "success"
        assert result.channel == "ghost"
        assert result.external_url == "https://blog.example.com/test"
        assert result.error is None

    @pytest.mark.asyncio
    async def test_publish_calls_correct_endpoint(self):
        mock_resp = self._make_mock_response()
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch(
            "content_autopilot.publishers.ghost.create_client", return_value=mock_client
        ):
            draft = make_draft()
            await self.publisher.publish(draft)

        call_args = mock_client.post.call_args
        assert call_args[0][0] == "http://blog.example.com/ghost/api/admin/posts/"

    @pytest.mark.asyncio
    async def test_publish_sends_correct_payload(self):
        mock_resp = self._make_mock_response()
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch(
            "content_autopilot.publishers.ghost.create_client", return_value=mock_client
        ):
            draft = make_draft(title_ko="내 글 제목")
            await self.publisher.publish(draft)

        call_kwargs = mock_client.post.call_args[1]
        payload = call_kwargs["json"]
        assert "posts" in payload
        assert payload["posts"][0]["title"] == "내 글 제목"

    @pytest.mark.asyncio
    async def test_publish_sends_ghost_auth_header(self):
        mock_resp = self._make_mock_response()
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch(
            "content_autopilot.publishers.ghost.create_client", return_value=mock_client
        ):
            draft = make_draft()
            await self.publisher.publish(draft)

        call_kwargs = mock_client.post.call_args[1]
        headers = call_kwargs["headers"]
        assert headers["Authorization"].startswith("Ghost ")

    @pytest.mark.asyncio
    async def test_publish_http_401_returns_failed(self):
        mock_resp = self._make_mock_response(status_code=401)
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch(
            "content_autopilot.publishers.ghost.create_client", return_value=mock_client
        ):
            draft = make_draft()
            result = await self.publisher.publish(draft)

        assert result.status == "failed"
        assert result.channel == "ghost"
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_publish_http_422_returns_failed(self):
        mock_resp = self._make_mock_response(status_code=422)
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch(
            "content_autopilot.publishers.ghost.create_client", return_value=mock_client
        ):
            draft = make_draft()
            result = await self.publisher.publish(draft)

        assert result.status == "failed"

    @pytest.mark.asyncio
    async def test_publish_network_error_returns_failed(self):
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))

        with patch(
            "content_autopilot.publishers.ghost.create_client", return_value=mock_client
        ):
            draft = make_draft()
            result = await self.publisher.publish(draft)

        assert result.status == "failed"
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_publish_with_send_newsletter_flag(self):
        mock_resp = self._make_mock_response()
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch(
            "content_autopilot.publishers.ghost.create_client", return_value=mock_client
        ):
            draft = make_draft()
            result = await self.publisher.publish(draft, send_newsletter=True)

        assert result.status == "success"
        call_kwargs = mock_client.post.call_args[1]
        payload = call_kwargs["json"]
        assert payload["posts"][0].get("newsletter") == {"id": "default"}


# ---------------------------------------------------------------------------
# get_members_count tests
# ---------------------------------------------------------------------------


class TestGetMembersCount:
    def setup_method(self):
        self.publisher = GhostPublisher(
            ghost_url="http://blog.example.com",
            admin_key=VALID_ADMIN_KEY,
        )

    @pytest.mark.asyncio
    async def test_returns_total_count(self):
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {
            "members": [],
            "meta": {"pagination": {"total": 42}},
        }

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch(
            "content_autopilot.publishers.ghost.create_client", return_value=mock_client
        ):
            count = await self.publisher.get_members_count()

        assert count == 42

    @pytest.mark.asyncio
    async def test_returns_zero_on_error(self):
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(side_effect=Exception("API error"))

        with patch(
            "content_autopilot.publishers.ghost.create_client", return_value=mock_client
        ):
            count = await self.publisher.get_members_count()

        assert count == 0
