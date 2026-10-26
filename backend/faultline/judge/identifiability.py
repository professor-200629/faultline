"""Identifiability oracle (evaluator side, PRIVATE).

Question answered: with the instruments and permissions of this case, could
ANY investigator separate the true cause from every other single-fault
explanation that fits the initial observations?

Method (documented in EVALUATION.md):
1. For each other fault family, build the best-matching alternative plant by
   calibrating its one hidden parameter on the noise-free simulator so that
   its alarm-window LT-101 trajectory ends where the true case's does.
   An alternative is VIABLE only if (a) a noisy investigator could not tell
   its alarm window from the truth's (max LT-101 difference within the same
   4-sigma rule used for tests) and (b) its fault is at least the minimum
   severity (otherwise it is just the healthy plant again). The stricter
   2 mm twin tolerance is used only to certify Twin Challenge pairs.
2. For every viable alternative, run each PERMITTED test from t = 0 on both
   noise-free plants and compare outcomes against 4-sigma thresholds derived
   from the datasheet noise. For waiting and the pump-stop test this includes
   the OLS level rate an investigator would fit (and, for waiting, its change
   from the alarm-window rate), with the rate's sd from the sample count.
3. The case is identifiable iff every viable alternative is separated by at
   least one permitted test.

Limits: single-fault hypothesis catalogue; each test is judged on its own
from t = 0 (no sequential combinations); a noise-free 4-sigma criterion is a
practical separability rule, not a formal statistical guarantee.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace

from ..analysis import ols_slope
from ..instruments import InstrumentError, InstrumentPanel
from ..sim.case import FAMILIES, CaseConfig, FaultConfig
from ..sim.plant import QUIET
from ..sim.spec import NOMINAL
from ..sim.twins import calibrate_leak, calibrate_pump

SEP_SIGMAS = 4.0
TWIN_TOL_LT_M = 0.002  # declared tolerance for "matching" LT-101 windows (sensor sd is 3 mm)
TWIN_TOL_FT102_L_S = 0.005  # declared tolerance for FT-102 (sensor sd is 0.01 L/s)
# An alternative is EXCLUDED by the alarm window only if a noisy investigator could tell it apart there:
# same 4-sigma rule as the tests (4 * sqrt(2) * LT-101 sd, about 17 mm; FT-102 4 sd = 0.04 L/s).
WINDOW_EXCLUDE_LT_M = SEP_SIGMAS * math.sqrt(2) * NOMINAL.level_sensor_noise_sd_m
WINDOW_EXCLUDE_FT102_L_S = SEP_SIGMAS * NOMINAL.demand_meter_noise_sd_m3s * 1000
FLAT_TOL_M = 0.004  # a window is "flat" if noise-free LT-101 moves less than this
# Minimum fault size, the same for both hydraulic families: 0.05 L/s of missing water.
MIN_MISSING_FLOW_L_S = 0.05


def _quiet_panel(case: CaseConfig) -> InstrumentPanel:
    return InstrumentPanel(case, seed=0, nominal=QUIET)


def window(case: CaseConfig) -> list[dict]:
    return _quiet_panel(case).historian()


def window_deviation(a: CaseConfig, b: CaseConfig) -> dict:
    wa, wb = window(a), window(b)
    d_lt = max(abs(x["LT101_m"] - y["LT101_m"]) for x, y in zip(wa, wb))
    d_ft = max(abs(x["FT102_L_s"] - y["FT102_L_s"]) for x, y in zip(wa, wb))
    d_cmd = max(abs(x["P101_command"] - y["P101_command"]) + abs(x["P101_run_feedback"] - y["P101_run_feedback"])
                for x, y in zip(wa, wb))
    return {
        "max_LT101_diff_m": d_lt,
        "max_FT102_diff_L_s": d_ft,
        "pump_command_differs": bool(d_cmd),
        "match": d_lt <= TWIN_TOL_LT_M and d_ft <= TWIN_TOL_FT102_L_S and not d_cmd,
        "indistinguishable_in_window": d_lt <= WINDOW_EXCLUDE_LT_M and d_ft <= WINDOW_EXCLUDE_FT102_L_S and not d_cmd,
    }


def _rate(samples: list[dict]) -> tuple[float, float]:
    """Noise-free LT-101 rate (mm/min) and the sd an investigator's OLS fit would have with datasheet noise."""
    ts = [s["t_s"] / 60.0 for s in samples]
    ys = [s["LT101_m"] * 1000.0 for s in samples]
    slope, _ = ols_slope(ts, ys) if len(set(ys)) > 1 else (0.0, 0.0)
    mt = sum(ts) / len(ts)
    sxx = sum((t - mt) ** 2 for t in ts)
    return slope, NOMINAL.level_sensor_noise_sd_m * 1000.0 / math.sqrt(sxx)


def probe_outcomes(case: CaseConfig) -> dict:
    """Noise-free outcome of each permitted test, each started fresh at t = 0."""
    site = case.site
    out: dict = {}
    if site.inlet_meter_available:
        out["inlet_flow"] = {"FT101_L_s": _quiet_panel(case).measure_inlet_flow(60)["mean_inlet_flow_L_s"]}
    if site.independent_level_available:
        r = _quiet_panel(case).independent_level()
        out["independent_level"] = {"dip_m": r["dip_level_m"], "dip_minus_LT_m": r["dip_level_m"] - r["LT101_same_step_m"]}
    if site.pump_stop_test_permitted:
        hold = min(site.max_pump_stop_s, site.max_extra_sim_s)
        if hold >= 60:
            try:
                r = _quiet_panel(case).pump_stop_test(hold)
                s = r["samples"]
                rate, sd = _rate(s)
                out["pump_stop_test"] = {"hold_s": hold, "LT_change_m": s[-1]["LT101_m"] - s[0]["LT101_m"],
                                         "rate_mm_min": rate, "rate_sd_mm_min": sd}
            except InstrumentError:
                pass
    if site.max_extra_sim_s >= 30:
        r = _quiet_panel(case).advance(site.max_extra_sim_s)
        s = r["samples"]
        w = window(case)
        r_wait, sd_wait = _rate(s)
        r_win, sd_win = _rate(w)
        out["wait"] = {"duration_s": site.max_extra_sim_s, "LT_change_m": s[-1]["LT101_m"] - w[-1]["LT101_m"],
                       "rate_change_mm_min": r_wait - r_win, "rate_change_sd_mm_min": math.hypot(sd_wait, sd_win)}
    return out


def _thresholds(a: dict, b: dict, test: str) -> list[tuple[str, float, float]]:
    """(quantity, |delta|, threshold) for one test."""
    n = NOMINAL
    if test == "inlet_flow":
        qa, qb = a["FT101_L_s"], b["FT101_L_s"]
        sd = n.inlet_meter_noise_rel * max(qa, qb) + n.inlet_meter_noise_abs_m3s * 1000
        return [("FT101_L_s", abs(qa - qb), SEP_SIGMAS * sd)]
    if test == "independent_level":
        sd_res = math.hypot(n.dip_noise_sd_m, n.level_sensor_noise_sd_m)
        return [
            ("dip_m", abs(a["dip_m"] - b["dip_m"]), SEP_SIGMAS * n.dip_noise_sd_m),
            ("dip_minus_LT_m", abs(a["dip_minus_LT_m"] - b["dip_minus_LT_m"]), SEP_SIGMAS * sd_res),
        ]
    if test == "pump_stop_test":
        sd = math.sqrt(2) * n.level_sensor_noise_sd_m
        return [("LT_change_m", abs(a["LT_change_m"] - b["LT_change_m"]), SEP_SIGMAS * sd),
                ("rate_mm_min", abs(a["rate_mm_min"] - b["rate_mm_min"]), SEP_SIGMAS * a["rate_sd_mm_min"])]
    if test == "wait":
        sd = math.sqrt(2) * n.level_sensor_noise_sd_m
        return [("LT_change_m", abs(a["LT_change_m"] - b["LT_change_m"]), SEP_SIGMAS * sd),
                ("rate_change_mm_min", abs(a["rate_change_mm_min"] - b["rate_change_mm_min"]),
                 SEP_SIGMAS * a["rate_change_sd_mm_min"])]
    raise ValueError(test)


def separation(truth: CaseConfig, alt: CaseConfig) -> dict:
    ta, tb = probe_outcomes(truth), probe_outcomes(alt)
    rows = []
    for test in ta:
        for qty, delta, thr in _thresholds(ta[test], tb[test], test):
            rows.append({"test": test, "quantity": qty, "delta": round(delta, 6), "threshold": round(thr, 6),
                         "separates": delta > thr})
    return {"rows": rows, "separable_by": sorted({r["test"] for r in rows if r["separates"]})}


@dataclass
class Alternative:
    family: str
    viable: bool
    reason: str
    case: CaseConfig | None = field(default=None, repr=False)
    parameter: dict = field(default_factory=dict)


def _observed_start_true_level(truth: CaseConfig) -> float:
    return window(truth)[0]["LT101_m"] - truth.mismatch.level_bias_m


def build_alternatives(truth: CaseConfig) -> list[Alternative]:
    w = window(truth)
    goal = w[-1]["LT101_m"]
    flat = max(s["LT101_m"] for s in w) - min(s["LT101_m"] for s in w) <= FLAT_TOL_M
    base = replace(truth, fault=FaultConfig(family="no_fault"), initial_level_m=_observed_start_true_level(truth))
    alts: list[Alternative] = []
    for fam in FAMILIES:
        if fam == truth.fault.family:
            continue
        if fam == "no_fault":
            cand, param = base, {}
        elif fam == "pump_delivery_reduced":
            cand = calibrate_pump(base, goal)
            k = cand.fault.pump_capacity_factor
            param = {"pump_capacity_factor": round(k, 4)}
            deficit = (1 - k) * NOMINAL.pump_rated_flow_m3s * 1000
            param["deficit_L_s"] = round(deficit, 4)
            if deficit < MIN_MISSING_FLOW_L_S:
                alts.append(Alternative(fam, False, f"best fit is a {deficit:.3f} L/s deficit: below fault size",
                                        None, param))
                continue
        elif fam == "tank_leak":
            cand = calibrate_leak(base, goal)
            c = cand.fault.leak_coeff_m25_s
            leak_now = c * math.sqrt(max(goal - truth.mismatch.level_bias_m, 0.0)) * 1000
            param = {"leak_L_s_at_t0": round(leak_now, 4)}
            if leak_now < MIN_MISSING_FLOW_L_S:
                alts.append(Alternative(fam, False, f"best fit needs a {leak_now:.3f} L/s leak: below fault size", None, param))
                continue
        else:  # level_sensor_stuck: worst case, frozen exactly at window start (closest to the reading)
            if not flat:
                alts.append(Alternative(fam, False, "LT-101 window is not flat, so a frozen element cannot explain it"))
                continue
            s0 = sum(x["LT101_m"] for x in w) / len(w) - truth.mismatch.level_bias_m
            cand = replace(base, fault=FaultConfig(family="level_sensor_stuck", stuck_at_m=s0), initial_level_m=s0)
            param = {"stuck_at_m": round(s0, 4), "onset": "window start (worst case)"}
        dev = window_deviation(truth, cand)
        param["window_max_LT101_diff_mm"] = round(dev["max_LT101_diff_m"] * 1000, 2)
        if not dev["indistinguishable_in_window"]:
            alts.append(Alternative(fam, False, f"excluded by initial observations (max LT-101 difference "
                                    f"{dev['max_LT101_diff_m'] * 1000:.1f} mm)", None, param))
            continue
        alts.append(Alternative(fam, True, "matches the alarm window", cand, param))
    return alts


def identifiability(truth: CaseConfig) -> dict:
    alts = build_alternatives(truth)
    report = []
    identifiable = True
    for a in alts:
        entry = {"family": a.family, "viable": a.viable, "reason": a.reason, "parameter": a.parameter}
        if a.viable:
            sep = separation(truth, a.case)
            entry["separation"] = sep
            if not sep["separable_by"]:
                identifiable = False
        report.append(entry)
    return {"identifiable": identifiable, "alternatives": report, "oracle_version": ORACLE_VERSION}


ORACLE_VERSION = "identifiability-v2"  # v2: trend rules for wait and pump stop; symmetric fault size
