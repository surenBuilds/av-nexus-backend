"""Security hardening negative-path tests.

Verifies org isolation, role gating, double-decision protection (including a
deterministic interleaved-session race), JWT expiry/tampering rejection on every
protected route, and list-endpoint non-leakage. No changes here to pipeline or
agent logic: only authz boundaries are exercised.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from jose import jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from av_nexus.agents import get_registry
from av_nexus.config import settings
from av_nexus.core.security import create_access_token, hash_password
from av_nexus.db.session import create_session
from av_nexus.llm.factory import build_llm_client
from av_nexus.models.decisions import Approval
from av_nexus.models.enums import Role
from av_nexus.models.identity import Organization, User
from av_nexus.orchestrator.service import OrchestratorService

API = "/api/v1"

CHAIRMAN_ACTOR = User(
    id=uuid.UUID(int=42), email="actor@example.com", password_hash="x",
    full_name="Actor", role=Role.CHAIRMAN.value, can_authorize_level4=True,
)

PASSWORD = "test-password-123"


def _register(client: TestClient, email: str, org_name: str) -> dict:
    resp = client.post(
        f"{API}/auth/register",
        json={"email": email, "password": PASSWORD, "full_name": "Chair", "org_name": org_name},
    )
    assert resp.status_code == 201, resp.text
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _create_pending_approval(client: TestClient, headers: dict) -> dict:
    created = client.post(
        f"{API}/tasks",
        headers=headers,
        json={
            "title": "L4 gate",
            "goal": "decide the big move",
            "capability": "opportunity_discovery",
            "approval_level": 4,
        },
    )
    assert created.status_code == 201, created.text
    task_id = created.json()["id"]
    ran = client.post(f"{API}/tasks/{task_id}/run", headers=headers).json()
    assert ran["task"]["status"] == "APPROVAL_REQUIRED"
    approvals = client.get(f"{API}/approvals", headers=headers).json()
    approval = next(a for a in approvals if a["status"] == "pending")
    return approval


# ------------------------------------------------------------------ org isolation
def test_cross_org_workflow_endpoints_404(client: TestClient) -> None:
    headers_a = _register(client, "org-a@example.com", "Org A")
    headers_b = _register(client, "org-b@example.com", "Org B")

    wf = client.post(
        f"{API}/workflows",
        headers=headers_b,
        json={"objective": "B's secret plan", "workflow_type": "opportunity_discovery"},
    )
    assert wf.status_code == 201, wf.text
    wf_id = wf.json()["id"]

    exclusive = [
        ("GET", f"{API}/workflows/{wf_id}", None),
        ("POST", f"{API}/workflows/{wf_id}/start", None),
        ("POST", f"{API}/workflows/{wf_id}/cancel", {"reason": "none"}),
        ("POST", f"{API}/workflows/{wf_id}/resume", None),
        ("GET", f"{API}/workflows/{wf_id}/tasks", None),
        ("GET", f"{API}/workflows/{wf_id}/runs", None),
        ("GET", f"{API}/workflows/{wf_id}/messages", None),
        ("GET", f"{API}/workflows/{wf_id}/trace", None),
        ("GET", f"{API}/workflows/{wf_id}/result", None),
    ]
    for method, url, payload in exclusive:
        resp = client.request(method, url, headers=headers_a, json=payload)
        assert resp.status_code == 404, f"{method} {url} -> {resp.status_code}"

    listed = client.get(f"{API}/workflows", headers=headers_a).json()
    assert all(w["id"] != wf_id for w in listed), "org A saw org B's workflow"
    mine = client.get(f"{API}/workflows", headers=headers_b).json()
    assert any(w["id"] == wf_id for w in mine)


def test_cross_org_approval_access_404_and_no_leak(client: TestClient) -> None:
    headers_a = _register(client, "org-a2@example.com", "Org A")
    headers_b = _register(client, "org-b2@example.com", "Org B")
    approval_b = _create_pending_approval(client, headers_b)

    listed = client.get(f"{API}/approvals", headers=headers_a).json()
    assert all(a["id"] != approval_b["id"] for a in listed)

    approve = client.post(
        f"{API}/approvals/{approval_b['id']}/approve",
        headers=headers_a,
        json={"decision": "approve", "reason": "steal"},
    )
    assert approve.status_code == 404, approve.text
    reject = client.post(
        f"{API}/approvals/{approval_b['id']}/reject",
        headers=headers_a,
        json={"decision": "reject", "reason": "sabotage"},
    )
    assert reject.status_code == 404, reject.text

    ok = client.post(
        f"{API}/approvals/{approval_b['id']}/approve",
        headers=headers_b,
        json={"decision": "approve", "reason": "mine"},
    )
    assert ok.status_code == 200, ok.text


# ------------------------------------------------------------- role gating (403)
def test_non_level4_user_cannot_approve_level4_403_not_noop(client: TestClient) -> None:
    session = create_session()
    try:
        analyst = User(
            email=f"analyst-{uuid.uuid4()}@example.com", password_hash=hash_password("x"),
            full_name="Analyst", role=Role.ANALYST.value, can_authorize_level4=False,
        )
        session.add(analyst)
        session.flush()
        org = Organization(name="Analyst Co", slug=f"analyst-{uuid.uuid4()}", owner_id=analyst.id)
        session.add(org)
        session.commit()
        analyst_id, org_id = analyst.id, org.id
    finally:
        session.close()

    svc_session = create_session()
    try:
        org = svc_session.get(Organization, org_id)
        assert org is not None
        service = OrchestratorService(svc_session, get_registry(), build_llm_client())
        task = service.create_task(
            org, CHAIRMAN_ACTOR, "Heavy deal", "go", capability="opportunity_discovery",
            approval_level=4,
        )
        asyncio.run(service.run_task(task, org, CHAIRMAN_ACTOR))
        approval = svc_session.scalar(
            select(Approval).where(Approval.entity_id == task.id)
        )
        assert approval is not None and approval.status == "pending"
        approval_id = approval.id
    finally:
        svc_session.close()

    headers = {"Authorization": f"Bearer {create_access_token(analyst_id, Role.ANALYST.value)}"}
    resp = client.post(
        f"{API}/approvals/{approval_id}/approve",
        headers=headers,
        json={"decision": "approve", "reason": "I insist"},
    )
    assert resp.status_code == 403, resp.text

    still = client.get(f"{API}/approvals", headers=headers).json()
    assert any(a["id"] == str(approval_id) and a["status"] == "pending" for a in still), (
        "403 must be a hard stop, not a silent no-op changing state"
    )


# ---------------------------------------------------------- double-decision (409)
def test_repeat_decision_rejected_409(client: TestClient) -> None:
    headers = _register(client, "double@example.com", "Double Co")
    approval = _create_pending_approval(client, headers)
    assert approval["status"] == "pending"

    first = client.post(
        f"{API}/approvals/{approval['id']}/approve",
        headers=headers,
        json={"decision": "approve", "reason": "yes"},
    )
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "approved"

    again = client.post(
        f"{API}/approvals/{approval['id']}/approve",
        headers=headers,
        json={"decision": "approve", "reason": "yes again"},
    )
    assert again.status_code == 409, again.text
    after_approve = client.post(
        f"{API}/approvals/{approval['id']}/reject",
        headers=headers,
        json={"decision": "reject", "reason": "changed my mind"},
    )
    assert after_approve.status_code == 409, after_approve.text

    approval2 = _create_pending_approval(client, headers)
    rejected = client.post(
        f"{API}/approvals/{approval2['id']}/reject",
        headers=headers,
        json={"decision": "reject", "reason": "no"},
    )
    assert rejected.status_code == 200, rejected.text
    reapprove = client.post(
        f"{API}/approvals/{approval2['id']}/approve",
        headers=headers,
        json={"decision": "approve", "reason": "well actually yes"},
    )
    assert reapprove.status_code == 409, reapprove.text


def test_concurrent_double_decision_race_rejected(db_session: Session) -> None:
    """Two sessions both read 'pending', then decide concurrently: exactly one wins.

    Deterministic interleaving: load the approval in two independent sessions
    before either decides, so the second session holds a stale 'pending' row.
    """
    org = Organization(name="Race Co", slug=f"race-{uuid.uuid4()}", owner_id=CHAIRMAN_ACTOR.id)
    db_session.add(org)
    db_session.commit()
    service = OrchestratorService(db_session, get_registry(), build_llm_client())
    service.sync_agent_registry()
    task = service.create_task(
        org, CHAIRMAN_ACTOR, "Buy", "buy", capability="opportunity_discovery",
        approval_level=4,
    )
    asyncio.run(service.run_task(task, org, CHAIRMAN_ACTOR))
    approval = db_session.scalar(select(Approval).where(Approval.entity_id == task.id))
    assert approval is not None and approval.status == "pending"
    approval_id, org_id = approval.id, org.id

    def _decide_in(session: Session, reason: str) -> str:
        svc = OrchestratorService(session, get_registry(), build_llm_client())
        row = session.get(Approval, approval_id)
        org = session.get(Organization, org_id)
        assert row is not None and org is not None
        try:
            svc.approve_approval(org, row, CHAIRMAN_ACTOR, reason)
        except ValueError:
            return "lost"
        return "won"

    s1 = create_session()
    s2 = create_session()
    try:
        s1.get(Approval, approval_id)  # both sessions cache a pending row
        s2.get(Approval, approval_id)
        assert _decide_in(s1, "first") == "won"
        assert _decide_in(s2, "second") == "lost"
    finally:
        s1.close()
        s2.close()

    check = create_session()
    try:
        final = check.get(Approval, approval_id)
        assert final is not None
        assert final.status == "approved"
        assert final.reason == "first"
    finally:
        check.close()


# ----------------------------------------------------------- JWT expiry/tampering
def _protected_routes(client: TestClient) -> list[tuple[str, str]]:
    """Every protected /api/v1 route, from the OpenAPI schema (avoids app-level
    docs/health routes and dynamic router internals)."""
    out: list[tuple[str, str]] = []
    spec = client.app.openapi()
    for path, operations in spec["paths"].items():
        if not path.startswith(API):
            continue
        if path in (f"{API}/auth/register", f"{API}/auth/login"):
            continue
        for verb in ("get", "post", "put", "patch", "delete"):
            if verb in operations:
                out.append((verb.upper(), path))
    return out


def _user_id(client: TestClient, headers: dict) -> str:
    me = client.get(f"{API}/auth/me", headers=headers)
    assert me.status_code == 200, me.text
    return me.json()["user"]["id"]


@pytest.mark.parametrize("bad_token_kind", ["tampered", "expired", "garbage_sub"])
def test_bad_jwt_rejected_on_every_protected_route(
    client: TestClient, bad_token_kind: str
) -> None:
    headers = _register(client, f"jwt-{bad_token_kind}@example.com", "JWT Co")
    user_id = _user_id(client, headers)

    if bad_token_kind == "tampered":
        token = create_access_token(uuid.UUID(user_id), Role.CHAIRMAN.value) + "x"
    elif bad_token_kind == "expired":
        past = datetime.now(UTC) - timedelta(hours=1)
        token = jwt.encode(
            {"sub": user_id, "role": Role.CHAIRMAN.value, "exp": past},
            settings.jwt_secret,
            algorithm=settings.jwt_algorithm,
        )
    else:
        token = jwt.encode(
            {"sub": "garbage-sub", "role": "chairman",
             "exp": datetime.now(UTC) + timedelta(hours=1)},
            settings.jwt_secret,
            algorithm=settings.jwt_algorithm,
        )

    routes = _protected_routes(client)
    assert routes, "no protected routes detected"
    for method, path in routes:
        concrete = _concrete_url(path)
        resp = client.request(method, concrete, headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 401, (
            f"{method} {concrete} -> {resp.status_code} ({resp.text[:120]})"
        )


def _concrete_url(path: str) -> str:
    """Replace path params with a syntactically valid UUID so the route matches
    and its auth dependency (401) runs instead of a routing-level 404."""
    import re

    return re.sub(r"\{[a-z_]+\}", "00000000-0000-0000-0000-000000000000", path)


# ------------------------------------------------------------ list non-leakage
def test_list_endpoints_do_not_leak_other_orgs_run_metrics(client: TestClient) -> None:
    headers_a = _register(client, "leak-a@example.com", "Leak A")
    headers_b = _register(client, "leak-b@example.com", "Leak B")

    wf_b = client.post(
        f"{API}/workflows",
        headers=headers_b,
        json={"objective": "B runs a workflow", "workflow_type": "opportunity_discovery"},
    ).json()
    client.post(f"{API}/workflows/{wf_b['id']}/start", headers=headers_b)
    task_b = client.post(
        f"{API}/tasks",
        headers=headers_b,
        json={"title": "B task", "goal": "b", "capability": "opportunity_discovery"},
    ).json()
    client.post(f"{API}/tasks/{task_b['id']}/run", headers=headers_b)
    tasks_b = client.get(f"{API}/tasks", headers=headers_b).json()
    refs_b = {t["task_ref"] for t in tasks_b}
    ids_b = {t["id"] for t in tasks_b}

    task_a = client.post(
        f"{API}/tasks",
        headers=headers_a,
        json={"title": "A task", "goal": "a", "capability": "opportunity_discovery"},
    ).json()
    client.post(f"{API}/tasks/{task_a['id']}/run", headers=headers_a)

    dash_a = client.get(f"{API}/dashboard", headers=headers_a).json()
    assert dash_a["group_performance"]["runs_tracked"] == 1, (
        "org A's run counter must not include org B's agent runs"
    )
    dash_b = client.get(f"{API}/dashboard", headers=headers_b).json()
    assert dash_b["group_performance"]["runs_tracked"] >= 2

    listed_tasks_a = client.get(f"{API}/tasks", headers=headers_a).json()
    assert all(t["id"] not in ids_b for t in listed_tasks_a)

    activity_a = client.get(f"{API}/activity", headers=headers_a).json()
    assert activity_a, "org A should have its own activity"
    for item in activity_a:
        assert item["entity"] not in refs_b, "activity feed leaked a cross-org entity"

    approvals_a = client.get(f"{API}/approvals", headers=headers_a).json()
    assert all(a["entity_id"] not in ids_b for a in approvals_a)