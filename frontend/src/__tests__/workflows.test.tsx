import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import type { ReactElement } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import WorkflowsPage from "../pages/WorkflowsPage";
import NewWorkflowPage from "../pages/NewWorkflowPage";
import WorkflowDetailPage from "../pages/WorkflowDetailPage";
import type {
  WorkflowResultData,
  WorkflowSnapshot,
  WorkflowTrace,
} from "../lib/types/domain";

const listWorkflows = vi.fn();
const createWorkflow = vi.fn();
const getWorkflowTrace = vi.fn();
const getWorkflowResult = vi.fn();
const startWorkflow = vi.fn();
const cancelWorkflow = vi.fn();
const resumeWorkflow = vi.fn();
const listCompanies = vi.fn();
const decideApproval = vi.fn();
const copyToClipboard = vi.fn();

vi.mock("../lib/api/workflows", () => ({
  listWorkflows: () => listWorkflows(),
  createWorkflow: (...args: unknown[]) => createWorkflow(...args),
  getWorkflowTrace: (...args: unknown[]) => getWorkflowTrace(...args),
  getWorkflowResult: (...args: unknown[]) => getWorkflowResult(...args),
  startWorkflow: (...args: unknown[]) => startWorkflow(...args),
  cancelWorkflow: (...args: unknown[]) => cancelWorkflow(...args),
  resumeWorkflow: (...args: unknown[]) => resumeWorkflow(...args),
  WORKFLOW_ACTIVE: new Set([
    "CREATED",
    "PLANNING",
    "RUNNING",
    "WAITING_FOR_DEPENDENCY",
    "WAITING_FOR_APPROVAL",
  ]),
  WORKFLOW_TERMINAL: new Set(["COMPLETED", "FAILED", "CANCELLED"]),
}));

vi.mock("../lib/utils/clipboard", () => ({
  copyToClipboard: (...args: unknown[]) => copyToClipboard(...args),
}));

vi.mock("../lib/api/data", () => ({
  listCompanies: () => listCompanies(),
  decideApproval: (...args: unknown[]) => decideApproval(...args),
}));

const wfBase: WorkflowSnapshot = {
  id: "w-1",
  org_id: "o-1",
  created_by: "u-1",
  name: "Opportunity discovery: smart construction",
  objective: "Launch a smart construction play.",
  workflow_type: "opportunity_discovery",
  status: "COMPLETED",
  priority: "medium",
  current_step: 13,
  total_steps: 13,
  meta_json: null,
  error: "",
  confidence: 74.2,
  cancel_requested: false,
  started_at: "2026-09-05T09:00:00Z",
  completed_at: "2026-09-05T09:00:30Z",
  created_at: "2026-09-05T08:59:00Z",
  updated_at: "2026-09-05T09:00:30Z",
};

const result: WorkflowResultData = {
  id: "r-1",
  workflow_id: "w-1",
  objective: wfBase.objective,
  summary: "Commercial retrofit offers a strong expansion lane.",
  report_md: "# EXECUTIVE SUMMARY\n\nCommercial retrofit is a go.",
  top_opportunities: [],
  market_findings: [],
  competitive_findings: [],
  risks: [],
  disagreements: [],
  next_actions: [],
  approval_requirements: [],
  stage_results_json: [],
  confidence: 74.2,
  recommendation: "VALIDATE_FURTHER",
  created_at: "2026-09-05T09:00:30Z",
};

const completedTrace: WorkflowTrace = {
  workflow: wfBase,
  steps: [
    {
      id: "s-1",
      workflow_id: "w-1",
      step_index: 0,
      name: "Market scan",
      agent_id: "opportunity_scout",
      agent_name: "Opportunity Scout",
      goal: "Scan for opportunities.",
      status: "COMPLETED",
      task_id: "t-1",
      task_ref: "T-ABC001",
      approval_level: 1,
      input_summary_json: { industry_focus: "smart_construction" },
      output_summary_json: { opportunity_score: "82" },
      review_json: null,
      error: null,
      started_at: "2026-09-05T09:00:01Z",
      ended_at: "2026-09-05T09:00:02Z",
    },
    {
      id: "s-2",
      workflow_id: "w-1",
      step_index: 1,
      name: "Risk review",
      agent_id: "risk",
      agent_name: "Risk Guardian",
      goal: "Assess risks.",
      status: "COMPLETED",
      task_id: "t-2",
      task_ref: "T-ABC002",
      approval_level: 3,
      input_summary_json: null,
      output_summary_json: { risk_level: "medium" },
      review_json: null,
      error: null,
      started_at: "2026-09-05T09:00:03Z",
      ended_at: "2026-09-05T09:00:04Z",
    },
  ],
  tasks: [],
  runs: [
    {
      task_id: "t-1",
      task_ref: "T-ABC001",
      step_name: "Market scan",
      agent_id: "opportunity_scout",
      status: "COMPLETED",
      error: null,
      tokens_in: 100,
      tokens_out: 50,
      cost_usd: 0.001,
    },
  ],
  messages: [
    {
      id: "m-1",
      from_agent: "validation",
      to_agent: "critic",
      message_type: "finding",
      summary: "Verdict GO",
    },
  ],
  approvals: [
    {
      id: "ap-1",
      entity_type: "decision",
      level: 4,
      status: "pending",
      requested_by: "chairman",
      reason: "Final go/no-go",
    },
  ],
  events: [
    {
      id: "e-1",
      workflow_id: "w-1",
      event_type: "workflow.started",
      actor: "system",
      step_index: null,
      message: "Workflow started",
      payload_json: null,
      created_at: "2026-09-05T09:00:00Z",
    },
  ],
};

function renderWithRouter(ui: ReactElement) {
  return render(<MemoryRouter>{ui}</MemoryRouter>);
}

describe("WorkflowsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    listWorkflows.mockResolvedValue([wfBase]);
  });

  it("renders a list of workflows with status and progress", async () => {
    renderWithRouter(<WorkflowsPage />);
    await screen.findByText(wfBase.name);
    expect(screen.getAllByText(/opportunity discovery/i).length).toBeGreaterThan(0);
    expect(screen.getByText("13/13 steps")).toBeInTheDocument();
    expect(screen.getByText("Completed")).toBeInTheDocument();
  });

  it("renders an empty state when there are no workflows", async () => {
    listWorkflows.mockResolvedValue([]);
    renderWithRouter(<WorkflowsPage />);
    await screen.findByText("No workflows yet");
  });

  it("renders an error state when the API is unavailable", async () => {
    listWorkflows.mockRejectedValue(new Error("Could not reach the backend. Is it running?"));
    renderWithRouter(<WorkflowsPage />);
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Could not reach the backend. Is it running?");
  });
});

describe("NewWorkflowPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    createWorkflow.mockResolvedValue(wfBase);
    listCompanies.mockResolvedValue([]);
  });

  it("creates a workflow with the given objective and industry focus", async () => {
    const user = userEvent.setup();
    renderWithRouter(<NewWorkflowPage />);

    await user.type(
      screen.getByLabelText("Objective"),
      "Expand into commercial retrofit markets",
    );
    await user.type(screen.getByLabelText(/Industry focus/), "commercial_real_estate");
    await user.click(screen.getByRole("button", { name: /create workflow/i }));

    await waitFor(() => {
      expect(createWorkflow).toHaveBeenCalledWith({
        objective: "Expand into commercial retrofit markets",
        workflow_type: "opportunity_discovery",
        company_id: null,
        priority: "medium",
        context: { industry_focus: "commercial_real_estate" },
      });
    });
  });
});

describe("WorkflowDetailPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getWorkflowTrace.mockResolvedValue(completedTrace);
    getWorkflowResult.mockResolvedValue(result);
    startWorkflow.mockResolvedValue(wfBase);
    cancelWorkflow.mockResolvedValue(wfBase);
    decideApproval.mockResolvedValue({ id: "ap-1", status: "approved" });
  });

  it("renders the workflow trace, steps, runs, and report", async () => {
    renderWithRouter(<WorkflowDetailPage />);
    await screen.findByRole("heading", { name: wfBase.name });
    expect(screen.getAllByText("Market scan").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Risk review").length).toBeGreaterThan(0);
    expect(screen.getAllByText("T-ABC001").length).toBeGreaterThan(0);
    expect(screen.getByText(/Commercial retrofit is a go/)).toBeInTheDocument();
    expect(screen.getByText(/EXECUTIVE SUMMARY/)).toBeInTheDocument();
  });

  it("approves a pending workflow gate", async () => {
    const user = userEvent.setup();
    renderWithRouter(<WorkflowDetailPage />);
    await screen.findByRole("heading", { name: wfBase.name });

    await user.click(screen.getByRole("button", { name: /approve/i }));

    await waitFor(() => {
      expect(decideApproval).toHaveBeenCalledWith("ap-1", "approve", "decided from workflow view");
    });
  });

  it("starts a created workflow", async () => {
    const user = userEvent.setup();
    const created = {
      ...wfBase,
      status: "CREATED",
      cancel_requested: true,
      current_step: 0,
      total_steps: 13,
    };
    getWorkflowTrace.mockResolvedValue({ ...completedTrace, workflow: created });

    renderWithRouter(<WorkflowDetailPage />);
    await screen.findByRole("heading", { name: wfBase.name });

    await user.click(screen.getByRole("button", { name: /^Start$/i }));

    await waitFor(() => {
      expect(startWorkflow).toHaveBeenCalledWith("w-1");
    });
  });

  it("copies the report to the clipboard", async () => {
    copyToClipboard.mockResolvedValue(undefined);
    const user = userEvent.setup();

    renderWithRouter(<WorkflowDetailPage />);
    await screen.findByRole("heading", { name: wfBase.name });

    await user.click(screen.getByRole("button", { name: /copy report/i }));

    await waitFor(() => {
      expect(copyToClipboard).toHaveBeenCalledWith(result.report_md);
    });
  });
});