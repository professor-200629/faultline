// Equipment view: supply sump -> P-101 -> discharge with FT-101 clamp -> T-101 -> FT-102 -> demand.
// Shows ONLY measured values with their timestamps. The tank fill is the LT-101
// INDICATED level (hatched, dashed edge). Nothing here represents a true level.
import type { Evidence, Nominal, SiteConditions, TelemetrySample } from "../api/types";
import { fmt, fmtSimRange, fmtSimT, isNum } from "../lib/format";
import { ft101Window } from "./Trends";

interface Props {
  nominal: Nominal | null;
  latest: TelemetrySample | null;
  evidence: Evidence[];
  site: SiteConditions | null;
}

function latestOfKind(evidence: Evidence[], kind: string): Evidence | null {
  for (let i = evidence.length - 1; i >= 0; i--) if (evidence[i].kind === kind) return evidence[i];
  return null;
}

function num(d: Record<string, unknown>, k: string): number | null {
  const v = d[k];
  return isNum(v) ? v : null;
}

export function EquipmentView({ nominal, latest, evidence, site }: Props) {
  const height = nominal?.tank.height_m ?? null;
  const weir = nominal?.tank.overflow_level_m ?? null;
  const outletLevel = nominal?.tank.demand_outlet_level_m ?? null;
  const tankTop = 40;
  const tankBottom = 250;
  const yL = (lvl: number) =>
    height ? tankBottom - (Math.min(Math.max(lvl, 0), height) / height) * (tankBottom - tankTop) : tankBottom;

  const lt = latest?.LT101_m;
  const ft102 = latest?.FT102_L_s;
  const cmd = latest?.P101_command;
  const fb = latest?.P101_run_feedback;
  const ft101 = latestOfKind(evidence, "inlet_flow_measurement");
  const dip = latestOfKind(evidence, "independent_level");
  const ft101v = ft101 ? num(ft101.data, "mean_inlet_flow_L_s") : null;
  const ft101sd = ft101 ? num(ft101.data, "stated_uncertainty_sd_L_s") : null;
  // Averaging window (data.t_start_s..t_end_s); the clamp is fitted before it from t_fit_start_s.
  const ftWin = ft101 ? ft101Window(ft101) : null;
  const dipv = dip ? num(dip.data, "dip_level_m") : null;
  const dipsd = dip ? num(dip.data, "stated_uncertainty_sd_m") : null;
  const dipT = dip ? num(dip.data, "t_s") : null;
  const ftUnavailable = site?.["inlet_flow_meter_FT101"] === "unavailable";
  const dipUnavailable = site?.["independent_level_DIP101"] === "unavailable";
  const onOff = (v: number | undefined) => (v === 1 ? "ON" : v === 0 ? "OFF" : "—");
  const yInd = isNum(lt) ? yL(lt) : null;
  const yWeir = isNum(weir) ? yL(weir) : null;
  const yOut = isNum(outletLevel) ? yL(outletLevel) : tankBottom - 6;
  const demandFlowing = isNum(ft102) && ft102 > 0.02;

  const aria = [
    "Process diagram of T-101 and P-101.",
    isNum(lt) ? `LT-101 indicates ${lt.toFixed(3)} metres at ${fmtSimT(latest?.t_s)}; the sensor could be wrong.` : "LT-101 reading not loaded.",
    isNum(ft102) ? `FT-102 reads ${ft102.toFixed(2)} litres per second.` : "",
    ft101v !== null ? `FT-101 measured ${ft101v.toFixed(3)} litres per second.` : "FT-101 not measured.",
    dipv !== null ? `DIP-101 measured ${dipv.toFixed(3)} metres.` : "DIP-101 not measured.",
    `P-101 command ${onOff(cmd)}, run feedback ${onOff(fb)}; delivered flow unknown unless measured.`,
  ].join(" ");

  return (
    <div className="equipment">
      <svg viewBox="0 0 440 296" className="equipment-svg" role="img" aria-label={aria}>
        <defs>
          <pattern id="ind-hatch" width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(-45)">
            <rect width="7" height="7" fill="var(--ind-fill)" />
            <line x1="0" y1="0" x2="0" y2="7" stroke="var(--ind-hatch)" strokeWidth="2.2" />
          </pattern>
          <marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M0,0 L10,5 L0,10 z" fill="var(--pipe)" />
          </marker>
        </defs>

        {/* Font sizes are set so SVG text renders at 11 px or more in the 1280 x 720 layout (SVG scaled to ~0.84). */}
        {/* supply sump (not instrumented: drawn as an outline only) */}
        <path d="M20 262 L20 288 L150 288 L150 262" className="eq-vessel" />
        <text x="85" y="283" className="eq-label-muted" textAnchor="middle">supply sump</text>

        {/* suction + discharge piping */}
        <path d="M70 268 L70 250" className="eq-pipe" />
        <path d="M70 214 L70 10 L315 10 L315 40" className="eq-pipe" />

        {/* P-101 pump symbol */}
        <g className="eq-pump">
          <circle cx="70" cy="232" r="18" />
          <path d="M58 242 L70 216 L82 242" fill="none" />
        </g>
        <text x="96" y="222" className="eq-tag">P-101</text>
        <text x="96" y="238" className="eq-label">command {onOff(cmd)}</text>
        <text x="96" y="254" className="eq-label">run feedback {onOff(fb)}</text>

        {/* FT-101 clamp-on meter on the discharge */}
        <rect x="61" y="100" width="18" height="24" rx="3" className={ft101v !== null ? "eq-clamp measured" : "eq-clamp"} />
        <text x="88" y="106" className="eq-tag">FT-101</text>
        {ft101v !== null ? (
          <>
            <text x="88" y="122" className="eq-value">
              {ft101v.toFixed(3)} ± {fmt(ft101sd, 3)} L/s
            </text>
            <text x="88" y="138" className="eq-label-muted">
              {fmtSimRange(ftWin?.t0, ftWin?.t1)} ({ft101?.evidence_id})
            </text>
          </>
        ) : ftUnavailable ? (
          <>
            <text x="88" y="122" className="eq-label-muted">unavailable</text>
            <text x="88" y="138" className="eq-label-muted">at this site</text>
          </>
        ) : (
          <text x="88" y="122" className="eq-label-muted">not measured</text>
        )}
        <text x="88" y="164" className="eq-label-muted">delivered flow</text>
        <text x="88" y="179" className="eq-label-muted">unknown unless</text>
        <text x="88" y="194" className="eq-label-muted">measured</text>

        {/* T-101 tank */}
        {yInd !== null && (
          <g>
            <rect x="231" y={yInd} width="98" height={tankBottom - yInd - 1} fill="url(#ind-hatch)" />
            <line x1="231" x2="329" y1={yInd} y2={yInd} className="eq-ind-edge" />
          </g>
        )}
        <path d={`M230 ${tankTop} L230 ${tankBottom} L330 ${tankBottom} L330 ${tankTop} Z`} className="eq-tank" />
        {yWeir !== null && (
          <g>
            <line x1="230" x2="330" y1={yWeir} y2={yWeir} className="eq-weir" />
            <text x="253" y={yWeir + 15} className="eq-label-muted">weir {fmt(weir, 2)} m</text>
          </g>
        )}
        <text x="280" y={tankBottom + 16} className="eq-tag" textAnchor="middle">T-101</text>
        <text x="280" y={tankBottom + 32} className="eq-label-muted" textAnchor="middle">
          {isNum(height) ? `height ${height.toFixed(2)} m` : ""}
        </text>

        {/* LT-101 transmitter on the roof */}
        <circle cx="290" cy="27" r="12.5" className="eq-inst" />
        <text x="290" y="32" className="eq-inst-text" textAnchor="middle">LT</text>
        {yInd !== null ? (
          <g>
            <line x1="330" x2="338" y1={yInd} y2={yInd} className="eq-leader" />
            <text x="341" y={yInd - 7} className="eq-tag">LT-101</text>
            <text x="341" y={yInd + 10} className="eq-value">{lt!.toFixed(3)} m</text>
            <text x="341" y={yInd + 25} className="eq-label-muted">indicated</text>
          </g>
        ) : (
          <text x="341" y="120" className="eq-label-muted">LT-101 —</text>
        )}

        {/* roof hatch + DIP-101 */}
        <rect x="236" y="35" width="22" height="5" className="eq-hatch" />
        {dipv !== null && (
          <g>
            <line x1="247" x2="247" y1="40" y2={yL(dipv)} className="eq-dip-tape" />
            <rect x={243} y={yL(dipv) - 4} width="8" height="8" transform={`rotate(45 247 ${yL(dipv)})`} className="eq-dip-mark" />
          </g>
        )}
        <text x="140" y="40" className="eq-tag">DIP-101</text>
        <text x="140" y="56" className={dipv !== null ? "eq-value" : "eq-label-muted"}>
          {dipv !== null ? `${dipv.toFixed(3)} m` : dipUnavailable ? "unavailable" : "not measured"}
        </text>
        {dipv !== null && (
          <text x="140" y="72" className="eq-label-muted">{fmtSimT(dipT)}</text>
        )}
        <path d="M202 35 L234 37" className="eq-leader" />

        {/* outlet -> FT-102 -> demand */}
        <path d={`M330 ${yOut} L428 ${yOut}`} className="eq-pipe" markerEnd="url(#arrow)" />
        {demandFlowing && <path d={`M332 ${yOut} L420 ${yOut}`} className="eq-flow-dash" />}
        <circle cx="372" cy={yOut} r="12.5" className="eq-inst" />
        <text x="372" y={yOut + 5} className="eq-inst-text" textAnchor="middle">FT</text>
        <text x="407" y={yOut - 10} className="eq-label-muted" textAnchor="middle">demand</text>
        <text x="345" y={yOut + 29} className="eq-tag">FT-102</text>
        <text x="345" y={yOut + 45} className="eq-value">{isNum(ft102) ? `${ft102.toFixed(2)} L/s` : "—"}</text>
      </svg>

      <dl className="readouts">
        <div className="readout">
          <dt>
            <span className="mono">LT-101</span> indicated level — the sensor could be wrong
          </dt>
          <dd>
            <span className="val tnum">{isNum(lt) ? `${lt.toFixed(3)} m` : "—"}</span>
            <span className="when">logged {fmtSimT(latest?.t_s)}</span>
          </dd>
        </div>
        <div className="readout">
          <dt>
            <span className="mono">FT-102</span> demand outlet flow
          </dt>
          <dd>
            <span className="val tnum">{isNum(ft102) ? `${ft102.toFixed(2)} L/s` : "—"}</span>
            <span className="when">logged {fmtSimT(latest?.t_s)}</span>
          </dd>
        </div>
        <div className="readout">
          <dt>
            <span className="mono">FT-101</span> portable inlet flow (delivered by P-101)
          </dt>
          <dd>
            {ft101v !== null ? (
              <>
                <span className="val tnum">
                  {ft101v.toFixed(3)} ± {fmt(ft101sd, 3)} L/s
                </span>
                <span className="when">
                  1 sd, averaged {fmtSimRange(ftWin?.t0, ftWin?.t1)}
                  {ftWin && ftWin.fitStart !== null && ftWin.fitStart < ftWin.t0 ? ` (clamp fitted from ${fmtSimT(ftWin.fitStart)})` : ""} ·{" "}
                  <span className="mono">{ft101?.evidence_id}</span>
                </span>
              </>
            ) : (
              <span className="val muted">{ftUnavailable ? "not measured (unavailable at this site)" : "not measured"}</span>
            )}
          </dd>
        </div>
        <div className="readout">
          <dt>
            <span className="mono">DIP-101</span> manual dip at the roof hatch
          </dt>
          <dd>
            {dipv !== null ? (
              <>
                <span className="val tnum">
                  {dipv.toFixed(3)} m{dipsd !== null ? ` ± ${Math.round(dipsd * 1000)} mm` : ""}
                </span>
                <span className="when">
                  {fmtSimT(dipT)} · <span className="mono">{dip?.evidence_id}</span>
                </span>
              </>
            ) : (
              <span className="val muted">{dipUnavailable ? "not measured (unavailable at this site)" : "not measured"}</span>
            )}
          </dd>
        </div>
        <div className="readout">
          <dt>
            <span className="mono">P-101</span> pump signals
          </dt>
          <dd>
            <span className="val">
              command {onOff(cmd)} · run feedback {onOff(fb)}
            </span>
            <span className="when">delivered flow: unknown unless measured</span>
          </dd>
        </div>
      </dl>
    </div>
  );
}
