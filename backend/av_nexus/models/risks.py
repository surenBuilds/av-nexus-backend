"""Risks."""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from av_nexus.models.base import Base, TimestampMixin, UuidPkMixin
from av_nexus.models.enums import RiskCategory, RiskLevel


class Risk(UuidPkMixin, TimestampMixin, Base):
    __tablename__ = "risks"

    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    company_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("companies.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(32), default=RiskCategory.MARKET.value)
    level: Mapped[str] = mapped_column(String(16), default=RiskLevel.MEDIUM.value)
    mitigation: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="open")
    owner_agent: Mapped[str] = mapped_column(String(64), default="risk")
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
