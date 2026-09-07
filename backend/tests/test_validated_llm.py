"""Phase 2 validated-LLM infrastructure tests.

- `BaseAgent._structured_llm` returns None for offline/mock providers, parses
  fenced JSON for real providers, validates against a pydantic schema, and turns
  parse/schema failures into non-retryable AgentExecutionError (→ FAILED step).
- `AgentResult.llm` validates the whole published result and sets mode="llm";
  schema violations raise AgentExecutionError.
- StrategyAgent: real provider path yields a schema-validated `strategy_commentary`
  built from real evidence (validator verdict / risk level / critic verdict /
  priority ranking) and mode="llm"; the offline path yields an honest
  "not_generated / no_llm_provider" marker with mode="deterministic".
- Workflow-level: a real provider that emits invalid output FAILS the first
  LLM-consuming step and the workflow with the raw error (no template fallback).
"""

from __future__ import annotations

import asyncio
import json
import uuid

import pytest
from sqlalchemy.orm import Session

from av_nexus import workflows  # noqa: F401  (engine import side effects)
from av_nexus.agents.base import AgentContext, AgentExecutionError, AgentResult
from av_nexus.agents.group_strategy import StrategyAgent, StrategyCommentarySchema
from av_nexus.llm.base import LLMResult
from av_nexus.llm.mock import MockLLM
from tests.test_workflows import _run_full_scenario


class FakeLLM:
    def __init__(self, make: object, *, provider: str = "fake_provider") -> None:
        self._make = make
        self._provider = provider

    def complete(self, system: str, user: str) -> LLMResult:
        return LLMResult(content=self._make(user), provider=self._provider)


def _ctx(**overrides: object) -> AgentContext:
    base = {"org_id": uuid.uuid4(), "execution_mode": "mock"}
    base.update(overrides)
    return AgentContext(
        org_id=base["org_id"],
        llm=base.get("llm"),
        inputs=base.get("inputs") or {},  # type: ignore[arg-type]
    )


# ------------------------------------------------------------ infrastructure #


def test_structured_llm_none_without_provider() -> None:
    assert StrategyAgent()._structured_llm(_ctx(), "s", "u", StrategyCommentarySchema) is None


def test_structured_llm_none_for_mock_provider() -> None:
    ctx = AgentContext(org_id=uuid.uuid4(), llm=MockLLM())
    assert StrategyAgent()._structured_llm(ctx, "s", "u", StrategyCommentarySchema) is None


def test_structured_llm_parses_fenced_json_and_validates() -> None:
    payload = json.dumps(
        {
            "summary": "lead with highest score",
            "capital_allocation_guidance": "stage funding",
            "portfolio_watchouts": ["concentration"],
            "key_assumptions": ["scores only"],
        }
    )
    fake = FakeLLM(lambda _user: f"```json\n{payload}\n```")
    ctx = AgentContext(org_id=uuid.uuid4(), llm=fake)
    out = StrategyAgent()._structured_llm(ctx, "s", "u", StrategyCommentarySchema)
    assert out is not None
    assert out["summary"] == "lead with highest score"


def test_structured_llm_rejects_invalid_json() -> None:
    fake = FakeLLM(lambda _user: "definitely not json")
    ctx = AgentContext(org_id=uuid.uuid4(), llm=fake)
    with pytest.raises(AgentExecutionError) as exc:
        StrategyAgent()._structured_llm(ctx, "s", "u", StrategyCommentarySchema)
    assert exc.value.retryable is False
    assert "parseable JSON" in str(exc.value)


def test_structured_llm_rejects_schema_violation() -> None:
    fake = FakeLLM(lambda _user: json.dumps({"capital_allocation_guidance": 42}))
    ctx = AgentContext(org_id=uuid.uuid4(), llm=fake)
    with pytest.raises(AgentExecutionError) as exc:
        StrategyAgent()._structured_llm(ctx, "s", "u", StrategyCommentarySchema)
    assert exc.value.retryable is False
    assert "schema validation" in str(exc.value)


def test_agent_result_llm_sets_mode_llm() -> None:
    good = {
        "summary": "ok",
        "capital_allocation_guidance": "g",
        "portfolio_watchouts": [],
        "key_assumptions": [],
    }
    res = AgentResult.llm(
        result=good, schema=StrategyCommentarySchema, confidence=0.5, assumptions=[], sources=[]
    )
    assert res.mode == "llm"
    assert isinstance(res.result["summary"], str)


def test_agent_result_llm_rejects_schema_violation() -> None:
    bad = {"summary": "ok"}  # missing required fields
    with pytest.raises(AgentExecutionError) as exc:
        AgentResult.llm(
            result=bad, schema=StrategyCommentarySchema, confidence=0.5, assumptions=[], sources=[]
        )
    assert exc.value.retryable is False


# ---------------------------------------------------------------- Strategy #


def _evidence_inputs(verdict: str, risk: str, title: str, score: float) -> dict[str, object]:
    return {
        "opportunities": [{"title": title, "category": title, "opportunity_score": score}],
        "validation": {"verdict": verdict, "validation_score": 70.0, "failure_reasons": []},
        "risk": {"overall_level": risk, "risk_matrix": []},
        "critic": {"verdict": "PASS WITH CAVEATS"},
    }


def _echo_commentary(user: str) -> str:
    data = json.loads(user)
    lead = data["priority_ranking"][0]["title"]
    return json.dumps(
        {
            "summary": (
                f"verdict={data['validator_verdict']} "
                f"risk={data['risk_level']} lead={lead}"
            ),
            "capital_allocation_guidance": "stage funding",
            "portfolio_watchouts": ["x"],
            "key_assumptions": ["against evidence only"],
        }
    )


def test_strategy_offline_marks_not_generated_and_stays_deterministic() -> None:
    ctx = AgentContext(
        org_id=uuid.uuid4(),
        llm=MockLLM(),
        inputs=_evidence_inputs("GO", "HIGH", "Smart Construction", 70.0),
    )
    result = asyncio.run(StrategyAgent().run(ctx, "strategic fit"))
    assert result.mode == "deterministic"
    marker = result.result.get("strategy_commentary")
    assert isinstance(marker, dict)
    assert marker["status"] == "not_generated"
    assert marker["reason"] == "no_llm_provider"
    assert result.result["priority_ranking"][0]["title"] == "Smart Construction"


def test_strategy_llm_receives_real_evidence_and_varies() -> None:
    a = AgentContext(
        org_id=uuid.uuid4(),
        llm=FakeLLM(_echo_commentary),
        inputs=_evidence_inputs("GO", "HIGH", "Smart Construction", 70.0),
    )
    b = AgentContext(
        org_id=uuid.uuid4(),
        llm=FakeLLM(_echo_commentary),
        inputs=_evidence_inputs("STOP", "LOW", "Fintech Pay", 55.0),
    )
    ra = asyncio.run(StrategyAgent().run(a, "strategic fit"))
    rb = asyncio.run(StrategyAgent().run(b, "strategic fit"))
    assert ra.mode == "llm" and rb.mode == "llm"
    ca, cb = ra.result["strategy_commentary"], rb.result["strategy_commentary"]
    assert ca["summary"] != cb["summary"]
    assert "verdict=GO" in ca["summary"] and "risk=HIGH" in ca["summary"]
    assert "verdict=STOP" in cb["summary"] and "lead=Fintech Pay" in cb["summary"]


# ---------------------------------------------------------------- workflow #


def test_workflow_fails_when_real_provider_emits_invalid_output(
    db_session: Session, monkeypatch
) -> None:
    from sqlalchemy import select

    from av_nexus.models.workflows import WorkflowStep
    from av_nexus.workflows import engine as engine_module

    monkeypatch.setattr(
        engine_module,
        "build_llm_client",
        lambda: FakeLLM(lambda _user: "completely broken response"),
    )
    wf, _ = _run_full_scenario(
        db_session, context={"industry_focus": "smart_construction"}, approve=False
    )
    assert wf.status == "FAILED"
    # the earliest LLM-consuming stage to run (validation < critic < strategy) fails
    failed_step = db_session.scalars(
        select(WorkflowStep)
        .where(WorkflowStep.workflow_id == wf.id, WorkflowStep.status == "FAILED")
    ).first()
    assert failed_step is not None
    assert failed_step.name == "validation"
    assert failed_step.error is not None
    assert "schema validation" in failed_step.error or "parseable JSON" in failed_step.error
    # no fabricated fallback was written into the failed step's output
    assert failed_step.output_summary_json in (None, {})