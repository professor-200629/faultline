// Judge-only reveal panel. Rendered ONLY when the API view carries `reveal`
// (i.e. after a judge reveal of a terminal run). Kept visually separate from
// the measured trends.
import type { Reveal, TelemetrySample } from "../api/types";
import { cls, hypName, humanize, isNum, testName } from "../lib/format";
import { Legend, TimeChart } from "./charts";

const GRADE_TEXT: Record<string, { title: string; text: string }> = {
  correct_diagnosis: {
    title: "Correct diagnosis",
    text: "The investigation named the true cause, and the permitted tests could separate it from the alternatives.",
  },
  wrong_diagnosis: {
    title: "Wrong diagnosis",
    text: "A diagnosis was submitted, but it names a different cause from the true one.",
  },
  appropriate_inconclusive: {
    title: "Appropriate inconclusive",
    text: "The permitted tests could not separate the viable causes, and the investigation correctly said so instead of guessing.",
  },
  wrong_inconclusive: {
    title: "Wrong inconclusive",
    text: "The investigation stopped at inconclusive but ruled out the true cause (or a cause the instruments could not exclude) along the way.",
  },
  unnecessary_inconclusive: {
    title: "Unnecessary inconclusive",
    text: "The permitted tests could have separated the causes, but the investigation stopped at inconclusive.",
  },
  unsupported_diagnosis: {
    title: "Unsupported diagnosis",
    text: "A diagnosis was submitted although the permitted tests could not separate the viable causes; any match with the truth is luck, not evidence.",
  },
  no_result: {
    title: "No result",
    text: "The run failed or was cancelled before a diagnosis was submitted.",
  },
};

function val(v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "number") return String(v);
  if (typeof v === "string") return v;
  return JSON.stringify(v);
}

export function RevealPanel({ reveal, kind, logged }: { reveal: Reveal; kind: string; logged: TelemetrySample[] }) {
  const g = reveal.grade ?? { category: "no_result", correct: false, confident_wrong: false, truth_family: reveal.fault_family, identifiable: false, status: "" };
  const gt = GRADE_TEXT[g.category] ?? { title: humanize(String(g.category)), text: "" };
  const trace = reveal.true_state_trace ?? [];
  const t0 = Math.min(trace[0]?.t_s ?? -900, logged[0]?.t_s ?? -900);
  const t1 = Math.max(trace[trace.length - 1]?.t_s ?? 0, logged[logged.length - 1]?.t_s ?? 0);
  const ident = reveal.identifiability ?? { identifiable: false, alternatives: [] };
  return (
    <section className="reveal" aria-labelledby="reveal-h" data-coach="reveal-panel">
      <h2 id="reveal-h" className="reveal-title" tabIndex={-1}>
        Judge-only ground truth — revealed after the investigation ended
      </h2>
      <p className="reveal-lede">
        Everything in this panel comes from the sealed case and the simulator&apos;s internal state. None of it was available to the
        investigation.
      </p>

      <div className="reveal-grid">
        <div className="reveal-block">
          <h3>True cause</h3>
          <p className="reveal-big">{hypName(reveal.fault_family)}</p>
          <p>{reveal.label}</p>
          {isNum(reveal.initial_true_level_m) && (
            <p className="small">
              True level at t = −900 s: <span className="mono tnum">{reveal.initial_true_level_m.toFixed(3)} m</span>
            </p>
          )}
        </div>
        <div className="reveal-block">
          <h3>Grade</h3>
          <p className="reveal-big">
            {gt.title} <span className="mono small">({g.category})</span>
          </p>
          <p>{gt.text}</p>
          <ul className="flags">
            <li>correct: {g.correct ? "yes" : "no"}</li>
            {g.remedy_matches_truth !== undefined && <li>recommended remedy matches the truth: {g.remedy_matches_truth ? "yes" : "no"}</li>}
            <li>confidently wrong: {g.confident_wrong ? "yes" : "no"}</li>
            {g.lucky_guess !== undefined && <li>lucky guess: {g.lucky_guess ? "yes" : "no"}</li>}
            {g.agent_confidence && <li>stated confidence: {g.agent_confidence}</li>}
          </ul>
        </div>
      </div>

      <div className="reveal-block">
        <h3>Could the permitted instruments decide it?</h3>
        <p>
          Identifiable with this site&apos;s instruments and tests: <strong>{ident.identifiable ? "yes" : "no"}</strong>
          <span className="muted small"> (noise-free 4-sigma separability rule per single test; {ident.oracle_version ?? "oracle"})</span>
        </p>
        <table className="alt-table">
          <thead>
            <tr>
              <th scope="col">Alternative to the truth</th>
              <th scope="col">Viable after the alarm window?</th>
              <th scope="col">Tests that separate it</th>
            </tr>
          </thead>
          <tbody>
            {ident.alternatives.map((a) => (
              <tr key={a.family}>
                <th scope="row">{hypName(a.family)}</th>
                <td>
                  {a.viable ? "viable" : "excluded"} <span className="muted small">— {a.reason}</span>
                </td>
                <td>
                  {a.separation ? (
                    a.separation.separable_by.length ? (
                      a.separation.separable_by.map(testName).join("; ")
                    ) : (
                      <span className="bad">none of the permitted tests</span>
                    )
                  ) : (
                    <span className="muted">not needed</span>
                  )}
                  {a.separation && (
                    <details className="small">
                      <summary>separation detail</summary>
                      <ul>
                        {a.separation.rows.map((r) => (
                          <li key={`${r.test}-${r.quantity}`} className="mono">
                            {testName(r.test)} · {r.quantity}: Δ {r.delta} vs threshold {r.threshold} → {r.separates ? "separates" : "does not separate"}
                          </li>
                        ))}
                      </ul>
                    </details>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {reveal.remedy_check && (
        <div className="reveal-block">
          <h3>Independent check of the simulated maintenance</h3>
          <p>
            <span className={cls("verdict", reveal.remedy_check.passed ? "verdict-pass" : "verdict-fail")}>
              {reveal.remedy_check.passed ? "PASSED" : "FAILED"}
            </span>{" "}
            <span className="muted small">
              {reveal.remedy_check.maintenance_action} · horizon {reveal.remedy_check.horizon_s} s · {reveal.remedy_check.evaluator_version}
            </span>
          </p>
          <ul className="checks">
            {reveal.remedy_check.checks.map((c) => (
              <li key={c.check}>
                <span className={cls("verdict", c.passed ? "verdict-pass" : "verdict-fail")}>{c.passed ? "pass" : "fail"}</span> {c.check}
                <span className="mono small muted">
                  {" "}
                  {Object.entries(c)
                    .filter(([k]) => k !== "check" && k !== "passed")
                    .map(([k, v]) => `${k}=${val(v)}`)
                    .join(", ")}
                </span>
              </li>
            ))}
          </ul>
          {reveal.remedy_check.note && <p className="small muted">{reveal.remedy_check.note}</p>}
        </div>
      )}

      {kind === "twin" && reveal.twin && (
        <div className="reveal-block">
          <h3>Twin slot mapping</h3>
          <p>
            Picked slot: <strong>{reveal.twin.picked_slot === "alpha" ? "System α" : reveal.twin.picked_slot === "beta" ? "System β" : reveal.twin.picked_slot}</strong>{" "}
            <span className="muted small">(pair {reveal.twin.pair_id})</span>
          </p>
          <ul className="twin-map">
            {Object.entries(reveal.twin.slot_labels).map(([slot, label]) => (
              <li key={slot} className={cls(slot === reveal.twin?.picked_slot && "picked")}>
                <strong>{slot === "alpha" ? "System α" : slot === "beta" ? "System β" : slot}</strong>: {label}
                {slot === reveal.twin?.picked_slot ? " (investigated)" : ""}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="reveal-block">
        <h3>Omniscient view: true level vs LT-101</h3>
        <TimeChart
          tone="judge"
          series={[
            { key: "true", label: "true level", color: "var(--judge)", points: trace.map((p) => ({ t: p.t_s, v: p.true_level_m })), width: 2.2 },
            ...(trace.some((p) => isNum(p.sensed_level_m))
              ? [{ key: "sensed", label: "LT-101 sensed (noise-free)", color: "var(--judge-2)", points: trace.map((p) => ({ t: p.t_s, v: p.sensed_level_m as number })), dash: "5 4" }]
              : []),
            { key: "logged", label: "LT-101 logged", color: "var(--measure)", points: logged.map((s) => ({ t: s.t_s, v: s.LT101_m })), width: 1.1, opacity: 0.8 },
          ]}
          xDomain={[t0, t1 + 30]}
          yLabel="level"
          yUnit="m"
          yMinSpan={0.08}
          height={190}
          ariaLabel="Judge-only chart: simulator true level compared with the LT-101 reading."
        />
        <Legend
          items={[
            { label: "true level (simulator, hidden during the run)", color: "var(--judge)", shape: "line" },
            { label: "LT-101 sensed, noise-free", color: "var(--judge-2)", shape: "dash" },
            { label: "LT-101 logged reading", color: "var(--measure)", shape: "line" },
          ]}
        />
      </div>

      <details className="reveal-block">
        <summary>Hidden case parameters</summary>
        <table className="kv">
          <tbody>
            {Object.entries(reveal.hidden_parameters ?? {}).map(([k, v]) => (
              <tr key={k}>
                <th scope="row" className="mono">{k}</th>
                <td className="mono">{val(v)}</td>
              </tr>
            ))}
            {Object.entries(reveal.model_mismatch ?? {}).map(([k, v]) => (
              <tr key={`mm-${k}`}>
                <th scope="row" className="mono">mismatch.{k}</th>
                <td className="mono">{val(v)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </section>
  );
}
