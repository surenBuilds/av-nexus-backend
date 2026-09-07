# Phase 2A/2B — Real Agent Execution & End-to-End Integration (Architecture Plan)

Short plan, written before implementation (per STEPS 1-3). Baseline verified before
any change: backend 33 tests green, ruff clean, mypy clean; frontend 22 tests green,
lint 0 errors, build ok.

## 1. Goal
Turn the green Phase-1 system into a working human-controlled multi-agent MVP:
user logs in -> enters objective -> starts a workflow -> orchestrator creates tasks ->
real-LLM-backed (or clearly-labelled deterministic mock) agent execution ->
runs / messages / disagreements / approval gates recorded -> final synthesis report ->
curated memory saved -> visible execution trace. Stable Phase-1 behavior must not regress.

## 2. Components (new / changed)
- **LLM provider abstraction** (`av_nexus/llm/`): keep `LLMClient` protocol +
  `LLMResult`. Add `anthropic_client`, `google_client` (Gemini), extend `openai_client`
  for OpenAI-compatible base URLs, and a `MeteredLLM` wrapper that accumulates
  tokens/cost. `factory.build_llm_client()` switches on `AVNEXUS_LLM_PROVIDER`
  (`off|openai|anthropic|google|openai_compatible`) and `AVNEXUS_EXECUTION_MODE`
  (`mock|live`). `mock` forces `MockLLM` (never fakes a provider).
- **Config**: add `execution_mode`, `research_tool_enabled` (off by default),
  `workflow_poll_seconds`, `agent_step_timeout_seconds`.
- **Tool system** (`av_nexus/tools/`): `Tool` dataclass (name, description, input
  schema, permission, timeout). Initial safe tools: `calculator`, `structured_analysis`,
  `internal_knowledge_search`, `company_context`, `memory_search`, plus a permanently
  gated `research_web`. Permission denied -> recorded, non-retryable. No shell, no
  arbitrary code, no unfettered internet.
- **AgentExecutor** (`av_nexus/execution/executor.py`): builds `AgentContext`
  (incl. memory/knowledge/tools), system prompt, runs `agent.run()` with bounded
  retries (retryable: provider error / timeout / rate limit; non-retryable: invalid
  result / permission / bad input), records `AgentRun` with tokens/cost/duration/
  tool_calls/attempts in trace, validates `AgentResult`, enforces step timeout.
- **Workflow persistence** (`av_nexus/models/workflows.py`): new tables only:
  `workflows`, `workflow_steps`, `workflow_events`, `workflow_results`. Reuses tasks,
  agent_runs, agent_messages, approvals, decisions, opportunities, memories,
  knowledge entities. Enums: `WorkflowStatus` (CREATED, PLANNING, RUNNING,
  WAITING_FOR_DEPENDENCY, WAITING_FOR_APPROVAL, REVIEWING, COMPLETED, FAILED,
  CANCELLED).
- **Nexus Orchestrator** (`av_nexus/workflows/engine.py` + `pipeline.py`):
  Opportunity Discovery DAG = scout -> {market_research, competitive_intelligence}
  (parallel) -> validation -> risk -> critic -> strategy(CSO) -> synthesis. Planned as
  Tasks with dependencies, executed by a background asyncio runner (own DB session,
  commits after each step so polling sees progress). Disagreement detection via
  `orchestrator.kernel`; critic review step on conflict; approval pause/resume/reject
  at L3/L4 (per-step and final-decision gates); cancellation flag; memory/knowledge
  curation at completion; final synthesis with the 10 mandatory sections.
- **Workflow API** (`av_nexus/api/workflows.py`): POST/GET /workflows,
  GET /workflows/{id}, start/cancel/resume, tasks/runs/messages/trace/result. Mounted
  in main.py.
- **Frontend**: `/workflows`, `/workflows/new`, `/workflows/:id` (polling UI, task
  graph, execution trace, approval gate, final report with COPY + EXPORT JSON), API
  client + types + routes + nav.

## 3. Execution-mode semantics (never faked)
- `mock`: deterministic agents, mode="deterministic", tokens 0. No network.
- `live`: real provider when configured; mode stays agent-reported
  ("deterministic" unless a provider produced output); tokens/cost recorded;
  provider failures -> retryable, bounded.

## 4. Final verification (per brief)
Backend ruff + mypy + pytest (existing 33 + new); frontend test + lint + build;
live local E2E smoke; engineering report with 17 items.