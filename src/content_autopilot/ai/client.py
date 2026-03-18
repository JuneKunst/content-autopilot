import time
from dataclasses import dataclass
from enum import Enum
from typing import TypedDict

import httpx
import structlog
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from content_autopilot.config import settings

log = structlog.get_logger()


class AIProvider(str, Enum):
    OPENAI = "openai"
    GEMINI = "gemini"
    CLAUDE = "claude"


class ProviderConfig(TypedDict):
    url: str
    model: str
    input_cost: float
    output_cost: float


PROVIDER_CONFIGS: dict[AIProvider, ProviderConfig] = {
    AIProvider.OPENAI: {
        "url": "https://api.openai.com/v1/chat/completions",
        "model": "gpt-4o-mini",
        "input_cost": 0.15,
        "output_cost": 0.60,
    },
    AIProvider.GEMINI: {
        "url": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        "model": "gemini-2.0-flash-lite",
        "input_cost": 0.075,
        "output_cost": 0.30,
    },
    AIProvider.CLAUDE: {
        "url": "https://api.anthropic.com/v1/messages",
        "model": "claude-haiku-4-20250414",
        "input_cost": 0.25,
        "output_cost": 1.25,
    },
}


@dataclass
class AIResponse:
    content: str
    usage: dict[str, int]
    model: str
    provider: str = ""


class AIAuthError(Exception):
    """Raised on 401 authentication failure."""


class AIRateLimitError(Exception):
    """Raised on 429 rate limit."""


class AIServerError(Exception):
    """Raised on 5xx server errors."""


class AIClient:

    def __init__(
        self,
        primary: AIProvider = AIProvider.OPENAI,
        fallbacks: list[AIProvider] | None = None,
        max_retries: int = 3,
        timeout: float = 60.0,
    ) -> None:
        self._providers = [primary] + (fallbacks or [])
        self.max_retries = max_retries
        self.timeout = timeout
        self._total_tokens: dict[str, int] = {"input": 0, "output": 0}
        self._api_keys = {
            AIProvider.OPENAI: settings.openai_api_key,
            AIProvider.GEMINI: settings.gemini_api_key,
            AIProvider.CLAUDE: settings.claude_api_key,
        }

    async def chat(
        self,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.7,
    ) -> AIResponse:
        last_error: Exception | None = None

        for provider in self._providers:
            api_key = self._api_keys.get(provider, "")
            if not api_key:
                continue
            try:
                if provider == AIProvider.CLAUDE:
                    return await self._call_claude(
                        prompt,
                        system_prompt,
                        temperature,
                        provider,
                    )
                return await self._call_openai_compat(
                    prompt,
                    system_prompt,
                    temperature,
                    provider,
                )
            except AIAuthError:
                log.warning("ai_auth_error", provider=provider.value)
                last_error = AIAuthError(f"{provider.value} auth failed")
                continue
            except (AIRateLimitError, AIServerError, httpx.TimeoutException) as e:
                log.warning("ai_provider_error", provider=provider.value, error=str(e))
                last_error = e
                continue

        raise last_error or RuntimeError("No AI provider available (check API keys)")

    async def _call_openai_compat(
        self,
        prompt: str,
        system_prompt: str,
        temperature: float,
        provider: AIProvider,
    ) -> AIResponse:
        config = PROVIDER_CONFIGS[provider]
        api_key = self._api_keys[provider]
        url = str(config["url"])
        model = str(config["model"])

        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        @retry(
            stop=stop_after_attempt(self.max_retries),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            retry=retry_if_exception_type(
                (AIRateLimitError, AIServerError, httpx.TimeoutException)
            ),
            reraise=True,
        )
        async def _call() -> AIResponse:
            start = time.monotonic()
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(url, json=payload, headers=headers)
            duration = time.monotonic() - start

            if resp.status_code == 401:
                raise AIAuthError(f"{provider.value} auth failed")
            if resp.status_code == 429:
                raise AIRateLimitError(f"{provider.value} rate limited")
            if resp.status_code >= 500:
                raise AIServerError(f"{provider.value} server error {resp.status_code}")
            resp.raise_for_status()

            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            raw_usage = data.get("usage", {})
            usage = {
                "input_tokens": raw_usage.get("prompt_tokens", 0),
                "output_tokens": raw_usage.get("completion_tokens", 0),
                "total_tokens": raw_usage.get("total_tokens", 0),
            }

            self._total_tokens["input"] += usage["input_tokens"]
            self._total_tokens["output"] += usage["output_tokens"]

            log.info(
                "ai_api_call",
                provider=provider.value,
                model=model,
                input_tokens=usage["input_tokens"],
                output_tokens=usage["output_tokens"],
                duration_s=round(duration, 3),
            )
            return AIResponse(
                content=content,
                usage=usage,
                model=model,
                provider=provider.value,
            )

        return await _call()

    async def _call_claude(
        self,
        prompt: str,
        system_prompt: str,
        temperature: float,
        provider: AIProvider,
    ) -> AIResponse:
        config = PROVIDER_CONFIGS[provider]
        api_key = self._api_keys[provider]
        url = str(config["url"])
        model = str(config["model"])

        payload: dict[str, str | float | int | list[dict[str, str]]] = {
            "model": model,
            "max_tokens": 4096,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
        }
        if system_prompt:
            payload["system"] = system_prompt

        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

        @retry(
            stop=stop_after_attempt(self.max_retries),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            retry=retry_if_exception_type(
                (AIRateLimitError, AIServerError, httpx.TimeoutException)
            ),
            reraise=True,
        )
        async def _call() -> AIResponse:
            start = time.monotonic()
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(url, json=payload, headers=headers)
            duration = time.monotonic() - start

            if resp.status_code == 401:
                raise AIAuthError("Claude auth failed")
            if resp.status_code == 429:
                raise AIRateLimitError("Claude rate limited")
            if resp.status_code >= 500:
                raise AIServerError(f"Claude server error {resp.status_code}")
            resp.raise_for_status()

            data = resp.json()
            content = data["content"][0]["text"]
            raw_usage = data.get("usage", {})
            usage = {
                "input_tokens": raw_usage.get("input_tokens", 0),
                "output_tokens": raw_usage.get("output_tokens", 0),
                "total_tokens": raw_usage.get("input_tokens", 0)
                + raw_usage.get("output_tokens", 0),
            }

            self._total_tokens["input"] += usage["input_tokens"]
            self._total_tokens["output"] += usage["output_tokens"]

            log.info(
                "ai_api_call",
                provider=provider.value,
                model=model,
                input_tokens=usage["input_tokens"],
                output_tokens=usage["output_tokens"],
                duration_s=round(duration, 3),
            )
            return AIResponse(
                content=content,
                usage=usage,
                model=model,
                provider=provider.value,
            )

        return await _call()

    @property
    def total_tokens_used(self) -> dict[str, int]:
        return dict(self._total_tokens)

    def estimate_monthly_cost(self, provider: AIProvider = AIProvider.OPENAI) -> float:
        config = PROVIDER_CONFIGS[provider]
        input_cost = (self._total_tokens["input"] / 1_000_000) * float(config["input_cost"])
        output_cost = (self._total_tokens["output"] / 1_000_000) * float(config["output_cost"])
        return round(input_cost + output_cost, 6)


DeepSeekClient = AIClient
DeepSeekAuthError = AIAuthError
DeepSeekRateLimitError = AIRateLimitError
DeepSeekServerError = AIServerError
