/**
 * The client for the Phase 9 FastAPI backend.
 *
 * Everything runs in the browser: the backend allows this origin through
 * CORS, and the simulation stream is an `EventSource`, so there is no reason
 * to proxy reads through the Next.js server.
 */

import type {
  CaseDetail,
  CaseSummary,
  CourtEvent,
  EventPage,
  HealthResponse,
  RuleDetail,
  RunDetail,
  RunStatus,
  RunSummary,
  SimulationRequest,
} from "./types";

export const API_URL = (
  process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000"
).replace(/\/+$/, "");

/** A request the backend answered with an error, carrying its `detail` */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/** The backend is not running, or is unreachable from the browser */
export class ApiUnreachableError extends Error {
  constructor(readonly url: string) {
    super(
      `Cannot reach the simulation backend at ${url}. ` +
        "Start it with: cd backend && python -m app.cli serve",
    );
    this.name = "ApiUnreachableError";
  }
}

export function apiUrl(path: string): string {
  return `${API_URL}${path}`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(apiUrl(path), {
      ...init,
      headers: { "content-type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch {
    throw new ApiUnreachableError(API_URL);
  }

  if (!response.ok) {
    throw new ApiError(response.status, await errorDetail(response));
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

async function errorDetail(response: Response): Promise<string> {
  try {
    const body = await response.json();
    const detail = (body as { detail?: unknown }).detail;
    if (typeof detail === "string") {
      return detail;
    }
    if (detail) {
      return JSON.stringify(detail);
    }
  } catch {
    // fall through to the status line
  }
  return `${response.status} ${response.statusText}`;
}

// ------------------------------------------------------------------ reads

export const getHealth = () => request<HealthResponse>("/health");

export const listCases = () => request<CaseSummary[]>("/api/cases");

export const getCase = (caseId: string) =>
  request<CaseDetail>(`/api/cases/${encodeURIComponent(caseId)}`);

export const listRules = () => request<RuleDetail[]>("/api/rules");

export const listRuns = () => request<RunSummary[]>("/api/runs");

export const getRun = (runId: string) =>
  request<RunDetail>(`/api/runs/${encodeURIComponent(runId)}`);

export const getEvents = (runId: string, after = 0) =>
  request<EventPage>(
    `/api/runs/${encodeURIComponent(runId)}/events?after=${after}`,
  );

// ----------------------------------------------------------------- writes

/**
 * Start a simulation. Returns at once with the run to follow - the trial
 * itself takes minutes, so the backend runs it in the background.
 */
export const startSimulation = (
  caseId: string,
  options: Partial<SimulationRequest>,
) =>
  request<RunDetail>(`/api/cases/${encodeURIComponent(caseId)}/simulate`, {
    method: "POST",
    body: JSON.stringify(options),
  });

export const deleteRun = (runId: string) =>
  request<void>(`/api/runs/${encodeURIComponent(runId)}`, {
    method: "DELETE",
  });

// ---------------------------------------------------------------- streaming

/** The Server-Sent Events endpoint for a run, for `new EventSource(...)` */
export const streamUrl = (runId: string) =>
  apiUrl(`/api/runs/${encodeURIComponent(runId)}/stream`);

/** Every court event type the stream names, so a listener can subscribe */
export const STREAM_EVENT_NAMES = [
  "CASE_LOADED",
  "RULES_EVALUATED",
  "AGENT_STARTED",
  "AGENT_ARGUMENT",
  "AGENT_RESPONSE",
  "EVIDENCE_ANALYZED",
  "EVIDENCE_REVIEWED",
  "JUDGE_QUESTION",
  "JURY_DECISION",
  "JURY_VERDICT",
  "JUDGE_DECISION",
  "AUDIT_COMPLETED",
  "STAGE_SKIPPED",
  "CASE_COMPLETE",
] as const;

/** The two messages that end a stream, named for the run rather than a stage */
export const STREAM_END_NAMES = ["run_completed", "run_failed"] as const;

export const isTerminal = (status: RunStatus) =>
  status === "completed" || status === "failed";

export const parseEvent = (data: string): CourtEvent | null => {
  try {
    return JSON.parse(data) as CourtEvent;
  } catch {
    return null;
  }
};
