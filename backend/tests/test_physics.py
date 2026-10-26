"""Simulator verification against analytic solutions and physical invariants.

These tests check the physics independently of the agent and the evaluator:
if the integrator were wrong, both would otherwise share the same mistake.
"""

import math
import statistics

import pytest

from faultline.analysis import rate_mm_min_from_flow
from faultline.sim.case import CaseConfig, FaultConfig, SiteConditions
from faultline.sim.plant import WINDOW_START_S, Plant, noise_free_plant
from faultline.sim.spec import NOMINAL

A = NOMINAL.tank_area_m2
QR = NOMINAL.pump_rated_flow_m3s


def case(family="no_fault", h0=1.5, demand=1.0e-3, pump_on=True, **fault):
    return CaseConfig(fault=FaultConfig(family=family, **fault), initial_level_m=h0, demand_m3s=demand,
                      pump_command_on=pump_on, site=SiteConditions())


def test_units_rate_conversion():
    # 0.2 L/s net into 2.0 m^2 rises 0.1 mm/s = 6 mm/min
    assert rate_mm_min_from_flow(0.2) == pytest.approx(6.0)


def test_no_flow_volume_is_constant():
    p = noise_free_plant(case(pump_on=False, demand=0.0))
    v0 = p.volume_m3
    p.advance_to(3600)
    assert p.volume_m3 == v0
    assert p.totals.inflow == 0 and p.totals.demand_out == 0 and p.totals.leak_out == 0


def test_constant_net_flow_matches_analytic_linear_solution():
    p = noise_free_plant(case(h0=1.0, demand=0.7e-3))  # pump starts in steady state at 1.2 L/s
    p.advance_to(WINDOW_START_S + 1200)
    expected = A * 1.0 + (QR - 0.7e-3) * 1200
    assert p.volume_m3 == pytest.approx(expected, rel=1e-12, abs=1e-12)


def test_pump_start_matches_first_order_analytic_solution():
    p = noise_free_plant(case(h0=1.0, demand=0.0, pump_on=False))
    p.set_pump_command(True)
    t = 60.0
    p.advance_to(WINDOW_START_S + t)
    tau = NOMINAL.pump_time_constant_s
    expected_in = QR * (t - tau * (1 - math.exp(-t / tau)))
    assert p.totals.inflow == pytest.approx(expected_in, rel=1e-9)
    assert p.pump_flow_m3s == pytest.approx(QR * (1 - math.exp(-t / tau)), rel=1e-9)


def test_torricelli_drain_matches_analytic_solution():
    c = 3.5e-4  # m^2.5/s
    p = noise_free_plant(case(family="tank_leak", h0=1.6, demand=0.0, pump_on=False, leak_coeff_m25_s=c))
    t = 900.0
    p.advance_to(WINDOW_START_S + t)
    # dh/dt = -(c/A) sqrt(h)  =>  sqrt(h) = sqrt(h0) - c t / (2A)
    h_exact = (math.sqrt(1.6) - c * t / (2 * A)) ** 2
    assert p.true_level() == pytest.approx(h_exact, rel=1e-9)


def test_leak_drains_to_empty_without_negative_volume_and_conserves_water():
    p = noise_free_plant(case(family="tank_leak", h0=0.3, demand=0.0, pump_on=False, leak_coeff_m25_s=2e-3))
    p.advance_to(WINDOW_START_S + 4000)
    assert p.volume_m3 >= 0.0
    assert p.true_level() < 1e-3
    assert abs(p.totals.balance_error(p.volume_m3)) < 1e-12


def test_overflow_is_accounted_not_destroyed():
    p = noise_free_plant(case(h0=2.39, demand=0.2e-3))  # net +1.0 L/s at the weir
    p.advance_to(WINDOW_START_S + 600)
    v_max = A * NOMINAL.overflow_level_m
    assert p.volume_m3 == pytest.approx(v_max)
    assert p.totals.overflow_out == pytest.approx(A * 2.39 + (QR - 0.2e-3) * 600 - v_max, rel=1e-9)
    assert abs(p.totals.balance_error(p.volume_m3)) < 1e-12


def test_demand_stops_below_outlet_and_is_booked_as_unmet():
    p = noise_free_plant(case(h0=0.06, demand=1.0e-3, pump_on=False))
    p.advance_to(WINDOW_START_S + 300)
    assert p.true_level() <= NOMINAL.outlet_level_m + 1e-3
    assert p.totals.unmet_demand > 0.25  # most of 0.3 m^3 of demand could not be served
    assert abs(p.totals.balance_error(p.volume_m3)) < 1e-12


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_conservation_and_bounds_with_every_fault_and_pump_cycling(seed):
    cfgs = [
        case(),
        case(family="pump_delivery_reduced", pump_capacity_factor=0.4),
        case(family="tank_leak", leak_coeff_m25_s=6e-4, h0=2.3, demand=0.1e-3),
        case(family="level_sensor_stuck", stuck_at_m=1.2, h0=1.4),
    ]
    for c in cfgs:
        p = Plant(case=c, seed=seed)
        for k in range(40):
            p.set_pump_command(k % 3 != 0)
            p.advance_to(p.t_s + 97)
            assert 0.0 <= p.volume_m3 <= A * NOMINAL.overflow_level_m + 1e-12
            assert abs(p.totals.balance_error(p.volume_m3)) < 1e-11


def test_seeded_noise_is_reproducible_and_seed_dependent():
    a = Plant(case=case(), seed=42)
    b = Plant(case=case(), seed=42)
    c = Plant(case=case(), seed=43)
    for p in (a, b, c):
        p.advance_to(0)
    assert [s.lt101_m for s in a.historian] == [s.lt101_m for s in b.historian]
    assert [s.lt101_m for s in a.historian] != [s.lt101_m for s in c.historian]


def test_level_noise_has_the_documented_spread():
    p = Plant(case=case(pump_on=False, demand=0.0), seed=7)  # true level constant
    p.advance_to(WINDOW_START_S + 20000)
    resid = [s.lt101_m - 1.5 for s in p.historian]
    assert statistics.pstdev(resid) == pytest.approx(NOMINAL.level_sensor_noise_sd_m, rel=0.1)
    assert abs(statistics.mean(resid)) < 0.0005


def test_logical_time_and_historian_cadence():
    p = Plant(case=case(), seed=1)
    p.advance_to(0)
    ts = [s.t_s for s in p.historian]
    assert ts[0] == WINDOW_START_S and ts[-1] == 0.0
    assert all(abs((b - a) - NOMINAL.historian_interval_s) < 1e-9 for a, b in zip(ts, ts[1:]))


# ----- each fault's actual effect on measurements -----

def test_reduced_pump_lowers_delivered_flow_but_not_run_feedback():
    p = noise_free_plant(case(family="pump_delivery_reduced", pump_capacity_factor=0.5))
    p.advance_to(0)
    assert p.pump_flow_m3s == pytest.approx(0.5 * QR)
    assert p.historian[-1].pump_run_feedback == 1 and p.historian[-1].pump_command == 1


def test_leak_adds_outflow_that_depends_on_level():
    c = 4e-4
    p = noise_free_plant(case(family="tank_leak", leak_coeff_m25_s=c, h0=1.6))
    p.advance_to(0)
    v_before = p.totals.leak_out
    p.advance_to(60)
    leak_rate = (p.totals.leak_out - v_before) / 60
    assert leak_rate == pytest.approx(c * math.sqrt(p.true_level()), rel=2e-3)


def test_stuck_sensor_reads_constant_while_true_level_changes():
    p = noise_free_plant(case(family="level_sensor_stuck", stuck_at_m=1.8, h0=1.86))
    p.advance_to(600)
    assert {s.lt101_m for s in p.historian} == {1.8}
    assert p.true_level() > 1.86 + 0.05  # healthy pump, 1.0 L/s demand: about +6 mm/min
    assert p.dip_reading() == pytest.approx(p.true_level())


def test_maintenance_restores_parameters():
    p = noise_free_plant(case(family="tank_leak", leak_coeff_m25_s=4e-4))
    p.apply_maintenance("repair_tank_leak")
    p.advance_to(0)
    assert p.totals.leak_out == 0.0
    with pytest.raises(ValueError):
        p.apply_maintenance("reveal_answer")
