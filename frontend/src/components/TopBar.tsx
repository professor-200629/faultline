import type { Route } from "../lib/router";
import { useAppData } from "../lib/appData";
import { cls, fmtClock, fmtUsd } from "../lib/format";

const NAV: { href: string; label: string; match: (r: Route) => boolean }[] = [
  { href: "#/", label: "Investigate / Runs", match: (r) => r.name === "runs" || r.name === "run" },
  { href: "#/twin", label: "Twin Challenge", match: (r) => r.name === "twin" },
  { href: "#/blind", label: "Blind Challenge", match: (r) => r.name === "blind" },
  { href: "#/guided", label: "Guided example", match: (r) => r.name === "guided" },
  { href: "#/about", label: "About", match: (r) => r.name === "about" },
];

function Wordmark() {
  return (
    <a className="wordmark" href="#/" aria-label="FAULTLINE home">
      <svg viewBox="0 0 32 20" width="28" height="18" aria-hidden="true" focusable="false">
        <path d="M1 13 L8 13 L11 3 L16 17 L19 8 L31 8" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinejoin="round" strokeLinecap="round" />
      </svg>
      <span>FAULTLINE</span>
    </a>
  );
}

function IntegrationChip() {
  const { status, statusError, checking, checkError, checkConnection } = useAppData();
  const p = status?.provider;
  const last = p?.last_check;
  const spend = status?.spend;
  const pct = spend && spend.ceiling_usd > 0 ? Math.min(100, (spend.estimated_total_usd / spend.ceiling_usd) * 100) : 0;
  return (
    <div className="integration" aria-label="Model provider integration">
      <div className="integration-line">
        <span className="integration-provider">{p?.name ?? "Nebius Token Factory"}</span>
        <span className="sep" aria-hidden="true">·</span>
        <span className="mono integration-model" title={p?.model}>
          {p?.model ?? (statusError ? "status unavailable" : "loading…")}
        </span>
      </div>
      <div className="integration-line small">
        {p ? (
          <span className={cls("dot-label", p.key_configured ? "ok" : "bad")}>
            <span className="dot" aria-hidden="true" />
            {p.key_configured ? "key configured" : "key not configured"}
          </span>
        ) : (
          <span className="muted">—</span>
        )}
        <span className="sep" aria-hidden="true">·</span>
        <span
          className={cls("check-result", last ? (last.ok ? "ok" : "bad") : "muted")}
          title={last?.error ?? (last ? `checked ${fmtClock(last.at)}` : "connection not checked yet")}
        >
          {last ? (last.ok ? `check ok ${fmtClock(last.at)}` : `check failed: ${last.error ?? "unknown"}`) : "not checked"}
        </span>
        <button type="button" className="btn btn-xs" onClick={() => void checkConnection()} disabled={checking || !!statusError}>
          {checking ? "Checking…" : "Check connection"}
        </button>
      </div>
      {spend && (
        <div className="integration-line small" title={`Price source: ${spend.price_source}`}>
          <span className="muted">est. spend</span>
          <span className="mono tnum">
            {fmtUsd(spend.estimated_total_usd)} / {fmtUsd(spend.ceiling_usd, 2)}
          </span>
          <span className="spend-bar" role="meter" aria-label="Estimated spend versus ceiling" aria-valuemin={0} aria-valuemax={spend.ceiling_usd} aria-valuenow={spend.estimated_total_usd}>
            <span style={{ width: `${pct}%` }} />
          </span>
        </div>
      )}
      {checkError && (
        <div className="integration-line small bad" role="alert">
          check request failed: {checkError}
        </div>
      )}
    </div>
  );
}

export function TopBar({ route }: { route: Route }) {
  return (
    <header className="topbar">
      <Wordmark />
      <nav className="nav" aria-label="Main">
        {NAV.map((n) => {
          const active = n.match(route);
          return (
            <a key={n.href} href={n.href} className={cls("nav-link", active && "active")} aria-current={active ? "page" : undefined}>
              {n.label}
            </a>
          );
        })}
      </nav>
      <IntegrationChip />
    </header>
  );
}

export function DisconnectedBanner() {
  const { statusError, refreshStatus, status } = useAppData();
  if (!statusError) return null;
  return (
    <div className="banner banner-error" role="alert">
      <span>
        <strong>Backend not reachable.</strong> /api/status failed: <span className="mono">{statusError}</span>.
        {status ? " Showing the last known state." : ""} Start the API on 127.0.0.1:8000, then retry.
      </span>
      <button type="button" className="btn btn-sm" onClick={() => void refreshStatus()}>
        Retry
      </button>
    </div>
  );
}
