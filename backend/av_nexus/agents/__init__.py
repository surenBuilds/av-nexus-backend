"""Composition root for the full agent network."""

from __future__ import annotations

from av_nexus.agents.base import AgentContext, AgentResult, BaseAgent
from av_nexus.agents.builder import ValidationAgent, VentureBuilderAgent
from av_nexus.agents.group_strategy import InvestmentAgent, MnAAgent, StrategyAgent
from av_nexus.agents.guardian import (
    CriticAgent,
    DataAnalyticsAgent,
    LegalComplianceAgent,
    RiskAgent,
)
from av_nexus.agents.management import (
    CeoAgent,
    FinanceAgent,
    MarketingAgent,
    OperationsAgent,
    SalesAgent,
)
from av_nexus.agents.registry import AgentRegistry
from av_nexus.agents.scout import (
    CompetitiveIntelligenceAgent,
    InnovationAgent,
    MarketResearchAgent,
    OpportunityScoutAgent,
)

__all__ = [
    "AgentContext",
    "AgentResult",
    "BaseAgent",
    "AgentRegistry",
    "build_registry",
    "ALL_AGENTS",
]


def build_registry() -> AgentRegistry:
    registry = AgentRegistry()
    for agent in ALL_AGENTS:
        registry.register(agent)
    return registry


ALL_AGENTS: list[BaseAgent] = [
    StrategyAgent(),
    OpportunityScoutAgent(),
    MarketResearchAgent(),
    CompetitiveIntelligenceAgent(),
    InnovationAgent(),
    ValidationAgent(),
    VentureBuilderAgent(),
    CeoAgent(),
    FinanceAgent(),
    MarketingAgent(),
    OperationsAgent(),
    SalesAgent(),
    RiskAgent(),
    LegalComplianceAgent(),
    InvestmentAgent(),
    MnAAgent(),
    DataAnalyticsAgent(),
    CriticAgent(),
]

_registry: AgentRegistry | None = None


def get_registry() -> AgentRegistry:
    """Lazy singleton used by the API layer."""
    global _registry
    if _registry is None:
        _registry = build_registry()
    return _registry
