"""Phase 1 data-integrity tests: no fabricated inputs in the pipeline.

- Market sizing (TAM/SAM/SOM) is derived from real scout inputs, not fixed
  100/50/10, and varies when inputs change.
- Competitive Intelligence reports an explicit intelligence gap (empty report +
  competitor_data_source: none_available) instead of invented companies.
- Validator (skeptic) inputs are threaded from real upstream stages, not
  hardcoded constants.
- Scout candidates carry a non-empty `title` (feeds Strategy priority_ranking).
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from av_nexus.agents.base import AgentContext, AgentResult
from av_nexus.agents.scout import (
    CompetitiveIntelligenceAgent,
    MarketResearchAgent,
    OpportunityScoutAgent,
)
from av_nexus.workflows import pipeline
from av_nexus.workflows.engine import _competitive_findings


def _sample_scout(
    demand: float, growth: float, entry: float, capital: float, competition: float
) -> AgentResult:
    return AgentResult.deterministic(
        result={
            "focus": "smart_construction",
            "candidates": [
                {
                    "title": "Smart Construction",
                    "industry": "smart_construction",
                    "category": "smart_construction",
                    "opportunity_score": 70.0,
                    "market_potential": demand,
                    "growth_rate": growth,
                    "entry_difficulty": entry,
                    "capital_requirements": capital,
                    "competition": competition,
                }
            ],
        },
        confidence=0.6,
        assumptions=[],
        sources=[],
    )


def _run_agent(agent: Any, inputs: dict[str, Any]) -> AgentResult:
    return asyncio.run(agent.run(AgentContext(org_id=uuid.uuid4(), inputs=inputs), "task"))


def test_market_sizing_derived_and_varies_with_input() -> None:
    low_scout = _sample_scout(
        demand=40.0, growth=25.0, entry=85.0, capital=90.0, competition=55.0
    )
    high_scout = _sample_scout(
        demand=92.0, growth=80.0, entry=30.0, capital=30.0, competition=15.0
    )
    low_ctx = pipeline._from_scout(low_scout)
    high_ctx = pipeline._from_scout(high_scout)
    assert low_ctx["competitor_count"] == 0

    low_market = _run_agent(MarketResearchAgent(), low_ctx)
    high_market = _run_agent(MarketResearchAgent(), high_ctx)
    low, high = low_market.result, high_market.result
    # no fixed 100/50/10: derived sizes differ and reflect real variation
    assert "tam" in low and "sam" in low and "som" in low
    assert high["tam"] > low["tam"]
    assert high["sam"] > low["sam"]
    assert high["som"] > low["som"]
    assert high["demand_score"] == 92.0

    low_val = pipeline._validation_inputs({"scout": low_scout, "market_research": low_market})
    high_val = pipeline._validation_inputs({"scout": high_scout, "market_research": high_market})
    assert low_val["willingness_to_pay"] != high_val["willingness_to_pay"]
    assert low_val["team_fit"] != high_val["team_fit"]
    assert high_val["willingness_to_pay"] > low_val["willingness_to_pay"]


def test_scout_candidate_carries_title() -> None:
    result = _run_agent(OpportunityScoutAgent(), {"industry_focus": "smart_construction"})
    cands = result.result["candidates"]
    assert cands, "scout produced no candidates"
    for c in cands[:2]:
        assert isinstance(c.get("title"), str) and c["title"]


def test_competitor_intelligence_reports_gap_not_fabrication() -> None:
    result = _run_agent(CompetitiveIntelligenceAgent(), {"competitors": []})
    assert result.result["competitor_report"] == []
    assert result.result["top_threat"] is None
    assert result.result["competitor_data_source"] == "none_available"
    note = result.result["note"].lower()
    assert "gap" in note or "invented" in note


def test_competitive_findings_honest_when_no_data() -> None:
    ci = AgentResult.deterministic(
        result={
            "competitor_report": [],
            "top_threat": None,
            "competitor_data_source": "none_available",
            "note": "gap",
        },
        confidence=0.35,
        assumptions=[],
        sources=[],
    )
    findings = _competitive_findings({"competitive_intelligence": ci})
    assert findings[0]["top_threat"] is None
    assert findings[0]["report"] == []