// Derives what the workstation displays from the public run view and its event log.
// LIVE view: authoritative fields come from the API view.
// REPLAY view: everything is reconstructed from the first `cutoff` recorded events;
// evidence/prediction payloads are taken from the recorded run but only once the
// event that produced them has been replayed.
import type {
  BoardEntry,
  BudgetPayload,
  Counters,
  Diagnosis,
  Evidence,
  InvestigatorMode,
  Prediction,
  ProviderInfo,
  Remedy,
  Reveal,
  RunEvent,
  RunStatus,
  RunView,
} from "../api/types";
import { isNum } from "./format";

export const HYPOTHESIS_ORDER = ["no_fault", "pump_delivery_reduced", "tank_leak", "level_sensor_stuck"];

export interface RunModel {
  status: RunStatus;
  statusReason: string;
  visited: Set<string>;
  /** Who produced the events: for an imported replay this is the RECORDED mode, never "replay". */
  mode: InvestigatorMode;
  provider: ProviderInfo;
  evidence: Evidence[];
  predictions: Prediction[];
  board: BoardEntry[];
  diagnosis: Diagnosis | null;
  remedy: Remedy | null;
  counters: Partial<Counters>;
  budget: BudgetPayload | null;
  simUsedS: number | null;
  simLimitS: number | null;
  /** Simulated "now" for clipping telemetry (seconds relative to the warning). */
  simNowS: number | null;
  wallUsedS: number | null;
  reveal: Reveal | null;
  events: RunEvent[];
}

export function defaultBoard(ids: string[] = HYPOTHESIS_ORDER): BoardEntry[] {
  return ids.map((id) => ({ id, status: "open", supporting_evidence: [], contradicting_evidence: [], note: "" }));
}

function lastOf(events: RunEvent[], type: string): RunEvent | undefined {
  for (let i = events.length - 1; i >= 0; i--) if (events[i].type === type) return events[i];
  return undefined;
}

function siteLimit(view: RunView): number | null {
  const v = view.public?.site?.["max_additional_time_s"];
  return isNum(v) ? v : null;
}

function wallUsed(view: RunView, counters: Partial<Counters>, budget: BudgetPayload | null): number | null {
  if (isNum(counters.elapsed_s) && counters.elapsed_s > 0) return counters.elapsed_s;
  if (budget && isNum(budget.wall_clock_remaining_s) && isNum(view.budgets?.wall_clock_s))
    return Math.max(0, view.budgets.wall_clock_s - budget.wall_clock_remaining_s);
  if (isNum(counters.elapsed_s)) return counters.elapsed_s;
  return null;
}

function visitedStatuses(events: RunEvent[]): Set<string> {
  const s = new Set<string>(["ready"]);
  for (const e of events) if (e.type === "status" && typeof e.payload.status === "string") s.add(e.payload.status);
  return s;
}

function asInvestigator(m: unknown): InvestigatorMode | null {
  return m === "live" || m === "reference" || m === "unstarted" ? m : null;
}

/** True when the run is an imported recording (it can never be started or revealed). */
export function isImportedReplay(view: RunView): boolean {
  return view.mode === "replay";
}

/**
 * The mode of the investigator whose steps the events record. For an imported replay
 * this is versions.recorded_mode, else the mode named by the last recorded status event.
 */
export function investigatorMode(view: RunView, events: RunEvent[]): InvestigatorMode {
  const direct = asInvestigator(view.mode);
  if (direct) return direct;
  const recorded = asInvestigator(view.versions?.["recorded_mode"]);
  if (recorded) return recorded;
  for (let i = events.length - 1; i >= 0; i--) {
    const e = events[i];
    if (e.type === "status" && (e.payload.mode === "live" || e.payload.mode === "reference")) return e.payload.mode;
  }
  return "unstarted";
}

/** When the run was recorded: the original creation time for an imported replay. */
export function recordedAt(view: RunView): number {
  const v = view.versions?.["recorded_at"];
  return view.mode === "replay" && isNum(v) ? v : view.created_at;
}

export function buildLiveModel(view: RunView, events: RunEvent[], hypIds?: string[]): RunModel {
  const budgetEv = lastOf(events, "budget");
  const budget = (budgetEv?.payload as BudgetPayload | undefined) ?? null;
  const counters: Partial<Counters> =
    view.counters && isNum(view.counters.tool_calls) ? view.counters : budget ? { ...budget } : {};
  const limit = view.simulated_time?.limit_s ?? siteLimit(view);
  let used: number | null = view.simulated_time?.used_s ?? null;
  if (used === null && budget && isNum(budget.simulated_time_remaining_s) && isNum(limit))
    used = Math.max(0, limit - budget.simulated_time_remaining_s);
  const visited = visitedStatuses(events);
  visited.add(view.status);
  return {
    status: view.status,
    statusReason: view.status_reason ?? "",
    visited,
    mode: investigatorMode(view, events),
    provider: view.provider ?? {},
    evidence: view.evidence ?? [],
    predictions: view.predictions ?? [],
    board: view.board && view.board.length ? view.board : defaultBoard(hypIds),
    diagnosis: view.diagnosis,
    remedy: view.remedy,
    counters,
    budget,
    simUsedS: used,
    simLimitS: limit,
    simNowS: view.simulated_time?.now_s ?? null,
    wallUsedS: wallUsed(view, counters, budget),
    reveal: view.reveal ?? null,
    events,
  };
}

export function buildReplayModel(view: RunView, events: RunEvent[], cutoff: number, hypIds?: string[]): RunModel {
  const evs = events.slice(0, Math.max(0, Math.min(cutoff, events.length)));
  let status: RunStatus = "ready";
  let reason = "";
  let mode: InvestigatorMode = "unstarted";
  let provider: ProviderInfo = {};
  const evidenceIds = new Set<string>();
  const predictionIds = new Set<string>();
  let board: BoardEntry[] | null = null;
  let diagnosis: Diagnosis | null = null;
  let remedy: Remedy | null = null;
  let budget: BudgetPayload | null = null;
  let revealed = false;
  for (const e of evs) {
    const p = e.payload;
    switch (e.type) {
      case "status":
        if (typeof p.status === "string") status = p.status as RunStatus;
        reason = typeof p.reason === "string" ? p.reason : "";
        if (p.mode === "live" || p.mode === "reference") {
          mode = p.mode;
          provider = { name: p.provider as string, model: p.model as string, label: p.label as string };
        }
        break;
      case "tool_result":
        if (p.ok && typeof p.evidence_id === "string") evidenceIds.add(p.evidence_id);
        if (p.ok && typeof p.prediction_id === "string") predictionIds.add(p.prediction_id);
        break;
      case "hypotheses":
        if (Array.isArray(p.board)) board = p.board as BoardEntry[];
        break;
      case "diagnosis":
        diagnosis = p as unknown as Diagnosis;
        break;
      case "remedy":
        remedy = p as unknown as Remedy;
        break;
      case "budget":
        budget = p as BudgetPayload;
        break;
      case "revealed":
        revealed = true;
        break;
    }
  }
  const evidence = (view.evidence ?? []).filter((e) => evidenceIds.has(e.evidence_id));
  const predictions = (view.predictions ?? []).filter((p) => predictionIds.has(p.prediction_id));
  const limit = view.simulated_time?.limit_s ?? siteLimit(view);
  const used =
    budget && isNum(budget.simulated_time_remaining_s) && isNum(limit)
      ? Math.max(0, limit - budget.simulated_time_remaining_s)
      : evs.length && isNum(limit)
        ? 0
        : null;
  const simNow = evidence.reduce((m, e) => (isNum(e.t_end_s) && e.t_end_s > m ? e.t_end_s : m), 0);
  const counters: Partial<Counters> = budget ? { ...budget } : {};
  return {
    status,
    statusReason: reason,
    visited: visitedStatuses(evs),
    mode,
    provider,
    evidence,
    predictions,
    board: board ?? defaultBoard(hypIds),
    diagnosis,
    remedy,
    counters,
    budget,
    simUsedS: used,
    simLimitS: limit,
    simNowS: simNow,
    wallUsedS: wallUsed(view, counters, budget),
    reveal: revealed ? view.reveal ?? null : null,
    events: evs,
  };
}

export function isTerminal(s: string): boolean {
  return s === "diagnosed" || s === "inconclusive" || s === "failed" || s === "cancelled";
}
