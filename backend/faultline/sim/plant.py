"""Deterministic, time-stepped physics of tank T-101 and pump P-101.

PRIVATE MODULE. A `Plant` holds the true state and hidden fault. Agent-facing
code never receives a Plant; it receives `instruments.InstrumentPanel`, which
returns whitelisted observation records only.

Model (see SIMULATOR.md for the full derivation):

    dV/dt = Q_in(t) - Q_d(t) - Q_leak(h) - Q_over
    h     = V / A
    Q_in  : first-order response to k * Q_rated * u   (u = pump command 0/1)
    Q_d   : demand, served only while h > outlet level
    Q_leak= C * sqrt(max(h - h_leak, 0))
    Q_over: whatever volume would exceed A * h_overflow (weir crest)

Each step of dt seconds integrates volume with classical RK4, using the exact
step-average of the exponential pump response. Volume is then bounded to
[0, A * h_overflow]; overflow and any leak volume that could not physically
leave (empty tank) are booked in `Totals`, so water is conserved exactly.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Optional

from .case import CaseConfig
from .spec import NOMINAL, NominalSpec

WINDOW_START_S = -NOMINAL.alarm_window_s  # logical time of the first logged sample


class NoiseSource:
    """Seeded per-channel Gaussian noise. Same seed + same draws => same values."""

    def __init__(self, seed: int) -> None:
        self._seed = int(seed)
        self._streams: dict[str, random.Random] = {}

    def gauss(self, channel: str) -> float:
        rng = self._streams.get(channel)
        if rng is None:
            # str seeds are hashed with SHA-512 by `random`, so this is stable across runs.
            rng = random.Random(f"faultline:{self._seed}:{channel}")
            self._streams[channel] = rng
        return rng.gauss(0.0, 1.0)

    def __repr__(self) -> str:  # never print seeds
        return "NoiseSource(<redacted>)"


def quantize(x: float, resolution: float) -> float:
    if resolution <= 0:
        return x
    return round(round(x / resolution) * resolution, 9)


@dataclass
class Totals:
    """Cumulative volumes (m^3) since the plant was created."""

    initial_volume: float = 0.0
    inflow: float = 0.0
    demand_out: float = 0.0
    leak_out: float = 0.0
    overflow_out: float = 0.0
    unmet_demand: float = 0.0

    def balance_error(self, volume_now: float) -> float:
        return volume_now - (self.initial_volume + self.inflow - self.demand_out - self.leak_out - self.overflow_out)


@dataclass
class HistorianSample:
    t_s: float
    lt101_m: float
    ft102_m3s: float
    pump_command: int
    pump_run_feedback: int


@dataclass
class Plant:
    case: CaseConfig
    seed: int
    nominal: NominalSpec = NOMINAL
    t_s: float = WINDOW_START_S
    volume_m3: float = 0.0
    pump_flow_m3s: float = 0.0
    sensed_level_m: float = 0.0
    pump_command: int = 1
    last_demand_flow_m3s: float = 0.0
    totals: Totals = field(default_factory=Totals)
    historian: list[HistorianSample] = field(default_factory=list)
    truth_log: list[dict] = field(default_factory=list)  # PRIVATE: true state at each historian tick
    # mutable copies of fault parameters (simulated maintenance can change them)
    pump_capacity_factor: float = 1.0
    leak_coeff: float = 0.0
    stuck_at_m: Optional[float] = None
    level_bias_m: float = 0.0

    def __post_init__(self) -> None:
        self.noise = NoiseSource(self.seed)
        f = self.case.fault
        self.pump_capacity_factor = f.pump_capacity_factor
        self.leak_coeff = f.leak_coeff_m25_s
        self.stuck_at_m = f.stuck_at_m
        self.level_bias_m = self.case.mismatch.level_bias_m
        h0 = self.case.initial_level_m
        if not 0.0 <= h0 <= self.overflow_level:
            raise ValueError("initial level outside [0, overflow level]")
        self.volume_m3 = self.area * h0
        self.totals = Totals(initial_volume=self.volume_m3)
        self.pump_command = 1 if self.case.pump_command_on else 0
        self.pump_flow_m3s = self._pump_target()  # start in steady state
        self.sensed_level_m = self.stuck_at_m if self.stuck_at_m is not None else h0
        self.last_demand_flow_m3s = self.demand_at(self.t_s) if h0 > self.nominal.outlet_level_m else 0.0
        self._record_sample()

    def __repr__(self) -> str:  # keep hidden truth out of logs and tracebacks
        return "Plant(<redacted>)"

    # ----- true-plant constants (may differ from nominal in mismatch cases) -----
    @property
    def area(self) -> float:
        return self.case.mismatch.tank_area_m2 or self.nominal.tank_area_m2

    @property
    def pump_rated(self) -> float:
        return self.case.mismatch.pump_rated_flow_m3s or self.nominal.pump_rated_flow_m3s

    @property
    def overflow_level(self) -> float:
        return self.nominal.overflow_level_m

    # ----- true state -----
    def true_level(self) -> float:
        return self.volume_m3 / self.area

    def demand_at(self, t: float) -> float:
        q = self.case.demand_m3s
        for t_change, q_new in self.case.demand_steps:
            if t >= t_change:
                q = q_new
        return q

    def _pump_target(self) -> float:
        return self.pump_command * self.pump_capacity_factor * self.pump_rated

    def _leak_flow(self, volume: float) -> float:
        if self.leak_coeff <= 0.0:
            return 0.0
        head = volume / self.area - self.case.fault.leak_height_m
        return self.leak_coeff * math.sqrt(head) if head > 0 else 0.0

    # ----- integration -----
    def step(self) -> None:
        dt = self.nominal.sim_dt_s
        tau = self.nominal.pump_time_constant_s
        target = self._pump_target()
        q0 = self.pump_flow_m3s
        decay = math.exp(-dt / tau)
        q1 = target + (q0 - target) * decay
        q_in_avg = target + (q0 - target) * tau / dt * (1.0 - decay)  # exact mean of the exponential

        h_start = self.true_level()
        q_d = self.demand_at(self.t_s)
        demand_active = h_start > self.nominal.outlet_level_m
        q_d_served = q_d if demand_active else 0.0

        v0 = self.volume_m3

        def dvdt(v: float) -> float:
            return q_in_avg - q_d_served - self._leak_flow(v)

        k1 = dvdt(v0)
        k2 = dvdt(v0 + 0.5 * dt * k1)
        k3 = dvdt(v0 + 0.5 * dt * k2)
        k4 = dvdt(v0 + dt * k3)
        v1 = v0 + dt * (k1 + 2 * k2 + 2 * k3 + k4) / 6.0

        in_vol = q_in_avg * dt
        demand_vol = q_d_served * dt
        leak_vol = 0.0 if self.leak_coeff <= 0.0 else max(0.0, v0 + in_vol - demand_vol - v1)
        v1 = v0 + in_vol - demand_vol - leak_vol  # close the balance exactly

        if v1 < 0.0:  # cannot leak more water than the tank holds
            leak_vol = max(0.0, leak_vol + v1)
            v1 = v0 + in_vol - demand_vol - leak_vol
            if v1 < 0.0:  # demand drew the last water within this step
                demand_vol = max(0.0, demand_vol + v1)
                v1 = 0.0
        overflow_vol = 0.0
        v_max = self.area * self.overflow_level
        if v1 > v_max:
            overflow_vol = v1 - v_max
            v1 = v_max

        t = self.totals
        t.inflow += in_vol
        t.demand_out += demand_vol
        t.leak_out += leak_vol
        t.overflow_out += overflow_vol
        t.unmet_demand += q_d * dt - demand_vol

        self.volume_m3 = v1
        self.pump_flow_m3s = q1
        self.last_demand_flow_m3s = demand_vol / dt
        self.t_s = round(self.t_s + dt, 6)

        h_end = self.true_level()
        if self.stuck_at_m is None:
            tau_s = self.nominal.level_sensor_time_constant_s
            self.sensed_level_m = h_end + (self.sensed_level_m - h_end) * math.exp(-dt / tau_s)
        else:
            self.sensed_level_m = self.stuck_at_m

        if self._on_historian_tick():
            self._record_sample()

    def _on_historian_tick(self) -> bool:
        interval = self.nominal.historian_interval_s
        return abs((self.t_s - WINDOW_START_S) / interval - round((self.t_s - WINDOW_START_S) / interval)) < 1e-9

    def advance_to(self, t_end: float) -> None:
        while self.t_s < t_end - 1e-9:
            self.step()

    def set_pump_command(self, on: bool) -> None:
        self.pump_command = 1 if on else 0

    # ----- sensor models (noise drawn at read time, per channel) -----
    def lt101_reading(self) -> float:
        n = self.nominal
        sd = n.level_sensor_noise_sd_m * self.case.mismatch.level_noise_scale
        raw = self.sensed_level_m + self.level_bias_m + sd * self.noise.gauss("LT-101")
        raw = min(max(raw, 0.0), n.level_sensor_range_m)
        return quantize(raw, n.level_sensor_resolution_m)

    def ft102_reading(self) -> float:
        n = self.nominal
        raw = self.last_demand_flow_m3s + self.case.mismatch.demand_meter_bias_m3s
        raw += n.demand_meter_noise_sd_m3s * self.noise.gauss("FT-102")
        return quantize(max(raw, 0.0), n.demand_meter_resolution_m3s)

    def ft101_reading(self, mean_true_inflow_m3s: float) -> tuple[float, float]:
        """Averaged clamp-on reading and its stated 1-sd uncertainty."""
        n = self.nominal
        sd = n.inlet_meter_noise_rel * mean_true_inflow_m3s + n.inlet_meter_noise_abs_m3s
        raw = mean_true_inflow_m3s + sd * self.noise.gauss("FT-101")
        stated_sd = n.inlet_meter_noise_rel * max(raw, 0.0) + n.inlet_meter_noise_abs_m3s
        return quantize(max(raw, 0.0), n.inlet_meter_resolution_m3s), stated_sd

    def dip_reading(self) -> float:
        n = self.nominal
        raw = self.true_level() + n.dip_noise_sd_m * self.noise.gauss("DIP-101")
        return quantize(min(max(raw, 0.0), n.tank_height_m), n.dip_resolution_m)

    def _record_sample(self) -> None:
        lt = self.lt101_reading()  # draw order LT-101 then FT-102, as in every earlier version
        ft = self.ft102_reading()
        self.truth_log.append({
            "t_s": self.t_s,
            "true_level_m": round(self.true_level(), 6),
            "true_inflow_L_s": round(self.pump_flow_m3s * 1000.0, 5),
            "true_leak_L_s": round(self._leak_flow(self.volume_m3) * 1000.0, 5),
            "sensed_level_m": round(self.sensed_level_m, 6),
            "LT101_logged_m": lt,
            "overflow_total_m3": round(self.totals.overflow_out, 6),
        })
        self.historian.append(
            HistorianSample(
                t_s=self.t_s,
                lt101_m=lt,
                ft102_m3s=ft,
                pump_command=self.pump_command,
                pump_run_feedback=self.pump_command,  # motor contactor follows command
            )
        )

    # ----- simulated maintenance (only via an approved intervention) -----
    def apply_maintenance(self, action: str) -> None:
        if action == "repair_pump":
            self.pump_capacity_factor = 1.0
        elif action == "repair_tank_leak":
            self.leak_coeff = 0.0
        elif action == "replace_level_sensor":
            self.stuck_at_m = None
            self.level_bias_m = 0.0
            self.sensed_level_m = self.true_level()
        elif action == "no_action":
            pass
        else:
            raise ValueError(f"unknown maintenance action {action!r}")


def _quiet_spec() -> NominalSpec:
    from dataclasses import replace

    return replace(
        NOMINAL,
        level_sensor_noise_sd_m=0.0,
        level_sensor_resolution_m=0.0,
        demand_meter_noise_sd_m3s=0.0,
        demand_meter_resolution_m3s=0.0,
        inlet_meter_noise_rel=0.0,
        inlet_meter_noise_abs_m3s=0.0,
        inlet_meter_resolution_m3s=0.0,
        dip_noise_sd_m=0.0,
        dip_resolution_m=0.0,
    )


QUIET = _quiet_spec()  # same physics and timing as NOMINAL, every noise source and quantiser off


def noise_free_plant(case: CaseConfig) -> Plant:
    """A copy of the case with every noise source scaled to zero (analysis only)."""
    return Plant(case=case, seed=0, nominal=QUIET)
