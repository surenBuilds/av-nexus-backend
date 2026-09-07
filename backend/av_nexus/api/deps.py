"""Shared API dependencies."""

from __future__ import annotations

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from av_nexus.core.security import get_current_user, get_org_for_user
from av_nexus.db.session import get_session
from av_nexus.models.identity import Organization, User


def get_org(
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> Organization:
    org = get_org_for_user(session, user)
    if org is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No organization for user")
    return org
