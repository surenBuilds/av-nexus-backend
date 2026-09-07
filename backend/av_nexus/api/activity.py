"""Decisions + activity feed routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from av_nexus.api.deps import get_org
from av_nexus.core.security import get_current_user
from av_nexus.db.session import get_session
from av_nexus.models.agents import Agent, AgentRun, Task
from av_nexus.models.decisions import Decision
from av_nexus.models.identity import Organization, User
from av_nexus.schemas.domain import ActivityItem, DecisionOut

router = APIRouter(tags=["activity"])


@router.get("/decisions", response_model=list[DecisionOut])
def list_decisions(
    session: Session = Depends(get_session),
    org: Organization = Depends(get_org),
    user: User = Depends(get_current_user),
) -> list[Decision]:
    stmt = (
        select(Decision)
        .where(Decision.org_id == org.id)
        .order_by(Decision.created_at.desc())
        .limit(50)
    )
    return list(session.scalars(stmt))


@router.get("/activity", response_model=list[ActivityItem])
def recent_activity(
    session: Session = Depends(get_session),
    org: Organization = Depends(get_org),
    user: User = Depends(get_current_user),
) -> list[ActivityItem]:
    joins = (
        select(AgentRun, Agent, Task)
        .join(Agent, AgentRun.agent_id == Agent.id)
        .join(Task, AgentRun.task_id == Task.id)
        .where(Task.org_id == org.id)
        .order_by(AgentRun.started_at.desc())
        .limit(40)
    )
    items = [
        ActivityItem(
            id=str(run.id),
            actor=agent.name,
            action=task.title,
            entity=task.task_ref,
            status=run.status,
            timestamp=run.started_at,
        )
        for run, agent, task in session.execute(joins)
    ]
    return items[:30]
