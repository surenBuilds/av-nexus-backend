"""Coding Agent: implements real code changes on an allowlisted repo as a
branch + pull request for human review — never writes to the base branch.

Follows the same honesty contract as every other agent here: code content
only ever comes from a real, schema-validated LLM response (see
BaseAgent._structured_llm). With no real provider configured, this agent
publishes an honest "not generated" result and proposes nothing — it never
fabricates a diff or opens a PR with placeholder content.
"""

from __future__ import annotations

import json
import uuid

from pydantic import BaseModel, ConfigDict

from av_nexus.agents.base import AgentContext, AgentResult, BaseAgent


class FileChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    content: str
    message: str = "Update via AV Nexus Coding Agent"


class CodeChangeSchema(BaseModel):
    """Real model provider output a code-change proposal must validate against."""

    model_config = ConfigDict(extra="forbid")

    branch_suffix: str
    title: str
    body: str
    summary: str
    files: list[FileChange]
    risks: list[str]


class SuggestedAddition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    area: str
    suggestion: str
    rationale: str


class CodebaseReviewSchema(BaseModel):
    """Real model provider output a codebase review must validate against."""

    model_config = ConfigDict(extra="forbid")

    summary: str
    strengths: list[str]
    gaps: list[str]
    suggested_additions: list[SuggestedAddition]


# Review mode reads real file content to stay grounded, but must fit in one
# LLM call — these caps bound how much of a real, possibly large repo gets
# pulled in, prioritizing likely-source files over assets/lockfiles.
_REVIEW_MAX_FILES = 15
_REVIEW_MAX_CHARS_PER_FILE = 4000
_REVIEW_SOURCE_EXTENSIONS = (
    ".ts", ".tsx", ".js", ".jsx", ".py", ".json", ".md", ".yml", ".yaml", ".css",
)  # fmt: skip


class CodingAgent(BaseAgent):
    agent_id = "coding"
    name = "Coding Agent"
    role = "Implements code changes as reviewable pull requests"
    description = (
        "Reads real files from an allowlisted GitHub repo, drafts a code change with a "
        "real model provider, and opens it as a branch + PR. Never pushes to the base "
        "branch — every change is a PR a human reviews and merges. Can also produce a "
        "read-only codebase review (mode='review') with no PR attempted."
    )
    capabilities = ["code_changes"]
    tools = ["github_read_file", "github_propose_pr", "github_list_files"]
    permissions = ["code_write", "research"]

    async def run(self, ctx: AgentContext, goal: str) -> AgentResult:
        repo = str(ctx.inputs.get("repo", "")).strip()
        if not repo:
            return AgentResult.deterministic(
                result={"status": "not_generated", "reason": "repo_required"},
                confidence=0.1,
                assumptions=[],
                sources=[],
                risks=["No repo was supplied — nothing was read or proposed"],
                next_recommended_agents=[],
            )

        if str(ctx.inputs.get("mode", "")).strip() == "review":
            return await self._run_review(ctx, repo)
        return await self._run_change(ctx, repo, goal)

    async def _run_review(self, ctx: AgentContext, repo: str) -> AgentResult:
        list_outcome = ctx.run_tool("github_list_files", {"repo": repo})
        list_result = list_outcome.get("result") or {}
        if not (list_outcome.get("ok") and list_result.get("ok")):
            error = list_result.get("error") or list_outcome.get("error") or "unknown error"
            return AgentResult.deterministic(
                result={"status": "not_generated", "reason": "list_files_failed", "error": error},
                confidence=0.1,
                assumptions=[],
                sources=[],
                risks=[f"Could not list files in {repo}: {error}"],
                next_recommended_agents=[],
            )

        all_files: list[str] = list_result.get("files", [])
        candidates = [f for f in all_files if f.endswith(_REVIEW_SOURCE_EXTENSIONS)]
        selected = candidates[:_REVIEW_MAX_FILES]

        read_files: dict[str, str] = {}
        read_errors: list[str] = []
        for path in selected:
            outcome = ctx.run_tool("github_read_file", {"repo": repo, "path": path})
            result = outcome.get("result") or {}
            if outcome.get("ok") and result.get("ok"):
                content = result.get("content", "")
                read_files[path] = content[:_REVIEW_MAX_CHARS_PER_FILE]
            else:
                read_errors.append(
                    f"{path}: {result.get('error') or outcome.get('error') or 'unknown error'}"
                )

        system_prompt = (
            "You are a senior software engineer reviewing a real codebase. Base your review "
            "ONLY on the real file listing and real file contents supplied below — never "
            "invent files, features, or code you were not shown. This is a partial view "
            "(a capped sample of files, not the whole repo), so be explicit in `gaps` about "
            "what you could not see rather than assuming the rest of the codebase matches "
            "what you did see. "
            "Respond ONLY with a JSON object exactly matching this schema: "
            + json.dumps(CodebaseReviewSchema.model_json_schema())
        )
        user_prompt = json.dumps(
            {
                "repo": repo,
                "total_files_in_repo": len(all_files),
                "files_reviewed": list(read_files.keys()),
                "files_reviewed_count_vs_total": f"{len(read_files)}/{len(all_files)}",
                "file_contents": read_files,
                "files_that_could_not_be_read": read_errors,
            },
            default=str,
        )

        review = self._structured_llm(ctx, system_prompt, user_prompt, CodebaseReviewSchema)
        if review is None:
            return AgentResult.deterministic(
                result={"status": "not_generated", "reason": "no_llm_provider", "repo": repo},
                confidence=0.2,
                assumptions=["Review requires a real model provider (e.g. Groq)"],
                sources=["none available"],
                risks=["No review was produced"],
                next_recommended_agents=[],
            )

        return AgentResult.llm(
            result={
                "repo": repo,
                "status": "review_complete",
                "files_reviewed": list(read_files.keys()),
                "files_reviewed_count": len(read_files),
                "total_files_in_repo": len(all_files),
                "summary": review["summary"],
                "strengths": review["strengths"],
                "gaps": review["gaps"],
                "suggested_additions": review["suggested_additions"],
            },
            schema=_ReviewOutputSchema,
            confidence=0.6,
            assumptions=[f"Review is grounded only in the {len(read_files)} files actually read"],
            sources=["validated LLM review (real provider)", "GitHub Contents/Trees API"],
            risks=[
                f"Only {len(read_files)} of {len(all_files)} real files in the repo were reviewed"
            ],
            next_recommended_agents=["coding"],
        )

    async def _run_change(self, ctx: AgentContext, repo: str, goal: str) -> AgentResult:
        task = str(ctx.inputs.get("task", "")).strip() or goal
        base = str(ctx.inputs.get("base", "main")).strip() or "main"
        context_paths = ctx.inputs.get("context_files") or []
        if not isinstance(context_paths, list):
            context_paths = []

        read_files: dict[str, str] = {}
        read_errors: list[str] = []
        for path in context_paths:
            outcome = ctx.run_tool("github_read_file", {"repo": repo, "path": str(path)})
            result = outcome.get("result") or {}
            if outcome.get("ok") and result.get("ok"):
                read_files[str(path)] = result.get("content", "")
            else:
                read_errors.append(
                    f"{path}: {result.get('error') or outcome.get('error') or 'unknown error'}"
                )

        system_prompt = (
            "You are a careful senior software engineer proposing a code change. "
            "Base every file edit ONLY on the real file contents supplied below — never "
            "invent files or assume content you were not given. If you need to see a file "
            "that was not supplied, say so in `risks` instead of guessing its content. "
            "Respond ONLY with a JSON object exactly matching this schema: "
            + json.dumps(CodeChangeSchema.model_json_schema())
        )
        user_prompt = json.dumps(
            {
                "repo": repo,
                "task": task,
                "existing_files": read_files,
                "files_that_could_not_be_read": read_errors,
            },
            default=str,
        )

        proposal = self._structured_llm(ctx, system_prompt, user_prompt, CodeChangeSchema)
        if proposal is None:
            return AgentResult.deterministic(
                result={
                    "status": "not_generated",
                    "reason": "no_llm_provider",
                    "repo": repo,
                    "task": task,
                },
                confidence=0.2,
                assumptions=["Code generation requires a real model provider (e.g. Groq)"],
                sources=["none available"],
                risks=["No code change was proposed — nothing was written or opened as a PR"],
                next_recommended_agents=[],
            )

        if not proposal["files"]:
            # A real, valid outcome — not a failure. The model looked at the
            # real files and genuinely found nothing to change (e.g. the
            # version asked for is already met). Reporting this as a failed
            # PR attempt would be misleading, since no change was ever
            # written or attempted.
            return AgentResult.llm(
                result={
                    "repo": repo,
                    "status": "no_change_needed",
                    "summary": proposal["summary"],
                    "pr_opened": False,
                    "pr_url": None,
                    "files_not_read": read_errors,
                },
                schema=_NoChangeOutputSchema,
                confidence=0.7,
                assumptions=["Proposal is grounded only in the files actually supplied"],
                sources=["validated LLM code proposal (real provider)", "GitHub Contents API"],
                risks=proposal["risks"],
                next_recommended_agents=[],
            )

        branch = f"av-nexus/{proposal['branch_suffix']}-{uuid.uuid4().hex[:8]}"
        pr_outcome = ctx.run_tool(
            "github_propose_pr",
            {
                "repo": repo,
                "base": base,
                "branch": branch,
                "title": proposal["title"],
                "body": proposal["body"],
                "files": [
                    {"path": f["path"], "content": f["content"], "message": f["message"]}
                    for f in proposal["files"]
                ],
            },
        )
        pr_result = pr_outcome.get("result") or {}
        pr_ok = bool(pr_outcome.get("ok")) and bool(pr_result.get("ok"))

        return AgentResult.llm(
            result={
                "repo": repo,
                "branch": branch,
                "summary": proposal["summary"],
                "files_changed": [f["path"] for f in proposal["files"]],
                "pr_opened": pr_ok,
                "pr_url": pr_result.get("pr_url") if pr_ok else None,
                "pr_error": None if pr_ok else (pr_result.get("error") or pr_outcome.get("error")),
                "files_not_read": read_errors,
            },
            schema=_CodingOutputSchema,
            confidence=0.75 if pr_ok else 0.5,
            assumptions=["Proposal is grounded only in the files actually supplied"],
            sources=["validated LLM code proposal (real provider)", "GitHub Contents API"],
            risks=proposal["risks"] + ([] if pr_ok else ["PR creation failed — see pr_error"]),
            next_recommended_agents=["critic"],
        )


class _CodingOutputSchema(BaseModel):
    model_config = ConfigDict(extra="ignore")

    repo: str
    branch: str
    summary: str
    files_changed: list[str]
    pr_opened: bool


class _NoChangeOutputSchema(BaseModel):
    model_config = ConfigDict(extra="ignore")

    repo: str
    status: str
    summary: str
    pr_opened: bool


class _ReviewOutputSchema(BaseModel):
    model_config = ConfigDict(extra="ignore")

    repo: str
    status: str
    files_reviewed_count: int
    total_files_in_repo: int
    summary: str
