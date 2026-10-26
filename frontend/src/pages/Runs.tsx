// Runs / evidence replay list (#/ and #/runs).
import { useCallback, useEffect, useState } from "react";
import { api, errorText } from "../api/client";
import type { RunListItem } from "../api/types";
import { EmptyState, ErrorBox, ModeBadge, Skeleton } from "../components/common";
import { cls, fmtDateTime, hypName, kindLabel, runStatusLabel } from "../lib/format";
import { runHref } from "../lib/router";
import { isTerminal } from "../lib/runModel";

export function RunsPage() {
  const [runs, setRuns] = useState<RunListItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setRuns(await api.runs());
      setError(null);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>Investigations</h1>
          <p className="lede">
            Recorded runs on the simulated T-101 / P-101 system. Open one to continue it on the workstation, or replay a finished one from its
            event log.
          </p>
        </div>
        <div className="btn-row">
          <a className="btn btn-primary" href="#/twin">
            New Twin Challenge
          </a>
          <a className="btn" href="#/blind">
            New Blind Challenge
          </a>
          <a className="btn" href="#/guided">
            Guided example
          </a>
          <button type="button" className="btn btn-ghost" onClick={() => void load()} disabled={loading}>
            {loading ? "Refreshing…" : "Refresh"}
          </button>
        </div>
      </div>

      {error && (
        <ErrorBox title="Could not list runs" message={error}>
          <button type="button" className="btn btn-sm" onClick={() => void load()}>
            Retry
          </button>
        </ErrorBox>
      )}
      {loading && !runs && <Skeleton lines={6} />}
      {runs && runs.length === 0 && (
        <EmptyState title="No recorded runs yet">
          <p>
            Start with the <a href="#/twin">Twin Challenge</a>, set up a <a href="#/blind">Blind Challenge</a>, or try the{" "}
            <a href="#/guided">guided example</a> (works offline with the reference procedure).
          </p>
        </EmptyState>
      )}
      {runs && runs.length > 0 && (
        <div className="table-wrap">
          <table className="runs-table">
            <caption className="sr-only">Recorded runs, newest first</caption>
            <thead>
              <tr>
                <th scope="col">Mode</th>
                <th scope="col">Run</th>
                <th scope="col">Kind</th>
                <th scope="col">Status</th>
                <th scope="col">Outcome</th>
                <th scope="col">Warning</th>
                <th scope="col">Created</th>
                <th scope="col">
                  <span className="sr-only">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {runs.map((r) => (
                <tr key={r.id}>
                  <td>
                    <ModeBadge
                      mode={r.mode}
                      size="sm"
                      providerName={r.provider?.name}
                      recordedMode={
                        r.mode === "replay" && (r.recorded_mode === "live" || r.recorded_mode === "reference")
                          ? r.recorded_mode
                          : undefined
                      }
                    />
                  </td>
                  <td>
                    <a className="mono" href={runHref(r.id)}>
                      {r.id}
                    </a>
                  </td>
                  <td>{kindLabel(r.kind)}</td>
                  <td>
                    <span className={cls("status-tag", `status-${r.status}`)}>{runStatusLabel(r.status)}</span>
                    {r.revealed && <span className="chip chip-judge">revealed</span>}
                  </td>
                  <td>
                    {r.outcome ? (
                      <>
                        {r.outcome}
                        {r.primary_hypothesis ? `: ${hypName(r.primary_hypothesis)}` : ""}
                      </>
                    ) : (
                      <span className="muted">—</span>
                    )}
                  </td>
                  <td>
                    {r.warning.map((w) => (
                      <span key={w} className="chip chip-alarm">
                        {w}
                      </span>
                    ))}
                  </td>
                  <td className="tnum small">{fmtDateTime(r.created_at)}</td>
                  <td className="actions">
                    <a className="btn btn-xs" href={runHref(r.id)}>
                      Open
                    </a>
                    {isTerminal(r.status) && (
                      <a className="btn btn-xs" href={runHref(r.id, true)}>
                        Replay
                      </a>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
