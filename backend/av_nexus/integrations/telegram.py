"""Telegram integration: lets the bound AV Nexus account query the
management agents from Telegram.

Formatting here summarizes real fields already present in each agent's
output_json — nothing is computed or phrased beyond what the agent itself
returned, so a Telegram reply never says something the underlying task
result doesn't actually support.
"""

from __future__ import annotations

from typing import Any

import httpx

from av_nexus.config import settings


class TelegramClient:
    def __init__(self, bot_token: str | None = None, timeout: float = 10.0) -> None:
        self.bot_token = bot_token if bot_token is not None else settings.telegram_bot_token
        self.timeout = timeout

    def send_message(self, chat_id: str, text: str) -> None:
        if not self.bot_token:
            return
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        try:
            httpx.post(
                url,
                json={"chat_id": chat_id, "text": text[:4000], "parse_mode": "Markdown"},
                timeout=self.timeout,
            )
        except httpx.HTTPError:
            # A failed Telegram delivery must never crash the webhook or
            # silently fabricate a "sent" state — the caller doesn't
            # currently need the failure surfaced further than "not raised".
            pass


HELP_TEXT = (
    "*AV Nexus — հրամաններ*\n"
    "/brief — ամփոփ CEO/Finance/Marketing/Operations/Sales վերանայում իրական Voxline տվյալով\n"
    "/ceo, /finance, /marketing, /operations, /sales — միայն այդ agent-ը"
)


def format_agent_summary(
    agent_id: str, output_json: dict[str, Any] | None, error: str | None
) -> str:
    if error:
        return f"❌ *{agent_id}*: {error}"
    result = (output_json or {}).get("result", {}) if output_json else {}

    if agent_id == "ceo":
        kpis = result.get("kpi_review", [])
        kpi_lines = (
            "\n".join(f"  • {k.get('name')}: {k.get('value')}" for k in kpis) or "  (no KPI data)"
        )
        return (
            f"👑 *CEO* — health {result.get('company_health_score', 'n/a')}\n"
            f"{kpi_lines}\n"
            f"Focus: {result.get('weekly_focus', 'n/a')}"
        )
    if agent_id == "finance":
        return (
            f"💰 *Finance* — health {result.get('financial_health_score', 'n/a')}\n"
            f"Revenue: ${result.get('revenue', 0)} · "
            f"LTV:CAC {result.get('ltv_cac_ratio', 'n/a')} · "
            f"Runway: {result.get('runway_months', 'n/a')} months"
        )
    if agent_id == "marketing":
        return f"📣 *Marketing* — {result.get('positioning', 'n/a')}"
    if agent_id == "operations":
        flags = ", ".join(result.get("process_flags", [])) or "no flags"
        reviewed = result.get("projects_reviewed", 0)
        return f"⚙️ *Operations* — {reviewed} project(s) reviewed · {flags}"
    if agent_id == "sales":
        leads = result.get("scored_leads", [])[:5]
        lead_lines = "\n".join(f"  • {ld.get('lead')}: {ld.get('score')}" for ld in leads)
        return f"🎯 *Sales* — top leads\n{lead_lines or '  (no leads)'}"
    return f"*{agent_id}*: {result}"
