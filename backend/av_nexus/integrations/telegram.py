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
            resp = httpx.post(
                url,
                json={"chat_id": chat_id, "text": text[:4000]},
                timeout=self.timeout,
            )
            if resp.status_code != 200:
                # Telegram rejected the message (e.g. bad request) — this is
                # an HTTP 200/4xx from Telegram's API, not a network error,
                # so httpx doesn't raise on it by itself. Surface it in the
                # app logs instead of silently pretending delivery worked.
                print(f"[telegram] sendMessage failed {resp.status_code}: {resp.text[:300]}")
        except httpx.HTTPError as exc:
            print(f"[telegram] sendMessage network error: {exc}")


HELP_TEXT = (
    "AV Nexus — հրամաններ\n"
    "/brief — ամփոփ Տնօրեն/Ֆինանսներ/Մարքեթինգ/Գործառնություններ/Վաճառք վերանայում\n"
    "իրական Voxline տվյալով\n"
    "/ceo, /finance, /marketing, /operations, /sales — միայն այդ ուղղությունը"
)

# Known, fixed warning strings from av_nexus.integrations.voxline translated
# for Telegram. An unmapped warning falls back to its original English text
# rather than being silently dropped or mistranslated.
WARNING_TRANSLATIONS: dict[str, str] = {
    (
        "Voxline has no expense/cash/COGS tracking yet — finance agent runs on revenue only; "
        "gross/net margin and runway will reflect that gap, not be guessed."
    ): (
        "Voxline-ը դեռ ծախսեր/քեշ չի հետևում. finance agent-ը հաշվարկում է միայն եկամուտից. "
        "margin-ը և runway-ն կարտացոլեն այս բացը, չեն գուշակվի։"
    ),
    (
        "Voxline has no project/delivery tracking — operations agent input is genuinely "
        "empty, not fabricated."
    ): (
        "Voxline-ը project tracking չունի. operations agent-ի input-ը իրապես "
        "դատարկ է, ոչ թե հորինված։"
    ),
}


def translate_warning(warning: str) -> str:
    return WARNING_TRANSLATIONS.get(warning, warning)


def format_agent_summary(
    agent_id: str, output_json: dict[str, Any] | None, error: str | None
) -> str:
    if error:
        return f"❌ {agent_id}: {error}"
    result = (output_json or {}).get("result", {}) if output_json else {}

    if agent_id == "ceo":
        kpis = result.get("kpi_review", [])
        # KPI names come through from Voxline's own weekly_goals metric
        # labels (see integrations/voxline.py) — translate the known ones,
        # leave anything else as-is rather than guessing a translation.
        kpi_name_map = {
            "Qualified Leads": "Որակավորված leads",
            "Meetings Scheduled": "Պլանավորված հանդիպումներ",
            "Pipeline Added ($)": "Ավելացված pipeline ($)",
        }
        kpi_lines = (
            "\n".join(
                f"  • {kpi_name_map.get(k.get('name'), k.get('name'))}: {k.get('value')}"
                for k in kpis
            )
            or "  (KPI տվյալ չկա)"
        )
        return (
            f"👑 Տնօրեն (CEO) — առողջության ցուցանիշ {result.get('company_health_score', 'n/a')}\n"
            f"{kpi_lines}\n"
            f"Ֆոկուս. {result.get('weekly_focus', 'n/a')}"
        )
    if agent_id == "finance":
        return (
            f"💰 Ֆինանսներ — առողջության ցուցանիշ {result.get('financial_health_score', 'n/a')}\n"
            f"Եկամուտ՝ ${result.get('revenue', 0)} · "
            f"LTV:CAC {result.get('ltv_cac_ratio', 'n/a')} · "
            f"Ինքնավարության ժամկետ (runway)՝ {result.get('runway_months', 'n/a')} ամիս"
        )
    if agent_id == "marketing":
        return f"📣 Մարքեթինգ — {result.get('positioning', 'n/a')}"
    if agent_id == "operations":
        flags = ", ".join(result.get("process_flags", [])) or "flag չկա"
        reviewed = result.get("projects_reviewed", 0)
        return f"⚙️ Գործառնություններ — {reviewed} project վերանայված · {flags}"
    if agent_id == "sales":
        leads = result.get("scored_leads", [])[:5]
        lead_lines = "\n".join(f"  • {ld.get('lead')}: {ld.get('score')}" for ld in leads)
        return f"🎯 Վաճառք — թոփ lead-ներ\n{lead_lines or '  (lead չկա)'}"
    return f"{agent_id}: {result}"
