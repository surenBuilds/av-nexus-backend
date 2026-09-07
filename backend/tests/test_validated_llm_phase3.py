"""Phase 3 tests: Critic `issues` and Validator `failure_reasons` /
`questions_to_answer` are REAL schema-validated LLM reasoning.

- Validator: evidence (demand/willingness/competition/team-fit/capital/provenance)
  reaches the model; two scenarios produce genuinely different reasoning; offline
  mode publishes honest "not_generated / no_llm_provider" markers; malformed
  provider output raises non-retryable AgentExecutionError.
- Critic: the merged upstream stage results reach the model; two scenarios produce
  genuinely different issues; offline mode is honest; malformed output FAILs.
- Workflow-level: a real provider that emits garbage only for Validator or only
  for Critic FAILS that step and the workflow with the raw error.
"""

from __future__ import annotations

import asyncio
import json
import uuid

import pytest
from sqlalchemy.orm import Session

from av_nexus.agents.base import AgentContext, AgentExecutionError
from av_nexus.agents.builder import ValidationAgent
from av_nexus.agents.guardian import CriticAgent
from av_nexus.llm.base import LLMResult
from av_nexus.llm.mock import MockLLM
from tests.test_workflows import _run_full_scenario


class FakeLLM:
    def __init__(self, make: object, *, provider: str = "fake_provider") -> None:
        self._make = make
        self._provider = provider

    def complete(self, system: str, user: str) -> LLMResult:
        return LLMResult(content=self._make(user), provider=self._provider)


def _validation_ctx(validation_inputs: dict[str, object], llm: object) -> AgentContext:
    return AgentContext(org_id=uuid.uuid4(), llm=llm, inputs=validation_inputs)


# ---------------------------------------------------------------- why choices #


def _echo_validator(user: str) -> str:
    data = json.loads(user)
    return json.dumps(
        {
            "summary": (
                f"demand={data['demand_score']} willingness={data['willingness_to_pay']} "
                f"competition={data['competition']}"
            ),
            "failure_reasons": [
                f"weak willingness observed ({data['willingness_to_pay']:.0f})"
                if data["willingness_to_pay"] < 50
                else "no fatal flaw surfaced from supplied evidence"
            ],
            "questions_to_answer": [
                f"can demand at {data['demand_score']:.0f}/100 support pricing?",
                "why now?",
            ],
        }
    )


def _echo_critic(user: str) -> str:
    data = json.loads(user)
    stages = data["reviewed_stage_results"]
    val_verdict = ((stages.get("validation") or {}).get("result") or {}).get("verdict", "?")
    return json.dumps(
        {
            "verdict": "CHALLENGED",
            "issues": [
                f"validation verdict {val_verdict} was not tested adversarially",
                "no rebuttal evidence captured",
            ],
        }
    )


_FULL_VALIDATION_INPUTS = {
    "idea": "Smart Construction",
    "demand_score": 68.0,
    "willingness_to_pay": 74.8,
    "competition": 30.0,
    "team_fit": 52.0,
    "market_size_score": 68.0,
    "capital": 80.0,
    "data_provenance": {
        "demand_score": "market_research (real)",
        "competition": "scout (derived)",
    },
}

_WEAK_VALIDATION_INPUTS = {
    "idea": "Ai Education",
    "demand_score": 40.0,
    "willingness_to_pay": 45.0,
    "competition": 80.0,
    "team_fit": 25.0,
    "market_size_score": 40.0,
    "capital": 95.0,
    "data_provenance": {"demand_score": "market_research (real)"},
}


def _critic_ctx(stage_results: dict[str, object], llm: object) -> AgentContext:
    return AgentContext(
        org_id=uuid.uuid4(),
        llm=llm,
        inputs={
            "under_review": {
                "result": stage_results,
                "confidence": 0.7,
                "sources": ["pipeline stages"],
                "assumptions": [],
            }
        },
    )


def _critic_payload(validation_verdict: str) -> dict[str, object]:
    return {
        "validation": {"result": {"verdict": validation_verdict, "validation_score": 70.0}},
        "risk": {"result": {"overall_level": "LOW"}},
        "market_research": {"result": {"demand_score": 68.0}},
    }


# ------------------------------------------------------------ Validator tests #


def test_validator_offline_marks_not_generated_and_stays_deterministic() -> None:
    result = asyncio.run(
        ValidationAgent().run(
            _validation_ctx(_FULL_VALIDATION_INPUTS, MockLLM()),
            "stress-test the idea",
        )
    )
    assert result.mode == "deterministic"
    assert result.result["failure_reasons"] == []
    assert result.result["questions_to_answer"] == []
    assert result.result["reasoning"] == {"status": "not_generated", "reason": "no_llm_provider"}
    assert result.result["verdict"] in ("GO", "CHALLENGE", "STOP")


def test_validator_llm_receives_evidence_and_varies() -> None:
    good = asyncio.run(
        ValidationAgent().run(
            _validation_ctx(_FULL_VALIDATION_INPUTS, FakeLLM(_echo_validator)),
            "stress-test the idea",
        )
    )
    weak = asyncio.run(
        ValidationAgent().run(
            _validation_ctx(_WEAK_VALIDATION_INPUTS, FakeLLM(_echo_validator)),
            "stress-test the idea",
        )
    )
    assert good.mode == "llm" and weak.mode == "llm"
    assert good.result["failure_reasons"] != weak.result["failure_reasons"]
    assert good.result["questions_to_answer"] != weak.result["questions_to_answer"]
    assert "no fatal flaw" in good.result["failure_reasons"][0]
    assert "weak willingness" in weak.result["failure_reasons"][0]


def test_validator_rejects_malformed_provider_output() -> None:
    ctx = _validation_ctx(_FULL_VALIDATION_INPUTS, FakeLLM(lambda _u: "{ not json"))
    with pytest.raises(AgentExecutionError) as exc:
        asyncio.run(ValidationAgent().run(ctx, "stress-test the idea"))
    assert exc.value.retryable is False


# --------------------------------------------------------------- Critic tests #


def test_critic_offline_marks_not_generated_and_stays_deterministic() -> None:
    result = asyncio.run(
        CriticAgent().run(_critic_ctx(_critic_payload("GO"), MockLLM()), "review the assessment")
    )
    assert result.mode == "deterministic"
    assert result.result["verdict"] == "NOT_REVIEWED"
    assert result.result["issues"] == []
    assert result.result["reasoning"] == {"status": "not_generated", "reason": "no_llm_provider"}


def test_critic_llm_receives_upstream_evidence_and_varies() -> None:
    go = asyncio.run(
        CriticAgent().run(_critic_ctx(_critic_payload("GO"), FakeLLM(_echo_critic)), "review")
    )
    stop = asyncio.run(
        CriticAgent().run(_critic_ctx(_critic_payload("STOP"), FakeLLM(_echo_critic)), "review")
    )
    assert go.mode == "llm" and stop.mode == "llm"
    assert go.result["issues"] != stop.result["issues"]
    assert "verdict GO" in go.result["issues"][0]
    assert "verdict STOP" in stop.result["issues"][0]


def test_critic_rejects_malformed_provider_output() -> None:
    ctx = _critic_ctx(_critic_payload("GO"), FakeLLM(lambda _u: "not json"))
    with pytest.raises(AgentExecutionError) as exc:
        asyncio.run(CriticAgent().run(ctx, "review"))
    assert exc.value.retryable is False


# -------------------------------------------------------------- workflow path #


class SelectiveLLM:
    """Returns schema-valid JSON for every stage EXCEPT the one whose prompt
    carries a unique marker; that stage gets garbage so the step FAILs."""

    def __init__(self, fail_if_contains: str, provider: str = "fake_provider") -> None:
        self.fail_if = fail_if_contains
        self.provider = provider

    def complete(self, system: str, user: str) -> LLMResult:
        if self.fail_if in user:
            return LLMResult(content="not json at all", provider=self.provider)
        if "demand_score" in user and "data_provenance" in user:
            payload = {
                "summary": "ok",
                "failure_reasons": ["none"],
                "questions_to_answer": ["why now?"],
            }
        elif "priority_ranking" in user and "validator_verdict" in user:
            payload = {
                "summary": "port", "capital_allocation_guidance": "stage",
                "portfolio_watchouts": ["x"], "key_assumptions": ["y"],
            }
        else:  # critic merged payload (contains upstream stage results)
            payload = {"verdict": "PASS WITH CAVEATS", "issues": ["minor"]}
        return LLMResult(content=json.dumps(payload), provider=self.provider)


def _fail_workflow(db_session: Session, monkeypatch, marker: str, expected_step: str) -> None:
    from av_nexus.workflows import engine as engine_module

    monkeypatch.setattr(engine_module, "build_llm_client", lambda: SelectiveLLM(marker))
    wf, _ = _run_full_scenario(
        db_session, context={"industry_focus": "smart_construction"}, approve=False
    )
    assert wf.status == "FAILED"

    from sqlalchemy import select

    from av_nexus.models.workflows import WorkflowStep

    failed = db_session.scalars(
        select(WorkflowStep).where(
            WorkflowStep.workflow_id == wf.id, WorkflowStep.status == "FAILED"
        )
    ).all()
    assert failed, "expected a FAILED step"
    assert failed[0].name == expected_step
    err = failed[0].error or ""
    assert "schema validation" in err or "parseable JSON" in err


def test_workflow_fails_on_invalid_validator_output(db_session: Session, monkeypatch) -> None:
    _fail_workflow(db_session, monkeypatch, "data_provenance", "validation")


def test_workflow_fails_on_invalid_critic_output(db_session: Session, monkeypatch) -> None:
    _fail_workflow(db_session, monkeypatch, "reviewed_stage_results", "critic")