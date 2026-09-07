import { useEffect, useState } from "react";

interface HealthResponse {
  status: string;
  app: string;
  env: string;
}

export function useHealth(): {
  data: HealthResponse | null;
  checking: boolean;
  check: () => Promise<void>;
} {
  const [data, setData] = useState<HealthResponse | null>(null);
  const [checking, setChecking] = useState(true);

  const check = async (): Promise<void> => {
    setChecking(true);
    try {
      const base = (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000").replace(
        /\/$/,
        "",
      );
      const res = await fetch(`${base}/health`, { signal: AbortSignal.timeout(5000) });
      setData(res.ok ? ((await res.json()) as HealthResponse) : null);
    } catch {
      setData(null);
    } finally {
      setChecking(false);
    }
  };

  useEffect(() => {
    void check();
  }, []);

  return { data, checking, check };
}