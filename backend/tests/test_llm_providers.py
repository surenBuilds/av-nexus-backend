"""Tests for LLM provider selection and honest provider labeling.

Groq reuses OpenAIClient (Groq's API is OpenAI-compatible) rather than a
bespoke client, so these tests cover: (1) the factory wires "groq" to the
right default base_url without clobbering an explicit override, and (2) the
client reports which endpoint actually answered instead of a hardcoded
"openai" label — a Groq response must say "groq", not "openai".
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from av_nexus.config import settings
from av_nexus.llm.factory import build_llm_client
from av_nexus.llm.openai_client import OpenAIClient


@pytest.fixture(autouse=True)
def _restore_llm_settings():
    original = (
        settings.execution_mode,
        settings.llm_provider,
        settings.llm_base_url,
        settings.llm_api_key,
    )
    yield
    (
        settings.execution_mode,
        settings.llm_provider,
        settings.llm_base_url,
        settings.llm_api_key,
    ) = original


def test_factory_defaults_groq_to_groq_base_url() -> None:
    settings.execution_mode = "live"
    settings.llm_provider = "groq"
    settings.llm_base_url = "https://api.openai.com/v1"  # untouched default
    settings.llm_api_key = "test-groq-key"

    client = build_llm_client()

    assert isinstance(client, OpenAIClient)
    assert client.base_url == "https://api.groq.com/openai/v1"


def test_factory_respects_explicit_base_url_override_for_groq() -> None:
    settings.execution_mode = "live"
    settings.llm_provider = "groq"
    settings.llm_base_url = "https://my-groq-proxy.internal/v1"
    settings.llm_api_key = "test-groq-key"

    client = build_llm_client()

    assert client.base_url == "https://my-groq-proxy.internal/v1"


def test_openai_client_labels_groq_responses_as_groq_not_openai() -> None:
    client = OpenAIClient(
        api_key="k",
        base_url="https://api.groq.com/openai/v1",
        model="llama-3.3-70b-versatile",
    )

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "hello"}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
    }
    with patch("httpx.Client.post", return_value=mock_response):
        result = client.complete("system", "user")

    assert result.provider == "groq"
    assert result.content == "hello"


def test_openai_client_still_labels_real_openai_as_openai() -> None:
    client = OpenAIClient(api_key="k", base_url="https://api.openai.com/v1", model="gpt-4o-mini")

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "hi"}}],
        "usage": {},
    }
    with patch("httpx.Client.post", return_value=mock_response):
        result = client.complete("system", "user")

    assert result.provider == "openai"


def test_openai_client_always_sends_an_explicit_max_tokens() -> None:
    # Regression test: an unset max_tokens let a real provider (Groq) cut a
    # verbose JSON response off mid-string, which then failed to parse —
    # not a transport error, a silent truncation. This asserts the request
    # body always carries a real, non-zero cap.
    client = OpenAIClient(api_key="k", base_url="https://api.groq.com/openai/v1", model="m")
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"choices": [{"message": {"content": "{}"}}], "usage": {}}
    with patch("httpx.Client.post", return_value=mock_response) as mock_post:
        client.complete("system", "user")
    sent_body = mock_post.call_args.kwargs["json"]
    assert sent_body["max_tokens"] == settings.llm_max_tokens
    assert sent_body["max_tokens"] > 0
