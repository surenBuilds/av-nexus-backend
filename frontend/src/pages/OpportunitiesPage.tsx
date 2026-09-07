import { Badge, EmptyState, ErrorState, Spinner, STATUS_TONE_CLASSES } from "../components/ui";
import { listOpportunities } from "../lib/api/data";
import { useFetch } from "../lib/hooks/useFetch";
import { formatRelative, scoreColor, statusLabel, statusTone } from "../lib/utils/format";

export default function OpportunitiesPage() {
  const { data, loading, error, refetch } = useFetch(listOpportunities);

  return (
    <div className="space-y-6">
      <header className="flex items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-100">Opportunities</h1>
          <p className="text-sm text-slate-500">Portfolio of business opportunities under evaluation</p>
        </div>
        <button type="button" className="btn btn-ghost" onClick={() => void refetch()} disabled={loading}>
          Refresh
        </button>
      </header>

      {loading && !data ? (
        <Spinner label="Loading opportunities…" />
      ) : error && !data ? (
        <ErrorState message={error.message} onRetry={() => void refetch()} />
      ) : !data || data.length === 0 ? (
        <EmptyState title="No opportunities yet" description="Opportunities appear after evaluation runs." />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[720px] text-left text-sm">
            <thead className="border-b border-ink-700 text-xs uppercase tracking-wider text-slate-500">
              <tr>
                <th className="px-4 py-2 font-medium">Title</th>
                <th className="px-4 py-2 font-medium">Category</th>
                <th className="px-4 py-2 font-medium">Score</th>
                <th className="px-4 py-2 font-medium">Market</th>
                <th className="px-4 py-2 font-medium">Growth</th>
                <th className="px-4 py-2 font-medium">Status</th>
                <th className="px-4 py-2 font-medium">Created</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-ink-700">
              {data.map((o) => {
                const color = scoreColor(o.opportunity_score);
                return (
                  <tr key={o.id}>
                    <td className="px-4 py-3">
                      <p className="font-medium text-slate-200">{o.title}</p>
                      {o.description && (
                        <p className="line-clamp-1 text-xs text-slate-500">{o.description}</p>
                      )}
                    </td>
                    <td className="px-4 py-3 text-slate-400">{o.category || "—"}</td>
                    <td className="px-4 py-3">
                      <span
                        className={`inline-flex items-center rounded-lg px-2 py-1 font-mono text-sm ring-1 ring-inset ${color.bg} ${color.text} ${color.ring}`}
                      >
                        {o.opportunity_score.toFixed(0)}
                      </span>
                    </td>
                    <td className="px-4 py-3 font-mono text-slate-300">{o.market_potential.toFixed(0)}</td>
                    <td className="px-4 py-3 font-mono text-slate-300">{o.growth_rate.toFixed(0)}</td>
                    <td className="px-4 py-3">
                      <Badge tone={STATUS_TONE_CLASSES[statusTone(o.status)] ?? STATUS_TONE_CLASSES.muted}>
                        {statusLabel(o.status)}
                      </Badge>
                    </td>
                    <td className="px-4 py-3 text-slate-500">{formatRelative(o.created_at)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}