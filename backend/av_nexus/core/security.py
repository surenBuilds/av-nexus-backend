"""Security: password hashing, JWT, current-user dependency, role gates, audit."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from av_nexus.config import settings
from av_nexus.db.session import get_session
from av_nexus.models.audit import AuditLog
from av_nexus.models.enums import Role
from av_nexus.models.identity import Organization, User

_bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(user_id: uuid.UUID, role: str) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=settings.jwt_expiry_minutes)
    payload = {"sub": str(user_id), "role": role, "exp": expire}
    return cast(str, jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm))


def decode_token(token: str) -> dict[str, Any] | None:
    try:
        return cast(
            dict[str, Any],
            jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]),
        )
    except JWTError:
        return None


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: Session = Depends(get_session),
) -> User:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    payload = decode_token(creds.credentials)
    if not payload:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")
    try:
        user = session.get(User, uuid.UUID(str(payload["sub"])))
    except (KeyError, ValueError, TypeError, AttributeError):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token") from None
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Inactive user")
    return user


def require_roles(*roles: Role) -> Callable[[User], User]:
    def _dep(user: User = Depends(get_current_user)) -> User:
        if user.role not in {r.value for r in roles}:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient role")
        return user

    return _dep


def require_level4(user: User) -> None:
    """Level-4 gates are reserved for the Chairman / level-4-capable users."""
    if not user.can_authorize_level4:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "This action requires Chairman (level 4) approval authority",
        )


def get_org_for_user(session: Session, user: User) -> Organization | None:
    stmt = (
        select(Organization)
        .filter(Organization.owner_id == user.id)
        .order_by(Organization.created_at)
    )
    return session.scalar(stmt)


def write_audit(
    session: Session,
    *,
    user: User | None,
    org_id: uuid.UUID | None,
    action: str,
    entity_type: str = "",
    entity_id: str = "",
    details: dict[str, Any] | None = None,
) -> None:
    session.add(
        AuditLog(
            user_id=user.id if user else None,
            org_id=org_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            details_json=details,
        )
    )
    session.flush()
