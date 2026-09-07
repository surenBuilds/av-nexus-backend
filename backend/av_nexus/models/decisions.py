"""Decisions + approvals (human control layer)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from av_nexus.models.base import Base, TimestampMixin, UuidPkMixin
from av_nexus.models.enums import (
    DecisionStatus,
    DecisionType,
    EntityType,
    RiskLevel,
)


class Decision(UuidPkMixin, TimestampMixin, Base):
    __tablename__ = "decisions"

    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    decision_type: Mapped[str] = mapped_column(String(32), default=DecisionType.OTHER.value)
    status: Mapped[str] = mapped_column(String(16), default=DecisionStatus.PROPOSED.value)
    reason: Mapped[str] = mapped_column(Text, default="")
    supporting_evidence_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    agents_involved_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    risk_level: Mapped[str] = mapped_column(String(16), default=RiskLevel.MEDIUM.value)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Approval(UuidPkMixin, TimestampMixin, Base):
    __tablename__ = "approvals"

    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    entity_type: Mapped[str] = mapped_column(String(32), default=EntityType.TASK.value)
    entity_id: Mapped[uuid.UUID] = mapped_column(index=True)
    level: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    requested_by: Mapped[str] = mapped_column(String(255), default="")
    decided_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
