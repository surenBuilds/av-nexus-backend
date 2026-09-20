"""Integration routes: sync real external data into agent runs.

Currently: Voxline AI Sales OS -> CEO/CFO/CMO/COO/Sales agents.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from av_nexus.api.deps import get_org
from av_nexus.core.security import get_current_user
from av_nexus.db.session import get_session
from av_nexus.integrations.voxline import (
    VoxlineClient,
    VoxlineUnavailableError,
    map_brief_to_agent_inputs,
)
from av_nexus.models.identity import Organization, User
from av_nexus.orchestrator.service import OrchestratorService

router = APIRouter(prefix="/integrations/voxline", tags=["integrations"])

# capability -> agent_id, used only for labeling the response; routing itself
# goes through `capability` so it stays correct even if agent_ids change.
_AGENT_CAPABILITIES: dict[str, str] = {
    "ceo": "company_strategy",
    "finance": "financial_analysis",
    "marketing": "marketing_strategy",
    "operations": "operations",
    "sales": "lead_research",
}


class VoxlineAgentRunOut(BaseModel):
    agent_id: str
    capability: str
    task_id: str | None = None
    status: str
    output_json: dict[str, Any] | None = None
    error: str | None = None


class VoxlineSyncResponse(BaseModel):
    brief_generated_at: str | None
    warnings: list[str]
    runs: list[VoxlineAgentRunOut]


def _service(session: Session) -> OrchestratorService:
    from av_nexus.agents import get_registry
    from av_nexus.llm.factory import build_llm_client

    return OrchestratorService(session, get_registry(), build_llm_client())


@router.post("/sync", response_model=VoxlineSyncResponse)
async def sync_voxline(
    session: Session = Depends(get_session),
    org: Organization = Depends(get_org),
    user: User = Depends(get_current_user),
) -> VoxlineSyncResponse:
    """Fetch the real Voxline CEO brief and run all 5 management agents on it.

    Fails loudly (502) if Voxline can't be reached rather than silently
    falling back to stale or invented data.
    """
    try:
        brief = VoxlineClient().fetch_ceo_brief()
    except VoxlineUnavailableError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc

    result = map_brief_to_agent_inputs(brief)
    service = _service(session)

    runs: list[VoxlineAgentRunOut] = []
    for agent_id, capability in _AGENT_CAPABILITIES.items():
        input_json = result.agent_inputs.get(agent_id, {})
        try:
            task = service.create_task(
                org,
                user,
                title=f"Voxline sync — {agent_id}",
                goal=f"Analyze current Voxline data for the {agent_id} function",
                capability=capability,
                approval_level=1,
                input_json=input_json,
            )
            session.commit()
            session.refresh(task)
            await service.run_task(task, org, user)
            session.refresh(task)
            runs.append(
                VoxlineAgentRunOut(
                    agent_id=agent_id,
                    capability=capability,
                    task_id=str(task.id),
                    status=task.status,
                    output_json=task.output_json,
                    error=task.error,
                )
            )
        except Exception as exc:  # noqa: BLE001 - one agent's failure shouldn't stop the rest
            session.rollback()
            runs.append(
                VoxlineAgentRunOut(
                    agent_id=agent_id,
                    capability=capability,
                    status="failed",
                    error=str(exc),
                )
            )

    return VoxlineSyncResponse(
        brief_generated_at=result.brief_generated_at,
        warnings=result.warnings,
        runs=runs,
    )
