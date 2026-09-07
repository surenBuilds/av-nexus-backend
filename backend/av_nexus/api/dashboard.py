"""Dashboard (command center) route."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from av_nexus.api.deps import get_org
from av_nexus.db.session import get_session
from av_nexus.models.agents import Agent, AgentRun, Task
from av_nexus.models.decisions import Approval, Decision
from av_nexus.models.enums import TaskStatus
from av_nexus.models.identity import Company, Organization
from av_nexus.models.opportunities import Opportunity
from av_nexus.models.risks import Risk
from av_nexus.schemas.domain import DashboardSummary

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardSummary)
def dashboard(
    session: Session = Depends(get_session), org: Organization = Depends(get_org)
) -> DashboardSummary:
    companies = list(session.scalars(select(Company).where(Company.org_id == org.id)))
    opportunities = list(
        session.scalars(
            select(Opportunity)
            .where(Opportunity.org_id == org.id)
            .order_by(Opportunity.opportunity_score.desc())
            .limit(5)
        )
    )
    risks = list(
        session.scalars(
            select(Risk)
            .where(Risk.org_id == org.id, Risk.status == "open")
            .order_by(Risk.created_at.desc())
        )
    )
    critical_risks = [r for r in risks if r.level in ("HIGH", "CRITICAL")]
    pending_approvals = list(
        session.scalars(
            select(Approval)
            .where(Approval.org_id == org.id, Approval.status == "pending")
            .order_by(Approval.created_at.desc())
            .limit(10)
        )
    )
    recent_decisions = list(
        session.scalars(
            select(Decision)
            .where(Decision.org_id == org.id)
            .order_by(Decision.created_at.desc())
            .limit(10)
        )
    )
    agents = list(session.scalars(select(Agent)))
    running_tasks = list(
        session.scalars(
            select(Task).where(
                Task.org_id == org.id,
                Task.status == TaskStatus.RUNNING.value,
            )
        )
    )
    tasks_completed = (
        session.scalar(
            select(func.count())
            .select_from(Task)
            .where(Task.org_id == org.id, Task.status == TaskStatus.COMPLETED.value)
        )
        or 0
    )
    runs = list(
        session.scalars(
            select(AgentRun)
            .join(Task, AgentRun.task_id == Task.id)
            .where(Task.org_id == org.id)
            .order_by(AgentRun.started_at.desc())
            .limit(10)
        )
    )

    return DashboardSummary(
        org_id=org.id,
        org_name=org.name,
        is_demo=org.is_demo,
        today_priorities=[
            {"title": "Review pending approvals", "count": len(pending_approvals)},
            {"title": "Deploy next sprint for flagged projects", "count": len(critical_risks)},
            {"title": "Run weekly portfolio review", "count": len(companies)},
        ],
        top_opportunities=[
            {
                "title": o.title,
                "score": o.opportunity_score,
                "status": o.status,
                "category": o.category,
            }
            for o in opportunities
        ],
        critical_risks=[
            {
                "title": r.title,
                "level": r.level,
                "category": r.category,
                "company": next((c.name for c in companies if c.id == r.company_id), None),
            }
            for r in critical_risks
        ],
        company_health=[
            {
                "name": c.name,
                "score": c.business_health_score,
                "status": _health_label(c.business_health_score),
                "stage": c.stage,
                "is_demo": c.is_demo,
            }
            for c in companies
        ],
        agent_activity=[
            {
                "agent_id": a.agent_id,
                "name": a.name,
                "status": a.status,
                "tasks_completed": a.tasks_completed,
                "performance_score": a.performance_score,
            }
            for a in agents
        ],
        pending_approvals=[
            {
                "id": str(a.id),
                "level": a.level,
                "status": a.status,
                "requested_by": a.requested_by,
                "reason": a.reason,
                "entity_type": a.entity_type,
            }
            for a in pending_approvals
        ],
        recent_decisions=[
            {
                "title": d.title,
                "status": d.status,
                "decision_type": d.decision_type,
                "confidence": d.confidence,
                "risk_level": d.risk_level,
            }
            for d in recent_decisions
        ],
        group_performance={
            "companies": len(companies),
            "opportunities": len(
                list(session.scalars(select(Opportunity).where(Opportunity.org_id == org.id)))
            ),
            "tasks_completed": tasks_completed or 0,
            "tasks_running": len(running_tasks),
            "runs_tracked": len(runs),
            "avg_agent_performance": round(
                sum(a.performance_score for a in agents) / max(len(agents), 1), 1
            ),
        },
    )


def _health_label(score: float) -> str:
    if score >= 70:
        return "GREEN"
    if score >= 45:
        return "YELLOW"
    return "RED"
