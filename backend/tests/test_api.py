"""API integration tests (offline TestClient, demo seed disabled)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import register_and_login

API = "/api/v1"


def test_health(client: TestClient) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_auth_flow(client: TestClient) -> None:
    headers = register_and_login(client)
    me = client.get(f"{API}/auth/me", headers=headers)
    assert me.status_code == 200
    body = me.json()
    assert body["user"]["role"] == "chairman"
    assert body["user"]["can_authorize_level4"] is True
    assert body["organization"]["name"] == "Test Holding"


def test_auth_rejects_duplicate_email(client: TestClient) -> None:
    register_and_login(client)
    resp = client.post(
        f"{API}/auth/register",
        json={"email": "chair@example.com", "password": "test-password-123", "full_name": "Dup"},
    )
    assert resp.status_code == 409


def test_agents_registered_after_lifespan(client: TestClient) -> None:
    headers = register_and_login(client)
    agents = client.get(f"{API}/agents", headers=headers)
    assert agents.status_code == 200
    assert len(agents.json()) == 18
    ids = {a["agent_id"] for a in agents.json()}
    assert {"strategy", "opportunity_scout", "critic", "risk", "legal_compliance"} <= ids


def test_agent_by_id(client: TestClient) -> None:
    headers = register_and_login(client)
    resp = client.get(f"{API}/agents/opportunity_scout", headers=headers)
    assert resp.status_code == 200
    assert "opportunity_discovery" in resp.json()["capabilities_json"]


def test_task_run_lifecycle(client: TestClient) -> None:
    headers = register_and_login(client)
    created = client.post(
        f"{API}/tasks",
        headers=headers,
        json={
            "title": "Scan fintech",
            "goal": "Find opportunities in fintech",
            "capability": "opportunity_discovery",
        },
    )
    assert created.status_code == 201
    task_id = created.json()["id"]

    ran = client.post(f"{API}/tasks/{task_id}/run", headers=headers)
    assert ran.status_code == 200
    body = ran.json()["task"]
    assert body["status"] == "COMPLETED"
    assert body["confidence"] > 0
    assert body["output_json"]["mode"] == "deterministic"
    assert len(ran.json()["agent_runs"]) == 1
    assert len(ran.json()["messages"]) == 1  # RESULT message


def test_level4_task_requires_approval(client: TestClient) -> None:
    headers = register_and_login(client)
    created = client.post(
        f"{API}/tasks",
        headers=headers,
        json={
            "title": "Sign contract",
            "goal": "execute contract",
            "capability": "opportunity_discovery",
            "approval_level": 4,
        },
    )
    task_id = created.json()["id"]
    ran = client.post(f"{API}/tasks/{task_id}/run", headers=headers).json()
    assert ran["task"]["status"] == "APPROVAL_REQUIRED"

    approvals = client.get(f"{API}/approvals", headers=headers).json()
    assert len(approvals) == 1
    approval_id = approvals[0]["id"]
    assert approvals[0]["level"] == 4

    rejected = client.post(f"{API}/approvals/{approval_id}/reject", headers=headers,
                           json={"decision": "reject", "reason": "Not now"})
    assert rejected.status_code == 200
    task = client.get(f"{API}/tasks/{task_id}", headers=headers).json()
    assert task["status"] == "FAILED"
    assert task["approval_status"] == "rejected"


def test_dependency_cycle_rejected_via_api(client: TestClient) -> None:
    headers = register_and_login(client)
    a = client.post(f"{API}/tasks", headers=headers, json={"title": "A", "goal": "a"}).json()
    b = client.post(f"{API}/tasks", headers=headers, json={"title": "B", "goal": "b"}).json()
    ok = client.post(
        f"{API}/tasks/{b['id']}/dependencies", headers=headers,
        json={"depends_on_task_id": a["id"]},
    )
    assert ok.status_code == 200
    bad = client.post(
        f"{API}/tasks/{a['id']}/dependencies", headers=headers,
        json={"depends_on_task_id": b["id"]},
    )
    assert bad.status_code == 422


def test_opportunity_and_company_crud(client: TestClient) -> None:
    headers = register_and_login(client)
    opp = client.post(
        f"{API}/opportunities", headers=headers,
        json={"title": "AI Tutor", "category": "ai_education", "opportunity_score": 88.0},
    )
    assert opp.status_code == 201
    assert opp.json()["opportunity_score"] == 88.0
    listing = client.get(f"{API}/opportunities", headers=headers).json()
    assert listing[0]["title"] == "AI Tutor"

    company = client.post(
        f"{API}/companies", headers=headers,
        json={"name": "Nova Learning", "industry": "edtech"},
    )
    assert company.status_code == 201
    assert company.json()["is_demo"] is False
    comps = client.get(f"{API}/companies", headers=headers).json()
    assert comps[0]["name"] == "Nova Learning"


def test_dashboard_shape(client: TestClient) -> None:
    headers = register_and_login(client)
    dash = client.get(f"{API}/dashboard", headers=headers)
    assert dash.status_code == 200
    body = dash.json()
    assert body["is_demo"] is False
    assert "pending_approvals" in body
    assert "agent_activity" in body
    assert "group_performance" in body
    assert len(body["agent_activity"]) == 18  # synced during lifespan


def test_orchestrator_pipeline_via_api(client: TestClient) -> None:
    headers = register_and_login(client)
    resp = client.post(
        f"{API}/orchestrator/run", headers=headers,
        json={"goal": "I want to create a new business in fintech", "pipeline": "business_creation"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["tasks"]) == 8
    assert all(t["status"] == "COMPLETED" for t in body["tasks"])
    assert body["recommendation"]["recommendation"] in ("BUILD", "VALIDATE_FURTHER", "REJECT")
    assert body["decision_id"]
    assert body["approval_status"] == "pending"
    # approval now pending: chairman flow can approve it
    approvals = client.get(f"{API}/approvals", headers=headers).json()
    assert len(approvals) >= 1
    decision_resp = client.post(
        f"{API}/approvals/{approvals[0]['id']}/approve", headers=headers,
        json={"decision": "approve", "reason": "proceed"},
    )
    assert decision_resp.status_code == 200
    assert decision_resp.json()["status"] == "approved"


def test_memory_and_knowledge_graph(client: TestClient) -> None:
    headers = register_and_login(client)
    put = client.put(
        f"{API}/memory/global", headers=headers,
        json={"layer": "global", "key": "chairman_goals", "value": {"area": "fintech"}},
    )
    assert put.status_code == 200
    got = client.get(f"{API}/memory/global", headers=headers).json()
    assert got[0]["key"] == "chairman_goals"
    assert got[0]["value"] == {"area": "fintech"}

    ent = client.post(
        f"{API}/knowledge-graph/entities", headers=headers,
        json={"entity_type": "industry", "name": "fintech"},
    ).json()
    rel = client.post(
        f"{API}/knowledge-graph/relationships", headers=headers,
        json={
            "from_entity_id": ent["id"],
            "to_entity_id": ent["id"],
            "relationship_type": "operates_in",
        },
    )
    assert rel.status_code == 201
    graph = client.get(f"{API}/knowledge-graph", headers=headers).json()
    assert len(graph["entities"]) == 1
    assert graph["relationships"][0]["type"] == "operates_in"


def test_memory_rejects_invalid_layer(client: TestClient) -> None:
    headers = register_and_login(client)
    bad = client.put(
        f"{API}/memory/nope", headers=headers,
        json={"layer": "nope", "key": "k", "value": {}},
    )
    assert bad.status_code == 422


def test_agent_detail_runs_and_messages(client: TestClient) -> None:
    headers = register_and_login(client)
    runs = client.get(f"{API}/agents/opportunity_scout/runs", headers=headers)
    assert runs.status_code == 200
    assert isinstance(runs.json(), list)
    msgs = client.get(
        f"{API}/agents/opportunity_scout/messages", headers=headers
    )
    assert msgs.status_code == 200
    assert isinstance(msgs.json(), list)


def test_tasks_filter_by_owner_agent(client: TestClient) -> None:
    headers = register_and_login(client)
    created = client.post(
        f"{API}/tasks",
        headers=headers,
        json={
            "title": "Filter me",
            "goal": "go",
            "capability": "opportunity_discovery",
        },
    ).json()
    owner_id = created["owner_agent_id"]
    assert owner_id  # routed to an agent by capability
    only = client.get(f"{API}/tasks?agent_id={owner_id}", headers=headers).json()
    assert any(t["id"] == created["id"] for t in only)


def test_decisions_and_activity_feed(client: TestClient) -> None:
    headers = register_and_login(client)
    decisions = client.get(f"{API}/decisions", headers=headers)
    assert decisions.status_code == 200
    assert isinstance(decisions.json(), list)
    activity = client.get(f"{API}/activity", headers=headers)
    assert activity.status_code == 200
    items = activity.json()
    assert isinstance(items, list)
    if items:
        assert {"actor", "action", "entity", "status", "timestamp"} <= set(items[0])
