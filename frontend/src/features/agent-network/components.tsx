import { Link } from "react-router-dom";
import { Badge, STATUS_TONE_CLASSES } from "../../components/ui";
import { scoreColor, statusLabel, statusTone } from "../../lib/utils/format";
import type { Agent } from "../../lib/types/domain";

export function groupTier(agentId: string): string {
  switch (agentId) {
    case "ceo":
      return "Executive";
    case "strategy":
      return "Strategy";
    case "opportunity_scout":
    case "market_research":
    case "competitive_intelligence":
    case "innovation":
      return "Intelligence";
    case "venture_builder":
    case "validation":
    case "data_analytics":
    case "operations":
    case "marketing":
    case "sales":
    case "finance":
    case "investment":
    case "mna":
      return "Delivery";
    case "risk":
    case "legal_compliance":
    case "critic":
      return "Governance";
    default:
      return "Delivery";
  }
}

export const TIER_ORDER = ["Executive", "Strategy", "Intelligence", "Delivery", "Governance"];

export function capabilitiesOf(agent: Agent): string[] {
  return agent.capabilities_json ?? [];
}

export function AgentCard({ agent }: { agent: Agent }) {
  const color = scoreColor(agent.performance_score);
  const tone = STATUS_TONE_CLASSES[statusTone(agent.status)] ?? STATUS_TONE_CLASSES.muted;
  return (
    <Link
      to={`/agents/${agent.agent_id}`}
      className="panel block p-4 transition-colors hover:border-accent/50 hover:bg-ink-800"
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="font-mono text-xs text-slate-500">{agent.agent_id}</p>
          <h3 className="mt-0.5 text-sm font-semibold text-slate-100">{agent.name}</h3>
        </div>
        <Badge tone={tone}>{statusLabel(agent.status)}</Badge>
      </div>
      <p className="mt-2 line-clamp-3 text-xs text-slate-400">{agent.description || "No description."}</p>
      <div className="mt-3 flex flex-wrap gap-1.5">
        {(agent.capabilities_json ?? []).slice(0, 4).map((cap) => (
          <span
            key={cap}
            className="rounded-md bg-ink-800 px-1.5 py-0.5 font-mono text-[10px] text-slate-400 ring-1 ring-inset ring-ink-600"
          >
            {cap}
          </span>
        ))}
        {(agent.capabilities_json ?? []).length > 4 && (
          <span className="text-[10px] text-slate-500">+{(agent.capabilities_json ?? []).length - 4}</span>
        )}
      </div>
      <div className="mt-3 flex items-center justify-between border-t border-ink-700 pt-3 text-xs">
        <span className="text-slate-500">{agent.tasks_completed} tasks completed</span>
        <span
          className={`inline-flex items-center rounded-lg px-2 py-0.5 font-mono ring-1 ring-inset ${color.bg} ${color.text} ${color.ring}`}
        >
          {agent.performance_score.toFixed(1)}
        </span>
      </div>
    </Link>
  );
}

export function AgentArchitecture({ agents }: { agents: Agent[] }) {
  return (
    <section className="panel">
      <header className="panel-header">
        <h2 className="text-sm font-semibold tracking-wide text-slate-300">
          Configured Agent Architecture
        </h2>
        <span className="text-xs text-slate-500">Directory-level grouping · not real-time messaging</span>
      </header>
      <div className="space-y-6 p-4">
        {TIER_ORDER.map((tier) => {
          const members = agents.filter((a) => groupTier(a.agent_id) === tier);
          if (members.length === 0) return null;
          return (
            <div key={tier}>
              <p className="mb-2 text-[10px] font-semibold uppercase tracking-widest text-slate-500">
                {tier} · {members.length}
              </p>
              <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-5">
                {members.map((agent) => (
                  <AgentCard key={agent.id} agent={agent} />
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}