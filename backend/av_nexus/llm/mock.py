"""Deterministic offline LLM stand-in for tests/dev with no provider."""

from __future__ import annotations

from av_nexus.llm.base import LLMResult


class MockLLM:
    """Returns a structured, deterministic 'no provider' response.

    Never impersonates a real model: the system text is prefixed with a clear
    statement that the provider is unavailable. Agents rely on their
    deterministic branches when this is active.
    """

    def complete(self, system: str, user: str) -> LLMResult:
        notice = (
            "[mock] LLM provider offline (AVNEXUS_LLM__PROVIDER is 'off'). "
            "No real model output. The caller must fall back to its "
            "deterministic computation and keep mode='deterministic'.\n"
        )
        return LLMResult(
            content=f"{notice}system: {system[:400]}\nuser: {user[:400]}",
            tokens_in=0,
            tokens_out=0,
            cost_usd=0.0,
            provider="mock",
        )
