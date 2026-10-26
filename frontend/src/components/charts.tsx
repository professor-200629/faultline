// Hand-written SVG time-series chart used for measured trends, twin previews and
// the judge-only omniscient view. Time is simulation seconds relative to the
// warning (t = 0) and is displayed in minutes.
import { useEffect, useRef, useState, type PointerEvent as RPointerEvent, type ReactNode, type RefObject } from "react";
import { isNum } from "../lib/format";

export interface SeriesPoint {
  t: number;
  v: number;
}

export interface Series {
  key: string;
  label: string;
  color: string;
  points: SeriesPoint[];
  dash?: string;
  width?: number;
  opacity?: number;
}

export interface PointMark {
  key: string;
  label: string;
  t: number;
  v: number;
  sd?: number;
  /** averaging interval, drawn as a horizontal segment */
  t0?: number;
  t1?: number;
  shape: "diamond" | "circle";
  color: string;
}

export interface Band {
  key: string;
  label: string;
  t0: number;
  t1: number;
  tone?: "test" | "alert";
}

export interface RefLine {
  key: string;
  v: number;
  label: string;
  color: string;
  dash?: string;
}

export function useElementWidth<T extends HTMLElement>(fallback = 420): [RefObject<T>, number] {
  const ref = useRef<T>(null);
  const [w, setW] = useState(fallback);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const update = () => {
      const width = el.getBoundingClientRect().width;
      if (width > 0) setW(Math.round(width));
    };
    update();
    if (typeof ResizeObserver === "undefined") {
      window.addEventListener("resize", update);
      return () => window.removeEventListener("resize", update);
    }
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, w];
}

export function niceStep(span: number, target: number): number {
  const raw = span / Math.max(1, target);
  const mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const norm = raw / mag;
  const step = norm < 1.5 ? 1 : norm < 3 ? 2 : norm < 7 ? 5 : 10;
  return step * mag;
}

export function ticks(min: number, max: number, target = 5): number[] {
  if (!(max > min)) return [min];
  const step = niceStep(max - min, target);
  const out: number[] = [];
  for (let v = Math.ceil(min / step - 1e-9) * step; v <= max + 1e-9; v += step) out.push(Number(v.toFixed(10)));
  return out;
}

function minuteLabel(s: number): string {
  const m = s / 60;
  const r = Math.round(m * 10) / 10;
  if (r === 0) return "0";
  return `${r > 0 ? "+" : "−"}${Math.abs(r)}`;
}

interface ChartProps {
  series: Series[];
  points?: PointMark[];
  bands?: Band[];
  refLines?: RefLine[];
  xDomain: [number, number];
  yLabel: string;
  yUnit: string;
  yDigits?: number;
  yMinSpan?: number;
  yDomain?: [number, number];
  height?: number;
  ariaLabel: string;
  markZero?: boolean;
  compact?: boolean;
  tone?: "measured" | "judge";
  footer?: ReactNode;
}

export function TimeChart({
  series,
  points = [],
  bands = [],
  refLines = [],
  xDomain,
  yLabel,
  yUnit,
  yDigits = 2,
  yMinSpan = 0.1,
  yDomain,
  height = 200,
  ariaLabel,
  markZero = true,
  compact = false,
  tone = "measured",
  footer,
}: ChartProps) {
  const [wrapRef, width] = useElementWidth<HTMLDivElement>();
  const [hoverT, setHoverT] = useState<number | null>(null);
  const m = compact ? { l: 42, r: 8, t: 8, b: 22 } : { l: 50, r: 12, t: 14, b: 34 };
  const W = Math.max(200, width);
  const H = height;
  const iw = W - m.l - m.r;
  const ih = H - m.t - m.b;

  const [x0, x1raw] = xDomain;
  const x1 = x1raw > x0 ? x1raw : x0 + 60;

  let lo = Infinity;
  let hi = -Infinity;
  const take = (v: number) => {
    if (isNum(v)) {
      lo = Math.min(lo, v);
      hi = Math.max(hi, v);
    }
  };
  for (const s of series) for (const p of s.points) if (p.t >= x0 - 1e-9 && p.t <= x1 + 1e-9) take(p.v);
  for (const p of points) {
    take(p.v - (p.sd ?? 0));
    take(p.v + (p.sd ?? 0));
  }
  for (const r of refLines) take(r.v);
  if (yDomain) {
    lo = yDomain[0];
    hi = yDomain[1];
  } else if (!isFinite(lo)) {
    lo = 0;
    hi = 1;
  } else {
    const span = Math.max(hi - lo, yMinSpan);
    const mid = (hi + lo) / 2;
    lo = mid - span / 2 - span * 0.08;
    hi = mid + span / 2 + span * 0.08;
  }

  const sx = (t: number) => m.l + ((t - x0) / (x1 - x0)) * iw;
  const sy = (v: number) => m.t + (1 - (v - lo) / (hi - lo)) * ih;
  const clampX = (t: number) => Math.min(x1, Math.max(x0, t));

  const xStepS = niceStep((x1 - x0) / 60, compact ? 4 : 7) * 60;
  const xTicks: number[] = [];
  for (let t = Math.ceil(x0 / xStepS) * xStepS; t <= x1 + 1e-9; t += xStepS) xTicks.push(t);
  const yTicks = ticks(lo, hi, compact ? 3 : 5);

  const pathFor = (pts: SeriesPoint[]) => {
    let d = "";
    let pen = false;
    for (const p of pts) {
      if (!isNum(p.v) || p.t < x0 - 1e-9 || p.t > x1 + 1e-9) {
        pen = false;
        continue;
      }
      d += `${pen ? "L" : "M"}${sx(p.t).toFixed(1)},${sy(p.v).toFixed(1)}`;
      pen = true;
    }
    return d;
  };

  const onMove = (e: RPointerEvent<SVGRectElement>) => {
    const rect = (e.currentTarget.ownerSVGElement ?? e.currentTarget).getBoundingClientRect();
    const px = e.clientX - rect.left;
    const t = x0 + ((px - m.l) / iw) * (x1 - x0);
    setHoverT(clampX(t));
  };

  const readout: string[] = [];
  if (hoverT !== null) {
    for (const s of series) {
      let best: SeriesPoint | null = null;
      for (const p of s.points) if (!best || Math.abs(p.t - hoverT) < Math.abs(best.t - hoverT)) best = p;
      if (best && Math.abs(best.t - hoverT) <= 30) readout.push(`${s.label} ${best.v.toFixed(yDigits + 1)} ${yUnit} at t = ${Math.round(best.t)} s`);
    }
  }

  const uid = useRef(`c${Math.random().toString(36).slice(2, 8)}`).current;

  return (
    <div className={`chart chart-${tone}`} ref={wrapRef}>
      <svg
        width={W}
        height={H}
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        aria-label={ariaLabel}
        className="chart-svg"
      >
        <defs>
          <pattern id={`${uid}-hatch`} width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <line x1="0" y1="0" x2="0" y2="6" stroke="var(--band-hatch)" strokeWidth="2" />
          </pattern>
          <clipPath id={`${uid}-clip`}>
            <rect x={m.l} y={m.t} width={iw} height={ih} />
          </clipPath>
        </defs>
        <rect x={m.l} y={m.t} width={iw} height={ih} className="chart-plot" />
        {yTicks.map((v) => (
          <g key={`y${v}`}>
            <line x1={m.l} x2={m.l + iw} y1={sy(v)} y2={sy(v)} className="chart-grid" />
            <text x={m.l - 6} y={sy(v)} className="chart-tick" textAnchor="end" dominantBaseline="middle">
              {v.toFixed(yDigits)}
            </text>
          </g>
        ))}
        {xTicks.map((t) => (
          <g key={`x${t}`}>
            <line x1={sx(t)} x2={sx(t)} y1={m.t} y2={m.t + ih} className="chart-grid" />
            <text x={sx(t)} y={m.t + ih + 13} className="chart-tick" textAnchor="middle">
              {minuteLabel(t)}
            </text>
          </g>
        ))}
        <g clipPath={`url(#${uid}-clip)`}>
          {bands.map((b) => {
            const a = sx(clampX(b.t0));
            const z = sx(clampX(b.t1));
            return (
              <g key={b.key}>
                <rect x={a} y={m.t} width={Math.max(1, z - a)} height={ih} fill={`url(#${uid}-hatch)`} className={`chart-band band-${b.tone ?? "test"}`} />
                {!compact && (
                  <text x={a + 3} y={m.t + 11} className="chart-band-label">
                    {b.label}
                  </text>
                )}
              </g>
            );
          })}
          {refLines.map((r) => (
            <g key={r.key}>
              <line x1={m.l} x2={m.l + iw} y1={sy(r.v)} y2={sy(r.v)} stroke={r.color} strokeDasharray={r.dash ?? "2 4"} strokeWidth={1.2} />
              <text x={m.l + iw - 4} y={sy(r.v) - 4} className="chart-ref-label" textAnchor="end" fill={r.color}>
                {r.label}
              </text>
            </g>
          ))}
          {series.map((s) => (
            <path
              key={s.key}
              d={pathFor(s.points)}
              fill="none"
              stroke={s.color}
              strokeWidth={s.width ?? 1.6}
              strokeDasharray={s.dash}
              strokeOpacity={s.opacity ?? 1}
              strokeLinejoin="round"
            />
          ))}
          {points.map((p) => {
            const cx = sx(p.t);
            const cy = sy(p.v);
            return (
              <g key={p.key}>
                {isNum(p.t0) && isNum(p.t1) && (
                  <line x1={sx(p.t0)} x2={sx(p.t1)} y1={cy} y2={cy} stroke={p.color} strokeWidth={2.5} strokeOpacity={0.7} />
                )}
                {isNum(p.sd) && p.sd > 0 && (
                  <g stroke={p.color} strokeWidth={1.3}>
                    <line x1={cx} x2={cx} y1={sy(p.v - p.sd)} y2={sy(p.v + p.sd)} />
                    <line x1={cx - 4} x2={cx + 4} y1={sy(p.v - p.sd)} y2={sy(p.v - p.sd)} />
                    <line x1={cx - 4} x2={cx + 4} y1={sy(p.v + p.sd)} y2={sy(p.v + p.sd)} />
                  </g>
                )}
                {p.shape === "diamond" ? (
                  <rect x={cx - 4.5} y={cy - 4.5} width={9} height={9} transform={`rotate(45 ${cx} ${cy})`} fill="var(--panel)" stroke={p.color} strokeWidth={2} />
                ) : (
                  <circle cx={cx} cy={cy} r={4.5} fill="var(--panel)" stroke={p.color} strokeWidth={2} />
                )}
                {!compact && (
                  <text x={cx + 7} y={cy - 7} className="chart-point-label" fill={p.color}>
                    {p.label}
                  </text>
                )}
              </g>
            );
          })}
        </g>
        {markZero && 0 >= x0 && 0 <= x1 && (
          <g>
            <line x1={sx(0)} x2={sx(0)} y1={m.t} y2={m.t + ih} className="chart-zero" />
            {!compact && (
              <text x={sx(0) + 4} y={m.t + ih - 6} className="chart-zero-label">
                t = 0 warning raised
              </text>
            )}
          </g>
        )}
        {hoverT !== null && <line x1={sx(hoverT)} x2={sx(hoverT)} y1={m.t} y2={m.t + ih} className="chart-cursor" />}
        <text x={m.l + iw / 2} y={H - 4} className="chart-axis-label" textAnchor="middle">
          {compact ? "min from warning" : "time relative to warning (min)"}
        </text>
        <text x={12} y={m.t + ih / 2} className="chart-axis-label" textAnchor="middle" transform={`rotate(-90 12 ${m.t + ih / 2})`}>
          {yLabel} ({yUnit})
        </text>
        <rect
          x={m.l}
          y={m.t}
          width={iw}
          height={ih}
          fill="transparent"
          onPointerMove={onMove}
          onPointerLeave={() => setHoverT(null)}
        />
      </svg>
      {!compact && (
        <div className="chart-readout" aria-hidden="true">
          {readout.length ? readout.join(" · ") : " "}
        </div>
      )}
      {footer}
    </div>
  );
}

export function Legend({ items }: { items: { label: string; color: string; shape: "line" | "dash" | "diamond" | "circle" | "band" | "zero" }[] }) {
  return (
    <ul className="legend">
      {items.map((i) => (
        <li key={i.label}>
          <svg width="18" height="10" aria-hidden="true" focusable="false">
            {i.shape === "line" && <line x1="1" x2="17" y1="5" y2="5" stroke={i.color} strokeWidth="2" />}
            {i.shape === "dash" && <line x1="1" x2="17" y1="5" y2="5" stroke={i.color} strokeWidth="2" strokeDasharray="4 3" />}
            {i.shape === "zero" && <line x1="9" x2="9" y1="0" y2="10" stroke={i.color} strokeWidth="1.5" strokeDasharray="2 2" />}
            {i.shape === "diamond" && <rect x="5" y="1" width="7" height="7" transform="rotate(45 8.5 4.5)" fill="none" stroke={i.color} strokeWidth="1.8" />}
            {i.shape === "circle" && <circle cx="9" cy="5" r="3.5" fill="none" stroke={i.color} strokeWidth="1.8" />}
            {i.shape === "band" && <rect x="1" y="0" width="16" height="10" fill="var(--band-fill)" stroke="var(--band-hatch)" />}
          </svg>
          {i.label}
        </li>
      ))}
    </ul>
  );
}
