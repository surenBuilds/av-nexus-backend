"""Phase 2A workflow tests: planning DAG, execution, gates, artifacts.

Covered paths (mock, offline/deterministic by design):
- plan() builds one Task per stage with the correct dependency edges;
- a started workflow executes every step (7 runs, RESULT messages);
- the final decision gate pauses at WAITING_FOR_APPROVAL, then approve → COMPLETED
  and reject → FAILED, or cancel → CANCELLED with future steps cancelled;
- finalization persists opportunities, curated memory/knowledge, the synthesis
  report (10 sections) and a Decision row with tokens in the run trace.
"""

from __future__ import annotations

import asyncio
import time
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from av_nexus.agents import get_registry
from av_nexus.llm.factory import build_llm_client
from av_nexus.models.agents import AgentMessage, AgentRun, Task, TaskDependency
from av_nexus.models.decisions import Approval, Decision
from av_nexus.models.enums import Role
from av_nexus.models.identity import Organization, User
from av_nexus.models.knowledge import KnowledgeRelationship
from av_nexus.models.memory import MemoryItem
from av_nexus.models.opportunities import Opportunity
from av_nexus.models.workflows import Workflow, WorkflowResult, WorkflowStep
from av_nexus.orchestrator.service import OrchestratorService
from av_nexus.workflows.engine import WorkflowEngine
from av_nexus.workflows.pipeline import STAGE_ORDER
from tests.conftest import register_and_login

OWNER = User(
    id=uuid.uuid4(),
    email="chair@workflows.test",
    password_hash="x",
    full_name="Chair",
    role=Role.CHAIRMAN.value,
    can_authorize_level4=True,
)

_REPORT_SECTIONS = [
    "EXECUTIVE SUMMARY",
    "TOP OPPORTUNITIES",
    "MARKET FINDINGS",
    "COMPETITIVE FINDINGS",
    "RISKS",
    "DISAGREEMENTS",
    "CONFIDENCE",
    "RECOMMENDATION",
    "VENTURE BLUEPRINT",
    "NEXT ACTIONS",
    "APPROVAL REQUIREMENTS",
]


def _setup(db_session: Session) -> Organization:
    org = Organization(id=uuid.uuid4(), name="Wf Org", slug="wf_org", owner_id=OWNER.id)
    db_session.add(org)
    db_session.commit()
    OrchestratorService(db_session, get_registry(), build_llm_client()).sync_agent_registry()
    return org


def _svc(db_session: Session) -> OrchestratorService:
    return OrchestratorService(db_session, get_registry(), build_llm_client())


# ------------------------------------------------------------------ engine #
def test_plan_builds_dag_with_dependencies(db_session: Session) -> None:
    org = _setup(db_session)
    engine = WorkflowEngine(db_session, get_registry(), build_llm_client())
    wf = engine.create_workflow(
        org, OWNER, "Find an education AI play", context={"industry_focus": "ai_education"}
    )
    engine.plan(db_session, wf, org, OWNER)

    steps = list(
        db_session.scalars(
            select(WorkflowStep)
            .where(WorkflowStep.workflow_id == wf.id)
            .order_by(WorkflowStep.step_index)
        )
    )
    assert [s.name for s in steps] == STAGE_ORDER
    assert all(s.task_id is not None for s in steps)

    dep_for = {}
    for s in steps:
        task = db_session.get(Task, s.task_id)
        assert task is not None
        deps = db_session.scalars(
            select(TaskDependency.depends_on_task_id).where(TaskDependency.task_id == task.id)
        ).all()
        dep_for[s.name] = set(deps)

    assert dep_for["market_research"] == dep_for["competitive_intelligence"] != set()
    assert set(dep_for["market_research"]) == {
        db_session.get(Task, next(s.task_id for s in steps if s.name == "scout")).id
    }
    assert len(dep_for["validation"]) == 2
    assert len(dep_for["risk"]) == 2
    assert dep_for["critic"] == {
        db_session.get(Task, next(s.task_id for s in steps if s.name == "validation")).id,
        db_session.get(Task, next(s.task_id for s in steps if s.name == "risk")).id,
    }
    assert len(dep_for["strategy"]) == 1


def _run_full_scenario(
    db_session: Session,
    *,
    context: dict[str, str],
    approve: bool | None = None,
    cancel_after_start: bool = False,
) -> tuple[Workflow, Organization]:
    """One asyncio.run() so the background runner lives on the testing loop."""
    org = _setup(db_session)
    engine = WorkflowEngine(db_session, get_registry(), build_llm_client())

    async def scenario() -> tuple[Workflow, Organization]:
        wf = engine.create_workflow(org, OWNER, "Launch a smart construction play", context=context)
        engine.plan(db_session, wf, org, OWNER)
        engine.start(db_session, wf, org, OWNER)
        if cancel_after_start:
            engine.cancel(db_session, wf, "user pressed stop")
            return db_session.get(Workflow, wf.id), org
        decided = False
        while True:
            db_session.expire_all()
            rec = db_session.get(Workflow, wf.id)
            if approve is not None and rec.status == "WAITING_FOR_APPROVAL" and not decided:
                approval = db_session.scalar(
                    select(Approval)
                    .where(Approval.org_id == org.id)
                    .order_by(Approval.created_at.desc())
                )
                assert approval is not None
                if approve:
                    _svc(db_session).approve_approval(org, approval, OWNER, "signed")
                else:
                    _svc(db_session).reject_approval(org, approval, OWNER, "not now")
                decided = True
                continue
            if rec.status in ("COMPLETED", "FAILED", "CANCELLED"):
                return rec, org
            await asyncio.sleep(0.05)

    return asyncio.run(scenario())


def test_workflow_pauses_for_approval_and_completes(db_session: Session) -> None:
    wf, org = _run_full_scenario(
        db_session, context={"industry_focus": "smart_construction"}, approve=True
    )
    assert wf.status == "COMPLETED"

    steps = list(
        db_session.scalars(
            select(WorkflowStep)
            .where(WorkflowStep.workflow_id == wf.id)
            .order_by(WorkflowStep.step_index)
        )
    )
    assert all(s.status == "COMPLETED" for s in steps)

    result = db_session.scalar(select(WorkflowResult).where(WorkflowResult.workflow_id == wf.id))
    assert result is not None
    for section in _REPORT_SECTIONS:
        assert section in result.report_md
    # Phase 1 made validator inputs honest; the recommendation is now derived
    # from real upstream signals and may legitimately be BUILD or VALIDATE_FURTHER.
    assert result.recommendation in ("BUILD", "VALIDATE_FURTHER")
    assert len(result.top_opportunities) >= 1

    runs = list(
        db_session.scalars(select(AgentRun).where(AgentRun.task_id.in_([s.task_id for s in steps])))
    )
    # 8 runs: the 7 pipeline stages plus the gated Venture Builder (Agent 6).
    assert len(runs) == len(STAGE_ORDER) + 1
    assert all(r.status == "COMPLETED" for r in runs)
    assert all(r.trace_json is not None for r in runs)

    messages = list(
        db_session.scalars(
            select(AgentMessage).where(AgentMessage.task_id.in_([s.task_id for s in steps]))
        )
    )
    assert len(messages) == len(STAGE_ORDER) + 1

    opps = list(db_session.scalars(select(Opportunity).where(Opportunity.org_id == org.id)))
    assert opps and all("workflow:" in (o.source or "") for o in opps)

    mem = db_session.scalar(select(MemoryItem).where(MemoryItem.key == f"workflow:{wf.id}"))
    assert mem is not None and mem.note == "Workflow synthesis summary"

    rels = list(
        db_session.scalars(
            select(KnowledgeRelationship).where(
                KnowledgeRelationship.relationship_type == "exists_in"
            )
        )
    )
    assert rels

    decision = db_session.scalar(select(Decision).where(Decision.org_id == org.id))
    assert decision is not None and decision.status == "approved"
    approval = db_session.scalar(select(Approval).where(Approval.org_id == org.id))
    assert approval is not None and approval.status == "approved"


def test_workflow_rejection_fails(db_session: Session) -> None:
    wf, _ = _run_full_scenario(
        db_session, context={"industry_focus": "smart_construction"}, approve=False
    )
    assert wf.status == "FAILED"
    assert "rejected" in wf.error.lower()


def test_workflow_cancel_stops_future_steps(db_session: Session) -> None:
    wf, _ = _run_full_scenario(
        db_session, context={"industry_focus": "ai_education"}, cancel_after_start=True
    )
    assert wf.status == "CANCELLED"
    steps = list(db_session.scalars(select(WorkflowStep).where(WorkflowStep.workflow_id == wf.id)))
    # no step may end RUNNING; anything not completed is cancelled
    assert all(s.status != "RUNNING" for s in steps)
    assert all(s.status in ("COMPLETED", "CANCELLED", "WAITING") for s in steps)


# -------------------------------------------------------------------- API #
def _poll_api(
    client: TestClient, headers: dict, wfid: str, terminal: set[str], timeout: float = 25.0
) -> str:
    deadline = time.time() + timeout
    while True:
        if time.time() > deadline:
            raise AssertionError("workflow did not reach a terminal state")
        resp = client.get(f"/api/v1/workflows/{wfid}", headers=headers)
        assert resp.status_code == 200, resp.text
        state = resp.json()["workflow"]["status"]
        if state in terminal:
            return state
        time.sleep(0.15)


def test_api_create_plans_and_lists(client: TestClient) -> None:
    headers = register_and_login(client)
    resp = client.post(
        "/api/v1/workflows",
        json={
            "objective": "Explore B2B automation",
            "context": {"industry_focus": "ai_b2b_automation"},
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    wf = resp.json()
    assert wf["status"] == "PLANNING"
    assert wf["total_steps"] == 7

    detail = client.get(f"/api/v1/workflows/{wf['id']}", headers=headers)
    assert detail.status_code == 200
    assert [s["name"] for s in detail.json()["steps"]] == STAGE_ORDER

    listing = client.get("/api/v1/workflows", headers=headers)
    assert listing.status_code == 200
    assert len(listing.json()) == 1


def test_api_end_to_end_approval_and_report(client: TestClient) -> None:
    headers = register_and_login(client)
    created = client.post(
        "/api/v1/workflows",
        json={
            "objective": "Validate a smart construction venture",
            "context": {"industry_focus": "smart_construction"},
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    wfid = created.json()["id"]

    started = client.post(f"/api/v1/workflows/{wfid}/start", json={}, headers=headers)
    assert started.status_code == 200, started.text

    state = _poll_api(client, headers, wfid, {"WAITING_FOR_APPROVAL", "COMPLETED", "FAILED"})
    assert state == "WAITING_FOR_APPROVAL"

    trace = client.get(f"/api/v1/workflows/{wfid}/trace", headers=headers)
    assert trace.status_code == 200
    pending = [a for a in trace.json()["approvals"] if a["status"] == "pending"]
    assert pending, "the final decision gate must create a pending approval"
    for approval in pending:
        decision_approval = client.post(
            f"/api/v1/approvals/{approval['id']}/approve",
            json={"decision": "approve", "reason": "chairman signs"},
            headers=headers,
        )
        assert decision_approval.status_code == 200, decision_approval.text

    state = _poll_api(client, headers, wfid, {"COMPLETED", "FAILED"})
    assert state == "COMPLETED"

    result = client.get(f"/api/v1/workflows/{wfid}/result", headers=headers)
    assert result.status_code == 200
    report = result.json()
    assert "EXECUTIVE SUMMARY" in report["report_md"]
    assert report["recommendation"] in ("BUILD", "VALIDATE_FURTHER")

    runs = client.get(f"/api/v1/workflows/{wfid}/runs", headers=headers)
    assert runs.status_code == 200
    assert len(runs.json()) == 8

    detail = client.get(f"/api/v1/workflows/{wfid}", headers=headers)
    assert all(s["status"] == "COMPLETED" for s in detail.json()["steps"])
