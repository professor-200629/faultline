"""Twin pairs: physically valid cases with matching initial observations.

Nothing here hand-authors telemetry. Each twin is an ordinary `CaseConfig`
whose hidden parameter is CALIBRATED by running the noise-free simulator, so
that the alarm-window observations of the two members agree. Tests in
`tests/test_twins.py` prove the match and the separating responses.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

from .case import CaseConfig, FaultConfig, SiteConditions
from .plant import noise_free_plant
from .spec import NOMINAL

A = NOMINAL.tank_area_m2
QR = NOMINAL.pump_rated_flow_m3s
W = NOMINAL.alarm_window_s


def _end_level(case: CaseConfig) -> float:
    p = noise_free_plant(case)
    p.advance_to(0.0)
    return p.historian[-1].lt101_m


def _bisect(f, lo: float, hi: float, iters: int = 60) -> float:
    flo = f(lo)
    for _ in range(iters):
        mid = 0.5 * (lo + hi)
        fm = f(mid)
        if (fm > 0) == (flo > 0):
            lo, flo = mid, fm
        else:
            hi = mid
    return 0.5 * (lo + hi)


def calibrate_leak(base: CaseConfig, goal_end_level_m: float) -> CaseConfig:
    """Healthy pump + orifice leak on `base` whose end-of-window LT-101 reading is the goal."""

    def leak_case(c: float) -> CaseConfig:
        return replace(base, fault=FaultConfig(family="tank_leak", leak_coeff_m25_s=c))

    c_hi = 2 * QR / math.sqrt(max(base.initial_level_m, 0.05))
    c = _bisect(lambda c: _end_level(leak_case(c)) - goal_end_level_m, 0.0, c_hi)
    return leak_case(c)


def calibrate_pump(base: CaseConfig, goal_end_level_m: float) -> CaseConfig:
    """Reduced pump (no leak) on `base` whose end-of-window LT-101 reading is the goal."""

    def pump_case(k: float) -> CaseConfig:
        return replace(base, fault=FaultConfig(family="pump_delivery_reduced", pump_capacity_factor=k))

    k = _bisect(lambda k: _end_level(pump_case(k)) - goal_end_level_m, 0.0, 1.0)
    return pump_case(k)


def calibrate_leak_to_match(target: CaseConfig) -> CaseConfig:
    base = replace(target, fault=FaultConfig(family="no_fault"))
    return calibrate_leak(base, _end_level(target))


def calibrate_pump_to_match(target: CaseConfig) -> CaseConfig:
    base = replace(target, fault=FaultConfig(family="no_fault"))
    return calibrate_pump(base, _end_level(target))


@dataclass(frozen=True)
class TwinPair:
    pair_id: str
    title: str
    situation: str  # public description shown to judge and agent alike
    members: tuple[CaseConfig, CaseConfig]
    member_labels: tuple[str, str]  # private: fault description per member
    distinguishing_tests: str  # public hint for the judge after the run


def falling_level_pair(site: SiteConditions | None = None) -> TwinPair:
    site = site or SiteConditions(note="Standard maintenance window; FT-101 clamp and dip tape on site.")
    worn = CaseConfig(
        fault=FaultConfig(family="pump_delivery_reduced", pump_capacity_factor=0.625),
        initial_level_m=1.55,
        demand_m3s=1.0e-3,
        site=site,
    )
    leak = calibrate_leak_to_match(worn)
    return TwinPair(
        pair_id="falling-level",
        title="Level falling while P-101 runs",
        situation="T-101 has been falling for 15 minutes although P-101 shows RUNNING and demand is normal.",
        members=(worn, leak),
        member_labels=("P-101 delivering 62.5% of rated flow (worn impeller), no leak",
                       "P-101 healthy, orifice leak calibrated to the same level trend"),
        distinguishing_tests="An FT-101 inlet-flow reading, or a short P-101 stop test, separates them; "
        "an independent dip reading does not (both level sensors are healthy).",
    )


def flat_reading_pair(site: SiteConditions | None = None) -> TwinPair:
    site = site or SiteConditions(note="Standard maintenance window; FT-101 clamp and dip tape on site.")
    s = 1.80
    demand = 1.0e-3
    balanced = CaseConfig(
        fault=FaultConfig(family="pump_delivery_reduced", pump_capacity_factor=demand / QR),
        initial_level_m=s,
        demand_m3s=demand,
        site=site,
    )
    # Sensing element froze at s when the true level was s, 10 min before the window;
    # the healthy pump has kept filling the tank since then.
    lead_s = 600.0
    true_rate = (QR - demand) / A
    stuck = CaseConfig(
        fault=FaultConfig(family="level_sensor_stuck", stuck_at_m=s),
        initial_level_m=s + true_rate * lead_s,
        demand_m3s=demand,
        site=site,
    )
    return TwinPair(
        pair_id="flat-reading",
        title="Level reading flat while P-101 runs",
        situation="LT-101 has read about 1.80 m for 15 minutes although P-101 shows RUNNING and demand is "
        "below the pump rating.",
        members=(stuck, balanced),
        member_labels=("LT-101 sensing element stuck at 1.80 m; true level rising",
                       "P-101 delivering exactly the demand (83% of rated); level genuinely steady"),
        distinguishing_tests="A dip reading, an FT-101 reading, or a P-101 stop test separates them.",
    )


AMBIGUOUS_SITE = SiteConditions(
    inlet_meter_available=False,
    independent_level_available=False,
    pump_stop_test_permitted=False,
    max_extra_sim_s=600.0,
    note="Night shift: no FT-101 clamp on site, roof hatch locked out (no dip reading), and P-101 must keep "
    "running because T-101 feeds a critical user. At most 10 more minutes before a decision.",
)


def all_pairs() -> dict[str, TwinPair]:
    return {p.pair_id: p for p in (falling_level_pair(), flat_reading_pair())}
