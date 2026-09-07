"""Anthropic Messages API client (provider via settings; no keys in code).

Implements the same `LLMClient` protocol as the OpenAI client. Errors are raised as
`ProviderError` so the executor can map them to bounded retries.
"""

from __future__ import annotations

import httpx

from av_nexus.config import settings
from av_nexus.llm.base import LLMResult, ProviderError

API_URL = "https://api.anthropic.com/v1/messages"


class AnthropicClient:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        timeout: int | None = None,
    ) -> None:
        self.api_key = api_key or settings.llm_api_key
        self.model = model or settings.llm_model or "claude-sonnet-4-5"
        self.timeout = timeout or settings.llm_timeout_seconds
        if not self.api_key:
            raise ProviderError("AVNEXUS_LLM__API_KEY is not set; cannot use Anthropic provider")

    def complete(self, system: str, user: str) -> LLMResult:
        body = {
            "model": self.model,
            "max_tokens": 1024,
            "temperature": 0.3,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(
                API_URL,
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json=body,
            )
            if resp.status_code != 200:
                raise ProviderError(f"Anthropic returned {resp.status_code}: {resp.text[:300]}")
            payload = resp.json()
            parts = payload.get("content") or []
            content = "".join(p.get("text", "") for p in parts if p.get("type") == "text")
            usage = payload.get("usage", {})
            return LLMResult(
                content=content,
                tokens_in=int(usage.get("input_tokens", 0)),
                tokens_out=int(usage.get("output_tokens", 0)),
                provider="anthropic",
            )
