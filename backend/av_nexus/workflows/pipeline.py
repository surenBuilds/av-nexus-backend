"""Opportunity Discovery workflow definition (Phase 2A).

DAG (dependencies = stage names that must COMPLETE first):

  scout
  └─┬ market_research           (parallel with competitive_intelligence)
    └─ competitive_intelligence
  validation  ◄── deps [market_research, competitive_intelligence]
  risk        ◄── deps [market_research, competitive_intelligence]
  critic      ◄── deps [validation, risk]      (reviews consolidated picture)
  strategy    ◄── deps [critic]                (Chief Strategy Officer)
  ── orchestrator synthesis → approval gate → chairman

Every stage is advisory (approval_level 1) and executes through the AgentExecutor.
Input transforms are pure and derive each stage's inputs from prior outputs.
"""

from __future__ import annotations

from typing import Any

from av_nexus.agents.base import AgentResult
from av_nexus.agents.scout import as_string
from av_nexus.agents.util import as_number

STAGE_ORDER = [
    "scout",
    "market_research",
    "competitive_intelligence",
    "validation",
    "risk",
    "critic",
    "strategy",
]


def stage_defs() -> list[dict[str, Any]]:
    return [
        {
            "name": "scout",
            "agent_id": "opportunity_scout",
            "agent_name": "Opportunity Scout",
            "goal": "Find and score the most attractive business opportunities",
            "deps": [],
        },
        {
            "name": "market_research",
            "agent_id": "market_research",
            "agent_name": "Market Research",
            "goal": "Validate the target market for the top opportunity",
            "deps": ["scout"],
        },
        {
            "name": "competitive_intelligence",
            "agent_id": "competitive_intelligence",
            "agent_name": "Competitive Intelligence",
            "goal": "Analyze competitors in the target market",
            "deps": ["scout"],
        },
        {
            "name": "validation",
            "agent_id": "validation",
            "agent_name": "Validation (Skeptic)",
            "goal": "Stress-test the business idea as a skeptic",
            "deps": ["market_research", "competitive_intelligence"],
        },
        {
            "name": "risk",
            "agent_id": "risk",
            "agent_name": "Risk Officer",
            "goal": "Identify and rate risks for the idea",
            "deps": ["market_research", "competitive_intelligence"],
        },
        {
            "name": "critic",
            "agent_id": "critic",
            "agent_name": "Critic",
            "goal": "Critically review the combined assessment for bias and gaps",
            "deps": ["validation", "risk"],
        },
        {
            "name": "strategy",
            "agent_id": "strategy",
            "agent_name": "Chief Strategy Officer",
            "goal": "Evaluate strategic fit and produce a portfolio recommendation",
            "deps": ["critic"],
        },
    ]


def workflow_label(workflow_type: str) -> str:
    return (
        "Opportunity Discovery (Scout → Market/CI → Validation → Risk → Critic → CSO → Synthesis)"
    )


def stage_inputs(
    stage_name: str, outputs: dict[str, AgentResult], meta: dict[str, Any]
) -> dict[str, Any]:
    """Pure input transforms per stage. `outputs` maps stage name → AgentResult."""
    if stage_name == "scout":
        focus = meta.get("industry_focus") or ""
        return {"industry_focus": focus or "auto", "objective": meta.get("objective", "")}
    if stage_name == "market_research":
        return _from_scout(outputs.get("scout"))
    if stage_name == "competitive_intelligence":
        # No real competitor dataset exists in the system: derive nothing, mark
        # the intelligence gap instead of inventing companies (see _competitor_inputs).
        return _competitor_inputs()
    if stage_name == "validation":
        return _validation_inputs(outputs)
    if stage_name == "risk":
        return _risk_inputs(outputs)
    if stage_name == "critic":
        return _critic_inputs(outputs)
    if stage_name == "strategy":
        return _strategy_inputs(outputs)
    return {}


def _strategy_inputs(outputs: dict[str, AgentResult]) -> dict[str, Any]:
    """Strategy evidence pack: top candidates plus the validation verdict and
    risk posture that the CSO needs to reason over (all real upstream values)."""
    validation = outputs.get("validation")
    risk = outputs.get("risk")
    critic = outputs.get("critic")
    return {
        "opportunities": _top_candidates(outputs.get("scout"), 5),
        "validation": validation.result if validation is not None else {},
        "risk": risk.result if risk is not None else {},
        "critic": critic.result if critic is not None else {},
    }


def _top_opportunity(scout: AgentResult | None) -> dict[str, Any] | None:
    if scout is None:
        return None
    candidates = scout.result.get("candidates")
    if isinstance(candidates, list) and candidates:
        return dict(candidates[0])
    return None


def _top_candidates(scout: AgentResult | None, limit: int) -> list[dict[str, Any]]:
    if scout is None:
        return []
    candidates = scout.result.get("candidates")
    if not isinstance(candidates, list):
        return []
    return [dict(c) for c in candidates[:limit]]


def _competitor_inputs() -> dict[str, Any]:
    """Honest competitor data contract.

    The system has no live/primary competitor dataset. Rather than presenting
    invented companies (e.g. "{industry} Leader Co") as intelligence, the CI
    stage is told explicitly that no data exists and reports an intelligence gap.
    """
    return {"competitors": [], "competitor_data_source": "none_available"}


def _from_scout(scout: AgentResult | None) -> dict[str, Any]:
    """Thread real scout evidence into the market stage.

    TAM/SAM/SOM are NOT fabricated here anymore: the market agent derives them
    from these inputs with a documented index-sizing formula. `competitor_count`
    is 0 because the system holds no competitor data (the CI stage reports the
    gap itself); a fabricated count must not leak into decisions.
    """
    top = _top_opportunity(scout)
    if not top:
        return {}
    return {
        "growth_rate": as_number(top.get("growth_rate"), 20.0),
        "demand_score": as_number(top.get("market_potential"), 55.0),
        "entry_barrier": as_number(top.get("entry_difficulty"), 50.0),
        "competitor_count": 0,
        "industry_focus": top.get("industry"),
        "idea": top.get("title") or top.get("industry"),
        "competition": as_number(top.get("competition"), 60.0),
        "capital": as_number(top.get("capital_requirements"), 60.0),
        "category": top.get("category"),
        "data_provenance": "scout candidate (derived scores); no primary market data",
    }


def _validation_inputs(outputs: dict[str, AgentResult]) -> dict[str, Any]:
    """Thread real upstream values into the Validation (Skeptic) stage.

    `competition` and `capital_requirements` come straight from the scout
    candidate. `willingness_to_pay` and `team_fit` have NO upstream source, so we
    derive documented proxies from real signals and label them as such — no
    silently hardcoded constants masquerading as data.
    """
    scout = outputs.get("scout")
    market = outputs.get("market_research")
    top = _top_opportunity(scout) or {}

    demand = as_number(market.result.get("demand_score"), 55.0) if market else 55.0
    growth = as_number(market.result.get("growth_rate_pct"), 20.0) if market else 20.0
    competition = as_number(top.get("competition"), 60.0)
    capital = as_number(top.get("capital_requirements"), 60.0)

    willingness_to_pay = round(min(90.0, 30.0 + 0.5 * demand + 0.2 * growth), 1)
    team_fit = round(max(20.0, 100.0 - 0.6 * capital), 1)

    focus = ""
    if market is not None:
        focus = as_string(market.result.get("industry_focus")) or as_string(
            market.result.get("recommendation")
        )
    return {
        "idea": focus or "validated opportunity",
        "demand_score": demand,
        "willingness_to_pay": willingness_to_pay,
        "competition": competition,
        "team_fit": team_fit,
        "market_size_score": demand,
        "industry_focus": focus,
        "capital": capital,
        "data_provenance": {
            "demand_score": "market_research.demand_score (real)",
            "growth_rate": "market_research.growth_rate_pct (real)",
            "competition": "scout candidate competition (derived)",
            "capital_requirements": "scout candidate capital_requirements (real)",
            "willingness_to_pay": "documented proxy from demand+growth (no primary data)",
            "team_fit": "documented proxy from capital_requirements (no primary data)",
        },
    }


def _risk_inputs(outputs: dict[str, AgentResult]) -> dict[str, Any]:
    validation = outputs.get("validation")
    risks = []
    if validation is not None:
        for reason in validation.result.get("failure_reasons", []):
            risks.append({"category": "market", "title": str(reason), "risk_score": 55.0})
    market = outputs.get("market_research")
    if market is not None and as_number(market.result.get("entry_barrier"), 0) > 60:
        risks.append(
            {
                "category": "market",
                "title": "High entry barrier may slow go-to-market",
                "risk_score": 65.0,
            }
        )
    return {"risks": risks, "capital": 60.0}


def _critic_inputs(outputs: dict[str, AgentResult]) -> dict[str, Any]:
    merged = {k: v.model_dump() for k, v in outputs.items()}
    confs = [r.confidence for r in outputs.values() if r is not None]
    confidence = round(sum(confs) / len(confs), 3) if confs else 0.0
    return {
        "under_review": {
            "result": merged,
            "confidence": confidence,
            "sources": ["pipeline stages"],
            "assumptions": [],
        }
    }
