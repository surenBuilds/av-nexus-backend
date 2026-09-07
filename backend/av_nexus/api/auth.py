"""Auth routes: register, login, me."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from av_nexus.config import settings
from av_nexus.core.security import (
    create_access_token,
    get_current_user,
    get_org_for_user,
    hash_password,
    verify_password,
    write_audit,
)
from av_nexus.db.session import get_session
from av_nexus.models.enums import Role
from av_nexus.models.identity import Organization, User
from av_nexus.schemas.auth import (
    LoginRequest,
    MeResponse,
    OrganizationOut,
    RegisterRequest,
    TokenResponse,
    UserOut,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, session: Session = Depends(get_session)) -> TokenResponse:
    existing = session.scalar(select(User).where(User.email == payload.email))
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")
    user = User(
        email=payload.email,
        password_hash=hash_password(payload.password),
        full_name=payload.full_name,
        role=Role.CHAIRMAN.value,  # first user of their org is the Chairman
        can_authorize_level4=True,
    )
    session.add(user)
    session.flush()
    slug = slugify(payload.org_name or "Artiswon")
    org = Organization(name=payload.org_name or "Artiswon", slug=slug, owner_id=user.id)
    session.add(org)
    write_audit(
        session,
        user=user,
        org_id=org.id,
        action="auth.register",
        entity_type="user",
        entity_id=str(user.id),
    )
    session.commit()
    token = create_access_token(user.id, user.role)
    return TokenResponse(access_token=token, expires_in=settings.jwt_expiry_minutes * 60)


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, session: Session = Depends(get_session)) -> TokenResponse:
    user = session.scalar(select(User).where(User.email == payload.email))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Inactive user")
    write_audit(
        session,
        user=user,
        org_id=None,
        action="auth.login",
        entity_type="user",
        entity_id=str(user.id),
    )
    session.commit()
    return TokenResponse(
        access_token=create_access_token(user.id, user.role),
        expires_in=settings.jwt_expiry_minutes * 60,
    )


@router.get("/me", response_model=MeResponse)
def me(
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> MeResponse:
    org = get_org_for_user(session, user)
    return MeResponse(
        user=UserOut.model_validate(user),
        organization=OrganizationOut.model_validate(org) if org else None,
    )


def slugify(name: str) -> str:
    s = "".join(c if c.isalnum() else "-" for c in name.lower()).strip("-")
    return (s or "org") + "-" + uuid.uuid4().hex[:6]
