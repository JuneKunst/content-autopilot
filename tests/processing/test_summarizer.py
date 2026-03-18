from unittest.mock import AsyncMock

import pytest

from content_autopilot.ai.client import AIResponse
from content_autopilot.processing.summarizer import Summarizer


class _FakeClient:
    def __init__(self, responses: list[AIResponse]) -> None:
        self.chat: AsyncMock = AsyncMock(side_effect=responses)


@pytest.mark.asyncio
async def test_process_english_content_runs_summarize_and_translate():
    client = _FakeClient(
        responses=[
            AIResponse(
                content='{"summary": "English summary.", "key_points": ["Point A", "Point B"]}',
                usage={"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
                model="deepseek-chat",
            ),
            AIResponse(
                content='{"summary_ko": "한국어 요약", "key_points_ko": ["포인트 A"]}',
                usage={"prompt_tokens": 5, "completion_tokens": 7, "total_tokens": 12},
                model="deepseek-chat",
            ),
        ]
    )
    summarizer = Summarizer(client=client)

    result = await summarizer.process(
        content="This is a long English article body.",
        source_url="https://example.com/post",
        source_lang="en",
        source_title="Sample Title",
    )

    assert result.source_url == "https://example.com/post"
    assert result.source_lang == "en"
    assert len(result.key_points) >= 1
    assert result.summary_ko
    assert result.token_usage["input_tokens"] == 15
    assert result.token_usage["output_tokens"] == 27
    assert client.chat.await_count == 2


@pytest.mark.asyncio
async def test_process_korean_content_skips_translation_step():
    client = _FakeClient(
        responses=[
            AIResponse(
                content='{"summary_ko": "요약", "key_points": ["핵심"]}',
                usage={"prompt_tokens": 9, "completion_tokens": 6, "total_tokens": 15},
                model="deepseek-chat",
            )
        ]
    )
    summarizer = Summarizer(client=client)

    result = await summarizer.process(
        content="이것은 한국어 원문입니다.",
        source_url="https://example.com/ko",
        source_lang="ko",
        source_title="한국어 제목",
    )

    assert result.source_lang == "ko"
    assert result.summary_ko == "요약"
    assert client.chat.await_count == 1


def test_parse_json_response_valid_json():
    summarizer = Summarizer(client=_FakeClient(responses=[]))
    parsed = summarizer._parse_json_response('{"summary": "ok", "key_points": ["a"]}')
    assert parsed == {"summary": "ok", "key_points": ["a"]}


def test_parse_json_response_json_code_block():
    summarizer = Summarizer(client=_FakeClient(responses=[]))
    parsed = summarizer._parse_json_response(
        "```json\n{\"summary_ko\": \"요약\", \"key_points_ko\": [\"포인트\"]}\n```"
    )
    assert parsed == {"summary_ko": "요약", "key_points_ko": ["포인트"]}


def test_parse_json_response_invalid_json_returns_empty_dict():
    summarizer = Summarizer(client=_FakeClient(responses=[]))
    parsed = summarizer._parse_json_response("this is not json")
    assert parsed == {}


@pytest.mark.asyncio
async def test_token_usage_keys_present_for_korean_path():
    client = _FakeClient(
        responses=[
            AIResponse(
                content='{"summary_ko": "요약", "key_points": ["핵심"]}',
                usage={"input_tokens": 3, "output_tokens": 4, "total_tokens": 7},
                model="deepseek-chat",
            )
        ]
    )
    summarizer = Summarizer(client=client)

    result = await summarizer.process(
        content="테스트",
        source_url="https://example.com/token",
        source_lang="ko",
    )

    assert "input_tokens" in result.token_usage
    assert "output_tokens" in result.token_usage
    assert result.token_usage["input_tokens"] == 3
    assert result.token_usage["output_tokens"] == 4
