"""LLM client abstraction.

AV Nexus never depends on a specific vendor SDK. `LLMClient` is a protocol;
OpenAI-compatible HTTP is implemented in `openai_client`, and `MockLLM` (offline,
deterministic) is the default so the system runs with no keys and no network.

Mode semantics (must never be faked):
- mode="llm"           → output was produced by a real model provider.
- mode="deterministic" → output was computed offline by this codebase.
Agents always report their mode in AgentResult.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass
class LLMResult:
    content: str
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    provider: str = "mock"


@runtime_checkable
class LLMClient(Protocol):
    def complete(self, system: str, user: str) -> LLMResult: ...


class ProviderError(RuntimeError):
    """Raised when an LLM provider fails; callers map to structured failures."""
