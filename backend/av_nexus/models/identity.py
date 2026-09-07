"""Identity + tenant + company models."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import JSON, Boolean, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from av_nexus.models.base import Base, TimestampMixin, UuidPkMixin
from av_nexus.models.enums import CompanyStage, Role


class User(UuidPkMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(32), default=Role.ANALYST.value)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    can_authorize_level4: Mapped[bool] = mapped_column(Boolean, default=False)

    organizations: Mapped[list[Organization]] = relationship(back_populates="owner")


class Organization(UuidPkMixin, TimestampMixin, Base):
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(255))
    slug: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)

    owner: Mapped[User] = relationship(back_populates="organizations")
    companies: Mapped[list[Company]] = relationship(back_populates="organization")


class Company(UuidPkMixin, TimestampMixin, Base):
    __tablename__ = "companies"

    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    slug: Mapped[str] = mapped_column(String(255), index=True)
    industry: Mapped[str] = mapped_column(String(255), default="")
    stage: Mapped[str] = mapped_column(String(32), default=CompanyStage.IDEA.value)
    mission: Mapped[str] = mapped_column(Text, default="")
    vision: Mapped[str] = mapped_column(Text, default="")
    business_health_score: Mapped[float] = mapped_column(Float, default=50.0)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    organization: Mapped[Organization] = relationship(back_populates="companies")
    products: Mapped[list[Product]] = relationship(back_populates="company")
    projects: Mapped[list[Project]] = relationship(back_populates="company")
    kpis: Mapped[list[Kpi]] = relationship(back_populates="company")
    financial_metrics: Mapped[list[FinancialMetric]] = relationship(back_populates="company")


# Cross-module forward refs for relationship annotations (resolved late by the
# SQLAlchemy registry; also lets mypy resolve names).
from av_nexus.models.catalog import FinancialMetric, Kpi, Product, Project  # noqa: E402,F401
