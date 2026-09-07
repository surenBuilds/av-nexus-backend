import { Badge, EmptyState, ErrorState, Spinner } from "../components/ui";
import { listCompanies } from "../lib/api/data";
import { useFetch } from "../lib/hooks/useFetch";
import { healthTone, scoreColor } from "../lib/utils/format";

export default function CompaniesPage() {
  const { data, loading, error, refetch } = useFetch(listCompanies);

  return (
    <div className="space-y-6">
      <header className="flex items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-100">Companies</h1>
          <p className="text-sm text-slate-500">Portfolio companies tracked by the operating system</p>
        </div>
        <button type="button" className="btn btn-ghost" onClick={() => void refetch()} disabled={loading}>
          Refresh
        </button>
      </header>

      {loading && !data ? (
        <Spinner label="Loading companies…" />
      ) : error && !data ? (
        <ErrorState message={error.message} onRetry={() => void refetch()} />
      ) : !data || data.length === 0 ? (
        <EmptyState title="No companies yet" description="Companies appear once added to the portfolio." />
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {data.map((c) => {
            const hasScore = c.business_health_score > 0;
            const color = scoreColor(hasScore ? c.business_health_score : 0);
            const tone = hasScore ? "select-none" : "";
            return (
              <article key={c.id} className="panel p-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <h2 className="text-sm font-semibold text-slate-100">{c.name}</h2>
                    <p className="text-xs text-slate-500">
                      {c.industry} · {c.stage}
                    </p>
                  </div>
                  <span className={tone}>
                    {hasScore ? (
                      <span className="flex items-center gap-1">
                        <span
                          className={`rounded px-2 py-1 font-mono text-sm ring-1 ring-inset ${color.bg} ${color.text} ${color.ring}`}
                        >
                          {c.business_health_score.toFixed(0)}
                        </span>
                        <span className="text-xs text-slate-500">health</span>
                      </span>
                    ) : (
                      <span className="text-xs text-slate-600">Health data unavailable</span>
                    )}
                  </span>
                </div>
                {c.mission && <p className="mt-3 text-xs text-slate-400">{c.mission}</p>}
                <div className="mt-3 flex items-center justify-between border-t border-ink-700 pt-3">
                  <span className="font-mono text-xs text-slate-500">{c.slug}</span>
                  <Badge tone={getHealthBadge(c.business_health_score)}>{getHealthLabel(c.business_health_score)}</Badge>
                </div>
              </article>
            );
          })}
        </div>
      )}
    </div>
  );
}

function getHealthLabel(score: number): string {
  if (score <= 0) return "UNSCORED";
  if (score >= 70) return "GREEN";
  if (score >= 45) return "YELLOW";
  return "RED";
}

function getHealthBadge(score: number): string {
  const tone = healthTone(score > 0 ? score : undefined);
  const map: Record<string, string> = {
    success: "bg-emerald-500/15 text-emerald-300 ring-emerald-500/40",
    warn: "bg-amber-500/15 text-amber-300 ring-amber-500/40",
    danger: "bg-red-500/15 text-red-300 ring-red-500/40",
    muted: "bg-slate-500/15 text-slate-300 ring-slate-500/40",
  };
  return map[tone];
}