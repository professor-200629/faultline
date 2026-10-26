// Run controls: start (LIVE / reference), cancel, approve/decline simulated maintenance,
// judge reveal, exports and replay entry. API errors are shown verbatim.
import { useEffect, useRef, useState } from "react";
import { api, errorText } from "../api/client";
import type { RunView, StatusResponse } from "../api/types";
import { useAppData } from "../lib/appData";
import { remedyName } from "../lib/format";
import { runHref } from "../lib/router";
import { isImportedReplay, isTerminal, type RunModel } from "../lib/runModel";

interface Props {
  view: RunView;
  model: RunModel;
  status: StatusResponse | null;
  onChanged: () => Promise<RunView | null>;
}

interface ActionError {
  action: string;
  text: string;
  /** The run status this error belongs to; it is hidden once the run moves on. */
  status: string;
}

export function RunControls({ view, model, status, onChanged }: Props) {
  const { refreshStatus } = useAppData();
  const [busy, setBusy] = useState<string | null>(null);
  const busyRef = useRef<string | null>(null);
  const [error, setError] = useState<ActionError | null>(null);
  const id = view.id;
  const st = model.status;
  const keyConfigured = status?.provider.key_configured ?? false;
  const terminal = isTerminal(st);
  const imported = isImportedReplay(view);

  const rootRef = useRef<HTMLDivElement>(null);
  const startRef = useRef<HTMLButtonElement>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);
  const approveRef = useRef<HTMLButtonElement>(null);
  const revealRef = useRef<HTMLButtonElement>(null);

  const run = async (action: string, fn: () => Promise<unknown>) => {
    if (busyRef.current) return; // ignore repeat clicks until the refreshed run is shown
    busyRef.current = action;
    setBusy(action);
    setError(null);
    const atStatus = st;
    let failed: string | null = null;
    try {
      await fn();
    } catch (e) {
      failed = errorText(e);
      setError({ action, text: failed, status: atStatus });
    }
    try {
      // Stay busy until the refresh lands, so the buttons cannot fire a duplicate request.
      const fresh = await onChanged();
      if (failed !== null && fresh) {
        const text = failed;
        setError({ action, text, status: fresh.status });
      }
    } finally {
      busyRef.current = null;
      setBusy(null);
    }
    if (action === "start-live" || action === "reveal") void refreshStatus();
  };

  // When an action removes the focused control (start, approve, cancel, reveal), focus
  // would fall to <body>. Move it to the next primary control instead. Polling changes
  // never steal focus from elsewhere on the page.
  const prev = useRef({ st, revealed: !!model.reveal });
  useEffect(() => {
    const was = prev.current;
    const revealed = !!model.reveal;
    prev.current = { st, revealed };
    if (was.st === st && was.revealed === revealed) return;
    const active = document.activeElement;
    const lost = !active || active === document.body || (rootRef.current?.contains(active) ?? false);
    if (!lost) return;
    if (revealed && !was.revealed) {
      document.getElementById("reveal-h")?.focus({ preventScroll: true });
      return;
    }
    const target =
      st === "ready"
        ? startRef.current
        : st === "investigating"
          ? cancelRef.current
          : st === "awaiting_approval"
            ? approveRef.current
            : revealRef.current && !revealRef.current.disabled
              ? revealRef.current
              : null;
    (target ?? rootRef.current)?.focus({ preventScroll: true });
  }, [st, model.reveal]);

  const revealReason = model.reveal
    ? null
    : st === "awaiting_approval"
      ? "Approve or decline the simulated maintenance first; ground truth is revealed only after the run is terminal."
      : !terminal
        ? "Available once the run is terminal (diagnosed, inconclusive, failed or cancelled)."
        : null;
  const guided = view.kind === "guided";
  const isBusy = busy !== null;
  // aria-disabled (not disabled) while busy, so the focused button is not blurred.
  const busyAttr = isBusy ? ({ "aria-disabled": true } as const) : {};
  const shownError = error && error.status === st ? error : null;

  return (
    <div className="controls" ref={rootRef} tabIndex={-1} aria-busy={isBusy ? "true" : "false"}>
      {imported && (
        <p className="hint">
          Imported recording: it cannot be started, continued or revealed. Any reveal recorded with it is shown in the judge-only panel.
        </p>
      )}

      {st === "ready" && !imported && (
        <div className="control-group" data-coach="start">
          <button
            type="button"
            className="btn btn-live"
            disabled={!keyConfigured}
            {...busyAttr}
            ref={keyConfigured ? startRef : undefined}
            aria-describedby={!keyConfigured ? "live-why" : undefined}
            onClick={() => void run("start-live", () => api.start(id, "live"))}
          >
            {busy === "start-live" ? "Starting…" : "Start LIVE investigation"}
            <span className="btn-sub">NVIDIA Nemotron via Nebius Token Factory</span>
          </button>
          {!keyConfigured && (
            <p id="live-why" className="hint">
              LIVE is unavailable: {status ? "the server has no NEBIUS_API_KEY configured." : "integration status is unknown."} There is no
              scripted substitute.
            </p>
          )}
          <button
            type="button"
            className="btn btn-ref"
            {...busyAttr}
            ref={keyConfigured ? undefined : startRef}
            onClick={() => void run("start-ref", () => api.start(id, "reference"))}
          >
            {busy === "start-ref" ? "Starting…" : "Start reference procedure"}
            <span className="btn-sub">deterministic baseline, not AI</span>
          </button>
        </div>
      )}

      {st === "investigating" && !imported && (
        <div className="control-group">
          <p className="hint">
            {model.mode === "live" ? "The agent is choosing measurements through validated tools." : "The deterministic reference procedure is running."}
          </p>
          <button type="button" className="btn btn-danger" ref={cancelRef} {...busyAttr} onClick={() => void run("cancel", () => api.cancel(id))}>
            {busy === "cancel" ? "Cancelling…" : "Cancel investigation"}
          </button>
        </div>
      )}

      {st === "awaiting_approval" && !imported && (
        <div className="control-group approval" data-coach="approval">
          <p className="approval-title">
            Recommended simulated maintenance: <strong>{remedyName(model.diagnosis?.recommended_remedy)}</strong>
          </p>
          <p className="hint">
            Diagnosis is separate from repair. Approving applies the recommended simulated maintenance and logs public readings afterwards; an
            independent evaluator also checks the true plant, and that result is shown at the reveal.
          </p>
          <div className="btn-row">
            <button type="button" className="btn btn-primary" ref={approveRef} {...busyAttr} onClick={() => void run("approve", () => api.remedy(id, true))}>
              {busy === "approve" ? "Applying…" : "Approve simulated maintenance"}
            </button>
            <button type="button" className="btn" {...busyAttr} onClick={() => void run("decline", () => api.remedy(id, false))}>
              {busy === "decline" ? "Declining…" : "Decline"}
            </button>
          </div>
        </div>
      )}

      {shownError && (
        <div className="error-box" role="alert">
          <strong>{shownError.action.startsWith("start") ? "Could not start" : "Request failed"}:</strong>{" "}
          <span className="error-text">{shownError.text}</span>
        </div>
      )}

      <div className="control-group" data-coach="reveal">
        {model.reveal ? (
          <p className="hint judge-hint">
            {imported ? "This recording includes its reveal. See the judge-only panel." : "Ground truth has been revealed. See the judge-only panel."}
          </p>
        ) : imported ? (
          <p className="hint judge-hint">No reveal was recorded with this run, and a replay cannot be revealed.</p>
        ) : (
          <>
            <button
              type="button"
              className="btn btn-judge"
              ref={revealRef}
              disabled={!!revealReason}
              {...busyAttr}
              aria-describedby={revealReason ? "reveal-why" : undefined}
              onClick={() => void run("reveal", () => (guided ? api.revealGuided(id) : api.judgeReveal(id)))}
            >
              {busy === "reveal" ? "Revealing…" : guided ? "Reveal ground truth (guided example)" : "Reveal ground truth (judge)"}
            </button>
            <p id="reveal-why" className="hint">
              {revealReason ?? (guided ? "Guided examples can be revealed without a judge session." : "Requires the judge session on this computer.")}
            </p>
          </>
        )}
      </div>

      <div className="control-group export-row">
        <a className="btn btn-sm" href={api.exportJsonUrl(id)} download={`faultline-${id}.json`}>
          Export evidence JSON
        </a>
        <a className="btn btn-sm" href={api.reportMdUrl(id)} download={`faultline-${id}.md`}>
          Report Markdown
        </a>
        {terminal && (
          <a className="btn btn-sm" href={runHref(id, true)}>
            Replay
          </a>
        )}
      </div>
    </div>
  );
}
