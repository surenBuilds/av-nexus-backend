"""Tests for the GitHub tools (github_read_file, github_propose_pr) and
CodingAgent end-to-end: repo allowlist enforcement, honest "not generated"
behavior with no real LLM provider, and a full proposal flow with a fake
real-provider LLM where only httpx (the actual network boundary) is mocked.
"""

from __future__ import annotations

import asyncio
import base64
import uuid
from unittest.mock import MagicMock, patch

import pytest

from av_nexus.agents.base import AgentContext
from av_nexus.agents.coding import CodingAgent
from av_nexus.config import settings
from av_nexus.llm.base import LLMResult
from av_nexus.tools.registry import ToolContext, ToolDef, ToolPermissionError, build_tool_registry


class FakeLLM:
    """Mirrors tests/test_validated_llm.py's FakeLLM: a real-provider stand-in
    whose provider name is not one of the offline/mock markers, so
    BaseAgent._structured_llm treats its output as real."""

    def __init__(self, make: object, *, provider: str = "fake_provider") -> None:
        self._make = make
        self._provider = provider

    def complete(self, system: str, user: str) -> LLMResult:
        return LLMResult(content=self._make(user), provider=self._provider)


@pytest.fixture(autouse=True)
def _restore_github_settings():
    original = (settings.github_token, settings.github_allowed_repos)
    yield
    settings.github_token, settings.github_allowed_repos = original


def _tool_ctx() -> ToolContext:
    return ToolContext(session=None, org_id=uuid.uuid4())  # type: ignore[arg-type]


def _tool_def(name: str) -> ToolDef:
    return ToolDef(name, "desc", "code_write", {})


# --------------------------------------------------------------- tool tests #


def test_github_read_file_rejects_repo_outside_allowlist() -> None:
    settings.github_token = "tok"
    settings.github_allowed_repos = "surenBuilds/Krtlab-appp"
    from av_nexus.tools.registry import _tool_github_read_file

    with pytest.raises(ToolPermissionError):
        _tool_github_read_file(
            _tool_ctx(), _tool_def("github_read_file"), {"repo": "someone/else", "path": "x.py"}
        )


def test_github_read_file_returns_real_decoded_content() -> None:
    settings.github_token = "tok"
    settings.github_allowed_repos = "surenBuilds/Krtlab-appp"
    from av_nexus.tools.registry import _tool_github_read_file

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "encoding": "base64",
        "content": base64.b64encode(b"print('hello')").decode(),
        "sha": "abc123",
    }
    with patch("httpx.get", return_value=mock_response):
        result = _tool_github_read_file(
            _tool_ctx(),
            _tool_def("github_read_file"),
            {"repo": "surenBuilds/Krtlab-appp", "path": "main.py"},
        )
    assert result == {"ok": True, "path": "main.py", "content": "print('hello')", "sha": "abc123"}


def test_github_read_file_reports_missing_file_honestly() -> None:
    settings.github_token = "tok"
    settings.github_allowed_repos = "surenBuilds/Krtlab-appp"
    from av_nexus.tools.registry import _tool_github_read_file

    mock_response = MagicMock()
    mock_response.status_code = 404
    with patch("httpx.get", return_value=mock_response):
        result = _tool_github_read_file(
            _tool_ctx(),
            _tool_def("github_read_file"),
            {"repo": "surenBuilds/Krtlab-appp", "path": "nope.py"},
        )
    assert result["ok"] is False
    assert "not found" in result["error"]


def test_github_propose_pr_never_writes_to_base_branch() -> None:
    """The tool has exactly one write path (contents PUT to `branch`) and one
    branch-creation path (git/refs from base's sha) — this asserts no call
    is ever made that writes content to `base` itself."""
    settings.github_token = "tok"
    settings.github_allowed_repos = "surenBuilds/Krtlab-appp"
    from av_nexus.tools.registry import _tool_github_propose_pr

    ref_resp = MagicMock(status_code=200)
    ref_resp.json.return_value = {"object": {"sha": "base-sha"}}
    branch_resp = MagicMock(status_code=201)
    existing_resp = MagicMock(status_code=404)
    put_resp = MagicMock(status_code=201)
    pr_resp = MagicMock(status_code=201)
    pr_resp.json.return_value = {"html_url": "https://github.com/x/y/pull/1", "number": 1}

    with (
        patch("httpx.get", side_effect=[ref_resp, existing_resp]),
        patch("httpx.post", side_effect=[branch_resp, pr_resp]) as mock_post,
        patch("httpx.put", return_value=put_resp) as mock_put,
    ):
        result = _tool_github_propose_pr(
            _tool_ctx(),
            _tool_def("github_propose_pr"),
            {
                "repo": "surenBuilds/Krtlab-appp",
                "base": "main",
                "branch": "av-nexus/test-123",
                "title": "Test change",
                "body": "body",
                "files": [{"path": "a.py", "content": "x = 1", "message": "add a.py"}],
            },
        )

    assert result == {"ok": True, "pr_url": "https://github.com/x/y/pull/1", "pr_number": 1}
    # Branch creation used base's sha but targeted refs/heads/<branch>, not base
    create_branch_call = mock_post.call_args_list[0]
    assert create_branch_call.kwargs["json"]["ref"] == "refs/heads/av-nexus/test-123"
    # The content write went to the new branch, never to "main"
    put_call = mock_put.call_args_list[0]
    assert put_call.kwargs["json"]["branch"] == "av-nexus/test-123"
    assert "main" not in put_call.args[0] or put_call.kwargs["json"]["branch"] != "main"


def test_github_propose_pr_rejects_repo_outside_allowlist() -> None:
    settings.github_token = "tok"
    settings.github_allowed_repos = "surenBuilds/Krtlab-appp"
    from av_nexus.tools.registry import _tool_github_propose_pr

    with pytest.raises(ToolPermissionError):
        _tool_github_propose_pr(
            _tool_ctx(),
            _tool_def("github_propose_pr"),
            {
                "repo": "someone/else",
                "branch": "x",
                "files": [{"path": "a.py", "content": "1"}],
            },
        )


# -------------------------------------------------------------- agent tests #


def test_coding_agent_without_repo_is_honest_not_generated() -> None:
    ctx = AgentContext(org_id=uuid.uuid4(), inputs={})
    result = asyncio.run(CodingAgent().run(ctx, "do something"))
    assert result.mode == "deterministic"
    assert result.result["status"] == "not_generated"
    assert result.result["reason"] == "repo_required"


def test_coding_agent_without_llm_provider_proposes_nothing() -> None:
    ctx = AgentContext(
        org_id=uuid.uuid4(), inputs={"repo": "surenBuilds/Krtlab-appp", "task": "fix bug"}
    )
    result = asyncio.run(CodingAgent().run(ctx, "fix bug"))
    assert result.mode == "deterministic"
    assert result.result["reason"] == "no_llm_provider"
    assert result.result["status"] == "not_generated"


def test_coding_agent_with_no_files_to_change_reports_no_change_not_a_failure(db_session) -> None:
    """Regression test: when the LLM correctly determines the real files
    already satisfy the task (e.g. a version bump that's already met), that
    is a legitimate outcome — not a failed PR attempt. No GitHub write calls
    should happen at all in this case."""
    settings.github_token = "tok"
    settings.github_allowed_repos = "surenBuilds/Krtlab-appp"

    proposal = {
        "branch_suffix": "react-bump",
        "title": "n/a",
        "body": "n/a",
        "summary": "react is already ^19.0.0, above the requested ^18.2.0 — no change needed",
        "files": [],
        "risks": [],
    }
    import json as _json

    llm = FakeLLM(lambda _user: _json.dumps(proposal))

    org_id = uuid.uuid4()
    tools = build_tool_registry(db_session, org_id, CodingAgent().permissions)
    ctx = AgentContext(
        org_id=org_id,
        llm=llm,
        inputs={
            "repo": "surenBuilds/Krtlab-appp",
            "task": "bump react to 18.2.0 if below",
            "context_files": ["package.json"],
        },
        tools=tools,
    )

    read_resp = MagicMock(status_code=200)
    read_resp.json.return_value = {
        "encoding": "base64",
        "content": base64.b64encode(b'"react": "^19.0.0"').decode(),
        "sha": "sha",
    }

    with (
        patch("httpx.get", return_value=read_resp) as mock_get,
        patch("httpx.post") as mock_post,
        patch("httpx.put") as mock_put,
    ):
        result = asyncio.run(CodingAgent().run(ctx, "bump react"))

    assert result.mode == "llm"
    assert result.result["status"] == "no_change_needed"
    assert result.result["pr_opened"] is False
    # Only the one context-file read happened — no branch/PR/commit calls.
    assert mock_get.call_count == 1
    mock_post.assert_not_called()
    mock_put.assert_not_called()


def test_coding_agent_full_flow_opens_real_pr_from_real_llm_proposal(db_session) -> None:
    settings.github_token = "tok"
    settings.github_allowed_repos = "surenBuilds/Krtlab-appp"

    proposal = {
        "branch_suffix": "fix-typo",
        "title": "Fix typo in README",
        "body": "Fixes a typo",
        "summary": "Corrected 'recieve' to 'receive'",
        "files": [{"path": "README.md", "content": "receive", "message": "fix typo"}],
        "risks": ["Small change, low risk"],
    }
    import json as _json

    llm = FakeLLM(lambda _user: f"```json\n{_json.dumps(proposal)}\n```")

    org_id = uuid.uuid4()
    tools = build_tool_registry(db_session, org_id, CodingAgent().permissions)
    ctx = AgentContext(
        org_id=org_id,
        llm=llm,
        inputs={"repo": "surenBuilds/Krtlab-appp", "task": "fix the typo"},
        tools=tools,
    )

    ref_resp = MagicMock(status_code=200)
    ref_resp.json.return_value = {"object": {"sha": "base-sha"}}
    branch_resp = MagicMock(status_code=201)
    existing_resp = MagicMock(status_code=404)
    put_resp = MagicMock(status_code=201)
    pr_resp = MagicMock(status_code=201)
    pr_resp.json.return_value = {
        "html_url": "https://github.com/surenBuilds/Krtlab-appp/pull/7",
        "number": 7,
    }

    with (
        patch("httpx.get", side_effect=[ref_resp, existing_resp]),
        patch("httpx.post", side_effect=[branch_resp, pr_resp]),
        patch("httpx.put", return_value=put_resp),
    ):
        result = asyncio.run(CodingAgent().run(ctx, "fix the typo"))

    assert result.mode == "llm"
    assert result.result["pr_opened"] is True
    assert result.result["pr_url"] == "https://github.com/surenBuilds/Krtlab-appp/pull/7"
    assert result.result["files_changed"] == ["README.md"]
    assert result.result["branch"].startswith("av-nexus/fix-typo-")
