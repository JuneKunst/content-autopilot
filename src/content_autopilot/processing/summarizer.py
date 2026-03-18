from __future__ import annotations

import json
import re
from typing import Protocol

from content_autopilot.ai.client import AIResponse, DeepSeekClient
from content_autopilot.common.logger import get_logger
from content_autopilot.common.text_utils import truncate
from content_autopilot.schemas import SummaryResult

log = get_logger("processing.summarizer")

MAX_INPUT_CHARS = 4000


class ChatClient(Protocol):
    async def chat(
        self,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.7,
    ) -> AIResponse: ...


class Summarizer:
    def __init__(self, client: ChatClient | None = None) -> None:
        self._client = client or DeepSeekClient()

    async def process(
        self,
        content: str,
        source_url: str,
        source_lang: str = "en",
        source_title: str = "",
    ) -> SummaryResult:
        truncated_content = truncate(content, MAX_INPUT_CHARS)

        if source_lang == "ko":
            summary_ko, key_points, token_usage = await self._summarize_korean(
                truncated_content, source_title
            )
        else:
            summary_ko, key_points, token_usage = await self._summarize_and_translate(
                truncated_content, source_title
            )

        return SummaryResult(
            summary_ko=summary_ko,
            source_url=source_url,
            source_title=source_title,
            source_lang=source_lang,
            key_points=key_points,
            token_usage=token_usage,
        )

    async def _summarize_and_translate(
        self, content: str, title: str
    ) -> tuple[str, list[str], dict[str, int]]:
        extract_prompt = (
            "Extract 3-5 key points from this content. "
            "Be concise (1-2 sentences per point).\n"
            "Focus on: what happened, why it matters, technical impact.\n\n"
            f"Title: {title}\n"
            f"Content: {content}\n\n"
            "Return JSON format:\n"
            '{"summary": "2-3 sentence summary", "key_points": ["point1", "point2", ...]}'
        )

        response = await self._client.chat(extract_prompt, temperature=0.3)
        extracted = self._parse_json_response(response.content)
        summary_en = self._string_or_default(extracted.get("summary"), content[:200])
        key_points_en = self._string_list_or_default(extracted.get("key_points"), [])

        key_points_str = "\n".join(f"- {point}" for point in key_points_en)
        translate_prompt = (
            "Translate to natural Korean. "
            "Not literal - use conversational Korean tone.\n\n"
            f"Summary: {summary_en}\n"
            "Key points:\n"
            f"{key_points_str}\n\n"
            "Return JSON:\n"
            '{"summary_ko": "한국어 요약", "key_points_ko": ["포인트1", "포인트2", ...]}'
        )

        translate_response = await self._client.chat(translate_prompt, temperature=0.3)
        translated = self._parse_json_response(translate_response.content)
        summary_ko = self._string_or_default(translated.get("summary_ko"), summary_en)
        key_points_ko = self._string_list_or_default(
            translated.get("key_points_ko"), key_points_en
        )

        total_usage = {
            "input_tokens": self._usage_value(response.usage, "input")
            + self._usage_value(translate_response.usage, "input"),
            "output_tokens": self._usage_value(response.usage, "output")
            + self._usage_value(translate_response.usage, "output"),
        }

        return (
            summary_ko,
            key_points_ko,
            total_usage,
        )

    async def _summarize_korean(
        self, content: str, title: str
    ) -> tuple[str, list[str], dict[str, int]]:
        prompt = f"""다음 내용을 요약해주세요. 핵심 포인트 3-5개를 추출해주세요.

제목: {title}
내용: {content}

JSON 형식으로 반환:
{{"summary_ko": "2-3문장 요약", "key_points": ["포인트1", "포인트2", ...]}}"""

        response = await self._client.chat(prompt, temperature=0.3)
        result = self._parse_json_response(response.content)
        summary_ko = self._string_or_default(result.get("summary_ko"), content[:200])
        key_points = self._string_list_or_default(result.get("key_points"), [])

        usage = {
            "input_tokens": self._usage_value(response.usage, "input"),
            "output_tokens": self._usage_value(response.usage, "output"),
        }

        return summary_ko, key_points, usage

    def _usage_value(self, usage: dict[str, int], token_type: str) -> int:
        if token_type == "input":
            return int(usage.get("input_tokens", usage.get("prompt_tokens", 0)))
        return int(usage.get("output_tokens", usage.get("completion_tokens", 0)))

    def _string_or_default(self, value: object, default: str) -> str:
        return value if isinstance(value, str) and value else default

    def _string_list_or_default(self, value: object, default: list[str]) -> list[str]:
        if isinstance(value, list):
            cleaned = [item for item in value if isinstance(item, str) and item]
            return cleaned if cleaned else default
        return default

    def _parse_json_response(self, content: str) -> dict[str, object]:
        cleaned = re.sub(r"```(?:json)?\s*", "", content).strip()
        cleaned = cleaned.rstrip("`").strip()

        try:
            parsed = json.loads(cleaned)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if match:
                try:
                    parsed = json.loads(match.group())
                    return parsed if isinstance(parsed, dict) else {}
                except json.JSONDecodeError as e:
                    log.debug(
                        "summarizer_json_extraction_failed",
                        error=str(e),
                        preview=cleaned[:100],
                    )

        log.warning("summarizer_invalid_json_response", preview=cleaned[:200])
        return {}
