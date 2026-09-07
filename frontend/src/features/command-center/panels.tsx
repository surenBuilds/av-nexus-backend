import { Link } from "react-router-dom";
import {
  Badge,
  Card,
  CardHeader,
  EmptyState,
  StatCard,
  STATUS_TONE_CLASSES,
} from "../../components/ui";
import { formatRelative, scoreColor, statusLabel, statusTone } from "../../lib/utils/format";
import type { DashboardSummary } from "../../lib/types/dashboard";

export function MetricRow({ data }: { data: DashboardSummary["group_performance"] }) {
  return (
    <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
      <StatCard label="Companies" value={data.companies} hint="Tracked portfolio" />
      <StatCard label="Opportunities" value={data.opportunities} hint="Registered pipelines" />
      <StatCard label="Tasks completed" value={data.tasks_completed} hint="Across all agents" />
      <StatCard
        label="Avg agent performance"
        value={`${data.avg_agent_performance ?? "—"}`}
        hint={`${data.tasks_running} running now`}
        tone="text-accent"
      />
    </div>
  );
}

export function TaskPipeline({ data }: { data: DashboardSummary["group_performance"] }) {
  const total = Math.max(data.tasks_total ?? 0, data.tasks_completed ?? 0, 1);
  const pct = Math.round(((data.tasks_completed ?? 0) / total) * 100);
  return (
    <Card>
      <CardHeader title="Task execution pipeline" />
      <div className="p-4">
        <div className="flex items-baseline justify-between text-sm">
          <span className="text-slate-400">Completed</span>
          <span className="font-mono text-slate-200">
            {data.tasks_completed} <span className="text-slate-600">/ {total}</span>
          </span>
        </div>
        <div
          className="mt-3 h-2 overflow-hidden rounded-full bg-ink-700"
          role="progressbar"
          aria-valuenow={pct}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label="Task completion"
        >
          <div className="h-full rounded-full bg-accent transition-all" style={{ width: `${pct}%` }} />
        </div>
        <dl className="mt-4 grid grid-cols-3 gap-3 text-center">
          <div>
            <dt className="text-xs text-slate-500">Running</dt>
            <dd className="font-mono text-lg text-amber-300">{data.tasks_running}</dd>
          </div>
          <div>
            <dt className="text-xs text-slate-500">Runs tracked</dt>
            <dd className="font-mono text-lg text-slate-200">{data.runs_tracked}</dd>
          </div>
          <div>
            <dt className="text-xs text-slate-500">Total tasks</dt>
            <dd className="font-mono text-lg text-slate-200">
              {data.tasks_total ?? data.tasks_completed}
            </dd>
          </div>
        </dl>
      </div>
    </Card>
  );
}

export function PrioritiesPanel({
  priorities,
}: {
  priorities: DashboardSummary["today_priorities"];
}) {
  return (
    <Card>
      <CardHeader title="Today's priorities" />
      {priorities.length === 0 ? (
        <EmptyState title="No priorities set" description="Priorities appear here when flagged." />
      ) : (
        <ol className="divide-y divide-ink-700">
          {priorities.map((item, idx) => {
            const title = typeof item.title === "string" ? item.title : "Priority";
            const count = typeof item.count === "number" ? item.count : 0;
            return (
              <li key={idx} className="flex items-center justify-between gap-3 px-4 py-3 text-sm">
                <span className="text-slate-300">{title}</span>
                {count > 0 && (
                  <Badge tone={STATUS_TONE_CLASSES.warn}>{count} item{count === 1 ? "" : "s"}</Badge>
                )}
              </li>
            );
          })}
        </ol>
      )}
    </Card>
  );
}

export function PendingApprovalsPanel({
  approvals,
}: {
  approvals: DashboardSummary["pending_approvals"];
}) {
  return (
    <Card>
      <CardHeader
        title="Pending approvals"
        actions={<Link to="/approvals" className="text-xs text-accent hover:underline">View all</Link>}
      />
      {approvals.length === 0 ? (
        <EmptyState title="Nothing awaiting approval" description="Approvals appear here when agents request them." />
      ) : (
        <ul className="divide-y divide-ink-700">
          {approvals.map((a) => {
            const reason = typeof a.reason === "string" ? a.reason : "";
            const entityType = typeof a.entity_type === "string" ? a.entity_type : "entity";
            const level = typeof a.level === "number" ? a.level : 1;
            return (
              <li key={String(a.id)} className="px-4 py-3">
                <div className="flex items-center justify-between gap-3">
                  <p className="truncate text-sm text-slate-200" title={reason}>
                    {reason || `${entityType} request`}
                  </p>
                  <Badge tone={STATUS_TONE_CLASSES.warn}>L{level}</Badge>
                </div>
                <p className="mt-1 text-xs text-slate-500">
                  {typeof a.requested_by === "string" ? a.requested_by : ""} ·{" "}
                  {entityType}
                </p>
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}

export function TopOpportunitiesPanel({
  opportunities,
}: {
  opportunities: DashboardSummary["top_opportunities"];
}) {
  return (
    <Card>
      <CardHeader
        title="Top opportunities"
        actions={<Link to="/opportunities" className="text-xs text-accent hover:underline">View all</Link>}
      />
      {opportunities.length === 0 ? (
        <EmptyState title="No opportunities yet" description="Scored opportunities appear here." />
      ) : (
        <ul className="divide-y divide-ink-700">
          {opportunities.map((o, idx) => {
            const title = typeof o.title === "string" ? o.title : "Opportunity";
            const score = typeof o.score === "number" ? o.score : 0;
            const category = typeof o.category === "string" ? o.category : "";
            const color = scoreColor(score);
            return (
              <li key={idx} className="flex items-center justify-between gap-3 px-4 py-3">
                <div className="min-w-0">
                  <p className="truncate text-sm text-slate-200">{title}</p>
                  {category && <p className="text-xs text-slate-500">{category}</p>}
                </div>
                <span
                  className={`inline-flex items-center gap-1 rounded-lg px-2 py-1 font-mono text-sm ring-1 ring-inset ${color.bg} ${color.text} ${color.ring}`}
                >
                  {score.toFixed(0)}
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}

export function CompanyHealthPanel({
  health,
}: {
  health: DashboardSummary["company_health"];
}) {
  return (
    <Card>
      <CardHeader
        title="Company health"
        actions={<Link to="/companies" className="text-xs text-accent hover:underline">View all</Link>}
      />
      {health.length === 0 ? (
        <EmptyState title="No companies" />
      ) : (
        <ul className="divide-y divide-ink-700">
          {health.map((c, idx) => {
            const name = typeof c.name === "string" ? c.name : "Company";
            const score = typeof c.score === "number" ? c.score : 0;
            const hasScore = typeof c.score === "number" && score > 0;
            const stage = typeof c.stage === "string" ? c.stage : "";
            const tone = scoreColor(hasScore ? score : 0);
            return (
              <li key={idx} className="flex items-center justify-between gap-3 px-4 py-3">
                <div className="min-w-0">
                  <p className="truncate text-sm text-slate-200">{name}</p>
                  <p className="text-xs text-slate-500">{stage}</p>
                </div>
                {hasScore ? (
                  <span
                    className={`inline-flex items-center rounded-lg px-2 py-1 font-mono text-sm ring-1 ring-inset ${tone.bg} ${tone.text} ${tone.ring}`}
                  >
                    {score.toFixed(0)}
                  </span>
                ) : (
                  <span className="text-xs text-slate-600">Health data unavailable</span>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}

export function AgentActivityPanel({
  activity,
}: {
  activity: DashboardSummary["agent_activity"];
}) {
  return (
    <Card>
      <CardHeader
        title="Agent activity"
        actions={<Link to="/agents" className="text-xs text-accent hover:underline">View network</Link>}
      />
      {activity.length === 0 ? (
        <EmptyState title="No agents registered" />
      ) : (
        <ul className="divide-y divide-ink-700">
          {activity.slice(0, 8).map((a, idx) => {
            const name = typeof a.name === "string" ? a.name : String(a.agent_id);
            const status = typeof a.status === "string" ? a.status : "IDLE";
            const completed = typeof a.tasks_completed === "number" ? a.tasks_completed : 0;
            const tone = STATUS_TONE_CLASSES[statusTone(status)] ?? STATUS_TONE_CLASSES.muted;
            return (
              <li key={idx} className="flex items-center justify-between gap-3 px-4 py-3">
                <div className="flex items-center gap-3">
                  <span aria-hidden="true" className="h-2 w-2 rounded-full bg-accent" />
                  <p className="text-sm text-slate-200">{name}</p>
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-xs text-slate-500">{completed} done</span>
                  <Badge tone={tone}>{statusLabel(status)}</Badge>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}

export function CriticalRisksPanel({
  risks,
}: {
  risks: DashboardSummary["critical_risks"];
}) {
  return (
    <Card>
      <CardHeader title="Critical risks" />
      {risks.length === 0 ? (
        <EmptyState title="No open critical risks" description="High and critical risks surface here." />
      ) : (
        <ul className="divide-y divide-ink-700">
          {risks.map((r, idx) => {
            const title = typeof r.title === "string" ? r.title : "Risk";
            const level = typeof r.level === "string" ? r.level : "";
            const company = typeof r.company === "string" ? r.company : null;
            return (
              <li key={idx} className="px-4 py-3">
                <div className="flex items-center justify-between gap-3">
                  <p className="truncate text-sm text-slate-200">{title}</p>
                  <Badge tone={level === "CRITICAL" ? STATUS_TONE_CLASSES.danger : STATUS_TONE_CLASSES.warn}>
                    {level}
                  </Badge>
                </div>
                {company && <p className="mt-1 text-xs text-slate-500">Company: {company}</p>}
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}

export function RecentDecisionsPanel({
  decisions,
}: {
  decisions: DashboardSummary["recent_decisions"];
}) {
  return (
    <Card>
      <CardHeader
        title="Recent decisions"
        actions={<Link to="/decisions" className="text-xs text-accent hover:underline">View all</Link>}
      />
      {decisions.length === 0 ? (
        <EmptyState title="No decisions recorded" />
      ) : (
        <ul className="divide-y divide-ink-700">
          {decisions.map((d, idx) => {
            const title = typeof d.title === "string" ? d.title : "Decision";
            const status = typeof d.status === "string" ? d.status : "";
            const risk = typeof d.risk_level === "string" ? d.risk_level : "MEDIUM";
            const tone = STATUS_TONE_CLASSES[statusTone(status)] ?? STATUS_TONE_CLASSES.muted;
            return (
              <li key={idx} className="flex items-center justify-between gap-3 px-4 py-3">
                <p className="truncate text-sm text-slate-200">{title}</p>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-slate-500">{risk}</span>
                  <Badge tone={tone}>{status}</Badge>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}

export function StatusStrip({
  data,
  activityCount,
}: {
  data: DashboardSummary | null;
  activityCount: number;
}) {
  const agents = data?.agent_activity.length ?? 0;
  return (
    <div className="flex flex-wrap items-center gap-3 text-xs">
      <StatusChip label="Backend" ok={Boolean(data)} />
      <StatusChip label="Database" ok={Boolean(data)} />
      <StatusChip label={`Agents registered`} ok={data !== null} text={`${agents}`} />
      <StatusChip label="Pending approvals" text={`${data?.pending_approvals.length ?? 0}`} />
      <StatusChip label="Active agents" text={`${data?.agent_activity.filter((a) => String(a.status) !== "IDLE").length ?? 0}`} />
      <span className="ml-auto hidden text-slate-600 sm:block">
        {activityCount} recent run events tracked
      </span>
    </div>
  );
}

function StatusChip({
  label,
  ok,
  text,
}: {
  label: string;
  ok?: boolean;
  text?: string;
}) {
  const bg = ok === undefined ? "bg-ink-800 text-slate-300 ring-ink-600" : ok ? "bg-emerald-500/10 text-emerald-300 ring-emerald-500/40" : "bg-red-500/10 text-red-300 ring-red-500/40";
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 ring-1 ring-inset ${bg}`}>
      <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-current" />
      {label}
      {text !== undefined && <span className="font-mono">{text}</span>}
    </span>
  );
}

export function timeAgo(iso: string | null | undefined): string {
  return formatRelative(iso);
}