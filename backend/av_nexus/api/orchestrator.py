"""Orchestrator route: run the business-creation / custom pipeline as a goal."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from av_nexus.api.deps import get_org
from av_nexus.core.security import get_current_user, write_audit
from av_nexus.db.session import get_session
from av_nexus.models.identity import Organization, User
from av_nexus.orchestrator.service import OrchestratorService
from av_nexus.schemas.tasks import OrchestratorRunRequest

router = APIRouter(prefix="/orchestrator", tags=["orchestrator"])


def _service(session: Session) -> OrchestratorService:
    from av_nexus.agents import get_registry
    from av_nexus.llm.factory import build_llm_client

    return OrchestratorService(session, get_registry(), build_llm_client())


@router.post("/run")
async def run_pipeline(
    payload: OrchestratorRunRequest,
    session: Session = Depends(get_session),
    org: Organization = Depends(get_org),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    pipeline = payload.pipeline
    if pipeline == "auto":
        pipeline = _recommend_pipeline(payload.goal)
    try:
        outcome = await _service(session).orchestrate(
            org, user, payload.goal, pipeline, payload.context or {}
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    write_audit(
        session,
        user=user,
        org_id=org.id,
        action="orchestrator.run",
        entity_type="pipeline",
        details={"pipeline": pipeline, "goal": payload.goal},
    )
    session.commit()
    return _shape_outcome(outcome)


def _recommend_pipeline(goal: str) -> str:
    g = goal.lower()
    create_keywords = (
        "create a business",
        "new business",
        "startup",
        "build a company",
        "create business",
    )
    research_keywords = (
        "research market",
        "market research",
        "validate",
    )
    if any(k in g for k in create_keywords):
        return "business_creation"
    if any(k in g for k in ("blueprint", "venture builder")):
        return "venture_blueprint"
    if any(k in g for k in research_keywords):
        return "business_creation"  # scout→research subset is usable
    raise ValueError("auto could not infer a pipeline; set pipeline explicitly")


def _shape_outcome(outcome: dict[str, Any]) -> dict[str, Any]:
    return {
        "pipeline": outcome["pipeline"],
        "goal": outcome["goal"],
        "tasks": outcome["tasks"],
        "conflicts": outcome["conflicts"],
        "recommendation": outcome["recommendation"],
        "confidence": outcome["confidence"],
        "risk_level": outcome["risk_level"],
        "stage_results": {
            name: {"result": r.result, "confidence": r.confidence, "mode": r.mode}
            for name, r in outcome["stages"].items()
        },
        "decision_id": outcome["decision_id"],
        "approval_id": outcome["approval_id"],
        "approval_status": outcome["approval_status"],
    }
