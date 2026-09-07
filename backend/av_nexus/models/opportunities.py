"""Opportunities, markets, competitors."""

from __future__ import annotations

import uuid

from sqlalchemy import JSON, Boolean, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from av_nexus.models.base import Base, TimestampMixin, UuidPkMixin
from av_nexus.models.enums import OpportunityStatus


class Opportunity(UuidPkMixin, TimestampMixin, Base):
    __tablename__ = "opportunities"

    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(128), default="")
    opportunity_score: Mapped[float] = mapped_column(Float, default=0.0)
    market_potential: Mapped[float] = mapped_column(Float, default=0.0)
    growth_rate: Mapped[float] = mapped_column(Float, default=0.0)
    competition: Mapped[float] = mapped_column(Float, default=0.0)
    entry_difficulty: Mapped[float] = mapped_column(Float, default=0.0)
    capital_requirements: Mapped[float] = mapped_column(Float, default=0.0)
    risk_score: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(16), default=OpportunityStatus.DISCOVERED.value)
    source: Mapped[str] = mapped_column(String(128), default="")
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)


class Market(UuidPkMixin, TimestampMixin, Base):
    __tablename__ = "markets"

    name: Mapped[str] = mapped_column(String(255))
    industry: Mapped[str] = mapped_column(String(255), default="")
    region: Mapped[str] = mapped_column(String(128), default="")
    tam: Mapped[float | None] = mapped_column(Float, nullable=True)
    sam: Mapped[float | None] = mapped_column(Float, nullable=True)
    som: Mapped[float | None] = mapped_column(Float, nullable=True)
    growth_rate_pct: Mapped[float] = mapped_column(Float, default=0.0)
    notes: Mapped[str] = mapped_column(Text, default="")
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)


class Competitor(UuidPkMixin, TimestampMixin, Base):
    __tablename__ = "competitors"

    name: Mapped[str] = mapped_column(String(255))
    industry: Mapped[str] = mapped_column(String(255), default="")
    company_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("companies.id"), nullable=True)
    products: Mapped[str] = mapped_column(Text, default="")
    pricing: Mapped[str] = mapped_column(Text, default="")
    strengths_j: Mapped[list[str]] = mapped_column(JSON, default=list)
    weaknesses_j: Mapped[list[str]] = mapped_column(JSON, default=list)
    threat_score: Mapped[float] = mapped_column(Float, default=0.0)
    recent_developments: Mapped[str] = mapped_column(Text, default="")
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
