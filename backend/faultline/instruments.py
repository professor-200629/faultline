"""The only door between the hidden plant and agent-facing code.

`InstrumentPanel` owns a private `Plant` and exposes measurement and bounded
intervention methods that return PUBLIC observation dictionaries built from
explicit whitelists. Site constraints (availability, permitted actions, time
budget) are enforced here in backend code, independent of the agent prompt.
"""

from __future__ import annotations

from dataclasses import dataclass

from .sim.case import CaseConfig, SiteConditions
from .sim.plant import WINDOW_START_S, HistorianSample, Plant
from .sim.spec import NOMINAL, NominalSpec

PUMP_TEST_LOW_TRIP_M = 0.50  # interlock acts on the LT-101 *reading*, like a real trip would
FT101_FIT_S = 30.0  # technician fits the clamp and waits for a steady reading (> 5 pump time constants)
GRID_S = NOMINAL.historian_interval_s  # every action starts and ends on a historian tick


class InstrumentError(Exception):
    """A request the plant or site rules refuse. Message is safe to show the agent."""


def public_sample(s: HistorianSample) -> dict:
    return {
        "t_s": s.t_s,
        "LT101_m": s.lt101_m,
        "FT102_L_s": round(s.ft102_m3s * 1000.0, 4),
        "P101_command": s.pump_command,
        "P101_run_feedback": s.pump_run_feedback,
    }


@dataclass
class TimeBudget:
    limit_s: float
    used_s: float = 0.0

    @property
    def remaining_s(self) -> float:
        return max(0.0, self.limit_s - self.used_s)


class InstrumentPanel:
    def __init__(self, case: CaseConfig, seed: int, nominal: NominalSpec = NOMINAL) -> None:
        self.__plant = Plant(case=case, seed=seed, nominal=nominal)
        self.__plant.advance_to(0.0)  # pre-run the alarm window: t = -900 s .. 0 s
        self.site: SiteConditions = case.site
        self.time = TimeBudget(limit_s=case.site.max_extra_sim_s)

    def __repr__(self) -> str:
        return "InstrumentPanel(<redacted>)"

    # ---- read-only public views ----
    @property
    def now_s(self) -> float:
        return self.__plant.t_s

    def historian(self, t_from: float = WINDOW_START_S, t_to: float | None = None) -> list[dict]:
        t_to = self.now_s if t_to is None else t_to
        return [public_sample(s) for s in self.__plant.historian if t_from - 1e-9 <= s.t_s <= t_to + 1e-9]

    def pump_command(self) -> int:
        return self.__plant.pump_command

    # ---- time ----
    def _check(self, duration_s: float) -> None:
        if duration_s <= 0:
            raise InstrumentError("duration must be positive")
        if duration_s > self.time.remaining_s + 1e-9:
            raise InstrumentError(
                f"operator time allowance exceeded: {duration_s:.0f} s requested, "
                f"{self.time.remaining_s:.0f} s remaining"
            )

    @staticmethod
    def _on_grid(duration_s: float, what: str) -> None:
        if abs(duration_s / GRID_S - round(duration_s / GRID_S)) > 1e-9:
            raise InstrumentError(f"{what} must be a multiple of {GRID_S:.0f} s (the historian interval)")

    def _spend(self, duration_s: float) -> None:
        self._check(duration_s)
        self.time.used_s += duration_s

    def advance(self, duration_s: float) -> dict:
        self._on_grid(duration_s, "waiting time")
        t0 = self.now_s
        self._spend(duration_s)
        self.__plant.advance_to(t0 + duration_s)
        return {"t_start_s": t0, "t_end_s": self.now_s, "samples": self.historian(t0 + 1e-6)}

    # ---- measurements ----
    def measure_inlet_flow(self, duration_s: float) -> dict:
        if not self.site.inlet_meter_available:
            raise InstrumentError("FT-101 portable inlet flow meter is unavailable at this site")
        if not 30 <= duration_s <= 300:
            raise InstrumentError("FT-101 averaging time must be between 30 and 300 s")
        self._on_grid(duration_s, "FT-101 averaging time")
        p = self.__plant
        t_fit = p.t_s
        self._spend(FT101_FIT_S + duration_s)
        p.advance_to(t_fit + FT101_FIT_S)  # fitting + settling: excludes pump spin-up after a stop test
        t0 = p.t_s
        v_in0 = p.totals.inflow
        p.advance_to(t0 + duration_s)
        mean_true = (p.totals.inflow - v_in0) / (p.t_s - t0)
        reading, sd = p.ft101_reading(mean_true)
        return {
            "instrument": "FT-101",
            "t_fit_start_s": t_fit,
            "fit_and_settle_s": FT101_FIT_S,
            "t_start_s": t0,
            "t_end_s": p.t_s,
            "mean_inlet_flow_L_s": round(reading * 1000.0, 4),
            "stated_uncertainty_sd_L_s": round(sd * 1000.0, 4),
            "P101_command_during": p.pump_command,
        }

    def independent_level(self) -> dict:
        if not self.site.independent_level_available:
            raise InstrumentError("DIP-101 independent level reading is unavailable at this site")
        p = self.__plant
        t0 = p.t_s
        self._spend(p.nominal.dip_duration_s)
        p.advance_to(t0 + p.nominal.dip_duration_s)
        dip = p.dip_reading()
        # The LT-101 sample logged at the same simulation step, for a like-for-like comparison. Actions stay on
        # the historian grid, so it exists; the fallback (latest earlier sample) is reported with its own time.
        lt = self.historian(WINDOW_START_S, p.t_s)[-1]
        return {
            "instrument": "DIP-101",
            "t_start_s": t0,
            "t_s": p.t_s,
            "dip_level_m": dip,
            "stated_uncertainty_sd_m": NOMINAL.dip_noise_sd_m,  # datasheet value, even in analysis runs
            "LT101_same_step_m": lt["LT101_m"],
            "LT101_sample_t_s": lt["t_s"],
        }

    def pump_stop_test(self, hold_s: float) -> dict:
        if not self.site.pump_stop_test_permitted:
            raise InstrumentError("stopping P-101 is not permitted at this site")
        if not 60 <= hold_s <= self.site.max_pump_stop_s:
            raise InstrumentError(f"pump stop hold must be between 60 and {self.site.max_pump_stop_s:.0f} s")
        self._on_grid(hold_s, "pump stop hold")
        p = self.__plant
        if p.pump_command != 1:
            raise InstrumentError("P-101 is not running, so a stop test is not meaningful")
        t0 = p.t_s
        self._check(hold_s)
        p.set_pump_command(False)
        tripped = False
        end = t0 + hold_s
        while p.t_s < end - 1e-9:
            p.step()
            last = p.historian[-1]
            if last.t_s == p.t_s and last.lt101_m < PUMP_TEST_LOW_TRIP_M:
                tripped = True
                break
        p.set_pump_command(True)
        self.time.used_s += p.t_s - t0
        return {
            "action": "P-101 stop test",
            "t_start_s": t0,
            "t_end_s": p.t_s,
            "requested_hold_s": hold_s,
            "aborted_by_low_level_interlock": tripped,
            "samples": self.historian(t0, p.t_s),
            "note": "P-101 command restored to ON at t_end_s",
        }

    def post_maintenance_observation(self, duration_s: float = 300.0) -> dict:
        """After an approved simulated maintenance: log the plant for a while and summarise PUBLIC readings only.

        Not an agent tool and not charged to the investigation's allowance (the investigation is over).
        """
        from .analysis import evaluate_alarms, window_summary

        p = self.__plant
        t0 = p.t_s
        p.set_pump_command(True)
        p.advance_to(t0 + duration_s)
        samples = self.historian(t0 + 1e-6, p.t_s)
        summ = window_summary(samples)
        return {"t_start_s": t0, "t_end_s": p.t_s, "summary": summ, "alarms_on_this_window": evaluate_alarms(samples),
                "note": "Logged LT-101 / FT-102 readings after maintenance. Public measurements, not ground truth."}

    # ---- judge / evaluator only (never registered as an agent tool) ----
    def _private_plant(self) -> Plant:
        return self.__plant
