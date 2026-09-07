"""Nexus Orchestrator — workflow lifecycle, execution, gates, memory.

The engine is the Phase 2A brain:
- Plans a workflow into Tasks + WorkflowSteps (dependency-aware DAG).
- Executes steps through `AgentExecutor` (never directly; agents stay pure).
- Runs parallel branches concurrently and commits after every step so polling
  clients observe progress.
- Detects disagreements (kernel), routes them to the Critic, and never hides them.
- Pauses/resumes at L3/L4 approval gates (per-step and final-decision).
- Cancels gracefully: future steps stop, completed work and audit history remain.
- Cures curated memory + knowledge-graph facts and renders the final synthesis.

Background runs use their OWN db session (`create_session`); the API sessions are
readers/writers only for their request, so server restarts must not lose state.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from av_nexus.agents.base import AgentResult
from av_nexus.agents.registry import AgentRegistry
from av_nexus.config import settings
from av_nexus.execution.executor import AgentExecutor, ExecutionError
from av_nexus.knowledge.store import KnowledgeGraphStore
from av_nexus.llm.base import LLMClient
from av_nexus.llm.factory import build_llm_client
from av_nexus.llm.metered import MeteredLLM
from av_nexus.memory.store import MemoryStore
from av_nexus.models.agents import Agent, AgentMessage, Task
from av_nexus.models.decisions import Approval, Decision
from av_nexus.models.enums import (
    ApprovalStatus,
    DecisionStatus,
    DecisionType,
    EntityType,
    MessageType,
    Role,
    TaskStatus,
    WorkflowEventType,
    WorkflowStatus,
)
from av_nexus.models.identity import Company, Organization, User
from av_nexus.models.knowledge import KnowledgeEntity
from av_nexus.models.workflows import Workflow, WorkflowEvent, WorkflowResult, WorkflowStep
from av_nexus.orchestrator import kernel
from av_nexus.orchestrator.service import OrchestratorService
from av_nexus.workflows.pipeline import STAGE_ORDER, stage_defs, stage_inputs, workflow_label

RUNNERS: dict[uuid.UUID, asyncio.Task[Any]] = {}

_CAP_FOR = {
    "opportunity_scout": "opportunity_discovery",
    "market_research": "market_research",
    "competitive_intelligence": "competitor_analysis",
    "validation": "idea_challenge",
    "risk": "risk_analysis",
    "critic": "critical_review",
    "strategy": "strategy",
}

# The Venture Builder (Agent 6) is a REAL synthesis-time step: it is only created
# and executed when the synthesis decision is BUILD or VALIDATE_FURTHER. This is
# enforced here in the engine, never assumed by the agent. It reuses the existing
# Task + AgentRun + AgentExecution plumbing (no parallel schema).
_VB_AGENT_ID = "venture_builder"
_VB_STEP_NAME = "venture_builder"
_BLUEPRINT_KEYS = [
    "company_name",
    "mission",
    "problem",
    "solution",
    "target_customer",
    "business_model",
    "pricing",
    "mvp_plan",
    "roadmap_12_months",
]


class WorkflowEngine:
    def __init__(self, session: Session, registry: AgentRegistry, llm: LLMClient) -> None:
        self.session = session
        self.registry = registry
        self.llm = llm

    # ------------------------------------------------------------------ create
    def create_workflow(
        self,
        org: Organization,
        user: User,
        objective: str,
        *,
        workflow_type: str = "opportunity_discovery",
        company_id: uuid.UUID | None = None,
        priority: str = "medium",
        context: dict[str, Any] | None = None,
    ) -> Workflow:
        meta = dict(context or {})
        meta["objective"] = objective
        if company_id is not None:
            meta["company_id"] = str(company_id)
        wf = Workflow(
            org_id=org.id,
            created_by=user.id,
            name=f"{objective[:80]}",
            objective=objective,
            workflow_type=workflow_type,
            status=WorkflowStatus.CREATED.value,
            priority=priority,
            meta_json=meta,
        )
        self.session.add(wf)
        self.session.flush()
        self._event(
            self.session,
            wf.id,
            WorkflowEventType.CREATED.value,
            actor=user.email,
            message="Workflow created, awaiting start",
        )
        self.session.commit()
        return wf

    # ------------------------------------------------------------------- plan
    def plan(self, session: Session, workflow: Workflow, org: Organization, user: User) -> None:
        if workflow.status not in (WorkflowStatus.CREATED.value, WorkflowStatus.PLANNING.value):
            raise ValueError(f"Workflow in state '{workflow.status}' cannot be re-planned")
        tasks_in_db = session.scalars(
            select(WorkflowStep).where(WorkflowStep.workflow_id == workflow.id)
        )
        if len(list(tasks_in_db)) > 0:
            return
        workflow.status = WorkflowStatus.PLANNING.value
        svc = OrchestratorService(session, self.registry, self.llm)
        by_name: dict[str, Task] = {}
        for idx, stage in enumerate(stage_defs()):
            deps = [by_name[d].id for d in stage["deps"] if d in by_name]
            task = svc.create_task(
                org,
                user,
                f"[{workflow.workflow_type}] {stage['goal']}",
                stage["goal"],
                capability=_CAP_FOR.get(stage["agent_id"], stage["agent_id"]),
                input_json={},
                depends_on=deps,
                priority=workflow.priority,
            )
            by_name[stage["name"]] = task
            step = WorkflowStep(
                workflow_id=workflow.id,
                step_index=idx,
                name=stage["name"],
                agent_id=stage["agent_id"],
                agent_name=stage["agent_name"],
                goal=stage["goal"],
                status="WAITING",
                task_id=task.id,
                task_ref=task.task_ref,
                approval_level=1,
            )
            session.add(step)
        workflow.total_steps = len(STAGE_ORDER)
        workflow.current_step = 0
        self._event(
            session,
            workflow.id,
            WorkflowEventType.PLANNED.value,
            message=f"Planned {len(STAGE_ORDER)} steps across the workflow DAG",
        )
        session.commit()

    # ------------------------------------------------------------------ start
    def start(self, session: Session, workflow: Workflow, org: Organization, user: User) -> None:
        if workflow.status not in (WorkflowStatus.CREATED.value, WorkflowStatus.PLANNING.value):
            raise ValueError(f"Cannot start workflow in state '{workflow.status}'")
        if not list(
            session.scalars(select(WorkflowStep).where(WorkflowStep.workflow_id == workflow.id))
        ):
            self.plan(session, workflow, org, user)
        workflow.status = WorkflowStatus.RUNNING.value
        workflow.started_at = _now()
        self._event(
            session,
            workflow.id,
            WorkflowEventType.STARTED.value,
            message="Workflow started by the user",
        )
        session.commit()
        if workflow.id in RUNNERS and not RUNNERS[workflow.id].done():
            return
        RUNNERS[workflow.id] = asyncio.create_task(self._run(str(workflow.id)))

    # ---------------------------------------------------------------- control
    def cancel(self, session: Session, workflow: Workflow, reason: str) -> None:
        if workflow.status in _TERMINAL:
            raise ValueError("Workflow already finished")
        workflow.cancel_requested = True
        workflow.status = WorkflowStatus.CANCELLED.value
        workflow.error = reason or "Cancelled by the user"
        self._event(
            session,
            workflow.id,
            WorkflowEventType.CANCELLED.value,
            actor="user",
            message=workflow.error,
        )
        session.commit()

    def resume(self, session: Session, workflow: Workflow) -> None:
        if workflow.status != WorkflowStatus.WAITING_FOR_APPROVAL.value:
            raise ValueError("Workflow is not waiting for approval")
        # The runner auto-continues once the approval is resolved; this simply
        # re-activates the label while it does.
        workflow.status = WorkflowStatus.RUNNING.value
        self._event(
            session,
            workflow.id,
            WorkflowEventType.RESUMED.value,
            message="Workflow resumed after approval review",
        )
        session.commit()

    # --------------------------------------------------------------- background
    async def _run(self, workflow_id: str) -> None:
        from av_nexus.db.session import create_session

        db = create_session()
        wf_uuid = uuid.UUID(workflow_id)
        try:
            await self._execute(db, wf_uuid)
        finally:
            db.close()
            RUNNERS.pop(wf_uuid, None)

    async def _execute(self, db: Session, workflow_id: uuid.UUID) -> None:
        wf = db.get(Workflow, workflow_id)
        if wf is None:
            return
        org = db.get(Organization, wf.org_id)
        if org is None:
            wf.status = WorkflowStatus.FAILED.value
            wf.error = "Workflow references a missing org"
            self._event(db, wf.id, WorkflowEventType.FAILED.value, message=wf.error)
            db.commit()
            return
        user = db.get(User, wf.created_by) if wf.created_by else None
        if user is None:
            # Graceful degradation: the runner never hard-fails a workflow just
            # because the creating user row is gone; execution continues under a
            # minimal system identity (the AgentContext user_id is informational).
            user = User(
                id=wf.created_by or uuid.uuid4(),
                email="workflow@system.invalid",
                password_hash="",
                full_name="Workflow System",
                role=Role.AGENT.value,
            )

        deps_by_name = {s["name"]: set(s["deps"]) for s in stage_defs()}
        poll = max(0.05, settings.workflow_poll_seconds)

        while True:
            db.expire_all()
            wf = db.get(Workflow, workflow_id)
            if wf is None or wf.cancel_requested:
                if wf is not None:
                    self._cancel_steps(db, wf, wf.error or "cancelled")
                    db.commit()
                return
            steps = self._ordered_steps(db, wf)
            status_of = {s.name: s.status for s in steps}
            ready = [
                s
                for s in steps
                if s.status == "WAITING"
                and all(status_of.get(d) == "COMPLETED" for d in deps_by_name.get(s.name, set()))
            ]
            if ready:
                wf.status = WorkflowStatus.RUNNING.value
                db.commit()
                await asyncio.gather(
                    *(self._exec_step(db, wf, s, org, user) for s in ready),
                    return_exceptions=True,
                )
                continue
            statuses = {s.status for s in steps}
            if statuses and statuses <= {"COMPLETED"}:
                await self._finalize(db, wf, org, user)
                return
            if any(s.status == "FAILED" for s in steps) and not ready:
                wf.status = WorkflowStatus.FAILED.value
                wf.error = "A required step failed and no alternatives remain"
                self._event(db, wf.id, WorkflowEventType.FAILED.value, message=wf.error)
                db.commit()
                return
            wf.status = WorkflowStatus.WAITING_FOR_DEPENDENCY.value
            db.commit()
            await asyncio.sleep(poll)

    async def _exec_step(
        self, db: Session, wf: Workflow, step: WorkflowStep, org: Organization, user: User
    ) -> str:
        db.expire_all()
        wf_row = db.get(Workflow, wf.id)
        step_row = db.get(WorkflowStep, step.id)
        if wf_row is None or step_row is None:
            return "cancelled"
        wf = wf_row
        step = step_row
        task = db.get(Task, step.task_id)
        if task is None:
            step.status = "FAILED"
            step.error = "Missing backing task"
            self._event(
                db,
                wf.id,
                WorkflowEventType.STEP_FAILED.value,
                step_index=step.step_index,
                message=step.error,
            )
            db.commit()
            return "failed"

        # L3/L4 approval gate -------------------------------------------------
        if step.approval_level >= 3 and task.approval_status != ApprovalStatus.APPROVED.value:
            if task.approval_status != ApprovalStatus.REQUIRED.value:
                approval = Approval(
                    org_id=wf.org_id,
                    entity_type=EntityType.TASK.value,
                    entity_id=task.id,
                    level=step.approval_level,
                    requested_by="orchestrator",
                    reason=f"Workflow step '{step.name}' requires human approval before execution",
                )
                db.add(approval)
                db.flush()
                task.approval_status = ApprovalStatus.REQUIRED.value
            wf.status = WorkflowStatus.WAITING_FOR_APPROVAL.value
            self._event(
                db,
                wf.id,
                WorkflowEventType.APPROVAL_REQUIRED.value,
                step_index=step.step_index,
                message=(
                    f"Workflow paused: step '{step.name}' needs L{step.approval_level} approval"
                ),
                payload={"level": step.approval_level, "task_id": str(task.id)},
            )
            db.commit()
            outcome = await self._wait_approval(db, wf, approval.id)
            if outcome == "cancelled":
                step.status = "CANCELLED"
                self._event(
                    db,
                    wf.id,
                    WorkflowEventType.STEP_CANCELLED.value,
                    step_index=step.step_index,
                    message="Cancelled while awaiting approval",
                )
                db.commit()
                return "cancelled"
            if outcome == "rejected":
                step.status = "FAILED"
                step.error = "Rejected at approval gate"
                wf.status = WorkflowStatus.FAILED.value
                wf.error = f"Step '{step.name}' rejected at the approval gate"
                self._event(
                    db,
                    wf.id,
                    WorkflowEventType.APPROVAL_REJECTED.value,
                    step_index=step.step_index,
                    message="Approval rejected — dependent execution stopped",
                )
                db.commit()
                return "failed"

        wf.status = WorkflowStatus.RUNNING.value
        wf.current_step = max(wf.current_step, step.step_index + 1)
        step.status = "RUNNING"
        step.started_at = _now()
        task.status = TaskStatus.RUNNING.value
        self._event(
            db,
            wf.id,
            WorkflowEventType.STEP_STARTED.value,
            step_index=step.step_index,
            message=f"{step.agent_name} started",
        )
        db.commit()

        inputs = stage_inputs(step.name, self._collect_outputs(db, wf), wf.meta_json or {})
        task.input_json = inputs
        step.input_summary_json = {
            "keys": list(inputs),
            "stage": step.name,
            "objective": (wf.meta_json or {}).get("objective", ""),
        }
        db.commit()

        agent_impl = self.registry.require(step.agent_id)
        agent_row = db.scalar(select(Agent).where(Agent.agent_id == step.agent_id))
        if agent_row is None or not agent_row.is_active:
            step.status = "FAILED"
            step.error = f"Agent '{step.agent_id}' is not available"
            task.status = TaskStatus.FAILED.value
            task.error = step.error
            self._event(
                db,
                wf.id,
                WorkflowEventType.STEP_FAILED.value,
                step_index=step.step_index,
                message=step.error,
            )
            db.commit()
            return "failed"

        company_id = _coerce_uuid((wf.meta_json or {}).get("company_id"))
        executor = AgentExecutor(
            db, agent_impl, agent_row, MeteredLLM(build_llm_client()), company_id=company_id
        )
        try:
            ex = await executor.execute(task, org, user)
        except ExecutionError as exc:
            step.status = "FAILED"
            step.error = f"{exc}"
            step.ended_at = _now()
            task.status = TaskStatus.FAILED.value
            task.error = f"{exc}"
            agent_row.status = "failed"
            wf.status = WorkflowStatus.FAILED.value
            wf.error = f"Step '{step.name}' failed: {exc}"
            self._event(
                db,
                wf.id,
                WorkflowEventType.STEP_FAILED.value,
                step_index=step.step_index,
                message=f"{exc}",
            )
            self._event(db, wf.id, WorkflowEventType.FAILED.value, message=wf.error)
            self._message(
                db,
                task,
                MessageType.ESCALATION.value,
                from_agent=step.agent_id,
                to_agent="orchestrator",
                payload={"error": wf.error},
            )
            db.commit()
            return "failed"

        task.output_json = ex.result.model_dump()
        task.status = TaskStatus.COMPLETED.value
        task.confidence = ex.result.confidence
        task.approval_status = (
            ApprovalStatus.APPROVED.value if step.approval_level >= 3 else ApprovalStatus.NONE.value
        )
        step.status = "COMPLETED"
        step.output_summary_json = {
            "mode": ex.result.mode,
            "confidence": ex.result.confidence,
            "keys": list(ex.result.result),
            "attempts": ex.attempts,
            "duration_ms": ex.duration_ms,
            "tools": len(ex.tool_calls),
            "tokens_in": ex.tokens_in,
            "tokens_out": ex.tokens_out,
        }
        step.ended_at = _now()
        agent_row.status = "idle"
        agent_row.tasks_completed += 1
        agent_row.performance_score = _perf(agent_row.performance_score, ex.result.confidence)
        self._event(
            db,
            wf.id,
            WorkflowEventType.STEP_COMPLETED.value,
            step_index=step.step_index,
            message=f"{step.agent_name} completed",
            payload=step.output_summary_json,
        )
        self._message(
            db,
            task,
            MessageType.RESULT.value,
            from_agent=step.agent_id,
            to_agent="orchestrator",
            payload={"confidence": ex.result.confidence, "mode": ex.result.mode},
        )
        db.commit()
        return "completed"

    async def _wait_approval(self, db: Session, wf: Workflow, approval_id: uuid.UUID) -> str:
        while True:
            db.expire_all()
            current = db.get(Workflow, wf.id)
            if current is None or current.cancel_requested:
                return "cancelled"
            approval = db.get(Approval, approval_id)
            if approval is None:
                return "failed"
            if approval.status == "approved":
                self._event(
                    db, wf.id, WorkflowEventType.APPROVAL_RESOLVED.value, message="Approval granted"
                )
                db.commit()
                return "approved"
            if approval.status == "rejected":
                self._event(
                    db,
                    wf.id,
                    WorkflowEventType.APPROVAL_REJECTED.value,
                    message="Approval rejected",
                )
                db.commit()
                return "rejected"
            await asyncio.sleep(max(0.05, settings.workflow_poll_seconds))

    # --------------------------------------------------- venture builder step
    async def _run_venture_builder(
        self,
        db: Session,
        wf: Workflow,
        org: Organization,
        user: User,
        stages: dict[str, AgentResult],
    ) -> None:
        """Execute the Venture Builder as a real workflow step (Task + AgentRun).

        Called only from `_finalize` after the gate check; `_finalize` verifies
        `wf.status` afterwards and aborts if this method failed the workflow.
        """
        step_index = max(
            (s.step_index for s in self._ordered_steps(db, wf)), default=-1
        ) + 1
        svc = OrchestratorService(db, self.registry, self.llm)
        task = svc.create_task(
            org,
            user,
            f"[{wf.workflow_type}] Produce a build-ready company blueprint",
            "Draft the company blueprint (mission, MVP, business model, pricing, "
            "12-month roadmap) for the recommended venture",
            capability="company_blueprint",
            input_json=_venture_builder_inputs(stages, wf),
            priority=wf.priority,
        )
        step = WorkflowStep(
            workflow_id=wf.id,
            step_index=step_index,
            name=_VB_STEP_NAME,
            agent_id=_VB_AGENT_ID,
            agent_name="Venture Builder",
            goal=task.goal,
            status="RUNNING",
            task_id=task.id,
            task_ref=task.task_ref,
            approval_level=1,
            input_summary_json={
                "keys": list(task.input_json or {}),
                "stage": _VB_STEP_NAME,
                "objective": wf.objective,
            },
        )
        db.add(step)
        wf.total_steps = step_index + 1
        wf.current_step = max(wf.current_step, step_index + 1)
        self._event(
            db,
            wf.id,
            WorkflowEventType.STEP_STARTED.value,
            step_index=step_index,
            message="Venture Builder started",
        )
        db.commit()

        try:
            agent_impl = self.registry.require(_VB_AGENT_ID)
        except KeyError:
            self._fail_venture_builder(
                db, wf, task, step, None, f"Agent '{_VB_AGENT_ID}' is not registered"
            )
            return
        agent_row = db.scalar(select(Agent).where(Agent.agent_id == _VB_AGENT_ID))
        if agent_row is None or not agent_row.is_active:
            self._fail_venture_builder(
                db, wf, task, step, agent_row, f"Agent '{_VB_AGENT_ID}' is not available"
            )
            return

        executor = AgentExecutor(
            db,
            agent_impl,
            agent_row,
            MeteredLLM(build_llm_client()),
            company_id=_coerce_uuid((wf.meta_json or {}).get("company_id")),
        )
        try:
            ex = await executor.execute(task, org, user)
        except ExecutionError as exc:
            self._fail_venture_builder(db, wf, task, step, agent_row, f"{exc}")
            return

        blueprint = ex.result.result.get("blueprint")
        if not isinstance(blueprint, dict):
            self._fail_venture_builder(
                db, wf, task, step, agent_row, "Venture Builder returned no blueprint object"
            )
            return
        missing = [k for k in _BLUEPRINT_KEYS if k not in blueprint]
        if missing:
            self._fail_venture_builder(
                db,
                wf,
                task,
                step,
                agent_row,
                f"Venture Builder produced a malformed blueprint; missing keys: {missing}",
            )
            return

        task.output_json = ex.result.model_dump()
        task.status = TaskStatus.COMPLETED.value
        task.confidence = ex.result.confidence
        task.approval_status = ApprovalStatus.NONE.value
        step.status = "COMPLETED"
        step.output_summary_json = {
            "mode": ex.result.mode,
            "confidence": ex.result.confidence,
            "keys": list(ex.result.result),
            "attempts": ex.attempts,
            "duration_ms": ex.duration_ms,
            "tokens_in": ex.tokens_in,
            "tokens_out": ex.tokens_out,
        }
        step.ended_at = _now()
        agent_row.status = "idle"
        agent_row.tasks_completed += 1
        agent_row.performance_score = _perf(agent_row.performance_score, ex.result.confidence)
        self._event(
            db,
            wf.id,
            WorkflowEventType.STEP_COMPLETED.value,
            step_index=step_index,
            message="Venture Builder completed the company blueprint",
            payload=step.output_summary_json,
        )
        self._message(
            db,
            task,
            MessageType.RESULT.value,
            from_agent=_VB_AGENT_ID,
            to_agent="orchestrator",
            payload={"confidence": ex.result.confidence, "mode": ex.result.mode},
        )
        db.commit()

    def _fail_venture_builder(
        self,
        db: Session,
        wf: Workflow,
        task: Task,
        step: WorkflowStep,
        agent_row: Agent | None,
        error: str,
    ) -> None:
        """Transition to a clear FAILED state with the raw error; no placeholders."""
        step.status = "FAILED"
        step.error = error
        step.ended_at = _now()
        task.status = TaskStatus.FAILED.value
        task.error = error
        if agent_row is not None:
            agent_row.status = "failed"
        wf.status = WorkflowStatus.FAILED.value
        wf.error = f"Step '{_VB_STEP_NAME}' failed: {error}"
        self._event(
            db,
            wf.id,
            WorkflowEventType.STEP_FAILED.value,
            step_index=step.step_index,
            message=error,
        )
        self._event(db, wf.id, WorkflowEventType.FAILED.value, message=wf.error)
        self._message(
            db,
            task,
            MessageType.ESCALATION.value,
            from_agent=_VB_AGENT_ID,
            to_agent="orchestrator",
            payload={"error": wf.error},
        )
        db.commit()

    # ---------------------------------------------------------------- finalize
    async def _finalize(self, db: Session, wf: Workflow, org: Organization, user: User) -> None:
        stages = self._collect_outputs(db, wf)
        conflicts = kernel.analyze_disagreements(stages)
        recommendation = kernel.normalize_recommendation(stages.get("validation"))
        confidence = kernel.derive_confidence(stages)
        risk_level = kernel.overall_risk_level(stages)
        merged = kernel.merge_pipeline_results(stages)

        self._persist_opportunities(db, wf, stages)
        # Venture Builder gate: only BUILD / VALIDATE_FURTHER spawn the blueprint
        # step. A failure here flips the workflow to FAILED with the raw error.
        if str(recommendation.get("recommendation", "")) in ("BUILD", "VALIDATE_FURTHER"):
            await self._run_venture_builder(db, wf, org, user, stages)
            if wf.status == WorkflowStatus.FAILED.value:
                return
            stages = self._collect_outputs(db, wf)
            merged = kernel.merge_pipeline_results(stages)
            confidence = kernel.derive_confidence(stages)
        result = WorkflowResult(
            workflow_id=wf.id,
            objective=wf.objective,
            summary=_executive_summary(
                wf.objective, recommendation, confidence, risk_level, conflicts
            ),
            report_md=_render_report(
                wf, stages, recommendation, confidence, risk_level, conflicts, merged
            ),
            top_opportunities=_top_opportunities(stages),
            market_findings=_market_findings(stages),
            competitive_findings=_competitive_findings(stages),
            risks=_risks(stages),
            disagreements=conflicts,
            next_actions=_next_actions(recommendation, stages),
            approval_requirements=_approval_requirements(conflicts, recommendation, risk_level),
            stage_results_json=list(merged.values()),
            confidence=confidence,
            recommendation=str(recommendation.get("recommendation", "")),
        )
        db.add(result)
        db.flush()

        decision = Decision(
            org_id=wf.org_id,
            title=f"Recommendation: {wf.objective[:200]}",
            decision_type=DecisionType.BUILD_COMPANY.value,
            reason=(
                f"{workflow_label(wf.workflow_type)} concluded "
                f"'{recommendation.get('recommendation')}' "
                f"(validation {recommendation.get('validation_score', 0.0)}/100)."
            ),
            supporting_evidence_json=[merged],
            agents_involved_json=list(stages),
            confidence=confidence,
            risk_level=risk_level,
        )
        db.add(decision)
        db.flush()

        self._curate_memory(db, wf, stages)
        self._curate_knowledge(db, wf, stages)

        self._event(
            db,
            wf.id,
            WorkflowEventType.SYNTHESIS_COMPLETED.value,
            message="Final synthesis assembled",
        )
        db.commit()

        approval = None
        if conflicts or recommendation.get("recommendation") in ("BUILD", "VALIDATE_FURTHER"):
            level = kernel.approval_level_for("money", risk_level)
            approval = Approval(
                org_id=wf.org_id,
                entity_type=EntityType.DECISION.value,
                entity_id=decision.id,
                level=level,
                requested_by="orchestrator",
                reason=str(decision.reason),
            )
            db.add(approval)
            db.flush()
            wf.status = WorkflowStatus.WAITING_FOR_APPROVAL.value
            self._event(
                db,
                wf.id,
                WorkflowEventType.APPROVAL_REQUIRED.value,
                message=f"Chairman review required (L{level}) before the workflow completes",
                payload={
                    "level": level,
                    "approval_id": str(approval.id),
                    "decision_id": str(decision.id),
                },
            )
            db.commit()
            outcome = await self._wait_approval(db, wf, approval.id)
            if outcome == "approved":
                decision.status = DecisionStatus.APPROVED.value
                wf.status = WorkflowStatus.COMPLETED.value
                wf.completed_at = _now()
                wf.confidence = confidence
                self._event(
                    db,
                    wf.id,
                    WorkflowEventType.COMPLETED.value,
                    message="Workflow completed after approval",
                )
                db.commit()
            elif outcome == "rejected":
                decision.status = DecisionStatus.REJECTED.value
                wf.status = WorkflowStatus.FAILED.value
                wf.error = "Final synthesis rejected at the approval gate"
                self._event(db, wf.id, WorkflowEventType.FAILED.value, message=wf.error)
                db.commit()
            else:  # cancelled
                self._cancel_steps(db, wf, "Cancelled while awaiting approval")
                db.commit()
            return

        wf.status = WorkflowStatus.COMPLETED.value
        wf.completed_at = _now()
        wf.confidence = confidence
        self._event(db, wf.id, WorkflowEventType.COMPLETED.value, message="Workflow completed")
        db.commit()

    # ----------------------------------------------------------------- helpers
    def _ordered_steps(self, session: Session, wf: Workflow) -> list[WorkflowStep]:
        return list(
            session.scalars(
                select(WorkflowStep)
                .where(WorkflowStep.workflow_id == wf.id)
                .order_by(WorkflowStep.step_index)
            )
        )

    def _collect_outputs(self, session: Session, wf: Workflow) -> dict[str, AgentResult]:
        outputs: dict[str, AgentResult] = {}
        for step in self._ordered_steps(session, wf):
            if step.status != "COMPLETED" or step.task_id is None:
                continue
            task = session.get(Task, step.task_id)
            if task is None or not isinstance(task.output_json, dict):
                continue
            try:
                outputs[step.name] = AgentResult.model_validate(task.output_json)
            except Exception:
                continue
        return outputs

    def _persist_opportunities(
        self, session: Session, wf: Workflow, stages: dict[str, AgentResult]
    ) -> None:
        from av_nexus.models.opportunities import Opportunity

        scout = stages.get("scout")
        if scout is None:
            return
        candidates = scout.result.get("candidates")
        if not isinstance(candidates, list):
            return
        existing = {
            o.title
            for o in session.scalars(select(Opportunity).where(Opportunity.org_id == wf.org_id))
        }
        for cand in candidates[:3]:
            if not isinstance(cand, dict):
                continue
            title = str(cand.get("title") or cand.get("industry") or "untitled")
            if title in existing:
                continue
            session.add(
                Opportunity(
                    org_id=wf.org_id,
                    title=title,
                    description=str(cand.get("rationale", "")),
                    category=str(cand.get("category", "")),
                    opportunity_score=float(cand.get("opportunity_score", 0.0)),
                    market_potential=float(cand.get("market_potential", 0.0)),
                    growth_rate=float(cand.get("growth_rate", 0.0)),
                    competition=float(cand.get("competition", 0.0)),
                    entry_difficulty=float(cand.get("entry_difficulty", 0.0)),
                    capital_requirements=float(cand.get("capital_requirements", 0.0)),
                    risk_score=float(cand.get("risk_score", 0.0)),
                    status="discovered",
                    source=f"workflow:{wf.id}",
                )
            )

    def _curate_memory(
        self, session: Session, wf: Workflow, stages: dict[str, AgentResult]
    ) -> None:
        ms = MemoryStore(session, wf.org_id)
        rec = "(no recommendation)"
        if stages.get("validation") is not None:
            rec = str(stages["validation"].result.get("verdict", rec))
        ms.put(
            "global",
            f"workflow:{wf.id}",
            {
                "objective": wf.objective,
                "verdict": rec,
                "confidence": kernel.derive_confidence(stages),
            },
            agent_id="orchestrator",
            note="Workflow synthesis summary",
        )
        top = _top_opportunity(stages)
        if top is not None:
            ms.put(
                "global",
                f"opportunity:{_slug(top.get('title', ''))}",
                {
                    "title": top.get("title"),
                    "industry": top.get("industry"),
                    "opportunity_score": top.get("opportunity_score"),
                    "source_workflow": str(wf.id),
                },
                note="Discovered opportunity (curated, workflow-sourced)",
            )
        market = stages.get("market_research")
        if market is not None:
            ind = str(top.get("industry", "market")) if top else "market"
            ms.put(
                "global",
                f"market:{_slug(ind)}",
                {
                    "recommendation": market.result.get("recommendation"),
                    "demand_score": market.result.get("demand_score"),
                },
                note="Market finding (curated, workflow-sourced)",
            )
        risk = stages.get("risk")
        if risk is not None:
            ms.put(
                "global",
                f"risk:{_slug(ind if top else 'market')}",
                {"overall_level": risk.result.get("overall_level")},
                note="Risk profile (curated, workflow-sourced)",
            )
        self._event(
            session,
            wf.id,
            WorkflowEventType.MEMORY_SAVED.value,
            message="Curated memories persisted",
        )

    def _curate_knowledge(
        self, session: Session, wf: Workflow, stages: dict[str, AgentResult]
    ) -> None:
        kg = KnowledgeGraphStore(session, wf.org_id)
        top = _top_opportunity(stages)
        if top is None:
            return
        opp = _entity(kg, "Opportunity", str(top.get("title", "opportunity")))
        mkt_name = str(top.get("industry", "market"))
        mkt = _entity(kg, "Market", mkt_name)
        _relationship(kg, opp, mkt, "exists_in", {"source": "workflow", "workflow_id": str(wf.id)})
        ci = stages.get("competitive_intelligence")
        if ci is not None:
            for entry in (
                ci.result.get("competitor_report") or []
                if isinstance(ci.result.get("competitor_report"), list)
                else []
            ):
                if not isinstance(entry, dict):
                    continue
                comp = _entity(kg, "Competitor", str(entry.get("name", "competitor")))
                _relationship(kg, comp, mkt, "exists_in", {"source": "workflow"})
                _relationship(kg, comp, opp, "competes_with", {"source": "workflow"})
        company_id = _coerce_uuid((wf.meta_json or {}).get("company_id"))
        if company_id is not None:
            company = session.get(Company, company_id)
            if company is not None and company.org_id == wf.org_id:
                co = _entity(kg, "Company", company.name)
                _relationship(kg, co, mkt, "operates_in", {"source": "workflow"})

    def _event(
        self,
        session: Session,
        workflow_id: uuid.UUID,
        event_type: str,
        *,
        actor: str = "orchestrator",
        step_index: int | None = None,
        message: str = "",
        payload: dict[str, Any] | None = None,
    ) -> WorkflowEvent:
        evt = WorkflowEvent(
            workflow_id=workflow_id,
            event_type=event_type,
            actor=actor,
            step_index=step_index,
            message=message,
            payload_json=payload,
        )
        session.add(evt)
        session.flush()
        return evt

    def _message(
        self,
        session: Session,
        task: Task,
        msg_type: str,
        *,
        from_agent: str,
        to_agent: str,
        payload: dict[str, Any],
    ) -> AgentMessage:
        m = AgentMessage(
            task_id=task.id,
            from_agent=from_agent,
            to_agent=to_agent,
            message_type=msg_type,
            payload_json=payload,
            priority=task.priority,
        )
        session.add(m)
        session.flush()
        return m

    def _cancel_steps(self, session: Session, wf: Workflow, reason: str) -> None:
        for step in self._ordered_steps(session, wf):
            if step.status in ("WAITING", "RUNNING"):
                step.status = "CANCELLED"
                step.error = reason
        wf.status = WorkflowStatus.CANCELLED.value
        wf.error = reason
        self._event(session, wf.id, WorkflowEventType.CANCELLED.value, message=reason)


_TERMINAL = {
    WorkflowStatus.COMPLETED.value,
    WorkflowStatus.FAILED.value,
    WorkflowStatus.CANCELLED.value,
}


def _now() -> datetime:
    return datetime.now(UTC)


def _perf(old: float, confidence: float) -> float:
    return round(min(100.0, old * 0.9 + confidence * 100 * 0.1), 2)


def _coerce_uuid(raw: object) -> uuid.UUID | None:
    if raw is None:
        return None
    try:
        return uuid.UUID(str(raw))
    except (ValueError, AttributeError):
        return None


def _slug(value: str) -> str:
    words = "".join(c if c.isalnum() else " " for c in value).split()
    return "_".join(words[:4]).lower()[:60] or "item"


def _top_opportunity(stages: dict[str, AgentResult]) -> dict[str, Any] | None:
    scout = stages.get("scout")
    if scout is None:
        return None
    candidates = scout.result.get("candidates")
    if isinstance(candidates, list) and candidates and isinstance(candidates[0], dict):
        return dict(candidates[0])
    return None


def _venture_builder_inputs(
    stages: dict[str, AgentResult], wf: Workflow
) -> dict[str, Any]:
    meta = wf.meta_json or {}
    top = _top_opportunity(stages)
    market = stages.get("market_research")
    validation = stages.get("validation")
    risk = stages.get("risk")
    strategy = stages.get("strategy")
    return {
        "objective": meta.get("objective") or wf.objective,
        "industry_focus": meta.get("industry_focus") or "",
        "opportunity": top or {},
        "market": market.result if market is not None else {},
        "validation": validation.result if validation is not None else {},
        "risk": risk.result if risk is not None else {},
        "strategy": strategy.result if strategy is not None else {},
        "synthesis_recommendation": str(
            kernel.normalize_recommendation(validation).get("recommendation", "")
        ),
    }


def _venture_blueprint(stages: dict[str, AgentResult]) -> dict[str, Any] | None:
    vb = stages.get("venture_builder")
    if vb is None:
        return None
    bp = vb.result.get("blueprint")
    return bp if isinstance(bp, dict) else None


def _entity(kg: KnowledgeGraphStore, etype: str, name: str) -> KnowledgeEntity:
    for ent in kg.entities():
        if ent.entity_type == etype and ent.name == name:
            return ent
    return kg.add_entity(etype, name)


def _relationship(
    kg: KnowledgeGraphStore,
    a: KnowledgeEntity,
    b: KnowledgeEntity,
    rtype: str,
    props: dict[str, Any],
) -> None:
    for rel in kg.relationships():
        if (
            rel.from_entity_id == a.id
            and rel.to_entity_id == b.id
            and rel.relationship_type == rtype
        ):
            return
    kg.add_relationship(a.id, b.id, rtype, props)


def _top_opportunities(stages: dict[str, AgentResult]) -> list[dict[str, Any]]:
    scout = stages.get("scout")
    if scout is None:
        return []
    candidates = scout.result.get("candidates")
    if not isinstance(candidates, list):
        return []
    return [
        {
            "title": c.get("title"),
            "industry": c.get("industry"),
            "category": c.get("category"),
            "opportunity_score": c.get("opportunity_score"),
            "rationale": c.get("rationale"),
        }
        for c in candidates[:3]
        if isinstance(c, dict)
    ]


def _market_findings(stages: dict[str, AgentResult]) -> list[dict[str, Any]]:
    market = stages.get("market_research")
    if market is None:
        return []
    r = market.result
    return [
        {
            "tam": r.get("tam"),
            "sam": r.get("sam"),
            "som": r.get("som"),
            "growth_rate_pct": r.get("growth_rate_pct"),
            "demand_score": r.get("demand_score"),
            "entry_barrier": r.get("entry_barrier"),
            "recommendation": r.get("recommendation"),
            "note": r.get("note"),
        }
    ]


def _competitive_findings(stages: dict[str, AgentResult]) -> list[dict[str, Any]]:
    ci = stages.get("competitive_intelligence")
    if ci is None:
        return []
    r = ci.result
    return [
        {
            "top_threat": r.get("top_threat"),
            "monitoring_status": r.get("monitoring_status"),
            "report": r.get("competitor_report"),
        }
    ]


def _risks(stages: dict[str, AgentResult]) -> list[dict[str, Any]]:
    risk = stages.get("risk")
    if risk is None:
        return []
    return [dict(e) for e in (risk.result.get("risk_matrix") or []) if isinstance(e, dict)]


def _next_actions(
    recommendation: dict[str, Any], stages: dict[str, AgentResult]
) -> list[dict[str, Any]]:
    actions = [
        {
            "action": "Validate the top opportunity with primary customer interviews",
            "owner": "validation / analysis",
        },
        {
            "action": "Refresh competitor intelligence with live monitoring",
            "owner": "competitive_intelligence",
        },
        {"action": "Model unit economics before any capital deployment", "owner": "finance"},
    ]
    rec = str(recommendation.get("recommendation", ""))
    if rec == "BUILD":
        actions.insert(
            0,
            {
                "action": "Draft an MVP build plan for the top opportunity",
                "owner": "venture_builder",
            },
        )
    if rec == "VALIDATE_FURTHER":
        actions.insert(
            0,
            {
                "action": "Commission deeper market validation before committing capital",
                "owner": "market_research",
            },
        )
    if rec == "REJECT":
        actions.insert(
            0,
            {
                "action": "Do not proceed; revisit only with material new evidence",
                "owner": "chairman",
            },
        )
    return actions


def _approval_requirements(
    conflicts: list[dict[str, Any]], recommendation: dict[str, Any], risk_level: str
) -> list[dict[str, Any]]:
    if conflicts or recommendation.get("recommendation") in ("BUILD", "VALIDATE_FURTHER"):
        level = kernel.approval_level_for("money", risk_level)
        return [
            {
                "scope": "Final synthesis recommendation",
                "level": level,
                "requires": "chairman" if level == 4 else "chairman or admin",
                "reason": "BUILD/VALIDATE_FURTHER recommendation or detected disagreements",
            }
        ]
    return []


def _executive_summary(
    objective: str,
    recommendation: dict[str, Any],
    confidence: float,
    risk_level: str,
    conflicts: list[dict[str, Any]],
) -> str:
    rec = str(recommendation.get("recommendation", "UNKNOWN"))
    score = recommendation.get("validation_score", 0.0)
    return (
        f"For '{objective}': the collective assessment recommends {rec} "
        f"(validation {score}/100, overall confidence {round(confidence * 100)}%). "
        f"Risk: {risk_level}. Disagreements detected: {len(conflicts)}."
    )


def _render_report(
    wf: Workflow,
    stages: dict[str, AgentResult],
    recommendation: dict[str, Any],
    confidence: float,
    risk_level: str,
    conflicts: list[dict[str, Any]],
    merged: dict[str, Any],
) -> str:
    sections: list[str] = [f"# Final Synthesis — {wf.objective}", ""]
    sections.append("## EXECUTIVE SUMMARY")
    sections.append(
        _executive_summary(wf.objective, recommendation, confidence, risk_level, conflicts)
    )
    sections.append("")
    sections.append("## TOP OPPORTUNITIES")
    for o in _top_opportunities(stages):
        sections.append(
            f"- {o.get('title')} ({o.get('industry')}): score {o.get('opportunity_score')}"
        )
    sections.append("")
    sections.append("## MARKET FINDINGS")
    for m in _market_findings(stages):
        sections.append(
            f"- {m.get('recommendation')}: TAM {m.get('tam')}, demand {m.get('demand_score')}, "
            f"growth {m.get('growth_rate_pct')}% (note: {m.get('note')})"
        )
    sections.append("")
    sections.append("## COMPETITIVE FINDINGS")
    for c in _competitive_findings(stages):
        sections.append(f"- Top threat: {c.get('top_threat')}. {c.get('monitoring_status')}")
    sections.append("")
    sections.append("## RISKS")
    if _risks(stages):
        for r in _risks(stages)[:10]:
            sections.append(f"- [{r.get('level')}] {r.get('category')}: {r.get('title')}")
    else:
        sections.append("- No explicit risks surfaced.")
    sections.append("")
    sections.append("## DISAGREEMENTS")
    if conflicts:
        for c in conflicts:
            sections.append(f"- {c.get('type')}: {c.get('detail')}")
    else:
        sections.append("- No disagreements detected between agents.")
    sections.append("")
    sections.append(
        f"## CONFIDENCE\n{round(confidence * 100)}% overall (mean of stage confidence)."
    )
    sections.append("")
    sections.append(
        "## RECOMMENDATION\n"
        f"{recommendation.get('recommendation')} "
        f"(validation {recommendation.get('validation_score')}/100)."
    )
    sections.append("")
    sections.append("## VENTURE BLUEPRINT")
    vbd = _venture_blueprint(stages)
    if vbd is None:
        sections.append("- No blueprint requested (recommendation was not BUILD/VALIDATE_FURTHER).")
    else:
        sections.append(f"- Company: {vbd.get('company_name', '')}")
        sections.append(f"- Mission: {vbd.get('mission', '')}")
        sections.append(f"- Problem: {vbd.get('problem', '')}")
        sections.append(f"- Solution: {vbd.get('solution', '')}")
        sections.append(f"- Target customer: {vbd.get('target_customer', '')}")
        sections.append(f"- Business model: {vbd.get('business_model', '')}")
        sections.append(f"- Pricing: {vbd.get('pricing', '')}")
        mvp = vbd.get("mvp_plan")
        if isinstance(mvp, dict):
            sections.append(
                f"- MVP plan ({mvp.get('duration_weeks')} wks): "
                f"{', '.join(mvp.get('focus_blocks') or [])} — "
                f"success = {mvp.get('success_metric', '')}"
            )
        roadmap = vbd.get("roadmap_12_months")
        if isinstance(roadmap, list):
            for entry in roadmap[:12]:
                if isinstance(entry, dict):
                    sections.append(
                        f"  - M{entry.get('month')}: {entry.get('milestone')}"
                    )
    sections.append("")
    sections.append("## NEXT ACTIONS")
    for a in _next_actions(recommendation, stages):
        sections.append(f"- {a.get('action')} (owner: {a.get('owner')})")
    sections.append("")
    sections.append("## APPROVAL REQUIREMENTS")
    reqs = _approval_requirements(conflicts, recommendation, risk_level)
    if reqs:
        for r in reqs:
            sections.append(f"- L{r.get('level')} {r.get('requires')}: {r.get('reason')}")
    else:
        sections.append("- None.")
    sections.append("")
    sections.append(
        "> Generated by the Nexus Orchestrator. Facts are sourced from workflow "
        "stage results; heuristic estimates are labelled as such and are not "
        "external research."
    )
    return "\n".join(sections)
