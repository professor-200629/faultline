import type { ReactNode } from "react";
import type { RunMode } from "../api/types";
import { cls } from "../lib/format";

function recordedText(m: string | undefined, imported: boolean): string {
  const what = m === "live" ? "LIVE run" : m === "reference" ? "reference procedure (not AI)" : m === "unstarted" ? "run (not started)" : null;
  if (imported) return what ? `imported recording of a ${what}` : "imported recording";
  return what ? `recorded ${what}` : "recorded run";
}

export function ModeBadge({
  mode,
  replay = false,
  recordedMode,
  size = "md",
  model,
  providerName,
}: {
  mode: RunMode | string;
  /** True on the replay route (#/run/:id/replay). */
  replay?: boolean;
  /** For an imported recording (mode "replay"): the mode it was recorded in, if known. */
  recordedMode?: string;
  size?: "sm" | "md" | "lg";
  model?: string;
  providerName?: string;
}) {
  const imported = mode === "replay";
  const isReplay = replay || imported;
  // A scripted test provider exists in the backend for automated tests only; never show it as LIVE.
  if (providerName === "scripted-test-fixture") {
    return (
      <span className={cls("mode-badge", "mode-reference", `mode-${size}`)}>
        <span className="mode-main">{isReplay ? "REPLAY · " : ""}TEST FIXTURE</span>
        <span className="mode-sub">scripted, not AI</span>
      </span>
    );
  }
  if (isReplay) {
    // Only an explicitly recorded mode (or the run's own mode) is named; never guess LIVE.
    const base = imported ? recordedMode : mode;
    return (
      <span className={cls("mode-badge", "mode-replay", `mode-${size}`)} title={base === "live" ? model : undefined}>
        <span className="mode-main">REPLAY</span>
        <span className="mode-sub">
          {size === "sm" && imported ? (base === "reference" ? "imported recording, not AI" : "imported recording") : recordedText(base, imported)}
        </span>
      </span>
    );
  }
  if (mode === "live") {
    return (
      <span className={cls("mode-badge", "mode-live", `mode-${size}`)} title={model}>
        <span className="mode-main">LIVE</span>
        <span className="mode-sub">NVIDIA Nemotron via Nebius{model && size === "lg" ? ` · ${model}` : ""}</span>
      </span>
    );
  }
  if (mode === "reference") {
    return (
      <span className={cls("mode-badge", "mode-reference", `mode-${size}`)}>
        <span className="mode-main">REFERENCE PROCEDURE</span>
        <span className="mode-sub">deterministic, not AI</span>
      </span>
    );
  }
  return (
    <span className={cls("mode-badge", "mode-unstarted", `mode-${size}`)}>
      <span className="mode-main">NOT STARTED</span>
      {size !== "sm" && <span className="mode-sub">no investigator assigned yet</span>}
    </span>
  );
}

export function Skeleton({ lines = 3, height }: { lines?: number; height?: number }) {
  if (height) return <div className="skeleton" style={{ height }} aria-hidden="true" />;
  return (
    <div aria-hidden="true">
      {Array.from({ length: lines }, (_, i) => (
        <div key={i} className="skeleton skeleton-line" style={{ width: `${92 - ((i * 17) % 40)}%` }} />
      ))}
    </div>
  );
}

export function ErrorBox({ title = "Error", message, children }: { title?: string; message: string; children?: ReactNode }) {
  return (
    <div className="error-box" role="alert">
      <strong>{title}:</strong> <span className="error-text">{message}</span>
      {children && <div className="error-actions">{children}</div>}
    </div>
  );
}

export function Panel({
  title,
  children,
  className,
  actions,
  coach,
  id,
  subtitle,
}: {
  title: ReactNode;
  children: ReactNode;
  className?: string;
  actions?: ReactNode;
  coach?: string;
  id?: string;
  subtitle?: ReactNode;
}) {
  return (
    <section className={cls("panel", className)} data-coach={coach} id={id} aria-label={typeof title === "string" ? title : undefined}>
      <header className="panel-head">
        <div>
          <h2 className="panel-title">{title}</h2>
          {subtitle && <p className="panel-sub">{subtitle}</p>}
        </div>
        {actions && <div className="panel-actions">{actions}</div>}
      </header>
      <div className="panel-body">{children}</div>
    </section>
  );
}

export function Tag({ children, kind = "tag" }: { children: ReactNode; kind?: "tag" | "evidence" | "prediction" | "alarm" }) {
  return <span className={cls("chip", `chip-${kind}`)}>{children}</span>;
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="empty-state">
      <p className="empty-title">{title}</p>
      {children && <div className="empty-body">{children}</div>}
    </div>
  );
}
