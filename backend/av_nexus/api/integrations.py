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
from av_nexus.integrations.voxline import VoxlineUnavailableError, run_agents_from_voxline
from av_nexus.models.identity import Organization, User

router = APIRouter(prefix="/integrations/voxline", tags=["integrations"])


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
        result, outcomes = await run_agents_from_voxline(session, org, user)
    except VoxlineUnavailableError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc

    return VoxlineSyncResponse(
        brief_generated_at=result.brief_generated_at,
        warnings=result.warnings,
        runs=[
            VoxlineAgentRunOut(
                agent_id=o.agent_id,
                capability=o.capability,
                task_id=o.task_id,
                status=o.status,
                output_json=o.output_json,
                error=o.error,
            )
            for o in outcomes
        ],
    )
