"""Specialist agents: opportunity scout, market research, competitive intelligence,
innovation & R&D."""

from __future__ import annotations

from typing import Any

from av_nexus.agents.base import AgentContext, AgentResult, BaseAgent
from av_nexus.agents.util import (
    as_number,
    confidence_from_sources,
    weighted_100,
)

# Deterministic industry seed catalog — clearly heuristic, not external research.
INDUSTRY_SEEDS: dict[str, dict[str, float]] = {
    "ai_education": {"potential": 82, "growth": 78, "entry": 55, "capital": 45},
    "ai_b2b_automation": {"potential": 88, "growth": 80, "entry": 65, "capital": 60},
    "robotics_sme": {"potential": 70, "growth": 58, "entry": 75, "capital": 85},
    "climate_tech": {"potential": 90, "growth": 82, "entry": 68, "capital": 70},
    "fintech_sme": {"potential": 78, "growth": 70, "entry": 72, "capital": 65},
    "healthcare_diagnostics": {"potential": 85, "growth": 60, "entry": 78, "capital": 75},
    "space_services": {"potential": 80, "growth": 74, "entry": 85, "capital": 95},
    "smart_construction": {"potential": 68, "growth": 54, "entry": 70, "capital": 80},
}


class OpportunityScoutAgent(BaseAgent):
    agent_id = "opportunity_scout"
    name = "Opportunity Scout"
    role = "Continuous opportunity discovery"
    description = (
        "Finds emerging industries, market gaps, underserved markets and startup "
        "opportunities; scores them 0-100."
    )
    capabilities = ["opportunity_discovery", "trend_analysis"]
    tools = []
    permissions = ["research"]

    async def run(self, ctx: AgentContext, goal: str) -> AgentResult:
        focus = as_string(ctx.inputs.get("industry_focus")) or infer_focus(goal)
        if focus == "auto":
            catalog: dict[str, dict[str, float]] = INDUSTRY_SEEDS
        else:
            default: dict[str, float] = {"potential": 60, "growth": 50, "entry": 60, "capital": 60}
            catalog = {focus: INDUSTRY_SEEDS.get(focus, default)}
        candidates: list[dict[str, Any]] = []
        for ind, v in catalog.items():
            competition = 70 - v["entry"]
            risk = 45.0 if v["capital"] < 55 else 62.0
            tech_advantage = 80.0 if ind.startswith(("ai", "fintech")) else 55.0
            score = weighted_100(
                [
                    (v["potential"], 0.25),
                    (v["growth"], 0.2),
                    (competition, 0.1),
                    (100 - v["entry"], 0.1),
                    (100 - v["capital"], 0.1),
                    (tech_advantage, 0.15),
                    (100 - risk, 0.1),
                ]
            )
            candidates.append(
                {
                    "title": _industry_title(ind),
                    "industry": ind,
                    "category": ind,
                    "opportunity_score": round(score, 1),
                    "market_potential": v["potential"],
                    "growth_rate": v["growth"],
                    "competition": round(competition, 1),
                    "entry_difficulty": v["entry"],
                    "capital_requirements": v["capital"],
                    "risk_score": risk,
                    "rationale": f"Heuristic scan of {ind}",
                }
            )
        candidates.sort(key=lambda c: float(c["opportunity_score"]), reverse=True)
        return AgentResult.deterministic(
            result={
                "focus": focus,
                "candidates": candidates,
                "note": "Deterministic heuristic screening. Scores are internal "
                "rules-of-thumb, not external market research.",
            },
            confidence=confidence_from_sources(2),
            assumptions=["Industry catalog is a static heuristic", "No live data feeds"],
            sources=["internal template: INDUSTRY_SEEDS"],
            risks=["Real opportunities may be missed without live data"],
            next_recommended_agents=["market_research", "competitive_intelligence"],
        )


class MarketResearchAgent(BaseAgent):
    agent_id = "market_research"
    name = "Market Research"
    role = "Market validation & sizing"
    description = "Estimates TAM/SAM/SOM, customer segments, demand and entry barriers."
    capabilities = ["market_research", "market_validation"]
    tools = []
    permissions = ["research"]

    async def run(self, ctx: AgentContext, goal: str) -> AgentResult:
        demand = as_number(ctx.inputs.get("demand_score"), 55.0)
        growth = as_number(ctx.inputs.get("growth_rate"), 20.0)
        entry_barrier = as_number(ctx.inputs.get("entry_barrier"), 50.0)
        competitors_count = int(as_number(ctx.inputs.get("competitor_count"), 0))
        competition = as_number(ctx.inputs.get("competition"), 60.0)

        # Documented market sizing (index model, not external figures):
        # - TAM scales with demand (0-100) and growth
        # - SAM discounts TAM by competitive pressure
        # - SOM discounts SAM by entry friction
        # Explicit tam/sam/som given by a caller (e.g. a task with real figures)
        # are honored as-is; otherwise the model derives values from actual inputs.
        if all(k in ctx.inputs for k in ("tam", "sam", "som")):
            tam = as_number(ctx.inputs.get("tam"), 100.0)
            sam = as_number(ctx.inputs.get("sam"), tam * 0.5)
            som = as_number(ctx.inputs.get("som"), tam * 0.1)
        else:
            tam = round(100.0 * (0.35 + demand / 100.0) * (0.75 + growth / 100.0), 1)
            sam = round(tam * (1.0 - min(competition, 90.0) / 200.0), 1)
            som = round(max(0.5, sam * (1.0 - min(entry_barrier, 90.0) / 250.0)), 1)

        if growth >= 60 and demand >= 60 and entry_barrier <= 60:
            rec = "VALIDATE"
        elif growth >= 50 and demand >= 50:
            rec = "INVESTIGATE FURTHER"
        elif growth < 30:
            rec = "WAIT"
        else:
            # competitor_count == 0 means "no data", so treat as unknown: do not
            # pick BUILD MVP on the strength of a fabricated count.
            rec = "BUILD MVP" if 0 < competitors_count <= 4 else "INVESTIGATE FURTHER"

        return AgentResult.deterministic(
            result={
                "tam": tam,
                "sam": round(sam, 2),
                "som": round(som, 2),
                "growth_rate_pct": growth,
                "demand_score": demand,
                "entry_barrier": entry_barrier,
                "competitor_count": competitors_count,
                "recommendation": rec,
                "note": "Sizing is an internal index model derived from scout inputs, "
                "not external figures.",
            },
            confidence=confidence_from_sources(2 if ctx.inputs else 0),
            assumptions=[
                "TAM/SAM/SOM derived from demand/growth/competition/entry scores",
                "No external or primary market data available",
            ],
            sources=["internal heuristic: market sizing"],
            risks=["Sizing can be materially wrong without primary research"],
            next_recommended_agents=["validation", "risk", "competitive_intelligence"],
        )


class CompetitiveIntelligenceAgent(BaseAgent):
    agent_id = "competitive_intelligence"
    name = "Competitive Intelligence"
    role = "Competitor monitoring"
    description = "Builds the competitor database; tracks products, pricing, threats."
    capabilities = ["competitor_analysis", "market_intelligence"]
    tools = []
    permissions = ["research"]

    async def run(self, ctx: AgentContext, goal: str) -> AgentResult:
        competitors = ctx.inputs.get("competitors") or []
        data_source = as_string(ctx.inputs.get("competitor_data_source"))
        entries: list[dict[str, Any]] = []
        for c in competitors:
            if not isinstance(c, dict):
                continue
            tscore = as_number(c.get("threat_score"), 40.0)
            entries.append(
                {
                    "name": c.get("name", ""),
                    "industry": c.get("industry", ""),
                    "products": c.get("products", ""),
                    "pricing": c.get("pricing", ""),
                    "strengths": c.get("strengths", []),
                    "weaknesses": c.get("weaknesses", []),
                    "threat_score": tscore,
                }
            )
        entries.sort(key=lambda e: float(e["threat_score"]), reverse=True)
        if not entries:
            # No dataset upstream: report the gap explicitly. Never invent
            # competitor identities and present them as intelligence.
            return AgentResult.deterministic(
                result={
                    "competitor_report": [],
                    "top_threat": None,
                    "competitor_data_source": "none_available",
                    "note": (
                        "No competitor dataset is available in this system. The stage "
                        "reports an intelligence gap instead of synthesizing invented "
                        "competitors."
                    ),
                },
                confidence=confidence_from_sources(0),
                assumptions=["No competitor data was supplied upstream"],
                sources=["none available"],
                risks=["Competitive position is unverified until a real dataset is attached"],
                next_recommended_agents=["strategy", "risk"],
            )
        return AgentResult.deterministic(
            result={
                "competitor_report": entries,
                "top_threat": entries[0]["name"] if entries else None,
                "competitor_data_source": data_source or "supplied",
                "monitoring_status": "dataset snapshot; live monitoring deferred",
            },
            confidence=confidence_from_sources(len(entries)),
            assumptions=["Competitor data must be curated upstream"],
            sources=["internal heuristic: threat scoring"],
            risks=["Stale competitor data leads to wrong strategy"],
            next_recommended_agents=["strategy", "risk"],
        )


class InnovationAgent(BaseAgent):
    agent_id = "innovation"
    name = "Innovation & R&D"
    role = "Product and technology ideation"
    description = "Problem → Technology → Opportunity → Product → Business model."
    capabilities = ["product_ideation", "technology_scouting"]
    tools = []
    permissions = ["research", "planning"]

    async def run(self, ctx: AgentContext, goal: str) -> AgentResult:
        problem = as_string(ctx.inputs.get("problem")) or goal
        tech = as_string(ctx.inputs.get("technology")) or "AI/LLM applied automation"
        idea = {
            "problem": problem,
            "technology": tech,
            "opportunity": f"Automate/optimize '{problem}' via {tech}",
            "product_idea": f"{tech.split('/')[0].title()} Assistant for {problem_slug(problem)}",
            "business_model": "SaaS subscription + usage-based pricing",
            "mvp_scope": "One vertical, one workflow, manual data backfill",
        }
        return AgentResult.deterministic(
            result={"idea": idea},
            confidence=confidence_from_sources(1),
            assumptions=["Idea generated heuristically; needs market review"],
            sources=["internal template: problem→product"],
            risks=["Idea may already be crowded; validation agent must check"],
            next_recommended_agents=["opportunity_scout", "validation", "market_research"],
        )


def as_string(value: object) -> str:
    return str(value) if value else ""


def _industry_title(ind: str) -> str:
    """Human-readable candidate title derived from the industry key (e.g.
    'smart_construction' → 'Smart Construction', 'ai_education' → 'AI Education')."""
    return " ".join(
        w.upper() if w.lower() == "ai" else (w[:1].upper() + w[1:])
        for w in ind.replace("_", " ").split()
    )


def infer_focus(goal: str) -> str:
    goal_l = goal.lower()
    for key, canonical in {
        "education": "ai_education",
        "robot": "robotics_sme",
        "climate": "climate_tech",
        "financ": "fintech_sme",
        "fintech": "fintech_sme",
        "health": "healthcare_diagnostics",
        "space": "space_services",
        "construct": "smart_construction",
        "b2b": "ai_b2b_automation",
        "automation": "ai_b2b_automation",
    }.items():
        if key in goal_l:
            return canonical
    return "auto"


def problem_slug(problem: str) -> str:
    words = "".join(c if c.isalnum() else " " for c in problem).split()
    return "_".join(words[:3]).lower() if words else "workflow"
