"""Opportunity, company, approval, decision, dashboard DTOs."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from av_nexus.schemas.common import ORMModel


# --- Opportunities -------------------------------------------------------
class OpportunityCreate(BaseModel):
    title: str
    description: str = ""
    category: str = ""
    opportunity_score: float = Field(default=0.0, ge=0, le=100)
    market_potential: float = Field(default=0.0, ge=0, le=100)
    growth_rate: float = Field(default=0.0, ge=0, le=100)
    competition: float = Field(default=0.0, ge=0, le=100)
    entry_difficulty: float = Field(default=0.0, ge=0, le=100)
    capital_requirements: float = Field(default=0.0, ge=0, le=100)
    risk_score: float = Field(default=0.0, ge=0, le=100)
    source: str = "manual"


class OpportunityOut(ORMModel):
    id: uuid.UUID
    org_id: uuid.UUID
    title: str
    description: str
    category: str
    opportunity_score: float
    market_potential: float
    growth_rate: float
    competition: float
    entry_difficulty: float
    capital_requirements: float
    risk_score: float
    status: str
    source: str
    is_demo: bool
    created_at: datetime


# --- Companies -----------------------------------------------------------
class CompanyCreate(BaseModel):
    name: str
    industry: str
    stage: str = "idea"
    mission: str = ""
    vision: str = ""


class CompanyOut(ORMModel):
    id: uuid.UUID
    org_id: uuid.UUID
    name: str
    slug: str
    industry: str
    stage: str
    business_health_score: float
    is_demo: bool
    mission: str
    vision: str


# --- Approvals -----------------------------------------------------------
class ApprovalOut(ORMModel):
    id: uuid.UUID
    org_id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID
    level: int
    status: str
    requested_by: str
    reason: str
    created_at: datetime


class ApprovalDecision(BaseModel):
    decision: str = Field(description="approve | reject")
    reason: str = ""


# --- Decisions -----------------------------------------------------------
class DecisionOut(ORMModel):
    id: uuid.UUID
    org_id: uuid.UUID
    title: str
    decision_type: str
    status: str
    reason: str
    supporting_evidence_json: list[dict[str, Any]]
    agents_involved_json: list[str]
    confidence: float
    risk_level: str
    approved_at: datetime | None


# --- Dashboard -----------------------------------------------------------
class DashboardSummary(BaseModel):
    org_id: uuid.UUID
    org_name: str
    is_demo: bool
    today_priorities: list[dict[str, Any]]
    top_opportunities: list[dict[str, Any]]
    critical_risks: list[dict[str, Any]]
    company_health: list[dict[str, Any]]
    agent_activity: list[dict[str, Any]]
    pending_approvals: list[dict[str, Any]]
    recent_decisions: list[dict[str, Any]]
    group_performance: dict[str, Any]


# --- Activity feed -------------------------------------------------------
class ActivityItem(BaseModel):
    id: str
    actor: str
    action: str
    entity: str
    status: str
    timestamp: datetime
