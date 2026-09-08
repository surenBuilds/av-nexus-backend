"""Task routes: create, list, get, run, dependencies, messages."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from av_nexus.api.deps import get_org
from av_nexus.core.security import get_current_user
from av_nexus.db.session import get_session
from av_nexus.models.agents import AgentMessage, Task
from av_nexus.models.identity import Organization, User
from av_nexus.orchestrator.service import OrchestratorService
from av_nexus.schemas.tasks import (
    DependencyCreate,
    MessageOut,
    TaskCreate,
    TaskOut,
    TaskRunResponse,
)

router = APIRouter(prefix="/tasks", tags=["tasks"])


def _service(session: Session) -> OrchestratorService:
    from av_nexus.agents import get_registry
    from av_nexus.llm.factory import build_llm_client

    return OrchestratorService(session, get_registry(), build_llm_client())


@router.post("", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
def create_task(
    payload: TaskCreate,
    session: Session = Depends(get_session),
    org: Organization = Depends(get_org),
    user: User = Depends(get_current_user),
) -> Task:
    try:
        task = _service(session).create_task(
            org,
            user,
            payload.title,
            payload.goal,
            description=payload.description,
            owner_agent_id=payload.owner_agent_id,
            capability=payload.capability,
            priority=payload.priority,
            approval_level=payload.approval_level,
            depends_on=payload.depends_on,
            input_json=payload.input_json,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    session.commit()
    session.refresh(task)
    return task


@router.get("", response_model=list[TaskOut])
def list_tasks(
    status_filter: str | None = None,
    agent_id: uuid.UUID | None = None,
    session: Session = Depends(get_session),
    org: Organization = Depends(get_org),
) -> list[Task]:
    stmt = select(Task).where(Task.org_id == org.id)
    if status_filter:
        stmt = stmt.where(Task.status == status_filter.upper())
    if agent_id is not None:
        stmt = stmt.where(Task.owner_agent_id == agent_id)
    stmt = stmt.order_by(Task.created_at.desc()).limit(100)
    return list(session.scalars(stmt))


@router.get("/{task_id}", response_model=TaskOut)
def get_task(
    task_id: uuid.UUID,
    session: Session = Depends(get_session),
    org: Organization = Depends(get_org),
) -> Task:
    task = session.get(Task, task_id)
    if task is None or task.org_id != org.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Task not found")
    return task


@router.post("/{task_id}/run", response_model=TaskRunResponse)
async def run_task(
    task_id: uuid.UUID,
    session: Session = Depends(get_session),
    org: Organization = Depends(get_org),
    user: User = Depends(get_current_user),
) -> TaskRunResponse:
    task = session.get(Task, task_id)
    if task is None or task.org_id != org.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Task not found")
    service = _service(session)
    await service.run_task(task, org, user)
    task = session.get(Task, task_id)
    assert task is not None
    from av_nexus.models.agents import AgentRun

    runs = list(session.scalars(select(AgentRun).where(AgentRun.task_id == task.id)))
    messages = list(session.scalars(select(AgentMessage).where(AgentMessage.task_id == task.id)))
    return TaskRunResponse(
        task=TaskOut.model_validate(task),
        agent_runs=[
            {
                "agent_id": str(r.agent_id),
                "status": r.status,
                "error": r.error,
                "tokens_in": r.tokens_in,
                "tokens_out": r.tokens_out,
                "cost_usd": r.cost_usd,
            }
            for r in runs
        ],
        messages=[
            {
                "from": m.from_agent,
                "to": m.to_agent,
                "type": m.message_type,
                "payload": m.payload_json,
                "sent_at": m.sent_at.isoformat(),
            }
            for m in messages
        ],
    )


@router.post("/{task_id}/dependencies", response_model=dict[str, str])
def add_dependency(
    task_id: uuid.UUID,
    payload: DependencyCreate,
    session: Session = Depends(get_session),
    org: Organization = Depends(get_org),
) -> dict[str, str]:
    task = session.get(Task, task_id)
    if task is None or task.org_id != org.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Task not found")
    try:
        _service(session).add_dependency(task, payload.depends_on_task_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    session.commit()
    return {"status": "ok"}


@router.get("/{task_id}/messages", response_model=list[MessageOut])
def task_messages(
    task_id: uuid.UUID,
    session: Session = Depends(get_session),
    org: Organization = Depends(get_org),
) -> list[AgentMessage]:
    task = session.get(Task, task_id)
    if task is None or task.org_id != org.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Task not found")
    return list(session.scalars(select(AgentMessage).where(AgentMessage.task_id == task.id)))
