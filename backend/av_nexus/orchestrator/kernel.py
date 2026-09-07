"""Orchestrator kernel — pure decision logic (no DB).

Responsibilities: pipeline planning, disagreement detection, approval-level
computation, result merging, confidence derivation. The DB-touching service
lives in `av_nexus.orchestrator.service`.
"""

from __future__ import annotations

from typing import Any

from av_nexus.agents.base import AgentResult
from av_nexus.agents.guardian import level_from_score
from av_nexus.agents.util import as_number


def analyze_disagreements(stages: dict[str, AgentResult]) -> list[dict[str, Any]]:
    """Detect conflicting signals across pipeline stages. Never hides them."""
    conflicts: list[dict[str, Any]] = []

    validation = stages.get("validation")
    risk = stages.get("risk")
    strategy = stages.get("strategy")

    if validation is not None:
        verdict = str(validation.result.get("verdict", ""))
        if verdict in ("CHALLENGE", "STOP"):
            conflicts.append(
                {
                    "type": "validation_vs_build",
                    "against": "strategy",
                    "detail": (
                        f"Validation verdict '{verdict}' conflicts with a build recommendation"
                    ),
                    "evidence": validation.result,
                }
            )

    if risk is not None:
        overall = str(risk.result.get("overall_level", "LOW"))
        if overall in ("HIGH", "CRITICAL"):
            conflicts.append(
                {
                    "type": "risk_vs_build",
                    "against": "strategy",
                    "detail": f"Risk level '{overall}' conflicts with a build recommendation",
                    "evidence": risk.result,
                }
            )

    if strategy is not None and validation is not None:
        strat_verdict = _strategy_direction(strategy.result)
        val_verdict = str(validation.result.get("verdict", "CHALLENGE"))
        if strat_verdict == "BUILD" and val_verdict != "GO":
            conflicts.append(
                {
                    "type": "strategy_vs_validation",
                    "against": "validation",
                    "detail": "Strategy leans BUILD while validation is not GO",
                    "evidence": {
                        "strategy": strat_verdict,
                        "validation": val_verdict,
                    },
                }
            )

    return conflicts


def _strategy_direction(result: dict[str, object]) -> str:
    ranking = result.get("priority_ranking")
    if isinstance(ranking, list) and len(ranking) >= 2:
        return "BUILD"
    if isinstance(ranking, list) and len(ranking) == 1:
        return "CONSIDER"
    return "UNKNOWN"


def merge_pipeline_results(stages: dict[str, AgentResult]) -> dict[str, Any]:
    """Merge each stage into a structured record for the final recommendation."""
    return {
        name: {
            "result": r.result,
            "confidence": r.confidence,
            "mode": r.mode,
            "risks": r.risks,
        }
        for name, r in stages.items()
    }


def derive_confidence(stages: dict[str, AgentResult]) -> float:
    if not stages:
        return 0.0
    confs = [r.confidence for r in stages.values()]
    return round(sum(confs) / len(confs), 3)


def overall_risk_level(stages: dict[str, AgentResult]) -> str:
    risk = stages.get("risk")
    if risk is None:
        return "MEDIUM"
    return str(risk.result.get("overall_level", "MEDIUM"))


def approval_level_for(run_kind: str, risk_level: str = "MEDIUM") -> int:
    """Map an action kind to an approval level (1-4)."""
    table: dict[str, int] = {
        "research": 1,
        "plan": 2,
        "blueprint": 2,
        "communications": 2,
        "external_action": 3,
        "contracts": 4,
        "money": 4,
        "hiring": 4,
        "legal": 4,
        "delete_data": 4,
    }
    base = table.get(run_kind, 2)
    if risk_level in ("HIGH", "CRITICAL") and base < 3:
        return 3
    return base


def normalize_recommendation(validation: AgentResult | None) -> dict[str, Any]:
    if validation is None:
        return {"recommendation": "INSUFFICIENT_INFORMATION", "confidence": 0.2}
    score = as_number(validation.result.get("validation_score"), 0.0)
    verdict = str(validation.result.get("verdict", "CHALLENGE"))
    if score >= 65 and verdict == "GO":
        rec = "BUILD"
    elif score >= 45:
        rec = "VALIDATE_FURTHER"
    else:
        rec = "REJECT"
    return {
        "recommendation": rec,
        "validation_score": score,
        "confidence": validation.confidence,
    }


def risk_flag_for_score(score: float) -> str:
    return level_from_score(score)
