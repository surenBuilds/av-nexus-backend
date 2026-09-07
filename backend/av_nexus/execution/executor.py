"""Agent execution engine.

`AgentExecutor` turns a `BaseAgent` plan into a persisted, observable execution:
- Builds an `AgentContext` with LLM (metered), tools (permission-checked), memory
  and knowledge affordances.
- Runs the agent with bounded retries (retryable: provider failure / timeout /
  rate-limit style errors; non-retryable: invalid output, permission denials,
  invalid inputs).
- Enforces a per-step timeout.
- Persists an `AgentRun` row with tokens/cost/duration and a trace that includes
  every tool call and the attempt count.

The executor never changes the agent's reported `mode` and never fabricates
results. Structured reasoning fields are produced by the agents themselves
through `BaseAgent._structured_llm` (validated against pydantic schemas); the
executor only honors schema-validation failures as non-retryable FAILED steps.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import Coroutine
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from av_nexus.agents.base import AgentContext, AgentExecutionError, AgentResult, BaseAgent
from av_nexus.config import settings
from av_nexus.llm.base import ProviderError
from av_nexus.llm.metered import MeteredLLM
from av_nexus.models.agents import Agent, AgentRun, Task
from av_nexus.models.enums import TaskStatus
from av_nexus.models.identity import Organization, User
from av_nexus.tools.registry import build_tool_registry


@dataclass
class Execution:
    result: AgentResult
    attempts: int = 1
    duration_ms: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    llm_used: bool = False
    run_id: uuid.UUID | None = None


class ExecutionError(RuntimeError):
    """Workflow-facing execution failure. `retryable` controls policy at the runner."""

    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


class AgentExecutor:
    def __init__(
        self,
        session: Session,
        agent_impl: BaseAgent,
        agent_row: Agent,
        llm: MeteredLLM,
        *,
        company_id: uuid.UUID | None = None,
    ) -> None:
        self.session = session
        self.agent = agent_impl
        self.agent_row = agent_row
        self.llm = llm
        self.company_id = company_id

    # -- prompt --------------------------------------------------------------
    def build_system_prompt(self, goal: str, org: Organization) -> str:
        tools = ", ".join(self.agent.tools) or "none"
        perms = ", ".join(self.agent.permissions) or "none"
        return (
            f"You are {self.agent.name} ({self.agent.agent_id}). Role: {self.agent.role}.\n"
            f"Description: {self.agent.description}\n"
            f"Declared tools: {tools}\n"
            f"Permissions: {perms}\n"
            f"Organization: {org.name} (org_id {org.id})\n"
            f"Execution mode: {settings.execution_mode} — report mode='deterministic' unless "
            "your output was genuinely produced by a model provider.\n"
            f"Constraints: never claim facts without a listed source; never perform "
            "external/irreversible actions; respond concisely in JSON.\n"
            f"Objective: {goal}"
        )

    # -- context -------------------------------------------------------------
    def build_context(
        self,
        task: Task,
        org: Organization,
        user: User,
        library: dict[str, Any] | None = None,
    ) -> AgentContext:
        tools = build_tool_registry(
            self.session,
            org.id,
            self.agent_row.permissions_json or [],
            self.company_id,
        )
        return AgentContext(
            org_id=org.id,
            user_id=user.id,
            company_id=self.company_id,
            llm=self.llm,
            inputs=dict(task.input_json or {}),
            data=self._context_data(org),
            memory=library.get("memory") if library else None,
            knowledge=library.get("knowledge") if library else None,
            tools=tools,
            execution_mode=settings.execution_mode,
        )

    def _context_data(self, org: Organization) -> dict[str, object]:
        from av_nexus.models.opportunities import Opportunity

        opps = list(
            self.session.scalars(
                select(Opportunity)
                .where(Opportunity.org_id == org.id)
                .order_by(Opportunity.opportunity_score.desc())
            )
        )
        return {
            "opportunities": [
                {
                    "title": o.title,
                    "opportunity_score": o.opportunity_score,
                    "category": o.category,
                    "status": o.status,
                }
                for o in opps
            ]
        }

    # -- execution ------------------------------------------------------------
    async def execute(self, task: Task, org: Organization, user: User) -> Execution:
        run = AgentRun(agent_id=self.agent_row.id, task_id=task.id, status=TaskStatus.RUNNING.value)
        self.session.add(run)
        self.session.flush()

        ctx = self.build_context(task, org, user)
        started = time.monotonic()

        result: AgentResult | None = None
        last_error: str | None = None
        attempts = 0
        for attempt in range(settings.agent_retries + 1):
            attempts = attempt + 1
            try:
                result = await self._run_with_timeout(ctx, task.goal)
                break
            except TimeoutError:
                last_error = f"agent step exceeded {settings.agent_step_timeout_seconds}s timeout"
                if attempt < settings.agent_retries:
                    await asyncio.sleep(0.05 * (attempt + 1))
            except AgentExecutionError as exc:
                last_error = f"{exc}"
                if not exc.retryable or attempt >= settings.agent_retries:
                    break
                await asyncio.sleep(0.05 * (attempt + 1))
            except ProviderError as exc:
                last_error = f"provider error: {exc}"
                if attempt < settings.agent_retries:
                    await asyncio.sleep(0.05 * (attempt + 1))

        duration_ms = int((time.monotonic() - started) * 1000)
        tool_calls = list(getattr(ctx.tools, "calls", []))

        llm_used = getattr(self.llm, "calls", 0) > 0
        run.tokens_in = int(getattr(self.llm, "tokens_in", 0))
        run.tokens_out = int(getattr(self.llm, "tokens_out", 0))
        run.trace_json = {
            "mode_platform": settings.execution_mode,
            "llm_used": llm_used,
            "attempts": attempts,
            "duration_ms": duration_ms,
            "tool_calls": tool_calls,
        }

        if result is not None:
            self._validate(result)
            run.status = TaskStatus.COMPLETED.value
            run.ended_at = _now()
            self.session.commit()
            return Execution(
                result=result,
                attempts=attempts,
                duration_ms=duration_ms,
                tokens_in=run.tokens_in,
                tokens_out=run.tokens_out,
                cost_usd=run.cost_usd,
                tool_calls=tool_calls,
                llm_used=llm_used,
                run_id=run.id,
            )

        run.status = TaskStatus.FAILED.value
        run.error = last_error or "unknown agent failure"
        run.ended_at = _now()
        self.session.commit()
        retryable = bool(last_error and ("timeout" in last_error or "provider" in last_error))
        raise ExecutionError(run.error, retryable=retryable)

    async def _run_with_timeout(self, ctx: AgentContext, goal: str) -> AgentResult:
        coro: Coroutine[Any, Any, AgentResult] = self.agent.run(ctx, goal)
        return await asyncio.wait_for(coro, timeout=settings.agent_step_timeout_seconds)

    @staticmethod
    def _validate(result: AgentResult) -> None:
        if not 0.0 <= result.confidence <= 1.0:
            raise ExecutionError("agent produced out-of-range confidence", retryable=False)
        if result.mode not in ("deterministic", "llm"):
            raise ExecutionError(f"agent reported unknown mode: {result.mode}", retryable=False)
        if not isinstance(result.result, dict):
            raise ExecutionError("agent result.output must be a dict", retryable=False)


from sqlalchemy import select  # noqa: E402  (used by _context_data)


def _now() -> Any:
    from datetime import UTC, datetime

    return datetime.now(UTC)
