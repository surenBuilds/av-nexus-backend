"""Agent contract: AgentContext, AgentResult, BaseAgent.

Guarantees honored by every agent:
- Agents are pure: produce structured outputs; never mutate DB, never move money,
  never reach external services. The orchestrator persists results.
- Every result reports mode ("llm" only if the reasoning fields were genuinely
  produced by a real model provider and passed schema validation; "deterministic"
  otherwise — the codebase never fakes a provider).
- confidence/assumptions/sources/risks are required and consistent.

Validated LLM output (used by Strategy, Critic, Validator):
- `BaseAgent._structured_llm` calls a real provider, parses the response
  (tolerating markdown fences), and validates it against a pydantic schema.
  Schema/parse failures raise `AgentExecutionError(retryable=False)` so the
  executor FAILS the step — output is never silently replaced with template text.
- When no real provider is present (offline mock), it returns None and the agent
  publishes an honest "not generated / no_llm_provider" marker with
  mode="deterministic".
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, cast

from pydantic import BaseModel, Field, ValidationError

from av_nexus.llm.base import LLMClient


def _parse_json_text(text: str) -> Any:
    """Parse a JSON payload, tolerating a markdown-code-fence wrapper."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[A-Za-z0-9_-]*\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned).strip()
    return json.loads(cleaned)


@dataclass
class AgentContext:
    org_id: uuid.UUID
    user_id: uuid.UUID | None = None
    company_id: uuid.UUID | None = None
    llm: LLMClient | None = None
    # Inputs handed to the task (structured, from prior stages of a pipeline).
    # Typed loosely: agents receive runtime JSON; outputs are strictly validated
    # in AgentResult.
    inputs: dict[str, Any] = field(default_factory=dict)
    data: dict[str, Any] = field(default_factory=dict)
    # Phase 2A execution affordances (optional; absent in pure unit runs).
    memory: object | None = None
    knowledge: object | None = None
    tools: object | None = None
    execution_mode: str = "mock"

    def run_tool(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        """Permission-checked tool execution, if a tool registry is attached.

        Returns {"ok": bool, "result": object, "error": str | None, "name": str}.
        """
        if self.tools is None or not hasattr(self.tools, "execute"):
            return {"ok": False, "name": name, "error": "no tool registry", "result": None}
        execute = cast(Any, self.tools).execute
        return cast(dict[str, Any], execute(name, args))


class AgentResult(BaseModel):
    result: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(ge=0.0, le=1.0)
    assumptions: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    next_recommended_agents: list[str] = Field(default_factory=list)
    mode: str = "deterministic"  # "llm" | "deterministic"

    @classmethod
    def deterministic(
        cls,
        result: dict[str, Any],
        *,
        confidence: float,
        assumptions: list[str],
        sources: list[str],
        risks: list[str] | None = None,
        next_recommended_agents: list[str] | None = None,
    ) -> AgentResult:
        return cls(
            result=result,
            confidence=round(max(0.0, min(1.0, confidence)), 3),
            assumptions=assumptions,
            sources=sources,
            risks=risks if risks is not None else [],
            next_recommended_agents=(
                next_recommended_agents if next_recommended_agents is not None else []
            ),
            mode="deterministic",
        )

    @classmethod
    def llm(
        cls,
        result: dict[str, Any],
        *,
        schema: type[BaseModel],
        confidence: float,
        assumptions: list[str],
        sources: list[str],
        risks: list[str] | None = None,
        next_recommended_agents: list[str] | None = None,
    ) -> AgentResult:
        """Publish output that a real provider produced and which passed validation.

        `result` is the complete dict the agent publishes; it is validated against
        `schema` before publishing (`schema.model_validate(result)`), so malformed
        or schema-violating provider output FAILS the step instead of being
        persisted. mode is set to "llm": agents must only call this when at least
        the reasoning fields came from a real model provider.
        """
        try:
            schema.model_validate(result)
        except ValidationError as exc:
            raise AgentExecutionError(
                f"llm result failed schema validation: {exc}", retryable=False
            ) from exc
        return cls(
            result=result,
            confidence=round(max(0.0, min(1.0, confidence)), 3),
            assumptions=assumptions,
            sources=sources,
            risks=risks if risks is not None else [],
            next_recommended_agents=(
                next_recommended_agents if next_recommended_agents is not None else []
            ),
            mode="llm",
        )


class AgentExecutionError(RuntimeError):
    """Structured agent failure. retryable=True → kernel may retry with backoff."""

    def __init__(self, message: str, *, retryable: bool = True) -> None:
        super().__init__(message)
        self.retryable = retryable


class BaseAgent:
    agent_id: str = "base"
    name: str = "Base Agent"
    role: str = "Specialist"
    description: str = ""
    capabilities: list[str] = []
    tools: list[str] = []
    permissions: list[str] = []

    async def run(self, ctx: AgentContext, goal: str) -> AgentResult:  # pragma: no cover
        raise NotImplementedError

    def _structured_llm(
        self,
        ctx: AgentContext,
        system: str,
        user: str,
        schema: type[BaseModel],
    ) -> dict[str, Any] | None:
        """Call a real provider and return schema-validated output, or None.

        - No client / offline mock client (provider == "mock") → None: the agent
          must then publish an honest "not generated" marker and keep
          mode="deterministic".
        - Real provider response that fails to parse or fails pydantic validation
          → `AgentExecutionError(retryable=False)`: the executor FAILS the step.
          No template fallback is ever substituted for real reasoning.
        - Provider transport errors propagate as `ProviderError`; the executor
          retries them and FAILs on exhaustion.
        """
        client = getattr(ctx, "llm", None)
        if client is None:
            return None
        try:
            out = client.complete(system, user)
        except Exception as exc:
            from av_nexus.llm.base import ProviderError

            if isinstance(exc, ProviderError):
                raise
            raise ProviderError(str(exc)) from exc
        if getattr(out, "provider", "mock") == "mock":
            return None
        try:
            parsed = _parse_json_text(out.content)
            validated = schema.model_validate(parsed)
        except ValidationError as exc:
            raise AgentExecutionError(
                f"llm output failed schema validation: {exc}", retryable=False
            ) from exc
        except ValueError as exc:
            raise AgentExecutionError(
                f"llm output was not parseable JSON: {exc}", retryable=False
            ) from exc
        return validated.model_dump()
