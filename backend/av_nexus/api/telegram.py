"""Telegram webhook for querying AV Nexus management agents from Telegram.

Security model (deliberately conservative — this endpoint is public):
- Refuses to do anything unless AVNEXUS_TELEGRAM_BOT_TOKEN,
  AVNEXUS_TELEGRAM_WEBHOOK_SECRET, AVNEXUS_TELEGRAM_ALLOWED_CHAT_ID, and
  AVNEXUS_TELEGRAM_BOUND_USER_EMAIL are all set.
- Verifies Telegram's X-Telegram-Bot-Api-Secret-Token header on every call.
- Only replies to messages from the one allowed chat id; everything else is
  silently dropped (still 200, so Telegram doesn't retry-storm us, but no
  agent runs and no data leaves for an unrecognized chat).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse

from av_nexus.config import settings
from av_nexus.core.security import get_org_for_user
from av_nexus.db.session import create_session
from av_nexus.integrations.telegram import (
    HELP_TEXT,
    TelegramClient,
    format_agent_summary,
    translate_warning,
)
from av_nexus.integrations.voxline import VoxlineUnavailableError, run_agents_from_voxline
from av_nexus.models.identity import User

router = APIRouter(prefix="/integrations/telegram", tags=["integrations"])

_SINGLE_AGENT_COMMANDS = {
    "/ceo": "ceo",
    "/finance": "finance",
    "/marketing": "marketing",
    "/operations": "operations",
    "/sales": "sales",
}


def _configured() -> bool:
    return bool(
        settings.telegram_bot_token
        and settings.telegram_webhook_secret
        and settings.telegram_allowed_chat_id
        and settings.telegram_bound_user_email
    )


@router.post("/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> JSONResponse:
    if not _configured():
        # Not an error to Telegram — the integration is simply off.
        return JSONResponse({"ok": True, "skipped": "telegram integration not configured"})

    if x_telegram_bot_api_secret_token != settings.telegram_webhook_secret:
        return JSONResponse({"ok": False}, status_code=403)

    update: dict[str, Any] = await request.json()
    message = update.get("message") or {}
    chat = message.get("chat") or {}
    chat_id = str(chat.get("id", ""))
    text = str(message.get("text", "")).strip()

    if not chat_id or chat_id != settings.telegram_allowed_chat_id:
        # Unrecognized chat: drop silently, never run agents or leak data.
        return JSONResponse({"ok": True})

    telegram = TelegramClient()

    if text in ("/start", "/help", ""):
        telegram.send_message(chat_id, HELP_TEXT)
        return JSONResponse({"ok": True})

    agent_ids: list[str] | None
    if text == "/brief":
        agent_ids = None  # all 5
    elif text in _SINGLE_AGENT_COMMANDS:
        agent_ids = [_SINGLE_AGENT_COMMANDS[text]]
    else:
        telegram.send_message(chat_id, "Չճանաչված հրաման։\n\n" + HELP_TEXT)
        return JSONResponse({"ok": True})

    session = create_session()
    try:
        user = session.query(User).filter(User.email == settings.telegram_bound_user_email).first()
        if user is None:
            telegram.send_message(
                chat_id, "❌ Bound account not found — check AVNEXUS_TELEGRAM_BOUND_USER_EMAIL"
            )
            return JSONResponse({"ok": True})
        org = get_org_for_user(session, user)
        if org is None:
            telegram.send_message(chat_id, "❌ Bound account has no organization")
            return JSONResponse({"ok": True})

        try:
            result, outcomes = await run_agents_from_voxline(session, org, user, agent_ids)
        except VoxlineUnavailableError as exc:
            telegram.send_message(chat_id, f"❌ Voxline unreachable: {exc}")
            return JSONResponse({"ok": True})

        parts = [format_agent_summary(o.agent_id, o.output_json, o.error) for o in outcomes]
        if result.warnings:
            translated = [translate_warning(w) for w in result.warnings]
            parts.append("\n⚠️ " + "\n⚠️ ".join(translated))
        telegram.send_message(chat_id, "\n\n".join(parts))
    finally:
        session.close()

    return JSONResponse({"ok": True})
