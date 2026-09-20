"""OpenAI-compatible HTTP LLM client (provider via settings; no keys in code).

Works with any OpenAI-compatible chat completions endpoint — OpenAI itself,
or another provider that speaks the same API (e.g. Groq's
https://api.groq.com/openai/v1). Point AVNEXUS_LLM__BASE_URL at the
provider's endpoint and AVNEXUS_LLM__API_KEY at its key; nothing
provider-specific is hardcoded here.
"""

from __future__ import annotations

from urllib.parse import urlparse

import httpx

from av_nexus.config import settings
from av_nexus.llm.base import LLMResult, ProviderError


class OpenAIClient:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        timeout: int | None = None,
        require_api_key: bool = True,
    ) -> None:
        self.api_key = api_key or settings.llm_api_key
        self.model = model or settings.llm_model
        self.base_url = base_url or settings.llm_base_url
        self.timeout = timeout or settings.llm_timeout_seconds
        if require_api_key and not self.api_key:
            raise ProviderError("AVNEXUS_LLM__API_KEY is not set; cannot use LLM provider")

    def _provider_label(self) -> str:
        # Report which endpoint actually answered, not a hardcoded "openai" —
        # e.g. api.groq.com should show up as "groq", not be mislabeled.
        host = urlparse(self.base_url).hostname or ""
        if "groq" in host:
            return "groq"
        if "openai" in host:
            return "openai"
        return host or "openai_compatible"

    def complete(self, system: str, user: str) -> LLMResult:
        url = f"{self.base_url.rstrip('/')}/chat/completions"
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.3,
        }
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(url, headers={"Authorization": f"Bearer {self.api_key}"}, json=body)
            if resp.status_code != 200:
                raise ProviderError(f"LLM provider returned {resp.status_code}: {resp.text[:300]}")
            payload = resp.json()
            content = payload["choices"][0]["message"]["content"]
            usage = payload.get("usage", {})
            return LLMResult(
                content=content,
                tokens_in=int(usage.get("prompt_tokens", 0)),
                tokens_out=int(usage.get("completion_tokens", 0)),
                provider=self._provider_label(),
            )
