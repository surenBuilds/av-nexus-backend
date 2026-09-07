"""Venture Builder (Agent 6) workflow tests.

The Venture Builder is a REAL synthesis-time step gated on the synthesis
decision: it runs only when the recommendation is BUILD or VALIDATE_FURTHER and
reuses the existing Task + AgentRun + AgentExecution plumbing.

Covered paths:
- happy path: VALIDATE_FURTHER -> an extra COMPLETED step + run + blueprint task
  output, and the final report carries a VENTURE BLUEPRINT section;
- malformed blueprint: the agent returns a blueprint missing required keys ->
  workflow FAILED with the raw "malformed blueprint" error (no placeholders);
- timeout: the agent step never returns -> executor retries then fails -> the
  workflow FAILED and the run/task record the timeout error;
- gating: a REJECT recommendation skips the Venture Builder step entirely.
"""

from __future__ import annotations

from sqlalchemy import select

from av_nexus.agents.base import AgentResult
from av_nexus.agents.builder import VentureBuilderAgent
from av_nexus.agents.util import confidence_from_sources
from av_nexus.models.agents import AgentRun, Task
from av_nexus.models.decisions import Decision
from av_nexus.models.workflows import Workflow, WorkflowResult, WorkflowStep
from av_nexus.orchestrator import kernel
from tests.test_workflows import _run_full_scenario


def _blueprint_keys(wf: Workflow, db_session) -> dict[str, object]:
    step = db_session.scalar(
        select(WorkflowStep)
        .where(WorkflowStep.workflow_id == wf.id, WorkflowStep.name == "venture_builder")
    )
    assert step is not None, "Venture Builder step must exist"
    task = db_session.get(Task, step.task_id)
    assert task is not None
    assert task.status == "COMPLETED"
    return task.output_json["result"]["blueprint"]  # type: ignore[index]


def _vb_run_and_step(
    wf: Workflow, db_session
) -> tuple[WorkflowStep, AgentRun]:
    step = db_session.scalar(
        select(WorkflowStep)
        .where(WorkflowStep.workflow_id == wf.id, WorkflowStep.name == "venture_builder")
    )
    assert step is not None
    run = db_session.scalar(select(AgentRun).where(AgentRun.task_id == step.task_id))
    assert run is not None
    return step, run


def test_venture_builder_runs_on_validate_further(db_session) -> None:
    wf, org = _run_full_scenario(
        db_session, context={"industry_focus": "smart_construction"}, approve=True
    )
    assert wf.status == "COMPLETED"

    step, run = _vb_run_and_step(wf, db_session)
    assert step.status == "COMPLETED"
    assert run.status == "COMPLETED"
    assert (step.output_summary_json or {}).get("mode") == "deterministic"

    blueprint = _blueprint_keys(wf, db_session)
    for key in (
        "company_name",
        "mission",
        "problem",
        "solution",
        "target_customer",
        "business_model",
        "pricing",
        "mvp_plan",
        "roadmap_12_months",
    ):
        assert key in blueprint, key
    assert isinstance(blueprint["company_name"], str) and blueprint["company_name"]
    assert isinstance(blueprint["roadmap_12_months"], list)
    assert len(blueprint["roadmap_12_months"]) == 12

    result = db_session.scalar(select(WorkflowResult).where(WorkflowResult.workflow_id == wf.id))
    assert result is not None
    assert "VENTURE BLUEPRINT" in result.report_md
    assert blueprint["company_name"] in result.report_md
    assert result.recommendation in ("BUILD", "VALIDATE_FURTHER")

    passed_decision = db_session.scalar(select(Decision).where(Decision.org_id == org.id))
    assert passed_decision is not None and passed_decision.status == "approved"
    assert wf.total_steps == 8


def test_venture_builder_malformed_blueprint_fails(db_session, monkeypatch) -> None:
    async def fake_run(self, ctx, goal):  # type: ignore[no-untyped-def]
        return AgentResult.deterministic(
            result={"blueprint": {"company_name": "Oak Ventures"}},
            confidence=confidence_from_sources(3),
            assumptions=["stub agent for failure injection"],
            sources=["test fixture"],
        )

    monkeypatch.setattr(VentureBuilderAgent, "run", fake_run)
    wf, _ = _run_full_scenario(
        db_session, context={"industry_focus": "smart_construction"}, approve=True
    )
    assert wf.status == "FAILED"
    assert "malformed blueprint" in wf.error
    assert "missing keys" in wf.error

    step, run = _vb_run_and_step(wf, db_session)
    assert step.status == "FAILED"
    # The agent "executed" fine — the malformed-output guard lives in the engine,
    # so the run row itself completed; only the step/task/workflow fail.
    assert run.status == "COMPLETED"
    assert "missing keys" in (step.error or "")
    task = db_session.get(Task, step.task_id)
    assert task is not None and task.status == "FAILED"
    results = list(
        db_session.scalars(select(WorkflowResult).where(WorkflowResult.workflow_id == wf.id))
    )
    assert results == []  # finalization aborted before a result row was written


def test_venture_builder_timeout_fails(db_session, monkeypatch) -> None:
    async def fake_timeout(self, ctx, goal):  # type: ignore[no-untyped-def]
        raise TimeoutError

    monkeypatch.setattr(VentureBuilderAgent, "run", fake_timeout)
    wf, _ = _run_full_scenario(
        db_session, context={"industry_focus": "smart_construction"}, approve=True
    )
    assert wf.status == "FAILED"
    assert "timeout" in wf.error.lower()

    step, run = _vb_run_and_step(wf, db_session)
    assert step.status == "FAILED"
    assert run.status == "FAILED"
    assert "timeout" in (run.error or "").lower()
    task = db_session.get(Task, step.task_id)
    assert task is not None and task.status == "FAILED"
    assert "timeout" in (task.error or "").lower()


def test_venture_builder_skipped_on_reject(db_session, monkeypatch) -> None:
    def decide_reject(validation_res):  # type: ignore[no-untyped-def]
        return {
            "recommendation": "REJECT",
            "rationale": "validation score is too low to proceed",
        }

    monkeypatch.setattr(kernel, "normalize_recommendation", decide_reject)
    # approve=True: disagreements may still raise a chairman gate at finalize, so
    # sign any gate that appears — the assertion below is that VB never runs.
    wf, _ = _run_full_scenario(
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
    assert not any(s.name == "venture_builder" for s in steps)
    assert wf.total_steps == 7

    result = db_session.scalar(select(WorkflowResult).where(WorkflowResult.workflow_id == wf.id))
    assert result is not None
    assert "No blueprint requested" in result.report_md
    assert "VENTURE BLUEPRINT" in result.report_md