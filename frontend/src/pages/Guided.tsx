// Guided example (#/guided): creates a sealed teaching run, starts it, and opens the
// workstation with coach marks (#/guided/:id).
import { useState } from "react";
import { api, errorText } from "../api/client";
import { ErrorBox } from "../components/common";
import { useAppData } from "../lib/appData";
import { navigate } from "../lib/router";

export function GuidedIntro() {
  const { status } = useAppData();
  const keyConfigured = status?.provider.key_configured ?? false;
  const [mode, setMode] = useState<"reference" | "live">("reference");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<{ text: string; runId: string | null } | null>(null);

  const go = async () => {
    setBusy(true);
    setError(null);
    let runId: string | null = null;
    try {
      runId = (await api.guided()).run_id;
      await api.start(runId, mode);
      navigate(`/guided/${encodeURIComponent(runId)}`);
    } catch (e) {
      setError({ text: errorText(e), runId });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="page narrow">
      <h1>Guided example</h1>
      <p className="lede">
        A short tour of the workstation on a sealed teaching case. You will see what is measured, what stays hidden, how evidence is cited,
        and why a diagnosis is separate from repair.
      </p>
      <section className="panel form-panel" aria-label="Guided example setup">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void go();
          }}
        >
          <fieldset className="field">
            <legend>Who investigates</legend>
            <label className="radio-card">
              <input type="radio" name="gmode" value="reference" checked={mode === "reference"} onChange={() => setMode("reference")} />
              <span>
                <strong>Reference procedure</strong> <span className="muted">(default)</span>
                <span className="small muted block">Deterministic baseline, not AI. Works offline.</span>
              </span>
            </label>
            <label className="radio-card">
              <input
                type="radio"
                name="gmode"
                value="live"
                checked={mode === "live"}
                onChange={() => setMode("live")}
                disabled={!keyConfigured}
                aria-describedby={!keyConfigured ? "g-live-why" : undefined}
              />
              <span>
                <strong>LIVE</strong>
                <span className="small muted block">NVIDIA Nemotron via Nebius Token Factory{status ? ` (${status.provider.model})` : ""}.</span>
                {!keyConfigured && (
                  <span id="g-live-why" className="small bad block">
                    {status
                      ? "Unavailable: the server has no NEBIUS_API_KEY configured."
                      : "Unavailable: integration status is unknown (backend not reachable)."}
                  </span>
                )}
              </span>
            </label>
          </fieldset>
          <button type="submit" className="btn btn-primary" disabled={busy}>
            {busy ? "Preparing…" : "Start the guided example"}
          </button>
        </form>
        {error && (
          <ErrorBox title="Could not start" message={error.text}>
            {error.runId && (
              <a className="btn btn-sm" href={`#/guided/${encodeURIComponent(error.runId)}`}>
                Open the run anyway
              </a>
            )}
          </ErrorBox>
        )}
      </section>
      <p className="hint">The teaching case is chosen by the app, not by a judge, so it can be revealed without a judge session once it ends.</p>
    </div>
  );
}
