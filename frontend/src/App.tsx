import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth/AuthContext";
import { Spinner } from "./components/ui";
import AppShell from "./layouts/AppShell";
import LoginPage from "./pages/LoginPage";
import CommandCenterPage from "./pages/CommandCenterPage";
import AgentsPage from "./pages/AgentsPage";
import AgentDetailPage from "./pages/AgentDetailPage";
import OpportunitiesPage from "./pages/OpportunitiesPage";
import CompaniesPage from "./pages/CompaniesPage";
import ApprovalsPage from "./pages/ApprovalsPage";
import DecisionsPage from "./pages/DecisionsPage";
import ActivityPage from "./pages/ActivityPage";
import WorkflowsPage from "./pages/WorkflowsPage";
import NewWorkflowPage from "./pages/NewWorkflowPage";
import WorkflowDetailPage from "./pages/WorkflowDetailPage";

function RequireAuth({ children }: { children: React.ReactNode }) {
  const { token, loading } = useAuth();
  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Spinner label="Checking session…" />
      </div>
    );
  }
  if (!token) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        element={
          <RequireAuth>
            <AppShell />
          </RequireAuth>
        }
      >
        <Route path="/command-center" element={<CommandCenterPage />} />
        <Route path="/agents" element={<AgentsPage />} />
        <Route path="/agents/:agentId" element={<AgentDetailPage />} />
        <Route path="/opportunities" element={<OpportunitiesPage />} />
        <Route path="/companies" element={<CompaniesPage />} />
        <Route path="/approvals" element={<ApprovalsPage />} />
        <Route path="/decisions" element={<DecisionsPage />} />
        <Route path="/activity" element={<ActivityPage />} />
        <Route path="/workflows" element={<WorkflowsPage />} />
        <Route path="/workflows/new" element={<NewWorkflowPage />} />
        <Route path="/workflows/:workflowId" element={<WorkflowDetailPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/command-center" replace />} />
    </Routes>
  );
}