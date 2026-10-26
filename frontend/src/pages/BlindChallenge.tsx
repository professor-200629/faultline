// Blind Challenge (#/blind): a judge picks a fault preset; the server returns an opaque run ID.
import { useEffect, useState } from "react";
import { api, errorText } from "../api/client";
import type { Presets } from "../api/types";
import { ErrorBox, Skeleton } from "../components/common";
import { hypName, humanize, siteLabel, siteValue } from "../lib/format";
import { navigate, runHref } from "../lib/router";

export function BlindChallengePage() {
  const [presets, setPresets] = useState<Presets | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [family, setFamily] = useState("");
  const [severity, setSeverity] = useState("");
  const [profile, setProfile] = useState("standard");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    api.judgePresets().then(
      (p) => alive && setPresets(p),
      (e) => alive && setLoadError(errorText(e)),
    );
    return () => {
      alive = false;
    };
  }, []);

  const severities = family && presets ? presets.families[family] ?? [] : [];
  const reset = () => {
    setFamily("");
    setSeverity("");
    setProfile("standard");
  };

  const submit = async () => {
    setBusy(true);
    setError(null);
    const f = family;
    const s = severity;
    const p = profile;
    reset(); // the choice is not kept in the page
    try {
      const { run_id } = await api.createBlind(f, s, p);
      navigate(runHref(run_id));
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>Blind Challenge</h1>
          <p className="lede">
            Choose a hidden fault for the investigator. Pick it without the screen being recorded or watched, then hand over.
          </p>
        </div>
      </div>
      <div className="two-col">
        <section className="panel form-panel" aria-label="Blind challenge setup">
          {loadError && <ErrorBox title="Judge controls unavailable" message={loadError} />}
          {!presets && !loadError && <Skeleton lines={5} />}
          {presets && (
            <form
              autoComplete="off"
              onSubmit={(e) => {
                e.preventDefault();
                if (family && severity) void submit();
              }}
            >
              <div className="field">
                <label htmlFor="blind-family">Fault family</label>
                <select
                  id="blind-family"
                  value={family}
                  onChange={(e) => {
                    setFamily(e.target.value);
                    setSeverity("");
                  }}
                  required
                >
                  <option value="">Choose…</option>
                  {Object.keys(presets.families).map((f) => (
                    <option key={f} value={f}>
                      {hypName(f)}
                    </option>
                  ))}
                </select>
              </div>
              <div className="field">
                <label htmlFor="blind-severity">Severity / variant</label>
                <select id="blind-severity" value={severity} onChange={(e) => setSeverity(e.target.value)} disabled={!family} required>
                  <option value="">{family ? "Choose…" : "Choose a family first"}</option>
                  {severities.map((s) => (
                    <option key={s} value={s}>
                      {humanize(s)}
                    </option>
                  ))}
                </select>
              </div>
              <div className="field">
                <label htmlFor="blind-site">Site profile</label>
                <select id="blind-site" value={profile} onChange={(e) => setProfile(e.target.value)}>
                  {Object.keys(presets.site_profiles).map((k) => (
                    <option key={k} value={k}>
                      {k.replace(/_/g, " ")}
                    </option>
                  ))}
                </select>
              </div>
              {presets.site_profiles[profile] && (
                <dl className="kv-list compact">
                  {Object.entries(presets.site_profiles[profile]).map(([k, v]) => (
                    <div key={k}>
                      <dt>{siteLabel(k)}</dt>
                      <dd>{siteValue(k, v)}</dd>
                    </div>
                  ))}
                </dl>
              )}
              <button type="submit" className="btn btn-primary" disabled={!family || !severity || busy}>
                {busy ? "Sealing the case…" : "Seal the case and open the run"}
              </button>
            </form>
          )}
          {error && <ErrorBox title="Could not create the run" message={error} />}
        </section>
        <section className="panel" aria-label="Privacy">
          <h2 className="panel-title">What stays secret</h2>
          <ul className="plain-list">
            <li>The server builds the case and returns an opaque random run ID. Nothing in the ID encodes the fault.</li>
            <li>The form resets as soon as you submit. Your choice is not kept in this page, in the URL or in browser storage.</li>
            <li>The investigation screen receives only logged readings and measurement results; the case stays in a sealed table.</li>
            <li>Ground truth appears only after a judge reveals a run that has ended.</li>
          </ul>
          <p className="hint">Judge controls work only from this computer (loopback) and need the judge session the page opens for you.</p>
        </section>
      </div>
    </div>
  );
}
