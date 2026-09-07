"""Business management agents: AI CEO, CFO, CMO, COO, Sales."""

from __future__ import annotations

from av_nexus.agents.base import AgentContext, AgentResult, BaseAgent
from av_nexus.agents.scout import as_string
from av_nexus.agents.util import as_number, confidence_from_sources, weighted_100


class CeoAgent(BaseAgent):
    agent_id = "ceo"
    name = "AI CEO"
    role = "Company-level strategy & KPI ownership"
    description = (
        "Per-company strategy, KPI monitoring, goal setting, weekly reporting. "
        "Cannot spend money, sign contracts or hire/fire humans without approval."
    )
    capabilities = ["company_strategy", "kpi_monitoring", "goal_setting"]
    tools = []
    permissions = ["research", "planning", "reporting"]

    async def run(self, ctx: AgentContext, goal: str) -> AgentResult:
        kpis = ctx.inputs.get("kpis") or []
        health = weighted_100(_kpi_factors(kpis)) if kpis else 50.0
        warning = [
            k
            for k in kpis
            if isinstance(k, dict) and as_number(k.get("value")) < as_number(k.get("target")) * 0.7
        ]
        return AgentResult.deterministic(
            result={
                "company_health_score": round(health, 1),
                "kpi_review": kpis,
                "weekly_focus": ("Fix at-risk KPIs" if warning else "Push growth measures"),
                "recommendations": (
                    ["Investigate KPI misses"] if warning else ["Scale what works"]
                ),
            },
            confidence=confidence_from_sources(len(kpis)),
            assumptions=["KPI data supplied by monitor pipelines"],
            sources=["internal heuristic: KPI gap analysis"],
            risks=["No action taken automatically; recommendations only"],
            next_recommended_agents=["finance", "operations", "marketing"],
        )


class FinanceAgent(BaseAgent):
    agent_id = "finance"
    name = "CFO"
    role = "Financial analysis & health"
    description = (
        "Revenue, expenses, profitability, cash flow, unit economics, forecast. "
        "Produces Financial Health Score 0-100."
    )
    capabilities = ["financial_analysis", "unit_economics", "forecasting", "budgeting"]
    tools = []
    permissions = ["research", "planning"]

    async def run(self, ctx: AgentContext, goal: str) -> AgentResult:
        revenue = as_number(ctx.inputs.get("revenue"))
        expenses = as_number(ctx.inputs.get("expenses"))
        cash = as_number(ctx.inputs.get("cash"))
        cogs = as_number(ctx.inputs.get("cogs"))
        cac = as_number(ctx.inputs.get("cac"), 100.0)
        ltv = as_number(ctx.inputs.get("ltv"), 200.0)

        gross_margin = (revenue - cogs) / revenue * 100 if revenue else 0.0
        net_margin = (revenue - expenses) / revenue * 100 if revenue else 0.0
        burn_rate = max(expenses - revenue, 0.0)
        runway = cash / burn_rate if burn_rate > 0 else 999.0
        ltv_cac = ltv / cac if cac > 0 else 0.0

        health = weighted_100(
            [
                (min(gross_margin, 100), 0.3),
                (min(max(net_margin, -50), 100), 0.2),
                (min(ltv_cac * 20, 100), 0.2),
                (min(runway, 36) / 36 * 100, 0.2),
                (60 if cash > 0 else 0, 0.1),
            ]
        )
        return AgentResult.deterministic(
            result={
                "revenue": revenue,
                "gross_margin_pct": round(gross_margin, 1),
                "net_margin_pct": round(net_margin, 1),
                "cac": cac,
                "ltv": ltv,
                "ltv_cac_ratio": round(ltv_cac, 2),
                "burn_rate": round(burn_rate, 2),
                "runway_months": round(runway, 1),
                "financial_health_score": round(health, 1),
                "note": "Computed from supplied figures; not audited.",
            },
            confidence=confidence_from_sources(3 if revenue else 0),
            assumptions=["Provided financials are accurate"],
            sources=["internal heuristic: unit economics"],
            risks=["Financial metrics require real bookkeeping to be reliable"],
            next_recommended_agents=["risk", "strategy"],
        )


class MarketingAgent(BaseAgent):
    agent_id = "marketing"
    name = "CMO"
    role = "Marketing & growth"
    description = "Brand, positioning, campaigns, funnels, growth experiments."
    capabilities = ["marketing_strategy", "growth_experiments", "branding"]
    tools = []
    permissions = ["planning", "drafting"]

    async def run(self, ctx: AgentContext, goal: str) -> AgentResult:
        audience = as_string(ctx.inputs.get("audience")) or "target SMB vertical"
        budget = as_number(ctx.inputs.get("budget"), 5000)
        return AgentResult.deterministic(
            result={
                "positioning": f"Best {audience} efficiency with measured ROI",
                "campaign_plan": [
                    {"channel": "Content/SEO", "share_pct": 40},
                    {"channel": "Outbound email", "share_pct": 30},
                    {"channel": "Paid social", "share_pct": 30},
                ],
                "content_calendar": {
                    "weekly": ["1 product teardown", "2 how-to posts", "1 case study"],
                },
                "funnel": ["Visit", "Demo", "Trial", "Paid"],
                "growth_experiments": ["pricing page A/B", "onboarding cohort analysis"],
                "budget_allocation_usd": budget,
            },
            confidence=confidence_from_sources(1),
            assumptions=["Budget and audience are provided inputs"],
            sources=["internal template: growth plan"],
            risks=["Paid channels are not executed without approval"],
            next_recommended_agents=["sales", "operations", "finance"],
        )


class OperationsAgent(BaseAgent):
    agent_id = "operations"
    name = "COO"
    role = "Operations & execution"
    description = "Processes, workflows, bottleneck and delay detection."
    capabilities = ["operations", "process_analysis", "bottleneck_detection"]
    tools = []
    permissions = ["research", "planning"]

    async def run(self, ctx: AgentContext, goal: str) -> AgentResult:
        projects = ctx.inputs.get("projects") or []
        bottlenecks = [
            p.get("name", "")
            for p in projects
            if isinstance(p, dict) and p.get("status") == "delayed"
        ]
        return AgentResult.deterministic(
            result={
                "projects_reviewed": len(projects),
                "bottlenecks": bottlenecks,
                "process_flags": (
                    ["Delayed projects need owners"] if bottlenecks else ["Operations steady"]
                ),
                "recommended_fixes": (
                    ["Assign explicit owners", "Re-plan dependencies"] if bottlenecks else []
                ),
            },
            confidence=confidence_from_sources(len(projects)),
            assumptions=["Project statuses supplied by tracking"],
            sources=["internal heuristic: bottleneck detection"],
            risks=["Tracking gaps hide operational issues"],
            next_recommended_agents=["ceo", "sales"],
        )


class SalesAgent(BaseAgent):
    agent_id = "sales"
    name = "Sales Analyst"
    role = "Pipeline, leads and CRM insights"
    description = "Lead scoring, segmentation, pipeline analysis, sales strategy."
    capabilities = ["lead_research", "pipeline", "crm_insights"]
    tools = []
    permissions = ["research"]

    async def run(self, ctx: AgentContext, goal: str) -> AgentResult:
        leads = ctx.inputs.get("leads") or []
        scored = [
            {
                "lead": lead.get("name", lead.get("email", "")),
                "score": round(_score_lead(lead), 1),
            }
            for lead in leads
            if isinstance(lead, dict)
        ]
        scored.sort(key=lambda x: as_number(x["score"]), reverse=True)
        return AgentResult.deterministic(
            result={
                "pipeline_stages": [
                    "LEAD",
                    "RESEARCH",
                    "QUALIFICATION",
                    "OUTREACH",
                    "MEETING",
                    "PROPOSAL",
                    "NEGOTIATION",
                    "CUSTOMER",
                ],
                "scored_leads": scored,
                "next_best_actions": ["Reach top 20% leads", "Re-engage stalled proposals"],
            },
            confidence=confidence_from_sources(len(scored)),
            assumptions=["Lead data is curated input"],
            sources=["internal heuristic: lead scoring"],
            risks=["Outreach is an external action; requires approval before sending"],
            next_recommended_agents=["marketing", "ceo"],
        )


def _score_lead(lead: dict[str, object]) -> float:
    budget = as_number(lead.get("budget"))
    fit = as_number(lead.get("fit"), 50.0)
    intent = as_number(lead.get("intent"), 50.0)
    return weighted_100([(min(budget / 100, 100), 0.4), (fit, 0.3), (intent, 0.3)])


def _kpi_factors(kpis: list[object]) -> list[tuple[float, float]]:
    return [
        (min(as_number(k.get("value")) / max(as_number(k.get("target")), 1) * 100, 100), 1.0)
        for k in kpis
        if isinstance(k, dict)
    ]
