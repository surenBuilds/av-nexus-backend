"""Tests for the Telegram webhook.

Covers the fail-closed security model (unconfigured -> no-op, wrong secret
-> 403, unrecognized chat -> silently dropped) and that /brief and the
single-agent commands actually run real agents against a mocked Voxline
brief and send a summary back — mirroring test_voxline_integration.py's
approach of mocking only the network boundary (VoxlineClient) and the
Telegram send, never the agent logic itself.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from av_nexus.config import settings
from tests.conftest import register_and_login
from tests.test_voxline_integration import REAL_BRIEF

API = "/api/v1"
WEBHOOK = f"{API}/integrations/telegram/webhook"
SECRET_HEADER = "X-Telegram-Bot-Api-Secret-Token"


def _telegram_settings(*, chat_id: str = "12345", email: str = "chair@example.com") -> None:
    settings.telegram_bot_token = "test-bot-token"
    settings.telegram_webhook_secret = "test-webhook-secret"
    settings.telegram_allowed_chat_id = chat_id
    settings.telegram_bound_user_email = email


def _clear_telegram_settings() -> None:
    settings.telegram_bot_token = ""
    settings.telegram_webhook_secret = ""
    settings.telegram_allowed_chat_id = ""
    settings.telegram_bound_user_email = ""


def _update(text: str, chat_id: str = "12345") -> dict:
    return {"message": {"chat": {"id": int(chat_id)}, "text": text}}


def teardown_function() -> None:
    _clear_telegram_settings()


def test_webhook_noop_when_not_configured(client: TestClient) -> None:
    _clear_telegram_settings()
    resp = client.post(WEBHOOK, json=_update("/brief"))
    assert resp.status_code == 200
    assert resp.json()["skipped"]


def test_webhook_rejects_wrong_secret_token(client: TestClient) -> None:
    register_and_login(client)
    _telegram_settings()
    resp = client.post(WEBHOOK, json=_update("/brief"), headers={SECRET_HEADER: "wrong"})
    assert resp.status_code == 403


def test_webhook_drops_unauthorized_chat_without_running_agents(client: TestClient) -> None:
    register_and_login(client)
    _telegram_settings(chat_id="12345")
    with patch("av_nexus.api.telegram.TelegramClient.send_message") as mock_send:
        resp = client.post(
            WEBHOOK,
            json=_update("/brief", chat_id="99999"),
            headers={SECRET_HEADER: "test-webhook-secret"},
        )
    assert resp.status_code == 200
    mock_send.assert_not_called()


def test_webhook_help_command_sends_help_text(client: TestClient) -> None:
    register_and_login(client)
    _telegram_settings()
    with patch("av_nexus.api.telegram.TelegramClient.send_message") as mock_send:
        resp = client.post(
            WEBHOOK, json=_update("/help"), headers={SECRET_HEADER: "test-webhook-secret"}
        )
    assert resp.status_code == 200
    mock_send.assert_called_once()
    assert "AV Nexus" in mock_send.call_args.args[1]


def test_webhook_brief_runs_all_five_agents_from_real_voxline_data(client: TestClient) -> None:
    register_and_login(client)
    _telegram_settings()
    with (
        patch(
            "av_nexus.integrations.voxline.VoxlineClient.fetch_ceo_brief",
            return_value=REAL_BRIEF,
        ),
        patch("av_nexus.api.telegram.TelegramClient.send_message") as mock_send,
    ):
        resp = client.post(
            WEBHOOK, json=_update("/brief"), headers={SECRET_HEADER: "test-webhook-secret"}
        )
    assert resp.status_code == 200
    mock_send.assert_called_once()
    sent_text = mock_send.call_args.args[1]
    for label in ("Տնօրեն", "Ֆինանսներ", "Մարքեթինգ", "Գործառնություններ", "Վաճառք"):
        assert label in sent_text
    assert "Nairi Medical Center" in sent_text


def test_webhook_single_agent_command_runs_only_that_agent(client: TestClient) -> None:
    register_and_login(client)
    _telegram_settings()
    with (
        patch(
            "av_nexus.integrations.voxline.VoxlineClient.fetch_ceo_brief",
            return_value=REAL_BRIEF,
        ),
        patch("av_nexus.api.telegram.TelegramClient.send_message") as mock_send,
    ):
        resp = client.post(
            WEBHOOK, json=_update("/sales"), headers={SECRET_HEADER: "test-webhook-secret"}
        )
    assert resp.status_code == 200
    sent_text = mock_send.call_args.args[1]
    assert "Վաճառք" in sent_text
    assert "Տնօրեն" not in sent_text
    assert "Nairi Medical Center" in sent_text


def test_webhook_translates_known_warnings_to_armenian(client: TestClient) -> None:
    register_and_login(client)
    _telegram_settings()
    with (
        patch(
            "av_nexus.integrations.voxline.VoxlineClient.fetch_ceo_brief",
            return_value=REAL_BRIEF,
        ),
        patch("av_nexus.api.telegram.TelegramClient.send_message") as mock_send,
    ):
        resp = client.post(
            WEBHOOK, json=_update("/brief"), headers={SECRET_HEADER: "test-webhook-secret"}
        )
    assert resp.status_code == 200
    sent_text = mock_send.call_args.args[1]
    assert "Voxline-ը դեռ ծախսեր" in sent_text
    assert "Voxline has no expense" not in sent_text


def test_send_message_logs_instead_of_silently_swallowing_telegram_rejection(capsys) -> None:
    # This is the exact bug that made the bot look broken: Telegram
    # returning a non-200 (e.g. bad request) isn't a network error, so
    # httpx doesn't raise — it must be checked explicitly or a failed send
    # looks identical to a successful one.
    from av_nexus.integrations.telegram import TelegramClient

    client = TelegramClient(bot_token="fake-token")
    mock_response = MagicMock()
    mock_response.status_code = 400
    mock_response.text = '{"ok":false,"description":"Bad Request: can\'t parse entities"}'
    with patch("httpx.post", return_value=mock_response):
        client.send_message("123", "hello")
    captured = capsys.readouterr()
    assert "sendMessage failed 400" in captured.out
