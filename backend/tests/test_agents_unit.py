"""Unit tests: security primitives, agent registry, agent contracts."""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from av_nexus.agents import ALL_AGENTS, build_registry, get_registry
from av_nexus.agents.base import AgentContext, AgentResult
from av_nexus.core.security import (
    create_access_token,
    decode_token,
    hash_password,
    verify_password,
)
from av_nexus.models.enums import Role


def test_password_hash_verify_roundtrip() -> None:
    h = hash_password("s3cret-pass")
    assert h != "s3cret-pass"
    assert verify_password("s3cret-pass", h)
    assert not verify_password("wrong", h)


def test_token_roundtrip() -> None:
    uid = uuid.uuid4()
    token = create_access_token(uid, Role.CHAIRMAN.value)
    payload = decode_token(token)
    assert payload is not None
    assert payload["sub"] == str(uid)
    assert payload["role"] == Role.CHAIRMAN.value
    assert decode_token("garbage.token.value") is None


def test_all_agents_registered_count_and_uniqueness() -> None:
    registry = build_registry()
    assert registry.count() == 18
    assert len(registry.agent_ids()) == len(set(registry.agent_ids()))
    ids = set()
    for a in ALL_AGENTS:
        assert a.agent_id
        assert a.capabilities
        ids.add(a.agent_id)
    assert len(ids) == 18


def test_find_by_capability_routes_to_multiple_agents() -> None:
    registry = get_registry()
    matches = registry.find_by_capability("market_validation")
    assert {a.agent_id for a in matches} >= {"validation", "market_research"}
    assert registry.get("risk") is not None
    assert registry.get("nope") is None


def test_agent_result_rejects_out_of_range_confidence() -> None:
    try:
        AgentResult(result={}, confidence=1.5)
    except Exception:
        return
    raise AssertionError("confidence > 1 should not validate")


def test_every_agent_report_contract(db_session: Session) -> None:
    import asyncio

    registry = get_registry()
    org_id = uuid.uuid4()
    for agent in registry.all():
        ctx = AgentContext(org_id=org_id, inputs={"industry_focus": "fintech_sme"})
        result = asyncio.run(agent.run(ctx, "analyze"))
        assert result.mode == "deterministic"
        assert 0.0 <= result.confidence <= 1.0
        assert isinstance(result.assumptions, list)
        assert isinstance(result.risks, list)
        assert isinstance(result.next_recommended_agents, list)
        assert isinstance(result.sources, list)
        assert result.result