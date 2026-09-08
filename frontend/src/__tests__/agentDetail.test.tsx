import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import AgentDetailPage from "../pages/AgentDetailPage";
import type { Agent, AgentMessage, AgentRun, Task } from "../lib/types/domain";

const getAgent = vi.fn();
const listAgentRuns = vi.fn();
const listAgentMessages = vi.fn();
const listTasks = vi.fn();

vi.mock("../lib/api/agents", () => ({
  getAgent: (...args: unknown[]) => getAgent(...args),
  listAgentRuns: (...args: unknown[]) => listAgentRuns(...args),
  listAgentMessages: (...args: unknown[]) => listAgentMessages(...args),
  listTasks: (...args: unknown[]) => listTasks(...args),
}));

const agent: Agent = {
  id: "11111111-1111-1111-1111-111111111111",
  agent_id: "opportunity_scout",
  name: "Opportunity Scout",
  role: "Scout",
  description: "Scans for opportunities",
  capabilities_json: ["opportunity_discovery"],
  tools_json: ["search"],
  permissions_json: ["read"],
  status: "IDLE",
  performance_score: 84.5,
  tasks_completed: 17,
  is_active: true,
};

const run: AgentRun = {
  id: "r-1",
  task_id: "t-1",
  task_ref: "T-ABC1",
  task_title: "Scan fintech niche",
  status: "COMPLETED",
  error: null,
  tokens_in: 100,
  tokens_out: 50,
  cost_usd: 0.02,
  started_at: "2026-09-05T09:00:00Z",
  ended_at: "2026-09-05T09:01:00Z",
};

const message: AgentMessage = {
  id: "m-1",
  task_id: "t-1",
  from_agent: "opportunity_scout",
  to_agent: "critic",
  message_type: "proposal",
  payload_json: { area: "fintech" },
  priority: "high",
  sent_at: "2026-09-05T09:00:30Z",
};

const task: Task = {
  id: "t-1",
  org_id: "o-1",
  task_ref: "T-ABC1",
  title: "Scan fintech niche",
  goal: "g",
  owner_agent_id: agent.id,
  status: "COMPLETED",
  priority: "high",
  confidence: 80,
  approval_status: "none",
  approval_level: 1,
  error: null,
  output_json: null,
  input_json: null,
  created_at: "2026-09-05T08:00:00Z",
  updated_at: "2026-09-05T09:00:00Z",
};

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/agents/opportunity_scout"]}>
      <Routes>
        <Route path="/agents/:agentId" element={<AgentDetailPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("AgentDetailPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getAgent.mockResolvedValue(agent);
    listAgentRuns.mockResolvedValue([run]);
    listAgentMessages.mockResolvedValue([message]);
    listTasks.mockResolvedValue([task]);
  });

  it("renders agent identity from the registry endpoint", async () => {
    renderPage();
    await screen.findByRole("heading", { name: "Opportunity Scout" });
    expect(screen.getByText("opportunity_discovery")).toBeInTheDocument();
    expect(getAgent).toHaveBeenCalledWith("opportunity_scout");
  });

  it("renders recent executions with token and cost data", async () => {
    renderPage();
    await screen.findByRole("heading", { name: "Opportunity Scout" });
    expect(screen.getByText(/150 tokens/)).toBeInTheDocument();
    expect(screen.getByText(/0.02/)).toBeInTheDocument();
  });

  it("renders recent agent-to-agent messages", async () => {
    renderPage();
    await screen.findByRole("heading", { name: "Opportunity Scout" });
    expect(screen.getAllByText("critic").length).toBeGreaterThan(0);
  });

  it("renders an empty state when the agent has no runs yet", async () => {
    listAgentRuns.mockResolvedValue([]);
    listAgentMessages.mockResolvedValue([]);
    renderPage();
    await screen.findByRole("heading", { name: "Opportunity Scout" });
    expect(await screen.findByText("No executions yet")).toBeInTheDocument();
    expect(screen.getByText("No messages yet")).toBeInTheDocument();
  });

  it("renders an error state when the registry lookup fails", async () => {
    getAgent.mockRejectedValue(new Error("Agent not registered"));
    renderPage();
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Agent not registered");
  });

  it("renders permissions as chips rather than raw stored data", async () => {
    renderPage();
    await screen.findByRole("heading", { name: "Opportunity Scout" });
    await waitFor(() => {
      expect(screen.getByText("Permissions")).toBeInTheDocument();
      expect(screen.getByText("read")).toBeInTheDocument();
    });
    expect(screen.queryByText(/capabilities_json/)).not.toBeInTheDocument();
  });
});