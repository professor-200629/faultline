"""Public statistics over observation records.

Everything here consumes ONLY public observation dictionaries (historian
samples and measurement results) plus the public nominal spec. It is used by
the alarm logic, the agent's tools, `predict_under_hypothesis` and the
deterministic baseline. It must never import the plant or a case config.
"""

from __future__ import annotations

import math
from statistics import median
from typing import Iterable, Sequence

from .sim.spec import NOMINAL, NominalSpec


def ols_slope(ts: Sequence[float], ys: Sequence[float]) -> tuple[float, float]:
    """Least-squares slope dy/dt and its standard error (iid-residual assumption)."""
    n = len(ts)
    if n < 3:
        raise ValueError("need at least 3 points for a trend")
    mt = sum(ts) / n
    my = sum(ys) / n
    sxx = sum((t - mt) ** 2 for t in ts)
    if sxx <= 0:
        raise ValueError("timestamps are not distinct")
    sxy = sum((t - mt) * (y - my) for t, y in zip(ts, ys))
    slope = sxy / sxx
    intercept = my - slope * mt
    resid = [y - (intercept + slope * t) for t, y in zip(ts, ys)]
    s2 = sum(r * r for r in resid) / (n - 2)
    return slope, math.sqrt(s2 / sxx)


def level_trend(samples: Iterable[dict]) -> dict:
    """Trend of LT-101 readings: rate in mm/min with standard error, plus spread."""
    pts = [(s["t_s"], s["LT101_m"]) for s in samples if s.get("LT101_m") is not None]
    ts = [p[0] / 60.0 for p in pts]
    ys = [p[1] * 1000.0 for p in pts]
    slope, se = ols_slope(ts, ys)
    mean_y = sum(ys) / len(ys)
    sd = math.sqrt(sum((y - mean_y) ** 2 for y in ys) / (len(ys) - 1))
    return {
        "n": len(pts),
        "t_from_s": pts[0][0],
        "t_to_s": pts[-1][0],
        "rate_mm_per_min": round(slope, 3),
        "rate_se_mm_per_min": round(se, 3),
        "first_m": pts[0][1],
        "last_m": pts[-1][1],
        "mean_m": round(mean_y / 1000.0, 4),
        "reading_sd_mm": round(sd, 2),
    }


def mean_demand_L_s(samples: Iterable[dict]) -> float:
    vals = [s["FT102_L_s"] for s in samples if s.get("FT102_L_s") is not None]
    return round(sum(vals) / len(vals), 4)


def pump_on_fraction(samples: Iterable[dict]) -> float:
    vals = [s["P101_command"] for s in samples]
    return sum(vals) / len(vals)


def rate_mm_min_from_flow(net_L_s: float, spec: NominalSpec = NOMINAL) -> float:
    """Level rate (mm/min) produced by a net volumetric flow (L/s) in the nominal tank."""
    return net_L_s / 1000.0 / spec.tank_area_m2 * 1000.0 * 60.0


def flow_L_s_from_rate(rate_mm_min: float, spec: NominalSpec = NOMINAL) -> float:
    return rate_mm_min / 60.0 / 1000.0 * spec.tank_area_m2 * 1000.0


def window_summary(samples: list[dict], spec: NominalSpec = NOMINAL) -> dict:
    """Mass-balance summary of a historian window using only public data."""
    trend = level_trend(samples)
    q_d = mean_demand_L_s(samples)
    on = pump_on_fraction(samples)
    rated = spec.pump_rated_flow_m3s * 1000.0
    expected_rate = rate_mm_min_from_flow(rated * on - q_d, spec)
    implied_net = flow_L_s_from_rate(trend["rate_mm_per_min"], spec)
    return {
        "level_trend": trend,
        "FT102_mean_L_s": q_d,
        "P101_command_on_fraction": round(on, 3),
        "nominal_expected_rate_mm_per_min": round(expected_rate, 3),
        "rate_minus_nominal_mm_per_min": round(trend["rate_mm_per_min"] - expected_rate, 3),
        "implied_net_inflow_L_s": round(implied_net, 4),
        "implied_net_inflow_note": "LT-101 rate x nominal tank area; equals pump delivery minus demand minus any leak, "
        "if LT-101 reads the true level",
    }


def evaluate_alarms(samples: list[dict], spec: NominalSpec = NOMINAL) -> list[dict]:
    """Public alarm rules evaluated on the alarm window."""
    alarms: list[dict] = []
    last_minute = [s["LT101_m"] for s in samples[-6:]]
    lvl = median(last_minute)
    if lvl < spec.low_level_alarm_m:
        alarms.append(
            {
                "tag": "LAL-101",
                "text": f"Low level: LT-101 {lvl:.3f} m is below {spec.low_level_alarm_m:.2f} m",
            }
        )
    summ = window_summary(samples, spec)
    dev = summ["rate_minus_nominal_mm_per_min"]
    if abs(dev) > spec.balance_alarm_mm_per_min:
        obs = summ["level_trend"]["rate_mm_per_min"]
        exp = summ["nominal_expected_rate_mm_per_min"]
        alarms.append(
            {
                "tag": "BAL-101",
                "text": (
                    f"Mass-balance deviation: LT-101 changing at {obs:+.1f} mm/min while P-101 is "
                    f"{'running' if summ['P101_command_on_fraction'] > 0.5 else 'stopped'} and FT-102 reads "
                    f"{summ['FT102_mean_L_s']:.2f} L/s; nominal balance predicts {exp:+.1f} mm/min"
                ),
            }
        )
    return alarms
