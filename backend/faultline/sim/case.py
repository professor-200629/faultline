"""Case configuration: the private truth of one simulated plant.

`SiteConditions` is PUBLIC (what is installed, what the operator permits).
`FaultConfig`, `MismatchConfig` and `CaseConfig` are PRIVATE: they hold the
hidden fault, the true coefficients and the initial true state. Only the
judge vault, the simulator and the evaluator may handle them.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Optional

FAMILIES = ("no_fault", "pump_delivery_reduced", "tank_leak", "level_sensor_stuck")


@dataclass(frozen=True)
class SiteConditions:
    """Public operating constraints for one investigation."""

    inlet_meter_available: bool = True  # can a technician fit FT-101?
    independent_level_available: bool = True  # can someone take a DIP-101 reading?
    pump_stop_test_permitted: bool = True  # may P-101 be stopped briefly?
    max_pump_stop_s: float = 300.0
    max_extra_sim_s: float = 1800.0  # additional logical time the operator allows
    note: str = ""

    def public_dict(self) -> dict:
        return {
            "inlet_flow_meter_FT101": "available" if self.inlet_meter_available else "unavailable",
            "independent_level_DIP101": "available" if self.independent_level_available else "unavailable",
            "pump_stop_test": (
                f"permitted, at most {self.max_pump_stop_s:.0f} s per test"
                if self.pump_stop_test_permitted
                else "not permitted"
            ),
            "max_additional_time_s": self.max_extra_sim_s,
            "note": self.note,
        }


@dataclass(frozen=True)
class FaultConfig:
    family: str = "no_fault"
    pump_capacity_factor: float = 1.0  # delivered / rated, 0 = no delivery with motor running
    leak_coeff_m25_s: float = 0.0  # Q_leak = C * sqrt(h - h_leak)
    leak_height_m: float = 0.0
    stuck_at_m: Optional[float] = None  # LT-101 sensing element frozen at this level

    def __post_init__(self) -> None:
        if self.family not in FAMILIES:
            raise ValueError(f"unknown fault family {self.family!r}")
        if not 0.0 <= self.pump_capacity_factor <= 1.0:
            raise ValueError("pump_capacity_factor must be in [0, 1]")
        if self.leak_coeff_m25_s < 0:
            raise ValueError("leak coefficient must be >= 0")


@dataclass(frozen=True)
class MismatchConfig:
    """Ways the real plant departs from the public nominal model.

    Used only for labelled model-mismatch evaluation cases.
    """

    tank_area_m2: Optional[float] = None
    pump_rated_flow_m3s: Optional[float] = None
    level_noise_scale: float = 1.0
    level_bias_m: float = 0.0
    demand_meter_bias_m3s: float = 0.0

    @property
    def is_nominal(self) -> bool:
        return self == MismatchConfig()


@dataclass(frozen=True)
class CaseConfig:
    fault: FaultConfig
    initial_level_m: float  # TRUE level at the start of the alarm window
    demand_m3s: float
    site: SiteConditions = field(default_factory=SiteConditions)
    mismatch: MismatchConfig = field(default_factory=MismatchConfig)
    pump_command_on: bool = True
    # Optional demand changes: ((t_s, demand_m3s), ...) taking effect at t_s.
    demand_steps: tuple = ()

    def to_private_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_private_dict(d: dict) -> "CaseConfig":
        return CaseConfig(
            fault=FaultConfig(**d["fault"]),
            initial_level_m=d["initial_level_m"],
            demand_m3s=d["demand_m3s"],
            site=SiteConditions(**d["site"]),
            mismatch=MismatchConfig(**d.get("mismatch", {})),
            pump_command_on=d.get("pump_command_on", True),
            demand_steps=tuple(tuple(x) for x in d.get("demand_steps", ())),
        )
