"""Agent registry DTOs."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel

from av_nexus.schemas.common import ORMModel


class AgentOut(ORMModel):
    id: uuid.UUID
    agent_id: str
    name: str
    role: str
    description: str
    capabilities_json: list[str]
    tools_json: list[str]
    permissions_json: list[str]
    status: str
    performance_score: float
    tasks_completed: int
    is_active: bool


class AgentRunOut(BaseModel):
    id: uuid.UUID
    task_id: uuid.UUID
    task_ref: str
    task_title: str
    status: str
    error: str | None
    tokens_in: int
    tokens_out: int
    cost_usd: float
    started_at: datetime
    ended_at: datetime | None


class AgentRegisterRequest(BaseModel):
    agent_id: str = "custom_agent"
    name: str = "Custom Agent"
    role: str = "Specialist"
    description: str = ""
    capabilities: list[str] = []
    permissions: list[str] = []
    tools: list[str] = []
