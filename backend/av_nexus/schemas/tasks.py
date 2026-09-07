"""Task + protocol DTOs."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from av_nexus.schemas.common import ORMModel


class TaskCreate(BaseModel):
    title: str
    goal: str
    description: str = ""
    owner_agent_id: uuid.UUID | None = None
    capability: str | None = None  # route by capability when owner not given
    priority: str = "medium"
    deadline: datetime | None = None
    approval_level: int = Field(default=1, ge=1, le=4)
    depends_on: list[uuid.UUID] = Field(default_factory=list)


class TaskOut(ORMModel):
    id: uuid.UUID
    org_id: uuid.UUID
    task_ref: str
    title: str
    goal: str
    owner_agent_id: uuid.UUID | None
    status: str
    priority: str
    confidence: float
    approval_status: str
    approval_level: int
    error: str | None
    output_json: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime


class TaskRunResponse(BaseModel):
    task: TaskOut
    agent_runs: list[dict[str, Any]] = Field(default_factory=list)
    messages: list[dict[str, Any]] = Field(default_factory=list)


class MessageOut(ORMModel):
    id: uuid.UUID
    task_id: uuid.UUID | None
    from_agent: str
    to_agent: str
    message_type: str
    payload_json: dict[str, Any] | None
    priority: str
    sent_at: datetime


class DependencyCreate(BaseModel):
    depends_on_task_id: uuid.UUID


class OrchestratorRunRequest(BaseModel):
    goal: str
    context: dict[str, Any] = Field(default_factory=dict)
    pipeline: str = "auto"  # "auto" | "business_creation" | "custom"
    run_async: bool = False
