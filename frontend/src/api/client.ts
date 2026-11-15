/* The only way the frontend reaches data (CLAUDE.md rule 4): one function per API endpoint. */
import type {
  ActionName, ChatOut, DetectOut, MetaOut, PreviewOut, ResultsOut, ScenarioIn, SimulateOut, SuppressOut,
} from "./types";

// Dev: the backend from `make dev`. Production: same-origin /api, which Vercel rewrites to the
// backend host (frontend/vercel.json). VITE_API_URL overrides both.
export const API_BASE = (
  import.meta.env.VITE_API_URL || (import.meta.env.DEV ? "http://localhost:8000" : "/api")
).replace(/\/$/, "");

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(API_BASE + path, { ...init, headers: { "Content-Type": "application/json", ...init?.headers } });
  } catch {
    throw new ApiError(0, `Can't reach the FireTwin API at ${API_BASE}.`);
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? body);
    } catch {
      /* not JSON: keep the status text */
    }
    throw new ApiError(res.status, `${path} failed (${res.status}): ${detail}`);
  }
  return (await res.json()) as T;
}

const post = <T>(path: string, body: unknown) => request<T>(path, { method: "POST", body: JSON.stringify(body) });

export const api = {
  health: () => request<{ status: string }>("/health"),
  meta: () => request<MetaOut>("/meta"),
  simulate: (inputs: ScenarioIn) => post<SimulateOut>("/simulate", inputs),
  // Verdict only: no scenario is created, so live views can call it on every change.
  preview: (inputs: ScenarioIn) => post<PreviewOut>("/preview", inputs),
  detect: (scenario_id: string) => post<DetectOut>("/detect", { scenario_id }),
  suppress: (scenario_id: string) => post<SuppressOut>("/suppress", { scenario_id }),
  apply: (scenario_id: string, action: ActionName) => post<SimulateOut>("/apply", { scenario_id, action }),
  results: (scenario_id: string) => request<ResultsOut>(`/results/${encodeURIComponent(scenario_id)}`),
  chat: (message: string, scenario_id?: string) => post<ChatOut>("/chat", { message, scenario_id }),
  exportUrl: (scenario_id: string) => `${API_BASE}/export/${encodeURIComponent(scenario_id)}.pdf`,
};
