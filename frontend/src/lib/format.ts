// Formatting helpers. They only format values received from the API; they never compute plant state.
import type { HypothesisStatus, RunKind, RunMode, RunStatus } from "../api/types";

export function isNum(v: unknown): v is number {
  return typeof v === "number" && Number.isFinite(v);
}

export function fmt(v: unknown, digits = 2, unit = ""): string {
  if (!isNum(v)) return "—";
  const s = v.toFixed(digits);
  return unit ? `${s} ${unit}` : s;
}

export function fmtSigned(v: unknown, digits = 2, unit = ""): string {
  if (!isNum(v)) return "—";
  const s = (v > 0 ? "+" : v < 0 ? "−" : "") + Math.abs(v).toFixed(digits);
  return unit ? `${s} ${unit}` : s;
}

/** Simulation time relative to the warning (t = 0), e.g. "t = +180 s". */
export function fmtSimT(t: unknown): string {
  if (!isNum(t)) return "t = —";
  const r = Math.round(t);
  return `t = ${r > 0 ? "+" : r < 0 ? "−" : ""}${Math.abs(r)} s`;
}

export function fmtSimRange(a: unknown, b: unknown): string {
  if (!isNum(a) || !isNum(b)) return "—";
  const s = (x: number) => `${x > 0 ? "+" : x < 0 ? "−" : ""}${Math.abs(Math.round(x))}`;
  return `t = ${s(a)}…${s(b)} s`;
}

export function fmtDuration(s: unknown): string {
  if (!isNum(s)) return "—";
  if (s < 90) return `${Math.round(s)} s`;
  const m = Math.floor(s / 60);
  const r = Math.round(s - m * 60);
  return r ? `${m} min ${r} s` : `${m} min`;
}

export function fmtUsd(v: unknown, digits = 4): string {
  if (!isNum(v)) return "—";
  return `$${v.toFixed(digits)}`;
}

export function fmtInt(v: unknown): string {
  if (!isNum(v)) return "—";
  return Math.round(v).toLocaleString("en-US");
}

export function fmtDateTime(epochS: unknown): string {
  if (!isNum(epochS)) return "—";
  const d = new Date(epochS * 1000);
  return d.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export function fmtClock(epochS: unknown): string {
  if (!isNum(epochS)) return "—";
  return new Date(epochS * 1000).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

const HYP_SHORT: Record<string, string> = {
  no_fault: "No fault",
  pump_delivery_reduced: "Pump delivery reduced",
  tank_leak: "Tank leak",
  level_sensor_stuck: "Level sensor stuck",
};

export function hypName(id: string | null | undefined): string {
  if (!id) return "—";
  return HYP_SHORT[id] ?? humanize(id);
}

export function humanize(id: string): string {
  const s = id.replace(/_/g, " ").trim();
  return s.charAt(0).toUpperCase() + s.slice(1);
}

export const STATUS_LABEL: Record<HypothesisStatus, string> = {
  open: "open",
  supported: "supported",
  weakened: "weakened",
  ruled_out: "ruled out",
};

export const RUN_STATUS_LABEL: Record<RunStatus, string> = {
  ready: "ready",
  investigating: "investigating",
  awaiting_approval: "awaiting approval",
  diagnosed: "diagnosed",
  inconclusive: "inconclusive",
  failed: "failed",
  cancelled: "cancelled",
};

export function runStatusLabel(s: string): string {
  return (RUN_STATUS_LABEL as Record<string, string>)[s] ?? s;
}

export function kindLabel(k: RunKind): string {
  switch (k) {
    case "twin":
      return "Twin challenge";
    case "blind":
      return "Blind challenge";
    case "guided":
      return "Guided example";
    default:
      return humanize(String(k));
  }
}

export function modeLabel(m: RunMode | string): string {
  if (m === "live") return "LIVE";
  if (m === "reference") return "REFERENCE PROCEDURE";
  if (m === "unstarted") return "NOT STARTED";
  if (m === "replay") return "REPLAY";
  return String(m).toUpperCase();
}

const REMEDY_LABEL: Record<string, string> = {
  replace_or_repair_pump: "Replace or repair P-101",
  repair_tank_leak: "Repair the T-101 leak",
  replace_level_sensor: "Replace LT-101 level sensor",
  no_action: "No maintenance action",
  none_until_more_evidence: "None until more evidence",
};

export function remedyName(r: string | null | undefined): string {
  if (!r) return "—";
  return REMEDY_LABEL[r] ?? humanize(r);
}

const TEST_LABEL: Record<string, string> = {
  inlet_flow: "FT-101 inlet flow measurement",
  independent_level: "DIP-101 independent level reading",
  pump_stop_test: "P-101 stop test",
  wait: "Wait and watch LT-101",
};

export function testName(t: string): string {
  return TEST_LABEL[t] ?? humanize(t);
}

const TOOL_LABEL: Record<string, string> = {
  read_observations: "Read historian",
  measure_inlet_flow: "Measure inlet flow (FT-101)",
  request_independent_level_measurement: "Request dip reading (DIP-101)",
  set_simulated_pump: "Stop P-101 (bounded test)",
  advance_simulation: "Wait and observe",
  predict_under_hypothesis: "Model-based expectation",
  update_hypotheses: "Update hypotheses",
  submit_diagnosis: "Submit diagnosis",
};

export function toolName(t: string): string {
  return TOOL_LABEL[t] ?? t;
}

const SITE_LABEL: Record<string, string> = {
  inlet_flow_meter_FT101: "FT-101 inlet meter",
  independent_level_DIP101: "DIP-101 dip reading",
  pump_stop_test: "P-101 stop test",
  max_additional_time_s: "Extra simulated time",
  note: "Note",
};

export function siteLabel(k: string): string {
  return SITE_LABEL[k] ?? humanize(k);
}

export function siteValue(k: string, v: string | number): string {
  if (k === "max_additional_time_s" && isNum(v)) return `${fmtDuration(v)} (${Math.round(v)} s)`;
  return String(v);
}

export function cls(...parts: (string | false | null | undefined)[]): string {
  return parts.filter(Boolean).join(" ");
}
