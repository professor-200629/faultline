"""`predict_under_hypothesis`: model-based expectations from PUBLIC data only.

Inputs are the evidence ledger (observations the agent has already obtained),
the nominal datasheet and an explicit candidate hypothesis. The module never
sees the plant, the case or the truth. Outputs are labelled expectations, not
observations, and cannot be cited as evidence.
"""

from __future__ import annotations

import math

from ..analysis import flow_L_s_from_rate, rate_mm_min_from_flow
from ..sim.spec import NOMINAL

HYPOTHESES = {
    "no_fault": "No equipment fault; the warning is explained by operating conditions",
    "pump_delivery_reduced": "P-101 delivers less than rated flow (worn, blocked or failed) while its motor runs",
    "tank_leak": "Unintended leak from T-101",
    "level_sensor_stuck": "LT-101 sensing element stuck; reading no longer follows the true level",
}
TESTS = ("inlet_flow", "independent_level", "pump_stop_test", "wait")


class PredictionError(Exception):
    pass


def _baseline(window_summary: dict) -> dict:
    tr = window_summary["level_trend"]
    q_d = window_summary["FT102_mean_L_s"]
    r_obs = tr["rate_mm_per_min"]
    se = tr["rate_se_mm_per_min"]
    rated = NOMINAL.pump_rated_flow_m3s * 1000
    q_net = flow_L_s_from_rate(r_obs)
    return {"r_obs": r_obs, "se": se, "q_d": q_d, "rated": rated, "q_net": q_net,
            "se_flow": flow_L_s_from_rate(se), "last_m": tr["last_m"], "t_to_s": tr["t_to_s"],
            "t_from_s": tr["t_from_s"]}


def _flows(h: str, b: dict) -> dict:
    """Pump delivery and leak implied by the alarm window under hypothesis h (L/s)."""
    if h == "no_fault":
        return {"q_in": b["rated"], "q_leak": 0.0, "lt_follows_true_level": True}
    if h == "pump_delivery_reduced":
        return {"q_in": max(0.0, b["q_net"] + b["q_d"]), "q_leak": 0.0, "lt_follows_true_level": True}
    if h == "tank_leak":
        return {"q_in": b["rated"], "q_leak": max(0.0, b["rated"] - b["q_d"] - b["q_net"]), "lt_follows_true_level": True}
    if h == "level_sensor_stuck":
        return {"q_in": b["rated"], "q_leak": 0.0, "lt_follows_true_level": False}
    raise PredictionError(f"unknown hypothesis {h!r}")


def _leak_projection(b: dict, f: dict, duration_s: float, q_in_L_s: float) -> tuple[float, float]:
    """Level change (mm) and end rate (mm/min) for an orifice leak at the tank bottom, integrated forward.

    The leak coefficient is fitted from the alarm window: C = q_leak / sqrt(h_last). A bottom leak gives the
    smallest possible slowing (dQ/dh >= Q / (2h) for any leak height), so the projected slowing is a lower bound.
    """
    area = NOMINAL.tank_area_m2
    h = b["last_m"]
    c = (f["q_leak"] / 1000.0) / math.sqrt(max(h, 1e-6))
    q_in, q_d = q_in_L_s / 1000.0, b["q_d"] / 1000.0
    dt, t = 1.0, 0.0
    while t < duration_s - 1e-9:
        h = max(0.0, h + dt * (q_in - q_d - c * math.sqrt(max(h, 0.0))) / area)
        t += dt
    end_rate = (q_in - q_d - c * math.sqrt(max(h, 0.0))) / area * 60000.0
    return (h - b["last_m"]) * 1000.0, end_rate


def predict(hypothesis: str, test: str, window_summary: dict, now_s: float, duration_s: float | None = None) -> dict:
    if hypothesis not in HYPOTHESES:
        raise PredictionError(f"hypothesis must be one of {sorted(HYPOTHESES)}")
    if test not in TESTS:
        raise PredictionError(f"test must be one of {list(TESTS)}")
    b = _baseline(window_summary)
    f = _flows(hypothesis, b)
    n = NOMINAL
    assumptions = [
        "nominal tank area and P-101 rating from the datasheet",
        "single fault; demand stays at the FT-102 alarm-window mean",
        "fault size inferred from the alarm-window LT-101 trend" if hypothesis in ("pump_delivery_reduced", "tank_leak") else
        "no fault parameters needed",
    ]
    out: dict = {"kind": "MODEL-BASED EXPECTATION (public nominal model; not an observation)",
                 "hypothesis": hypothesis, "test": test, "assumptions": assumptions}

    if test == "inlet_flow":
        sd_meter = n.inlet_meter_noise_rel * f["q_in"] + n.inlet_meter_noise_abs_m3s * 1000
        sd_fit = b["se_flow"] if hypothesis == "pump_delivery_reduced" else 0.0
        out["expected_FT101_L_s"] = round(f["q_in"], 3)
        out["expected_sd_L_s"] = round(math.hypot(sd_meter, sd_fit), 3)
    elif test == "independent_level":
        sd = math.hypot(n.dip_noise_sd_m, n.level_sensor_noise_sd_m) * 1000
        if f["lt_follows_true_level"]:
            out["expected_dip_minus_LT_mm"] = 0.0
            out["expected_sd_mm"] = round(sd, 1)
        else:
            # True level keeps following the nominal balance since at least the window start.
            true_rate = rate_mm_min_from_flow(b["rated"] - b["q_d"])
            elapsed_min = (now_s + n.dip_duration_s - b["t_from_s"]) / 60.0
            out["expected_dip_minus_LT_mm"] = f"at least {true_rate * elapsed_min:+.0f} (sign of nominal balance; grows with time since the element froze)"
            out["expected_sd_mm"] = round(sd, 1)
    elif test == "pump_stop_test":
        hold = duration_s or 300.0
        if f["lt_follows_true_level"]:
            rate = rate_mm_min_from_flow(-(b["q_d"] + f["q_leak"]))
            # pump run-down adds about q_in * tau of volume after the stop command
            ramp_mm = f["q_in"] / 1000 * n.pump_time_constant_s / n.tank_area_m2 * 1000
            if hypothesis == "tank_leak":
                change, end_rate = _leak_projection(b, f, hold, 0.0)
                out["expected_LT_rate_during_stop_mm_per_min"] = round(rate, 2)
                out["expected_LT_change_mm"] = round(change + ramp_mm, 1)
                out["assumptions"].append("orifice leak at the tank bottom (least possible slowing)")
            else:
                out["expected_LT_rate_during_stop_mm_per_min"] = round(rate, 2)
                out["expected_LT_change_mm"] = round(rate * hold / 60.0 + ramp_mm, 1)
        else:
            out["expected_LT_rate_during_stop_mm_per_min"] = 0.0
            out["expected_LT_change_mm"] = 0.0
        out["expected_sd_mm"] = round(math.sqrt(2) * n.level_sensor_noise_sd_m * 1000, 1)
        out["hold_s"] = hold
    elif test == "wait":
        dur = duration_s or 600.0
        rate = b["r_obs"] if f["lt_follows_true_level"] else 0.0
        out["expected_sd_mm"] = round(math.hypot(math.sqrt(2) * n.level_sensor_noise_sd_m * 1000, b["se"] * dur / 60.0), 1)
        out["duration_s"] = dur
        if hypothesis == "tank_leak":
            change, end_rate = _leak_projection(b, f, dur, f["q_in"])
            out["expected_LT_change_mm"] = round(change, 1)
            out["expected_LT_rate_at_end_mm_per_min"] = round(end_rate, 2)
            out["expected_rate_change_from_alarm_window_mm_per_min"] = round(end_rate - b["r_obs"], 2)
            out["assumptions"].append("orifice leak at the tank bottom: the fall slows as the level drops "
                                      "(least possible slowing; a higher leak slows more)")
        else:
            out["expected_LT_change_mm"] = round(rate * dur / 60.0, 1)
            out["expected_LT_rate_at_end_mm_per_min"] = round(rate, 2)
            out["expected_rate_change_from_alarm_window_mm_per_min"] = 0.0
    out["implied_P101_delivery_L_s"] = round(f["q_in"], 3)
    out["implied_leak_L_s"] = round(f["q_leak"], 3)
    return out
