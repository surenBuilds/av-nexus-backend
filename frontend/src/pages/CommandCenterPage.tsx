import { getDashboard } from "../lib/api/data";
import { useFetch } from "../lib/hooks/useFetch";
import { Cards } from "../features/command-center/index";

export default function CommandCenterPage() {
  const { data, loading, error, refetch } = useFetch(getDashboard);

  return (
    <div className="space-y-6">
      <header className="flex items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-100">Command Center</h1>
          <p className="text-sm text-slate-500">
            Live operational view{data ? ` · ${data.org_name}` : ""}
          </p>
        </div>
        <button
          type="button"
          className="btn btn-ghost"
          onClick={() => void refetch()}
          disabled={loading}
        >
          {loading ? "Refreshing…" : "Refresh"}
        </button>
      </header>

      <Cards data={data} loading={loading} error={error} onRetry={() => void refetch()} />
    </div>
  );
}