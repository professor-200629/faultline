"""Public nominal specification of the T-101 tank / P-101 pump skid.

Everything here is PUBLIC: it is what a technician would read on the
datasheet and P&ID, and it is exactly what the agent is given. Hidden truth
(fault parameters, true coefficients, noise seeds) lives in `sim.case` and is
never imported by agent-facing code.

Units are SI (m, m^2, m^3/s, s) unless a field name says otherwise.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class NominalSpec:
    # Tank T-101: vertical cylinder with a flat bottom.
    tank_area_m2: float = 2.0
    tank_height_m: float = 2.5
    overflow_level_m: float = 2.40  # weir crest; water above it leaves via the overflow drain
    outlet_level_m: float = 0.05  # demand nozzle; demand cannot be served below this level

    # Pump P-101 delivering from a large supply sump into T-101.
    pump_rated_flow_m3s: float = 1.2e-3  # 1.20 L/s at rated speed, assumed independent of tank level
    pump_time_constant_s: float = 5.0  # first-order spin-up / run-down of delivered flow

    # LT-101 level transmitter (installed, logged by the historian).
    level_sensor_range_m: float = 2.5
    level_sensor_noise_sd_m: float = 0.003
    level_sensor_resolution_m: float = 0.001
    level_sensor_time_constant_s: float = 2.0

    # FT-102 demand (outlet) flow meter (installed, logged by the historian).
    demand_meter_noise_sd_m3s: float = 1.0e-5
    demand_meter_resolution_m3s: float = 1.0e-5

    # FT-101 portable clamp-on inlet flow meter (only if a technician can fit it).
    inlet_meter_noise_rel: float = 0.02
    inlet_meter_noise_abs_m3s: float = 1.0e-5
    inlet_meter_resolution_m3s: float = 1.0e-5

    # Independent manual level reading (dip tape through the roof hatch).
    dip_noise_sd_m: float = 0.005
    dip_resolution_m: float = 0.005
    dip_duration_s: float = 120.0

    # Historian, alarms, integration.
    historian_interval_s: float = 10.0
    sim_dt_s: float = 1.0
    alarm_window_s: float = 900.0
    low_level_alarm_m: float = 1.0
    balance_alarm_mm_per_min: float = 2.5

    def public_dict(self) -> dict:
        """Datasheet values in display units for the agent and the UI."""
        return {
            "tank": {
                "tag": "T-101",
                "shape": "vertical cylinder, flat bottom",
                "cross_section_m2": self.tank_area_m2,
                "height_m": self.tank_height_m,
                "overflow_level_m": self.overflow_level_m,
                "demand_outlet_level_m": self.outlet_level_m,
            },
            "pump": {
                "tag": "P-101",
                "rated_delivery_L_s": round(self.pump_rated_flow_m3s * 1000, 4),
                "delivery_time_constant_s": self.pump_time_constant_s,
                "note": "Delivery assumed independent of tank level over the operating range. "
                "The run signal reports the motor contactor, not delivered flow.",
            },
            "instruments": {
                "LT-101": {
                    "kind": "level transmitter (logged)",
                    "noise_sd_mm": self.level_sensor_noise_sd_m * 1000,
                    "resolution_mm": self.level_sensor_resolution_m * 1000,
                    "range_m": [0.0, self.level_sensor_range_m],
                },
                "FT-102": {
                    "kind": "demand outlet flow meter (logged)",
                    "noise_sd_L_s": self.demand_meter_noise_sd_m3s * 1000,
                    "resolution_L_s": self.demand_meter_resolution_m3s * 1000,
                },
                "FT-101": {
                    "kind": "portable clamp-on inlet flow meter (technician fitted, averaged reading; "
                    "fitting and settling takes 30 s before averaging starts)",
                    "uncertainty": f"{self.inlet_meter_noise_rel * 100:.0f}% of reading + "
                    f"{self.inlet_meter_noise_abs_m3s * 1000:.2f} L/s (1 sd)",
                },
                "DIP-101": {
                    "kind": "independent manual dip-tape level reading",
                    "noise_sd_mm": self.dip_noise_sd_m * 1000,
                    "resolution_mm": self.dip_resolution_m * 1000,
                    "duration_s": self.dip_duration_s,
                },
            },
            "historian_interval_s": self.historian_interval_s,
            "alarms": {
                "LAL-101": f"LT-101 reading below {self.low_level_alarm_m:.2f} m",
                "BAL-101": "LT-101 rate differs from the nominal mass balance "
                f"(P-101 rated delivery x command - FT-102) by more than "
                f"{self.balance_alarm_mm_per_min} mm/min over the last "
                f"{self.alarm_window_s / 60:.0f} min",
            },
        }

    def as_dict(self) -> dict:
        return asdict(self)


NOMINAL = NominalSpec()
