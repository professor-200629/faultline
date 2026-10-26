// State machine strip and budget meters.
import type { Budgets, Counters, InvestigatorMode } from "../api/types";
import { cls, fmt, fmtInt, fmtUsd, isNum, runStatusLabel } from "../lib/format";

const MAIN = ["ready", "investigating", "awaiting_approval"];
const ENDS = ["diagnosed", "inconclusive", "failed", "cancelled"];

export function StateStrip({ status, visited, reason }: { status: string; visited: Set<string>; reason: string }) {
  const node = (s: string) => {
    const current = s === status;
    const past = !current && visited.has(s);
    return (
      <li key={s} className={cls("state", current && "state-current", past && "state-past", `state-${s}`)} aria-current={current ? "step" : undefined}>
        {runStatusLabel(s)}
        {current && <span className="sr-only"> (current state)</span>}
      </li>
    );
  };
  return (
    <div className="state-strip-wrap">
      <ol className="state-strip" aria-label="Run state machine">
        {MAIN.map(node)}
        <li className="state-ends-group">
          <ul className="state-ends" aria-label="terminal states">
            {ENDS.map(node)}
          </ul>
        </li>
      </ol>
      {reason && (
        <p className="state-reason">
          <span className="muted">reason:</span> {reason}
        </p>
      )}
    </div>
  );
}

function Meter({ label, used, max, unit, digits = 0 }: { label: string; used: number | null; max: number | null; unit?: string; digits?: number }) {
  const pct = isNum(used) && isNum(max) && max > 0 ? Math.min(100, (used / max) * 100) : 0;
  const tone = pct >= 100 ? "full" : pct >= 75 ? "high" : "ok";
  return (
    <div className="meter">
      <div className="meter-head">
        <span>{label}</span>
        <span className="mono tnum">
          {isNum(used) ? used.toFixed(digits) : "—"} / {isNum(max) ? max.toFixed(digits) : "—"}
          {unit ? ` ${unit}` : ""}
        </span>
      </div>
      <div
        className={cls("meter-bar", `meter-${tone}`)}
        role="meter"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={isNum(max) ? max : undefined}
        aria-valuenow={isNum(used) ? used : undefined}
      >
        <span style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

export function BudgetMeters({
  budgets,
  counters,
  wallUsedS,
  simUsedS,
  simLimitS,
  mode,
}: {
  budgets: Budgets | null;
  counters: Partial<Counters>;
  wallUsedS: number | null;
  simUsedS: number | null;
  simLimitS: number | null;
  /** The investigator's mode; for an imported replay pass the recorded mode, never "replay". */
  mode: InvestigatorMode;
}) {
  const isModel = mode === "live";
  return (
    <div className="meters">
      <Meter label="Tool calls" used={isNum(counters.tool_calls) ? counters.tool_calls : mode === "unstarted" ? 0 : null} max={budgets?.max_tool_calls ?? null} />
      <Meter
        label={isModel ? "Model calls" : mode === "reference" ? "Procedure steps (model-call budget)" : "Model calls"}
        used={isNum(counters.model_calls) ? counters.model_calls : mode === "unstarted" ? 0 : null}
        max={budgets?.max_model_calls ?? null}
      />
      <Meter label="Wall clock" used={wallUsedS ?? (mode === "unstarted" ? 0 : null)} max={budgets?.wall_clock_s ?? null} unit="s" digits={1} />
      <Meter label="Simulated time" used={simUsedS} max={simLimitS} unit="s" />
      <dl className="token-stats">
        <div>
          <dt>tokens in / out</dt>
          <dd className="mono tnum">
            {mode === "reference" ? "none (not a model)" : `${fmtInt(counters.prompt_tokens)} / ${fmtInt(counters.completion_tokens)}`}
          </dd>
        </div>
        {isModel && isNum(counters.reasoning_tokens) && counters.reasoning_tokens > 0 && (
          <div>
            <dt>reasoning tokens</dt>
            <dd className="mono tnum">{fmtInt(counters.reasoning_tokens)}</dd>
          </div>
        )}
        <div>
          <dt>est. cost</dt>
          <dd className="mono tnum">{mode === "reference" ? "$0 (no provider)" : fmtUsd(counters.estimated_cost_usd)}</dd>
        </div>
        <div>
          <dt>rejected / provider failures</dt>
          <dd className="mono tnum">
            {fmtInt(counters.rejected_tool_calls)} / {fmtInt(counters.provider_failures)}
          </dd>
        </div>
        {isModel && isNum(counters.model_calls) && isNum(counters.usage_reported_calls) && (
          <div>
            <dt>usage reported</dt>
            <dd className="mono tnum">
              {counters.usage_reported_calls} of {counters.model_calls} calls
            </dd>
          </div>
        )}
      </dl>
      {isNum(budgets?.request_timeout_s) && (
        <p className="fineprint">
          Per-request timeout {fmt(budgets?.request_timeout_s, 0)} s, up to {budgets?.max_retries} retries; every retry counts as a model call.
        </p>
      )}
    </div>
  );
}
