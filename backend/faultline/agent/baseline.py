"""Comparator A: a deterministic reference diagnostic procedure (NOT AI).

It plugs into the same loop, tools, validation, observations and budgets as
the Nemotron agent, acting as a provider that reads the public tool results
already in the conversation and emits the next tool call. It never sees the
plant or the truth.

Procedure (written before any evaluation ran):
 1. Read the alarm window. No BAL-101 deviation -> no fault.
 2. Candidates: rate below nominal -> reduced pump or leak; reading flat ->
    also a stuck sensor (a leak or a pump deficit can make the level flat too).
 3. Use the first available separating test, in this order:
    FT-101 inlet flow -> dip reading (only if a stuck sensor is a candidate)
    -> P-101 stop test.
 4. Decide with 3-sigma rules on the stated uncertainties; otherwise submit
    inconclusive and ask for the missing measurement.
"""

from __future__ import annotations

import json
import math
from typing import Any

from ..analysis import flow_L_s_from_rate
from ..sim.spec import NOMINAL
from .provider import ProviderResult, tool_call
from .public_model import HYPOTHESES

QR = NOMINAL.pump_rated_flow_m3s * 1000  # L/s
LT_SD_MM = NOMINAL.level_sensor_noise_sd_m * 1000


class ReferenceProcedure:
    name = "reference-procedure"
    label = "REFERENCE PROCEDURE (deterministic, not AI)"
    model = "reference-procedure-v1"
    billable = False  # makes no API calls, so the spending ceiling never applies

    def __init__(self) -> None:
        self.calls = 0

    # -- reading the conversation (public tool results only) --
    @staticmethod
    def _results(messages: list[dict]) -> list[tuple[str, dict]]:
        out = []
        for m in messages:
            if m.get("role") == "tool":
                try:
                    out.append((m.get("name", ""), json.loads(m["content"])))
                except (ValueError, KeyError):
                    pass
        return out

    @staticmethod
    def _site(messages: list[dict]) -> dict:
        brief = messages[1]["content"]
        return json.loads(brief[brief.index("{"):])["site_conditions"]

    def _reply(self, name: str, args: dict) -> ProviderResult:
        self.calls += 1
        return ProviderResult(message={"role": "assistant", "content": "", "tool_calls": [tool_call(name, args, f"ref-{self.calls}")]},
                              usage={"prompt_tokens": None, "completion_tokens": None, "total_tokens": None,
                                     "reasoning_tokens": None},
                              model=self.model, finish_reason="tool_calls", latency_ms=0)

    def _submit(self, outcome: str, primary: str | None, status: dict, sup: dict, con: dict, summary: str,
                remedy: str, requested: str = "", confidence: str = "medium") -> ProviderResult:
        hyps = [{"id": h, "status": status[h], "supporting_evidence": sup.get(h, []),
                 "contradicting_evidence": con.get(h, []), "note": ""} for h in HYPOTHESES]
        args: dict[str, Any] = {"outcome": outcome, "hypotheses": hyps, "confidence": confidence, "summary": summary,
                                "recommended_remedy": remedy}
        if primary:
            args["primary_hypothesis"] = primary
        if requested:
            args["requested_evidence"] = requested
        return self._reply("submit_diagnosis", args)

    async def complete(self, messages, tools, tool_choice, max_tokens, timeout_s) -> ProviderResult:
        res = self._results(messages)
        site = self._site(messages)
        ev = {name: r for name, r in res if r.get("evidence_id")}
        window = next((r for n, r in res if n == "read_observations"), None)
        if window is None:
            return self._reply("read_observations", {"scope": "alarm_window", "purpose": "establish the alarm-window mass balance"})
        e1 = window["evidence_id"]
        s = window["data"]["summary"]
        r_obs, r_nom = s["level_trend"]["rate_mm_per_min"], s["nominal_expected_rate_mm_per_min"]
        se = s["level_trend"]["rate_se_mm_per_min"]
        q_d = s["FT102_mean_L_s"]
        dev = r_obs - r_nom
        flat = abs(r_obs) <= max(1.0, 3 * se)
        all_h = list(HYPOTHESES)

        if abs(dev) <= NOMINAL.balance_alarm_mm_per_min:
            st = {h: "ruled_out" for h in all_h}
            st["no_fault"] = "supported"
            return self._submit("diagnosed", "no_fault", st, {"no_fault": [e1]},
                                {h: [e1] for h in all_h if h != "no_fault"},
                                f"{e1}: LT-101 rate {r_obs:+.1f} mm/min matches the nominal balance {r_nom:+.1f} mm/min.",
                                "no_action")
        if dev > 0 and not flat:
            st = {h: "open" for h in all_h}
            return self._submit("inconclusive", None, st, {}, {}, f"{e1}: level rises faster than the nominal balance; "
                                "no single catalogued fault explains that.", "none_until_more_evidence",
                                "an independent level reading and an FT-101 inlet-flow reading", "low")

        cands = {"pump_delivery_reduced", "tank_leak"} | ({"level_sensor_stuck"} if flat else set())
        status = {h: ("open" if h in cands else "ruled_out") for h in all_h}
        con = {h: [e1] for h in all_h if h not in cands}
        sup: dict[str, list[str]] = {}

        inlet = ev.get("measure_inlet_flow")
        dip = ev.get("request_independent_level_measurement")
        stop = ev.get("set_simulated_pump")
        avail = site

        # --- FT-101 ---
        if inlet is None and avail["inlet_flow_meter_FT101"] == "available":
            return self._reply("measure_inlet_flow", {"duration_s": 60, "purpose": "separate reduced pump delivery from a leak"})
        if inlet is not None:
            q_in = inlet["data"]["mean_inlet_flow_L_s"]
            sd = inlet["data"]["stated_uncertainty_sd_L_s"]
            e = inlet["evidence_id"]
            if q_in < QR - 3 * sd:
                status["pump_delivery_reduced"] = "supported"
                sup["pump_delivery_reduced"] = [e]
                q_net = flow_L_s_from_rate(r_obs)
                if abs(q_in - (q_net + q_d)) <= 3 * math.hypot(sd, flow_L_s_from_rate(se)) + 0.02:
                    for h in ("tank_leak", "level_sensor_stuck"):
                        if h in cands:
                            status[h] = "ruled_out"
                            con[h] = [e1, e]
                    return self._submit("diagnosed", "pump_delivery_reduced", status, sup, con,
                                        f"{e}: FT-101 {q_in:.3f} L/s vs rated {QR:.2f}; with FT-102 {q_d:.3f} L/s it closes "
                                        f"the {e1} balance, leaving no room for a leak.", "replace_or_repair_pump")
            else:
                status["pump_delivery_reduced"] = "ruled_out"
                con["pump_delivery_reduced"] = [e]
                if not flat:
                    status["tank_leak"] = "supported"
                    sup["tank_leak"] = [e1, e]
                    return self._submit("diagnosed", "tank_leak", status, sup, con,
                                        f"{e}: FT-101 {q_in:.3f} L/s is rated delivery, yet {e1} shows the level "
                                        f"{r_obs:+.1f} mm/min below balance: water leaves by an unmetered path.",
                                        "repair_tank_leak")

        # --- dip, when a stuck sensor is still possible ---
        if status.get("level_sensor_stuck") == "open":
            if dip is None and avail["independent_level_DIP101"] == "available":
                return self._reply("request_independent_level_measurement",
                                   {"purpose": "check whether LT-101 follows the true level"})
            if dip is not None:
                e = dip["evidence_id"]
                diff = dip["data"]["dip_minus_LT_mm"]
                sd = dip["data"]["comparison_sd_mm"]
                if abs(diff) > 3 * sd:
                    status["level_sensor_stuck"] = "supported"
                    sup["level_sensor_stuck"] = [e]
                    for h in ("pump_delivery_reduced", "tank_leak"):
                        if status[h] == "open":
                            status[h] = "weakened"
                            con[h] = [e]
                    return self._submit("diagnosed", "level_sensor_stuck", status, sup, con,
                                        f"{e}: dip reading differs from LT-101 by {diff:+.0f} mm (sd {sd:.0f}).",
                                        "replace_level_sensor")
                status["level_sensor_stuck"] = "ruled_out"
                con["level_sensor_stuck"] = [e]

        open_h = [h for h in all_h if status[h] in ("open", "supported")]
        if len(open_h) == 1:
            h = open_h[0]
            status[h] = "supported"
            sup.setdefault(h, [e1])
            remedy = {"tank_leak": "repair_tank_leak", "pump_delivery_reduced": "replace_or_repair_pump",
                      "level_sensor_stuck": "replace_level_sensor"}[h]
            return self._submit("diagnosed", h, status, sup, con, f"Only {h} remains consistent with the evidence.", remedy)

        # --- P-101 stop test ---
        if stop is None and avail["pump_stop_test"].startswith("permitted"):
            hold = min(300, int(float(avail["pump_stop_test"].split("at most ")[1].split(" ")[0])))
            return self._reply("set_simulated_pump", {"state": "off", "hold_s": hold,
                                                      "purpose": "with P-101 stopped, any fall beyond FT-102 demand is a leak"})
        if stop is not None:
            e = stop["evidence_id"]
            tr = stop["data"]["LT101_trend_while_stopped"]
            r_stop, se_stop = tr["rate_mm_per_min"], tr["rate_se_mm_per_min"]
            r_dem = -q_d / 1000 / NOMINAL.tank_area_m2 * 60000
            margin = 3 * se_stop + 1.0
            if status.get("level_sensor_stuck") == "open" and abs(r_stop) <= margin:
                status["level_sensor_stuck"] = "supported"
                sup["level_sensor_stuck"] = [e]
                for h in ("pump_delivery_reduced", "tank_leak"):
                    status[h] = "ruled_out"
                    con[h] = [e]
                return self._submit("diagnosed", "level_sensor_stuck", status, sup, con,
                                    f"{e}: LT-101 did not move ({r_stop:+.2f} mm/min) with P-101 stopped and demand "
                                    f"{q_d:.2f} L/s.", "replace_level_sensor")
            if status.get("level_sensor_stuck") == "open":
                status["level_sensor_stuck"] = "ruled_out"
                con["level_sensor_stuck"] = [e]
            if r_stop < r_dem - margin:
                status["tank_leak"] = "supported"
                sup["tank_leak"] = [e]
                status["pump_delivery_reduced"] = "ruled_out"
                con["pump_delivery_reduced"] = [e]
                return self._submit("diagnosed", "tank_leak", status, sup, con,
                                    f"{e}: with P-101 stopped LT-101 fell {r_stop:+.1f} mm/min, faster than demand alone "
                                    f"({r_dem:+.1f}).", "repair_tank_leak")
            if abs(r_stop - r_dem) <= margin:
                status["pump_delivery_reduced"] = "supported"
                sup["pump_delivery_reduced"] = [e]
                status["tank_leak"] = "ruled_out"
                con["tank_leak"] = [e]
                return self._submit("diagnosed", "pump_delivery_reduced", status, sup, con,
                                    f"{e}: with P-101 stopped LT-101 fell at the demand rate ({r_stop:+.1f} vs "
                                    f"{r_dem:+.1f} mm/min), so no leak; the deficit is pump delivery.",
                                    "replace_or_repair_pump")

        requested = []
        if avail["inlet_flow_meter_FT101"] != "available":
            requested.append("an FT-101 inlet-flow reading")
        if "level_sensor_stuck" in open_h and avail["independent_level_DIP101"] != "available":
            requested.append("an independent dip reading")
        if not avail["pump_stop_test"].startswith("permitted"):
            requested.append("permission for a short P-101 stop test")
        return self._submit("inconclusive", None, status, sup, con,
                            f"{e1}: the level is {dev:+.1f} mm/min off the nominal balance, but the permitted "
                            f"instruments cannot separate {', '.join(open_h)}.", "none_until_more_evidence",
                            " or ".join(requested) or "a separating measurement", "low")
