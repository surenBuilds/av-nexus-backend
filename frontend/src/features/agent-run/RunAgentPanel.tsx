import { useState } from "react";
import { Play, AlertCircle } from "lucide-react";
import { createTask, runTask } from "../../lib/api/tasks";
import { ApiError } from "../../lib/api/client";
import { Spinner } from "../../components/ui";
import type { Task, TaskRunResponse } from "../../lib/types/domain";

interface RunAgentPanelProps {
  agentId: string; // DB uuid, routes directly via owner_agent_id
  agentName: string;
  onRan?: (result: TaskRunResponse) => void;
}

const PLACEHOLDER_BY_HINT: Record<string, string> = {
  finance: '{\n  "revenue": 100000,\n  "expenses": 70000,\n  "cash": 50000,\n  "cogs": 40000\n}',
  marketing: '{\n  "audience": "Armenian SMB retailers",\n  "budget": 12000\n}',
  operations:
    '{\n  "projects": [\n    { "name": "Migration", "status": "delayed" }\n  ]\n}',
  sales:
    '{\n  "leads": [\n    { "name": "Acme Co", "budget": 5000, "fit": 70, "intent": 60 }\n  ]\n}',
};

/** A self-contained panel for running any registered agent ad hoc, outside
 * the fixed venture-evaluation workflow — the direct-execution path this
 * project already has via POST /tasks + POST /tasks/{id}/run, now exposed
 * through the UI instead of only being reachable by hand-crafting requests. */
export function RunAgentPanel({ agentId, agentName, onRan }: RunAgentPanelProps) {
  const [goal, setGoal] = useState("");
  const [inputText, setInputText] = useState("{}");
  const [jsonError, setJsonError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [apiError, setApiError] = useState<string | null>(null);
  const [lastResult, setLastResult] = useState<Task | null>(null);

  const placeholder = PLACEHOLDER_BY_HINT[agentId] ?? "{}";

  async function handleRun(): Promise<void> {
    setJsonError(null);
    setApiError(null);

    let parsedInputs: Record<string, unknown> = {};
    const trimmed = inputText.trim();
    if (trimmed.length > 0) {
      try {
        const parsed: unknown = JSON.parse(trimmed);
        if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
          throw new Error("Input must be a JSON object, e.g. {\"revenue\": 1000}");
        }
        parsedInputs = parsed as Record<string, unknown>;
      } catch (err) {
        setJsonError(err instanceof Error ? err.message : "Invalid JSON");
        return;
      }
    }

    if (!goal.trim()) {
      setJsonError("Goal is required.");
      return;
    }

    setSubmitting(true);
    try {
      const task = await createTask({
        title: goal.slice(0, 80),
        goal,
        owner_agent_id: agentId,
        input_json: parsedInputs,
      });
      const result = await runTask(task.id);
      setLastResult(result.task);
      onRan?.(result);
    } catch (err) {
      setApiError(err instanceof ApiError ? err.detail : "Failed to run agent");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="panel">
      <header className="panel-header">
        <h2 className="text-sm font-semibold tracking-wide text-slate-300">Run {agentName} now</h2>
      </header>
      <div className="space-y-4 p-4">
        <div>
          <label htmlFor="run-goal" className="text-xs text-slate-500">
            Goal
          </label>
          <input
            id="run-goal"
            type="text"
            value={goal}
            onChange={(e) => setGoal(e.target.value)}
            placeholder="e.g. Weekly financial health check"
            className="mt-1 w-full rounded-lg border border-ink-600 bg-ink-800 px-3 py-2 text-sm text-slate-200 placeholder:text-slate-600 focus:border-accent focus:outline-none"
            disabled={submitting}
          />
        </div>

        <div>
          <label htmlFor="run-inputs" className="text-xs text-slate-500">
            Inputs (JSON) — real data this agent should reason over. Leave as{" "}
            <code className="font-mono text-slate-400">{"{}"}</code> to run with no data (the agent
            will report honestly low confidence rather than invent numbers).
          </label>
          <textarea
            id="run-inputs"
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            placeholder={placeholder}
            rows={6}
            className="mt-1 w-full rounded-lg border border-ink-600 bg-ink-850 px-3 py-2 font-mono text-xs text-slate-200 placeholder:text-slate-600 focus:border-accent focus:outline-none"
            disabled={submitting}
          />
          {jsonError && (
            <p className="mt-1.5 flex items-center gap-1.5 text-xs text-red-300">
              <AlertCircle className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
              {jsonError}
            </p>
          )}
        </div>

        {apiError && (
          <p className="flex items-center gap-1.5 rounded-lg border border-red-900 bg-red-950/40 px-3 py-2 text-xs text-red-200">
            <AlertCircle className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
            {apiError}
          </p>
        )}

        <div className="flex items-center justify-end">
          <button
            type="button"
            className="btn btn-gradient"
            onClick={() => void handleRun()}
            disabled={submitting}
          >
            {submitting ? (
              <span className="inline-flex items-center gap-2">
                <Spinner /> Running…
              </span>
            ) : (
              <span className="inline-flex items-center gap-2">
                <Play className="h-3.5 w-3.5" aria-hidden="true" />
                Run now
              </span>
            )}
          </button>
        </div>

        {lastResult && (
          <div className="rounded-lg border border-ink-600 bg-ink-850 p-3">
            <div className="flex items-center justify-between">
              <span className="badge-mono">{lastResult.status}</span>
              <span className="text-xs text-slate-500">
                confidence {(lastResult.confidence * 100).toFixed(0)}%
              </span>
            </div>
            <pre className="mt-2 max-h-64 overflow-auto text-[11px] text-slate-300">
              {JSON.stringify(lastResult.output_json, null, 2)}
            </pre>
          </div>
        )}
      </div>
    </section>
  );
}
