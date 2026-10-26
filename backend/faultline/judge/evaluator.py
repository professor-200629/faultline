"""Independent outcome checking (PRIVATE, judge side).

The evaluator grades a terminal investigation against the sealed truth and
the identifiability oracle, and verifies an approved simulated remedy by
running a copy of the true plant forward. The agent never calls this module
and never sees its output before the run is terminal.
"""

from __future__ import annotations

import copy
from typing import Optional

from ..sim.plant import Plant
from ..sim.spec import NOMINAL

CORRECT_REMEDY = {
    "no_fault": "no_action",
    "pump_delivery_reduced": "replace_or_repair_pump",
    "tank_leak": "repair_tank_leak",
    "level_sensor_stuck": "replace_level_sensor",
}
MAINTENANCE_ACTION = {
    "replace_or_repair_pump": "repair_pump",
    "repair_tank_leak": "repair_tank_leak",
    "replace_level_sensor": "replace_level_sensor",
    "no_action": "no_action",
}
EVALUATOR_VERSION = "evaluator-v3"  # v2: overflow excluded; v3: wrong_inconclusive, remedy necessity


def grade(truth_family: str, identifiable: bool, status: str, diagnosis: Optional[dict],
          viable_alternatives: Optional[list] = None) -> dict:
    """Category of one terminal investigation. Pure function of truth + outcome.

    An inconclusive outcome is *appropriate* only if the case cannot be
    separated AND the submission keeps the true cause and every viable
    alternative open (status 'open' or 'supported'); ruling out the true cause
    is a wrong inconclusive.
    """
    out = {"truth_family": truth_family, "identifiable": identifiable, "status": status,
           "evaluator_version": EVALUATOR_VERSION}
    if status in ("failed", "cancelled") or not diagnosis:
        out.update(category="no_result", correct=False, confident_wrong=False)
        return out
    outcome = diagnosis.get("outcome")
    primary = diagnosis.get("primary_hypothesis")
    conf = diagnosis.get("confidence")
    remedy = diagnosis.get("recommended_remedy")
    out["agent_outcome"] = outcome
    out["agent_primary"] = primary
    out["agent_confidence"] = conf
    out["remedy_matches_truth"] = remedy == CORRECT_REMEDY.get(truth_family)
    if outcome == "diagnosed":
        if not identifiable:
            out.update(category="unsupported_diagnosis", correct=False, lucky_guess=primary == truth_family,
                       confident_wrong=conf in ("medium", "high"))
        elif primary == truth_family:
            out.update(category="correct_diagnosis", correct=True, confident_wrong=False)
        else:
            out.update(category="wrong_diagnosis", correct=False, confident_wrong=conf in ("medium", "high"))
    elif outcome == "inconclusive":
        status_of = {h["id"]: h["status"] for h in diagnosis.get("hypotheses", [])}
        must_stay_open = [truth_family] + list(viable_alternatives or [])
        closed = [h for h in must_stay_open if status_of.get(h) not in ("open", "supported")]
        out["closed_but_still_possible"] = closed
        if closed:
            out.update(category="wrong_inconclusive", correct=False, confident_wrong=False)
        elif identifiable:
            out.update(category="unnecessary_inconclusive", correct=False, confident_wrong=False)
        else:
            out.update(category="appropriate_inconclusive", correct=True, confident_wrong=False)
    else:
        out.update(category="no_result", correct=False, confident_wrong=False)
    return out


def verify_remedy(plant: Plant, remedy: str, truth_family: Optional[str] = None, horizon_s: float = 600.0) -> dict:
    """Apply the approved simulated maintenance to the plant, then check a forward copy.

    Pass criteria (healthy plant, nominal datasheet):
      * hydraulics: true net inflow over the horizon within 0.03 L/s of
        P-101 rated delivery - mean demand - (no leak);
      * instrumentation: LT-101 sensing element within 5 mm of the true level.
    """
    action = MAINTENANCE_ACTION[remedy]
    plant.apply_maintenance(action)
    probe = copy.deepcopy(plant)
    probe.set_pump_command(True)
    probe.advance_to(probe.t_s + 60.0)  # let the pump settle after any earlier test
    tot0, t0 = copy.copy(probe.totals), probe.t_s
    probe.advance_to(t0 + horizon_s)
    dt = probe.t_s - t0
    tot = probe.totals
    # Overflow is excluded: spilling over the weir is not a fault and must not mask or fake one.
    net = (tot.inflow - tot.demand_out - tot.leak_out - (tot0.inflow - tot0.demand_out - tot0.leak_out)) / dt * 1000
    demand = (tot.demand_out - tot0.demand_out) / dt * 1000
    overflow_l = (tot.overflow_out - tot0.overflow_out) * 1000
    expected = NOMINAL.pump_rated_flow_m3s * 1000 - demand
    tracking = max(abs(r["sensed_level_m"] - r["true_level_m"]) for r in probe.truth_log if r["t_s"] >= t0)
    checks = [
        {"check": "hydraulics match the healthy nominal balance (delivery - demand - leak)", "value_L_s": round(net, 4),
         "expected_L_s": round(expected, 4), "tolerance_L_s": 0.03, "passed": abs(net - expected) <= 0.03,
         "overflow_during_check_L": round(overflow_l, 1)},
        {"check": "LT-101 tracks the true level", "max_error_mm": round(tracking * 1000, 2),
         "tolerance_mm": 5.0, "passed": tracking <= 0.005},
    ]
    if truth_family is not None:
        needed = CORRECT_REMEDY[truth_family]
        checks.append({"check": "maintenance addressed the actual fault (not unnecessary or wrong)",
                       "needed": needed, "applied": remedy, "passed": remedy == needed})
    return {"maintenance_action": action, "horizon_s": horizon_s, "checks": checks,
            "passed": all(c["passed"] for c in checks), "evaluator_version": EVALUATOR_VERSION,
            "note": "Checked by the independent evaluator on a forward copy of the true simulated plant."}
