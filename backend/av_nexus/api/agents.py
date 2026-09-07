"""Agent registry routes + agent detail (runs, messages)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from av_nexus.agents import get_registry
from av_nexus.core.security import get_current_user, require_roles
from av_nexus.db.session import get_session
from av_nexus.models.agents import Agent, AgentMessage, AgentRun, Task
from av_nexus.models.enums import Role
from av_nexus.models.identity import User
from av_nexus.schemas.agents import AgentOut, AgentRegisterRequest, AgentRunOut
from av_nexus.schemas.tasks import MessageOut

router = APIRouter(prefix="/agents", tags=["agents"])


@router.get("", response_model=list[AgentOut])
def list_agents(
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[AgentOut]:
    registry = get_registry()
    rows = {a.agent_id: a for a in session.scalars(select(Agent))}
    agents = []
    for meta in registry.snapshot():
        row = rows.get(str(meta["agent_id"]))
        if row is None:  # registered at runtime but not yet synced to DB
            continue
        agents.append(
            AgentOut(
                id=row.id,
                agent_id=row.agent_id,
                name=row.name,
                role=row.role,
                description=row.description,
                capabilities_json=row.capabilities_json,
                tools_json=row.tools_json,
                permissions_json=row.permissions_json,
                status=row.status,
                performance_score=row.performance_score,
                tasks_completed=row.tasks_completed,
                is_active=row.is_active,
            )
        )
    return agents


@router.get("/{agent_id}", response_model=AgentOut)
def get_agent(
    agent_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> Agent:
    row = session.scalar(select(Agent).where(Agent.agent_id == agent_id))
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Agent not registered")
    return row


@router.get("/{agent_id}/runs", response_model=list[AgentRunOut])
def agent_runs(
    agent_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[AgentRunOut]:
    row = session.scalar(select(Agent).where(Agent.agent_id == agent_id))
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Agent not registered")
    joins = (
        select(AgentRun, Task)
        .join(Task, AgentRun.task_id == Task.id)
        .where(AgentRun.agent_id == row.id)
        .order_by(AgentRun.started_at.desc())
        .limit(20)
    )
    return [
        AgentRunOut(
            id=run.id,
            task_id=run.task_id,
            task_ref=task.task_ref,
            task_title=task.title,
            status=run.status,
            error=run.error,
            tokens_in=run.tokens_in,
            tokens_out=run.tokens_out,
            cost_usd=run.cost_usd,
            started_at=run.started_at,
            ended_at=run.ended_at,
        )
        for run, task in session.execute(joins)
    ]


@router.get("/{agent_id}/messages", response_model=list[MessageOut])
def agent_messages(
    agent_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[AgentMessage]:
    row = session.scalar(select(Agent).where(Agent.agent_id == agent_id))
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Agent not registered")
    stmt = (
        select(AgentMessage)
        .where(
            or_(
                AgentMessage.from_agent == agent_id,
                AgentMessage.to_agent == agent_id,
            )
        )
        .order_by(AgentMessage.sent_at.desc())
        .limit(25)
    )
    return list(session.scalars(stmt))


@router.post("", response_model=AgentOut, status_code=status.HTTP_201_CREATED)
def register_agent(
    payload: AgentRegisterRequest,
    session: Session = Depends(get_session),
    user: User = Depends(require_roles(Role.ADMIN, Role.CHAIRMAN)),
) -> Agent:
    existing = session.scalar(select(Agent).where(Agent.agent_id == payload.agent_id))
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Agent already registered")
    row = Agent(
        agent_id=payload.agent_id,
        name=payload.name,
        role=payload.role,
        description=payload.description,
        capabilities_json=payload.capabilities,
        tools_json=payload.tools,
        permissions_json=payload.permissions,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row
