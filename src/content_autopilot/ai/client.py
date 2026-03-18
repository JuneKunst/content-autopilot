"""DeepSeek async API client with retry and token tracking."""

import time
from dataclasses import dataclass, field

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

DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
DEEPSEEK_MODEL = "deepseek-chat"

# Pricing per million tokens (DeepSeek V3)
_INPUT_COST_PER_MTOK = 0.27
_OUTPUT_COST_PER_MTOK = 1.10


@dataclass
class AIResponse:
    content: str
    usage: dict[str, int]  # {input_tokens, output_tokens, total_tokens}
    model: str


class DeepSeekAuthError(Exception):
    """Raised on 401 authentication failure."""


class DeepSeekRateLimitError(Exception):
    """Raised on 429 rate limit."""


class DeepSeekServerError(Exception):
    """Raised on 5xx server errors."""


class DeepSeekClient:
    """Async DeepSeek API client with retry and token tracking."""

    def __init__(
        self,
        api_key: str | None = None,
        max_retries: int = 3,
        timeout: float = 30.0,
    ) -> None:
        self._api_key = api_key or settings.deepseek_api_key
        self.max_retries = max_retries
        self.timeout = timeout
        self._total_tokens_used: dict[str, int] = {"input": 0, "output": 0}

    async def chat(
        self,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.7,
    ) -> AIResponse:
        """Send a chat completion request to DeepSeek API."""

        @retry(
            stop=stop_after_attempt(self.max_retries),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            retry=retry_if_exception_type(
                (DeepSeekRateLimitError, DeepSeekServerError, httpx.TimeoutException)
            ),
            reraise=True,
        )
        async def _call() -> AIResponse:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            payload = {
                "model": DEEPSEEK_MODEL,
                "messages": messages,
                "temperature": temperature,
            }

            headers = {
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            }

            start = time.monotonic()
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    DEEPSEEK_API_URL,
                    json=payload,
                    headers=headers,
                )

            duration = time.monotonic() - start

            if response.status_code == 401:
                raise DeepSeekAuthError("DeepSeek API authentication failed (401)")
            if response.status_code == 429:
                raise DeepSeekRateLimitError("DeepSeek rate limit exceeded (429)")
            if response.status_code >= 500:
                raise DeepSeekServerError(
                    f"DeepSeek server error ({response.status_code})"
                )

            response.raise_for_status()
            data = response.json()

            choice = data["choices"][0]["message"]["content"]
            raw_usage = data.get("usage", {})
            usage = {
                "input_tokens": raw_usage.get("prompt_tokens", 0),
                "output_tokens": raw_usage.get("completion_tokens", 0),
                "total_tokens": raw_usage.get("total_tokens", 0),
            }
            model = data.get("model", DEEPSEEK_MODEL)

            # Accumulate token usage
            self._total_tokens_used["input"] += usage["input_tokens"]
            self._total_tokens_used["output"] += usage["output_tokens"]

            log.info(
                "deepseek_api_call",
                model=model,
                input_tokens=usage["input_tokens"],
                output_tokens=usage["output_tokens"],
                duration_s=round(duration, 3),
            )

            return AIResponse(content=choice, usage=usage, model=model)

        return await _call()

    @property
    def total_tokens_used(self) -> dict[str, int]:
        return dict(self._total_tokens_used)

    def estimate_monthly_cost(self) -> float:
        """Estimate cost in USD based on accumulated token usage.

        DeepSeek V3: $0.27/MTok input, $1.10/MTok output.
        """
        input_cost = (self._total_tokens_used["input"] / 1_000_000) * _INPUT_COST_PER_MTOK
        output_cost = (self._total_tokens_used["output"] / 1_000_000) * _OUTPUT_COST_PER_MTOK
        return round(input_cost + output_cost, 6)
