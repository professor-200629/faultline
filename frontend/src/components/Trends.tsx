// Measured trends: logged LT-101 (historian) with pump-stop test intervals shaded,
// DIP-101 points and, in a separate panel, FT-102 with FT-101 measurements (±1 sd).
import type { Evidence, Nominal, TelemetrySample } from "../api/types";
import { isNum } from "../lib/format";
import { Legend, TimeChart, type Band, type PointMark } from "./charts";

const C_LEVEL = "var(--measure)";
const C_DIP = "var(--measure-2)";
const C_FLOW = "var(--measure)";
const C_FT101 = "var(--measure-2)";

function n(d: Record<string, unknown>, k: string): number | null {
  const v = d[k];
  return isNum(v) ? v : null;
}

export function pumpStopBands(evidence: Evidence[]): Band[] {
  return evidence
    .filter((e) => e.kind === "pump_stop_test")
    .map((e) => ({
      key: e.evidence_id,
      label: `P-101 stopped (${e.evidence_id})${e.data["aborted_by_low_level_interlock"] ? ", aborted" : ""}`,
      t0: e.t_start_s,
      t1: e.t_end_s,
    }));
}

export function dipMarks(evidence: Evidence[]): PointMark[] {
  const out: PointMark[] = [];
  for (const e of evidence) {
    if (e.kind !== "independent_level") continue;
    const v = n(e.data, "dip_level_m");
    const t = n(e.data, "t_s");
    if (v === null || t === null) continue;
    out.push({ key: e.evidence_id, label: `DIP-101 ${e.evidence_id}`, t, v, sd: n(e.data, "stated_uncertainty_sd_m") ?? undefined, shape: "diamond", color: C_DIP });
  }
  return out;
}

/** FT-101 averaging window (data.t_start_s..data.t_end_s), falling back to the evidence span. */
export function ft101Window(e: Evidence): { t0: number; t1: number; fitStart: number | null } {
  return {
    t0: n(e.data, "t_start_s") ?? e.t_start_s,
    t1: n(e.data, "t_end_s") ?? e.t_end_s,
    fitStart: n(e.data, "t_fit_start_s"),
  };
}

export function ft101Marks(evidence: Evidence[]): PointMark[] {
  const out: PointMark[] = [];
  for (const e of evidence) {
    if (e.kind !== "inlet_flow_measurement") continue;
    const v = n(e.data, "mean_inlet_flow_L_s");
    if (v === null) continue;
    // The evidence item spans clamp fit + averaging; the mean covers only data.t_start_s..data.t_end_s.
    const { t0, t1 } = ft101Window(e);
    out.push({
      key: e.evidence_id,
      label: `FT-101 ${e.evidence_id}`,
      t: (t0 + t1) / 2,
      t0,
      t1,
      v,
      sd: n(e.data, "stated_uncertainty_sd_L_s") ?? undefined,
      shape: "circle",
      color: C_FT101,
    });
  }
  return out;
}

export function MeasuredTrends({
  samples,
  nowS,
  evidence,
  nominal,
  note,
  clipped,
}: {
  samples: TelemetrySample[];
  nowS: number;
  evidence: Evidence[];
  nominal: Nominal | null;
  note?: string;
  clipped?: boolean;
}) {
  const start = samples.length ? Math.min(samples[0].t_s, -900) : -900;
  const xDomain: [number, number] = [start, Math.max(nowS, 0) + 30];
  const bands = pumpStopBands(evidence);
  const dips = dipMarks(evidence);
  const ft101 = ft101Marks(evidence);
  const rated = nominal?.pump.rated_delivery_L_s;
  const level = samples.map((s) => ({ t: s.t_s, v: s.LT101_m }));
  const flow = samples.map((s) => ({ t: s.t_s, v: s.FT102_L_s }));
  const last = samples[samples.length - 1];
  return (
    <div className="trends">
      <TimeChart
        series={[{ key: "lt", label: "LT-101", color: C_LEVEL, points: level }]}
        points={dips}
        bands={bands}
        xDomain={xDomain}
        yLabel="LT-101 level"
        yUnit="m"
        yDigits={2}
        yMinSpan={0.08}
        height={196}
        ariaLabel={`LT-101 logged level from ${Math.round(start / 60)} to ${Math.round(nowS / 60)} minutes relative to the warning${
          last ? `; latest ${last.LT101_m.toFixed(3)} m` : ""
        }. ${dips.length} DIP-101 readings, ${bands.length} pump-stop tests shaded.`}
      />
      <Legend
        items={[
          { label: "LT-101 logged reading", color: C_LEVEL, shape: "line" },
          { label: "DIP-101 dip ±1 sd", color: C_DIP, shape: "diamond" },
          { label: "P-101 stop test", color: "", shape: "band" },
          { label: "warning raised (t = 0)", color: "var(--alarm)", shape: "zero" },
        ]}
      />
      <TimeChart
        series={[{ key: "ft102", label: "FT-102", color: C_FLOW, points: flow, width: 1.3 }]}
        points={ft101}
        bands={bands}
        refLines={isNum(rated) ? [{ key: "rated", v: rated, label: `P-101 rated ${rated.toFixed(2)} L/s (datasheet)`, color: "var(--muted)" }] : []}
        xDomain={xDomain}
        yLabel="flow"
        yUnit="L/s"
        yDigits={2}
        yMinSpan={0.3}
        height={150}
        ariaLabel={`FT-102 demand flow${last ? `, latest ${last.FT102_L_s.toFixed(2)} L/s` : ""}; ${ft101.length} FT-101 inlet measurements.`}
      />
      <Legend
        items={[
          { label: "FT-102 demand (logged)", color: C_FLOW, shape: "line" },
          { label: "FT-101 inlet, averaged ±1 sd", color: C_FT101, shape: "circle" },
          { label: "datasheet rating", color: "var(--muted)", shape: "dash" },
        ]}
      />
      <p className="fineprint">
        {note ?? "Logged readings only."}
        {clipped ? " Replay: trends are limited to the simulated time reached so far." : ""}
      </p>
    </div>
  );
}
