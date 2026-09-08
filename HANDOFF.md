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
- Frontend: **35/35 vitest passing** (30 baseline + 5 new for RunAgentPanel),
  eslint clean (5 pre-existing non-blocking fast-refresh warnings only),
  production build green
- All verification above was run directly, not copied from a report.

## Latest session (frontend UI for the 10 previously-dormant agents)

Built the "run any agent ad hoc" UI (option (a) from the previous handoff):
- `lib/types/domain.ts`: added `input_json` to `Task`, added
  `TaskCreatePayload`/`TaskRunResponse` types.
- `lib/api/tasks.ts` (new): `createTask`, `getTask`, `runTask`,
  `runAgentNow` — thin wrappers over the existing `/tasks` API, no new
  backend behavior.
- `features/agent-run/RunAgentPanel.tsx` (new): goal input + JSON textarea
  for real `input_json`, "Run now" button, inline result display. Client-
  side JSON validation with a clear error, not a silent failure. Routes by
  `owner_agent_id` (the agent's own DB uuid, already available on the
  agent-detail page) rather than by capability string, since it's more
  precise and avoids relying on capability-string uniqueness.
- Wired into `AgentDetailPage.tsx` — every one of the 18 agents (not just
  the original 8 in the fixed venture-evaluation pipeline) now has a real,
  working "Run this agent now" panel reachable from the UI, with results
  and a refreshed run/task history immediately visible on the same page.
- 5 new tests (`__tests__/runAgentPanel.test.tsx`): renders correctly,
  submits real JSON and calls createTask/runTask with the right payload,
  rejects invalid JSON without calling the API, requires a goal, surfaces
  API errors.
- Two existing test fixtures (`agentDetail.test.tsx`, `approvals.test.tsx`)
  updated for the new required `input_json` field on `Task`.

This closes the loop from the previous session: the 10 agents were made
callable via the API, and now a human can actually use them from the app
without hand-crafting HTTP requests.

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

(a) is done. Remaining, in priority order for Suren's 1-2 week "fully
working" target:

1. **Voxline Sales OS → Railway deploy** (option (b) from before). Blocked
   on Suren providing: Railway account access, and real env var values
   (GEMINI_API_KEY, RESEND_API_KEY/FROM_EMAIL, GMAIL_USER/APP_PASSWORD,
   VOXLINE_CONTACT_*). The known auth gap (no route-level auth on that
   repo's API) must be fixed or the service must stay off a public domain
   — do not deploy it publicly as-is. Without this, CEO/CFO/CMO/COO/Sales
   agents are honest but limited to hand-typed input_json — real value
   requires a real data feed.
2. Approval-level UI: tasks created via RunAgentPanel currently default to
   approval_level 1 (no gate) — matches the "advisory only in this phase"
   decision made earlier in this project. If Suren wants any of these 10
   agents to eventually trigger real external actions (e.g. Sales agent
   actually sending outreach), that needs explicit approval-level wiring
   in the UI too, plus a real decision on which actions are gated.
3. The coding agent (option (c)) — still not started. Higher risk, needs
   its own write/commit approval-gating design first. Recommend not
   starting this inside the 1-2 week window unless (1) and (2) are done
   with room to spare.

Do not start more than one without checking in — the pattern in this
project has consistently been: pick one narrow thing, prove it end-to-end
with real tests, verify independently, then move on.
