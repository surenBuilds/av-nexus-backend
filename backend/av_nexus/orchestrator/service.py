"""Orchestrator service: task lifecycle, agent execution, pipeline orchestration.

DB-touching orchestration glue. Holds no external tool execution; agents never
do side effects. Approval gates stop work at level ≥3.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import CursorResult, select, update
from sqlalchemy.orm import Session

from av_nexus.agents.base import AgentContext, AgentExecutionError, AgentResult
from av_nexus.agents.registry import AgentRegistry
from av_nexus.config import settings
from av_nexus.llm.base import LLMClient
from av_nexus.models.agents import Agent, AgentMessage, AgentRun, Task, TaskDependency
from av_nexus.models.decisions import Approval, Decision
from av_nexus.models.enums import (
    ApprovalStatus,
    DecisionStatus,
    DecisionType,
    EntityType,
    MessageType,
    Priority,
    TaskStatus,
)
from av_nexus.models.identity import Organization, User
from av_nexus.orchestrator import kernel
from av_nexus.orchestrator.pipelines import describe_pipeline, plan_pipeline


class OrchestratorService:
    def __init__(self, session: Session, registry: AgentRegistry, llm: LLMClient) -> None:
        self.session = session
        self.registry = registry
        self.llm = llm

    # -- registry persistence ------------------------------------------------
    def sync_agent_registry(self) -> int:
        existing = {a.agent_id: a for a in self.session.scalars(select(Agent))}
        created = 0
        for agent in self.registry.all():
            row = existing.get(agent.agent_id)
            if row is None:
                self.session.add(
                    Agent(
                        agent_id=agent.agent_id,
                        name=agent.name,
                        role=agent.role,
                        description=agent.description,
                        capabilities_json=agent.capabilities,
                        tools_json=agent.tools,
                        permissions_json=agent.permissions,
                    )
                )
                created += 1
        self.session.commit()
        return created

    # -- tasks ---------------------------------------------------------------
    def create_task(
        self,
        org: Organization,
        user: User,
        title: str,
        goal: str,
        *,
        description: str = "",
        owner_agent_id: uuid.UUID | None = None,
        capability: str | None = None,
        priority: str = Priority.MEDIUM.value,
        approval_level: int = 1,
        depends_on: list[uuid.UUID] | None = None,
        input_json: dict[str, Any] | None = None,
    ) -> Task:
        if owner_agent_id is None and capability:
            agent = self._pick_agent(capability)
            if agent is not None:
                owner_agent_id = agent.id
        elif owner_agent_id is not None:
            agent_row = self.session.get(Agent, owner_agent_id)
            if agent_row is None:
                raise ValueError("Unknown owner_agent_id")
        task = Task(
            org_id=org.id,
            title=title,
            goal=goal,
            description=description,
            owner_agent_id=owner_agent_id,
            priority=priority,
            approval_level=approval_level,
            input_json=input_json,
            created_by=user.id,
        )
        self.session.add(task)
        self.session.flush()
        for dep in depends_on or []:
            self.add_dependency(task, dep)
        return task

    def add_dependency(self, task: Task, depends_on_task_id: uuid.UUID) -> TaskDependency:
        if task.id == depends_on_task_id:
            raise ValueError("A task cannot depend on itself")
        if self._would_cycle(task.id, depends_on_task_id):
            raise ValueError("Dependency would create a cycle")
        dep = TaskDependency(task_id=task.id, depends_on_task_id=depends_on_task_id)
        self.session.add(dep)
        self.session.flush()
        return dep

    def _would_cycle(self, task_id: uuid.UUID, depends_on: uuid.UUID) -> bool:
        """If `depends_on` (transitively) depends on `task_id`, adding the edge
        task_id → depends_on creates a cycle."""
        visited: set[uuid.UUID] = set()

        def reach(current: uuid.UUID) -> bool:
            if current == task_id:
                return True
            if current in visited:
                return False
            visited.add(current)
            deps = list(
                self.session.scalars(
                    select(TaskDependency).where(TaskDependency.task_id == current)
                )
            )
            for d in deps:
                if reach(d.depends_on_task_id):
                    return True
            return False

        return reach(depends_on)

    # -- single task execution ------------------------------------------------
    async def run_task(self, task: Task, org: Organization, user: User) -> dict[str, Any]:
        if task.status == TaskStatus.COMPLETED.value:
            return {"task_state": "already_completed"}
        if task.status == TaskStatus.RUNNING.value:
            raise RuntimeError("Task already running")

        agent_row = self.session.get(Agent, task.owner_agent_id) if task.owner_agent_id else None
        if agent_row is not None and not agent_row.is_active:
            agent_row = None
        if agent_row is None:
            task.status = TaskStatus.FAILED.value
            task.error = "No active owner agent; route by capability first"
            self.session.commit()
            return {"task_state": "failed", "error": task.error}

        # Approval gate for level 3+ actions.
        if task.approval_level >= 3 and task.approval_status != ApprovalStatus.APPROVED.value:
            task.status = TaskStatus.APPROVAL_REQUIRED.value
            task.approval_status = ApprovalStatus.REQUIRED.value
            self._create_approval(org, task)
            self.session.commit()
            return {
                "task_state": "approval_required",
                "message": "This action requires approval before execution.",
            }

        agent = self.registry.get(agent_row.agent_id)
        if agent is None:
            raise ValueError(f"Agent not present in runtime registry: {agent_row.agent_id}")

        run = AgentRun(agent_id=agent_row.id, task_id=task.id, status=TaskStatus.RUNNING.value)
        self.session.add(run)
        task.status = TaskStatus.RUNNING.value
        agent_row.status = "thinking"
        self.session.commit()

        ctx = AgentContext(
            org_id=org.id,
            user_id=user.id,
            llm=self.llm,
            inputs=dict(task.input_json or {}),
            data=self._context_data(org),
        )
        result: AgentResult | None = None
        error: str | None = None
        for attempt in range(settings.agent_retries + 1):
            try:
                result = await agent.run(ctx, task.goal)
                break
            except AgentExecutionError as exc:
                error = str(exc)
                if not exc.retryable or attempt >= settings.agent_retries:
                    break
                await asyncio.sleep(0.05 * (attempt + 1))
            except Exception as exc:  # unknown failure → escalate, no silent meltdown
                error = f"{type(exc).__name__}: {exc}"
                break

        if result is not None:
            run.status = TaskStatus.COMPLETED.value
            run.trace_json = {"mode": result.mode, "attempts": 1}
            task.output_json = result.model_dump()
            task.confidence = result.confidence
            task.status = TaskStatus.COMPLETED.value
            task.approval_status = (
                ApprovalStatus.APPROVED.value
                if task.approval_level >= 3
                else ApprovalStatus.NONE.value
            )
            agent_row.status = "idle"
            agent_row.tasks_completed += 1
            agent_row.performance_score = _update_performance(
                agent_row.performance_score, result.confidence
            )
            self._message(
                task,
                MessageType.RESULT.value,
                from_agent=agent_row.agent_id,
                to_agent="orchestrator",
                payload={"confidence": result.confidence, "mode": result.mode},
            )
        else:
            run.status = TaskStatus.FAILED.value
            run.error = error
            task.status = TaskStatus.FAILED.value
            task.error = error or "agent failed with no error detail"
            agent_row.status = "failed"
            self._message(
                task,
                MessageType.ESCALATION.value,
                from_agent=agent_row.agent_id,
                to_agent="orchestrator",
                payload={"error": task.error},
            )

        run.ended_at = _now()
        self.session.commit()
        return {"task_state": task.status.lower(), "task_id": str(task.id)}

    # -- pipeline orchestration ----------------------------------------------
    async def orchestrate(
        self,
        org: Organization,
        user: User,
        goal: str,
        pipeline_name: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            stages_def = plan_pipeline(pipeline_name)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc

        prev: dict[str, Any] | None = None
        stages: dict[str, AgentResult] = {}
        tasks: list[dict[str, Any]] = []

        for idx, stage in enumerate(stages_def):
            inp: dict[str, Any] = dict(stage.get("inputs") or {})
            transformer: Callable[[dict[str, Any] | None, dict[str, Any]], dict[str, Any]] = stage[
                "transform"
            ]
            inp = transformer(prev, inp)
            if stage["name"] == "critic":
                # reviewer must see the consolidated picture, not just prev stage
                inp = {
                    **inp,
                    "merged": {k: v.model_dump() for k, v in stages.items()},
                    "confidence": kernel.derive_confidence(stages),
                }
            title = f"[{pipeline_name}] {stage['goal_base']} — stage {idx + 1}"
            task = self.create_task(
                org,
                user,
                title,
                stage["goal_base"],
                capability=_capability_for(stage["agent_id"]),
                input_json={**inp, "opportunities": [prev["result"]] if prev else []},
            )
            # persist handoff message per protocol
            self._message(
                task,
                MessageType.TASK_ASSIGNMENT.value,
                from_agent="orchestrator",
                to_agent=stage["agent_id"],
                payload={"stage": idx + 1},
            )
            await self.run_task(task, org, user)
            tasks.append({"stage": stage["name"], "task_ref": task.task_ref, "status": task.status})
            if task.status == TaskStatus.COMPLETED.value and isinstance(task.output_json, dict):
                stages[stage["name"]] = AgentResult.model_validate(task.output_json)
                prev = {"result": task.output_json}
            elif task.status == TaskStatus.FAILED.value:
                # fallback: ask another agent with overlapping capability
                fallback = self._fallback_agent(stage["agent_id"])
                if fallback is not None:
                    fb_task = self.create_task(
                        org,
                        user,
                        f"[fallback] {title}",
                        stage["goal_base"],
                        owner_agent_id=fallback.id,
                        input_json=task.input_json,
                    )
                    await self.run_task(fb_task, org, user)
                    if fb_task.status == TaskStatus.COMPLETED.value and isinstance(
                        fb_task.output_json, dict
                    ):
                        stages[stage["name"]] = AgentResult.model_validate(fb_task.output_json)
                        tasks.append(
                            {
                                "stage": f"{stage['name']}(fallback)",
                                "task_ref": fb_task.task_ref,
                                "status": fb_task.status,
                            }
                        )
                        prev = {"result": fb_task.output_json}
                        continue
                raise RuntimeError(f"Pipeline aborted at stage {stage['name']}: {task.error}")

        conflicts = kernel.analyze_disagreements(stages)
        recommendation = kernel.normalize_recommendation(stages.get("validation"))
        confidence = kernel.derive_confidence(stages)
        risk_level = kernel.overall_risk_level(stages)
        merged = kernel.merge_pipeline_results(stages)

        decision = Decision(
            org_id=org.id,
            title=f"Recommendation: {goal}",
            decision_type=DecisionType.BUILD_COMPANY.value,
            reason=(
                f"{describe_pipeline(pipeline_name)} concluded "
                f"'{recommendation['recommendation']}' "
                f"(validation {recommendation['validation_score']}/100)."
            ),
            supporting_evidence_json=[merged],
            agents_involved_json=list(stages),
            confidence=confidence,
            risk_level=risk_level,
        )
        self.session.add(decision)
        self.session.flush()

        approval = None
        if conflicts or recommendation["recommendation"] in ("BUILD", "VALIDATE_FURTHER"):
            level = kernel.approval_level_for("money", risk_level)
            approval = self._create_approval(
                org,
                None,
                target_decision=decision,
                level=level,
                requested_by="orchestrator",
                reason=str(decision.reason),
            )
        self.session.commit()

        return {
            "pipeline": pipeline_name,
            "goal": goal,
            "stages": stages,
            "tasks": tasks,
            "conflicts": conflicts,
            "recommendation": recommendation,
            "confidence": confidence,
            "risk_level": risk_level,
            "merged": merged,
            "decision_id": str(decision.id),
            "approval_id": str(approval.id) if approval else None,
            "approval_status": "pending" if approval else "not_required",
        }

    def decision_from_pipeline(
        self,
        org: Organization,
        goal: str,
        *,
        recommendation: dict[str, Any],
        confidence: float,
        risk_level: str,
        merged: dict[str, Any],
        agents: list[str],
        reason: str,
    ) -> Decision:
        decision = Decision(
            org_id=org.id,
            title=f"Recommendation: {goal}",
            decision_type=DecisionType.BUILD_COMPANY.value,
            reason=reason,
            supporting_evidence_json=[merged],
            agents_involved_json=agents,
            confidence=confidence,
            risk_level=risk_level,
        )
        self.session.add(decision)
        self.session.flush()
        return decision

    # -- approvals -------------------------------------------------------------
    def approve_approval(
        self, org: Organization, approval: Approval, user: User, reason: str
    ) -> None:
        self._decide_approval(approval, user, reason, status="approved")

    def reject_approval(
        self, org: Organization, approval: Approval, user: User, reason: str
    ) -> None:
        self._decide_approval(approval, user, reason, status="rejected")

    def _decide_approval(
        self, approval: Approval, user: User, reason: str, *, status: str
    ) -> None:
        self._guard_approval(approval, user)
        # Atomic conditional UPDATE: even if two concurrent request sessions both
        # read "pending" from a stale identity map, only one decider can flip the
        # row. The rowcount check turns the loser into a 409, never a silent no-op.
        result = self.session.execute(
            update(Approval)
            .where(Approval.id == approval.id, Approval.status == "pending")
            .values(status=status, decided_by=user.id, decided_at=_now(), reason=reason)
        )
        assert isinstance(result, CursorResult)
        if result.rowcount != 1:
            self.session.rollback()
            raise ValueError("Approval already decided")
        self.session.refresh(approval)
        if approval.entity_type == EntityType.DECISION.value:
            decision = self.session.get(Decision, approval.entity_id)
            if decision:
                decision.status = (
                    DecisionStatus.APPROVED.value
                    if status == "approved"
                    else DecisionStatus.REJECTED.value
                )
                decision.approved_by = user.id
                decision.approved_at = _now()
        elif approval.entity_type == EntityType.TASK.value:
            task = self.session.get(Task, approval.entity_id)
            if task:
                if status == "approved":
                    task.approval_status = ApprovalStatus.APPROVED.value
                    task.status = TaskStatus.APPROVAL_REQUIRED.value
                else:
                    task.approval_status = ApprovalStatus.REJECTED.value
                    task.status = TaskStatus.FAILED.value
                    task.error = "Rejected at approval gate"
        self.session.commit()

    # -- helpers -----------------------------------------------------------------
    def _pick_agent(self, capability: str) -> Agent | None:
        matches = self.registry.find_by_capability(capability)
        if not matches:
            return None
        row = self.session.scalar(select(Agent).where(Agent.agent_id == matches[0].agent_id))
        return row if row is not None and row.is_active else None

    def _fallback_agent(self, agent_id: str) -> Agent | None:
        primary = self.registry.get(agent_id)
        if primary is None:
            return None
        for capability in primary.capabilities:
            for alt in self.registry.find_by_capability(capability):
                if alt.agent_id == agent_id:
                    continue
                row = self.session.scalar(select(Agent).where(Agent.agent_id == alt.agent_id))
                if row is not None and row.is_active:
                    return row
        return None

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

    def _create_approval(
        self,
        org: Organization,
        task: Task | None,
        *,
        target_decision: Decision | None = None,
        level: int | None = None,
        requested_by: str = "orchestrator",
        reason: str = "",
    ) -> Approval:
        if target_decision is not None:
            approval = Approval(
                org_id=org.id,
                entity_type=EntityType.DECISION.value,
                entity_id=target_decision.id,
                level=level or 2,
                requested_by=requested_by,
                reason=reason,
            )
        else:
            assert task is not None
            approval = Approval(
                org_id=org.id,
                entity_type=EntityType.TASK.value,
                entity_id=task.id,
                level=task.approval_level,
                requested_by=requested_by,
                reason=reason,
            )
        self.session.add(approval)
        self.session.flush()
        return approval

    def _guard_approval(self, approval: Approval, user: User) -> None:
        # Note: the pending->decided transition itself is enforced by the atomic
        # conditional UPDATE in _decide_approval (concurrency-safe); here we only
        # enforce the role/authority boundary so PermissionError (403) wins over
        # the 409 conflict when an unauthorized user tries to decide.
        if approval.level >= 4 and not user.can_authorize_level4:
            raise PermissionError("Level-4 approvals require Chairman authority")
        if approval.level == 3 and user.role not in ("chairman", "admin"):
            raise PermissionError("Level-3 approvals require chairman or admin")

    def _message(
        self, task: Task, msg_type: str, *, from_agent: str, to_agent: str, payload: dict[str, Any]
    ) -> AgentMessage:
        m = AgentMessage(
            task_id=task.id,
            from_agent=from_agent,
            to_agent=to_agent,
            message_type=msg_type,
            payload_json=payload,
            priority=task.priority,
        )
        self.session.add(m)
        self.session.flush()
        return m


def _capability_for(agent_id: str) -> str:
    """Map a pipeline agent to a routing capability (used when creating tasks)."""
    capabilities = {
        "opportunity_scout": "opportunity_discovery",
        "market_research": "market_research",
        "competitive_intelligence": "competitor_analysis",
        "validation": "idea_challenge",
        "finance": "financial_analysis",
        "risk": "risk_analysis",
        "strategy": "strategy",
        "critic": "critical_review",
        "venture_builder": "company_blueprint",
    }
    return capabilities.get(agent_id, agent_id)


def _now() -> datetime:
    return datetime.now(UTC)


def _update_performance(old: float, confidence: float) -> float:
    return round(min(100.0, old * 0.9 + confidence * 100 * 0.1), 2)
