"""Venture building: Validation (skeptic) + Venture Builder."""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ConfigDict

from av_nexus.agents.base import AgentContext, AgentResult, BaseAgent
from av_nexus.agents.scout import as_string
from av_nexus.agents.util import as_number, confidence_from_sources


class ValidationJudgeSchema(BaseModel):
    """Skeptic reasoning that a real model provider must produce in valid form."""

    model_config = ConfigDict(extra="forbid")

    summary: str
    failure_reasons: list[str]
    questions_to_answer: list[str]


class ValidationOutputSchema(BaseModel):
    """Full published Validator output: deterministic score/verdict plus the
    schema-validated reasoning."""

    model_config = ConfigDict(extra="ignore")

    validation_score: float
    verdict: str
    failure_reasons: list[str]
    questions_to_answer: list[str]


class ValidationAgent(BaseAgent):
    agent_id = "validation"
    name = "Validation Officer"
    role = "Adversarial idea challenger"
    description = (
        "Acts as a skeptic. Actively searches for reasons the idea may fail; "
        "produces a 0-100 validation score."
    )
    capabilities = ["idea_challenge", "market_validation"]
    tools = []
    permissions = ["research"]

    async def run(self, ctx: AgentContext, goal: str) -> AgentResult:
        market_demand = as_number(ctx.inputs.get("demand_score"), 55.0)
        willingness = as_number(ctx.inputs.get("willingness_to_pay"), 50.0)
        competitive_color = as_number(ctx.inputs.get("competition"), 60.0)
        team_fit = as_number(ctx.inputs.get("team_fit"), 50.0)
        market_size = as_number(ctx.inputs.get("market_size_score"), 50.0)

        score = (
            market_demand * 0.25
            + willingness * 0.2
            + (100 - competitive_color) * 0.15
            + team_fit * 0.15
            + market_size * 0.25
        )
        verdict = "GO" if score >= 65 else "CHALLENGE" if score >= 45 else "STOP"

        result: dict[str, Any] = {
            "validation_score": round(min(100.0, max(0.0, score)), 1),
            "verdict": verdict,
        }

        system_prompt = (
            "You are the Validation Officer: an adversarial skeptic who actively "
            "searches for reasons an idea will fail. Base every claim ONLY on the "
            "supplied evidence and its noted data provenance; never invent external "
            "facts. Respond ONLY with a JSON object exactly matching this schema: "
            + json.dumps(ValidationJudgeSchema.model_json_schema())
        )
        user_prompt = json.dumps(
            {
                "idea": as_string(ctx.inputs.get("idea")) or "validated opportunity",
                "demand_score": market_demand,
                "willingness_to_pay": willingness,
                "competition": competitive_color,
                "team_fit": team_fit,
                "market_size_score": market_size,
                "capital": as_number(ctx.inputs.get("capital"), 60.0),
                "data_provenance": ctx.inputs.get("data_provenance", {}),
            },
            default=str,
        )

        reasoning = self._structured_llm(ctx, system_prompt, user_prompt, ValidationJudgeSchema)
        if reasoning is None:
            result["failure_reasons"] = []
            result["questions_to_answer"] = []
            result["reasoning"] = {"status": "not_generated", "reason": "no_llm_provider"}
            return AgentResult.deterministic(
                result=result,
                confidence=confidence_from_sources(3 if ctx.inputs else 1),
                assumptions=[
                    "Scores reflect available inputs only",
                    "Failure analysis requires a model provider",
                ],
                sources=["internal heuristic: weighted skeptic score"],
                risks=["Score is not a substitute for primary customer interviews"],
                next_recommended_agents=["risk", "critic", "finance"],
            )

        result["failure_reasons"] = reasoning["failure_reasons"]
        result["questions_to_answer"] = reasoning["questions_to_answer"]
        return AgentResult.llm(
            result=result,
            schema=ValidationOutputSchema,
            confidence=confidence_from_sources(4 if ctx.inputs else 2),
            assumptions=[
                "Scores reflect available inputs only",
                "Failure analysis produced by a real model provider",
            ],
            sources=[
                "internal heuristic: weighted skeptic score",
                "validated LLM skeptic reasoning (real provider)",
            ],
            risks=["Score is not a substitute for primary customer interviews"],
            next_recommended_agents=["risk", "critic", "finance"],
        )


class VentureBuilderAgent(BaseAgent):
    agent_id = "venture_builder"
    name = "Venture Builder"
    role = "Company blueprint creator"
    description = (
        "Produces a complete company blueprint: name, mission, MVP, go-to-market, "
        "team, budget, 12-month roadmap."
    )
    capabilities = ["company_blueprint", "business_model"]
    tools = []
    permissions = ["planning", "drafting"]

    async def run(self, ctx: AgentContext, goal: str) -> AgentResult:
        # Real input contract (fed by the engine only after a BUILD /
        # VALIDATE_FURTHER synthesis decision): every field below is derived from
        # pipeline stage evidence, never hard-coded.
        opportunity = ctx.inputs.get("opportunity") or {}
        market = ctx.inputs.get("market") or {}
        validation = ctx.inputs.get("validation") or {}
        risk = ctx.inputs.get("risk") or {}
        strategy = ctx.inputs.get("strategy") or {}
        objective = as_string(ctx.inputs.get("objective")) or goal
        industry = as_string(opportunity.get("industry")) or as_string(
            ctx.inputs.get("industry_focus")
        ) or "target market"

        top = opportunity if isinstance(opportunity, dict) else {}
        opp_title = as_string(top.get("title")) or objective
        demand = as_number(market.get("demand_score"), 55.0)
        competition = as_number(top.get("competition"), as_number(market.get("competition"), 60.0))
        entry_barrier = as_number(market.get("entry_barrier"), 50.0)
        failure_reasons_raw = validation.get("failure_reasons")
        failure_reasons: list[Any] = (
            failure_reasons_raw if isinstance(failure_reasons_raw, list) else []
        )
        overall_risk = as_string(risk.get("overall_level")) or "MEDIUM"
        risk_matrix_raw = risk.get("risk_matrix")
        risk_matrix: list[Any] = risk_matrix_raw if isinstance(risk_matrix_raw, list) else []
        cap_hint = as_number(top.get("capital_requirements"), 65.0)
        ranking_raw = strategy.get("priority_ranking")
        ranking: list[Any] = ranking_raw if isinstance(ranking_raw, list) else []

        company_name = _company_name(opp_title)
        if demand >= 70:
            segment = f"Tech-forward SMBs in {industry} with existing budgets"
        elif demand >= 40:
            segment = f"Early-adopter SMBs in {industry}"
        else:
            segment = f"Niche early adopters in {industry}"
        problem = as_string(top.get("rationale")) or (
            f"The '{opp_title}' opportunity remains unserved in {industry}"
        )
        if demand >= 70:
            business_model = "SaaS annual contracts with usage-based add-ons"
        elif demand >= 45:
            business_model = "SaaS subscription with usage-based pricing"
        else:
            business_model = "Service-led onboarding with usage pricing"
        pricing = {
            "entry": round(max(19, 50 * (demand / 100.0)), 0),
            "pro": round(max(49, 150 * (demand / 100.0)), 0),
            "enterprise": "custom (negotiated)",
        }
        mvp_blocks = ["onboarding"]
        if entry_barrier > 60:
            mvp_blocks.append("sales-assisted activation")
        else:
            mvp_blocks.append("self-serve activation")
        if competition > 65:
            mvp_blocks.append("differentiated workflow")
        roadmap = [m_block(month) for month in range(1, 13)]
        if failure_reasons:
            roadmap[0] = "customer interview wave to retire open validation gaps"
            roadmap[2] = "validation gaps review gates MVP scope"
        if overall_risk in ("HIGH", "CRITICAL"):
            roadmap[3] = "risk mitigation review before scaling spend"
            roadmap[8] = "go/no-go checkpoint on the overall risk level"
        for entry in risk_matrix[:3]:
            if isinstance(entry, dict) and as_number(entry.get("risk_score"), 0) >= 70:
                roadmap[5] = f"mitigation review for top risk: {as_string(entry.get('title'))}"
                break

        blueprint = {
            "company_name": company_name,
            "mission": f"Make '{opp_title}' accessible to {segment}",
            "problem": problem,
            "solution": (
                f"Focused MVP for {segment} that tackles "
                f"{as_string(opportunity.get('category')) or industry}: "
                f"{', '.join(mvp_blocks)}"
            ),
            "target_customer": segment,
            "business_model": business_model,
            "pricing": pricing,
            "mvp_plan": {
                "focus_blocks": mvp_blocks,
                "duration_weeks": 6 if entry_barrier > 60 else 4,
                "success_metric": "activated accounts and first paying pilot",
            },
            "roadmap_12_months": [
                {
                    "month": month,
                    "milestone": milestone,
                }
                for month, milestone in enumerate(roadmap, 1)
            ],
            "team_structure": ["PM", "2 engineers", "designer (shared)", "growth marketer"],
            "budget_estimate_usd": round(cap_hint / 100.0) * 10000,
            "forecast_rationale": {
                "demand_score": demand,
                "competition": competition,
                "entry_barrier": entry_barrier,
                "approved_priority": ranking[0] if ranking else None,
            },
            "risks_acknowledged": [
                {"level": overall_risk, "count": len(risk_matrix)},
                {"validation_gaps": failure_reasons},
            ],
        }
        return AgentResult.deterministic(
            result={"blueprint": blueprint},
            confidence=confidence_from_sources(3 if ctx.inputs else 0),
            assumptions=[
                "Blueprint is derived from pipeline evidence "
                f"(validation {as_number(validation.get('validation_score'), 0.0)}/100, "
                f"risk {overall_risk})",
                "Pricing and budget are estimates to be validated, not external figures",
            ],
            sources=["internal template: venture blueprint derived from workflow stage results"],
            risks=["Names/pricing are derived estimates until primary validation"],
            next_recommended_agents=["finance", "risk", "marketing", "operations"],
        )


def _company_name(raw: str) -> str:
    words = "".join(c if c.isalnum() else " " for c in raw).split()
    head = words[:4] or ["Ventura"]
    return " ".join(w[:1].upper() + w[1:] for w in head)


def name_slug(raw: str) -> str:
    words = "".join(c if c.isalnum() else " " for c in raw).split()
    return ("_".join(words[:3]) or "ventura").lower()[:40]


def m_block(month: int) -> str:
    blocks = {
        1: "design partners signed",
        2: "MVP v1 live",
        3: "first 10 paying pilot users",
        4: "pricing validated",
        5: "product market fit metrics tracked",
        6: "seed revenue run-rate reviewed",
        7: "expand to second segment",
        8: "evaluate paid acquisition",
        9: "hiring for growth",
        10: "partner integrations",
        11: "second product line decision",
        12: "series-A readiness review",
    }
    return blocks.get(month, "operate & iterate")
