import type { HealthResponse, RunDetail, RunSummary, StartRunBody } from "./types";

// Base URL comes from the environment. VITE_API_URL is accepted for older deployments.
const envBase = import.meta.env.VITE_API_BASE_URL ?? import.meta.env.VITE_API_URL;
export const API_BASE = (envBase ?? (import.meta.env.DEV ? "http://127.0.0.1:8000" : "")).replace(/\/+$/, "");

// Optional access token for a backend that sets API_AUTH_TOKEN. This is the workspace's own access
// token, never a Gemini/Tavily key. Kept in sessionStorage only, so it is cleared when the tab closes.
const TOKEN_KEY = "newsletter-agent-token";

export function getToken(): string {
  try {
    return sessionStorage.getItem(TOKEN_KEY) ?? "";
  } catch {
    return "";
  }
}

export function setToken(token: string) {
  try {
    if (token) sessionStorage.setItem(TOKEN_KEY, token);
    else sessionStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage unavailable */
  }
}

export function authHeaders(json = false): Record<string, string> {
  const headers: Record<string, string> = {};
  if (json) headers["Content-Type"] = "application/json";
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  return headers;
}

export class ApiError extends Error {
  status: number;
  fields: { field: string; message: string }[];
  constructor(status: number, message: string, fields: { field: string; message: string }[] = []) {
    super(message);
    this.status = status;
    this.fields = fields;
  }
  get offline() {
    return this.status === 0;
  }
}

export const errorMessage = (e: unknown, fallback = "Something went wrong.") =>
  e instanceof Error ? e.message : fallback;

async function errorFromResponse(res: Response): Promise<ApiError> {
  let message = `Request failed (${res.status}).`;
  let fields: { field: string; message: string }[] = [];
  try {
    const body = await res.json();
    if (Array.isArray(body.errors) && body.errors.length) {
      fields = body.errors;
      message = fields.map((e) => (e.field ? `${e.field}: ${e.message}` : e.message)).join("; ");
    } else if (typeof body.detail === "string") {
      message = body.detail;
    }
  } catch {
    /* non-JSON error body */
  }
  return new ApiError(res.status, message, fields);
}

async function send(path: string, init?: RequestInit, extraHeaders?: Record<string, string>): Promise<Response> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { ...authHeaders(Boolean(init?.body)), ...extraHeaders },
    });
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") throw e;
    throw new ApiError(0, `Cannot reach the backend at ${API_BASE || "this origin"}.`);
  }
  if (!res.ok) throw await errorFromResponse(res);
  return res;
}

async function json<T>(path: string, init?: RequestInit): Promise<T> {
  return (await (await send(path, init)).json()) as T;
}

const runPath = (id: string) => `/api/agent/runs/${encodeURIComponent(id)}`;

export type FileKind = "html" | "md";

/** Fetches a saved newsletter file through the authenticated client and triggers a browser download. */
async function downloadFile(id: string, kind: FileKind): Promise<string> {
  const res = await send(`${runPath(id)}/newsletter.${kind}?download=true`);
  const blob = await res.blob();
  const disposition = res.headers.get("content-disposition") ?? "";
  const filename = disposition.match(/filename="?([^";]+)"?/i)?.[1] ?? `newsletter.${kind}`;
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.style.display = "none";
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  return filename;
}

export const api = {
  health: (signal?: AbortSignal) => json<HealthResponse>("/api/health", { signal }),
  listRuns: (limit = 20, signal?: AbortSignal) => json<RunSummary[]>(`/api/agent/runs?limit=${limit}`, { signal }),
  getRun: (id: string, signal?: AbortSignal) => json<RunDetail>(runPath(id), { signal }),
  startRun: (body: StartRunBody) => json<RunDetail>("/api/agent/runs", { method: "POST", body: JSON.stringify(body) }),
  approveResearch: (id: string, selectedIds: string[] | null) =>
    json<RunDetail>(`${runPath(id)}/approve-research`, {
      method: "POST",
      body: JSON.stringify({ selected_ids: selectedIds }),
    }),
  approveNewsletter: (id: string) => json<RunDetail>(`${runPath(id)}/approve-newsletter`, { method: "POST" }),
  revise: (id: string, feedback: string) =>
    json<RunDetail>(`${runPath(id)}/revise`, {
      method: "POST",
      body: JSON.stringify({ feedback: feedback.trim() || null }),
    }),
  cancel: (id: string) => json<RunDetail>(`${runPath(id)}/cancel`, { method: "POST" }),
  /** Opens the authenticated SSE stream. Caller reads the body. */
  events: (id: string, after: number, signal: AbortSignal) =>
    send(`${runPath(id)}/events?after=${after}`, { signal }, { Accept: "text/event-stream" }),
  /** Direct file URL. Only usable without auth (the backend serves it with a sandbox CSP). */
  fileUrl: (id: string, kind: FileKind) => `${API_BASE}${runPath(id)}/newsletter.${kind}`,
  downloadFile,
};
