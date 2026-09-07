"""Secure tool registry for the Phase 2A execution engine.

Every tool declares: name, description, input schema, required permission, timeout.
The executor NEVER lets the frontend choose permissions or tools; an agent may only
invoke a tool whose permission is in the agent's own permission list. Denials are
recorded (non-retryable) — they are never silently re-attempted.

Security posture for this phase:
- No arbitrary code execution (calculator uses a strict AST whitelist).
- No shell access.
- No unfettered internet: the future web research tool is permanently gated behind
  `research_tool_enabled` and an explicit permission that no agent holds yet.
- All DB-backed tools are scoped to the caller's org.
"""

from __future__ import annotations

import ast
import operator
import statistics
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from av_nexus.config import settings
from av_nexus.models.catalog import FinancialMetric, Kpi, Product
from av_nexus.models.identity import Company
from av_nexus.models.knowledge import KnowledgeEntity, KnowledgeRelationship
from av_nexus.models.memory import MemoryItem


class ToolPermissionError(RuntimeError):
    """Agent invoked a tool its permission list does not include."""


@dataclass
class ToolDef:
    name: str
    description: str
    permission: str
    input_schema: dict[str, str]
    timeout_seconds: int = 5

    def manifest(self) -> dict[str, object]:
        return {
            "name": self.name,
            "description": self.description,
            "permission": self.permission,
            "input_schema": self.input_schema,
            "timeout_seconds": self.timeout_seconds,
        }


@dataclass
class ToolContext:
    session: Session
    org_id: uuid.UUID
    company_id: uuid.UUID | None = None


@dataclass
class ToolRegistry:
    session: Session
    org_id: uuid.UUID
    agent_permissions: list[str]
    company_id: uuid.UUID | None = None
    tools: list[ToolDef] = field(default_factory=list)
    calls: list[dict[str, Any]] = field(default_factory=list)

    # -- public API ----------------------------------------------------------
    def available(self) -> list[dict[str, object]]:
        return [t.manifest() for t in self.tools if t.permission in self.agent_permissions]

    def context(self) -> ToolContext:
        return ToolContext(session=self.session, org_id=self.org_id, company_id=self.company_id)

    def execute(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        tool = next((t for t in self.tools if t.name == name), None)
        if tool is None:
            outcome = {"ok": False, "name": name, "error": "unknown tool", "result": None}
        elif tool.permission not in self.agent_permissions:
            outcome = {
                "ok": False,
                "name": name,
                "error": f"permission denied: requires '{tool.permission}'",
                "code": "permission_denied",
                "result": None,
            }
        else:
            try:
                outcome = {
                    "ok": True,
                    "name": name,
                    "error": None,
                    "result": _CALLS[name](self.context(), tool, args),
                }
            except ToolPermissionError:
                outcome = {
                    "ok": False,
                    "name": name,
                    "error": "permission denied",
                    "code": "permission_denied",
                    "result": None,
                }
            except Exception as exc:  # tool bug must not melt the pipeline
                outcome = {
                    "ok": False,
                    "name": name,
                    "error": f"{type(exc).__name__}",
                    "result": None,
                }
        self.calls.append(
            {
                "name": name,
                "args": args,
                "ok": bool(outcome.get("ok")),
                "error": outcome.get("error"),
                "result": outcome.get("result"),
            }
        )
        return outcome


# ---------------------------------------------------------------------------
# Tool implementations (pure + DB-scoped)
# ---------------------------------------------------------------------------
_BINARY_OPS: dict[type, Callable[[float, float], float]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY_OPS: dict[type, Callable[[float], float]] = {ast.UAdd: operator.pos, ast.USub: operator.neg}


def _safe_eval(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _safe_eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, int | float):
        return float(node.value)
    if isinstance(node, ast.BinOp) and type(node.op) in _BINARY_OPS:
        left = _safe_eval(node.left)
        right = _safe_eval(node.right)
        return float(_BINARY_OPS[type(node.op)](left, right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPS:
        return float(_UNARY_OPS[type(node.op)](_safe_eval(node.operand)))
    raise ValueError("unsupported expression")


def _tool_calculator(ctx: ToolContext, tool: ToolDef, args: dict[str, Any]) -> dict[str, Any]:
    expr = str(args.get("expression", "")).strip()
    if not expr:
        raise ValueError("expression is required")
    try:
        parsed = ast.parse(expr, mode="eval")
        value = _safe_eval(parsed.body)
    except (ValueError, SyntaxError, ZeroDivisionError):
        raise ValueError("unsupported or invalid expression") from None
    return {
        "expression": expr,
        "result": value,
        "note": "Safe AST arithmetic only; no code execution.",
    }


def _tool_structured_analysis(
    ctx: ToolContext, tool: ToolDef, args: dict[str, Any]
) -> dict[str, Any]:
    values = args.get("values")
    if not isinstance(values, list) or not all(
        isinstance(v, int | float) and not isinstance(v, bool) for v in values
    ):
        raise ValueError("values must be a list of numbers")
    nums = [float(v) for v in values]
    n = len(nums)
    mean = sum(nums) / n
    return {
        "count": n,
        "sum": round(sum(nums), 4),
        "mean": round(mean, 4),
        "median": round(statistics.median(nums), 4),
        "min": round(min(nums), 4),
        "max": round(max(nums), 4),
        "stddev": round(statistics.pstdev(nums), 4),
    }


def _tool_memory_search(ctx: ToolContext, tool: ToolDef, args: dict[str, Any]) -> dict[str, Any]:
    query = str(args.get("query", "")).lower().strip()
    layer = args.get("layer")
    stmt = select(MemoryItem).where(MemoryItem.org_id == ctx.org_id)
    if layer:
        stmt = stmt.where(MemoryItem.layer == str(layer))
    items = list(ctx.session.scalars(stmt))[:50]
    hit = layer is not None and not query

    def matches(item: MemoryItem) -> bool:
        if not query:
            return True
        hay = f"{item.key} {item.note} {item.value_json}".lower()
        return query in hay

    results = [
        {
            "layer": i.layer,
            "key": i.key,
            "note": i.note,
            "value": i.value_json,
            "source_agent": i.agent_id,
        }
        for i in items
        if matches(i)
    ][:10]
    return {"results": results, "hit": hit or bool(results)}


def _tool_internal_knowledge_search(
    ctx: ToolContext, tool: ToolDef, args: dict[str, Any]
) -> dict[str, Any]:
    query = str(args.get("query", "")).lower().strip()
    if not query:
        raise ValueError("query is required")
    ents = list(
        ctx.session.scalars(select(KnowledgeEntity).where(KnowledgeEntity.org_id == ctx.org_id))
    )
    rels = list(
        ctx.session.scalars(
            select(KnowledgeRelationship).where(KnowledgeRelationship.org_id == ctx.org_id)
        )
    )
    entity_matches = [
        {
            "entity_type": e.entity_type,
            "name": e.name,
            "properties": e.properties_json or {},
        }
        for e in ents
        if query in e.name.lower()
    ]
    rel_matches = [
        {
            "from": rp.from_name,
            "to": rp.to_name,
            "type": rp.relationship_type,
        }
        for rp in _relationship_rows(ents, rels)
        if query in rp.from_name.lower() or query in rp.to_name.lower()
    ]
    return {
        "entities": entity_matches[:10],
        "relationships": rel_matches[:10],
        "total_entities": len(ents),
    }


def _tool_company_context(ctx: ToolContext, tool: ToolDef, args: dict[str, Any]) -> dict[str, Any]:
    raw = args.get("company_id")
    company_id = uuid.UUID(str(raw)) if raw else ctx.company_id
    if company_id is None:
        return {"company": None, "reason": "no company context for this run"}
    company = ctx.session.get(Company, company_id)
    if company is None or company.org_id != ctx.org_id:
        return {"company": None, "reason": "unknown or foreign company"}
    products = list(ctx.session.scalars(select(Product).where(Product.company_id == company.id)))
    kpis = list(ctx.session.scalars(select(Kpi).where(Kpi.company_id == company.id)))
    fins = list(
        ctx.session.scalars(select(FinancialMetric).where(FinancialMetric.company_id == company.id))
    )
    return {
        "company": {
            "id": str(company.id),
            "name": company.name,
            "industry": company.industry,
            "stage": company.stage,
            "health_score": company.business_health_score,
            "mission": company.mission,
        },
        "products": [{"name": p.name, "status": p.status} for p in products],
        "kpis": [
            {"name": k.name, "value": k.value, "target": k.target, "unit": k.unit} for k in kpis
        ],
        "financials": [
            {"metric": f.metric, "value": f.value, "period": f.period, "currency": f.currency}
            for f in fins
        ],
    }


def _tool_research_web(ctx: ToolContext, tool: ToolDef, args: dict[str, Any]) -> dict[str, Any]:
    """Permanently gated this phase: no unfettered internet. Never fakes results."""
    if not settings.research_tool_enabled:
        raise ToolPermissionError("external research is disabled in this phase")
    return {
        "results": [],
        "note": "research_web is not configured; no external data was fetched.",
    }


_CALLS = {
    "calculator": _tool_calculator,
    "structured_analysis": _tool_structured_analysis,
    "memory_search": _tool_memory_search,
    "internal_knowledge_search": _tool_internal_knowledge_search,
    "company_context": _tool_company_context,
    "research_web": _tool_research_web,
}


def default_tools() -> list[ToolDef]:
    return [
        ToolDef(
            "calculator",
            "Safe arithmetic on an expression (add/sub/mul/div/pow/mod)",
            "research",
            {"expression": "string"},
        ),
        ToolDef(
            "structured_analysis",
            "Statistics over a list of numbers (count/sum/mean/median/min/max/stddev)",
            "research",
            {"values": "list[number]"},
        ),
        ToolDef(
            "internal_knowledge_search",
            "Search the organization knowledge graph by entity/relationship name",
            "research",
            {"query": "string"},
        ),
        ToolDef(
            "memory_search",
            "Search persisted agent/company/global memory within the org",
            "research",
            {"query": "string", "layer": "string|optional"},
        ),
        ToolDef(
            "company_context",
            "Company profile (health, products, KPIs, financials) scoped to the org",
            "research",
            {"company_id": "uuid|optional"},
        ),
        ToolDef(
            "research_web",
            "External web research (gated OFF this phase)",
            "external",
            {"query": "string"},
        ),
    ]


def build_tool_registry(
    session: Session,
    org_id: uuid.UUID,
    agent_permissions: list[str],
    company_id: uuid.UUID | None = None,
) -> ToolRegistry:
    return ToolRegistry(
        session=session,
        org_id=org_id,
        agent_permissions=agent_permissions,
        company_id=company_id,
        tools=default_tools(),
    )


@dataclass
class _KnowledgeRow:
    from_name: str
    to_name: str
    relationship_type: str


def _relationship_rows(
    ents: list[KnowledgeEntity], rels: list[KnowledgeRelationship]
) -> list[_KnowledgeRow]:
    by_id = {e.id: e for e in ents}
    rows: list[_KnowledgeRow] = []
    for r in rels:
        from_ent = by_id.get(r.from_entity_id)
        to_ent = by_id.get(r.to_entity_id)
        rows.append(
            _KnowledgeRow(
                from_name=from_ent.name if from_ent is not None else "",
                to_name=to_ent.name if to_ent is not None else "",
                relationship_type=r.relationship_type,
            )
        )
    return rows
