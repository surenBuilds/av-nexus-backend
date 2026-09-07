"""Group strategy layer: Chief Strategy Officer, Investment, M&A."""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ConfigDict

from av_nexus.agents.base import AgentContext, AgentResult, BaseAgent
from av_nexus.agents.scout import as_string
from av_nexus.agents.util import as_number, confidence_from_sources, weighted_100


class StrategyCommentarySchema(BaseModel):
    """Schema-validated strategic commentary produced by a real model provider."""

    model_config = ConfigDict(extra="forbid")

    summary: str
    capital_allocation_guidance: str
    portfolio_watchouts: list[str]
    key_assumptions: list[str]


class StrategyOutputSchema(BaseModel):
    """Full published Strategy output; outer layer mirrors the deterministic keys
    and requires the validated commentary."""

    model_config = ConfigDict(extra="ignore")

    goal: str
    priority_ranking: list[dict[str, Any]]
    recommended_industries: list[str]
    portfolio_sku: int
    one_year_plan: list[dict[str, Any]]
    three_year_plan: dict[str, Any]
    ten_year_scenarios: list[str]
    strategy_commentary: StrategyCommentarySchema


class StrategyAgent(BaseAgent):
    agent_id = "strategy"
    name = "Chief Strategy Officer"
    role = "Group strategy & capital allocation advisor"
    description = (
        "Long-term portfolio strategy, industry selection, company prioritization, "
        "1/3/10-year planning."
    )
    capabilities = ["strategy", "portfolio", "prioritization", "scenario_analysis"]
    tools = []
    permissions = ["research", "planning"]

    async def run(self, ctx: AgentContext, goal: str) -> AgentResult:
        opps = ctx.inputs.get("opportunities") or ctx.data.get("opportunities") or []
        companies = ctx.inputs.get("companies") or ctx.data.get("companies") or []
        inputs_used = 1 if opps else 0
        inputs_used += 1 if companies else 0

        ranked = sorted(
            [o for o in opps if isinstance(o, dict) and as_number(o.get("opportunity_score")) > 0],
            key=lambda o: as_number(o.get("opportunity_score")),
            reverse=True,
        )[:5]

        priority_ranking = [
            {"title": o.get("title", ""), "score": as_number(o.get("opportunity_score"))}
            for o in ranked
        ]

        one_yr = [
            {
                "quarter": f"Q{q}",
                "focus": {
                    "discover": q == 1,
                    "validate_top2": q in (2, 3),
                    "invest_in_top1": q == 4,
                },
            }
            for q in range(1, 5)
        ]

        three_yr = {
            "build": len(priority_ranking),
            "scenario_bear": "pause new builds, optimize portfolio",
            "scenario_base": "operate + 1 new company",
            "scenario_bull": "operate + expand to 2 new companies",
        }
        ten_yr = [
            "conglomerate: 3-5 companies across regulated industries",
            "platform: shared operations for the group",
        ]

        result: dict[str, Any] = {
            "goal": goal,
            "priority_ranking": priority_ranking,
            "recommended_industries": sorted(
                {o.get("category", "") for o in ranked if o.get("category")}
            ),
            "portfolio_sku": len(companies),
            "one_year_plan": one_yr,
            "three_year_plan": three_yr,
            "ten_year_scenarios": ten_yr,
        }

        # Real evidence for the commentary: validator verdict, risk posture,
        # critic verdict and the top-ranked opportunities.
        validation = ctx.inputs.get("validation") or {}
        risk = ctx.inputs.get("risk") or {}
        critic = ctx.inputs.get("critic") or {}

        system_prompt = (
            "You are the Chief Strategy Officer of a venture group. Review ONLY the "
            "supplied portfolio evidence and produce concise, evidence-grounded strategic "
            "commentary. Never claim facts not supported by the evidence. Respond ONLY "
            "with a JSON object exactly matching this schema: "
            + json.dumps(StrategyCommentarySchema.model_json_schema())
        )
        user_prompt = json.dumps(
            {
                "goal": goal,
                "priority_ranking": priority_ranking,
                "portfolio_company_count": len(companies),
                "recommended_industries": result["recommended_industries"],
                "three_year_plan": three_yr,
                "ten_year_scenarios": ten_yr,
                "validator_verdict": as_string(validation.get("verdict")) or "not available",
                "validator_score": as_number(validation.get("validation_score"), 0.0),
                "risk_level": as_string(risk.get("overall_level")) or "not available",
                "critic_verdict": as_string(critic.get("verdict")) or "not available",
            },
            default=str,
        )

        commentary = self._structured_llm(ctx, system_prompt, user_prompt, StrategyCommentarySchema)
        if commentary is None:
            result["strategy_commentary"] = {
                "status": "not_generated",
                "reason": "no_llm_provider",
            }
            return AgentResult.deterministic(
                result=result,
                confidence=confidence_from_sources(inputs_used),
                assumptions=["Ranking uses Opportunity Score only", "No external market data"],
                sources=["internal heuristic: priority_ranking"],
                risks=["Concentration risk if top opportunity fails"],
                next_recommended_agents=["validation", "risk"],
            )

        result["strategy_commentary"] = commentary
        return AgentResult.llm(
            result=result,
            schema=StrategyOutputSchema,
            confidence=confidence_from_sources(inputs_used + 1),
            assumptions=["Ranking uses Opportunity Score only", "No external market data"],
            sources=[
                "internal heuristic: priority_ranking",
                "validated LLM commentary (real provider)",
            ],
            risks=["Concentration risk if top opportunity fails"],
            next_recommended_agents=["validation", "risk"],
        )


class InvestmentAgent(BaseAgent):
    agent_id = "investment"
    name = "Investment Officer"
    role = "Capital allocation recommendations"
    description = "ROI, risk, growth, liquidity and strategic value comparison across options."
    capabilities = ["capital_allocation", "roi_analysis", "investment_analysis"]
    tools = []
    permissions = ["research", "planning"]

    async def run(self, ctx: AgentContext, goal: str) -> AgentResult:
        options = ctx.inputs.get("options") or []
        scored: list[dict[str, object]] = []
        for opt in options if isinstance(options, list) else []:
            if isinstance(opt, dict):
                roi = as_number(opt.get("roi"), 10)
                risk = as_number(opt.get("risk"), 40)
                growth = as_number(opt.get("growth"), 10)
                liquidity = as_number(opt.get("liquidity"), 50)
                strategic = as_number(opt.get("strategic_value"), 50)
                index = weighted_100(
                    [
                        (roi, 0.3),
                        (100 - risk, 0.25),
                        (growth, 0.15),
                        (liquidity, 0.15),
                        (strategic, 0.15),
                    ]
                )
                scored.append(
                    {
                        "option": opt.get("option", opt.get("name", "")),
                        "roi": roi,
                        "risk": risk,
                        "index": round(index, 1),
                    }
                )
        scored.sort(key=lambda x: as_number(x.get("index"), 0.0), reverse=True)
        recommendation = next(iter(scored), None)
        return AgentResult.deterministic(
            result={
                "recommendation": recommendation,
                "ranked_options": scored,
                "allocation_suggestion": {
                    recommendation["option"]: "fund first" if recommendation else ""
                }
                if recommendation
                else {},
            },
            confidence=confidence_from_sources(len(scored)),
            assumptions=["Option scores are provided inputs"],
            sources=["internal heuristic: weighted index"],
            risks=["ROI estimates may not materialize"],
            next_recommended_agents=["risk", "critic"],
        )


class MnAAgent(BaseAgent):
    agent_id = "mna"
    name = "M&A Scout"
    role = "Acquisition, partnership and synergy analysis"
    description = "Scans acquisition targets, partnerships, undervalued companies."
    capabilities = ["ma_scanning", "synergy_analysis", "partnership_scan"]
    tools = []
    permissions = ["research"]

    async def run(self, ctx: AgentContext, goal: str) -> AgentResult:
        targets = ctx.inputs.get("targets") or []
        analyzed = [
            {
                "target": t.get("name", t.get("target", "")),
                "strategic_fit": t.get("strategic_fit", 50),
                "risk": t.get("risk", 30),
                "synergy": t.get("synergy", 40),
            }
            for t in targets
            if isinstance(t, dict)
        ]
        analyze = not analyzed and not targets
        return AgentResult.deterministic(
            result={
                "matches": analyzed,
                "phase1_advisory": (
                    "Provide acquisition targets to enable scanning; Phase 1 is advisory "
                    "only, no transactions execute."
                ),
                "scan_performed": not analyze,
            },
            confidence=confidence_from_sources(len(analyzed)),
            assumptions=["Target financials must come from a trusted data source"],
            sources=["internal heuristic: fit/synergy scoring"],
            risks=["M&A decisions are irreversible; require level-4 approval"],
            next_recommended_agents=["legal_compliance", "finance", "risk"],
        )