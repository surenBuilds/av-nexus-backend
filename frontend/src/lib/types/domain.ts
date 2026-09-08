export interface User {
  id: string;
  email: string;
  full_name: string;
  role: string;
  can_authorize_level4: boolean;
}

export interface Organization {
  id: string;
  name: string;
  slug: string;
  is_demo: boolean;
}

export interface MeResponse {
  user: User;
  organization: Organization | null;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
}

export interface Agent {
  id: string;
  agent_id: string;
  name: string;
  role: string;
  description: string;
  capabilities_json: string[];
  tools_json: string[];
  permissions_json: string[];
  status: string;
  performance_score: number;
  tasks_completed: number;
  is_active: boolean;
}

export interface AgentRun {
  id: string;
  task_id: string;
  task_ref: string;
  task_title: string;
  status: string;
  error: string | null;
  tokens_in: number;
  tokens_out: number;
  cost_usd: number;
  started_at: string;
  ended_at: string | null;
}

export interface AgentMessage {
  id: string;
  task_id: string | null;
  from_agent: string;
  to_agent: string;
  message_type: string;
  payload_json: Record<string, unknown> | null;
  priority: string;
  sent_at: string;
}

export interface Task {
  id: string;
  org_id: string;
  task_ref: string;
  title: string;
  goal: string;
  owner_agent_id: string | null;
  status: string;
  priority: string;
  confidence: number;
  approval_status: string;
  approval_level: number;
  error: string | null;
  output_json: Record<string, unknown> | null;
  input_json: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

export interface TaskCreatePayload {
  title: string;
  goal: string;
  description?: string;
  capability?: string;
  owner_agent_id?: string;
  priority?: string;
  approval_level?: number;
  input_json?: Record<string, unknown>;
}

export interface TaskRunResponse {
  task: Task;
  agent_runs: Array<{
    agent_id: string;
    status: string;
    error: string | null;
    tokens_in: number;
    tokens_out: number;
    cost_usd: number;
  }>;
  messages: Array<{
    from: string;
    to: string;
    type: string;
    payload: Record<string, unknown>;
    sent_at: string;
  }>;
}

export interface Opportunity {
  id: string;
  org_id: string;
  title: string;
  description: string;
  category: string;
  opportunity_score: number;
  market_potential: number;
  growth_rate: number;
  competition: number;
  entry_difficulty: number;
  capital_requirements: number;
  risk_score: number;
  status: string;
  source: string;
  is_demo: boolean;
  created_at: string;
}

export interface Company {
  id: string;
  org_id: string;
  name: string;
  slug: string;
  industry: string;
  stage: string;
  business_health_score: number;
  is_demo: boolean;
  mission: string;
  vision: string;
}

export interface Approval {
  id: string;
  org_id: string;
  entity_type: string;
  entity_id: string;
  level: number;
  status: string;
  requested_by: string;
  reason: string;
  created_at: string;
}

export interface Decision {
  id: string;
  org_id: string;
  title: string;
  decision_type: string;
  status: string;
  reason: string;
  supporting_evidence_json: Record<string, unknown>[];
  agents_involved_json: string[];
  confidence: number;
  risk_level: string;
  approved_at: string | null;
}

export interface ActivityItem {
  id: string;
  actor: string;
  action: string;
  entity: string;
  status: string;
  timestamp: string;
}

export type Status =
  | "RUNNING"
  | "COMPLETED"
  | "FAILED"
  | "QUEUED"
  | "BLOCKED"
  | "CANCELLED";

export type Priority = "low" | "medium" | "high" | "critical";

export interface WorkflowSnapshot {
  id: string;
  org_id: string;
  created_by: string | null;
  name: string;
  objective: string;
  workflow_type: string;
  status: string;
  priority: string;
  current_step: number;
  total_steps: number;
  meta_json: Record<string, unknown> | null;
  error: string;
  confidence: number;
  cancel_requested: boolean;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface WorkflowStepSnapshot {
  id: string;
  workflow_id: string;
  step_index: number;
  name: string;
  agent_id: string;
  agent_name: string;
  goal: string;
  status: string;
  task_id: string | null;
  task_ref: string;
  approval_level: number;
  input_summary_json: Record<string, unknown> | null;
  output_summary_json: Record<string, unknown> | null;
  review_json: Record<string, unknown> | null;
  error: string | null;
  started_at: string | null;
  ended_at: string | null;
}

export interface WorkflowEventItem {
  id: string;
  workflow_id: string;
  event_type: string;
  actor: string;
  step_index: number | null;
  message: string;
  payload_json: Record<string, unknown> | null;
  created_at: string;
}

export interface WorkflowResultData {
  id: string;
  workflow_id: string;
  objective: string;
  summary: string;
  report_md: string;
  top_opportunities: Array<Record<string, unknown>>;
  market_findings: Array<Record<string, unknown>>;
  competitive_findings: Array<Record<string, unknown>>;
  risks: Array<Record<string, unknown>>;
  disagreements: Array<Record<string, unknown>>;
  next_actions: Array<Record<string, unknown>>;
  approval_requirements: Array<Record<string, unknown>>;
  stage_results_json: Array<Record<string, unknown>>;
  confidence: number;
  recommendation: string;
  created_at: string;
}

export interface WorkflowDetail {
  workflow: WorkflowSnapshot;
  steps: WorkflowStepSnapshot[];
  events: WorkflowEventItem[];
  result: WorkflowResultData | null;
}

export interface WorkflowTaskRef {
  step: WorkflowStepSnapshot;
  task: Record<string, unknown>;
}

export interface RunSnapshot {
  task_id: string;
  task_ref: string;
  step_name: string;
  agent_id: string | null;
  status: string;
  error: string | null;
  tokens_in: number;
  tokens_out: number;
  cost_usd: number;
}

export interface WorkflowTrace {
  workflow: WorkflowSnapshot;
  steps: WorkflowStepSnapshot[];
  tasks: WorkflowTaskRef[];
  runs: RunSnapshot[];
  messages: Array<Record<string, unknown>>;
  approvals: Array<Record<string, unknown>>;
  events: WorkflowEventItem[];
}

export interface WorkflowCreatePayload {
  objective: string;
  workflow_type?: string;
  company_id?: string | null;
  priority?: string;
  context?: Record<string, string>;
}