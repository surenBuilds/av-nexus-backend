# AV Nexus — Roadmap

Definition of done per phase: **pytest green · mypy clean · ruff clean · API importable ·
offline (no network, no keys required); real LLM optional via env.**

## PHASE 0 — Design ✅
- `ARCHITECTURE.md`, `docs/DATABASE.md`, `docs/AGENTS.md`, `docs/PROTOCOL.md`, `ROADMAP.md`.

## PHASE 1 — Core Infrastructure ✅
- Reusable backend scaffold: FastAPI app factory, `pydantic-settings` config (`.env`,
  no secrets), SQLite/postgres dual DB, SQLAlchemy 2.0 models for the 22-domain schema.
- Auth: register/login/jwt/me with role gates (`chairman|admin|analyst|agent`);
  bcrypt; audit log hooks.
- Agent registry + `BaseAgent` contract + capability discovery.
- Task system: create/queue/depend/status transitions; approval-level integration.
- Shared memory (global / company / agent / decision) + knowledge graph entities.
- Reference agents in **deterministic mode**: strategy, opportunity_scout,
  market_research, competitive_intelligence, validation, venture_builder, finance,
  risk, critic, legal_compliance. `LLMClient` protocol + OpenAI HTTP implementation +
  `MockLLM` (offline).
- Orchestrator kernel: plan pipeline → route by capability → run → merge → review →
  escalate; 11-step business-creation pipeline; disagreement detection.
- Demo seed: Voxline AI, KrtLab, Atlas (all `is_demo=true`).
- Tests for models/auth/tasks/registry/orchestrator/agents/API/permissions.

## PHASE 2 — Orchestrator polish 🔜
- Persistent review threads, richer disagreement matrix, confidence derivation from
  source coverage, decision comparison UI data shape.

## PHASE 3 — Core agent behaviors
- Full LLM prompts per agent; deterministic fallback when provider absent; latency,
  token, cost capture in `agent_runs`.

## PHASE 4 — Business management agents
- CEO/CFO/CMO/COO/Sales real behaviors: KPI ingestion, anomaly detection, weekly
  report generation.

## PHASE 5 — Dashboard
- React + Vite command center: Command Center, Agent Network, Opportunities, Companies,
  Portfolio, Intelligence, Finance, Operations, Risks, Decisions, Knowledge, Activity.

## PHASE 6 — Memory semantics
- Agent memory summaries, decision memory queries, knowledge graph query endpoints.

## PHASE 7 — Advanced collaboration
- Debate protocol, review threads, agent self-evaluation scoring.

## PHASE 8 — Scale
- Redis-backed task worker, WebSockets activity stream, pgvector semantic retrieval,
  rate limiting, Alembic migrations.

## PHASE 9 — Test hardening
- Failure injection: agent crash, tool unavailable, DB down, task timeout, approval
  denied, disagreement conflict.

## PHASE 10 — Deployment
- Docker Compose (api/web/postgres/redis), staging env, health checks, secrets via env.