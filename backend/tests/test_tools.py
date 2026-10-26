"""Tool validation outside the model: schemas, site rules, budgets, evidence rules."""

import json

import pytest

from faultline.agent.tools import TOOL_SPECS, ToolExecutor
from faultline.instruments import InstrumentPanel
from faultline.sim.twins import AMBIGUOUS_SITE, falling_level_pair, flat_reading_pair


def ex(site=None, member=0, seed=5):
    return ToolExecutor(InstrumentPanel(falling_level_pair(site).members[member], seed))


def read(e):
    return e.execute("read_observations", {"scope": "alarm_window", "purpose": "baseline"})


def test_registry_contains_only_real_tools():
    assert set(TOOL_SPECS) == {"read_observations", "measure_inlet_flow", "request_independent_level_measurement",
                               "set_simulated_pump", "advance_simulation", "predict_under_hypothesis",
                               "update_hypotheses", "submit_diagnosis"}
    for spec in TOOL_SPECS.values():
        assert spec["function"]["parameters"]["additionalProperties"] is False


@pytest.mark.parametrize("name,args,needle", [
    ("reveal_truth", {}, "unknown tool"),
    ("measure_inlet_flow", "{not json", "not valid JSON"),
    ("measure_inlet_flow", {"duration_s": 5, "purpose": "x" * 10}, "duration_s"),
    ("measure_inlet_flow", {"duration_s": 60, "purpose": "split", "hidden": 1}, "hidden"),
    ("set_simulated_pump", {"state": "on", "hold_s": 120, "purpose": "test it"}, "state"),
    ("set_simulated_pump", {"state": "off", "hold_s": 900, "purpose": "test it"}, "hold_s"),
    ("advance_simulation", {"duration_s": 60}, "purpose"),
])
def test_invalid_calls_are_rejected_with_explicit_errors(name, args, needle):
    out = ex().execute(name, args)
    assert not out.ok
    assert needle in out.result["error"]


def test_site_limit_on_pump_stop_hold_is_enforced_in_backend():
    e = ex()
    out = e.execute("set_simulated_pump", {"state": "off", "hold_s": 400, "purpose": "too long for this site"})
    assert not out.ok and "between 60 and 300" in out.result["error"]


def test_unavailable_instruments_and_forbidden_actions_are_refused():
    e = ex(AMBIGUOUS_SITE)
    assert "unavailable" in e.execute("measure_inlet_flow", {"duration_s": 60, "purpose": "pump?"}).result["error"]
    assert "unavailable" in e.execute("request_independent_level_measurement", {"purpose": "sensor?"}).result["error"]
    assert "not permitted" in e.execute("set_simulated_pump", {"state": "off", "hold_s": 120, "purpose": "leak?"}).result["error"]
    assert e.evidence == []  # refused calls create no evidence and cost no simulated time
    assert e.panel.time.used_s == 0


def test_simulated_time_allowance_is_enforced():
    e = ex(AMBIGUOUS_SITE)  # 600 s allowance
    assert e.execute("advance_simulation", {"duration_s": 500, "purpose": "watch trend"}).ok
    out = e.execute("advance_simulation", {"duration_s": 200, "purpose": "watch more"})
    assert not out.ok and "allowance exceeded" in out.result["error"]


def test_measurements_get_sequential_evidence_ids_and_timestamps():
    e = ex()
    r1 = read(e)
    r2 = e.execute("measure_inlet_flow", {"duration_s": 60, "purpose": "pump vs leak"})
    r3 = e.execute("request_independent_level_measurement", {"purpose": "sensor check"})
    assert [r1.evidence_id, r2.evidence_id, r3.evidence_id] == ["E1", "E2", "E3"]
    assert r2.result["t_start_s"] == 0 and r2.result["t_end_s"] == 90  # 30 s fit/settle + 60 s averaging
    assert (r2.result["data"]["t_start_s"], r2.result["data"]["t_end_s"]) == (30, 90)
    assert r3.result["data"]["t_s"] == 210
    assert r3.result["data"]["LT101_sample_t_s"] == 210  # comparable reading logged at the same step


def test_predictions_need_the_alarm_window_and_cannot_be_cited_as_evidence():
    e = ex()
    out = e.execute("predict_under_hypothesis", {"hypothesis": "tank_leak", "test": "inlet_flow", "purpose": "what if"})
    assert not out.ok and "read_observations" in out.result["error"]
    read(e)
    p = e.execute("predict_under_hypothesis", {"hypothesis": "tank_leak", "test": "inlet_flow", "purpose": "what if"})
    assert p.ok and p.prediction_id == "P1" and "MODEL-BASED EXPECTATION" in p.result["kind"]
    bad = e.execute("update_hypotheses", {"hypotheses": [{"id": "tank_leak", "status": "supported",
                                                          "supporting_evidence": ["P1"], "contradicting_evidence": []}]})
    assert not bad.ok and "not evidence" in bad.result["error"]


def test_predictions_use_only_public_inputs():
    import inspect

    from faultline.agent import public_model

    src = inspect.getsource(public_model)
    for forbidden in ("Plant", "CaseConfig", "FaultConfig", "instruments", "judge", "sim.case", "sim.plant"):
        assert forbidden not in src


def _board(**status):
    base = {"no_fault": "ruled_out", "pump_delivery_reduced": "ruled_out", "tank_leak": "ruled_out",
            "level_sensor_stuck": "ruled_out"}
    base.update(status)
    return [{"id": h, "status": s, "supporting_evidence": ["E1"] if s == "supported" else [],
             "contradicting_evidence": ["E1"] if s in ("ruled_out", "weakened") else []} for h, s in base.items()]


def test_diagnosis_requires_cited_support_and_contradicted_alternatives():
    e = ex()
    read(e)
    loose = e.execute("submit_diagnosis", {
        "outcome": "diagnosed", "primary_hypothesis": "tank_leak", "confidence": "high", "summary": "it is a leak",
        "recommended_remedy": "repair_tank_leak",
        "hypotheses": _board(tank_leak="supported", pump_delivery_reduced="open")})
    assert not loose.ok and "pump_delivery_reduced" in loose.result["error"]
    unknown = e.execute("submit_diagnosis", {
        "outcome": "diagnosed", "primary_hypothesis": "tank_leak", "confidence": "high", "summary": "E9 shows a leak",
        "recommended_remedy": "repair_tank_leak",
        "hypotheses": [dict(h, supporting_evidence=["E9"]) if h["id"] == "tank_leak" else h
                       for h in _board(tank_leak="supported")]})
    assert not unknown.ok and "unknown evidence id" in unknown.result["error"]
    assert e.diagnosis is None


def test_inconclusive_requires_open_alternatives_and_requested_evidence():
    e = ex()
    read(e)
    out = e.execute("submit_diagnosis", {
        "outcome": "inconclusive", "confidence": "low", "summary": "E1 cannot separate pump from leak",
        "recommended_remedy": "none_until_more_evidence",
        "hypotheses": _board(tank_leak="open", pump_delivery_reduced="open")})
    assert not out.ok and "requested_evidence" in out.result["error"]
    ok = e.execute("submit_diagnosis", {
        "outcome": "inconclusive", "confidence": "low", "summary": "E1 cannot separate pump from leak",
        "recommended_remedy": "none_until_more_evidence", "requested_evidence": "FT-101 inlet flow",
        "hypotheses": _board(tank_leak="open", pump_delivery_reduced="open")})
    assert ok.ok and ok.terminal and e.diagnosis["outcome"] == "inconclusive"


def test_identical_actions_reproduce_identical_evidence():
    def trace(seed):
        e = ex(seed=seed)
        read(e)
        e.execute("measure_inlet_flow", {"duration_s": 60, "purpose": "pump vs leak"})
        e.execute("set_simulated_pump", {"state": "off", "hold_s": 120, "purpose": "leak test"})
        return json.dumps([x.public() for x in e.evidence], sort_keys=True)

    assert trace(9) == trace(9)
    assert trace(9) != trace(10)


def test_off_grid_durations_are_rejected_before_touching_the_plant():
    e = ex()
    for name, args in [("measure_inlet_flow", {"duration_s": 45, "purpose": "pump vs leak"}),
                       ("advance_simulation", {"duration_s": 95, "purpose": "watch"}),
                       ("set_simulated_pump", {"state": "off", "hold_s": 125, "purpose": "leak test"})]:
        out = e.execute(name, args)
        assert not out.ok and "multiple of 10" in out.result["error"]
    assert e.panel.now_s == 0 and e.evidence == []


def test_dip_reading_always_has_a_same_step_lt101_comparison():
    e = ex()
    e.execute("advance_simulation", {"duration_s": 30, "purpose": "watch"})
    e.execute("measure_inlet_flow", {"duration_s": 50, "purpose": "pump vs leak"})
    out = e.execute("request_independent_level_measurement", {"purpose": "sensor check"})
    assert out.ok and out.result["data"]["LT101_sample_t_s"] == out.result["data"]["t_s"]


def test_unexpected_tool_failure_is_contained(monkeypatch):
    e = ex()

    def boom(*a, **k):
        raise TypeError("internal detail that must not reach the model")

    monkeypatch.setattr(e.panel, "independent_level", boom)
    out = e.execute("request_independent_level_measurement", {"purpose": "sensor check"})
    assert not out.ok and out.result["error"] == "internal tool error; the call was not completed"


def test_inlet_flow_after_a_stop_test_is_measured_at_steady_state():
    e = ToolExecutor(InstrumentPanel(falling_level_pair().members[1], 3))  # healthy pump + leak
    e.execute("set_simulated_pump", {"state": "off", "hold_s": 120, "purpose": "leak test"})
    out = e.execute("measure_inlet_flow", {"duration_s": 30, "purpose": "pump check"})
    q, sd = out.result["data"]["mean_inlet_flow_L_s"], out.result["data"]["stated_uncertainty_sd_L_s"]
    assert abs(q - 1.20) < 4 * sd  # spin-up excluded by the 30 s fit-and-settle period


def test_inconclusive_cannot_rule_out_without_evidence():
    e = ex()
    read(e)
    board = [{"id": "no_fault", "status": "ruled_out", "supporting_evidence": [], "contradicting_evidence": ["E1"]},
             {"id": "pump_delivery_reduced", "status": "open", "supporting_evidence": [], "contradicting_evidence": []},
             {"id": "tank_leak", "status": "open", "supporting_evidence": [], "contradicting_evidence": []},
             {"id": "level_sensor_stuck", "status": "ruled_out", "supporting_evidence": [], "contradicting_evidence": []}]
    out = e.execute("submit_diagnosis", {"outcome": "inconclusive", "confidence": "low", "summary": "E1 cannot decide",
                                         "recommended_remedy": "none_until_more_evidence",
                                         "requested_evidence": "FT-101", "hypotheses": board})
    assert not out.ok and "level_sensor_stuck" in out.result["error"]
