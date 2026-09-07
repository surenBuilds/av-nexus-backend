import { useState } from "react";
import {
  Badge,
  EmptyState,
  ErrorState,
  Spinner,
  STATUS_TONE_CLASSES,
} from "../components/ui";
import { decideApproval, listApprovals } from "../lib/api/data";
import { listTasks } from "../lib/api/agents";
import { useFetch } from "../lib/hooks/useFetch";
import { formatRelative, statusLabel, statusTone } from "../lib/utils/format";
import type { Approval, Task } from "../lib/types/domain";
import ApprovalActions, { type Approvable } from "../features/approvals/ApprovalActions";

interface TaskContext {
  approval: Approval;
  task: Task | null;
}

function taskContexts(approvals: Approval[], tasks: Task[]): TaskContext[] {
  const taskById = new Map(tasks.map((t) => [t.id, t]));
  return approvals
    .filter((a) => a.status === "pending")
    .map((a) => ({ approval: a, task: taskById.get(a.entity_id) ?? null }));
}

export default function ApprovalsPage() {
  const { data: approvals, loading, error, refetch } = useFetch(listApprovals);
  const { data: tasks } = useFetch(listTasks);
  const [message, setMessage] = useState<{ tone: "success" | "danger"; text: string } | null>(null);

  const handleDecision = async (
    id: string,
    decision: "approve" | "reject",
    reason: string,
  ): Promise<void> => {
    await decideApproval(id, decision, reason);
    setMessage({ tone: decision === "approve" ? "success" : "danger", text: `${decision} recorded.` });
  };

  const pending = (approvals ?? []).filter((a) => a.status === "pending");
  const resolved = (approvals ?? []).filter((a) => a.status !== "pending");
  const contexts = taskContexts(pending, tasks ?? []);

  return (
    <div className="space-y-6">
      <header className="flex items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-100">Approvals</h1>
          <p className="text-sm text-slate-500">Human control layer for agent decisions</p>
        </div>
        <button
          type="button"
          className="btn btn-ghost"
          onClick={() => void refetch()}
          disabled={loading}
        >
          Refresh
        </button>
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

      {loading && !approvals ? (
        <Spinner label="Loading approvals…" />
      ) : error && !approvals ? (
        <ErrorState message={error.message} onRetry={() => void refetch()} />
      ) : !approvals ? null : (
        <>
          <section className="panel">
            <header className="panel-header">
              <h2 className="text-sm font-semibold tracking-wide text-slate-300">
                Awaiting decision
              </h2>
              <Badge tone={STATUS_TONE_CLASSES.warn}>{pending.length} pending</Badge>
            </header>
            {contexts.length === 0 ? (
              <EmptyState title="No pending approvals" description="Approve or reject requests as agents raise them." />
            ) : (
              <ul className="divide-y divide-ink-700">
                {contexts.map(({ approval, task }) => (
                  <li key={approval.id} className="flex flex-col gap-3 px-4 py-4 lg:flex-row lg:items-center lg:justify-between">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <Badge tone={STATUS_TONE_CLASSES.warn}>Level {approval.level}</Badge>
                        <span className="text-sm font-medium text-slate-200">
                          {task ? task.title : approval.reason || approval.entity_type}
                        </span>
                      </div>
                      <p className="mt-1 text-xs text-slate-500">
                        {task ? `${task.task_ref} · ` : ""}
                        Requested by {approval.requested_by} · {approval.entity_type} · {formatRelative(approval.created_at)}
                      </p>
                    </div>
                    <ApprovalActions
                      approval={toApprovable(approval)}
                      onDecision={handleDecision}
                      onChanged={() => {
                        void refetch();
                      }}
                    />
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="panel">
            <header className="panel-header">
              <h2 className="text-sm font-semibold tracking-wide text-slate-300">
                Decision history
              </h2>
              <Badge tone={STATUS_TONE_CLASSES.muted}>{resolved.length} recorded</Badge>
            </header>
            {resolved.length === 0 ? (
              <EmptyState title="No decisions yet" />
            ) : (
              <ul className="divide-y divide-ink-700">
                {resolved.map((a) => (
                  <li key={a.id} className="flex items-center justify-between gap-3 px-4 py-3">
                    <div className="min-w-0">
                      <p className="truncate text-sm text-slate-200">
                        {a.reason || a.entity_type}
                        <span className="ml-2 text-xs text-slate-500">L{a.level}</span>
                      </p>
                      <p className="text-xs text-slate-500">by {a.requested_by}</p>
                    </div>
                    <Badge tone={STATUS_TONE_CLASSES[statusTone(a.status)] ?? STATUS_TONE_CLASSES.muted}>
                      {statusLabel(a.status)}
                    </Badge>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </>
      )}
    </div>
  );
}

function toApprovable(a: Approval): Approvable {
  return {
    id: a.id,
    entity_type: a.entity_type,
    level: a.level,
    status: a.status,
    requested_by: a.requested_by,
    reason: a.reason,
  };
}