"""A counting wrapper around an LLMClient that accumulates tokens/metadata.

The executor injects this into AgentContext so every provider call an agent makes
is reflected in the owning AgentRun's token counters. It never alters output.
"""

from __future__ import annotations

from typing import cast

from av_nexus.llm.base import LLMResult


class MeteredLLM:
    """Wraps an LLMClient, summing tokens and provider info per execution."""

    def __init__(self, inner: object) -> None:
        self.inner = inner
        self.tokens_in = 0
        self.tokens_out = 0
        self.calls = 0

    def complete(self, system: str, user: str) -> LLMResult:
        result = self.inner.complete(system, user)  # type: ignore[attr-defined]
        if getattr(result, "provider", "mock") != "mock":
            self.tokens_in += int(getattr(result, "tokens_in", 0))
            self.tokens_out += int(getattr(result, "tokens_out", 0))
            self.calls += 1
        return cast(LLMResult, result)
