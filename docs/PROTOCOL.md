# AV Nexus — Agent Communication Protocol

Version 1.0. Messages are JSON, persisted in `agent_messages`, and idempotent.

## 1. Task message

```json
{
  "task_id": "...",
  "from_agent": "opportunity_scout",
  "to_agent": "market_research",
  "task_type": "market_validation",
  "priority": "high",
  "context": {"industry": "ai_education"},
  "expected_output": {"schema": "validation_file"},
  "deadline": "...",
  "confidence_required": 0.8
}
```

## 2. Output envelope (mandatory for every agent result)

```json
{
  "result": {},
  "confidence": 0.7,
  "assumptions": ["TAM from public analyst estimates"],
  "sources": ["internal heuristic: market_size=1.0 if demand_score>0.6"],
  "risks": ["estimate unverified externally"],
  "next_recommended_agents": ["validation", "risk"],
  "mode": "deterministic"
}
```

Rules:

- `mode` is **never omitted**. `llm` = output produced by a real model provider.
  `deterministic` = computed offline by code. UI must render the difference.
- `confidence` must be consistent: outputs with no evidence cannot be 1.0.
- A result that references external data MUST list a source; missing source ⇒
  `confidence` capped at 0.4 by the kernel.

## 3. Message types (`message_type`)

| type | meaning |
|---|---|
| `task_assignment` | orchestrator delegates to agent |
| `handoff` | agent passes work to another |
| `result` | agent returns structured output |
| `question` | agent asks orchestrator for clarification |
| `disagreement` | two agents conflict |
| `critique` | critic reviews an output |
| `escalation` | agent escalates to orchestrator |
| `approval_request` | orchestrator requests human gate |

## 4. Disagreement resolution flow

```
Strategy: BUILD (conf 0.82)  vs  Risk: DO NOT BUILD (conf 0.71)
→ kernel detects polarity conflict on same decision payload
→ request additional evidence from both (message_type=question)
→ invoke critic (message_type=critique) on both
→ compose DecisionComparison {options, differences, critic_opinion, confidence}
→ publish to Chairman (approval_request, level 4) — never hidden
```

## 5. Orchestration pipeline message

The `POST /orchestrator/run` endpoint accepts a natural-goal description, plans a stage
list, and emits `Task` + `TaskMessage` records; the response contains the full `agent_runs`
trace:

```
User Request → Orchestrator → [strategy, opportunity_scout, market_research,
validation, finance, risk, critic] → merged FinalRecommendation → approval gate
```