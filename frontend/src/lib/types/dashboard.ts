export interface DashboardSummary {
  org_id: string;
  org_name: string;
  is_demo: boolean;
  today_priorities: Record<string, unknown>[];
  top_opportunities: Record<string, unknown>[];
  critical_risks: Record<string, unknown>[];
  company_health: Record<string, unknown>[];
  agent_activity: Record<string, unknown>[];
  pending_approvals: Record<string, unknown>[];
  recent_decisions: Record<string, unknown>[];
  group_performance: {
    companies: number;
    opportunities: number;
    tasks_completed: number;
    tasks_running: number;
    tasks_total: number;
    runs_tracked: number;
    avg_agent_performance: number;
    [key: string]: unknown;
  };
}