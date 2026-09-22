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
    """Real web search via DuckDuckGo when enabled; never fakes results.

    Gated by settings.research_tool_enabled (default OFF) so this stays an
    explicit opt-in per deployment. When it fails or returns nothing, that
    is reported honestly in `note` rather than backfilled with invented
    results.
    """
    if not settings.research_tool_enabled:
        raise ToolPermissionError("external research is disabled in this phase")

    query = str(args.get("query", "")).strip()
    if not query:
        return {"results": [], "note": "empty query — nothing searched"}

    max_results = int(args.get("max_results", 5) or 5)
    try:
        from ddgs import DDGS

        with DDGS() as ddgs:
            hits = list(ddgs.text(query, max_results=max_results))
    except Exception as exc:  # noqa: BLE001 - any search failure is reported, not swallowed into fake data
        return {"results": [], "note": f"web search failed: {exc}"}

    results = [
        {
            "title": h.get("title", ""),
            "url": h.get("href") or h.get("link", ""),
            "snippet": h.get("body", ""),
        }
        for h in hits
    ]
    note = f"{len(results)} real result(s) from DuckDuckGo" if results else "no results found"
    return {"results": results, "note": note}


def _github_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.github_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _github_repo_allowed(repo: str) -> bool:
    allowed = {r.strip() for r in settings.github_allowed_repos.split(",") if r.strip()}
    return repo in allowed


def _tool_github_read_file(
    ctx: ToolContext, tool: ToolDef, args: dict[str, Any]
) -> dict[str, Any]:
    """Read one real file's content from GitHub. Never invents file contents —
    a missing file or read failure is reported, not filled in with a guess."""
    import base64

    import httpx

    repo = str(args.get("repo", ""))
    path = str(args.get("path", ""))
    ref = str(args.get("ref", "") or "")
    if not settings.github_token:
        return {"ok": False, "error": "AVNEXUS_GITHUB_TOKEN is not configured"}
    if not _github_repo_allowed(repo):
        raise ToolPermissionError(f"repo '{repo}' is not in AVNEXUS_GITHUB_ALLOWED_REPOS")
    if not path:
        return {"ok": False, "error": "path is required"}

    url = f"https://api.github.com/repos/{repo}/contents/{path}"
    params = {"ref": ref} if ref else {}
    try:
        resp = httpx.get(url, headers=_github_headers(), params=params, timeout=15.0)
    except httpx.HTTPError as exc:
        return {"ok": False, "error": f"network error: {exc}"}
    if resp.status_code == 404:
        return {"ok": False, "error": f"file not found: {path}"}
    if resp.status_code != 200:
        return {"ok": False, "error": f"GitHub returned {resp.status_code}: {resp.text[:300]}"}
    data = resp.json()
    if data.get("encoding") != "base64":
        return {"ok": False, "error": f"unexpected encoding: {data.get('encoding')}"}
    content = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
    return {"ok": True, "path": path, "content": content, "sha": data.get("sha")}


def _tool_github_propose_pr(
    ctx: ToolContext, tool: ToolDef, args: dict[str, Any]
) -> dict[str, Any]:
    """Create a branch, commit the given files, and open a PR against base.

    Never touches the base branch directly — this tool has no code path that
    writes to `base`; it only ever creates a new branch and a pull request
    for a human to review and merge.
    """
    import base64

    import httpx

    repo = str(args.get("repo", ""))
    base = str(args.get("base", "main"))
    branch = str(args.get("branch", ""))
    title = str(args.get("title", ""))
    body = str(args.get("body", ""))
    files = args.get("files") or []

    if not settings.github_token:
        return {"ok": False, "error": "AVNEXUS_GITHUB_TOKEN is not configured"}
    if not _github_repo_allowed(repo):
        raise ToolPermissionError(f"repo '{repo}' is not in AVNEXUS_GITHUB_ALLOWED_REPOS")
    if not branch or branch == base:
        return {"ok": False, "error": "a branch name distinct from base is required"}
    if not isinstance(files, list) or not files:
        return {"ok": False, "error": "files must be a non-empty list of {path, content}"}

    headers = _github_headers()
    api = f"https://api.github.com/repos/{repo}"

    try:
        base_ref = httpx.get(f"{api}/git/ref/heads/{base}", headers=headers, timeout=15.0)
        if base_ref.status_code != 200:
            return {
                "ok": False,
                "error": f"could not read base branch '{base}': {base_ref.text[:300]}",
            }
        base_sha = base_ref.json()["object"]["sha"]

        create_branch = httpx.post(
            f"{api}/git/refs",
            headers=headers,
            json={"ref": f"refs/heads/{branch}", "sha": base_sha},
            timeout=15.0,
        )
        if create_branch.status_code not in (201, 422):  # 422: branch already exists — reuse it
            return {"ok": False, "error": f"could not create branch: {create_branch.text[:300]}"}

        for f in files:
            if not isinstance(f, dict) or "path" not in f or "content" not in f:
                return {"ok": False, "error": f"malformed file entry: {f!r}"}
            path = f["path"]
            existing = httpx.get(
                f"{api}/contents/{path}", headers=headers, params={"ref": branch}, timeout=15.0
            )
            put_body: dict[str, Any] = {
                "message": f.get("message", f"Update {path}"),
                "content": base64.b64encode(f["content"].encode("utf-8")).decode("ascii"),
                "branch": branch,
            }
            if existing.status_code == 200:
                put_body["sha"] = existing.json()["sha"]
            put_resp = httpx.put(
                f"{api}/contents/{path}", headers=headers, json=put_body, timeout=15.0
            )
            if put_resp.status_code not in (200, 201):
                return {
                    "ok": False,
                    "error": f"could not write {path}: {put_resp.text[:300]}",
                }

        pr_resp = httpx.post(
            f"{api}/pulls",
            headers=headers,
            json={
                "title": title or f"Automated changes on {branch}",
                "head": branch,
                "base": base,
                "body": body,
            },
            timeout=15.0,
        )
        if pr_resp.status_code not in (201, 422):  # 422: PR may already exist for this branch
            return {"ok": False, "error": f"could not open PR: {pr_resp.text[:300]}"}
        if pr_resp.status_code == 201:
            pr_data = pr_resp.json()
            return {"ok": True, "pr_url": pr_data["html_url"], "pr_number": pr_data["number"]}
        return {
            "ok": True,
            "pr_url": None,
            "note": "branch pushed; a PR for it may already be open",
        }
    except httpx.HTTPError as exc:
        return {"ok": False, "error": f"network error: {exc}"}


_CALLS = {
    "calculator": _tool_calculator,
    "structured_analysis": _tool_structured_analysis,
    "memory_search": _tool_memory_search,
    "internal_knowledge_search": _tool_internal_knowledge_search,
    "company_context": _tool_company_context,
    "research_web": _tool_research_web,
    "github_read_file": _tool_github_read_file,
    "github_propose_pr": _tool_github_propose_pr,
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
            "Real DuckDuckGo web search (opt-in via AVNEXUS_RESEARCH_TOOL_ENABLED)",
            "external",
            {"query": "string", "max_results": "number|optional"},
        ),
        ToolDef(
            "github_read_file",
            "Read one real file's content from an allowlisted GitHub repo",
            "code_write",
            {"repo": "string", "path": "string", "ref": "string|optional"},
        ),
        ToolDef(
            "github_propose_pr",
            "Create a branch, commit files, and open a PR — never writes to base directly",
            "code_write",
            {
                "repo": "string",
                "base": "string",
                "branch": "string",
                "title": "string",
                "body": "string",
                "files": "list[{path, content}]",
            },
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
