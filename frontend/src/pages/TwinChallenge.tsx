// Twin Challenge (#/twin): two systems with the same warning and different faults.
import { useEffect, useMemo, useRef, useState } from "react";
import { api, errorText } from "../api/client";
import type { Presets, TwinCard, TwinChallenge } from "../api/types";
import { Legend, TimeChart } from "../components/charts";
import { ErrorBox, Skeleton } from "../components/common";
import { useAppData } from "../lib/appData";
import { fmt, fmtSigned, hypName, siteLabel, siteValue } from "../lib/format";
import { navigate, runHref } from "../lib/router";

const HEADLINE = "These systems show the same warning. Their faults are different. Choose one secretly and let Faultline earn its diagnosis.";
const SLOT_NAME = { alpha: "System α", beta: "System β" } as const;
const SLOT_COLOR = { alpha: "var(--measure)", beta: "var(--measure-2)" } as const;

function yDomainFor(cards: TwinCard[]): [number, number] {
  let lo = Infinity;
  let hi = -Infinity;
  for (const c of cards)
    for (const s of c.samples) {
      lo = Math.min(lo, s.LT101_m);
      hi = Math.max(hi, s.LT101_m);
    }
  if (!isFinite(lo)) return [0, 1];
  const span = Math.max(hi - lo, 0.08);
  const mid = (hi + lo) / 2;
  return [mid - span / 2 - span * 0.1, mid + span / 2 + span * 0.1];
}

function CardView({ card, yDomain }: { card: TwinCard; yDomain: [number, number] }) {
  const s = card.summary;
  const tr = s.level_trend;
  return (
    <article className="twin-card" aria-labelledby={`twin-${card.slot}`}>
      <h3 id={`twin-${card.slot}`} className="twin-name">
        {SLOT_NAME[card.slot]}
      </h3>
      <TimeChart
        compact
        series={[{ key: card.slot, label: `LT-101 ${SLOT_NAME[card.slot]}`, color: SLOT_COLOR[card.slot], points: card.samples.map((x) => ({ t: x.t_s, v: x.LT101_m })) }]}
        xDomain={[card.samples[0]?.t_s ?? -900, 0]}
        yDomain={yDomain}
        yLabel="LT-101"
        yUnit="m"
        height={130}
        ariaLabel={`${SLOT_NAME[card.slot]} alarm-window LT-101 preview: ${tr.first_m.toFixed(3)} to ${tr.last_m.toFixed(3)} metres.`}
      />
      <dl className="kv-list compact">
        <div>
          <dt>LT-101 trend</dt>
          <dd className="tnum">
            {fmtSigned(tr.rate_mm_per_min, 2)} ± {fmt(tr.rate_se_mm_per_min, 2)} mm/min
          </dd>
        </div>
        <div>
          <dt>nominal balance expects</dt>
          <dd className="tnum">{fmtSigned(s.nominal_expected_rate_mm_per_min, 2)} mm/min</dd>
        </div>
        <div>
          <dt>FT-102 mean</dt>
          <dd className="tnum">{fmt(s.FT102_mean_L_s, 3)} L/s</dd>
        </div>
        <div>
          <dt>P-101 command ON</dt>
          <dd className="tnum">{fmt(s.P101_command_on_fraction * 100, 0)} % of window</dd>
        </div>
      </dl>
      <ul className="alarm-list">
        {card.alarms.map((a) => (
          <li key={a.tag}>
            <span className="chip chip-alarm">{a.tag}</span> <span className="small">{a.text}</span>
          </li>
        ))}
      </ul>
    </article>
  );
}

export function TwinChallengePage() {
  const { catalog, catalogError } = useAppData();
  const [presets, setPresets] = useState<Presets | null>(null);
  const [presetsError, setPresetsError] = useState<string | null>(null);
  const [pairId, setPairId] = useState<string>("");
  const [profile, setProfile] = useState("standard");
  const [challenge, setChallenge] = useState<TwinChallenge | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const busyRef = useRef(false);
  const headlineRef = useRef<HTMLHeadingElement>(null);
  const titleRef = useRef<HTMLHeadingElement>(null);
  // Building the pair (or starting over) replaces the focused control; move focus on purpose.
  const focusAfter = useRef<"challenge" | "form" | null>(null);
  useEffect(() => {
    const want = focusAfter.current;
    if (!want) return;
    focusAfter.current = null;
    (want === "challenge" ? headlineRef.current : titleRef.current)?.focus();
  }, [challenge]);

  useEffect(() => {
    let alive = true;
    api.judgePresets().then(
      (p) => alive && setPresets(p),
      (e) => alive && setPresetsError(errorText(e)),
    );
    return () => {
      alive = false;
    };
  }, []);

  useEffect(() => {
    if (!pairId && catalog?.twin_pairs.length) setPairId(catalog.twin_pairs[0].pair_id);
  }, [catalog, pairId]);

  const create = async () => {
    if (busyRef.current) return;
    busyRef.current = true;
    setBusy("create");
    setError(null);
    try {
      const c = await api.createTwin(pairId, profile);
      focusAfter.current = "challenge";
      setChallenge(c);
    } catch (e) {
      setError(errorText(e));
    } finally {
      busyRef.current = false;
      setBusy(null);
    }
  };

  const pick = async (slot: "alpha" | "beta" | "random") => {
    if (!challenge || busyRef.current) return;
    busyRef.current = true;
    setBusy(slot);
    setError(null);
    try {
      const { run_id } = await api.pickTwin(challenge.challenge_id, slot);
      setChallenge(null); // the choice is not kept in the page
      navigate(runHref(run_id));
    } catch (e) {
      setError(errorText(e));
    } finally {
      busyRef.current = false;
      setBusy(null);
    }
  };

  const startOver = () => {
    if (busyRef.current) return;
    focusAfter.current = "form";
    setChallenge(null);
    setError(null);
  };
  // aria-disabled (not disabled) while busy, so the focused button keeps focus.
  const busyAttr = busy !== null ? ({ "aria-disabled": true } as const) : {};

  const yDomain = useMemo(() => (challenge ? yDomainFor(challenge.cards) : ([0, 1] as [number, number])), [challenge]);
  const profiles = presets ? Object.entries(presets.site_profiles) : [];
  const ordered = challenge ? [...challenge.cards].sort((a, b) => (a.slot === "alpha" ? -1 : b.slot === "alpha" ? 1 : 0)) : [];

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1 ref={titleRef} tabIndex={-1}>
            Twin Challenge
          </h1>
          {!challenge && <p className="lede">{HEADLINE}</p>}
        </div>
      </div>

      {!challenge && (
        <section className="panel form-panel" aria-label="Set up a twin challenge">
          {catalogError && <ErrorBox title="Catalog unavailable" message={catalogError} />}
          {presetsError && <ErrorBox title="Judge controls unavailable" message={presetsError} />}
          {!catalog && !catalogError ? (
            <Skeleton lines={4} />
          ) : (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                void create();
              }}
            >
              <fieldset className="field">
                <legend>Twin pair</legend>
                {catalog?.twin_pairs.map((p) => (
                  <label key={p.pair_id} className="radio-card">
                    <input type="radio" name="pair" value={p.pair_id} checked={pairId === p.pair_id} onChange={() => setPairId(p.pair_id)} />
                    <span>
                      <strong>{p.title}</strong>
                      <span className="small muted block">{p.situation}</span>
                    </span>
                  </label>
                ))}
              </fieldset>
              <div className="field">
                <label htmlFor="twin-site">Site profile</label>
                <select id="twin-site" value={profile} onChange={(e) => setProfile(e.target.value)} disabled={!presets}>
                  {profiles.length ? (
                    profiles.map(([k]) => (
                      <option key={k} value={k}>
                        {k.replace(/_/g, " ")}
                      </option>
                    ))
                  ) : (
                    <option value="standard">standard</option>
                  )}
                </select>
                {presets?.site_profiles[profile] && <p className="hint">{String(presets.site_profiles[profile].note ?? "")}</p>}
              </div>
              <button type="submit" className="btn btn-primary" disabled={!pairId || !presets} {...busyAttr}>
                {busy === "create" ? "Building twins…" : "Build the twin pair"}
              </button>
              <p className="hint">The server builds both sealed systems and shows only their logged alarm windows.</p>
            </form>
          )}
          {error && <ErrorBox title="Request failed" message={error} />}
        </section>
      )}

      {challenge && (
        <section className="twin" aria-labelledby="twin-headline">
          <h2 id="twin-headline" className="twin-headline" ref={headlineRef} tabIndex={-1}>
            {HEADLINE}
          </h2>
          <p className="twin-situation">
            <strong>{challenge.title}.</strong> {challenge.situation}
          </p>

          <div className="twin-grid">
            {ordered.map((c) => (
              <CardView key={c.slot} card={c} yDomain={yDomain} />
            ))}
          </div>

          <div className="pick-row">
            <button type="button" className="btn btn-primary" {...busyAttr} onClick={() => void pick("alpha")}>
              {busy === "alpha" ? "Sealing…" : "Investigate α"}
            </button>
            <button type="button" className="btn btn-primary" {...busyAttr} onClick={() => void pick("beta")}>
              {busy === "beta" ? "Sealing…" : "Investigate β"}
            </button>
            <button type="button" className="btn btn-judge" {...busyAttr} onClick={() => void pick("random")}>
              {busy === "random" ? "Dealing…" : "Deal one at random — nobody knows"}
            </button>
            <button type="button" className="btn btn-ghost" {...busyAttr} onClick={startOver}>
              Start over
            </button>
          </div>
          <p className="hint">
            Picking creates a sealed run with a fresh noise seed and opens it on the workstation. Each challenge can be used once.
          </p>
          {error && <ErrorBox title="Request failed" message={error} />}

          <div className="panel">
            <h3 className="panel-title">Both alarm windows, overlaid</h3>
            <TimeChart
              series={ordered.map((c) => ({
                key: c.slot,
                label: SLOT_NAME[c.slot],
                color: SLOT_COLOR[c.slot],
                points: c.samples.map((x) => ({ t: x.t_s, v: x.LT101_m })),
                dash: c.slot === "beta" ? "5 3" : undefined,
              }))}
              xDomain={[ordered[0]?.samples[0]?.t_s ?? -900, 0]}
              yDomain={yDomain}
              yLabel="LT-101"
              yUnit="m"
              height={180}
              markZero
              ariaLabel="Both systems' LT-101 alarm windows overlaid."
            />
            <Legend
              items={ordered.map((c) => ({ label: `${SLOT_NAME[c.slot]} LT-101 (preview noise)`, color: SLOT_COLOR[c.slot], shape: c.slot === "beta" ? "dash" : "line" }))}
            />
          </div>

          <div className="twin-facts">
            <div className="panel">
              <h3 className="panel-title">Candidate causes</h3>
              <p>
                One system has <strong>{hypName(challenge.candidate_causes[0])}</strong>
                {challenge.candidate_causes[1] ? (
                  <>
                    , the other has <strong>{hypName(challenge.candidate_causes[1])}</strong>
                  </>
                ) : null}
                . Which is which is sealed on the server.
              </p>
            </div>
            <div className="panel">
              <h3 className="panel-title">Match proof</h3>
              <ul className="proof">
                <li>
                  Noise-free max LT-101 difference:{" "}
                  <strong className="tnum">{fmt(challenge.match.noise_free_max_LT101_difference_mm, 2)} mm</strong> (tolerance{" "}
                  {fmt(challenge.match.tolerance_mm, 1)} mm)
                </li>
                <li>FT-102 identical: {challenge.match.FT102_identical ? "yes" : "no"}</li>
                <li>P-101 command and run feedback identical: {challenge.match.pump_signals_identical ? "yes" : "no"}</li>
                <li className="muted">{challenge.match.note}</li>
              </ul>
            </div>
            <div className="panel">
              <h3 className="panel-title">Site conditions</h3>
              <dl className="kv-list compact">
                {Object.entries(challenge.site).map(([k, v]) => (
                  <div key={k}>
                    <dt>{siteLabel(k)}</dt>
                    <dd>{siteValue(k, v)}</dd>
                  </div>
                ))}
              </dl>
            </div>
          </div>

        </section>
      )}
    </div>
  );
}
