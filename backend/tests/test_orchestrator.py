"""Unit tests: kernel decisions, pipelines, orchestrator service."""

from __future__ import annotations

import asyncio
import uuid

from sqlalchemy.orm import Session

from av_nexus.agents import get_registry
from av_nexus.agents.base import AgentResult
from av_nexus.llm.factory import build_llm_client
from av_nexus.models.decisions import Approval, Decision
from av_nexus.models.enums import Role
from av_nexus.models.identity import Organization, User
from av_nexus.orchestrator import kernel
from av_nexus.orchestrator.pipelines import plan_pipeline
from av_nexus.orchestrator.service import OrchestratorService

OWNER = User(
    id=uuid.UUID(int=1), email="a@b.c", password_hash="x", full_name="Owner",
    role=Role.CHAIRMAN.value, can_authorize_level4=True,
)


ORGS_COUNTER = 0


def test_disagreement_detection() -> None:
    stages = {
        "validation": AgentResult(
            result={"verdict": "STOP", "validation_score": 20.0}, confidence=0.6
        ),
        "risk": AgentResult(result={"overall_level": "CRITICAL"}, confidence=0.7),
        "strategy": AgentResult(
            result={"priority_ranking": [{"title": "X", "score": 90}, {"title": "Y", "score": 80}]},
            confidence=0.8,
        ),
    }
    conflicts = kernel.analyze_disagreements(stages)
    types = {c["type"] for c in conflicts}
    assert "validation_vs_build" in types
    assert "risk_vs_build" in types
    assert "strategy_vs_validation" in types


def test_no_false_disagreement_when_aligned() -> None:
    stages = {
        "validation": AgentResult(
            result={"verdict": "GO", "validation_score": 80.0}, confidence=0.9
        ),
        "risk": AgentResult(result={"overall_level": "LOW"}, confidence=0.7),
        "strategy": AgentResult(result={"priority_ranking": []}, confidence=0.5),
    }
    assert kernel.analyze_disagreements(stages) == []


def test_approval_level_mapping() -> None:
    assert kernel.approval_level_for("research") == 1
    assert kernel.approval_level_for("plan") == 2
    assert kernel.approval_level_for("money") == 4
    assert kernel.approval_level_for("external_action") == 3
    # high risk escalates even research gates
    assert kernel.approval_level_for("plan", "HIGH") == 3


def test_plan_pipeline_definition() -> None:
    stages = plan_pipeline("business_creation")
    names = [s["name"] for s in stages]
    assert names == [
        "opportunity_scan", "market_research", "competitive_intelligence",
        "validation", "finance", "risk", "strategy", "critic",
    ]


ORGS_COUNTER = 0


def _service(db_session: Session) -> OrchestratorService:
    global ORGS_COUNTER
    ORGS_COUNTER += 1
    org = Organization(
        id=uuid.uuid4(), name=f"O{ORGS_COUNTER}", slug=f"o{ORGS_COUNTER}",
        owner_id=OWNER.id,
    )
    db_session.add(org)
    db_session.commit()
    service = OrchestratorService(db_session, get_registry(), build_llm_client())
    service.sync_agent_registry()
    return service


def test_run_task_completes_and_records(db_session: Session) -> None:
    service = _service(db_session)
    org = db_session.query(Organization).first()
    assert org is not None
    task = service.create_task(
        org, OWNER, "Find opportunities", "Find new business opportunities",
        capability="opportunity_discovery",
    )
    asyncio.run(service.run_task(task, org, OWNER))
    db_session.refresh(task)
    assert task.status == "COMPLETED"
    assert task.confidence > 0
    assert task.output_json is not None
    assert task.output_json["mode"] == "deterministic"
    from av_nexus.models.agents import AgentRun

    runs = db_session.query(AgentRun).filter(AgentRun.task_id == task.id).all()
    assert len(runs) == 1
    assert runs[0].status == "COMPLETED"


def test_approval_gate_blocks_level3(db_session: Session) -> None:
    service = _service(db_session)
    org = db_session.query(Organization).first()
    assert org is not None
    task = service.create_task(
        org, OWNER, "Send money", "wire transfer", capability="opportunity_discovery",
        approval_level=4,
    )
    state = asyncio.run(service.run_task(task, org, OWNER))
    assert state["task_state"] == "approval_required"
    db_session.refresh(task)
    assert task.status == "APPROVAL_REQUIRED"
    approval = db_session.query(Approval).filter(Approval.entity_id == task.id).first()
    assert approval is not None
    assert approval.level == 4


def test_dependency_cycle_detection(db_session: Session) -> None:
    service = _service(db_session)
    org = db_session.query(Organization).first()
    assert org is not None
    a = service.create_task(org, OWNER, "A", "a")
    b = service.create_task(org, OWNER, "B", "b")
    service.add_dependency(b, a.id)
    try:
        service.add_dependency(a, b.id)
    except ValueError:
        return
    raise AssertionError("cycle should have been rejected")


def test_business_creation_pipeline(db_session: Session) -> None:
    service = _service(db_session)
    org = db_session.query(Organization).first()
    assert org is not None
    outcome = asyncio.run(
        service.orchestrate(
            org, OWNER, "I want to create a new business in fintech", "business_creation"
        )
    )
    assert set(outcome["stages"]) >= {
        "opportunity_scan", "market_research", "competitive_intelligence",
        "validation", "finance", "risk", "strategy", "critic",
    }
    assert outcome["stages"]["validation"].result["verdict"] in ("GO", "CHALLENGE", "STOP")
    assert outcome["recommendation"]["recommendation"] in ("BUILD", "VALIDATE_FURTHER", "REJECT")
    assert outcome["confidence"] > 0
    decision = db_session.get(Decision, uuid.UUID(str(outcome["decision_id"])))
    assert decision is not None
    assert decision.agents_involved_json  # evidence recorded
    # BUILD or VALIDATE_FURTHER implies a pending approval for the chairman
    if outcome["recommendation"]["recommendation"] in ("BUILD", "VALIDATE_FURTHER"):
        assert outcome["approval_id"] is not None
        approval = db_session.get(Approval, uuid.UUID(str(outcome["approval_id"])))
        assert approval is not None
        assert approval.status == "pending"


def test_level4_approval_requires_chairman_authority(db_session: Session) -> None:
    service = _service(db_session)
    org = db_session.query(Organization).first()
    assert org is not None
    task = service.create_task(
        org, OWNER, "Buy company", "acquisition", capability="opportunity_discovery",
        approval_level=4,
    )
    asyncio.run(service.run_task(task, org, OWNER))
    approval = db_session.query(Approval).filter(Approval.entity_id == task.id).first()
    assert approval is not None

    analyst = User(
        id=uuid.uuid4(), email="analyst@x.io", password_hash="h", full_name="A",
        role=Role.ANALYST.value, can_authorize_level4=False,
    )
    try:
        service.approve_approval(org, approval, analyst, "yolo")
    except PermissionError:
        pass
    else:
        raise AssertionError("analyst must not approve level-4")


def test_level4_approval_succeeds_for_chairman(db_session: Session) -> None:
    service = _service(db_session)
    org = db_session.query(Organization).first()
    assert org is not None
    task = service.create_task(
        org, OWNER, "Buy company", "acquisition", capability="opportunity_discovery",
        approval_level=4,
    )
    asyncio.run(service.run_task(task, org, OWNER))
    approval = db_session.query(Approval).filter(Approval.entity_id == task.id).first()
    assert approval is not None
    service.approve_approval(org, approval, OWNER, "chairman signed")
    db_session.refresh(approval)
    assert approval.status == "approved"


def test_level3_requires_chairman_or_admin(db_session: Session) -> None:
    service = _service(db_session)
    org = db_session.query(Organization).first()
    assert org is not None
    task = service.create_task(
        org, OWNER, "Post press release", "external communication",
        capability="opportunity_discovery", approval_level=3,
    )
    asyncio.run(service.run_task(task, org, OWNER))
    approval = db_session.query(Approval).filter(Approval.entity_id == task.id).first()
    assert approval is not None
    analyst = User(
        id=uuid.uuid4(), email="analyst@x.io", password_hash="h", full_name="A",
        role=Role.ANALYST.value, can_authorize_level4=False,
    )
    try:
        service.approve_approval(org, approval, analyst, "nope")
    except PermissionError:
        return
    raise AssertionError("analyst must not approve level-3")