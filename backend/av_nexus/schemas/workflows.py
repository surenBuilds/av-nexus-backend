"""Workflow DTOs (Phase 2A)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from av_nexus.schemas.common import ORMModel


class WorkflowCreate(BaseModel):
    objective: str = Field(min_length=3, max_length=1000)
    workflow_type: str = "opportunity_discovery"
    company_id: uuid.UUID | None = None
    priority: str = "medium"
    context: dict[str, str] = Field(default_factory=dict)


class WorkflowOut(ORMModel):
    id: uuid.UUID
    org_id: uuid.UUID
    created_by: uuid.UUID | None
    name: str
    objective: str
    workflow_type: str
    status: str
    priority: str
    current_step: int
    total_steps: int
    meta_json: dict[str, Any] | None
    error: str
    confidence: float
    cancel_requested: bool
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class WorkflowStepOut(ORMModel):
    id: uuid.UUID
    workflow_id: uuid.UUID
    step_index: int
    name: str
    agent_id: str
    agent_name: str
    goal: str
    status: str
    task_id: uuid.UUID | None
    task_ref: str
    approval_level: int
    input_summary_json: dict[str, Any] | None
    output_summary_json: dict[str, Any] | None
    review_json: dict[str, Any] | None
    error: str | None
    started_at: datetime | None
    ended_at: datetime | None


class WorkflowEventOut(ORMModel):
    id: uuid.UUID
    workflow_id: uuid.UUID
    event_type: str
    actor: str
    step_index: int | None
    message: str
    payload_json: dict[str, Any] | None
    created_at: datetime


class WorkflowResultOut(ORMModel):
    id: uuid.UUID
    workflow_id: uuid.UUID
    objective: str
    summary: str
    report_md: str
    top_opportunities: list[dict[str, Any]]
    market_findings: list[dict[str, Any]]
    competitive_findings: list[dict[str, Any]]
    risks: list[dict[str, Any]]
    disagreements: list[dict[str, Any]]
    next_actions: list[dict[str, Any]]
    approval_requirements: list[dict[str, Any]]
    stage_results_json: list[dict[str, Any]]
    confidence: float
    recommendation: str
    created_at: datetime


class WorkflowDetailOut(BaseModel):
    workflow: WorkflowOut
    steps: list[WorkflowStepOut]
    events: list[WorkflowEventOut]
    result: WorkflowResultOut | None


class WorkflowTaskOut(BaseModel):
    step: WorkflowStepOut
    task: dict[str, Any]


class RunInfo(BaseModel):
    task_id: uuid.UUID
    task_ref: str
    step_name: str
    agent_id: str | None
    status: str
    error: str | None
    tokens_in: int
    tokens_out: int
    cost_usd: float


class WorkflowTraceOut(BaseModel):
    workflow: WorkflowOut
    steps: list[WorkflowStepOut]
    tasks: list[WorkflowTaskOut]
    runs: list[RunInfo]
    messages: list[dict[str, Any]]
    approvals: list[dict[str, Any]]
    events: list[WorkflowEventOut]


class WorkflowControlRequest(BaseModel):
    reason: str = ""
    context: dict[str, str] = Field(default_factory=dict)
