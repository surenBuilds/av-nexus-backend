# HANDOFF — read this first before continuing work

This file exists so work can switch between Claude (chat) and opencode (CLI)
without losing context. Whoever picks this up next: read this whole file,
then update/replace it at the end of your session with the new state.

## How to pick up from here (for opencode / a fresh session)

```
git clone https://github.com/surenBuilds/av-nexus-backend.git
cd av-nexus-backend/backend && uv sync && uv run pytest -q   # expect 91 passed
cd ../frontend && npm install && npm test                     # expect 30 passed
```
Read this file end to end before writing any code. It tells you exactly
what's done, what's verified, and what's next — don't re-derive it from
scratch or re-audit things already covered below.

## Last verified state (this commit)

- Backend: **91/91 pytest passing**, ruff clean, mypy --strict clean (64 files)
- Frontend: **30/30 vitest passing**, eslint clean (5 pre-existing non-blocking
  fast-refresh warnings only), production build green
- All verification above was run directly, not copied from a report.

## What just happened in this session

1. Cloned the real repo directly (not via opencode) and independently
   re-verified every number opencode had previously reported — all matched.
2. Applied AW-Nexus's visual design (a separate AI-Studio-generated repo,
   `github.com/surenBuilds/AW-Nexus`) to this frontend: lucide-react icons
   in nav, `.btn-gradient` / `.badge-mono` utility classes, gradient CTA
   on "Create workflow" only (Approve/Reject on L3/L4 gates intentionally
   left on plain green/red — clarity over flair at a decision gate).
   AW-Nexus's own Express backend/agent logic was explicitly NOT reused —
   it fabricates data (`Math.random()` scores, hardcoded TAM/SAM/SOM,
   static blueprint text) and would have reintroduced exactly the
   fabrication problem earlier phases spent effort removing.
3. **Major discovery**: all 18 agents from the original spec (including
   CEO, CFO, CMO, COO, Sales, Innovation, Legal & Compliance, Investment,
   M&A, Data & Analytics — the ones a previous chat summary had incorrectly
   reported as "not built") already exist as real, honest, input-driven
   code in `agents/management.py`, `agents/group_strategy.py`,
   `agents/guardian.py`, `agents/scout.py`, and are registered in
   `agents/__init__.py::ALL_AGENTS`. They were never fabricating anything —
   they just had **no invocation path**: the fixed pipelines
   (`business_creation`, `venture_blueprint`) only call the original 8
   agents, and the generic `POST /tasks` → `POST /tasks/{id}/run` path
   (which IS agent-agnostic via `capability` routing) was silently
   dropping `input_json` because the `TaskCreate` API schema never had
   the field, even though `OrchestratorService.create_task()` always
   accepted it.
4. Fixed the actual bug: added `input_json` to `TaskCreate` (request) and
   `TaskOut` (response) schemas, wired it through the `/tasks` POST
   endpoint. This one fix makes all 10 previously-dormant agents callable
   with real data through the existing, already-tested execution engine —
   no parallel execution path was created.
5. Added `tests/test_management_agents.py` (15 tests) proving, through the
   real HTTP API, that CEO/CFO/CMO/COO/Sales/Innovation/Legal/Investment/
   M&A/DataAnalytics all run end-to-end, and — critically — that their
   output genuinely varies with different `input_json` (e.g. two different
   financial pictures produce two different `financial_health_score`
   values), not template text with numbers swapped in.

## What is still NOT done (don't assume otherwise)

- **No real external data source is connected.** These agents compute
  correctly from whatever `input_json` a caller supplies, but nothing in
  this system yet feeds them real Voxline revenue/leads/KPIs automatically.
  The Voxline AI Sales OS (separate repo) has never run continuously
  anywhere reachable — this was investigated at length earlier and is
  still unresolved. Until that's deployed (Railway, with a persistent
  volume) or another real data source exists, these agents are honest but
  low-value in practice — call them with real numbers by hand, or wire a
  real integration before expecting a genuinely useful CEO daily report.
- **No frontend UI yet** for creating/running tasks against these 10
  agents with custom `input_json` — the existing frontend's workflow UI
  only drives the original 8-agent venture-evaluation pipeline. A
  generic "run any agent with these inputs" screen doesn't exist.
- **The coding agent** (the one meant to work on Suren's other products —
  KrtLab, Voxline, etc.) has not been started. Agreed policy so far:
  file writes without approval, but git commit/push gated behind human
  confirmation. No code exists for this yet.
- **AW-Nexus's Express backend** is now confirmed dead weight — it was
  never wired in and should not be deployed or maintained. Its only
  remaining value was as a design reference, which has been extracted.

## Recommended next step

Pick ONE:
(a) Build the generic "run an agent with custom inputs" frontend screen,
    so the now-functional 10 agents are actually usable by a human without
    curling the API by hand.
(b) Go back to deploying Voxline Sales OS on Railway so these agents have
    a real data feed instead of hand-typed input_json.
(c) Start the coding agent (higher risk — needs its own write/commit
    approval-gating design before any code).

Do not start more than one without checking in — the pattern in this
project has consistently been: pick one narrow thing, prove it end-to-end
with real tests, verify independently, then move on.
