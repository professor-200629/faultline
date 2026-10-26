"""Judge presets for the Blind Challenge (PRIVATE).

The judge picks a fault family, a severity and a site profile. The server
builds the case; the browser only ever learns an opaque run ID.
"""

from __future__ import annotations

from dataclasses import replace

from .case import CaseConfig, FaultConfig, SiteConditions
from .spec import NOMINAL
from .twins import AMBIGUOUS_SITE

QR = NOMINAL.pump_rated_flow_m3s
A = NOMINAL.tank_area_m2

SITE_PROFILES = {
    "standard": SiteConditions(note="Day shift: FT-101 clamp and dip tape on site; P-101 may be stopped briefly."),
    "no_inlet_meter": SiteConditions(inlet_meter_available=False,
                                     note="FT-101 clamp is out for calibration; dip tape on site; P-101 may be stopped."),
    "no_independent_level": SiteConditions(independent_level_available=False,
                                           note="Roof hatch locked out (no dip reading); FT-101 on site."),
    "night_shift": AMBIGUOUS_SITE,
}

SITUATION = "A warning is active on T-101. P-101 is in manual and commanded ON; the level controller is bypassed."

# family -> severity -> builder(site) -> CaseConfig
PRESETS = {
    "no_fault": {
        "high_demand": lambda site: CaseConfig(FaultConfig("no_fault"), initial_level_m=1.05, demand_m3s=1.35e-3,
                                               site=site),
    },
    "pump_delivery_reduced": {
        "mild": lambda site: CaseConfig(FaultConfig("pump_delivery_reduced", pump_capacity_factor=0.80),
                                        initial_level_m=1.60, demand_m3s=1.0e-3, site=site),
        "severe": lambda site: CaseConfig(FaultConfig("pump_delivery_reduced", pump_capacity_factor=0.45),
                                          initial_level_m=1.70, demand_m3s=0.9e-3, site=site),
        "failed": lambda site: CaseConfig(FaultConfig("pump_delivery_reduced", pump_capacity_factor=0.0),
                                          initial_level_m=1.90, demand_m3s=0.8e-3, site=site),
    },
    "tank_leak": {
        "small": lambda site: CaseConfig(FaultConfig("tank_leak", leak_coeff_m25_s=2.2e-4), initial_level_m=1.65,
                                         demand_m3s=1.0e-3, site=site),
        "large": lambda site: CaseConfig(FaultConfig("tank_leak", leak_coeff_m25_s=6.0e-4), initial_level_m=1.85,
                                         demand_m3s=0.9e-3, site=site),
    },
    "level_sensor_stuck": {
        "true_level_rising": lambda site: CaseConfig(FaultConfig("level_sensor_stuck", stuck_at_m=1.75),
                                                     initial_level_m=1.75 + (QR - 1.0e-3) / A * 600, demand_m3s=1.0e-3,
                                                     site=site),
        "true_level_falling": lambda site: CaseConfig(FaultConfig("level_sensor_stuck", stuck_at_m=1.40),
                                                      initial_level_m=1.40 - (1.4e-3 - QR) / A * 600,
                                                      demand_m3s=1.4e-3, site=site),
    },
}


def build_preset(family: str, severity: str, site_profile: str) -> CaseConfig:
    try:
        builder = PRESETS[family][severity]
        site = SITE_PROFILES[site_profile]
    except KeyError:
        raise ValueError("unknown preset") from None
    return builder(site)


def preset_menu() -> dict:
    """What the judge form may offer. Safe to send to the judge's browser."""
    return {
        "families": {f: list(sev) for f, sev in PRESETS.items()},
        "site_profiles": {k: v.public_dict() for k, v in SITE_PROFILES.items()},
    }
