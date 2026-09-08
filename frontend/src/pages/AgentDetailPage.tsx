import { useParams, Link } from "react-router-dom";
import {
  Badge,
  EmptyState,
  ErrorState,
  Spinner,
  STATUS_TONE_CLASSES,
} from "../components/ui";
import { getAgent, listAgentRuns, listAgentMessages, listTasks } from "../lib/api/agents";
import { useFetch } from "../lib/hooks/useFetch";
import { RunAgentPanel } from "../features/agent-run/RunAgentPanel";
import {
  formatDateTime,
  formatNumber,
  formatRelative,
  scoreColor,
  statusLabel,
  statusTone,
} from "../lib/utils/format";

export default function AgentDetailPage() {
  const { agentId = "" } = useParams<{ agentId: string }>();
  const agentState = useFetch(() => getAgent(agentId));
  const runsState = useFetch(() => listAgentRuns(agentId));
  const messagesState = useFetch(() => listAgentMessages(agentId));
  const tasksState = useFetch(() => {
    if (!agentState.data) return Promise.resolve([]);
    return listTasks(agentState.data.id);
  }, [agentState.data?.id]);

  const { data: agent, loading, error, refetch } = agentState;

  if (loading && !agent) {
    return (
      <div className="space-y-6">
        <div className="h-8 w-64 animate-pulse rounded-xl bg-ink-800" />
        <Spinner label="Loading agent…" />
      </div>
    );
  }

  if (error && !agent) {
    return <ErrorState message={error.message} onRetry={() => void refetch()} />;
  }

  if (!agent) return null;

  const tone = STATUS_TONE_CLASSES[statusTone(agent.status)] ?? STATUS_TONE_CLASSES.muted;
  const perf = scoreColor(agent.performance_score);
  const runs = runsState.data ?? [];
  const messages = messagesState.data ?? [];
  const tasks = tasksState.data ?? [];

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2 text-sm text-slate-500">
        <Link to="/agents" className="hover:text-accent">Agent Network</Link>
        <span aria-hidden="true">/</span>
        <span className="text-slate-300">{agent.name}</span>
      </div>

      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold text-slate-100">{agent.name}</h1>
          <p className="font-mono text-sm text-slate-500">{agent.agent_id}</p>
        </div>
        <div className="flex items-center gap-3">
          <Badge tone={tone}>{statusLabel(agent.status)}</Badge>
          <span
            className={`inline-flex items-center rounded-lg px-2.5 py-1 font-mono text-sm ring-1 ring-inset ${perf.bg} ${perf.text} ${perf.ring}`}
          >
            {agent.performance_score.toFixed(1)}
          </span>
        </div>
      </header>

      <section className="panel p-4">
        <dl className="grid gap-4 md:grid-cols-2">
          <div>
            <dt className="text-xs text-slate-500">Role</dt>
            <dd className="mt-1 text-sm text-slate-200">{agent.role}</dd>
          </div>
          <div>
            <dt className="text-xs text-slate-500">Status</dt>
            <dd className="mt-1 text-sm text-slate-200">
              {statusLabel(agent.status)} · {agent.is_active ? "Active" : "Inactive"}
            </dd>
          </div>
          <div className="md:col-span-2">
            <dt className="text-xs text-slate-500">Description</dt>
            <dd className="mt-1 text-sm leading-relaxed text-slate-300">
              {agent.description || "No description provided."}
            </dd>
          </div>
        </dl>
        <KeywordList title="Capabilities" items={agent.capabilities_json} />
        <KeywordList title="Tools" items={agent.tools_json} />
        <KeywordList title="Permissions" items={agent.permissions_json} />
      </section>

      <RunAgentPanel
        agentId={agent.id}
        agentName={agent.name}
        onRan={() => {
          void runsState.refetch();
          void messagesState.refetch();
          void tasksState.refetch();
        }}
      />

      <div className="grid gap-6 lg:grid-cols-2">
        <section className="panel">
          <header className="panel-header">
            <h2 className="text-sm font-semibold tracking-wide text-slate-300">Recent executions</h2>
          </header>
          {runsState.loading && !runs.length ? (
            <Spinner label="Loading runs…" />
          ) : runsState.error && !runs.length ? (
            <ErrorState message={runsState.error.message} onRetry={() => void runsState.refetch()} />
          ) : runs.length === 0 ? (
            <EmptyState title="No executions yet" description="Runs appear after the agent works on a task." />
          ) : (
            <ul className="divide-y divide-ink-700">
              {runs.map((run) => (
                <li key={run.id} className="px-4 py-3">
                  <div className="flex items-center justify-between gap-3">
                    <p className="truncate text-sm text-slate-200">
                      {run.task_title}
                      <span className="ml-2 font-mono text-xs text-slate-500">{run.task_ref}</span>
                    </p>
                    <Badge tone={STATUS_TONE_CLASSES[statusTone(run.status)] ?? STATUS_TONE_CLASSES.muted}>
                      {statusLabel(run.status)}
                    </Badge>
                  </div>
                  <p className="mt-1 text-xs text-slate-500">
                    {formatRelative(run.started_at)} · {formatNumber(run.tokens_in + run.tokens_out)} tokens ·
                    ${run.cost_usd.toFixed(2)}
                  </p>
                  {run.error && <p className="mt-1 text-xs text-red-300">Error: {run.error}</p>}
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="panel">
          <header className="panel-header">
            <h2 className="text-sm font-semibold tracking-wide text-slate-300">Recent messages</h2>
          </header>
          {messagesState.loading && !messages.length ? (
            <Spinner label="Loading messages…" />
          ) : messagesState.error && !messages.length ? (
            <ErrorState message={messagesState.error.message} onRetry={() => void messagesState.refetch()} />
          ) : messages.length === 0 ? (
            <EmptyState title="No messages yet" description="Agent-to-agent messages appear here." />
          ) : (
            <ul className="divide-y divide-ink-700">
              {messages.map((m) => (
                <li key={m.id} className="px-4 py-3">
                  <p className="text-sm text-slate-200">
                    <span className="font-mono text-xs text-accent">{m.from_agent}</span>
                    <span className="mx-1.5 text-slate-600">→</span>
                    <span className="font-mono text-xs text-accent">{m.to_agent}</span>
                  </p>
                  <p className="mt-1 text-xs text-slate-500">
                    {m.message_type} · {formatDateTime(m.sent_at)}
                  </p>
                  {m.payload_json && (
                    <pre className="mt-2 overflow-x-auto rounded-lg bg-ink-850 p-2 text-[10px] text-slate-400">
                      {JSON.stringify(m.payload_json, null, 2)}
                    </pre>
                  )}
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      <section className="panel">
        <header className="panel-header">
          <h2 className="text-sm font-semibold tracking-wide text-slate-300">Task history</h2>
        </header>
        {tasksState.loading && !tasks.length ? (
          <Spinner label="Loading tasks…" />
        ) : tasksState.error && !tasks.length ? (
          <ErrorState message={tasksState.error.message} onRetry={() => void tasksState.refetch()} />
        ) : tasks.length === 0 ? (
          <EmptyState title="No tasks assigned" description="Tasks routed to this agent will appear here." />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-ink-700 text-xs uppercase tracking-wider text-slate-500">
                <tr>
                  <th className="px-4 py-2 font-medium">Ref</th>
                  <th className="px-4 py-2 font-medium">Title</th>
                  <th className="px-4 py-2 font-medium">Status</th>
                  <th className="px-4 py-2 font-medium">Priority</th>
                  <th className="px-4 py-2 font-medium">Created</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-ink-700">
                {tasks.map((task) => (
                  <tr key={task.id}>
                    <td className="px-4 py-2 font-mono text-xs text-slate-500">{task.task_ref}</td>
                    <td className="px-4 py-2 text-slate-200">{task.title}</td>
                    <td className="px-4 py-2">
                      <Badge tone={STATUS_TONE_CLASSES[statusTone(task.status)] ?? STATUS_TONE_CLASSES.muted}>
                        {statusLabel(task.status)}
                      </Badge>
                    </td>
                    <td className="px-4 py-2 text-slate-400">{task.priority}</td>
                    <td className="px-4 py-2 text-slate-500">{formatRelative(task.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}

function KeywordList({ title, items }: { title: string; items: string[] }) {
  if (!items || items.length === 0) return null;
  return (
    <div className="mt-4">
      <p className="text-xs text-slate-500">{title}</p>
      <div className="mt-1.5 flex flex-wrap gap-1.5">
        {items.map((item) => (
          <span
            key={item}
            className="rounded-md bg-ink-800 px-2 py-0.5 font-mono text-[11px] text-slate-400 ring-1 ring-inset ring-ink-600"
          >
            {item}
          </span>
        ))}
      </div>
    </div>
  );
}