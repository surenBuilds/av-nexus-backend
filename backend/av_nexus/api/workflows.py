"""Workflow routes (Phase 2A).

Human-control surface for the Nexus Orchestrator: create → plan → start →
poll (tasks/runs/messages/trace) → approve/reject at gates → final report.
State always lives in the DB; these routes only read/write via their request
session. Long-running execution happens in the background runner.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from av_nexus.api.deps import get_org
from av_nexus.core.security import get_current_user, write_audit
from av_nexus.db.session import get_session
from av_nexus.models.agents import AgentMessage, AgentRun, Task
from av_nexus.models.decisions import Approval
from av_nexus.models.identity import Organization, User
from av_nexus.models.workflows import Workflow, WorkflowEvent, WorkflowResult, WorkflowStep
from av_nexus.schemas.tasks import MessageOut, TaskOut
from av_nexus.schemas.workflows import (
    RunInfo,
    WorkflowControlRequest,
    WorkflowCreate,
    WorkflowDetailOut,
    WorkflowEventOut,
    WorkflowOut,
    WorkflowResultOut,
    WorkflowStepOut,
    WorkflowTaskOut,
    WorkflowTraceOut,
)
from av_nexus.workflows.engine import WorkflowEngine

router = APIRouter(prefix="/workflows", tags=["workflows"])

_ALLOWED_TYPES = {"opportunity_discovery"}


def _engine(session: Session) -> WorkflowEngine:
    from av_nexus.agents import get_registry
    from av_nexus.llm.factory import build_llm_client

    return WorkflowEngine(session, get_registry(), build_llm_client())


def _get_workflow(session: Session, org: Organization, workflow_id: uuid.UUID) -> Workflow:
    wf = session.get(Workflow, workflow_id)
    if wf is None or wf.org_id != org.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workflow not found")
    return wf


def _steps(session: Session, wf: Workflow) -> list[WorkflowStep]:
    return list(
        session.scalars(
            select(WorkflowStep)
            .where(WorkflowStep.workflow_id == wf.id)
            .order_by(WorkflowStep.step_index)
        )
    )


def _task_ids(steps: list[WorkflowStep]) -> list[uuid.UUID]:
    return [s.task_id for s in steps if s.task_id is not None]


# ---------------------------------------------------------------------- create
@router.post("", response_model=WorkflowOut, status_code=status.HTTP_201_CREATED)
def create_workflow(
    payload: WorkflowCreate,
    session: Session = Depends(get_session),
    org: Organization = Depends(get_org),
    user: User = Depends(get_current_user),
) -> Workflow:
    wtype = payload.workflow_type if payload.workflow_type != "auto" else "opportunity_discovery"
    if wtype not in _ALLOWED_TYPES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, f"Unsupported workflow type: {wtype}"
        )
    if payload.priority not in ("low", "medium", "high", "critical"):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "priority must be low|medium|high|critical"
        )
    engine = _engine(session)
    try:
        wf = engine.create_workflow(
            org,
            user,
            payload.objective,
            workflow_type=wtype,
            company_id=payload.company_id,
            priority=payload.priority,
            context=payload.context,
        )
        engine.plan(session, wf, org, user)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    write_audit(
        session,
        user=user,
        org_id=org.id,
        action="workflow.create",
        entity_type="workflow",
        entity_id=str(wf.id),
    )
    session.commit()
    session.refresh(wf)
    return wf


@router.get("", response_model=list[WorkflowOut])
def list_workflows(
    status_filter: str | None = None,
    session: Session = Depends(get_session),
    org: Organization = Depends(get_org),
) -> list[Workflow]:
    stmt = select(Workflow).where(Workflow.org_id == org.id)
    if status_filter:
        stmt = stmt.where(Workflow.status == status_filter.upper())
    stmt = stmt.order_by(Workflow.created_at.desc()).limit(100)
    return list(session.scalars(stmt))


# ---------------------------------------------------------------------- detail
@router.get("/{workflow_id}", response_model=WorkflowDetailOut)
def get_workflow(
    workflow_id: uuid.UUID,
    session: Session = Depends(get_session),
    org: Organization = Depends(get_org),
) -> WorkflowDetailOut:
    wf = _get_workflow(session, org, workflow_id)
    steps = _steps(session, wf)
    events = list(
        session.scalars(
            select(WorkflowEvent)
            .where(WorkflowEvent.workflow_id == wf.id)
            .order_by(WorkflowEvent.created_at)
        )
    )
    result = session.scalar(select(WorkflowResult).where(WorkflowResult.workflow_id == wf.id))
    return WorkflowDetailOut(
        workflow=WorkflowOut.model_validate(wf),
        steps=[WorkflowStepOut.model_validate(s) for s in steps],
        events=[WorkflowEventOut.model_validate(e) for e in events],
        result=WorkflowResultOut.model_validate(result) if result else None,
    )


# -------------------------------------------------------------------- controls
@router.post("/{workflow_id}/start", response_model=WorkflowOut)
async def start_workflow(
    workflow_id: uuid.UUID,
    session: Session = Depends(get_session),
    org: Organization = Depends(get_org),
    user: User = Depends(get_current_user),
) -> Workflow:
    wf = _get_workflow(session, org, workflow_id)
    try:
        _engine(session).start(session, wf, org, user)
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    write_audit(
        session,
        user=user,
        org_id=org.id,
        action="workflow.start",
        entity_type="workflow",
        entity_id=str(wf.id),
    )
    session.commit()
    session.refresh(wf)
    return wf


@router.post("/{workflow_id}/cancel", response_model=WorkflowOut)
def cancel_workflow(
    workflow_id: uuid.UUID,
    payload: WorkflowControlRequest,
    session: Session = Depends(get_session),
    org: Organization = Depends(get_org),
    user: User = Depends(get_current_user),
) -> Workflow:
    wf = _get_workflow(session, org, workflow_id)
    try:
        _engine(session).cancel(session, wf, payload.reason)
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    write_audit(
        session,
        user=user,
        org_id=org.id,
        action="workflow.cancel",
        entity_type="workflow",
        entity_id=str(wf.id),
    )
    session.commit()
    session.refresh(wf)
    return wf


@router.post("/{workflow_id}/resume", response_model=WorkflowOut)
def resume_workflow(
    workflow_id: uuid.UUID,
    session: Session = Depends(get_session),
    org: Organization = Depends(get_org),
    user: User = Depends(get_current_user),
) -> Workflow:
    wf = _get_workflow(session, org, workflow_id)
    try:
        _engine(session).resume(session, wf)
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    write_audit(
        session,
        user=user,
        org_id=org.id,
        action="workflow.resume",
        entity_type="workflow",
        entity_id=str(wf.id),
    )
    session.commit()
    session.refresh(wf)
    return wf


# -------------------------------------------------------------------- artifacts
@router.get("/{workflow_id}/tasks", response_model=list[WorkflowTaskOut])
def workflow_tasks(
    workflow_id: uuid.UUID,
    session: Session = Depends(get_session),
    org: Organization = Depends(get_org),
) -> list[WorkflowTaskOut]:
    wf = _get_workflow(session, org, workflow_id)
    out: list[WorkflowTaskOut] = []
    for step in _steps(session, wf):
        if step.task_id is None:
            continue
        task = session.get(Task, step.task_id)
        if task is None:
            continue
        out.append(
            WorkflowTaskOut(
                step=WorkflowStepOut.model_validate(step),
                task=TaskOut.model_validate(task).model_dump(),
            )
        )
    return out


@router.get("/{workflow_id}/runs", response_model=list[RunInfo])
def workflow_runs(
    workflow_id: uuid.UUID,
    session: Session = Depends(get_session),
    org: Organization = Depends(get_org),
) -> list[RunInfo]:
    wf = _get_workflow(session, org, workflow_id)
    steps = _steps(session, wf)
    ids = _task_ids(steps)
    if not ids:
        return []
    runs = list(
        session.scalars(
            select(AgentRun).where(AgentRun.task_id.in_(ids)).order_by(AgentRun.started_at)
        )
    )
    step_by_task = {s.task_id: s for s in steps if s.task_id is not None}
    task_by_id = {t.id: t for t in session.scalars(select(Task).where(Task.id.in_(ids)))}
    return [
        RunInfo(
            task_id=r.task_id,
            task_ref=task_by_id[r.task_id].task_ref if r.task_id in task_by_id else "",
            step_name=step_by_task[r.task_id].name if r.task_id in step_by_task else "",
            agent_id=str(r.agent_id),
            status=r.status,
            error=r.error,
            tokens_in=r.tokens_in,
            tokens_out=r.tokens_out,
            cost_usd=r.cost_usd,
        )
        for r in runs
    ]


@router.get("/{workflow_id}/messages", response_model=list[MessageOut])
def workflow_messages(
    workflow_id: uuid.UUID,
    session: Session = Depends(get_session),
    org: Organization = Depends(get_org),
) -> list[AgentMessage]:
    wf = _get_workflow(session, org, workflow_id)
    ids = _task_ids(_steps(session, wf))
    if not ids:
        return []
    return list(
        session.scalars(
            select(AgentMessage).where(AgentMessage.task_id.in_(ids)).order_by(AgentMessage.sent_at)
        )
    )


@router.get("/{workflow_id}/trace", response_model=WorkflowTraceOut)
def workflow_trace(
    workflow_id: uuid.UUID,
    session: Session = Depends(get_session),
    org: Organization = Depends(get_org),
) -> WorkflowTraceOut:
    wf = _get_workflow(session, org, workflow_id)
    steps = _steps(session, wf)
    ids = _task_ids(steps)
    tasks = (
        {t.id: t for t in session.scalars(select(Task).where(Task.id.in_(ids))) if t.id in ids}
        if ids
        else {}
    )
    runs = list(session.scalars(select(AgentRun).where(AgentRun.task_id.in_(ids)))) if ids else []
    messages = (
        list(session.scalars(select(AgentMessage).where(AgentMessage.task_id.in_(ids))))
        if ids
        else []
    )
    events = list(
        session.scalars(
            select(WorkflowEvent)
            .where(WorkflowEvent.workflow_id == wf.id)
            .order_by(WorkflowEvent.created_at)
        )
    )
    approval_ids = {
        e.payload_json.get("approval_id")
        for e in events
        if e.payload_json and isinstance(e.payload_json.get("approval_id"), str)
    }
    all_approval_ids: set[uuid.UUID] = set()
    for raw in approval_ids:
        try:
            all_approval_ids.add(uuid.UUID(raw))
        except ValueError:
            continue
    for a in session.scalars(select(Approval).where(Approval.org_id == org.id)):
        if a.entity_id in set(ids) or a.id in all_approval_ids:
            all_approval_ids.add(a.id)
    approvals = (
        list(session.scalars(select(Approval).where(Approval.id.in_(all_approval_ids))))
        if all_approval_ids
        else []
    )
    step_by_task = {s.task_id: s for s in steps if s.task_id is not None}
    return WorkflowTraceOut(
        workflow=WorkflowOut.model_validate(wf),
        steps=[WorkflowStepOut.model_validate(s) for s in steps],
        tasks=[
            WorkflowTaskOut(
                step=WorkflowStepOut.model_validate(step_by_task[t.id]),
                task=TaskOut.model_validate(t).model_dump(),
            )
            for t in sorted(tasks.values(), key=lambda x: step_by_task[x.id].step_index)
        ],
        runs=[
            RunInfo(
                task_id=r.task_id,
                task_ref=tasks[r.task_id].task_ref if r.task_id in tasks else "",
                step_name=step_by_task[r.task_id].name if r.task_id in step_by_task else "",
                agent_id=str(r.agent_id),
                status=r.status,
                error=r.error,
                tokens_in=r.tokens_in,
                tokens_out=r.tokens_out,
                cost_usd=r.cost_usd,
            )
            for r in runs
        ],
        messages=[
            {
                "id": str(m.id),
                "task_id": str(m.task_id) if m.task_id else None,
                "from_agent": m.from_agent,
                "to_agent": m.to_agent,
                "message_type": m.message_type,
                "payload": m.payload_json,
                "sent_at": m.sent_at.isoformat(),
            }
            for m in messages
        ],
        approvals=[
            {
                "id": str(a.id),
                "entity_type": a.entity_type,
                "entity_id": str(a.entity_id),
                "level": a.level,
                "status": a.status,
                "requested_by": a.requested_by,
                "reason": a.reason,
                "created_at": a.created_at.isoformat(),
            }
            for a in approvals
        ],
        events=[WorkflowEventOut.model_validate(e) for e in events],
    )


@router.get("/{workflow_id}/result", response_model=WorkflowResultOut | None)
def workflow_result(
    workflow_id: uuid.UUID,
    session: Session = Depends(get_session),
    org: Organization = Depends(get_org),
) -> WorkflowResult | None:
    wf = _get_workflow(session, org, workflow_id)
    return session.scalar(select(WorkflowResult).where(WorkflowResult.workflow_id == wf.id))
