"""Workflow persistence (Phase 2A).

Only these four new tables are added: workflows, workflow_steps, workflow_events,
workflow_results. Everything else (tasks, agent_runs, agent_messages, approvals,
decisions, opportunities, memories, knowledge entities) is reused as-is.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from av_nexus.models.base import Base, TimestampMixin, UuidPkMixin, utcnow
from av_nexus.models.enums import Priority, WorkflowStatus


class Workflow(UuidPkMixin, TimestampMixin, Base):
    __tablename__ = "workflows"

    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(255))
    objective: Mapped[str] = mapped_column(Text)
    workflow_type: Mapped[str] = mapped_column(String(64), default="opportunity_discovery")
    status: Mapped[str] = mapped_column(
        String(32), default=WorkflowStatus.CREATED.value, index=True
    )
    priority: Mapped[str] = mapped_column(String(16), default=Priority.MEDIUM.value)
    current_step: Mapped[int] = mapped_column(Integer, default=0)
    total_steps: Mapped[int] = mapped_column(Integer, default=0)
    meta_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    steps: Mapped[list[WorkflowStep]] = relationship(
        back_populates="workflow", cascade="all, delete-orphan"
    )
    events: Mapped[list[WorkflowEvent]] = relationship(
        back_populates="workflow", cascade="all, delete-orphan"
    )
    results: Mapped[list[WorkflowResult]] = relationship(
        back_populates="workflow", cascade="all, delete-orphan"
    )


class WorkflowStep(UuidPkMixin, Base):
    __tablename__ = "workflow_steps"

    workflow_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workflows.id"), index=True)
    step_index: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(128))
    agent_id: Mapped[str] = mapped_column(String(64))
    agent_name: Mapped[str] = mapped_column(String(255))
    goal: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="WAITING", index=True)
    task_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tasks.id"), nullable=True)
    task_ref: Mapped[str] = mapped_column(String(16), default="")
    approval_level: Mapped[int] = mapped_column(Integer, default=1)
    input_summary_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    output_summary_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    review_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    workflow: Mapped[Workflow] = relationship(back_populates="steps")


class WorkflowEvent(UuidPkMixin, Base):
    __tablename__ = "workflow_events"

    workflow_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workflows.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(64))
    actor: Mapped[str] = mapped_column(String(64), default="orchestrator")
    step_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    message: Mapped[str] = mapped_column(Text, default="")
    payload_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    workflow: Mapped[Workflow] = relationship(back_populates="events")


class WorkflowResult(UuidPkMixin, Base):
    __tablename__ = "workflow_results"

    workflow_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflows.id"), unique=True, index=True
    )
    objective: Mapped[str] = mapped_column(Text, default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    report_md: Mapped[str] = mapped_column(Text, default="")
    top_opportunities: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    market_findings: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    competitive_findings: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    risks: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    disagreements: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    next_actions: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    approval_requirements: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    stage_results_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    recommendation: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    workflow: Mapped[Workflow] = relationship(back_populates="results")
