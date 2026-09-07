import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import CommandCenterPage from "../pages/CommandCenterPage";
import type { DashboardSummary } from "../lib/types/dashboard";

const getDashboard = vi.fn();

vi.mock("../lib/api/data", () => ({
  getDashboard: () => getDashboard(),
}));

function summary(overrides: Partial<DashboardSummary> = {}): DashboardSummary {
  return {
    org_id: "o-1",
    org_name: "Artiswon",
    is_demo: true,
    today_priorities: [{ title: "Review pending approvals", count: 1 }],
    top_opportunities: [{ title: "Fintech expansion", score: 82, status: "OPEN", category: "fintech" }],
    critical_risks: [{ title: "Cash runway < 6 months", level: "HIGH", category: "finance", company: null }],
    company_health: [{ name: "Voxline AI", score: 74, status: "GREEN", stage: "early", is_demo: true }],
    agent_activity: [{ agent_id: "finance", name: "Finance Agent", status: "IDLE", tasks_completed: 12, performance_score: 88 }],
    pending_approvals: [{ id: "a-1", level: 3, status: "pending", requested_by: "orchestrator", reason: "Approve blueprint", entity_type: "task" }],
    recent_decisions: [{ title: "Enter fintech", status: "APPROVED", decision_type: "growth", confidence: 0.9, risk_level: "LOW" }],
    group_performance: {
      companies: 3,
      opportunities: 12,
      tasks_completed: 45,
      tasks_running: 2,
      tasks_total: 50,
      runs_tracked: 100,
      avg_agent_performance: 82.5,
    },
    ...overrides,
  };
}

function renderPage() {
  return render(
    <MemoryRouter>
      <CommandCenterPage />
    </MemoryRouter>,
  );
}

describe("CommandCenterPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getDashboard.mockResolvedValue(summary());
  });

  it("shows a loading spinner while fetching, then the dashboard", async () => {
    renderPage();
    expect(screen.getAllByRole("status").length).toBeGreaterThan(0);
    await screen.findByText("Live operational view · Artiswon");
    expect(screen.getByText("Today's priorities")).toBeInTheDocument();
    expect(screen.getByText(/Top opportunities/)).toBeInTheDocument();
  });

  it("renders group performance metrics from real dashboard data", async () => {
    renderPage();
    await screen.findByText("Live operational view · Artiswon");
    expect(screen.getByText("Avg agent performance")).toBeInTheDocument();
    expect(screen.getByText("82.5")).toBeInTheDocument();
    expect(screen.getAllByText("3").length).toBeGreaterThan(0);
  });

  it("renders company health with a score and an honest unsupported case", async () => {
    getDashboard.mockResolvedValue(
      summary({
        company_health: [
          { name: "Voxline AI", score: 74, status: "GREEN", stage: "early", is_demo: true },
          { name: "KrtLab", score: 0, status: "RED", stage: "seed", is_demo: true },
        ],
      }),
    );
    renderPage();
    await screen.findByText("Company health");
    expect(screen.getByText("KrtLab")).toBeInTheDocument();
    expect(screen.getByText("Health data unavailable")).toBeInTheDocument();
  });

  it("renders an empty state when the API returns no pending approvals", async () => {
    getDashboard.mockResolvedValue(summary({ pending_approvals: [] }));
    renderPage();
    await screen.findByText("Nothing awaiting approval");
  });

  it("renders an error state with a retry when the backend is unreachable", async () => {
    getDashboard.mockRejectedValue(new Error("Could not reach the backend. Is it running?"));
    renderPage();
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Could not reach the backend. Is it running?");
    expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument();
  });

  it("renders critical risks surfaced from the dashboard endpoint", async () => {
    renderPage();
    await screen.findByText("Critical risks");
    expect(screen.getByText("Cash runway < 6 months")).toBeInTheDocument();
    expect(screen.getByText("HIGH")).toBeInTheDocument();
  });
});