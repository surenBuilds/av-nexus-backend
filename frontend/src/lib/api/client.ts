export const API_BASE_URL: string =
  (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000").replace(/\/$/, "") +
  "/api/v1";

const TOKEN_KEY = "avnexus_token";
const USER_KEY = "avnexus_user";

export class ApiError extends Error {
  status: number;
  detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setSession(token: string, userJson: string): void {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USER_KEY, userJson);
}

export function clearSession(): void {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  timeoutMs?: number;
}

async function parseError(res: Response): Promise<ApiError> {
  let detail = `Request failed with status ${res.status}`;
  try {
    const body = (await res.json()) as unknown;
    if (typeof body === "object" && body !== null) {
      const record = body as Record<string, unknown>;
      if (typeof record.detail === "string") detail = record.detail;
      else if (Array.isArray(record.detail) && record.detail.length > 0) {
        const first = record.detail[0] as Record<string, unknown>;
        if (typeof first.msg === "string") detail = first.msg;
      }
    }
  } catch {
    // non-JSON error body; keep generic detail
  }
  return new ApiError(res.status, detail);
}

export async function request<T>(
  path: string,
  options: RequestOptions = {},
  authorized = true,
): Promise<T> {
  const { method = "GET", body, timeoutMs = 10_000 } = options;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  const headers: Record<string, string> = { Accept: "application/json" };
  const token = getToken();
  if (authorized && token) headers.Authorization = `Bearer ${token}`;
  if (body !== undefined) headers["Content-Type"] = "application/json";

  try {
    const res = await fetch(`${API_BASE_URL}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller.signal,
    });
    if (res.status === 401) {
      clearSession();
    }
    if (!res.ok) throw await parseError(res);
    if (res.status === 204) return undefined as T;
    return (await res.json()) as T;
  } catch (err) {
    if (err instanceof ApiError) throw err;
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new ApiError(0, "Request timed out. Check that the backend is running.");
    }
    throw new ApiError(0, "Could not reach the backend. Is it running?");
  } finally {
    clearTimeout(timer);
  }
}