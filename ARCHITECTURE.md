# AV Nexus (Artiswon Nexus) — System Architecture

> AI Business Operating System: discover → research → analyze → validate → build → launch → operate → measure → optimize → scale.

Version: 0.1.0 (Phase 1) · Status: implemented for Core Infrastructure + Orchestrator skeleton

---

## 1. Architecture Analysis

### 1.1 What we are building

AV Nexus is **not a chatbot and not a single agent**. It is a hierarchical **multi-agent
organization** that helps a human owner (`HUMAN OWNER / CHAIRMAN`) discover business
opportunities, research markets, validate ideas, build companies, and then operate a
portfolio of companies with automated monitoring, KPI tracking, risk management, and
board-level reporting.

### 1.2 Key architectural qualities (in priority order)

| Priority | Quality | How enforced |
|---|---|---|
| 1 | Reliability | Retry → fallback → escalation ladder; structured failures; no crashes |
| 2 | Security | JWT auth, role gates, approval levels, audit log, no secrets in code |
| 3 | Modularity | `BaseAgent` contract; plugin-style agents; composed at runtime |
| 4 | Observability | Every task/agent-run/message/decision recorded; execution traces |
| 5 | Scalability | Stateless API + DB-backed state; workers behind queue later |
| 6 | Human control | Level-3/4 actions always require explicit human approval |

### 1.3 Missing requirements / gaps identified in the brief

- **LLM provider abstraction** — the brief names no model provider. We define an
  `LLMClient` protocol so OpenAI / Anthropic / local models can be plugged in and swapped
  as the "agent framework" evolves. Deterministic `MockLLM` keeps the whole system
  offline-testable and honest (no faked "real" research).
- **Honesty boundary** — the brief forbids faking autonomy and fake intelligence. Agents
  carry a `mode`: `llm` (real provider) or `deterministic` (computed, offline). Outputs
  are labeled with `confidence`, `assumptions`, `sources`, `risks`. No output pretends to
  be live external research unless a real data source produced it.
- **Tenant model** — the brief mentions many companies under one owner. We add an
  `Organization` root: Chairman → Organization → Companies.
- **Legal disclaimer** — the Legal & Compliance Agent must print an explicit non-lawyer
  disclaimer (spec §AGENT 14). We honor that in the agent definition and its outputs.
- **Demo mode** — three sample companies (Voxline AI, KrtLab, Atlas) are seeded and every
  seeded metric is **flagged `is_demo=true`** so the dashboard can show "DEMO DATA".

### 1.4 Known risks (tracked, not hidden)

- **Risk R-01** Deterministic agents are not autonomous. Mitigation: orchestration is
  real; agents run either via a real LLM (when `AVNEXUS_LLM__PROVIDER` is configured) or
  in explicit deterministic mode that is surfaced in results and UI.
- **Risk R-02** LLM hallucination on business numbers. Mitigation: confidence system,
  critic review step, Chairman approval gate, and a rule that uncertain numbers are
  labeled instead of asserted.
- **Risk R-03** External tool access. Phase 1 ships **no** external side-effecting tools
  (no money movement, no email send, no contracts). The approval system is fully wired so
  that when such tools arrive they default to Level 4 (Chairman) gates.
- **Risk R-04** Scale. Phase 1 runs tasks in-process with async concurrency. The Task API
  is queue-neutral by design (see `orchestrator`), so a real Redis worker can replace the
  in-process executor without changing task semantics.

---

## 2. System Diagram

```
                        ┌───────────────────────────┐
                        │   👑 HUMAN OWNER / CHAIRMAN  │  ← final authority; level-4 approvals
                        └────────────┬──────────────┘
                                     │  WebSocket + REST (JWT)
                                     ▼
                     ┌────────────────────────────────┐
                     │      NEXUS ORCHESTRATOR        │
                     │   AI COMMAND CENTER (kernel)   │
                     │  route · merge · cross-check   │
                     │  detect disagreement · review  │
                     │  escalate · confidence score   │
                     └──────────────┬─────────────────┘
                                    │
              ┌─────────────────────┼──────────────────────┐
              ▼                     ▼                      ▼
   ┌────────────────────┐ ┌──────────────────┐ ┌────────────────────────┐
   │ GROUP STRATEGY     │ │ SPECIALIST       │ │ BUSINESS MANAGEMENT    │
   │ LAYER              │ │ AGENT NETWORK    │ │ (per company)          │
   │ CSO · INTEL · COO  │ │ Scout · Market   │ │ AI CEO · CFO · CMO ·   │
   │ CFO · RISK · LEGAL │ │ Research · CI ·  │ │ COO · Sales · Invest · │
   │ INVEST · M&A · DATA│ │ Innovation ·     │ │ M&A                    │
   │ Critic · Analytics │ │ Validation ·     │ │                        │
   └────────────────────┘ │ Venture Builder  │ │                        │
                          └──────────────────┘ └────────────────────────┘
                                    │
                                    ▼
        ┌──────────────────────────────────────────────────────────┐
        │ SHARED STATE LAYER                                        │
        │ PostgreSQL (relational) · Shared Memory (global/company/  │
        │ agent/decision) · Knowledge Graph · Task Store · Audit    │
        └──────────────────────────────────────────────────────────┘
```

Execution path for a business-creation request (11-step pipeline, §9 of brief):

```
User: "I want to create a new business"
 ↓
[1] Opportunity Scout → [2] Market Research → [3] Competitive Intelligence
 → [4] Validation Agent (skeptic) → [5] Finance (CFO) → [6] Risk Agent
 → [7] Chief Strategy → [8] Critic → [9] Orchestrator merges + confidence
 → [10] HUMAN CHAIRMAN approves/rejects/modifies → [11] Venture Builder blueprint
```

---

## 3. Technology Stack Decision

| Layer | Choice | Rationale / notes |
|---|---|---|
| Backend | **Python 3.13 + FastAPI** | Async, typed (Pydantic v2), mature agent/LLM ecosystem; aligns with existing `core-client-os` conventions |
| ORM | SQLAlchemy 2.0 (declarative) | Production-grade; Alembic migrations; DB-agnostic repos |
| Database | PostgreSQL; **SQLite fallback** for dev/tests | pydantic-settings `AVNEXUS_DB_URL`; SQLite keeps CI offline |
| Vector / memory | layering now; pgvector SQLAlchemy type stubbed | Semantic retrieval deferred (Phase 6) |
| Cache / queue | Redis planned; **in-process async** now | Task executor is queue-neutral (R-04) |
| LLM | Provider abstraction `LLMClient` | OpenAI-compatible HTTP; `MockLLM` deterministic offline; no keys in repo |
| Frontend | React + TypeScript + Vite + Zustand | Lighter than Next for a command-center SPA; dark mode |
| Realtime | WebSockets (FastAPI) | Agent activity stream (Phase 5) |
| Auth | JWT (access token) + bcrypt + role gates | Roles: `chairman, admin, analyst, agent` |
| Deploy | Docker Compose (api + web + postgres [+ redis]) | `infrastructure/docker-compose.yml` |
| Env | Development / Staging / Production via env vars | `AVNEXUS_ENV`, `.env` (no secrets in git) |

### 3.1 Directory layout

```
av-nexus/
  ARCHITECTURE.md          this file
  ROADMAP.md               phase plan + definition of done
  docs/
    DATABASE.md            schema detail
    AGENTS.md              agent registry design
    PROTOCOL.md            agent communication protocol
  backend/
    av_nexus/
      config.py            pydantic-settings
      main.py              FastAPI app factory
      db/                  engine + session
      models/              SQLAlchemy tables (22 domains)
      schemas/             Pydantic DTOs
      api/                 routers (auth, agents, tasks, ...)
      core/                security, audit, approvals
      agents/              BaseAgent + registry + reference agents
      orchestrator/        kernel: routing, merge, review, escalate
      llm/                 LLMClient protocol + OpenAI + Mock
      memory/              shared memory layers
      knowledge/           knowledge graph
      seed/                demo data (Voxline AI, KrtLab, Atlas)
    tests/
  frontend/                Vite + React dashboard
  infrastructure/          docker-compose, Dockerfiles
```

---

## 4. Agent Registry Design

See `docs/AGENTS.md` for the full contract. Executive summary:

- **Every agent is a `BaseAgent`** registered at composition root into an `AgentRegistry`
  keyed by stable `agent_id`.
- Agent metadata: `agent_id, name, role, capabilities[], tools[], permissions[],
  status, performance_score, tasks_completed` (persisted in `agents` table).
- Capabilities enable **dynamic discovery**: the orchestrator routes a task to the set of
  agents whose capabilities match the required skill, never by hardcoded name.
- Reference agents implemented in Phase 1 (with deterministic + LLM modes):
  `opportunity_scout, market_research, competitive_intelligence, validation,
  venture_builder, strategy, finance, risk, critic, legal_compliance`. Additional roles
  (`ceo, cmo, coo, sales, investment, mna, data_analytics, innovation`) are registered
  with definitions and a deterministic default so no agent appears missing.

## 5. Agent Communication Protocol

See `docs/PROTOCOL.md`. Payload contracts:

```json
{
  "task_id": "...", "from_agent": "opportunity_scout",
  "to_agent": "market_research", "task_type": "market_validation",
  "priority": "high", "context": {}, "expected_output": {},
  "deadline": "...", "confidence_required": 0.8
}
```

Every agent output envelope (the **truth-in-reporting contract**):

```json
{
  "result": {}, "confidence": 0.0,
  "assumptions": [], "sources": [], "risks": [],
  "next_recommended_agents": [], "mode": "deterministic" | "llm"
}
```

## 6. Database

See `docs/DATABASE.md`. 22 tables covering users, organizations, companies, agents,
agent_capabilities, tasks, task_dependencies, agent_messages, agent_runs, decisions,
approvals, opportunities, markets, competitors, products, projects, kpis,
financial_metrics, risks, audit_logs, knowledge_entities, knowledge_relationships.

## 7. Orchestration & Human Approval

- Task statuses: `QUEUED → RUNNING → (WAITING | REVIEW | APPROVAL_REQUIRED) → COMPLETED | FAILED`.
- Approval levels: **L1** research/analyze (auto) · **L2** drafts/plans (auto) ·
  **L3** external action (needs approval) · **L4** Chairman (money, contracts, hiring,
  legal, irreversible).
- Decisions with an approval gate are never marked COMPLETED until approved;
  disagreement between agents triggers an explicit Critic review and a comparison
  presented to the Chairman.

## 8. Honesty & Demo Rules

- Every agent output carries `mode` + `confidence` + `sources`.
- Seeded metrics carry `is_demo=true`; the UI renders a persistent "DEMO DATA" badge.
- No endpoint pretends to execute external side-effecting actions; the approval system is
  the gate for future tools.
- The Legal agent always attaches its 'not legal advice' disclaimer.

## 9. Phase Plan

| Phase | Scope | Status |
|---|---|---|
| 0 | Docs (this repo) | ✅ |
| 1 | Core Infrastructure: auth, db, agent registry, task system, approvals, demo seed | ✅ |
| 2 | Orchestrator: routing, aggregation, disagreement detection, escalation, 11-step pipeline | ✅ (kernel) |
| 3 | Core agent behaviors (strategy, scout, market research, validation, critic, risk) | ✅ (deterministic + LLM-ready) |
| 4 | Business management agents (CEO/CFO/CMO/COO) | 🔜 Phase 4 |
| 5 | Dashboard UI (Command Center, Agent Network) | 🔜 Phase 5 |
| 6 | Memory semantics + knowledge graph query API | 🔜 Phase 6 |
| 7 | Advanced collaboration (debate, review threads) | 🔜 Phase 7 |
| 8 | Redis worker, WebSockets, pgvector | 🔜 Phase 8 |
| 9 | Full test hardening + failure-injection suite | 🔜 Phase 9 |
| 10 | Production deployment (Docker Compose, staging) | 🔜 Phase 10 |