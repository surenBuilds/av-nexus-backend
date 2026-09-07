export function formatRelative(iso: string | null | undefined): string {
  if (!iso) return "—";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "—";
  const seconds = Math.round((Date.now() - then) / 1000);
  if (seconds < 60) return "just now";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  if (days < 30) return `${days}d ago`;
  return new Date(iso).toLocaleDateString();
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString();
}

export function formatNumber(value: number | undefined | null): string {
  if (value === undefined || value === null) return "—";
  return new Intl.NumberFormat().format(value);
}

export function formatCompact(value: number | undefined | null): string {
  if (value === undefined || value === null) return "—";
  return new Intl.NumberFormat("en", { notation: "compact" }).format(value);
}

export function statusTone(status: string): "success" | "danger" | "warn" | "muted" {
  switch (status.toUpperCase()) {
    case "RUNNING":
    case "QUEUED":
    case "PENDING":
    case "IN_PROGRESS":
    case "PROPOSED":
      return "warn";
    case "COMPLETED":
    case "SUCCEEDED":
    case "APPROVED":
    case "ACTIVE":
    case "IDLE":
      return "success";
    case "FAILED":
    case "REJECTED":
    case "CANCELLED":
    case "BLOCKED":
      return "danger";
    default:
      return "muted";
  }
}

export function statusLabel(status: string): string {
  const lower = status.toLowerCase();
  const map: Record<string, string> = {
    running: "Running",
    queued: "Queued",
    completed: "Completed",
    failed: "Failed",
    cancelled: "Cancelled",
    blocked: "Blocked",
    pending: "Pending",
    approved: "Approved",
    rejected: "Rejected",
    proposed: "Proposed",
    idle: "Idle",
    active: "Active",
    inactive: "Inactive",
  };
  return map[lower] ?? status;
}

export function healthTone(score: number | undefined | null): "success" | "warn" | "danger" | "muted" {
  if (score === undefined || score === null || Number.isNaN(score)) return "muted";
  if (score >= 70) return "success";
  if (score >= 45) return "warn";
  return "danger";
}

export interface ScoreColor {
  bg: string;
  text: string;
  ring: string;
}

export function scoreColor(score: number): ScoreColor {
  if (score >= 70) return { bg: "bg-emerald-500/15", text: "text-emerald-300", ring: "ring-emerald-500/40" };
  if (score >= 45) return { bg: "bg-amber-500/15", text: "text-amber-300", ring: "ring-amber-500/40" };
  return { bg: "bg-red-500/15", text: "text-red-300", ring: "ring-red-500/40" };
}

export const STATUS_TONE_CLASSES: Record<string, string> = {
  success: "bg-emerald-500/15 text-emerald-300 ring-emerald-500/40",
  warn: "bg-amber-500/15 text-amber-300 ring-amber-500/40",
  danger: "bg-red-500/15 text-red-300 ring-red-500/40",
  muted: "bg-slate-500/15 text-slate-300 ring-slate-500/40",
};