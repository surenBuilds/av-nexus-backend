"""Build the active LLM client from settings (swappable provider).

Mode semantics (honest by construction):
- EXECUTION_MODE=mock  -> always `MockLLM` regardless of provider settings. Agents
  report mode="deterministic" and nothing pretends to come from a real model.
- EXECUTION_MODE=live  -> a real provider client is required (openai, anthropic,
  google, openai_compatible). Missing key at construction raises ProviderError.
"""

from __future__ import annotations

from av_nexus.config import settings
from av_nexus.llm.base import LLMClient
from av_nexus.llm.mock import MockLLM


def build_llm_client() -> LLMClient:
    if settings.execution_mode.strip().lower() == "mock":
        return MockLLM()
    return _build_real_client()


def _build_real_client() -> LLMClient:
    provider = settings.llm_provider.strip().lower()
    if provider == "off":
        return MockLLM()
    if provider == "anthropic":
        from av_nexus.llm.anthropic_client import AnthropicClient

        return AnthropicClient()
    if provider == "google":
        from av_nexus.llm.google_client import GoogleClient

        return GoogleClient()
    if provider == "openai_compatible":
        from av_nexus.llm.openai_client import OpenAIClient

        return OpenAIClient(base_url=settings.llm_base_url, require_api_key=False)
    if provider == "openai":
        from av_nexus.llm.openai_client import OpenAIClient

        return OpenAIClient()
    # Unknown provider name -> fall back to the deterministic mock and record why.
    return MockLLM()
