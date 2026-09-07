"""Pipeline definitions & stage input transforms."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

Stage = dict[str, Any]


# --- input transforms (defined before stage lists that reference them) --------
def _top_opportunity(prev: dict[str, Any] | None) -> dict[str, Any] | None:
    if not prev:
        return None
    result = prev.get("result")
    candidates = result.get("candidates") if isinstance(result, dict) else None
    if isinstance(candidates, list) and candidates:
        return dict(candidates[0])  # already sorted desc
    return None


def _from_opportunity(prev: dict[str, Any] | None, inp: dict[str, Any]) -> dict[str, Any]:
    top = _top_opportunity(prev)
    if not top:
        return inp
    return {
        "tam": 100.0,
        "sam": 50.0,
        "som": 10.0,
        "growth_rate": top.get("growth_rate", 20.0),
        "demand_score": top.get("market_potential", 55.0),
        "entry_barrier": top.get("entry_difficulty", 50.0),
        "competitor_count": 4,
        "industry_focus": top.get("industry"),
        "idea": top.get("title") or top.get("industry"),
        "competition": top.get("competition", 60.0),
        "capital": top.get("capital_requirements", 60.0),
        "category": top.get("category"),
    }


def _from_market(prev: dict[str, Any] | None, inp: dict[str, Any]) -> dict[str, Any]:
    market = prev.get("result", {}) if prev and isinstance(prev.get("result"), dict) else {}
    return {
        "idea": inp.get("industry_focus") or market.get("recommendation"),
        "demand_score": market.get("demand_score", 55.0),
        "willingness_to_pay": 50.0,
        "competition": inp.get("competition", 60.0),
        "team_fit": 60.0,
        "market_size_score": market.get("demand_score", 50.0),
        "industry_focus": inp.get("industry_focus"),
        "capital": inp.get("capital", 60.0),
    }


def _earliest_company_summary(prev: dict[str, Any] | None, inp: dict[str, Any]) -> dict[str, Any]:
    return {
        "revenue": 0.0,
        "expenses": 3000.0,
        "cash": 50000.0,
        "cogs": 0.0,
        "cac": 100.0,
        "ltv": 200.0,
    }


def _from_validation_risk(prev: dict[str, Any] | None, inp: dict[str, Any]) -> dict[str, Any]:
    validation = prev.get("result", {}) if prev and isinstance(prev.get("result"), dict) else {}
    risks = []
    for reason in validation.get("failure_reasons", []):
        risks.append({"category": "market", "title": str(reason), "risk_score": 55.0})
    return {"risks": risks, "capital": inp.get("capital", 60.0)}


def _from_all(prev: dict[str, Any] | None, inp: dict[str, Any]) -> dict[str, Any]:
    opp = _top_opportunity(inp.get("opportunities"))
    return {"opportunities": [opp] if opp else []}


def _from_consolidated(prev: dict[str, Any] | None, inp: dict[str, Any]) -> dict[str, Any]:
    merged = inp.get("merged") or {}
    return {
        "under_review": {
            "result": {"merged_stage_count": len(merged)},
            "confidence": inp.get("confidence", 0.5),
            "sources": ["pipeline stages"] if len(merged) else [],
            "assumptions": merged.get("assumptions", []),
        }
    }


# --- pipeline stage definitions -----------------------------------------------
def _stage(
    name: str,
    agent_id: str,
    goal: str,
    inp: dict[str, Any],
    transform: Callable[[dict[str, Any] | None, dict[str, Any]], dict[str, Any]],
) -> Stage:
    return {
        "name": name,
        "agent_id": agent_id,
        "goal_base": goal,
        "inputs": inp,
        "transform": transform,
    }


business_creation: list[Stage] = [
    _stage(
        "opportunity_scan",
        "opportunity_scout",
        "Find new business opportunities",
        {"industry_focus": "auto"},
        lambda prev, inp: prev if prev is not None else inp,
    ),
    _stage(
        "market_research",
        "market_research",
        "Validate the target market for the top opportunity",
        {},
        _from_opportunity,
    ),
    _stage(
        "competitive_intelligence",
        "competitive_intelligence",
        "Analyze competitors in the target market",
        {},
        _from_opportunity,
    ),
    _stage(
        "validation", "validation", "Stress-test the business idea as a skeptic", {}, _from_market
    ),
    _stage(
        "finance", "finance", "Run early unit economics for the idea", {}, _earliest_company_summary
    ),
    _stage("risk", "risk", "Analyze risks for the idea", {}, _from_validation_risk),
    _stage("strategy", "strategy", "Evaluate strategic fit for the portfolio", {}, _from_all),
    _stage("critic", "critic", "Critically review the combined assessment", {}, _from_consolidated),
]


def plan_pipeline(pipeline: str) -> list[Stage]:
    if pipeline == "business_creation":
        return [dict(s) for s in business_creation]
    if pipeline == "venture_blueprint":
        return [
            _stage(
                "venture_builder",
                "venture_builder",
                "Produce a company blueprint for the approved opportunity",
                {},
                lambda prev, inp: prev if prev is not None else inp,
            )
        ]
    raise ValueError(f"Unknown pipeline: {pipeline}")


def describe_pipeline(pipeline: str) -> str:
    names = {
        "business_creation": "Scout → Market → CI → Validation → Finance → Risk → "
        "Strategy → Critic → Orchestrator merge",
        "venture_blueprint": "Venture Builder blueprint",
    }
    return names.get(pipeline, pipeline)
