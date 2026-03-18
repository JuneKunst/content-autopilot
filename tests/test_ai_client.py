import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from content_autopilot.ai.client import (
    AIResponse,
    AIClient,
    AIProvider,
)
from content_autopilot.ai.prompts import PromptLoader


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_openai_like_response(
    content: str = "Hello",
    input_tokens: int = 10,
    output_tokens: int = 20,
    model: str = "gpt-4o-mini",
    status_code: int = 200,
) -> MagicMock:
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


@pytest.mark.asyncio
async def test_chat_returns_ai_response():
    client = AIClient(max_retries=1)
    client._api_keys[AIProvider.OPENAI] = "openai-key"
    mock_resp = _make_openai_like_response(
        content="Test answer",
        input_tokens=5,
        output_tokens=15,
        model="gpt-4o-mini",
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
        result = await client.chat("What is 2+2?")

    assert isinstance(result, AIResponse)
    assert result.content == "Test answer"
    assert result.usage["input_tokens"] == 5
    assert result.usage["output_tokens"] == 15
    assert result.usage["total_tokens"] == 20
    assert result.model == "gpt-4o-mini"
    assert result.provider == "openai"


@pytest.mark.asyncio
async def test_chat_falls_back_to_gemini_on_openai_auth_error():
    client = AIClient(
        primary=AIProvider.OPENAI,
        fallbacks=[AIProvider.GEMINI],
        max_retries=1,
    )
    client._api_keys[AIProvider.OPENAI] = "bad-openai-key"
    client._api_keys[AIProvider.GEMINI] = "gemini-key"

    openai_auth_error = _make_openai_like_response(status_code=401)
    gemini_success = _make_openai_like_response(
        content="Gemini answer",
        model="gemini-2.0-flash-lite",
    )
    captured_payload = {}
    called_urls: list[str] = []
    call_count = 0

    async def fake_post(url, *, json=None, headers=None, **kwargs):
        nonlocal call_count
        call_count += 1
        called_urls.append(url)
        captured_payload["headers"] = headers
        if call_count == 1:
            return openai_auth_error
        return gemini_success

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=fake_post):
        result = await client.chat("User msg", system_prompt="You are helpful.")

    assert result.content == "Gemini answer"
    assert result.provider == "gemini"
    assert called_urls[0] == "https://api.openai.com/v1/chat/completions"
    assert called_urls[1] == "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
    assert captured_payload["headers"]["Authorization"] == "Bearer gemini-key"


@pytest.mark.asyncio
async def test_chat_raises_runtime_error_when_all_provider_keys_missing():
    client = AIClient(
        primary=AIProvider.OPENAI,
        fallbacks=[AIProvider.GEMINI, AIProvider.CLAUDE],
        max_retries=1,
    )
    client._api_keys[AIProvider.OPENAI] = ""
    client._api_keys[AIProvider.GEMINI] = ""
    client._api_keys[AIProvider.CLAUDE] = ""

    with pytest.raises(RuntimeError, match="No AI provider available"):
        await client.chat("Hello")

@pytest.mark.asyncio
async def test_call_claude_uses_expected_headers_and_payload_format():
    client = AIClient(primary=AIProvider.CLAUDE, max_retries=1)
    client._api_keys[AIProvider.CLAUDE] = "claude-key"
    captured = {}

    claude_body = {
        "content": [{"text": "Claude says hi"}],
        "usage": {"input_tokens": 11, "output_tokens": 22},
    }
    claude_resp = MagicMock(spec=httpx.Response)
    claude_resp.status_code = 200
    claude_resp.json.return_value = claude_body
    claude_resp.raise_for_status = MagicMock()

    async def fake_post(url, *, json=None, headers=None, **kwargs):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        return claude_resp

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=fake_post):
        result = await client.chat("Ping", system_prompt="System context")

    assert result.content == "Claude says hi"
    assert result.provider == "claude"
    assert captured["url"] == "https://api.anthropic.com/v1/messages"
    assert captured["headers"]["x-api-key"] == "claude-key"
    assert "Authorization" not in captured["headers"]
    assert captured["json"]["messages"] == [{"role": "user", "content": "Ping"}]
    assert captured["json"]["system"] == "System context"


@pytest.mark.asyncio
async def test_token_tracking_accumulates():
    client = AIClient(max_retries=1)
    client._api_keys[AIProvider.OPENAI] = "openai-key"

    mock_resp1 = _make_openai_like_response(input_tokens=10, output_tokens=20)
    mock_resp2 = _make_openai_like_response(input_tokens=30, output_tokens=40)

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=[mock_resp1, mock_resp2]):
        await client.chat("First")
        await client.chat("Second")

    assert client.total_tokens_used["input"] == 40
    assert client.total_tokens_used["output"] == 60


def test_estimate_monthly_cost_zero_when_no_calls():
    client = AIClient()
    assert client.estimate_monthly_cost() == 0.0


def test_estimate_monthly_cost_calculation():
    client = AIClient()
    client._total_tokens["input"] = 1_000_000
    client._total_tokens["output"] = 1_000_000
    cost = client.estimate_monthly_cost(provider=AIProvider.OPENAI)
    assert abs(cost - 0.75) < 1e-5


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
