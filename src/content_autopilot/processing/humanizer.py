from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Protocol

import yaml

from content_autopilot.ai.client import AIClient, AIResponse
from content_autopilot.common.logger import get_logger
from content_autopilot.schemas import ArticleDraft, SummaryResult

log = get_logger("processing.humanizer")

MIN_CONTENT_LENGTH = 300
MAX_REGENERATE_ATTEMPTS = 2
DEFAULT_PERSONA_PATH = "config/personas/default.yaml"
DEFAULT_PERSONA = {
    "name": "default",
    "tone": "친근하고 정보 전달력 있는 테크 블로거",
    "style_rules": [],
    "forbidden_patterns": [],
}


class ChatClient(Protocol):
    async def chat(
        self,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.7,
    ) -> AIResponse: ...


class Humanizer:
    def __init__(
        self,
        persona_path: str = DEFAULT_PERSONA_PATH,
        client: ChatClient | None = None,
    ) -> None:
        self._client: ChatClient = client or AIClient()
        self._persona: dict[str, object] = self._load_persona(persona_path)

    def _load_persona(self, persona_path: str) -> dict[str, object]:
        path = Path(persona_path)
        if path.exists():
            with path.open(encoding="utf-8") as f:
                loaded = yaml.safe_load(f)
            if isinstance(loaded, dict):
                return {str(key): value for key, value in loaded.items()}

        log.warning("persona_not_found", path=persona_path)
        return dict(DEFAULT_PERSONA)

    async def humanize(
        self,
        summary_ko: str,
        source_url: str,
        source_title: str = "",
        persona_path: str | None = None,
    ) -> ArticleDraft:
        persona = self._load_persona(persona_path) if persona_path else self._persona

        prompt = self._build_prompt(summary_ko, source_url, source_title, persona)

        draft = ArticleDraft(
            title_ko=summary_ko[:30],
            content_ko=f"{summary_ko}\n\n📌 출처: {source_url}",
            summary_ko=summary_ko,
            source_attribution=source_url,
            persona_id="default",
            tags=[],
        )
        for attempt in range(MAX_REGENERATE_ATTEMPTS + 1):
            response = await self._client.chat(prompt, temperature=0.8)
            draft = self._parse_draft_response(response.content, source_url, summary_ko, persona)

            issues = self._check_quality(draft, persona)
            if not issues:
                break
            if attempt < MAX_REGENERATE_ATTEMPTS:
                log.info("humanizer_regenerating", attempt=attempt + 1, issues=issues)
                prompt = (
                    prompt
                    + "\n\n주의사항 (이전 시도에서 발견된 문제):\n"
                    + "\n".join(f"- {issue}" for issue in issues)
                )

        return draft

    def _build_prompt(
        self,
        summary_ko: str,
        source_url: str,
        source_title: str,
        persona: dict[str, object],
    ) -> str:
        raw_style_rules = persona.get("style_rules", [])
        style_rule_list = raw_style_rules if isinstance(raw_style_rules, list) else []
        style_rules = "\n".join(
            f"- {rule}" for rule in style_rule_list if isinstance(rule, str)
        )
        raw_forbidden = persona.get("forbidden_patterns", [])
        forbidden_list = raw_forbidden if isinstance(raw_forbidden, list) else []
        forbidden = ", ".join(
            pattern
            for pattern in forbidden_list
            if isinstance(pattern, str)
        )
        raw_openings = persona.get("example_openings", [])
        opening_list = raw_openings if isinstance(raw_openings, list) else []
        example_text = "\n".join(
            f"- {opening}" for opening in opening_list[:3] if isinstance(opening, str)
        )

        return f"""당신은 {persona.get("tone", "테크 블로거")}입니다.
다음 내용을 한국어 블로그 포스트로 재작성해주세요.

원본 정보:
- 제목: {source_title}
- 요약: {summary_ko}
- 출처: {source_url}

스타일 규칙:
{style_rules or "- 명확하고 자연스러운 한국어 문장 사용"}

도입부 예시 (참고만, 그대로 쓰지 말것):
{example_text or "- 핵심을 먼저 전달하고 맥락을 자연스럽게 설명"}

절대 사용하지 않을 표현: {forbidden or "없음"}

구조:
1. 제목 (임팩트 있게, 15자 이내 권장)
2. 도입부 (왜 지금 이게 중요한지, 1-2문장)
3. 본문 (3-4 문단, 핵심 내용 + 맥락 + 시사점)
4. 마무리 (개인 의견 또는 독자 질문)
5. 출처 링크 반드시 포함: {source_url}

태그 3-5개 생성 (한국어 또는 영어 기술 용어)

JSON 형식으로 반환:
{{
  "title_ko": "제목",
  "content_ko": "전체 본문 (출처 링크 포함, 최소 300자)",
  "tags": ["tag1", "tag2", "tag3"]
}}"""

    def _parse_draft_response(
        self,
        content: str,
        source_url: str,
        summary_ko: str,
        persona: dict[str, object] | None = None,
    ) -> ArticleDraft:
        clean = re.sub(r"```(?:json)?\s*", "", content).strip().rstrip("`").strip()

        data: dict[str, object] = {}
        try:
            parsed = json.loads(clean)
            if isinstance(parsed, dict):
                data = parsed
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", clean, re.DOTALL)
            if match:
                try:
                    parsed = json.loads(match.group())
                    if isinstance(parsed, dict):
                        data = parsed
                except json.JSONDecodeError:
                    data = {}

        title_value = data.get("title_ko")
        title_ko = title_value if isinstance(title_value, str) else ""
        content_value = data.get("content_ko")
        content_ko = content_value if isinstance(content_value, str) else ""
        tags_value = data.get("tags")
        raw_tags: list[object] = tags_value if isinstance(tags_value, list) else []
        tags = [tag for tag in raw_tags if isinstance(tag, str) and tag.strip()]

        if not title_ko:
            title_ko = summary_ko[:30]
        if not content_ko:
            content_ko = summary_ko

        if source_url not in content_ko:
            content_ko = f"{content_ko}\n\n📌 출처: {source_url}"

        persona_id = "default"
        if isinstance(persona, dict):
            persona_name = persona.get("name")
            if isinstance(persona_name, str) and persona_name:
                persona_id = persona_name

        return ArticleDraft(
            title_ko=title_ko,
            content_ko=content_ko,
            summary_ko=summary_ko,
            source_attribution=source_url,
            persona_id=persona_id,
            tags=tags[:5],
        )

    def _check_quality(self, draft: ArticleDraft, persona: dict[str, object]) -> list[str]:
        issues: list[str] = []
        if len(draft.content_ko) < MIN_CONTENT_LENGTH:
            content_len = len(draft.content_ko)
            issues.append(
                f"본문이 너무 짧습니다 ({content_len}자, 최소 {MIN_CONTENT_LENGTH}자 필요)"
            )
        if draft.source_attribution not in draft.content_ko:
            issues.append("출처 링크가 본문에 없습니다")

        raw_forbidden = persona.get("forbidden_patterns", [])
        forbidden_list = raw_forbidden if isinstance(raw_forbidden, list) else []
        for pattern in forbidden_list:
            if isinstance(pattern, str) and pattern and pattern in draft.content_ko:
                issues.append(f"금지 표현 감지: '{pattern}'")
        return issues

    async def process_summary(self, summary_result: SummaryResult) -> ArticleDraft:
        return await self.humanize(
            summary_ko=summary_result.summary_ko,
            source_url=summary_result.source_url,
            source_title=summary_result.source_title,
        )
