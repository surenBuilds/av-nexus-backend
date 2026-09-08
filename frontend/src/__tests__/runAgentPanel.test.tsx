import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { RunAgentPanel } from "../features/agent-run/RunAgentPanel";
import type { Task, TaskRunResponse } from "../lib/types/domain";

const createTask = vi.fn();
const runTask = vi.fn();

vi.mock("../lib/api/tasks", () => ({
  createTask: (...args: unknown[]) => createTask(...args),
  runTask: (...args: unknown[]) => runTask(...args),
}));

const baseTask: Task = {
  id: "t-1",
  org_id: "o-1",
  task_ref: "T-0001",
  title: "Financial health check",
  goal: "Financial health check",
  owner_agent_id: "a-finance",
  status: "COMPLETED",
  priority: "medium",
  confidence: 0.8,
  approval_status: "none",
  approval_level: 1,
  error: null,
  output_json: { result: { financial_health_score: 72.5 }, confidence: 0.8, mode: "deterministic" },
  input_json: { revenue: 100000, expenses: 70000 },
  created_at: "2026-09-05T09:00:00Z",
  updated_at: "2026-09-05T09:00:00Z",
};

const runResponse: TaskRunResponse = {
  task: baseTask,
  agent_runs: [],
  messages: [],
};

beforeEach(() => {
  createTask.mockReset();
  runTask.mockReset();
});

describe("RunAgentPanel", () => {
  it("renders goal input, JSON textarea, and run button", () => {
    render(<RunAgentPanel agentId="a-finance" agentName="CFO" />);
    expect(screen.getByLabelText(/goal/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/inputs \(json\)/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /run now/i })).toBeInTheDocument();
  });

  it("submits real JSON input and shows the result", async () => {
    const user = userEvent.setup();
    createTask.mockResolvedValue({ id: "t-1" });
    runTask.mockResolvedValue(runResponse);

    render(<RunAgentPanel agentId="a-finance" agentName="CFO" />);

    await user.type(screen.getByLabelText(/goal/i), "Financial health check");

    const textarea = screen.getByLabelText(/inputs \(json\)/i) as HTMLTextAreaElement;
    await user.clear(textarea);
    // Paste avoids userEvent's curly-brace special-key interpretation.
    await user.click(textarea);
    await user.paste('{"revenue": 100000, "expenses": 70000}');

    await user.click(screen.getByRole("button", { name: /run now/i }));

    await waitFor(() => {
      expect(createTask).toHaveBeenCalledWith(
        expect.objectContaining({
          goal: "Financial health check",
          owner_agent_id: "a-finance",
          input_json: { revenue: 100000, expenses: 70000 },
        }),
      );
    });
    expect(runTask).toHaveBeenCalledWith("t-1");
    await screen.findByText(/COMPLETED/);
    expect(screen.getByText(/financial_health_score/)).toBeInTheDocument();
  });

  it("shows a validation error and does not call the API for invalid JSON", async () => {
    const user = userEvent.setup();
    render(<RunAgentPanel agentId="a-finance" agentName="CFO" />);

    await user.type(screen.getByLabelText(/goal/i), "Check");
    const textarea = screen.getByLabelText(/inputs \(json\)/i);
    await user.clear(textarea);
    await user.click(textarea);
    await user.paste("not valid json");

    await user.click(screen.getByRole("button", { name: /run now/i }));

    expect(await screen.findByText(/invalid json|unexpected token/i)).toBeInTheDocument();
    expect(createTask).not.toHaveBeenCalled();
  });

  it("requires a goal before submitting", async () => {
    const user = userEvent.setup();
    render(<RunAgentPanel agentId="a-finance" agentName="CFO" />);

    await user.click(screen.getByRole("button", { name: /run now/i }));

    expect(await screen.findByText(/goal is required/i)).toBeInTheDocument();
    expect(createTask).not.toHaveBeenCalled();
  });

  it("surfaces API errors from a failed run", async () => {
    const user = userEvent.setup();
    createTask.mockRejectedValue(new Error("boom"));

    render(<RunAgentPanel agentId="a-finance" agentName="CFO" />);
    await user.type(screen.getByLabelText(/goal/i), "Check");
    await user.click(screen.getByRole("button", { name: /run now/i }));

    expect(await screen.findByText(/failed to run agent/i)).toBeInTheDocument();
  });
});
