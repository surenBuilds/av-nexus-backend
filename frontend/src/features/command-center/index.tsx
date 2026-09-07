import { ErrorState, Spinner } from "../../components/ui";
import type { DashboardSummary } from "../../lib/types/dashboard";
import {
  AgentActivityPanel,
  CompanyHealthPanel,
  CriticalRisksPanel,
  MetricRow,
  PendingApprovalsPanel,
  PrioritiesPanel,
  RecentDecisionsPanel,
  StatusStrip,
  TaskPipeline,
  TopOpportunitiesPanel,
} from "./panels";

export function Cards({
  data,
  loading,
  error,
  onRetry,
}: {
  data: DashboardSummary | null;
  loading: boolean;
  error: Error | null;
  onRetry: () => void;
}) {
  if (loading && !data) {
    return (
      <div className="space-y-6">
        <div className="h-10 animate-pulse rounded-xl bg-ink-800" />
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="h-24 animate-pulse rounded-xl bg-ink-800" />
          ))}
        </div>
        <div className="h-64 animate-pulse rounded-xl bg-ink-800" />
        <Spinner label="Loading command center…" />
      </div>
    );
  }

  if (error && !data) {
    return <ErrorState message={error.message} onRetry={onRetry} />;
  }

  if (!data) return null;

  return (
    <div className="space-y-6">
      <StatusStrip data={data} activityCount={data.group_performance.runs_tracked} />
      <MetricRow data={data.group_performance} />

      <div className="grid gap-6 lg:grid-cols-3">
        <TaskPipeline data={data.group_performance} />
        <PrioritiesPanel priorities={data.today_priorities} />
        <PendingApprovalsPanel approvals={data.pending_approvals} />
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <TopOpportunitiesPanel opportunities={data.top_opportunities} />
        <CompanyHealthPanel health={data.company_health} />
        <CriticalRisksPanel risks={data.critical_risks} />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <AgentActivityPanel activity={data.agent_activity} />
        <RecentDecisionsPanel decisions={data.recent_decisions} />
      </div>
    </div>
  );
}