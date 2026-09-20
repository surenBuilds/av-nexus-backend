"""Tests for the Voxline integration.

test_map_brief_* are pure unit tests of map_brief_to_agent_inputs — no
network, no DB — proving the mapping is honest: real fields flow through,
missing ones are flagged in `warnings` rather than defaulted to a
plausible-looking fake number.

test_sync_endpoint_* exercise the /integrations/voxline/sync route with a
stubbed VoxlineClient (still no real network call) to prove the whole path
creates and runs real tasks for all 5 agents from mapped data.
"""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from av_nexus.integrations.voxline import VoxlineUnavailableError, map_brief_to_agent_inputs
from tests.conftest import register_and_login

API = "/api/v1"

REAL_BRIEF = {
    "generated_at": "2026-09-20T10:00:00Z",
    "top_20_leads": [
        {"name": "Nairi Medical Center", "email": "info@nairi.am", "lead_score": 92},
        {"name": "Yeremyan Products", "email": "sales@yeremyan.am", "lead_score": 84},
    ],
    "sent_proposals_value_usd": 4200,
    "accepted_proposals_value_usd": 1800,
    "pipeline_health_score": 63,
    "highest_priority_opportunities": [
        {"type": "Voxline AI Chatbot", "count": 5, "avg_deal_usd": 1500},
    ],
    "recommended_actions": ["Review 2 outreach message(s) awaiting approval"],
    "potential_risks": [],
    "weekly_goals": [
        {"target": 15, "current": 3, "metric": "Qualified Leads"},
        {"target": 5, "current": 1, "metric": "Meetings Scheduled"},
        {"target": 20000, "current": 4200, "metric": "Pipeline Added ($)"},
    ],
    "strategic_recommendations": [],
}

EMPTY_BRIEF = {
    "generated_at": "2026-09-20T10:00:00Z",
    "top_20_leads": [],
    "sent_proposals_value_usd": 0,
    "accepted_proposals_value_usd": 0,
    "pipeline_health_score": 0,
    "highest_priority_opportunities": [],
    "recommended_actions": [],
    "potential_risks": [],
    "weekly_goals": [],
    "strategic_recommendations": [],
}


def test_map_brief_carries_real_lead_scores_into_sales_input() -> None:
    result = map_brief_to_agent_inputs(REAL_BRIEF)
    leads = result.agent_inputs["sales"]["leads"]
    assert leads == [
        {"name": "Nairi Medical Center", "email": "info@nairi.am", "fit": 92, "intent": 92},
        {"name": "Yeremyan Products", "email": "sales@yeremyan.am", "fit": 84, "intent": 84},
    ]


def test_map_brief_uses_accepted_revenue_not_sent_pipeline_for_finance() -> None:
    result = map_brief_to_agent_inputs(REAL_BRIEF)
    assert result.agent_inputs["finance"]["revenue"] == 1800
    assert "cash" not in result.agent_inputs["finance"]
    assert "expenses" not in result.agent_inputs["finance"]


def test_map_brief_ceo_kpis_match_real_weekly_goals() -> None:
    result = map_brief_to_agent_inputs(REAL_BRIEF)
    kpis = result.agent_inputs["ceo"]["kpis"]
    assert {"name": "Qualified Leads", "value": 3, "target": 15} in kpis
    assert len(kpis) == 3


def test_map_brief_operations_input_is_genuinely_empty_not_fabricated() -> None:
    result = map_brief_to_agent_inputs(REAL_BRIEF)
    assert result.agent_inputs["operations"] == {"projects": []}
    assert any("no project" in w.lower() for w in result.warnings)


def test_map_brief_empty_data_produces_warnings_not_fake_numbers() -> None:
    result = map_brief_to_agent_inputs(EMPTY_BRIEF)
    assert result.agent_inputs["sales"]["leads"] == []
    # accepted_proposals_value_usd is genuinely 0 in this brief, and 0 is
    # real data (not a missing value), so it's still included honestly.
    assert result.agent_inputs["finance"]["revenue"] == 0
    assert any("no real leads" in w.lower() for w in result.warnings)
    assert any("no weekly_goals" in w.lower() for w in result.warnings)


def test_sync_endpoint_runs_all_five_agents_from_real_brief(client: TestClient) -> None:
    headers = register_and_login(client)
    with patch(
        "av_nexus.integrations.voxline.VoxlineClient.fetch_ceo_brief",
        return_value=REAL_BRIEF,
    ):
        resp = client.post(f"{API}/integrations/voxline/sync", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["brief_generated_at"] == "2026-09-20T10:00:00Z"
    agent_ids = {r["agent_id"] for r in body["runs"]}
    assert agent_ids == {"ceo", "finance", "marketing", "operations", "sales"}
    for run in body["runs"]:
        assert run["status"] == "COMPLETED", run
        assert run["output_json"] is not None
    sales_run = next(r for r in body["runs"] if r["agent_id"] == "sales")
    scored = sales_run["output_json"]["result"]["scored_leads"]
    assert {s["lead"] for s in scored} == {"Nairi Medical Center", "Yeremyan Products"}


def test_sync_endpoint_returns_502_when_voxline_unreachable(client: TestClient) -> None:
    headers = register_and_login(client)
    with patch(
        "av_nexus.integrations.voxline.VoxlineClient.fetch_ceo_brief",
        side_effect=VoxlineUnavailableError("Could not reach Voxline at http://example.invalid/api/ceo/brief"),
    ):
        resp = client.post(f"{API}/integrations/voxline/sync", headers=headers)
    assert resp.status_code == 502
    assert "Voxline" in resp.json()["detail"]
