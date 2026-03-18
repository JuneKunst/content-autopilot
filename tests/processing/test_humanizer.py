import json
from unittest.mock import AsyncMock

import pytest

from content_autopilot.ai.client import AIResponse
from content_autopilot.processing.humanizer import Humanizer, MIN_CONTENT_LENGTH
from content_autopilot.schemas import ArticleDraft, SummaryResult


class _FakeClient:
    def __init__(self, responses: list[AIResponse]) -> None:
        self.chat: AsyncMock = AsyncMock(side_effect=responses)


def _long_korean_content(source_url: str) -> str:
    base = (
        "요즘 개발자 커뮤니티에서 가장 많이 회자되는 주제는 생성형 인공지능 도구의 실무 적용입니다. "
        "단순한 데모를 넘어 실제 팀 워크플로우에 연결하려면 품질 기준, 검수 방식, 비용 추적까지 함께 설계해야 합니다. "
        "특히 문서화와 요약 자동화는 빠르게 효과를 보여주지만, 출처를 명확하게 남기지 않으면 신뢰가 크게 떨어질 수 있습니다. "
        "그래서 도구를 도입할 때는 성능 수치보다도 팀이 이해 가능한 문장과 책임 있는 인용 체계를 먼저 챙기는 것이 중요합니다. "
        "결국 좋은 자동화는 화려한 문장보다 정확한 맥락과 재현 가능한 근거를 남기는 데서 시작된다고 생각합니다. "
    )
    return f"{base}\n\n출처: {source_url}"


def _draft_json(title: str, content: str, tags: list[str]) -> str:
    return json.dumps(
        {
            "title_ko": title,
            "content_ko": content,
            "tags": tags,
        },
        ensure_ascii=False,
    )


@pytest.mark.asyncio
async def test_humanize_returns_article_draft_with_source_and_length():
    source_url = "https://example.com/source"
    client = _FakeClient(
        responses=[
            AIResponse(
                content=_draft_json(
                    "AI 실무 적용 포인트",
                    _long_korean_content(source_url),
                    ["ai", "요약", "automation"],
                ),
                usage={"input_tokens": 11, "output_tokens": 22, "total_tokens": 33},
                model="deepseek-chat",
            )
        ]
    )
    humanizer = Humanizer(client=client)

    result = await humanizer.humanize(
        summary_ko="핵심 요약",
        source_url=source_url,
        source_title="원문 제목",
    )

    assert result.source_attribution == source_url
    assert source_url in result.content_ko
    assert len(result.content_ko) >= 300
    assert len(result.tags) >= 1


def test_check_quality_returns_issues_for_short_content():
    humanizer = Humanizer(client=_FakeClient(responses=[]))
    draft = ArticleDraft(
        title_ko="짧은 글",
        content_ko="짧은 본문",
        summary_ko="요약",
        source_attribution="https://example.com/source",
        tags=[],
    )

    issues = humanizer._check_quality(draft, {"forbidden_patterns": []})

    assert any("본문이 너무 짧습니다" in issue for issue in issues)


def test_check_quality_returns_issues_for_missing_source_link_in_content():
    humanizer = Humanizer(client=_FakeClient(responses=[]))
    long_content_without_source = "가" * MIN_CONTENT_LENGTH
    draft = ArticleDraft(
        title_ko="출처 누락",
        content_ko=long_content_without_source,
        summary_ko="요약",
        source_attribution="https://example.com/source",
        tags=[],
    )

    issues = humanizer._check_quality(draft, {"forbidden_patterns": []})

    assert "출처 링크가 본문에 없습니다" in issues


def test_check_quality_returns_empty_for_valid_draft():
    source_url = "https://example.com/source"
    humanizer = Humanizer(client=_FakeClient(responses=[]))
    draft = ArticleDraft(
        title_ko="정상",
        content_ko=_long_korean_content(source_url),
        summary_ko="요약",
        source_attribution=source_url,
        tags=["ai"],
    )

    issues = humanizer._check_quality(draft, {"forbidden_patterns": ["금지문구"]})

    assert issues == []


def test_parse_draft_response_with_valid_json_returns_article_draft():
    source_url = "https://example.com/source"
    humanizer = Humanizer(client=_FakeClient(responses=[]))

    result = humanizer._parse_draft_response(
        content=_draft_json("제목", _long_korean_content(source_url), ["ai", "python"]),
        source_url=source_url,
        summary_ko="요약",
    )

    assert result.title_ko == "제목"
    assert source_url in result.content_ko
    assert result.tags == ["ai", "python"]


def test_parse_draft_response_with_json_code_block_returns_article_draft():
    source_url = "https://example.com/source"
    humanizer = Humanizer(client=_FakeClient(responses=[]))
    response = (
        "```json\n"
        + _draft_json("코드블록 제목", _long_korean_content(source_url), ["llm"])
        + "\n```"
    )

    result = humanizer._parse_draft_response(
        content=response,
        source_url=source_url,
        summary_ko="요약",
    )

    assert result.title_ko == "코드블록 제목"
    assert source_url in result.content_ko
    assert result.tags == ["llm"]


def test_parse_draft_response_with_invalid_json_falls_back_to_summary():
    source_url = "https://example.com/source"
    summary_ko = "원본 요약 텍스트"
    humanizer = Humanizer(client=_FakeClient(responses=[]))

    result = humanizer._parse_draft_response(
        content="this is not json",
        source_url=source_url,
        summary_ko=summary_ko,
    )

    assert result.title_ko == summary_ko[:30]
    assert summary_ko in result.content_ko
    assert source_url in result.content_ko


def test_parse_draft_response_auto_inserts_source_url_when_missing():
    source_url = "https://example.com/source"
    humanizer = Humanizer(client=_FakeClient(responses=[]))

    result = humanizer._parse_draft_response(
        content='{"title_ko":"제목","content_ko":"본문만 있음","tags":["test"]}',
        source_url=source_url,
        summary_ko="요약",
    )

    assert source_url in result.content_ko


@pytest.mark.asyncio
async def test_process_summary_uses_summary_result_and_returns_article_draft():
    source_url = "https://example.com/source"
    client = _FakeClient(
        responses=[
            AIResponse(
                content=_draft_json(
                    "요약 기반 제목",
                    _long_korean_content(source_url),
                    ["tech", "korean"],
                ),
                usage={"input_tokens": 9, "output_tokens": 19, "total_tokens": 28},
                model="deepseek-chat",
            )
        ]
    )
    humanizer = Humanizer(client=client)
    summary_result = SummaryResult(
        summary_ko="입력 요약",
        source_url=source_url,
        source_title="원문",
        source_lang="en",
        key_points=["핵심"],
        token_usage={"input_tokens": 1, "output_tokens": 1},
    )

    result = await humanizer.process_summary(summary_result)

    assert result.summary_ko == "입력 요약"
    assert result.source_attribution == source_url
    assert source_url in result.content_ko
