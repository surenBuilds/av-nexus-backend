import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

type Mode = "login" | "register";

export default function LoginPage() {
  const { login, register } = useAuth();
  const navigate = useNavigate();
  const [mode, setMode] = useState<Mode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [orgName, setOrgName] = useState("Artiswon");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (event: FormEvent): Promise<void> => {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      if (mode === "login") {
        await login({ email, password });
      } else {
        await register({ email, password, full_name: fullName, org_name: orgName });
      }
      navigate("/command-center", { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Authentication failed");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <div className="w-full max-w-md">
        <div className="mb-8 text-center">
          <p className="text-sm font-bold uppercase tracking-[0.3em] text-accent">AV Nexus</p>
          <h1 className="mt-2 text-2xl font-semibold text-slate-100">
            AI Business Operating System
          </h1>
          <p className="mt-1 text-sm text-slate-500">
            Command Center &amp; Agent Network console
          </p>
        </div>

        <div className="panel p-6">
          <div className="mb-4 flex rounded-lg bg-ink-800 p-1" role="tablist" aria-label="Authentication mode">
            {(["login", "register"] as const).map((m) => (
              <button
                key={m}
                type="button"
                role="tab"
                aria-selected={mode === m}
                className={`flex-1 rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
                  mode === m ? "bg-accent text-ink-950" : "text-slate-400 hover:text-slate-200"
                }`}
                onClick={() => {
                  setMode(m);
                  setError(null);
                }}
              >
                {m === "login" ? "Sign in" : "Create account"}
              </button>
            ))}
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            {mode === "register" && (
              <div className="space-y-4">
                <label className="block">
                  <span className="mb-1 block text-xs font-medium text-slate-400">
                    Full name
                  </span>
                  <input
                    required
                    className="input"
                    value={fullName}
                    onChange={(e) => setFullName(e.target.value)}
                    autoComplete="name"
                  />
                </label>
                <label className="block">
                  <span className="mb-1 block text-xs font-medium text-slate-400">
                    Organization
                  </span>
                  <input
                    className="input"
                    value={orgName}
                    onChange={(e) => setOrgName(e.target.value)}
                  />
                </label>
              </div>
            )}

            <label className="block">
              <span className="mb-1 block text-xs font-medium text-slate-400">Email</span>
              <input
                required
                type="email"
                className="input"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="email"
                placeholder="you@company.com"
              />
            </label>

            <label className="block">
              <span className="mb-1 block text-xs font-medium text-slate-400">Password</span>
              <input
                required
                type="password"
                className="input"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete={mode === "login" ? "current-password" : "new-password"}
                minLength={8}
              />
            </label>

            {error && (
              <p role="alert" className="rounded-lg bg-red-950/60 px-3 py-2 text-sm text-red-200">
                {error}
              </p>
            )}

            <button
              type="submit"
              disabled={submitting}
              className="btn btn-primary w-full"
            >
              {submitting ? "Please wait…" : mode === "login" ? "Sign in" : "Create account"}
            </button>
          </form>
        </div>

        <p className="mt-4 text-center text-xs text-slate-600">
          Demo account (seeded): chairman@avnexus.local · password on request from seed
        </p>
      </div>
    </div>
  );
}