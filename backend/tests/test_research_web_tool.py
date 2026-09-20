"""Tests for the research_web tool: gated by default, real results when
enabled, and never fabricates on failure or empty query.
"""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest

from av_nexus.config import settings
from av_nexus.tools.registry import ToolContext, ToolDef, ToolPermissionError, _tool_research_web


@pytest.fixture(autouse=True)
def _restore_research_flag():
    original = settings.research_tool_enabled
    yield
    settings.research_tool_enabled = original


def _ctx() -> ToolContext:
    return ToolContext(session=None, org_id=uuid.uuid4())  # type: ignore[arg-type]


def _tool() -> ToolDef:
    return ToolDef("research_web", "desc", "external", {"query": "string"})


def test_research_web_raises_when_disabled() -> None:
    settings.research_tool_enabled = False
    with pytest.raises(ToolPermissionError):
        _tool_research_web(_ctx(), _tool(), {"query": "Armenian AI startups"})


def test_research_web_returns_real_results_when_enabled() -> None:
    settings.research_tool_enabled = True
    fake_hits = [
        {"title": "Voxline AI", "href": "https://voxline.am", "body": "AI automation in Armenia"},
    ]
    with patch("ddgs.DDGS") as mock_ddgs_cls:
        mock_ddgs_cls.return_value.__enter__.return_value.text.return_value = fake_hits
        result = _tool_research_web(_ctx(), _tool(), {"query": "Voxline AI Armenia"})

    assert result["results"] == [
        {"title": "Voxline AI", "url": "https://voxline.am", "snippet": "AI automation in Armenia"}
    ]
    assert "1 real result" in result["note"]


def test_research_web_reports_failure_instead_of_fabricating() -> None:
    settings.research_tool_enabled = True
    with patch("ddgs.DDGS", side_effect=RuntimeError("network unreachable")):
        result = _tool_research_web(_ctx(), _tool(), {"query": "anything"})

    assert result["results"] == []
    assert "network unreachable" in result["note"]


def test_research_web_empty_query_returns_empty_without_calling_search() -> None:
    settings.research_tool_enabled = True
    with patch("ddgs.DDGS") as mock_ddgs_cls:
        result = _tool_research_web(_ctx(), _tool(), {"query": "  "})
    mock_ddgs_cls.assert_not_called()
    assert result["results"] == []
