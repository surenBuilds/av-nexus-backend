import { useState } from "react";

export interface Approvable {
  id: string;
  entity_type: string;
  level: number;
  status: string;
  requested_by: string;
  reason: string;
}

interface ApprovalActionsProps {
  approval: Approvable;
  onDecision: (id: string, decision: "approve" | "reject", reason: string) => Promise<void>;
  onChanged: (approval: Approvable) => void;
}

export default function ApprovalActions({ approval, onDecision, onChanged }: ApprovalActionsProps) {
  const [pending, setPending] = useState<"approve" | "reject" | null>(null);
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);

  if (approval.status !== "pending") {
    return <span className="text-xs text-slate-600">{approval.status}</span>;
  }

  const decide = async (decision: "approve" | "reject"): Promise<void> => {
    setError(null);
    setPending(decision);
    try {
      await onDecision(approval.id, decision, reason);
      const updated: Approvable = { ...approval, status: decision === "approve" ? "approved" : "rejected" };
      onChanged(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Decision failed");
    } finally {
      setPending(null);
    }
  };

  return (
    <div className="flex flex-col items-start gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          className="btn btn-primary px-2.5 py-1 text-xs"
          onClick={() => void decide("approve")}
          disabled={pending !== null}
        >
          {pending === "approve" ? "Submitting…" : "Approve"}
        </button>
        <button
          type="button"
          className="btn btn-danger px-2.5 py-1 text-xs"
          onClick={() => void decide("reject")}
          disabled={pending !== null}
        >
          {pending === "reject" ? "Submitting…" : "Reject"}
        </button>
        <label className="flex items-center gap-1.5 text-xs text-slate-500">
          <span>Note:</span>
          <input
            className="w-32 rounded-md border border-ink-600 bg-ink-850 px-2 py-1 text-xs text-slate-200"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="optional"
            disabled={pending !== null}
          />
        </label>
      </div>
      {error && <p role="alert" className="text-xs text-red-300">{error}</p>}
    </div>
  );
}