"""Approval routes (the human control layer)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from av_nexus.api.deps import get_org
from av_nexus.core.security import get_current_user, write_audit
from av_nexus.db.session import get_session
from av_nexus.models.decisions import Approval
from av_nexus.models.identity import Organization, User
from av_nexus.orchestrator.service import OrchestratorService
from av_nexus.schemas.domain import ApprovalDecision, ApprovalOut

router = APIRouter(prefix="/approvals", tags=["approvals"])


def _service(session: Session) -> OrchestratorService:
    from av_nexus.agents import get_registry
    from av_nexus.llm.factory import build_llm_client

    return OrchestratorService(session, get_registry(), build_llm_client())


@router.get("", response_model=list[ApprovalOut])
def list_approvals(
    status_filter: str = "pending",
    session: Session = Depends(get_session),
    org: Organization = Depends(get_org),
) -> list[Approval]:
    stmt = select(Approval).where(Approval.org_id == org.id)
    if status_filter:
        stmt = stmt.where(Approval.status == status_filter)
    return list(session.scalars(stmt.order_by(Approval.created_at.desc()).limit(100)))


@router.post("/{approval_id}/approve", response_model=ApprovalOut)
def approve(
    approval_id: uuid.UUID,
    payload: ApprovalDecision,
    session: Session = Depends(get_session),
    org: Organization = Depends(get_org),
    user: User = Depends(get_current_user),
) -> Approval:
    approval = session.get(Approval, approval_id)
    if approval is None or approval.org_id != org.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Approval not found")
    try:
        _service(session).approve_approval(org, approval, user, payload.reason)
    except PermissionError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    write_audit(
        session,
        user=user,
        org_id=org.id,
        action="approval.approve",
        entity_type="approval",
        entity_id=str(approval.id),
    )
    session.commit()
    session.refresh(approval)
    return approval


@router.post("/{approval_id}/reject", response_model=ApprovalOut)
def reject(
    approval_id: uuid.UUID,
    payload: ApprovalDecision,
    session: Session = Depends(get_session),
    org: Organization = Depends(get_org),
    user: User = Depends(get_current_user),
) -> Approval:
    approval = session.get(Approval, approval_id)
    if approval is None or approval.org_id != org.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Approval not found")
    try:
        _service(session).reject_approval(org, approval, user, payload.reason)
    except PermissionError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    write_audit(
        session,
        user=user,
        org_id=org.id,
        action="approval.reject",
        entity_type="approval",
        entity_id=str(approval.id),
    )
    session.commit()
    session.refresh(approval)
    return approval
