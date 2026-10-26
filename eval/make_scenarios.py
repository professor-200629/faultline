"""Build the DEV and HELD-OUT scenario sets and their oracle labels.

Run once:  .venv\\Scripts\\python eval\\make_scenarios.py
The held-out file is frozen after creation: its SHA-256 is recorded in
EVALUATION.md before any live model run. Do not edit it after seeing results;
if a change is ever needed, create heldout-v2 and disclose why.

DEV scenarios (twin pairs and Blind Challenge presets) were used while writing
the prompt, tools and the reference procedure. HELD-OUT scenarios use different
parameter values, seeds, site combinations, and include labelled model-mismatch
cases. Identifiability labels come from judge/identifiability.py.
"""

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from faultline.judge.identifiability import ORACLE_VERSION, identifiability  # noqa: E402
from faultline.sim.case import CaseConfig, FaultConfig, MismatchConfig  # noqa: E402
from faultline.sim.presets import PRESETS, SITE_PROFILES  # noqa: E402
from faultline.sim.spec import NOMINAL  # noqa: E402
from faultline.sim.twins import AMBIGUOUS_SITE, falling_level_pair, flat_reading_pair  # noqa: E402

QR, A = NOMINAL.pump_rated_flow_m3s, NOMINAL.tank_area_m2
S = SITE_PROFILES


def stuck(at, demand, lead_s, site, **mm):
    rate = (QR - demand) / A
    return CaseConfig(FaultConfig("level_sensor_stuck", stuck_at_m=at), initial_level_m=at + rate * lead_s,
                      demand_m3s=demand, site=site, mismatch=MismatchConfig(**mm))


def pump(k, h0, demand, site, **mm):
    return CaseConfig(FaultConfig("pump_delivery_reduced", pump_capacity_factor=k), initial_level_m=h0,
                      demand_m3s=demand, site=site, mismatch=MismatchConfig(**mm))


def leak(c, h0, demand, site, **mm):
    return CaseConfig(FaultConfig("tank_leak", leak_coeff_m25_s=c), initial_level_m=h0, demand_m3s=demand,
                      site=site, mismatch=MismatchConfig(**mm))


def healthy(h0, demand, site, **mm):
    return CaseConfig(FaultConfig("no_fault"), initial_level_m=h0, demand_m3s=demand, site=site,
                      mismatch=MismatchConfig(**mm))


HELDOUT = [
    # id, description, case, seed, tags
    ("H01", "healthy, demand above pump rating, low level", healthy(1.04, 1.40e-3, S["standard"]), 9101, ["healthy"]),
    ("H02", "healthy, high demand, no FT-101", healthy(1.02, 1.30e-3, S["no_inlet_meter"]), 9102, ["healthy", "missing_measurement"]),
    ("H03", "healthy, high demand, night shift", healthy(0.99, 1.45e-3, S["night_shift"]), 9103, ["healthy", "missing_measurement"]),
    ("H04", "pump 70%, standard", pump(0.70, 1.72, 0.95e-3, S["standard"]), 9104, ["pump"]),
    ("H05", "pump 55%, no FT-101", pump(0.55, 1.95, 1.05e-3, S["no_inlet_meter"]), 9105, ["pump", "missing_measurement"]),
    ("H06", "pump failed (0%), no dip", pump(0.0, 2.10, 0.70e-3, S["no_independent_level"]), 9106, ["pump", "missing_measurement"]),
    ("H07", "pump 80% balancing demand: flat reading", pump(0.80, 1.62, 0.96e-3, S["standard"]), 9107, ["pump", "flat_reading"]),
    ("H08", "pump 60%, night shift", pump(0.60, 1.50, 1.0e-3, S["night_shift"]), 9108, ["pump", "ambiguous"]),
    ("H09", "pump 75%, LT-101 twice as noisy as datasheet", pump(0.75, 1.80, 1.0e-3, S["standard"], level_noise_scale=2.0),
     9109, ["pump", "noisy", "model_mismatch"]),
    ("H10", "leak medium, standard", leak(3.0e-4, 1.80, 1.0e-3, S["standard"]), 9110, ["leak"]),
    ("H11", "leak large, no FT-101", leak(5.0e-4, 2.20, 0.85e-3, S["no_inlet_meter"]), 9111, ["leak", "missing_measurement"]),
    ("H12", "leak small, standard", leak(1.6e-4, 1.40, 1.10e-3, S["standard"]), 9112, ["leak"]),
    ("H13", "leak medium, night shift", leak(4.0e-4, 1.60, 1.0e-3, S["night_shift"]), 9113, ["leak", "ambiguous"]),
    ("H14", "leak, true tank area 2.2 m2 (datasheet 2.0)", leak(3.5e-4, 1.75, 1.0e-3, S["standard"], tank_area_m2=2.2),
     9114, ["leak", "model_mismatch"]),
    ("H15", "leak medium, no dip", leak(2.5e-4, 1.90, 0.90e-3, S["no_independent_level"]), 9115, ["leak", "missing_measurement"]),
    ("H16", "stuck sensor, true level rising", stuck(1.55, 0.95e-3, 300, S["standard"]), 9116, ["stuck", "flat_reading"]),
    ("H17", "stuck sensor, true level falling", stuck(1.30, 1.35e-3, 600, S["standard"]), 9117, ["stuck", "flat_reading"]),
    ("H18", "stuck sensor rising, no FT-101", stuck(2.05, 0.80e-3, 120, S["no_inlet_meter"]), 9118, ["stuck", "missing_measurement"]),
    ("H19", "stuck sensor rising, night shift", stuck(1.70, 1.0e-3, 600, S["night_shift"]), 9119, ["stuck", "ambiguous"]),
    ("H20", "stuck sensor rising, no dip", stuck(1.45, 0.90e-3, 400, S["no_independent_level"]), 9120, ["stuck", "missing_measurement"]),
    ("H21", "stuck sensor falling, no FT-101, noisier LT-101", stuck(1.60, 1.30e-3, 300, S["no_inlet_meter"], level_noise_scale=1.5),
     9121, ["stuck", "noisy", "model_mismatch"]),
    ("H22", "pump 65% with LT-101 calibration offset +40 mm", pump(0.65, 1.70, 1.0e-3, S["standard"], level_bias_m=0.040),
     9122, ["pump", "model_mismatch"]),
    ("H23", "leak with FT-102 reading 0.05 L/s low", leak(3.2e-4, 1.85, 0.95e-3, S["no_inlet_meter"], demand_meter_bias_m3s=-0.05e-3),
     9123, ["leak", "model_mismatch", "missing_measurement"]),
    ("H24", "pump 70%, true tank area 1.8 m2 (datasheet 2.0)", pump(0.70, 1.65, 1.0e-3, S["no_inlet_meter"], tank_area_m2=1.8),
     9124, ["pump", "model_mismatch", "missing_measurement"]),
]


def dev_set():
    out = []
    for site_name, site in (("standard", None), ("night_shift", AMBIGUOUS_SITE)):
        for make in (falling_level_pair, flat_reading_pair):
            p = make(site)
            for i, m in enumerate(p.members):
                out.append((f"D-{p.pair_id}-{i}-{site_name}", p.member_labels[i], m, 100 + len(out), ["twin", site_name]))
    for fam, sevs in PRESETS.items():
        for sev, build in sevs.items():
            out.append((f"D-preset-{fam}-{sev}", f"{fam} / {sev}", build(S["standard"]), 200 + len(out), ["preset"]))
    return out


def materialise(rows):
    items = []
    for sid, desc, case, seed, tags in rows:
        ident = identifiability(case)
        items.append({"id": sid, "description": desc, "seed": seed, "tags": tags, "truth_family": case.fault.family,
                      "identifiable": ident["identifiable"],
                      "viable_alternatives": [a["family"] for a in ident["alternatives"] if a["viable"]],
                      "case": case.to_private_dict()})
    return items


def write(name, rows):
    items = materialise(rows)
    doc = {"set": name, "oracle_version": ORACLE_VERSION, "count": len(items), "scenarios": items}
    path = ROOT / "eval" / "scenarios" / f"{name}.json"
    text = json.dumps(doc, indent=1)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:  # LF on every OS so the hash is stable
        fh.write(text)
    digest = hashlib.sha256(text.encode()).hexdigest()
    print(f"{path.name}: {len(items)} scenarios, sha256 {digest}")
    for it in items:
        print(f"  {it['id']:<34} {it['truth_family']:<22} identifiable={it['identifiable']!s:<5} "
              f"alts={','.join(it['viable_alternatives']) or '-'} tags={','.join(it['tags'])}")
    return digest


# ---------------------------------------------------------------- held-out v2
# Created after an adversarial review found that the v1 non-identifiable cases (and several others) were
# near-copies of dev twins on the same site object. v2 uses held-out-only site profiles and the stated
# minimum-distance rule below. Created before any model (Nemotron) evaluation; only arm A had run on v1.
from faultline.sim.case import SiteConditions  # noqa: E402

HS = {
    "standard2": SiteConditions(max_pump_stop_s=240.0, max_extra_sim_s=1500.0,
                                note="Day shift at the river intake: FT-101 clamp and dip tape on site; P-101 may be "
                                     "stopped for up to 4 minutes."),
    "remote": SiteConditions(inlet_meter_available=False, max_pump_stop_s=240.0, max_extra_sim_s=1500.0,
                             note="Remote booster station: no FT-101 clamp on site; dip tape available; P-101 may be "
                                  "stopped for up to 4 minutes."),
    "hatch": SiteConditions(independent_level_available=False, max_pump_stop_s=180.0, max_extra_sim_s=1200.0,
                            note="Roof hatch under repair (no dip reading); FT-101 on site; P-101 may be stopped for "
                                 "up to 3 minutes."),
    "storm": SiteConditions(inlet_meter_available=False, independent_level_available=False,
                            pump_stop_test_permitted=False, max_extra_sim_s=480.0,
                            note="Storm call-out: no FT-101, roof access closed, P-101 must keep running for fire "
                                 "water. At most 8 more minutes before a decision."),
}

HELDOUT_V2 = [
    ("V01", "healthy, demand 1.50 L/s above rating, low level", healthy(1.12, 1.50e-3, HS["standard2"]), 7201, ["healthy"]),
    ("V02", "healthy, demand 1.47 L/s, storm site", healthy(0.98, 1.47e-3, HS["storm"]), 7202, ["healthy", "missing_measurement"]),
    ("V03", "healthy, normal demand, operator check (no alarm)", healthy(1.30, 0.90e-3, HS["remote"]), 7203, ["healthy"]),
    ("V04", "pump 72%", pump(0.72, 1.78, 0.92e-3, HS["standard2"]), 7204, ["pump"]),
    ("V05", "pump 52%, no FT-101", pump(0.52, 2.05, 1.08e-3, HS["remote"]), 7205, ["pump", "missing_measurement"]),
    ("V06", "pump failed (0%), no dip", pump(0.0, 2.20, 0.62e-3, HS["hatch"]), 7206, ["pump", "missing_measurement"]),
    ("V07", "pump 78% balancing demand: flat reading", pump(0.78, 1.30, 0.936e-3, HS["standard2"]), 7207, ["pump", "flat_reading"]),
    ("V08", "pump 66%, storm site", pump(0.66, 1.85, 0.92e-3, HS["storm"]), 7208, ["pump", "ambiguous", "missing_measurement"]),
    ("V09", "pump 74%, LT-101 twice as noisy as datasheet", pump(0.74, 1.66, 1.12e-3, HS["standard2"], level_noise_scale=2.0),
     7209, ["pump", "noisy", "model_mismatch"]),
    ("V10", "pump 68%, LT-101 calibration offset +35 mm", pump(0.68, 1.58, 0.88e-3, HS["hatch"], level_bias_m=0.035),
     7210, ["pump", "model_mismatch", "missing_measurement"]),
    ("V11", "pump 71%, true tank area 1.85 m2 (datasheet 2.0)", pump(0.71, 1.92, 0.95e-3, HS["remote"], tank_area_m2=1.85),
     7211, ["pump", "model_mismatch", "missing_measurement"]),
    ("V12", "leak medium", leak(2.8e-4, 1.95, 1.05e-3, HS["standard2"]), 7212, ["leak"]),
    ("V13", "leak large, no FT-101", leak(5.5e-4, 2.25, 0.80e-3, HS["remote"]), 7213, ["leak", "missing_measurement"]),
    ("V14", "leak small", leak(1.4e-4, 1.30, 1.06e-3, HS["standard2"]), 7214, ["leak"]),
    ("V15", "leak medium, storm site", leak(3.3e-4, 1.42, 0.86e-3, HS["storm"]), 7215, ["leak", "ambiguous", "missing_measurement"]),
    ("V16", "leak, true tank area 2.15 m2 (datasheet 2.0)", leak(3.8e-4, 1.85, 0.96e-3, HS["standard2"], tank_area_m2=2.15),
     7216, ["leak", "model_mismatch"]),
    ("V17", "leak medium, no dip", leak(2.3e-4, 2.10, 0.84e-3, HS["hatch"]), 7217, ["leak", "missing_measurement"]),
    ("V18", "leak with FT-102 reading 0.04 L/s low, no FT-101", leak(3.0e-4, 1.80, 1.02e-3, HS["remote"],
                                                                     demand_meter_bias_m3s=-0.04e-3),
     7218, ["leak", "model_mismatch", "missing_measurement"]),
    ("V19", "stuck sensor, true level rising", stuck(1.62, 0.90e-3, 450, HS["standard2"]), 7219, ["stuck", "flat_reading"]),
    ("V20", "stuck sensor, true level falling", stuck(1.22, 1.32e-3, 500, HS["standard2"]), 7220, ["stuck", "flat_reading"]),
    ("V21", "stuck sensor rising, no FT-101", stuck(2.12, 0.78e-3, 150, HS["remote"]), 7221, ["stuck", "missing_measurement"]),
    ("V22", "stuck sensor rising, storm site", stuck(1.58, 0.86e-3, 300, HS["storm"]), 7222,
     ["stuck", "ambiguous", "missing_measurement"]),
    ("V23", "stuck sensor rising, no dip", stuck(1.38, 1.04e-3, 700, HS["hatch"]), 7223, ["stuck", "missing_measurement"]),
    ("V24", "stuck sensor falling, no FT-101, noisier LT-101", stuck(1.66, 1.42e-3, 250, HS["remote"], level_noise_scale=1.5),
     7224, ["stuck", "noisy", "model_mismatch", "missing_measurement"]),
    ("V25", "pump balancing demand at the storm site: flat reading", pump(0.90, 1.45, 1.08e-3, HS["storm"]), 7225,
     ["pump", "flat_reading", "ambiguous", "missing_measurement"]),
    ("V26", "leak balancing pump surplus: flat reading", leak(1.6e-4, 1.56, 1.0e-3, HS["standard2"]), 7226,
     ["leak", "flat_reading"]),
]

DIST_MARGIN = {"deviation_mm_min": 1.5, "demand_L_s": 0.10, "level_m": 0.15}
DISTANCE_RULE = ("A held-out scenario is too close to a dev scenario when both have the same fault family AND the "
                 "same instrument availability (FT-101, DIP-101, stop test) AND every one of these differs by less "
                 "than its margin: alarm-window LT-101 deviation from the nominal balance (1.5 mm/min), FT-102 "
                 "demand (0.10 L/s), first logged LT-101 level (0.15 m).")


def _features(case):
    from faultline.analysis import window_summary
    from faultline.judge.identifiability import window

    w = window(case)
    s = window_summary(w)
    site = case.site
    return {"family": case.fault.family,
            "avail": (site.inlet_meter_available, site.independent_level_available, site.pump_stop_test_permitted),
            "deviation_mm_min": s["rate_minus_nominal_mm_per_min"], "demand_L_s": s["FT102_mean_L_s"],
            "level_m": w[0]["LT101_m"]}


def distance_violations(heldout_rows, dev_rows):
    dev = [(sid, _features(c)) for sid, _, c, _, _ in dev_rows]
    bad = []
    for hid, _, case, _, _ in heldout_rows:
        f = _features(case)
        for did, g in dev:
            if f["family"] != g["family"] or f["avail"] != g["avail"]:
                continue
            if all(abs(f[k] - g[k]) < m for k, m in DIST_MARGIN.items()):
                bad.append((hid, did, {k: round(f[k] - g[k], 3) for k in DIST_MARGIN}))
    return bad


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "both"
    if target in ("dev", "both"):
        write("dev-v2", dev_set())
    if target in ("heldout", "both"):
        bad = distance_violations(HELDOUT_V2, dev_set())
        if bad:
            for b in bad:
                print("TOO CLOSE TO DEV:", b)
            raise SystemExit("held-out v2 violates the minimum-distance rule; nothing written")
        print("distance rule satisfied:", DISTANCE_RULE)
        if (ROOT / "eval" / "scenarios" / "heldout-v2.json").exists() and "--force" not in sys.argv:
            print("heldout-v2.json already exists and is frozen; refusing to overwrite")
        else:
            write("heldout-v2", HELDOUT_V2)
