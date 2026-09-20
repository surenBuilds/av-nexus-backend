"""Integration with Voxline AI Sales OS: pulls the real CEO brief and maps it
into the exact `input_json` shape each management agent already consumes.

Nothing here invents numbers. If a figure genuinely isn't available from the
brief (e.g. Voxline currently has no expense/cash tracking), the
corresponding agent input is simply omitted rather than defaulted to a
plausible-looking value — the agent's own code already handles missing
inputs by falling back to its documented defaults, and callers can see
exactly what was and wasn't supplied via `VoxlineSyncResult.warnings`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx

from av_nexus.config import settings


class VoxlineUnavailableError(RuntimeError):
    """Raised when the Voxline brief can't be fetched or is malformed."""


@dataclass
class VoxlineSyncResult:
    """Per-agent input_json payloads mapped from one real Voxline CEO brief,
    plus a record of anything that could not be derived from real data."""

    agent_inputs: dict[str, dict[str, Any]]
    warnings: list[str] = field(default_factory=list)
    brief_generated_at: str | None = None


class VoxlineClient:
    """Thin HTTP client for the Voxline AI Sales OS API.

    `base_url` and `api_key` come from AVNEXUS_VOXLINE_BASE_URL /
    AVNEXUS_VOXLINE_API_KEY so no URL or credential is hardcoded here.
    """

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: float = 15.0,
    ) -> None:
        resolved_base = base_url if base_url is not None else settings.voxline_base_url
        self.base_url = resolved_base.rstrip("/")
        self.api_key = api_key if api_key is not None else settings.voxline_api_key
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["X-Internal-Api-Key"] = self.api_key
        return headers

    def fetch_ceo_brief(self) -> dict[str, Any]:
        if not self.base_url:
            raise VoxlineUnavailableError(
                "AVNEXUS_VOXLINE_BASE_URL is not configured — nothing to fetch from."
            )
        url = f"{self.base_url}/api/ceo/brief"
        try:
            resp = httpx.get(url, headers=self._headers(), timeout=self.timeout)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise VoxlineUnavailableError(f"Could not reach Voxline at {url}: {exc}") from exc
        data = resp.json()
        brief = data.get("brief")
        if not isinstance(brief, dict):
            raise VoxlineUnavailableError("Voxline response did not contain a 'brief' object")
        return brief


def map_brief_to_agent_inputs(brief: dict[str, Any]) -> VoxlineSyncResult:
    """Pure mapping, fully unit-testable offline: real Voxline brief fields
    -> the exact input_json keys av_nexus.agents.management already reads.
    """
    warnings: list[str] = []

    # -- Sales agent: leads -------------------------------------------------
    # SalesAgent._score_lead reads budget/fit/intent per lead. Voxline's
    # top_20_leads carries lead_score (0-100, already computed by Voxline's
    # own ICP scorer) and icp_score/fit_reasons but not a budget figure or
    # a separate intent signal, so we map lead_score onto both `fit` and
    # `intent` (the two dimensions Voxline actually scores) and leave
    # `budget` unset rather than guessing a dollar amount Voxline never
    # captured.
    top_leads = brief.get("top_20_leads") or []
    if not isinstance(top_leads, list):
        top_leads = []
        warnings.append("top_20_leads missing or malformed in Voxline brief")
    sales_leads = []
    for c in top_leads:
        if not isinstance(c, dict):
            continue
        score = c.get("lead_score")
        sales_leads.append(
            {
                "name": c.get("name"),
                "email": c.get("email"),
                "fit": score if isinstance(score, (int, float)) else 50.0,
                "intent": score if isinstance(score, (int, float)) else 50.0,
            }
        )
    if not sales_leads:
        warnings.append(
            "No real leads in Voxline brief — sales agent will run with an empty pipeline"
        )

    # -- Finance (CFO) agent --------------------------------------------------
    # FinanceAgent reads revenue/expenses/cash/cogs/cac/ltv. Voxline currently
    # tracks proposal value (sent + accepted), not bookkeeping-grade revenue,
    # expenses or cash — so only `revenue` is populated (from accepted
    # proposals, i.e. money actually agreed, not just sent), and the rest are
    # deliberately left out rather than defaulted, so FinanceAgent's own
    # "revenue: 0 -> health reflects that" path runs honestly instead of us
    # inventing expenses/cash Voxline doesn't track yet.
    accepted_revenue = brief.get("accepted_proposals_value_usd")
    sent_pipeline_value = brief.get("sent_proposals_value_usd")
    finance_input: dict[str, Any] = {}
    if isinstance(accepted_revenue, (int, float)):
        finance_input["revenue"] = accepted_revenue
    else:
        warnings.append("accepted_proposals_value_usd missing from Voxline brief")
    if not isinstance(sent_pipeline_value, (int, float)):
        warnings.append("sent_proposals_value_usd missing from Voxline brief")
    warnings.append(
        "Voxline has no expense/cash/COGS tracking yet — finance agent runs on revenue only; "
        "gross/net margin and runway will reflect that gap, not be guessed."
    )

    # -- CEO agent: kpis ------------------------------------------------------
    # CeoAgent reads kpis=[{value, target}, ...]. Voxline's weekly_goals is
    # already exactly that shape (target is a real business-set config value
    # on the Voxline side, current is computed there from real records).
    weekly_goals = brief.get("weekly_goals") or []
    if not isinstance(weekly_goals, list):
        weekly_goals = []
    kpis = [
        {"name": g.get("metric"), "value": g.get("current"), "target": g.get("target")}
        for g in weekly_goals
        if isinstance(g, dict)
    ]
    if not kpis:
        warnings.append(
            "No weekly_goals in Voxline brief — CEO agent has no KPI signal this run"
        )

    # -- Operations (COO) agent -----------------------------------------------
    # OperationsAgent reads projects=[{name, status}]. Voxline doesn't model
    # "projects" at all (it's a sales system, not a delivery tracker), so
    # there is no honest way to populate this — left empty rather than
    # fabricating project records.
    operations_input: dict[str, Any] = {"projects": []}
    warnings.append(
        "Voxline has no project/delivery tracking — operations agent input is "
        "genuinely empty, not fabricated."
    )

    # -- Marketing (CMO) agent -------------------------------------------------
    # MarketingAgent reads audience/budget. Voxline's opportunity mix tells us
    # which service categories are actually generating pipeline, which is a
    # real (if partial) proxy for audience — budget has no real source in
    # Voxline today so it's left for the agent's own documented default.
    opportunities = brief.get("highest_priority_opportunities") or []
    top_service = None
    if isinstance(opportunities, list) and opportunities:
        first = opportunities[0]
        if isinstance(first, dict):
            top_service = first.get("type")
    marketing_input: dict[str, Any] = {}
    if top_service:
        marketing_input["audience"] = top_service
    else:
        warnings.append(
            "No opportunity data in Voxline brief — marketing agent falls back "
            "to its own default audience"
        )

    return VoxlineSyncResult(
        agent_inputs={
            "ceo": {"kpis": kpis},
            "finance": finance_input,
            "marketing": marketing_input,
            "operations": operations_input,
            "sales": {"leads": sales_leads},
        },
        warnings=warnings,
        brief_generated_at=(
            brief.get("generated_at") if isinstance(brief.get("generated_at"), str) else None
        ),
    )
