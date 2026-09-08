import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ApprovalsPage from "../pages/ApprovalsPage";
import type { Approval, Task } from "../lib/types/domain";

const listApprovals = vi.fn();
const listTasks = vi.fn();
const decideApproval = vi.fn();

vi.mock("../lib/api/data", () => ({
  listApprovals: () => listApprovals(),
  decideApproval: (...args: unknown[]) => decideApproval(...args),
}));

vi.mock("../lib/api/agents", () => ({
  listTasks: () => listTasks(),
}));

const approval: Approval = {
  id: "a-1",
  org_id: "o-1",
  entity_type: "task",
  entity_id: "t-1",
  level: 3,
  status: "pending",
  requested_by: "business_coach_orchestrator",
  reason: "Approve venture blueprint",
  created_at: "2026-09-05T10:00:00Z",
};

const task: Task = {
  id: "t-1",
  org_id: "o-1",
  task_ref: "T-ABC123",
  title: "Venture blueprint for fintech expansion",
  goal: "Build",
  owner_agent_id: null,
  status: "COMPLETED",
  priority: "high",
  confidence: 85,
  approval_status: "pending",
  approval_level: 3,
  error: null,
  output_json: null,
  input_json: null,
  created_at: "2026-09-05T09:00:00Z",
  updated_at: "2026-09-05T10:00:00Z",
};

function renderPage() {
  return render(
    <MemoryRouter>
      <ApprovalsPage />
    </MemoryRouter>,
  );
}

describe("ApprovalsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    listApprovals.mockResolvedValue([approval]);
    listTasks.mockResolvedValue([task]);
    decideApproval.mockResolvedValue({ ...approval, status: "approved" });
  });

  it("shows a loading state while approvals are being fetched", () => {
    listApprovals.mockReturnValue(new Promise(() => undefined));
    renderPage();
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("renders pending approvals and their task context", async () => {
    renderPage();
    await screen.findByText("Awaiting decision");
    await screen.findByText("Venture blueprint for fintech expansion");
    expect(screen.getByText(/Level 3/)).toBeInTheDocument();
    expect(screen.getByText(/T-ABC123/)).toBeInTheDocument();
  });

  it("approves an approval via the API and records the outcome", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("Venture blueprint for fintech expansion");

    await user.click(screen.getByRole("button", { name: /approve/i }));

    await waitFor(() => {
      expect(decideApproval).toHaveBeenCalledWith("a-1", "approve", "");
    });
    await screen.findByText(/approve recorded\./i);
    // refetch is triggered after a decision
    expect(listApprovals).toHaveBeenCalled();
  });

  it("surfaces errors if a decision fails", async () => {
    const user = userEvent.setup();
    decideApproval.mockRejectedValue(new Error("Level 4 requires chairman"));
    renderPage();
    await screen.findByText("Venture blueprint for fintech expansion");

    await user.click(screen.getByRole("button", { name: /approve/i }));

    await screen.findByRole("alert");
    expect(screen.getByRole("alert")).toHaveTextContent("Level 4 requires chairman");
  });

  it("renders an empty state when there are no approvals", async () => {
    listApprovals.mockResolvedValue([]);
    renderPage();
    await screen.findByText("No pending approvals");
  });

  it("renders an error state when the API is unavailable", async () => {
    listApprovals.mockRejectedValue(new Error("Could not reach the backend. Is it running?"));
    renderPage();
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Could not reach the backend. Is it running?");
  });
});