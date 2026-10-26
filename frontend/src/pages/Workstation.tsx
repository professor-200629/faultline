// Workstation (#/run/:id): equipment + trends | timeline | hypotheses + controls.
// Also hosts REPLAY (#/run/:id/replay) and the guided coach marks (#/guided/:id).
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { RunEvent, RunView } from "../api/types";
import { CoachMarks, type CoachStep } from "../components/CoachMarks";
import { EmptyState, ErrorBox, ModeBadge, Panel, Skeleton } from "../components/common";
import { EquipmentView } from "../components/Equipment";
import { HypothesisBoard } from "../components/HypothesisBoard";
import { RevealPanel } from "../components/RevealPanel";
import { RunControls } from "../components/RunControls";
import { BudgetMeters, StateStrip } from "../components/RunStatus";
import { Timeline } from "../components/Timeline";
import { MeasuredTrends } from "../components/Trends";
import { useAppData } from "../lib/appData";
import { cls, fmtDateTime, kindLabel, modeLabel, siteLabel, siteValue } from "../lib/format";
import { runHref } from "../lib/router";
import { buildLiveModel, buildReplayModel, HYPOTHESIS_ORDER, investigatorMode, isImportedReplay, isTerminal, recordedAt } from "../lib/runModel";
import { useRun } from "../lib/useRun";

function visibleInTimeline(e: RunEvent): boolean {
  if (e.type === "budget") return false;
  if (e.type === "model_request") {
    const a = typeof e.payload.attempt === "number" ? e.payload.attempt : 1;
    return a > 1 || !!e.payload.forced_submit;
  }
  return true;
}

function reducedMotion(): boolean {
  return window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
}

// ------------------------------------------------------------------ replay
function useReplay(events: RunEvent[], enabled: boolean) {
  const total = events.length;
  const [cursor, setCursor] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState<1 | 4>(1);
  const started = useRef(false);

  useEffect(() => {
    if (enabled && total > 0 && !started.current) {
      started.current = true;
      setCursor(1);
      setPlaying(true);
    }
  }, [enabled, total]);

  useEffect(() => {
    if (!playing) return;
    if (cursor >= total) {
      setPlaying(false);
      return;
    }
    const nextEv = events[cursor];
    const prevEv = events[cursor - 1];
    const gapMs = prevEv ? Math.max(0, (nextEv.at - prevEv.at) * 1000) : 0;
    const base = visibleInTimeline(nextEv) ? Math.min(2000, Math.max(450, gapMs)) : 60;
    const t = window.setTimeout(() => setCursor((c) => Math.min(total, c + 1)), base / speed);
    return () => window.clearTimeout(t);
  }, [playing, cursor, speed, total, events]);

  const stepFwd = () => {
    setPlaying(false);
    setCursor((c) => {
      let n = Math.min(total, c + 1);
      while (n < total && !visibleInTimeline(events[n - 1])) n++;
      return n;
    });
  };
  const stepBack = () => {
    setPlaying(false);
    setCursor((c) => {
      let n = Math.max(0, c - 1);
      while (n > 0 && !visibleInTimeline(events[n - 1])) n--;
      return n;
    });
  };
  const restart = () => {
    setCursor(0);
    setPlaying(true);
  };
  return { cursor, setCursor, playing, setPlaying, speed, setSpeed, stepFwd, stepBack, restart, total };
}

function ReplayControls({ r, view }: { r: ReturnType<typeof useReplay>; view: RunView }) {
  const done = r.cursor >= r.total;
  return (
    <div className="replay-controls">
      <div className="btn-row">
        <button type="button" className="btn btn-sm" onClick={r.restart} aria-label="Restart replay from the beginning">
          Restart
        </button>
        <button type="button" className="btn btn-sm" onClick={r.stepBack} disabled={r.cursor <= 0} aria-label="Step back one entry">
          ◀ Step
        </button>
        <button
          type="button"
          className="btn btn-sm btn-primary"
          onClick={() => (done ? r.restart() : r.setPlaying(!r.playing))}
          aria-label={r.playing ? "Pause replay" : done ? "Replay again" : "Play replay"}
        >
          {r.playing ? "Pause" : done ? "Replay again" : "Play"}
        </button>
        <button type="button" className="btn btn-sm" onClick={r.stepFwd} disabled={done} aria-label="Step forward one entry">
          Step ▶
        </button>
      </div>
      <div className="btn-row" role="group" aria-label="Replay speed">
        <span className="small muted">speed</span>
        {([1, 4] as const).map((s) => (
          <button key={s} type="button" className={cls("btn btn-xs", r.speed === s && "btn-on")} aria-pressed={r.speed === s} onClick={() => r.setSpeed(s)}>
            {s}x
          </button>
        ))}
      </div>
      <label className="replay-scrub">
        <span className="small muted">
          event {r.cursor} of {r.total}
        </span>
        <input
          type="range"
          min={0}
          max={r.total}
          value={r.cursor}
          onChange={(e) => {
            r.setPlaying(false);
            r.setCursor(Number(e.target.value));
          }}
          aria-label="Replay position (events)"
        />
      </label>
      <div className="export-row">
        <a className="btn btn-sm" href={runHref(view.id)}>
          Exit replay
        </a>
        <a className="btn btn-sm" href={`/api/runs/${encodeURIComponent(view.id)}/export.json`} download={`faultline-${view.id}.json`}>
          Export evidence JSON
        </a>
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ guided steps
function guidedSteps(view: RunView, predictionCount: number): CoachStep[] {
  const tags = view.public.warning.map((w) => w.tag).join(", ");
  return [
    {
      target: "warning",
      title: "The warning",
      body: (
        <p>
          The run starts from a warning ({tags}). It says the logged readings disagree with what the datasheet balance predicts. It says that
          something is wrong, not what.
        </p>
      ),
    },
    {
      target: "equipment",
      title: "Measured telemetry vs hidden truth",
      body: (
        <p>
          The diagram shows only what instruments report, each with its time. The hatched fill is what LT-101 <em>indicates</em>; the sensor
          itself could be the fault. The true level stays inside the simulator until a reveal.
        </p>
      ),
    },
    {
      target: "timeline",
      title: "Evidence IDs",
      body: (
        <p>
          Every measurement or test the investigator asks for is computed by the simulator and recorded as evidence E1, E2, and so on. A
          diagnosis must cite these IDs, and the backend rejects IDs that do not exist.
        </p>
      ),
    },
    {
      target: "timeline",
      title: "Predictions are not evidence",
      body: (
        <p>
          The investigator can ask what a test would show if a hypothesis were true. Those answers appear as violet P# cards labelled
          “model-based expectation — not evidence” and cannot be cited. This run has {predictionCount} so far.
        </p>
      ),
    },
    {
      target: "hypotheses",
      title: "Hypothesis board",
      body: (
        <p>
          Four candidate causes, each open, supported, weakened or ruled out, with the evidence that supports or contradicts it. Select an
          evidence chip to find it in the timeline.
        </p>
      ),
    },
    {
      target: "budgets",
      title: "Budgets",
      body: (
        <p>
          Tool calls, model calls, wall clock and simulated plant time are all limited. If a budget runs out the run ends as failed, or the
          investigator must report inconclusive and say which measurement would decide.
        </p>
      ),
    },
    {
      target: "controls",
      title: "Diagnosis is not repair",
      body: (
        <p>
          A diagnosis changes nothing in the plant. When one is submitted you approve or decline the recommended simulated maintenance. You
          then see measured readings after the maintenance; an independent evaluator&apos;s check of the true plant stays sealed until the reveal.
        </p>
      ),
    },
    {
      target: "reveal",
      title: "Reveal",
      body: (
        <p>
          Once the run is terminal, the ground truth can be revealed. It appears in a separate amber panel with the grade and an omniscient
          chart. This guided example can be revealed without a judge session.
        </p>
      ),
    },
  ];
}

// ------------------------------------------------------------------ page
export function Workstation({ id, replay, guide = false }: { id: string; replay: boolean; guide?: boolean }) {
  const { status, catalog } = useAppData();
  const rs = useRun(id, !replay);
  const { view, events, telemetry } = rs;
  const hypIds = useMemo(() => (catalog ? Object.keys(catalog.hypotheses) : HYPOTHESIS_ORDER), [catalog]);
  const replayable = replay && !!view && isTerminal(view.status);
  const r = useReplay(events, replayable);
  const [highlight, setHighlight] = useState<string | null>(null);
  const [coachOpen, setCoachOpen] = useState(guide);
  const centerRef = useRef<HTMLDivElement>(null);
  const guideBtnRef = useRef<HTMLButtonElement>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const restoreGuideFocus = useRef(false);
  const closeCoach = useCallback(() => {
    restoreGuideFocus.current = true;
    setCoachOpen(false);
  }, []);
  // When the guide closes with focus inside it, focus would fall to <body>; return it to
  // "Show guide" (or the run heading). Focus the user moved elsewhere is left alone.
  useEffect(() => {
    if (coachOpen || !restoreGuideFocus.current) return;
    restoreGuideFocus.current = false;
    const active = document.activeElement;
    if (active && active !== document.body && active.isConnected) return;
    (guideBtnRef.current ?? headingRef.current)?.focus();
  }, [coachOpen]);

  const model = useMemo(() => {
    if (!view) return null;
    return replayable ? buildReplayModel(view, events, r.cursor, hypIds) : buildLiveModel(view, events, hypIds);
  }, [view, events, replayable, r.cursor, hypIds]);

  // Telemetry: full historian live; in replay, limited to the simulated time reached so far.
  const samples = useMemo(() => {
    const all = telemetry?.samples ?? [];
    if (!replayable || !model) return all;
    const lim = model.simNowS ?? 0;
    return all.filter((s) => s.t_s <= lim + 1e-6);
  }, [telemetry, replayable, model]);
  const nowS = replayable ? model?.simNowS ?? 0 : telemetry?.now_s ?? model?.simNowS ?? 0;
  const latest = samples.length ? samples[samples.length - 1] : null;

  const visibleCount = model ? model.events.filter(visibleInTimeline).length : 0;
  useEffect(() => {
    const col = centerRef.current;
    if (!col || col.scrollHeight <= col.clientHeight + 4) return;
    const nearBottom = col.scrollHeight - col.scrollTop - col.clientHeight < 140;
    if (nearBottom || (replayable && r.playing)) col.scrollTo({ top: col.scrollHeight, behavior: reducedMotion() ? "auto" : "smooth" });
  }, [visibleCount, replayable, r.playing]);

  const hasReveal = !!model?.reveal;
  useEffect(() => {
    if (hasReveal && !replayable) centerRef.current?.scrollTo({ top: 0, behavior: reducedMotion() ? "auto" : "smooth" });
  }, [hasReveal, replayable]);

  const onEvidence = useCallback((eid: string) => {
    const el = document.getElementById(`tl-ev-${eid}`);
    if (!el) return;
    el.scrollIntoView({ block: "center", behavior: reducedMotion() ? "auto" : "smooth" });
    el.focus({ preventScroll: true });
    setHighlight(eid);
    window.setTimeout(() => setHighlight((h) => (h === eid ? null : h)), 1800);
  }, []);

  if (rs.loading) {
    return (
      <div className="ws" aria-busy="true">
        <div className="run-head">
          <Skeleton lines={2} />
        </div>
        <div className="ws-grid">
          <div className="ws-col">
            <Skeleton height={280} />
            <Skeleton height={200} />
          </div>
          <div className="ws-col">
            <Skeleton lines={8} />
          </div>
          <div className="ws-col">
            <Skeleton height={160} />
            <Skeleton lines={6} />
          </div>
        </div>
      </div>
    );
  }
  if (rs.error || !view || !model) {
    return (
      <div className="page">
        <ErrorBox title="Could not load run" message={rs.error ?? "unknown error"}>
          <a className="btn btn-sm" href="#/">
            Back to runs
          </a>
          <button type="button" className="btn btn-sm" onClick={() => window.location.reload()}>
            Retry
          </button>
        </ErrorBox>
      </div>
    );
  }
  if (replay && !replayable) {
    return (
      <div className="page">
        <EmptyState title="Replay is available once the run has ended">
          <p>
            Run <span className="mono">{view.id}</span> is {view.status}.{" "}
            <a href={runHref(view.id)}>Open the live workstation</a>.
          </p>
        </EmptyState>
      </div>
    );
  }

  const knownEvidence = new Set(model.evidence.map((e) => e.evidence_id));
  const timelineEvents = model.events;
  const providerModel = view.provider?.model;
  // Imported recordings have mode "replay"; steps, budgets and labels follow the RECORDED mode.
  const imported = isImportedReplay(view);
  const invMode = investigatorMode(view, events);
  const invModeText = `${modeLabel(invMode)}${invMode === "reference" ? " (deterministic, not AI)" : ""}`;

  return (
    <div className={cls("ws", replayable && "ws-replay")}>
      {replayable && (
        <div className="replay-banner" role="status">
          <strong>REPLAY</strong> of {imported ? "imported recording" : "recorded run"} <span className="mono">{view.id}</span> — recorded{" "}
          {fmtDateTime(recordedAt(view))}, mode {invModeText}, model <span className="mono">{providerModel ?? "—"}</span>. Nothing here is
          happening now.
        </div>
      )}
      {imported && !replayable && (
        <div className="replay-banner" role="status">
          <strong>IMPORTED RECORDING</strong> <span className="mono">{view.id}</span> — recorded {fmtDateTime(recordedAt(view))}, mode{" "}
          {invModeText}, model <span className="mono">{providerModel ?? "—"}</span>. Nothing here is happening now; it cannot be started or
          revealed.{" "}
          {isTerminal(view.status) && <a href={runHref(view.id, true)}>Play it back step by step</a>}
        </div>
      )}
      {rs.pollError && !replayable && (
        <div className="banner banner-warn" role="status">
          Live updates interrupted: {rs.pollError}.{" "}
          {rs.pollRetrying ? (
            "Retrying…"
          ) : (
            <button type="button" className="btn btn-xs" onClick={() => void rs.refresh()}>
              Retry now
            </button>
          )}
        </div>
      )}

      <header className="run-head">
        <div className="run-head-row">
          <ModeBadge
            mode={view.mode}
            replay={replayable}
            recordedMode={imported ? invMode : undefined}
            size="lg"
            model={providerModel}
            providerName={view.provider?.name}
          />
          <div className="run-id">
            <div className="run-id-main">
              <h1 className="run-id-h1" ref={headingRef} tabIndex={-1}>
                <span className="run-id-label">{replayable ? "Replay of run" : "Run"}</span> <span className="mono">{view.id}</span>
              </h1>
              {view.kind === "guided" && !coachOpen && !replayable && (
                <button type="button" className="btn btn-xs" ref={guideBtnRef} onClick={() => setCoachOpen(true)}>
                  Show guide
                </button>
              )}
            </div>
            <span className="muted small">
              {kindLabel(view.kind)} · created {fmtDateTime(view.created_at)}
            </span>
          </div>
          <StateStrip status={model.status} visited={model.visited} reason={model.statusReason} />
        </div>
        <div className="run-head-row warning-row" data-coach="warning">
          {view.public.warning.map((w) => (
            <p key={w.tag} className="warning">
              <span className="chip chip-alarm">{w.tag}</span> {w.text}
            </p>
          ))}
        </div>
      </header>

      <div className="ws-grid">
        <div className="ws-col ws-left">
          <Panel title="Equipment" subtitle={view.public.situation} coach="equipment">
            <EquipmentView nominal={view.public.nominal} latest={latest} evidence={model.evidence} site={view.public.site} />
          </Panel>
          <Panel title="Measured trends" coach="trends">
            {rs.telemetryError && !telemetry ? (
              <ErrorBox title="Telemetry unavailable" message={rs.telemetryError} />
            ) : !telemetry ? (
              <Skeleton height={300} />
            ) : (
              <MeasuredTrends samples={samples} nowS={nowS} evidence={model.evidence} nominal={view.public.nominal} note={telemetry.note} clipped={replayable} />
            )}
          </Panel>
          <Panel title="Site conditions">
            <dl className="kv-list">
              {Object.entries(view.public.site).map(([k, v]) => (
                <div key={k}>
                  <dt>{siteLabel(k)}</dt>
                  <dd>{siteValue(k, v)}</dd>
                </div>
              ))}
            </dl>
          </Panel>
        </div>

        <div className="ws-col ws-center" ref={centerRef}>
          {model.reveal && <RevealPanel reveal={model.reveal} kind={view.kind} logged={samples} />}
          <Panel
            title="Investigation timeline"
            coach="timeline"
            subtitle={
              (imported ? "Recorded: " : "") +
              (invMode === "live"
                ? "Agent steps with their stated purpose; every observation is computed by the simulator."
                : invMode === "reference"
                  ? "Deterministic reference procedure steps (not AI); every observation is computed by the simulator."
                  : imported
                    ? "the recording does not name its investigator."
                    : "No investigator has started yet.")
            }
          >
            {timelineEvents.filter(visibleInTimeline).length === 0 ? (
              <EmptyState title="No events yet" />
            ) : (
              <Timeline
                events={timelineEvents}
                mode={invMode}
                highlight={highlight}
                predictions={model.predictions}
                busy={rs.loading}
                quiet={replayable && r.playing && r.speed > 1}
              />
            )}
            {model.status === "investigating" && !replayable && !imported && (
              <p className="working" role="status">
                <span className="working-dot" aria-hidden="true" /> {invMode === "live" ? "Waiting for the agent…" : "Procedure running…"}
              </p>
            )}
          </Panel>
        </div>

        <div className="ws-col ws-right">
          <Panel title={replayable ? "Replay controls" : "Run controls"} coach="controls">
            {replayable ? <ReplayControls r={r} view={view} /> : <RunControls view={view} model={model} status={status} onChanged={rs.refresh} />}
          </Panel>
          <Panel title="Hypotheses" coach="hypotheses" subtitle="Status as recorded by the investigator; chips are evidence IDs.">
            <HypothesisBoard
              board={model.board}
              descriptions={catalog?.hypotheses ?? null}
              diagnosis={model.diagnosis}
              knownEvidence={knownEvidence}
              onEvidence={onEvidence}
            />
          </Panel>
          <Panel title="Budgets" coach="budgets">
            <BudgetMeters
              budgets={view.budgets}
              counters={model.counters}
              wallUsedS={model.wallUsedS}
              simUsedS={model.simUsedS}
              simLimitS={model.simLimitS}
              mode={invMode}
            />
          </Panel>
        </div>
      </div>

      {coachOpen && !replayable && <CoachMarks steps={guidedSteps(view, model.predictions.length)} onClose={closeCoach} />}
    </div>
  );
}
