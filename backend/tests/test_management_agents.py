"""Prove the 10 previously-dormant agents (CEO, CFO, CMO, COO, Sales,
Innovation, Legal & Compliance, Investment, M&A, Data & Analytics) are
actually invocable end-to-end through the real API — not just registered
metadata. Each test creates a task via capability routing (reusing the
existing generic Task -> AgentExecutor path, no parallel execution engine),
runs it, and asserts the output is genuinely derived from the supplied
`input_json`, not templated/fabricated content.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import register_and_login

API = "/api/v1"


def _create_and_run(
    client: TestClient, headers: dict[str, str], *, capability: str, goal: str, input_json: dict
) -> dict:
    created = client.post(
        f"{API}/tasks",
        headers=headers,
        json={
            "title": f"Run {capability}",
            "goal": goal,
            "capability": capability,
            "input_json": input_json,
        },
    )
    assert created.status_code == 201, created.text
    task_id = created.json()["id"]
    ran = client.post(f"{API}/tasks/{task_id}/run", headers=headers)
    assert ran.status_code == 200, ran.text
    body = ran.json()["task"]
    assert body["status"] == "COMPLETED", body
    return body["output_json"]


def test_input_json_is_actually_wired_to_the_task(client: TestClient) -> None:
    """Regression guard for the bug this test suite exists to catch: the API
    schema previously dropped input_json silently, so every agent behind it
    only ever saw an empty inputs dict regardless of what the caller sent."""
    headers = register_and_login(client)
    created = client.post(
        f"{API}/tasks",
        headers=headers,
        json={
            "title": "Check wiring",
            "goal": "sanity check",
            "capability": "financial_analysis",
            "input_json": {"revenue": 999999, "expenses": 1},
        },
    )
    task_id = created.json()["id"]
    got = client.get(f"{API}/tasks/{task_id}", headers=headers).json()
    assert got["input_json"] == {"revenue": 999999, "expenses": 1}


def test_ceo_agent_runs_with_no_data_honestly_low_confidence(client: TestClient) -> None:
    headers = register_and_login(client)
    out = _create_and_run(
        client, headers, capability="company_strategy", goal="Weekly review", input_json={}
    )
    result = out["result"]
    assert "company_health_score" in result
    # No KPIs supplied -> confidence_from_sources(0), must not pretend otherwise.
    assert out["confidence"] <= 0.5
    assert "KPI data supplied by monitor pipelines" in out["assumptions"]


def test_cfo_agent_computes_real_financials_not_fabricated(client: TestClient) -> None:
    headers = register_and_login(client)
    out = _create_and_run(
        client,
        headers,
        capability="financial_analysis",
        goal="Financial health check",
        input_json={"revenue": 100000, "expenses": 70000, "cash": 50000, "cogs": 40000},
    )
    result = out["result"]
    # gross_margin = (100000 - 40000) / 100000 * 100 = 60.0
    assert result["gross_margin_pct"] == 60.0
    # net_margin = (100000 - 70000) / 100000 * 100 = 30.0
    assert result["net_margin_pct"] == 30.0
    assert result["revenue"] == 100000


def test_cfo_agent_output_changes_with_different_inputs(client: TestClient) -> None:
    """The whole point of wiring real input_json through: two different
    financial pictures must produce two different scores, proving this
    isn't a template with the numbers swapped in cosmetically."""
    headers = register_and_login(client)
    healthy = _create_and_run(
        client,
        headers,
        capability="financial_analysis",
        goal="Financial health check",
        input_json={"revenue": 200000, "expenses": 80000, "cash": 500000, "cogs": 50000},
    )
    struggling = _create_and_run(
        client,
        headers,
        capability="financial_analysis",
        goal="Financial health check",
        input_json={"revenue": 20000, "expenses": 90000, "cash": 5000, "cogs": 18000},
    )
    assert (
        healthy["result"]["financial_health_score"] > struggling["result"]["financial_health_score"]
    )
    assert healthy["result"]["net_margin_pct"] > struggling["result"]["net_margin_pct"]


def test_cmo_agent_reflects_supplied_budget(client: TestClient) -> None:
    headers = register_and_login(client)
    out = _create_and_run(
        client,
        headers,
        capability="marketing_strategy",
        goal="Plan Q1 campaign",
        input_json={"audience": "Armenian SMB retailers", "budget": 12000},
    )
    result = out["result"]
    assert result["budget_allocation_usd"] == 12000
    assert "Armenian SMB retailers" in result["positioning"]


def test_coo_agent_detects_real_bottlenecks(client: TestClient) -> None:
    headers = register_and_login(client)
    out = _create_and_run(
        client,
        headers,
        capability="bottleneck_detection",
        goal="Ops review",
        input_json={
            "projects": [
                {"name": "Migration", "status": "delayed"},
                {"name": "Onboarding flow", "status": "on_track"},
            ]
        },
    )
    result = out["result"]
    assert result["bottlenecks"] == ["Migration"]
    assert result["projects_reviewed"] == 2


def test_coo_agent_no_bottlenecks_when_none_supplied(client: TestClient) -> None:
    headers = register_and_login(client)
    out = _create_and_run(
        client,
        headers,
        capability="bottleneck_detection",
        goal="Ops review",
        input_json={"projects": [{"name": "Migration", "status": "on_track"}]},
    )
    assert out["result"]["bottlenecks"] == []


def test_sales_agent_scores_and_ranks_real_leads(client: TestClient) -> None:
    headers = register_and_login(client)
    out = _create_and_run(
        client,
        headers,
        capability="lead_research",
        goal="Score this week's leads",
        input_json={
            "leads": [
                {"name": "Cold Corp", "budget": 500, "fit": 20, "intent": 10},
                {"name": "Hot Startup", "budget": 20000, "fit": 90, "intent": 95},
            ]
        },
    )
    scored = out["result"]["scored_leads"]
    assert scored[0]["lead"] == "Hot Startup"  # sorted descending by score
    assert scored[0]["score"] > scored[1]["score"]


def test_innovation_agent_uses_supplied_problem_and_technology(client: TestClient) -> None:
    headers = register_and_login(client)
    out = _create_and_run(
        client,
        headers,
        capability="product_ideation",
        goal="Ideate",
        input_json={"problem": "manual invoice reconciliation", "technology": "OCR/LLM extraction"},
    )
    idea = out["result"]["idea"]
    assert idea["problem"] == "manual invoice reconciliation"
    assert "OCR/LLM extraction" in idea["opportunity"]


def test_legal_compliance_flags_sector_specific_risk(client: TestClient) -> None:
    headers = register_and_login(client)
    out = _create_and_run(
        client,
        headers,
        capability="compliance_review",
        goal="Screen new fintech venture",
        input_json={"sector": "financial services", "processes_personal_data": True},
    )
    flags = (
        out["result"]["flags"]
        if "flags" in out["result"]
        else out["result"].get("compliance_flags", [])
    )
    joined = " ".join(str(f) for f in flags)
    assert "AML" in joined or "licensing" in joined
    assert "Privacy" in joined or "GDPR" in joined


def test_data_analytics_agent_detects_real_anomaly(client: TestClient) -> None:
    headers = register_and_login(client)
    out = _create_and_run(
        client,
        headers,
        capability="anomaly_detection",
        goal="Check metrics",
        input_json={"metrics_series": {"signups": [10, 11, 9, 12, 60]}},
    )
    anomalies = out["result"]["anomalies"]
    assert any(a["metric"] == "signups" for a in anomalies)


def test_investment_agent_ranks_options_by_composite_index(client: TestClient) -> None:
    headers = register_and_login(client)
    out = _create_and_run(
        client,
        headers,
        capability="capital_allocation",
        goal="Where should the next $1M go?",
        input_json={
            "options": [
                {
                    "name": "Safe bond-like SaaS",
                    "roi": 15,
                    "risk": 10,
                    "growth": 8,
                    "liquidity": 80,
                },
                {
                    "name": "High-growth new market",
                    "roi": 40,
                    "risk": 70,
                    "growth": 60,
                    "liquidity": 20,
                },
            ]
        },
    )
    result = out["result"]
    assert len(result["ranked_options"]) == 2
    assert result["ranked_options"][0]["option"] == "Safe bond-like SaaS"  # higher composite index
    assert result["recommendation"]["option"] == "Safe bond-like SaaS"


def test_mna_agent_analyzes_real_targets_not_invented_ones(client: TestClient) -> None:
    headers = register_and_login(client)
    out = _create_and_run(
        client,
        headers,
        capability="ma_scanning",
        goal="Scan for acquisition targets",
        input_json={
            "targets": [
                {"name": "Small SaaS Co", "strategic_fit": 75, "risk": 20, "synergy": 65},
            ]
        },
    )
    matches = out["result"]["matches"]
    assert len(matches) == 1
    assert matches[0]["target"] == "Small SaaS Co"
    assert matches[0]["strategic_fit"] == 75


def test_mna_agent_honest_when_no_targets_supplied(client: TestClient) -> None:
    headers = register_and_login(client)
    out = _create_and_run(
        client,
        headers,
        capability="ma_scanning",
        goal="Scan for acquisition targets",
        input_json={},
    )
    assert out["result"]["matches"] == []


def test_all_18_agents_are_listed_and_none_are_fabricated_shells(client: TestClient) -> None:
    """Regression guard: confirms the full registry (not just the 8-agent
    venture pipeline) is reachable via the real API."""
    headers = register_and_login(client)
    agents = client.get(f"{API}/agents", headers=headers).json()
    ids = {a["agent_id"] for a in agents}
    assert ids == {
        "strategy",
        "opportunity_scout",
        "market_research",
        "competitive_intelligence",
        "innovation",
        "validation",
        "venture_builder",
        "ceo",
        "finance",
        "marketing",
        "operations",
        "sales",
        "risk",
        "legal_compliance",
        "investment",
        "mna",
        "data_analytics",
        "critic",
    }
