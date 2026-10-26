// Thin fetch wrapper: same-origin credentials, ~10 s timeout via AbortController,
// and backend error text surfaced verbatim (`{"error": ...}` or FastAPI `{"detail": ...}`).
import type {
  Catalog,
  CheckResult,
  Presets,
  Remedy,
  Reveal,
  RunListItem,
  RunView,
  StatusResponse,
  Telemetry,
  TwinChallenge,
} from "./types";

export type ApiErrorKind = "http" | "timeout" | "network" | "parse";

export class ApiError extends Error {
  readonly status: number;
  readonly kind: ApiErrorKind;
  constructor(message: string, status: number, kind: ApiErrorKind) {
    super(message);
    this.status = status;
    this.kind = kind;
  }
}

const JUDGE_HEADER = "x-faultline-judge";
const DEFAULT_TIMEOUT_MS = 10_000;

interface RequestOptions {
  method?: "GET" | "POST";
  body?: unknown;
  judge?: boolean;
  timeoutMs?: number;
  signal?: AbortSignal;
}

async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const ctrl = new AbortController();
  let timedOut = false;
  const timer = window.setTimeout(() => {
    timedOut = true;
    ctrl.abort();
  }, opts.timeoutMs ?? DEFAULT_TIMEOUT_MS);
  const onOuterAbort = () => ctrl.abort();
  opts.signal?.addEventListener("abort", onOuterAbort);
  const headers: Record<string, string> = { Accept: "application/json" };
  if (opts.body !== undefined) headers["Content-Type"] = "application/json";
  if (opts.judge) headers[JUDGE_HEADER] = "1";
  let res: Response;
  try {
    res = await fetch(path, {
      method: opts.method ?? "GET",
      headers,
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
      credentials: "same-origin",
      signal: ctrl.signal,
    });
  } catch (e) {
    if (timedOut) throw new ApiError(`request timed out after ${Math.round((opts.timeoutMs ?? DEFAULT_TIMEOUT_MS) / 1000)} s`, 0, "timeout");
    if (opts.signal?.aborted) throw e;
    throw new ApiError("backend not reachable", 0, "network");
  } finally {
    window.clearTimeout(timer);
    opts.signal?.removeEventListener("abort", onOuterAbort);
  }
  const text = await res.text();
  let data: unknown = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      if (!res.ok) throw new ApiError(text.slice(0, 300) || `HTTP ${res.status}`, res.status, "http");
      throw new ApiError("response was not valid JSON", res.status, "parse");
    }
  }
  if (!res.ok) {
    const obj = (data ?? {}) as { error?: unknown; detail?: unknown };
    const msg =
      typeof obj.error === "string"
        ? obj.error
        : typeof obj.detail === "string"
          ? obj.detail
          : `HTTP ${res.status}`;
    throw new ApiError(msg, res.status, "http");
  }
  return data as T;
}

export function errorText(e: unknown): string {
  if (e instanceof ApiError) return e.message;
  if (e instanceof Error) return e.message;
  return String(e);
}

// ------------------------------------------------------------------ judge session
let judgeSession: Promise<void> | null = null;

export function ensureJudgeSession(force = false): Promise<void> {
  if (force || !judgeSession) {
    judgeSession = request<{ ok: boolean }>("/api/judge/session", { method: "POST", judge: true }).then(
      () => undefined,
      (e) => {
        judgeSession = null;
        throw e;
      },
    );
  }
  return judgeSession;
}

/** Judge call: opens the session first, and re-opens it once if the server rotated its token (restart). */
async function judgeRequest<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  await ensureJudgeSession();
  try {
    return await request<T>(path, { ...opts, judge: true });
  } catch (e) {
    if (e instanceof ApiError && e.status === 403 && e.message === "judge session required") {
      await ensureJudgeSession(true);
      return request<T>(path, { ...opts, judge: true });
    }
    throw e;
  }
}

// ------------------------------------------------------------------ endpoints
export const api = {
  status: (signal?: AbortSignal) => request<StatusResponse>("/api/status", { signal }),
  checkConnection: () => request<CheckResult>("/api/status/check", { method: "POST", timeoutMs: 30_000 }),
  catalog: () => request<Catalog>("/api/catalog"),
  runs: () => request<RunListItem[]>("/api/runs"),
  run: (id: string, after = 0, signal?: AbortSignal) =>
    request<RunView>(`/api/runs/${encodeURIComponent(id)}?after=${after}`, { signal }),
  telemetry: (id: string, signal?: AbortSignal) =>
    request<Telemetry>(`/api/runs/${encodeURIComponent(id)}/telemetry`, { signal }),
  start: (id: string, mode: "live" | "reference") =>
    request<{ ok: boolean }>(`/api/runs/${encodeURIComponent(id)}/start`, { method: "POST", body: { mode } }),
  cancel: (id: string) => request<{ ok: boolean }>(`/api/runs/${encodeURIComponent(id)}/cancel`, { method: "POST" }),
  remedy: (id: string, approve: boolean) =>
    request<Remedy>(`/api/runs/${encodeURIComponent(id)}/remedy`, { method: "POST", body: { approve } }),
  guided: () => request<{ run_id: string }>("/api/guided", { method: "POST" }),
  revealGuided: (id: string) =>
    request<Reveal>(`/api/runs/${encodeURIComponent(id)}/reveal-guided`, { method: "POST" }),
  exportJsonUrl: (id: string) => `/api/runs/${encodeURIComponent(id)}/export.json`,
  reportMdUrl: (id: string) => `/api/runs/${encodeURIComponent(id)}/report.md`,

  judgePresets: () => judgeRequest<Presets>("/api/judge/presets"),
  createBlind: (family: string, severity: string, site_profile: string) =>
    judgeRequest<{ run_id: string }>("/api/judge/blind-runs", {
      method: "POST",
      body: { family, severity, site_profile },
    }),
  createTwin: (pair_id: string, site_profile: string) =>
    judgeRequest<TwinChallenge>("/api/judge/twin-challenges", { method: "POST", body: { pair_id, site_profile } }),
  pickTwin: (cid: string, slot: "alpha" | "beta" | "random") =>
    judgeRequest<{ run_id: string }>(`/api/judge/twin-challenges/${encodeURIComponent(cid)}/pick`, {
      method: "POST",
      body: { slot },
    }),
  judgeReveal: (id: string) =>
    judgeRequest<Reveal>(`/api/judge/runs/${encodeURIComponent(id)}/reveal`, { method: "POST" }),
};
