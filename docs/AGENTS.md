# AV Nexus — Agent Registry Design

## 1. Contract

Every agent is an instance of `BaseAgent` (abstract) with:

```python
class AgentContext:
    org_id, user_id, llm: LLMClient | None, memory: SharedMemory,
    knowledge: KnowledgeGraphStore

class AgentResult(BaseModel):
    result: dict                # structured output of this specific agent
    confidence: float           # 0..1
    assumptions: list[str]
    sources: list[str]
    risks: list[str]
    next_recommended_agents: list[str]   # capabilities, not ids
    mode: Literal["llm", "deterministic"]
```

`run(ctx, task) -> AgentResult` is the only required method. Agents **never** mutate DB
state, execute money moving, or reach external services. They produce structured outputs;
the orchestrator persists outputs as task `output_json`.

## 2. Registry

`AgentRegistry` maps stable `agent_id` → `BaseAgent`. Supports:

- `register(agent)` / `get(agent_id)` / `all()`
- `find_by_capability(capability)` → list of agents whose `capabilities` include it
- `snapshot()` → dict for the `/agents` API (metadata + live status counters)

The orchestrator routes **by capability**, never by hardcoded agent name:

```
required_skill "market_validation" → registry.find_by_capability → {validation, market_research}
```

## 3. Agent inventory (18+ roles)

| agent_id | role | capabilities |
|---|---|---|
| `strategy` | Chief Strategy Officer | `strategy, portfolio, prioritization` |
| `opportunity_scout` | Opportunity Scout | `opportunity_discovery, trend_analysis` |
| `market_research` | Market Researcher | `market_research, market_validation` |
| `competitive_intelligence` | Competitive Intelligence | `competitor_analysis, market_intelligence` |
| `innovation` | Innovation & R&D | `product_ideation, technology_scouting` |
| `venture_builder` | Venture Builder | `company_blueprint, business_model` |
| `validation` | Validation (skeptic) | `idea_challenge, market_validation` |
| `ceo` | AI CEO (per company) | `company_strategy, kpi_monitoring` |
| `finance` | CFO | `financial_analysis, unit_economics, forecasting` |
| `marketing` | CMO | `marketing_strategy, growth_experiments, branding` |
| `operations` | COO | `operations, process_analysis, bottleneck_detection` |
| `sales` | Sales | `lead_research, pipeline, crm_insights` |
| `risk` | Risk Officer | `risk_analysis, scenario_analysis` |
| `legal_compliance` | Legal & Compliance | `compliance_review, risk_screening` |
| `investment` | Investment | `capital_allocation, roi_analysis` |
| `mna` | M&A | `ma_scanning, synergy_analysis` |
| `data_analytics` | Data & Analytics | `metrics_analysis, anomaly_detection` |
| `critic` | Critic | `critical_review, bias_detection` |

## 4. Permissions / approval tied to capability class

| Capability class | Approval level | Auto? |
|---|---|---|
| research/analyze/score | 1 | yes |
| create draft plan/blueprint | 2 | yes |
| execute external action (future) | 3 | no — approval required |
| money / contracts / hiring / legal / irreversible | 4 | no — Chairman only |

Agents advertise `permissions[]` (capability classes). The orchestrator checks the task's
`approval_level`; if ≥3 it flips the task to `APPROVAL_REQUIRED` before any run completes.

## 5. Failure semantics

An agent raising is converted (by the kernel) to `AgentResult(mode="deterministic",
result={"error": ...}, confidence=0.0)` is NOT acceptable — a failing agent must produce a
structured `AgentExecutionError` with `retryable` flag. Kernel policy:

1. retry (max 2, exponential backoff)
2. fallback agent with overlapping capability
3. mark task `FAILED`, message orchestrator, escalate to Chairman