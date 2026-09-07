import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError } from "../lib/api/client";
import { createWorkflow } from "../lib/api/workflows";
import { listCompanies } from "../lib/api/data";
import { Spinner } from "../components/ui";
import type { Company } from "../lib/types/domain";

export default function NewWorkflowPage() {
  const navigate = useNavigate();
  const [objective, setObjective] = useState("");
  const [priority, setPriority] = useState("medium");
  const [industryFocus, setIndustryFocus] = useState("");
  const [companyId, setCompanyId] = useState("");
  const [companies, setCompanies] = useState<Company[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void listCompanies()
      .then(setCompanies)
      .catch(() => setCompanies([]));
  }, []);

  const canSubmit = objective.trim().length >= 3 && !submitting;

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!canSubmit) return;
    setSubmitting(true);
    setError(null);
    try {
      const context: Record<string, string> = {};
      if (industryFocus.trim()) context.industry_focus = industryFocus.trim();
      const wf = await createWorkflow({
        objective: objective.trim(),
        workflow_type: "opportunity_discovery",
        company_id: companyId || null,
        priority,
        context,
      });
      navigate(`/workflows/${wf.id}`);
    } catch (err) {
      setError(err instanceof Error || err instanceof ApiError ? err.message : String(err));
      setSubmitting(false);
    }
  };

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <header>
        <h1 className="text-xl font-semibold text-slate-100">New workflow</h1>
        <p className="text-sm text-slate-500">
          Define an objective and the agent network will plan, execute, and report on it.
        </p>
      </header>

      <form onSubmit={(e) => void handleSubmit(e)} className="panel space-y-4 p-5">
        <label className="block">
          <span className="text-sm font-medium text-slate-300">Objective</span>
          <textarea
            rows={4}
            className="input mt-1.5 w-full"
            placeholder="e.g. Expand our smart construction offering into commercial retrofit markets"
            value={objective}
            onChange={(e) => setObjective(e.target.value)}
            required
          />
        </label>

        <div className="grid gap-4 md:grid-cols-2">
          <label className="block">
            <span className="text-sm font-medium text-slate-300">Priority</span>
            <select
              className="input mt-1.5 w-full"
              value={priority}
              onChange={(e) => setPriority(e.target.value)}
            >
              <option value="low">Low</option>
              <option value="medium">Medium</option>
              <option value="high">High</option>
              <option value="critical">Critical</option>
            </select>
          </label>

          <label className="block">
            <span className="text-sm font-medium text-slate-300">Industry focus</span>
            <input
              className="input mt-1.5 w-full"
              placeholder="e.g. commercial_real_estate"
              value={industryFocus}
              onChange={(e) => setIndustryFocus(e.target.value)}
            />
          </label>
        </div>

        <label className="block">
          <span className="text-sm font-medium text-slate-300">
            Company context <span className="text-slate-600">(optional)</span>
          </span>
          <select
            className="input mt-1.5 w-full"
            value={companyId}
            onChange={(e) => setCompanyId(e.target.value)}
          >
            <option value="">None — the objective stands alone</option>
            {companies.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name} · {c.industry}
              </option>
            ))}
          </select>
        </label>

        {error && (
          <div role="alert" className="rounded-lg bg-red-500/10 px-3 py-2 text-sm text-red-300 ring-1 ring-inset ring-red-500/40">
            {error}
          </div>
        )}

        <div className="flex items-center justify-end gap-3 pt-2">
          <button
            type="button"
            className="btn btn-ghost"
            onClick={() => navigate("/workflows")}
            disabled={submitting}
          >
            Cancel
          </button>
          <button type="submit" className="btn btn-primary" disabled={!canSubmit}>
            {submitting ? (
              <span className="inline-flex items-center gap-2">
                <Spinner /> Creating…
              </span>
            ) : (
              "Create workflow"
            )}
          </button>
        </div>
      </form>
    </div>
  );
}