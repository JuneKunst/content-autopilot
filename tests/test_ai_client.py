"""Tests for DeepSeek AI client and prompt loader."""

import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from content_autopilot.ai.client import (
    AIResponse,
    DeepSeekAuthError,
    DeepSeekClient,
    DeepSeekRateLimitError,
    DeepSeekServerError,
)
from content_autopilot.ai.prompts import PromptLoader


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_api_response(
    content: str = "Hello",
    input_tokens: int = 10,
    output_tokens: int = 20,
    model: str = "deepseek-chat",
    status_code: int = 200,
) -> MagicMock:
    """Build a mock httpx.Response for DeepSeek API."""
    body = {
        "choices": [{"message": {"content": content}}],
        "usage": {
            "prompt_tokens": input_tokens,
            "completion_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        },
        "model": model,
    }
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = status_code
    mock_resp.json.return_value = body
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


# ---------------------------------------------------------------------------
# DeepSeekClient.chat() — happy path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_chat_returns_ai_response():
    """chat() returns an AIResponse with correct fields."""
    client = DeepSeekClient(api_key="test-key")
    mock_resp = _make_api_response(content="Test answer", input_tokens=5, output_tokens=15)

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
        result = await client.chat("What is 2+2?")

    assert isinstance(result, AIResponse)
    assert result.content == "Test answer"
    assert result.usage["input_tokens"] == 5
    assert result.usage["output_tokens"] == 15
    assert result.usage["total_tokens"] == 20
    assert result.model == "deepseek-chat"


@pytest.mark.asyncio
async def test_chat_with_system_prompt():
    """chat() includes system prompt in messages when provided."""
    client = DeepSeekClient(api_key="test-key")
    mock_resp = _make_api_response(content="OK")
    captured_payload = {}

    async def fake_post(url, *, json=None, headers=None, **kwargs):
        captured_payload.update(json or {})
        return mock_resp

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=fake_post):
        await client.chat("User msg", system_prompt="You are helpful.")

    messages = captured_payload["messages"]
    assert messages[0] == {"role": "system", "content": "You are helpful."}
    assert messages[1] == {"role": "user", "content": "User msg"}


# ---------------------------------------------------------------------------
# Token tracking
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_token_tracking_accumulates():
    """total_tokens_used accumulates across multiple calls."""
    client = DeepSeekClient(api_key="test-key")

    mock_resp1 = _make_api_response(input_tokens=10, output_tokens=20)
    mock_resp2 = _make_api_response(input_tokens=30, output_tokens=40)

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=[mock_resp1, mock_resp2]):
        await client.chat("First")
        await client.chat("Second")

    assert client.total_tokens_used["input"] == 40
    assert client.total_tokens_used["output"] == 60


# ---------------------------------------------------------------------------
# estimate_monthly_cost()
# ---------------------------------------------------------------------------

def test_estimate_monthly_cost_zero_when_no_calls():
    client = DeepSeekClient(api_key="test-key")
    assert client.estimate_monthly_cost() == 0.0


def test_estimate_monthly_cost_calculation():
    """Cost = input * 0.27/MTok + output * 1.10/MTok."""
    client = DeepSeekClient(api_key="test-key")
    # Manually inject token counts
    client._total_tokens_used["input"] = 1_000_000   # 1 MTok → $0.27
    client._total_tokens_used["output"] = 1_000_000  # 1 MTok → $1.10
    cost = client.estimate_monthly_cost()
    assert abs(cost - 1.37) < 1e-5


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_chat_raises_auth_error_on_401():
    client = DeepSeekClient(api_key="bad-key", max_retries=1)
    mock_resp = _make_api_response(status_code=401)
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
        with pytest.raises(DeepSeekAuthError):
            await client.chat("Hello")


@pytest.mark.asyncio
async def test_chat_raises_server_error_on_500():
    client = DeepSeekClient(api_key="test-key", max_retries=1)
    mock_resp = _make_api_response(status_code=500)
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
        with pytest.raises(DeepSeekServerError):
            await client.chat("Hello")


# ---------------------------------------------------------------------------
# Retry logic
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_chat_retries_on_rate_limit_then_succeeds():
    """Retries on 429 and succeeds on the third attempt."""
    client = DeepSeekClient(api_key="test-key", max_retries=3)

    rate_limit_resp = _make_api_response(status_code=429)
    rate_limit_resp.raise_for_status = MagicMock()
    success_resp = _make_api_response(content="Finally!", input_tokens=5, output_tokens=5)

    call_count = 0

    async def flaky_post(url, *, json=None, headers=None, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            return rate_limit_resp
        return success_resp

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=flaky_post):
        # Patch tenacity wait to avoid actual sleeping in tests
        with patch("tenacity.wait_exponential.__call__", return_value=0):
            result = await client.chat("Hello")

    assert result.content == "Finally!"
    assert call_count == 3


# ---------------------------------------------------------------------------
# PromptLoader
# ---------------------------------------------------------------------------

def test_prompt_loader_render_basic():
    """PromptLoader renders a simple template correctly."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Write a test template
        tpl_path = Path(tmpdir) / "hello.txt"
        tpl_path.write_text("Hello, {{ name }}!")

        loader = PromptLoader(templates_dir=tmpdir)
        result = loader.render("hello.txt", name="World")

    assert result == "Hello, World!"


def test_prompt_loader_render_missing_template_raises():
    """PromptLoader raises TemplateNotFound for missing templates."""
    from jinja2 import TemplateNotFound

    with tempfile.TemporaryDirectory() as tmpdir:
        loader = PromptLoader(templates_dir=tmpdir)
        with pytest.raises(TemplateNotFound):
            loader.render("nonexistent.txt")


def test_prompt_loader_load_summarize_prompt():
    """load_summarize_prompt passes correct variables to template."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tpl = Path(tmpdir) / "summarize.txt"
        tpl.write_text(
            "Summarize: {{ source_title }} at {{ source_url }}\n{{ source_content }}"
        )

        loader = PromptLoader(templates_dir=tmpdir)
        result = loader.load_summarize_prompt(
            source_content="Some content",
            source_url="https://example.com",
            source_title="Example Article",
        )

    assert "Example Article" in result
    assert "https://example.com" in result
    assert "Some content" in result


def test_prompt_loader_load_humanize_prompt():
    """load_humanize_prompt passes correct variables to template."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tpl = Path(tmpdir) / "humanize.txt"
        tpl.write_text(
            "Humanize: {{ summary_ko }} | {{ source_title }} | {{ persona_config.name }}"
        )

        loader = PromptLoader(templates_dir=tmpdir)
        result = loader.load_humanize_prompt(
            summary_ko="한국어 요약",
            source_url="https://example.com",
            source_title="Test Title",
            persona_config={"name": "tech_writer"},
        )

    assert "한국어 요약" in result
    assert "Test Title" in result
    assert "tech_writer" in result
