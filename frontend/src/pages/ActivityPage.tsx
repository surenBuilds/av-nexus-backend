import { EmptyState, ErrorState, Spinner } from "../components/ui";
import { listActivity } from "../lib/api/data";
import { useFetch } from "../lib/hooks/useFetch";
import { formatRelative, statusLabel } from "../lib/utils/format";

const TONE_DOT: Record<string, string> = {
  RUNNING: "bg-amber-400",
  QUEUED: "bg-amber-400",
  COMPLETED: "bg-emerald-400",
  FAILED: "bg-red-400",
  CANCELLED: "bg-slate-400",
};

export default function ActivityPage() {
  const { data, loading, error, refetch } = useFetch(listActivity);

  return (
    <div className="space-y-6">
      <header className="flex items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-100">Activity</h1>
          <p className="text-sm text-slate-500">Recent agent executions across the organization</p>
        </div>
        <button type="button" className="btn btn-ghost" onClick={() => void refetch()} disabled={loading}>
          Refresh
        </button>
      </header>

      {loading && !data ? (
        <Spinner label="Loading activity…" />
      ) : error && !data ? (
        <ErrorState message={error.message} onRetry={() => void refetch()} />
      ) : !data || data.length === 0 ? (
        <EmptyState title="No activity yet" description="Agent runs will appear here as work is executed." />
      ) : (
        <ol className="space-y-2" aria-label="Recent activity">
          {data.map((item) => (
            <li key={item.id} className="panel flex items-center gap-3 px-4 py-3">
              <span
                aria-hidden="true"
                className={`h-2 w-2 shrink-0 rounded-full ${TONE_DOT[item.status] ?? "bg-slate-500"}`}
              />
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm text-slate-200">
                  <span className="font-medium text-accent">{item.actor}</span>
                  <span className="mx-1.5 text-slate-500">·</span>
                  {item.action}
                </p>
                <p className="text-xs text-slate-500">
                  <span className="font-mono">{item.entity}</span> · {statusLabel(item.status)}
                </p>
              </div>
              <time className="shrink-0 text-xs text-slate-500" dateTime={item.timestamp}>
                {formatRelative(item.timestamp)}
              </time>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}