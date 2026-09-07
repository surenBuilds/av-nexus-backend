import { listAgents } from "../lib/api/agents";
import { useFetch } from "../lib/hooks/useFetch";
import {
  Badge,
  EmptyState,
  ErrorState,
  Spinner,
  STATUS_TONE_CLASSES,
  StatCard,
} from "../components/ui";
import { AgentArchitecture, AgentCard } from "../features/agent-network/components";
import { statusLabel } from "../lib/utils/format";

export default function AgentsPage() {
  const { data: agents, loading, error, refetch } = useFetch(listAgents);

  if (loading && !agents) {
    return (
      <div className="space-y-6">
        <div className="h-24 animate-pulse rounded-xl bg-ink-800" />
        <Spinner label="Loading agent network…" />
      </div>
    );
  }

  if (error && !agents) {
    return <ErrorState message={error.message} onRetry={() => void refetch()} />;
  }

  if (!agents) return null;

  const active = agents.filter((a) => a.is_active).length;
  const idle = agents.filter((a) => a.status === "IDLE").length;

  return (
    <div className="space-y-6">
      <header className="flex items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-100">Agent Network</h1>
          <p className="text-sm text-slate-500">Registered workforce across the organization</p>
        </div>
        <button
          type="button"
          className="btn btn-ghost"
          onClick={() => void refetch()}
          disabled={loading}
        >
          Refresh
        </button>
      </header>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard label="Registered" value={agents.length} />
        <StatCard label="Active" value={active} hint={`${idle} idle`} />
        <StatCard
          label="Avg performance"
          value={
            agents.length
              ? (agents.reduce((sum, a) => sum + a.performance_score, 0) / agents.length).toFixed(1)
              : "—"
          }
          tone="text-accent"
        />
        <StatCard label="Total tasks completed" value={agents.reduce((s, a) => s + a.tasks_completed, 0)} />
      </div>

      {agents.length === 0 ? (
        <EmptyState title="No agents registered" description="Agents appear after registration." />
      ) : (
        <>
          <AgentArchitecture agents={agents} />
          <section className="panel">
            <header className="panel-header">
              <h2 className="text-sm font-semibold tracking-wide text-slate-300">
                All agents
              </h2>
              <Badge tone={STATUS_TONE_CLASSES.muted}>
                {agents.length} total · {active} active
              </Badge>
            </header>
            <div className="grid grid-cols-1 gap-4 p-4 sm:grid-cols-2 xl:grid-cols-3">
              {agents.map((agent) => (
                <AgentCard key={agent.id} agent={agent} />
              ))}
            </div>
          </section>
        </>
      )}

      {/* status legend for accessibility context */}
      <p className="text-xs text-slate-600">
        Agent statuses: {[...new Set(agents.map((a) => statusLabel(a.status)))].join(", ")}. Click an
        agent to open its detail view.
      </p>
    </div>
  );
}