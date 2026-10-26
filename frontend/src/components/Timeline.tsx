// Investigation timeline: renders the recorded event log in order.
// Visual types: agent/procedure step, backend validation, evidence, model-based
// expectation (never evidence), provider error, nudge, status, diagnosis, remedy, reveal.
import { useEffect, useRef, useState, type ReactNode } from "react";
import type { BoardEntry, Diagnosis, InvestigatorMode, Prediction, Remedy, RunEvent } from "../api/types";
import {
  cls,
  fmtInt,
  hypName,
  humanize,
  isNum,
  remedyName,
  runStatusLabel,
  STATUS_LABEL,
  testName,
  toolName,
} from "../lib/format";

interface Props {
  events: RunEvent[];
  /** The investigator's mode; for an imported replay pass the recorded mode, never "replay". */
  mode: InvestigatorMode;
  highlight: string | null;
  predictions: Prediction[];
  busy?: boolean;
  /** Suppress screen-reader announcements (e.g. replay playing at 4x). */
  quiet?: boolean;
}

const s = (v: unknown): string => (typeof v === "string" ? v : v === null || v === undefined ? "" : JSON.stringify(v));

function ArgList({ name, args }: { name: string; args: Record<string, unknown> }) {
  if (name === "submit_diagnosis") {
    return (
      <dl className="args">
        <div><dt>outcome</dt><dd>{s(args.outcome)}</dd></div>
        {args.primary_hypothesis ? <div><dt>primary</dt><dd>{hypName(s(args.primary_hypothesis))}</dd></div> : null}
        <div><dt>confidence</dt><dd>{s(args.confidence)}</dd></div>
        <div><dt>remedy</dt><dd>{remedyName(s(args.recommended_remedy))}</dd></div>
      </dl>
    );
  }
  if (name === "update_hypotheses") {
    const hs = Array.isArray(args.hypotheses) ? (args.hypotheses as BoardEntry[]) : [];
    return (
      <div>
        <ul className="hyp-mini">
          {hs.map((h) => (
            <li key={String(h.id)}>
              <span>{hypName(String(h.id))}</span>{" "}
              <span className={cls("pill", `pill-${h.status}`)}>{STATUS_LABEL[h.status] ?? String(h.status)}</span>
              {[...(h.supporting_evidence ?? []).map((x) => `+${x}`), ...(h.contradicting_evidence ?? []).map((x) => `−${x}`)].map((x) => (
                <span key={x} className="mono small muted"> {x}</span>
              ))}
            </li>
          ))}
        </ul>
        {args.next_step ? <p className="small muted">next step: {s(args.next_step)}</p> : null}
      </div>
    );
  }
  const entries = Object.entries(args).filter(([k]) => k !== "purpose");
  if (!entries.length) return null;
  return (
    <dl className="args">
      {entries.map(([k, v]) => (
        <div key={k}>
          <dt>{k}</dt>
          <dd className="mono">
            {k === "hypothesis" ? hypName(s(v)) : k === "test" ? testName(s(v)) : s(v)}
            {k.endsWith("_s") && isNum(v) ? " (s)" : ""}
          </dd>
        </div>
      ))}
    </dl>
  );
}

function PredictionBody({ p }: { p: Record<string, unknown> }) {
  const expected = Object.entries(p).filter(([k]) => k.startsWith("expected_") || k.startsWith("implied_"));
  const assumptions = Array.isArray(p.assumptions) ? (p.assumptions as string[]) : [];
  return (
    <>
      <p className="tl-text">
        If <strong>{hypName(s(p.hypothesis))}</strong> were true, <strong>{testName(s(p.test))}</strong> would show:
      </p>
      <dl className="args">
        {expected.map(([k, v]) => (
          <div key={k}>
            <dt className="mono">{k}</dt>
            <dd className="mono">{s(v)}</dd>
          </div>
        ))}
      </dl>
      {assumptions.length > 0 && (
        <details className="small">
          <summary>Assumptions</summary>
          <ul>
            {assumptions.map((a) => (
              <li key={a}>{a}</li>
            ))}
          </ul>
        </details>
      )}
    </>
  );
}

function DiagnosisCard({ d }: { d: Diagnosis }) {
  return (
    <>
      <p className="diag-outcome">
        <span className={cls("outcome", d.outcome === "diagnosed" ? "outcome-diag" : "outcome-inc")}>{String(d.outcome ?? "submitted").toUpperCase()}</span>
        {d.primary_hypothesis && <strong> {hypName(d.primary_hypothesis)}</strong>}
        <span className="muted"> · confidence {d.confidence} (qualitative, not calibrated)</span>
      </p>
      <p className="tl-text">{d.summary}</p>
      <dl className="args">
        <div><dt>recommended</dt><dd>{remedyName(d.recommended_remedy)}</dd></div>
        {d.requested_evidence ? <div><dt>evidence needed</dt><dd>{d.requested_evidence}</dd></div> : null}
      </dl>
    </>
  );
}

export function RemedyBody({ r }: { r: Remedy }) {
  if (!r.approved) {
    return (
      <p className="tl-text">
        Declined: {remedyName(r.remedy)}. {r.note ?? ""}
      </p>
    );
  }
  const v = r.verification;
  const o = r.post_maintenance_observation;
  return (
    <>
      <p className="tl-text">
        Approved simulated maintenance: <strong>{remedyName(r.remedy)}</strong>.
      </p>
      {o && (
        <p className="tl-text">
          Measured after maintenance (t = {fmtInt(o.t_start_s)}..{fmtInt(o.t_end_s)} s): LT-101{" "}
          <span className="mono tnum">{o.summary.level_trend.rate_mm_per_min.toFixed(2)} mm/min</span> against a nominal balance of{" "}
          <span className="mono tnum">{o.summary.nominal_expected_rate_mm_per_min.toFixed(2)} mm/min</span>; FT-102{" "}
          <span className="mono tnum">{o.summary.FT102_mean_L_s.toFixed(2)} L/s</span>.{" "}
          {o.alarms_on_this_window.length
            ? <>Still alarming: {o.alarms_on_this_window.map((a) => a.tag).join(", ")}.</>
            : <>No alarm on these readings.</>}
          <span className="small muted"> Public measurements, not ground truth.</span>
        </p>
      )}
      {r.independent_check && <p className="small muted">{r.independent_check}</p>}
      {v && (
        <>
          <p className="tl-text">
            Independent verification (recorded by an older version, shown before reveal):{" "}
            <span className={cls("verdict", v.passed ? "verdict-pass" : "verdict-fail")}>{v.passed ? "PASSED" : "FAILED"}</span>
            <span className="muted small"> · horizon {fmtInt(v.horizon_s)} s · {v.evaluator_version}</span>
          </p>
          <ul className="checks">
            {(v.checks ?? []).map((c) => (
              <li key={c.check}>
                <span className={cls("verdict", c.passed ? "verdict-pass" : "verdict-fail")}>{c.passed ? "pass" : "fail"}</span> {c.check}
                <span className="mono small muted">
                  {" "}
                  {Object.entries(c)
                    .filter(([k]) => k !== "check" && k !== "passed")
                    .map(([k, val]) => `${k}=${s(val)}`)
                    .join(", ")}
                </span>
              </li>
            ))}
          </ul>
          {v.note && <p className="small muted">{v.note}</p>}
        </>
      )}
    </>
  );
}

interface Rendered {
  cls: string;
  id?: string;
  role?: string;
  focusable?: boolean;
  content: ReactNode;
}

function renderEntry(e: RunEvent, mode: InvestigatorMode, highlight: string | null, predictions: Prediction[]): Rendered | null {
  const p = e.payload;
  const stepWord = mode === "live" ? "Agent step" : mode === "reference" ? "Procedure step" : "Step";
  switch (e.type) {
    case "created":
      return {
        cls: "tl-system",
        content: (
          <>
            <span className="tl-kind">Case</span>
            <span className="tl-text">Sealed case created ({humanize(s(p.kind))}); the investigator has not started.</span>
          </>
        ),
      };
    case "status": {
      const st = s(p.status);
      return {
        cls: cls("tl-status", st === "failed" && "tl-bad"),
        content: (
          <>
            <span className="tl-kind">Status</span>
            <span className="tl-text">
              <strong>{runStatusLabel(st)}</strong>
              {p.label ? ` — ${s(p.label)}` : ""}
              {p.model ? <span className="mono small"> · {s(p.model)}</span> : null}
              {p.reason ? <span className="muted"> · {s(p.reason)}</span> : null}
            </span>
          </>
        ),
      };
    }
    case "model_request": {
      const attempt = isNum(p.attempt) ? p.attempt : 1;
      if (attempt <= 1 && !p.forced_submit) return null;
      return {
        cls: "tl-model",
        content: (
          <>
            <span className="tl-kind">{mode === "reference" ? "Procedure" : "Model call"}</span>
            <span className="tl-text small">
              #{s(p.n)}
              {attempt > 1 ? ` · retry attempt ${attempt}` : ""}
              {p.forced_submit ? " · final turn: only submit_diagnosis is offered" : ""}
            </span>
          </>
        ),
      };
    }
    case "model_response": {
      const u = (p.usage ?? {}) as Record<string, unknown>;
      const note = s(p.note);
      const calls = Array.isArray(p.tool_calls) ? (p.tool_calls as string[]) : [];
      return {
        cls: "tl-model",
        content: (
          <>
            <span className="tl-kind">{mode === "reference" ? "Procedure" : "Model call"}</span>
            <span className="tl-text small">
              #{s(p.n)}{" "}
              {mode === "reference" ? (
                <span className="muted">deterministic rule step, no model</span>
              ) : (
                <span className="muted">
                  {isNum(p.latency_ms) ? `${fmtInt(p.latency_ms)} ms` : ""}
                  {isNum(u.prompt_tokens) ? ` · ${fmtInt(u.prompt_tokens)} in / ${fmtInt(u.completion_tokens)} out tokens` : " · usage not reported"}
                  {p.finish_reason ? ` · finish ${s(p.finish_reason)}` : ""}
                </span>
              )}
              {calls.length ? <span className="muted"> · requested {calls.join(", ")}</span> : <span className="muted"> · no tool call</span>}
              {note && (
                <span className="model-note">
                  <span className="model-note-label">model note</span> {note}
                </span>
              )}
            </span>
          </>
        ),
      };
    }
    case "provider_error":
      return {
        cls: "tl-provider",
        content: (
          <>
            <span className="tl-kind">Provider error</span>
            <span className="tl-text">
              <strong>{s(p.kind)}</strong>
              {p.status !== null && p.status !== undefined ? ` (HTTP ${s(p.status)})` : ""}: {s(p.message)}
              <span className="muted small">
                {" "}
                · attempt {s(p.attempt)} · {p.will_retry ? "retrying (charged to the model-call budget)" : "not retried"}
              </span>
            </span>
          </>
        ),
      };
    case "nudge":
      return {
        cls: "tl-nudge",
        content: (
          <>
            <span className="tl-kind">Nudge</span>
            <span className="tl-text small">No tool call was returned; the loop asked again: “{s(p.text)}”</span>
          </>
        ),
      };
    case "tool_call": {
      const name = s(p.name);
      const args = (p.args ?? {}) as Record<string, unknown>;
      return {
        cls: "tl-agent",
        content: (
          <>
            <span className="tl-kind">{stepWord}</span>
            <div className="tl-card">
              <p className="tl-head">
                <strong>{toolName(name)}</strong> <span className="mono small muted">{name}</span>
              </p>
              <ArgList name={name} args={args} />
              {p.purpose ? (
                <p className="rationale">
                  <span className="rationale-label">rationale</span> {s(p.purpose)}
                </p>
              ) : null}
            </div>
          </>
        ),
      };
    }
    case "tool_result": {
      const name = s(p.name);
      if (!p.ok) {
        return {
          cls: "tl-validation",
          content: (
            <>
              <span className="tl-kind">Backend validation</span>
              <span className="tl-text">
                <span className="mono small">{name}</span> rejected by backend: <span className="error-text">{s(p.error)}</span>
              </span>
            </>
          ),
        };
      }
      if (typeof p.evidence_id === "string") {
        const id = p.evidence_id;
        return {
          cls: cls("tl-evidence", highlight === id && "flash"),
          id: `tl-ev-${id}`,
          focusable: true,
          content: (
            <>
              <span className="tl-kind">Evidence</span>
              <div className="tl-card">
                <p className="tl-head">
                  <span className="chip chip-evidence">{id}</span>{" "}
                  <span className="small muted">simulator observation · {toolName(name)}</span>
                </p>
                <p className="tl-text">{s(p.summary)}</p>
              </div>
            </>
          ),
        };
      }
      if (typeof p.prediction_id === "string") {
        const id = p.prediction_id;
        const pred =
          (p.prediction as Record<string, unknown> | undefined) ??
          (predictions.find((x) => x.prediction_id === id) as Record<string, unknown> | undefined);
        return {
          cls: "tl-prediction",
          id: `tl-pr-${id}`,
          content: (
            <>
              <span className="tl-kind">Expectation</span>
              <div className="tl-card">
                <p className="tl-head">
                  <span className="chip chip-prediction">{id}</span>{" "}
                  <span className="pred-label">model-based expectation — not evidence</span>
                </p>
                {pred ? <PredictionBody p={pred} /> : <p className="small muted">details not available</p>}
              </div>
            </>
          ),
        };
      }
      return {
        cls: "tl-accepted",
        content: (
          <>
            <span className="tl-kind">Backend validation</span>
            <span className="tl-text small">
              <span className="mono">{name}</span> accepted
              {name === "submit_diagnosis"
                ? " (evidence citations and outcome rules checked)"
                : name === "update_hypotheses"
                  ? " (evidence IDs checked)"
                  : ""}
            </span>
          </>
        ),
      };
    }
    case "hypotheses": {
      const board = Array.isArray(p.board) ? (p.board as BoardEntry[]) : [];
      return {
        cls: "tl-system",
        content: (
          <>
            <span className="tl-kind">Board</span>
            <span className="tl-text small">
              Hypothesis board updated:{" "}
              {board.map((h) => (
                <span key={String(h.id)} className="board-inline">
                  {hypName(String(h.id))} <span className={cls("pill", `pill-${h.status}`)}>{STATUS_LABEL[h.status] ?? String(h.status)}</span>
                </span>
              ))}
            </span>
          </>
        ),
      };
    }
    case "diagnosis":
      return {
        cls: "tl-diagnosis",
        content: (
          <>
            <span className="tl-kind">Diagnosis</span>
            <div className="tl-card">
              <DiagnosisCard d={p as unknown as Diagnosis} />
            </div>
          </>
        ),
      };
    case "remedy":
      return {
        cls: "tl-remedy",
        content: (
          <>
            <span className="tl-kind">Maintenance</span>
            <div className="tl-card">
              <RemedyBody r={p as unknown as Remedy} />
            </div>
          </>
        ),
      };
    case "revealed":
      return {
        cls: "tl-revealed",
        content: (
          <>
            <span className="tl-kind">Judge</span>
            <span className="tl-text">Ground truth revealed after the investigation ended. {s(p.note)}</span>
          </>
        ),
      };
    case "budget":
      return null;
    default:
      return {
        cls: "tl-system",
        content: (
          <>
            <span className="tl-kind">{e.type}</span>
            <span className="tl-text small mono">{JSON.stringify(p).slice(0, 200)}</span>
          </>
        ),
      };
  }
}

/** Short screen-reader text for the entries worth announcing; model-call bookkeeping is skipped. */
function announcement(e: RunEvent): string | null {
  const p = e.payload;
  switch (e.type) {
    case "status":
      return `Status: ${runStatusLabel(s(p.status))}.`;
    case "tool_result":
      if (!p.ok) return `Backend validation rejected ${s(p.name)}.`;
      if (typeof p.evidence_id === "string") return `Evidence ${p.evidence_id}: ${s(p.summary).slice(0, 160)}`;
      if (typeof p.prediction_id === "string") return `Expectation ${p.prediction_id}, model-based, not evidence.`;
      return null;
    case "provider_error":
      return `Provider error: ${s(p.kind)}.`;
    case "diagnosis": {
      const d = p as unknown as Diagnosis;
      return `Diagnosis submitted: ${String(d.outcome ?? "")}${d.primary_hypothesis ? `, ${hypName(d.primary_hypothesis)}` : ""}.`;
    }
    case "remedy":
      return p.approved ? `Simulated maintenance approved: ${remedyName(s(p.remedy))}.` : "Simulated maintenance declined.";
    case "revealed":
      return "Ground truth revealed.";
    default:
      return null;
  }
}

export function Timeline({ events, mode, highlight, predictions, busy, quiet = false }: Props) {
  // Only entries that arrive after the first render fade in.
  const firstSeq = useRef<number | null>(null);
  if (firstSeq.current === null && events.length) firstSeq.current = events[events.length - 1].seq;

  // The list itself is not a live region (that would drop its list semantics and read
  // every model-call line). A separate status region announces meaningful additions.
  const lastSeq = useRef<number | null>(null);
  const [said, setSaid] = useState("");
  useEffect(() => {
    const last = events.length ? events[events.length - 1].seq : 0;
    const prev = lastSeq.current;
    lastSeq.current = last;
    if (prev === null || last <= prev || quiet) return; // first render, rewind, or muted
    const fresh = events.filter((e) => e.seq > prev).map(announcement).filter((x): x is string => !!x);
    if (!fresh.length) return;
    setSaid(fresh.length > 3 ? `${fresh.length} new timeline entries. Latest: ${fresh[fresh.length - 1]}` : fresh.join(" "));
  }, [events, quiet]);

  return (
    <div className="timeline-wrap" aria-busy={busy ? "true" : "false"}>
      <ol className="timeline" aria-label="Investigation timeline">
        {events.map((e) => {
          const r = renderEntry(e, mode, highlight, predictions);
          if (!r) return null;
          const isNew = firstSeq.current !== null && e.seq > firstSeq.current;
          return (
            <li key={e.seq} id={r.id} role={r.role} tabIndex={r.focusable ? -1 : undefined} className={cls("tl-entry", r.cls, isNew && "tl-new")}>
              {r.content}
            </li>
          );
        })}
      </ol>
      <p className="sr-only" role="status" aria-live="polite" aria-atomic="true">
        {said}
      </p>
    </div>
  );
}
