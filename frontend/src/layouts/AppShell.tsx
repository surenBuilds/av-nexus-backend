import { useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import {
  LayoutGrid,
  Network,
  Radar,
  Building2,
  GitBranch,
  ShieldCheck,
  Gavel,
  Activity,
} from "lucide-react";
import { useHealth } from "../hooks/useHealth";
import { useAuth } from "../auth/AuthContext";

const NAV_ITEMS = [
  { to: "/command-center", label: "Command Center", section: "OPERATIONS", icon: LayoutGrid },
  { to: "/agents", label: "Agent Network", section: "OPERATIONS", icon: Network },
  { to: "/opportunities", label: "Opportunities", section: "TRACKING", icon: Radar },
  { to: "/companies", label: "Companies", section: "TRACKING", icon: Building2 },
  { to: "/workflows", label: "Workflows", section: "TRACKING", icon: GitBranch },
  { to: "/approvals", label: "Approvals", section: "GOVERNANCE", icon: ShieldCheck },
  { to: "/decisions", label: "Decisions", section: "GOVERNANCE", icon: Gavel },
  { to: "/activity", label: "Activity", section: "GOVERNANCE", icon: Activity },
] as const;

function Section({ name }: { name: string }) {
  return (
    <p className="mt-5 px-3 text-[10px] font-semibold uppercase tracking-widest text-slate-600">
      {name}
    </p>
  );
}

function SidebarContent({ collapsed }: { collapsed: boolean }) {
  let lastSection = "";
  return (
    <div className="px-3 pb-6">
      <p className="px-3 pb-4 text-xs font-bold uppercase tracking-[0.2em] text-accent">
        {collapsed ? "AV" : "AV NEXUS"}
      </p>
      {NAV_ITEMS.reduce<React.ReactNode[]>((acc, item) => {
        if (item.section !== lastSection) {
          lastSection = item.section;
          if (!collapsed) acc.push(<Section key={item.section} name={item.section} />);
        }
        const Icon = item.icon;
        acc.push(
          <NavLink
            key={item.to}
            to={item.to}
            title={collapsed ? item.label : undefined}
            className={({ isActive }) =>
              `mt-1 flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                isActive
                  ? "bg-accent/10 text-accent ring-1 ring-inset ring-accent/30"
                  : "text-slate-400 hover:bg-ink-800 hover:text-slate-200"
              }`
            }
          >
            <Icon aria-hidden="true" className="h-4 w-4 shrink-0" />
            {!collapsed && <span className="truncate">{item.label}</span>}
          </NavLink>,
        );
        return acc;
      }, [])}
    </div>
  );
}

export default function AppShell() {
  const [collapsed, setCollapsed] = useState(false);
  const { me, logout } = useAuth();
  const navigate = useNavigate();
  const health = useHealth();

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  return (
    <div className="flex min-h-screen">
      <aside
        aria-label="Primary navigation"
        className={`sticky top-0 hidden h-screen shrink-0 flex-col border-r border-ink-700 bg-ink-900/60 md:flex ${
          collapsed ? "w-16" : "w-60"
        } transition-[width]`}
      >
        <div className="flex-1 overflow-y-auto pt-5">
          <SidebarContent collapsed={collapsed} />
        </div>
        <button
          type="button"
          className="m-3 flex items-center justify-center rounded-lg border border-ink-600 bg-ink-800 px-3 py-1.5 text-xs text-slate-300 hover:bg-ink-700"
          onClick={() => setCollapsed((v) => !v)}
        >
          {collapsed ? "Expand" : "Collapse"}
        </button>
      </aside>

      <div className="min-w-0 flex-1">
        <header className="sticky top-0 z-10 border-b border-ink-700 bg-ink-950/90 backdrop-blur">
          <div className="flex items-center justify-between gap-4 px-4 py-3 lg:px-6">
            <div className="flex items-center gap-3">
              <div className="md:hidden">
                <p className="text-sm font-bold tracking-widest text-accent">AV NEXUS</p>
              </div>
              <div className="hidden md:block">
                <p className="flex items-center gap-2 text-sm font-semibold text-slate-200">
                  {health.data ? health.data.app : "Command Center"}
                  <span className="badge-mono">AV-OS</span>
                </p>
                <p className="text-xs text-slate-500">
                  {me?.organization?.name ?? "—"} · {me?.user.role}
                </p>
              </div>
            </div>

            <div className="flex items-center gap-3">
              <div
                className={`hidden items-center gap-2 rounded-full px-3 py-1 text-xs ring-1 ring-inset sm:flex ${
                  health.data
                    ? "bg-emerald-500/10 text-emerald-300 ring-emerald-500/40"
                    : "bg-amber-500/10 text-amber-300 ring-amber-500/40"
                }`}
                role="status"
              >
                <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-current" />
                {health.data ? `Backend ${health.data.status.toUpperCase()}` : "Backend offline"}
              </div>
              <div className="flex items-center gap-2">
                <div className="flex h-8 w-8 items-center justify-center rounded-full bg-accent/15 text-xs font-bold text-accent ring-1 ring-inset ring-accent/30">
                  {me?.user.full_name.charAt(0).toUpperCase() ?? "?"}
                </div>
                <span className="hidden text-sm text-slate-300 lg:block">
                  {me?.user.full_name}
                </span>
                <button
                  type="button"
                  className="btn btn-ghost px-2 py-1 text-xs"
                  onClick={handleLogout}
                >
                  Sign out
                </button>
              </div>
            </div>
          </div>
        </header>

        <main className="px-4 py-6 lg:px-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}