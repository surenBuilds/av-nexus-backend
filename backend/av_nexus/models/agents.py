"""Agents, tasks, dependencies, messages, agent runs."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from av_nexus.models.base import Base, TimestampMixin, UuidPkMixin, utcnow
from av_nexus.models.enums import (
    AgentStatus,
    ApprovalStatus,
    Priority,
    TaskStatus,
)


def short_ref(prefix: str = "T") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:6].upper()}"


class Agent(UuidPkMixin, TimestampMixin, Base):
    """Registry row for an agent."""

    __tablename__ = "agents"

    agent_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    capabilities_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    tools_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    permissions_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(32), default=AgentStatus.IDLE.value)
    performance_score: Mapped[float] = mapped_column(Float, default=0.0)
    tasks_completed: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    capabilities: Mapped[list[AgentCapability]] = relationship(
        back_populates="agent", cascade="all, delete-orphan"
    )
    runs: Mapped[list[AgentRun]] = relationship(back_populates="agent")


class AgentCapability(Base):
    __tablename__ = "agent_capabilities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    agent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agents.id"), index=True)
    capability: Mapped[str] = mapped_column(String(128))

    agent: Mapped[Agent] = relationship(back_populates="capabilities")


class Task(UuidPkMixin, TimestampMixin, Base):
    __tablename__ = "tasks"

    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    task_ref: Mapped[str] = mapped_column(String(16), default=lambda: short_ref())
    title: Mapped[str] = mapped_column(String(255))
    goal: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text, default="")
    owner_agent_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("agents.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default=TaskStatus.QUEUED.value)
    priority: Mapped[str] = mapped_column(String(16), default=Priority.MEDIUM.value)
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    input_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    output_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    approval_status: Mapped[str] = mapped_column(String(16), default=ApprovalStatus.NONE.value)
    approval_level: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    dependencies: Mapped[list[TaskDependency]] = relationship(
        foreign_keys="TaskDependency.task_id",
        back_populates="task",
        cascade="all, delete-orphan",
    )
    messages: Mapped[list[AgentMessage]] = relationship(back_populates="task")


class TaskDependency(Base):
    __tablename__ = "task_dependencies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tasks.id"), index=True)
    depends_on_task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tasks.id"))

    task: Mapped[Task] = relationship(foreign_keys=[task_id], back_populates="dependencies")


class AgentMessage(UuidPkMixin, Base):
    __tablename__ = "agent_messages"

    task_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tasks.id"), nullable=True, index=True
    )
    from_agent: Mapped[str] = mapped_column(String(64))
    to_agent: Mapped[str] = mapped_column(String(64))
    message_type: Mapped[str] = mapped_column(String(32))
    payload_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    priority: Mapped[str] = mapped_column(String(16), default=Priority.MEDIUM.value)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    task: Mapped[Task | None] = relationship(back_populates="messages")


class AgentRun(UuidPkMixin, Base):
    __tablename__ = "agent_runs"

    agent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agents.id"), index=True)
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tasks.id"), index=True)
    status: Mapped[str] = mapped_column(String(32), default=TaskStatus.RUNNING.value)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    trace_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    agent: Mapped[Agent] = relationship(back_populates="runs")
