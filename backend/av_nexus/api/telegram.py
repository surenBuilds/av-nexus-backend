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
from sqlalchemy.orm import Session

from av_nexus.config import settings
from av_nexus.core.security import get_org_for_user
from av_nexus.db.session import create_session
from av_nexus.integrations.telegram import (
    HELP_TEXT,
    TelegramClient,
    format_agent_summary,
    format_coding_result,
    translate_warning,
)
from av_nexus.integrations.voxline import VoxlineUnavailableError, run_agents_from_voxline
from av_nexus.llm.factory import build_llm_client
from av_nexus.models.agents import Task
from av_nexus.models.identity import Organization, User
from av_nexus.orchestrator.service import OrchestratorService

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

    is_code_command = text.startswith("/code")
    agent_ids: list[str] | None = None
    if text == "/brief":
        agent_ids = None  # all 5
    elif text in _SINGLE_AGENT_COMMANDS:
        agent_ids = [_SINGLE_AGENT_COMMANDS[text]]
    elif not is_code_command:
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

        if is_code_command:
            task_text = text[len("/code") :].strip()
            if not task_text:
                telegram.send_message(
                    chat_id,
                    "Օգտագործում. /code ֆայլ1,ֆայլ2 | նկարագրություն\n"
                    "Օրինակ. /code package.json | bump react to ^18.2.0",
                )
                return JSONResponse({"ok": True})
            if "|" in task_text:
                files_part, _, task_desc = task_text.partition("|")
                context_files = [f.strip() for f in files_part.split(",") if f.strip()]
                task_text = task_desc.strip()
            else:
                context_files = []
            if not context_files:
                telegram.send_message(
                    chat_id,
                    "Ինձ պետք է իմանալ, թե որ ֆայլ(եր)ն ես ուզում, որ կարդամ ու փոփոխեմ, "
                    "այլապես չեմ կարող իրական բովանդակություն տեսնել։\n\n"
                    "Օգտագործում. /code ֆայլ1,ֆայլ2 | նկարագրություն\n"
                    "Օրինակ. /code package.json | bump react to ^18.2.0",
                )
                return JSONResponse({"ok": True})
            repo = (settings.github_allowed_repos or "").split(",")[0].strip()
            if not repo:
                telegram.send_message(
                    chat_id, "❌ AVNEXUS_GITHUB_ALLOWED_REPOS-ը կոնֆիգուրացված չէ"
                )
                return JSONResponse({"ok": True})
            task = await _run_coding_task(
                session, org, user, repo=repo, task_text=task_text, context_files=context_files
            )
            telegram.send_message(chat_id, format_coding_result(task.output_json, task.error))
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


async def _run_coding_task(
    session: Session,
    org: Organization,
    user: User,
    *,
    repo: str,
    task_text: str,
    context_files: list[str],
) -> Task:
    """Create and run one Coding Agent task, routed purely by capability so
    it always reaches CodingAgent regardless of registry ordering."""
    from av_nexus.agents import get_registry

    service = OrchestratorService(session, get_registry(), build_llm_client())
    task = service.create_task(
        org,
        user,
        title=f"Telegram /code — {task_text[:60]}",
        goal=task_text,
        capability="code_changes",
        approval_level=1,
        input_json={"repo": repo, "task": task_text, "context_files": context_files},
    )
    session.commit()
    session.refresh(task)
    await service.run_task(task, org, user)
    session.refresh(task)
    return task
