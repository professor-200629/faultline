"""Twin Challenge claims: matching initial observations, separating tests, honest ambiguity."""

import pytest

from faultline.analysis import evaluate_alarms, window_summary
from faultline.instruments import InstrumentPanel
from faultline.judge.identifiability import (TWIN_TOL_LT_M, identifiability, separation, probe_outcomes,
                                             window_deviation)
from faultline.sim.twins import AMBIGUOUS_SITE, all_pairs, falling_level_pair, flat_reading_pair


@pytest.mark.parametrize("pair_id", ["falling-level", "flat-reading"])
def test_twin_members_have_different_hidden_causes(pair_id):
    a, b = all_pairs()[pair_id].members
    assert a.fault.family != b.fault.family


@pytest.mark.parametrize("pair_id", ["falling-level", "flat-reading"])
def test_noise_free_alarm_windows_match_within_declared_tolerance(pair_id):
    a, b = all_pairs()[pair_id].members
    dev = window_deviation(a, b)
    assert dev["match"], dev
    assert dev["max_LT101_diff_m"] <= TWIN_TOL_LT_M
    assert dev["max_FT102_diff_L_s"] == 0.0
    assert not dev["pump_command_differs"]


@pytest.mark.parametrize("pair_id", ["falling-level", "flat-reading"])
def test_noisy_windows_raise_the_same_alarms_and_trends_agree(pair_id):
    """With independent noise seeds, both members raise the same alarm and their
    LT-101 trends agree within their combined standard error."""
    a, b = all_pairs()[pair_id].members
    for seed_a, seed_b in [(11, 12), (101, 202), (7, 8)]:
        wa = InstrumentPanel(a, seed_a).historian(-900, 0)
        wb = InstrumentPanel(b, seed_b).historian(-900, 0)
        assert [x["tag"] for x in evaluate_alarms(wa)] == [x["tag"] for x in evaluate_alarms(wb)]
        sa, sb = window_summary(wa)["level_trend"], window_summary(wb)["level_trend"]
        combined_se = (sa["rate_se_mm_per_min"] ** 2 + sb["rate_se_mm_per_min"] ** 2) ** 0.5
        assert abs(sa["rate_mm_per_min"] - sb["rate_mm_per_min"]) < 4 * combined_se


def test_falling_pair_is_separated_by_inlet_flow_and_pump_stop_but_not_by_dip():
    worn, leak = falling_level_pair().members
    sep = separation(worn, leak)
    assert "inlet_flow" in sep["separable_by"]
    assert "pump_stop_test" in sep["separable_by"]
    assert "independent_level" not in sep["separable_by"]
    o_w, o_l = probe_outcomes(worn), probe_outcomes(leak)
    assert o_w["inlet_flow"]["FT101_L_s"] == pytest.approx(0.75, abs=0.005)
    assert o_l["inlet_flow"]["FT101_L_s"] == pytest.approx(1.20, abs=0.005)
    # with P-101 stopped, only the leak case falls faster than the demand draw
    assert o_l["pump_stop_test"]["LT_change_m"] < o_w["pump_stop_test"]["LT_change_m"] - 0.05


def test_flat_pair_is_separated_by_dip_inlet_flow_and_pump_stop():
    stuck, balanced = flat_reading_pair().members
    sep = separation(stuck, balanced)
    assert {"independent_level", "inlet_flow", "pump_stop_test"} <= set(sep["separable_by"])
    o_s, o_b = probe_outcomes(stuck), probe_outcomes(balanced)
    assert o_s["independent_level"]["dip_minus_LT_m"] > 0.10  # true level has kept rising
    assert abs(o_b["independent_level"]["dip_minus_LT_m"]) < 0.002
    assert o_s["pump_stop_test"]["LT_change_m"] == pytest.approx(0.0, abs=1e-9)  # frozen reading
    assert o_b["pump_stop_test"]["LT_change_m"] < -0.1


@pytest.mark.parametrize("pair_id", ["falling-level", "flat-reading"])
def test_every_member_is_identifiable_with_standard_instruments(pair_id):
    for m in all_pairs()[pair_id].members:
        assert identifiability(m)["identifiable"]


@pytest.mark.parametrize("make", [falling_level_pair, flat_reading_pair])
def test_members_are_not_identifiable_when_separating_instruments_are_unavailable(make):
    for m in make(AMBIGUOUS_SITE).members:
        rep = identifiability(m)
        assert rep["identifiable"] is False
        viable = [a for a in rep["alternatives"] if a["viable"]]
        assert viable and all(not a["separation"]["separable_by"] for a in viable)


def test_flat_reading_also_admits_a_balancing_leak_which_the_oracle_finds():
    stuck = flat_reading_pair().members[0]
    viable = {a["family"] for a in identifiability(stuck)["alternatives"] if a["viable"]}
    assert viable == {"pump_delivery_reduced", "tank_leak"}


def test_leak_wait_prediction_models_orifice_slowing_unlike_the_pump_hypothesis():
    from faultline.agent.tools import ToolExecutor

    e = ToolExecutor(InstrumentPanel(falling_level_pair().members[1], 21))
    e.execute("read_observations", {"scope": "alarm_window", "purpose": "baseline"})
    args = {"test": "wait", "duration_s": 1200, "purpose": "does waiting separate them?"}
    p_leak = e.execute("predict_under_hypothesis", {**args, "hypothesis": "tank_leak"}).result
    p_pump = e.execute("predict_under_hypothesis", {**args, "hypothesis": "pump_delivery_reduced"}).result
    assert p_leak["expected_rate_change_from_alarm_window_mm_per_min"] > 0.3  # the fall slows
    assert p_pump["expected_rate_change_from_alarm_window_mm_per_min"] == 0.0
    # the leak expectation matches the noise-free simulator within 3 of its stated sd, and beats the pump one
    from faultline.judge.identifiability import probe_outcomes
    from dataclasses import replace
    leak = replace(falling_level_pair().members[1], site=replace(falling_level_pair().members[1].site,
                                                                   max_extra_sim_s=1200.0))
    truth = probe_outcomes(leak)["wait"]["LT_change_m"] * 1000
    err_leak = abs(p_leak["expected_LT_change_mm"] - truth)
    err_pump = abs(p_pump["expected_LT_change_mm"] - truth)
    assert err_leak < 3 * p_leak["expected_sd_mm"] and err_leak < err_pump


def test_minimum_fault_size_is_symmetric_for_pump_and_leak():
    from faultline.judge.identifiability import MIN_MISSING_FLOW_L_S, build_alternatives
    from faultline.sim.case import CaseConfig, FaultConfig

    small_leak = CaseConfig(FaultConfig("tank_leak", leak_coeff_m25_s=0.10e-3 / 1.6 ** 0.5), initial_level_m=1.6,
                            demand_m3s=1.0e-3, site=AMBIGUOUS_SITE)
    small_pump = CaseConfig(FaultConfig("pump_delivery_reduced", pump_capacity_factor=1 - 0.10 / 1.2),
                            initial_level_m=1.6, demand_m3s=1.0e-3, site=AMBIGUOUS_SITE)
    assert MIN_MISSING_FLOW_L_S == 0.05
    alt_of_leak = {a.family: a.viable for a in build_alternatives(small_leak)}
    alt_of_pump = {a.family: a.viable for a in build_alternatives(small_pump)}
    assert alt_of_leak["pump_delivery_reduced"] and alt_of_pump["tank_leak"]  # 0.10 L/s twins stay mutual twins
    assert identifiability(small_leak)["identifiable"] == identifiability(small_pump)["identifiable"] is False
