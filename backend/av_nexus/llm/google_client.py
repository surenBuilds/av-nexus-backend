"""Google Gemini (GenerateContent) client (provider via settings; no keys in code).

Implements the same `LLMClient` protocol as the OpenAI client. Requires the Google
API key; the model is passed as a full model name (e.g. `gemini-2.0-flash`).
"""

from __future__ import annotations

import httpx

from av_nexus.config import settings
from av_nexus.llm.base import LLMResult, ProviderError

API_URL = "https://generativelanguage.googleapis.com/v1beta/models"


class GoogleClient:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        timeout: int | None = None,
    ) -> None:
        self.api_key = api_key or settings.llm_api_key
        self.model = model or settings.llm_model or "gemini-2.0-flash"
        self.timeout = timeout or settings.llm_timeout_seconds
        if not self.api_key:
            raise ProviderError("AVNEXUS_LLM__API_KEY is not set; cannot use Google provider")

    def complete(self, system: str, user: str) -> LLMResult:
        url = f"{API_URL}/{self.model}:generateContent"
        body = {
            "contents": [{"parts": [{"text": f"{system}\n\n{user}"}]}],
        }
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(
                url,
                headers={"x-goog-api-key": self.api_key},
                json=body,
            )
            if resp.status_code != 200:
                raise ProviderError(f"Google Gemini returned {resp.status_code}: {resp.text[:300]}")
            payload = resp.json()
            candidates = payload.get("candidates") or []
            content = ""
            if candidates:
                parts = candidates[0].get("content", {}).get("parts") or []
                content = "".join(p.get("text", "") for p in parts)
            usage = payload.get("usageMetadata", {})
            return LLMResult(
                content=content,
                tokens_in=int(usage.get("promptTokenCount", 0)),
                tokens_out=int(usage.get("candidatesTokenCount", 0)),
                provider="google",
            )
