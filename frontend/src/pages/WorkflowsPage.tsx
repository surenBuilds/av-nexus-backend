import { Link } from "react-router-dom";
import {
  Badge,
  EmptyState,
  ErrorState,
  Spinner,
  STATUS_TONE_CLASSES,
} from "../components/ui";
import { listWorkflows } from "../lib/api/workflows";
import { useFetch } from "../lib/hooks/useFetch";
import { formatRelative, statusLabel, statusTone } from "../lib/utils/format";
import type { WorkflowSnapshot } from "../lib/types/domain";

export default function WorkflowsPage() {
  const { data, loading, error, refetch } = useFetch(listWorkflows);
  const workflows = data ?? [];

  return (
    <div className="space-y-6">
      <header className="flex items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-100">Workflows</h1>
          <p className="text-sm text-slate-500">
            Multi-agent pipelines that turn an objective into an approval-ready report
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            type="button"
            className="btn btn-ghost"
            onClick={() => void refetch()}
            disabled={loading}
          >
            Refresh
          </button>
          <Link to="/workflows/new" className="btn btn-primary">
            New workflow
          </Link>
        </div>
      </header>

      {loading && !workflows.length ? (
        <Spinner label="Loading workflows…" />
      ) : error && !workflows.length ? (
        <ErrorState message={error.message} onRetry={() => void refetch()} />
      ) : workflows.length === 0 ? (
        <section className="panel">
          <EmptyState
            title="No workflows yet"
            description="Kick one off from the objective bar on the command center, or create a new workflow."
          />
        </section>
      ) : (
        <section className="panel">
          <ul className="divide-y divide-ink-700">
            {workflows.map((wf: WorkflowSnapshot) => (
              <li
                key={wf.id}
                className="flex flex-col gap-2 px-4 py-4 lg:flex-row lg:items-center lg:justify-between"
              >
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge tone={STATUS_TONE_CLASSES[statusTone(wf.status)] ?? STATUS_TONE_CLASSES.muted}>
                      {statusLabel(wf.status)}
                    </Badge>
                    <Link
                      to={`/workflows/${wf.id}`}
                      className="text-sm font-medium text-slate-200 hover:text-accent"
                    >
                      {wf.name}
                    </Link>
                  </div>
                  <p className="mt-1 line-clamp-2 text-xs text-slate-500">{wf.objective}</p>
                </div>
                <div className="flex shrink-0 items-center gap-4 text-xs text-slate-500">
                  <span className="capitalize">{wf.workflow_type.replace(/_/g, " ")}</span>
                  <span>
                    {wf.current_step}/{wf.total_steps} steps
                  </span>
                  <span>{formatRelative(wf.created_at)}</span>
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}