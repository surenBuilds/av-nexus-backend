# AV Nexus — Database Design

PostgreSQL for production (`AVNEXUS_DB_URL`), SQLite for CI/dev/tests (fully offline).
All timestamps UTC. All tables have `created_at`/`updated_at` where meaningful.

`org_id` (organization) is the tenant boundary. `NULL` org means "system/global".

## Tables

### users
- `id` uuid PK
- `email` unique, `password_hash`, `full_name`
- `role` enum: `chairman | admin | analyst | agent`
- `is_active`
- `can_authorize_level4` bool (only chairman)

### organizations
- `id`, `name`, `slug` unique, `owner_id` → users
- one per windowed Chairman; root of the tenant tree

### companies
- `id`, `org_id` FK, `name`, `slug`, `industry`, `stage`
  (`idea|mvp|active|growth|paused`)
- `mission`, `vision`, `business_health_score` (0–100)
- `is_demo` bool — **true for seeded demo companies**
- `metadata_json`

### agents
- `id`, `agent_id` (stable key e.g. `opportunity_scout`) unique
- `name`, `role`, `description`
- `capabilities_json`, `tools_json`, `permissions_json`
- `status` (`idle|thinking|researching|waiting|blocked|reviewing|completed|failed`)
- `performance_score` float, `tasks_completed` int
- `is_active`

### agent_capabilities
- `id`, `agent_id` FK, `capability` (e.g. `market_research`)

### tasks
- `id` uuid, `task_ref` human id (e.g. `T-7F3K`)
- `org_id` FK, `title`, `goal`, `description`
- `owner_agent_id` FK → agents
- `status` enum: `QUEUED|RUNNING|WAITING|REVIEW|APPROVAL_REQUIRED|COMPLETED|FAILED`
- `priority` (`low|medium|high|critical`)
- `deadline`, `output_json`, `confidence` float, `error`
- `approval_status` (`none|required|approved|rejected`)
- `created_by` → users

### task_dependencies
- `id`, `task_id` FK, `depends_on_task_id` FK (cycle-checked)

### agent_messages
- `id`, `task_id` FK, `from_agent` key, `to_agent` key, `message_type`,
  `payload_json`, `priority`, `sent_at`

### agent_runs
- `id`, `agent_id`, `task_id`, `status`, `started_at`, `ended_at`,
  `error`, `tokens_in`, `tokens_out`, `cost_usd`, `trace_json`

### decisions
- `id`, `org_id`, `title`, `decision_type`
  (`capital_allocation|build_company|kill_company|strategy|approval|other`)
- `status` (`proposed|approved|rejected|modified`)
- `reason`, `supporting_evidence_json`, `agents_involved_json`
- `confidence`, `risk_level` (`LOW|MEDIUM|HIGH|CRITICAL`)
- `approved_by` → users, `created_at`, `approved_at`

### approvals
- `id`, `org_id`, `entity_type` (`company|task|opportunity|decision`), `entity_id`
- `level` int (1–4), `status` (`pending|approved|rejected`)
- `requested_by` (agent key or user id), `decided_by` → users
- `reason`, `created_at`, `decided_at`

### opportunities
- `id`, `org_id`, `title`, `description`, `category`
- Score sub-fields: `opportunity_score`, `market_potential`, `growth_rate`,
  `competition`, `entry_difficulty`, `capital_requirements`, `risk_score`
- `status` (`discovered|researched|validated|approved|rejected|paused`)
- `source`, `is_demo`

### markets
- `id`, `name`, `industry`, `region`, `tam`, `sam`, `som`, `growth_rate_pct`,
  `notes`, `is_demo`

### competitors
- `id`, `name`, `industry`, `company_id` FK (optional link)
- `products`, `pricing`, `strengths_j`, `weaknesses_j`, `threat_score`,
  `recent_developments`, `is_demo`

### products
- `id`, `company_id` FK, `name`, `description`, `pricing_model`, `status`, `is_demo`

### projects
- `id`, `company_id` FK, `name`, `description`, `status`, `owner`, `deadline`, `is_demo`

### kpis
- `id`, `company_id` FK, `name`, `value` float, `target`, `unit`, `period`,
  `recorded_at`, `is_demo`

### financial_metrics
- `id`, `company_id` FK, `metric` (`revenue|expenses|gross_margin|net_margin|cac|ltv|
  burn_rate|runway_months|cash`), `value` float, `currency`, `period`, `is_demo`

### risks
- `id`, `org_id`, `company_id` FK (nullable), `title`, `description`, `category`
  (`financial|market|operational|technology|reputation|strategic|compliance`)
- `level` (`LOW|MEDIUM|HIGH|CRITICAL`), `mitigation`, `status`
  (`open|mitigating|closed`), `owner_agent`, `is_demo`

### audit_logs
- `id`, `user_id` FK nullable, `org_id`, `action`, `entity_type`, `entity_id`,
  `details_json`, `ip`, `created_at`

### knowledge_entities
- `id`, `org_id`, `entity_type`
  (`company|industry|product|customer|competitor|market|technology|investment|project|person|opportunity`)
- `name`, `properties_json`

### knowledge_relationships
- `id`, `org_id`, `from_entity_id` FK, `to_entity_id` FK,
  `relationship_type` (`operates_in|competes_with|solves|exists_in|funds|sells_to|...`)
- `properties_json`

## Conventions
- UUID primary keys (`uuid4`).
- JSON columns via SQLAlchemy `JSON` (SQLite-compatible).
- Enums as string columns (SQLite-friendly) with app-level validation.
- Indexes on: `tasks(org_id,status)`, `agent_messages(task_id)`,
  `opportunities(org_id,status)`, `audit_logs(org_id,created_at)`,
  `risks(org_id,level)`, `kpis(company_id)`, `financial_metrics(company_id)`.