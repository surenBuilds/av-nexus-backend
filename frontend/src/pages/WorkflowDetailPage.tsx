import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  Badge,
  EmptyState,
  ErrorState,
  Skeleton,
  Spinner,
  STATUS_TONE_CLASSES,
} from "../components/ui";
import { decideApproval } from "../lib/api/data";
import {
  cancelWorkflow,
  getWorkflowResult,
  getWorkflowTrace,
  resumeWorkflow,
  startWorkflow,
  WORKFLOW_ACTIVE,
  WORKFLOW_TERMINAL,
} from "../lib/api/workflows";
import { useFetch } from "../lib/hooks/useFetch";
import { copyToClipboard } from "../lib/utils/clipboard";
import { formatDateTime, formatRelative, statusLabel, statusTone } from "../lib/utils/format";
import type {
  WorkflowSnapshot,
  WorkflowStepSnapshot,
  WorkflowTrace,
} from "../lib/types/domain";

function recTone(status: string): string {
  return STATUS_TONE_CLASSES[statusTone(status)] ?? STATUS_TONE_CLASSES.muted;
}

function recommendationTone(recommendation: string): string {
  if (recommendation === "BUILD" || recommendation === "ENTER") return STATUS_TONE_CLASSES.success;
  if (recommendation === "VALIDATE_FURTHER") return STATUS_TONE_CLASSES.warn;
  return STATUS_TONE_CLASSES.muted;
}

function Stepper({ steps }: { steps: WorkflowStepSnapshot[] }) {
  return (
    <ol className="space-y-0">
      {steps.map((step, idx) => (
        <li key={step.id} className="flex gap-3">
          <div className="flex flex-col items-center">
            <span
              className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-semibold ring-1 ring-inset ${
                step.status === "COMPLETED"
                  ? "bg-emerald-500/15 text-emerald-300 ring-emerald-500/40"
                  : step.status === "RUNNING" || step.status === "WAITING"
                    ? "bg-amber-500/15 text-amber-300 ring-amber-500/40"
                    : step.status === "FAILED"
                      ? "bg-red-500/15 text-red-300 ring-red-500/40"
                      : "bg-ink-700 text-slate-400 ring-ink-600"
              }`}
            >
              {idx + 1}
            </span>
            {idx < steps.length - 1 && <span className="my-1 w-px flex-1 bg-ink-700" />}
          </div>
          <div className="min-w-0 flex-1 pb-6">
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone={recTone(step.status)}>{statusLabel(step.status)}</Badge>
              <span className="text-sm font-medium text-slate-200">{step.name}</span>
              <span className="text-xs text-slate-500">by {step.agent_name}</span>
              {step.approval_level > 1 && (
                <Badge tone={STATUS_TONE_CLASSES.warn}>L{step.approval_level} gate</Badge>
              )}
            </div>
            <p className="mt-1 text-xs text-slate-500">{step.goal}</p>
            {step.task_ref && <p className="mt-0.5 font-mono text-[11px] text-slate-600">{step.task_ref}</p>}
            {step.error && <p className="mt-1 text-xs text-red-300">Error: {step.error}</p>}
            {step.output_summary_json && Object.keys(step.output_summary_json).length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1.5">
                {Object.entries(step.output_summary_json).map(([key, value]) => (
                  <span
                    key={key}
                    className="rounded bg-ink-800 px-1.5 py-0.5 font-mono text-[11px] text-slate-300"
                  >
                    {key}: {String(value)}
                  </span>
                ))}
              </div>
            )}
            {step.started_at && (
              <p className="mt-1 text-[11px] text-slate-600">
                {formatDateTime(step.started_at)}
                {step.ended_at ? ` → ${formatDateTime(step.ended_at)}` : ""}
              </p>
            )}
          </div>
        </li>
      ))}
    </ol>
  );
}

function DetailKey({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <dt className="text-xs text-slate-500">{label}</dt>
      <dd className="mt-1 text-sm text-slate-200">{value}</dd>
    </div>
  );
}

function downloadReport(resultId: string, reportMd: string): void {
  const blob = new Blob([reportMd], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `workflow-report-${resultId.slice(0, 8)}.md`;
  anchor.click();
  URL.revokeObjectURL(url);
}

export default function WorkflowDetailPage() {
  const { workflowId = "" } = useParams<{ workflowId: string }>();
  const traceState = useFetch(() => getWorkflowTrace(workflowId), [workflowId]);
  const resultState = useFetch(() => getWorkflowResult(workflowId), [workflowId]);
  const [message, setMessage] = useState<{ tone: "success" | "danger"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const trace: WorkflowTrace | null = traceState.data;
  const wf: WorkflowSnapshot | null = trace?.workflow ?? null;
  const active = Boolean(wf && WORKFLOW_ACTIVE.has(wf.status) && !wf.cancel_requested);

  useEffect(() => {
    if (!active) return;
    const handle = window.setInterval(() => {
      void traceState.refetch();
      void resultState.refetch();
    }, 2000);
    return () => window.clearInterval(handle);
    // traceState/resultState.refetch are stable; active is derived from fetched status
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, workflowId]);

  const runAction = async (action: () => Promise<unknown>, okText: string) => {
    setBusy(true);
    setMessage(null);
    try {
      await action();
      setMessage({ tone: "success", text: okText });
      await traceState.refetch();
    } catch (err) {
      setMessage({ tone: "danger", text: err instanceof Error ? err.message : String(err) });
    } finally {
      setBusy(false);
    }
  };

  const handleDecision = async (
    approvalId: string,
    decision: "approve" | "reject",
  ): Promise<void> => {
    if (!wf) return;
    setBusy(true);
    setMessage(null);
    try {
      await decideApproval(approvalId, decision, "decided from workflow view");
      setMessage({
        tone: decision === "approve" ? "success" : "danger",
        text: `${decision === "approve" ? "Approved" : "Rejected"} the workflow gate.`,
      });
      await traceState.refetch();
    } catch (err) {
      setMessage({ tone: "danger", text: err instanceof Error ? err.message : String(err) });
    } finally {
      setBusy(false);
    }
  };

  if (traceState.loading && !trace) {
    return (
      <div className="space-y-6">
        <div className="h-8 w-64 animate-pulse rounded-xl bg-ink-800" />
        <Skeleton className="h-40 w-full" />
        <Spinner label="Loading workflow trace…" />
      </div>
    );
  }

  if (traceState.error && !trace) {
    return <ErrorState message={traceState.error.message} onRetry={() => void traceState.refetch()} />;
  }

  if (!wf || !trace) return null;

  const pendingApprovals = trace.approvals.filter((a) => a.status === "pending");
  const terminal = WORKFLOW_TERMINAL.has(wf.status);
  const steps = trace.steps;

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2 text-sm text-slate-500">
        <Link to="/workflows" className="hover:text-accent">
          Workflows
        </Link>
        <span aria-hidden="true">/</span>
        <span className="text-slate-300">{wf.name}</span>
      </div>

      <header className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-xl font-semibold text-slate-100">{wf.name}</h1>
            <Badge tone={recTone(wf.status)}>{statusLabel(wf.status)}</Badge>
            <Badge tone={STATUS_TONE_CLASSES.muted}>{wf.priority}</Badge>
          </div>
          <p className="mt-1 text-sm text-slate-400">{wf.objective}</p>
          <p className="mt-1 text-xs text-slate-500">
            {wf.workflow_type.replace(/_/g, " ")} · created {formatRelative(wf.created_at)}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button type="button" className="btn btn-ghost" onClick={() => void traceState.refetch()} disabled={busy}>
            Refresh
          </button>
          {(wf.status === "CREATED" || wf.status === "PLANNING") && (
            <button
              type="button"
              className="btn btn-primary"
              disabled={busy}
              onClick={() => void runAction(() => startWorkflow(wf.id), "Workflow started.")}
            >
              Start
            </button>
          )}
          {wf.status === "FAILED" && !wf.cancel_requested && (
            <button
              type="button"
              className="btn btn-primary"
              disabled={busy}
              onClick={() => void runAction(() => resumeWorkflow(wf.id), "Workflow resumed.")}
            >
              Resume
            </button>
          )}
          {active && (
            <button
              type="button"
              className="btn btn-danger"
              disabled={busy}
              onClick={() => void runAction(() => cancelWorkflow(wf.id), "Cancellation requested.")}
            >
              Cancel
            </button>
          )}
        </div>
      </header>

      {message && (
        <div
          role="status"
          className={`rounded-lg px-3 py-2 text-sm ring-1 ring-inset ${
            message.tone === "success"
              ? "bg-emerald-500/10 text-emerald-300 ring-emerald-500/40"
              : "bg-red-500/10 text-red-300 ring-red-500/40"
          }`}
        >
          {message.text}
        </div>
      )}

      {!terminal && (
        <div className="rounded-lg bg-amber-500/10 px-3 py-2 text-sm text-amber-300 ring-1 ring-inset ring-amber-500/40" role="status">
          Live trace — refreshing every {2}s until the workflow reaches a terminal state.
        </div>
      )}

      <dl className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <DetailKey label="Progress" value={`${wf.current_step} / ${wf.total_steps} steps`} />
        <DetailKey label="Confidence" value={wf.confidence === 0 && !terminal ? "—" : `${wf.confidence.toFixed(1)}`} />
        <DetailKey label="Started" value={formatDateTime(wf.started_at)} />
        <DetailKey label="Completed" value={formatDateTime(wf.completed_at)} />
      </dl>
      {wf.error && (
        <div className="rounded-lg bg-red-500/10 px-3 py-2 text-sm text-red-300 ring-1 ring-inset ring-red-500/40">
          {wf.error}
        </div>
      )}

      <section className="panel">
        <header className="panel-header">
          <h2 className="text-sm font-semibold tracking-wide text-slate-300">Agent pipeline</h2>
        </header>
        {steps.length === 0 ? (
          <EmptyState title="No steps planned yet" description="Start the workflow to generate the task graph." />
        ) : (
          <div className="px-4 py-4">
            <Stepper steps={steps} />
          </div>
        )}
      </section>

      {pendingApprovals.length > 0 && (
        <section className="panel">
          <header className="panel-header">
            <h2 className="text-sm font-semibold tracking-wide text-slate-300">Awaiting your decision</h2>
            <Badge tone={STATUS_TONE_CLASSES.warn}>{pendingApprovals.length} pending</Badge>
          </header>
          <ul className="divide-y divide-ink-700">
            {pendingApprovals.map((a) => (
              <li key={String(a.id)} className="flex flex-col gap-2 px-4 py-3 lg:flex-row lg:items-center lg:justify-between">
                <div>
                  <p className="text-sm font-medium text-slate-200">
                    {String(a.entity_type ?? "decision")} · level L{String(a.level)}
                  </p>
                  <p className="text-xs text-slate-500">requested by {String(a.requested_by ?? "—")}</p>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    className="btn btn-primary px-2.5 py-1 text-xs"
                    disabled={busy}
                    onClick={() => void handleDecision(String(a.id), "approve")}
                  >
                    Approve
                  </button>
                  <button
                    type="button"
                    className="btn btn-danger px-2.5 py-1 text-xs"
                    disabled={busy}
                    onClick={() => void handleDecision(String(a.id), "reject")}
                  >
                    Reject
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="panel">
        <header className="panel-header">
          <h2 className="text-sm font-semibold tracking-wide text-slate-300">Execution traces</h2>
        </header>
        {trace.runs.length === 0 ? (
          <div className="px-4 py-6 text-sm text-slate-500">No agent runs recorded yet.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-ink-700 text-xs uppercase tracking-wider text-slate-500">
                  <th className="px-4 py-2">Run</th>
                  <th className="px-4 py-2">Step</th>
                  <th className="px-4 py-2">Agent</th>
                  <th className="px-4 py-2">Status</th>
                  <th className="px-4 py-2 text-right">Tokens</th>
                  <th className="px-4 py-2 text-right">Cost</th>
                </tr>
              </thead>
              <tbody>
                {trace.runs.map((run) => (
                  <tr key={run.task_id} className="border-b border-ink-800/60">
                    <td className="px-4 py-2 font-mono text-xs text-slate-400">{run.task_ref}</td>
                    <td className="px-4 py-2 text-slate-300">{run.step_name}</td>
                    <td className="px-4 py-2 text-slate-300">{run.agent_id ?? "—"}</td>
                    <td className="px-4 py-2">
                      <Badge tone={recTone(run.status)}>{statusLabel(run.status)}</Badge>
                    </td>
                    <td className="px-4 py-2 text-right font-mono text-xs text-slate-400">
                      {run.tokens_in + run.tokens_out}
                    </td>
                    <td className="px-4 py-2 text-right font-mono text-xs text-slate-400">
                      ${run.cost_usd.toFixed(4)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {trace.messages.length > 0 && (
          <div className="border-t border-ink-700 px-4 py-3">
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-500">Agent messages</h3>
            <ul className="space-y-1.5">
              {trace.messages.map((m) => (
                <li key={String(m.id)} className="text-xs text-slate-400">
                  <span className="font-mono text-slate-500">
                    {String(m.from_agent ?? "")} → {String(m.to_agent ?? "")}
                  </span>
                  : {String(m.message_type ?? "note")}
                  {"summary" in m && m.summary ? ` — ${String(m.summary)}` : ""}
                </li>
              ))}
            </ul>
          </div>
        )}
      </section>

      <section className="panel">
        <header className="panel-header">
          <h2 className="text-sm font-semibold tracking-wide text-slate-300">Events</h2>
        </header>
        {trace.events.length === 0 ? (
          <div className="px-4 py-6 text-sm text-slate-500">No events recorded yet.</div>
        ) : (
          <ul className="divide-y divide-ink-700">
            {[...trace.events].reverse().slice(0, 60).map((event) => (
              <li key={event.id} className="flex items-center gap-3 px-4 py-2.5 text-xs">
                <Badge tone={recTone(event.event_type)}>{event.event_type.replace(/_/g, " ")}</Badge>
                <span className="min-w-0 flex-1 truncate text-slate-400">{event.message}</span>
                <span className="shrink-0 text-slate-600">{formatRelative(event.created_at)}</span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="panel">
        <header className="panel-header">
          <h2 className="text-sm font-semibold tracking-wide text-slate-300">Final report</h2>
          {resultState.data && (
            <div className="flex items-center gap-2">
              <button
                type="button"
                className="btn btn-ghost px-2 py-1 text-xs"
                onClick={() => {
                  void copyToClipboard(resultState.data!.report_md)
                    .then(() => setMessage({ tone: "success", text: "Report copied to clipboard." }))
                    .catch(() => setMessage({ tone: "danger", text: "Could not copy report." }));
                }}
              >
                COPY REPORT
              </button>
              <button
                type="button"
                className="btn btn-ghost px-2 py-1 text-xs"
                onClick={() => downloadReport(resultState.data!.id, resultState.data!.report_md)}
              >
                EXPORT JSON
              </button>
            </div>
          )}
        </header>
        {!resultState.data ? (
          resultState.loading && !terminal ? (
            <Spinner label="Rendering report…" />
          ) : (
            <EmptyState
              title="No report yet"
              description="The final synthesis report is generated once the workflow completes."
            />
          )
        ) : (
          <div className="space-y-4 px-4 py-4">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm font-medium text-slate-300">Recommendation</span>
              <Badge tone={recommendationTone(resultState.data.recommendation)}>
                {resultState.data.recommendation}
              </Badge>
              <Badge tone={STATUS_TONE_CLASSES.muted}>
                confidence {resultState.data.confidence.toFixed(1)}
              </Badge>
            </div>
            <p className="text-sm text-slate-300">{resultState.data.summary}</p>
            <pre className="max-h-[36rem] overflow-auto rounded-lg bg-ink-900 p-4 font-mono text-xs leading-relaxed text-slate-300 ring-1 ring-inset ring-ink-700">
              {resultState.data.report_md}
            </pre>
          </div>
        )}
      </section>
    </div>
  );
}