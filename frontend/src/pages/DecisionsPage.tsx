import { Badge, EmptyState, ErrorState, Spinner, STATUS_TONE_CLASSES } from "../components/ui";
import { listDecisions } from "../lib/api/data";
import { useFetch } from "../lib/hooks/useFetch";
import { formatRelative, statusLabel, statusTone } from "../lib/utils/format";

export default function DecisionsPage() {
  const { data, loading, error, refetch } = useFetch(listDecisions);

  return (
    <div className="space-y-6">
      <header className="flex items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-100">Decisions</h1>
          <p className="text-sm text-slate-500">Strategic decisions recorded by the operating system</p>
        </div>
        <button type="button" className="btn btn-ghost" onClick={() => void refetch()} disabled={loading}>
          Refresh
        </button>
      </header>

      {loading && !data ? (
        <Spinner label="Loading decisions…" />
      ) : error && !data ? (
        <ErrorState message={error.message} onRetry={() => void refetch()} />
      ) : !data || data.length === 0 ? (
        <EmptyState title="No decisions recorded" description="Pipeline evaluations record decisions automatically." />
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {data.map((d) => (
            <article key={d.id} className="panel p-4">
              <div className="flex items-start justify-between gap-3">
                <h2 className="text-sm font-semibold text-slate-100">{d.title}</h2>
                <Badge tone={STATUS_TONE_CLASSES[statusTone(d.status)] ?? STATUS_TONE_CLASSES.muted}>
                  {statusLabel(d.status)}
                </Badge>
              </div>
              <p className="mt-1 text-xs text-slate-500">
                {d.decision_type} · risk {d.risk_level}
              </p>
              {d.reason && <p className="mt-3 text-xs leading-relaxed text-slate-400">{d.reason}</p>}
              <dl className="mt-4 grid grid-cols-2 gap-3 border-t border-ink-700 pt-3 text-xs">
                <div>
                  <dt className="text-slate-500">Confidence</dt>
                  <dd className="mt-0.5 font-mono text-slate-200">{(d.confidence * 100).toFixed(0)}%</dd>
                </div>
                <div>
                  <dt className="text-slate-500">Agents involved</dt>
                  <dd className="mt-0.5 text-slate-300">
                    {d.agents_involved_json.length || "—"}
                  </dd>
                </div>
              </dl>
              <p className="mt-3 border-t border-ink-700 pt-3 text-xs text-slate-500">
                Approved {formatRelative(d.approved_at)}
              </p>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}