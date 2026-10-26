"""Evidence export: JSON bundle and Markdown report.

Before a judge reveal the bundle contains only public data (the same objects
the investigation screen shows). After a reveal it adds a clearly separated
`judge_reveal` section.
"""

from __future__ import annotations

import hashlib
import json
import time

LIMITATIONS = [
    "Simulation prototype: one documented tank-and-pump topology with a single-fault catalogue. "
    "It is not certified control software and not field-validated maintenance advice.",
    "Diagnoses are relative to four hypotheses (no fault, reduced pump delivery, tank leak, stuck level sensor); "
    "combined or unmodelled faults may be misdiagnosed or reported inconclusive.",
    "Confidence labels are the agent's qualitative judgement, not calibrated probabilities.",
    "Identifiability labels come from a noise-free 4-sigma separability rule applied to single tests, "
    "not a formal statistical guarantee.",
    "Usefulness to maintenance trainees and technicians has not been validated with real users.",
]
FORMAT = "faultline-evidence-v1"


def _digest(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True).encode()).hexdigest()


def export_bundle(manager, run_id: str) -> dict:
    run = manager._require(run_id)
    store = manager.store
    rt = manager._runtimes.get(run_id)
    live = rt is not None and run["status"] == "investigating"
    evidence = [e.public() for e in rt.executor.evidence] if live else run["evidence"]
    events = store.events(run_id)
    calls = store.model_calls(run_id)
    telemetry = manager.public_telemetry(run_id)
    bundle = {
        "format": FORMAT,
        "generated_at": time.time(),
        "run": {k: run[k] for k in ("id", "kind", "mode", "status", "status_reason", "created_at", "terminal_at",
                                     "provider", "budgets", "counters", "versions")},
        "mode_label": {"live": "LIVE: NVIDIA Nemotron on Nebius Token Factory",
                       "reference": "REFERENCE PROCEDURE: deterministic, not AI",
                       "unstarted": "NOT STARTED",
                       "replay": "REPLAY of a recorded run"}.get(run["mode"], run["mode"].upper()),
        "context": run["public"],
        "evidence": evidence,
        "telemetry": telemetry,
        "predictions": run["predictions"] if not live else rt.executor.predictions,
        "hypothesis_board": rt.executor.board if live else run["board"],
        "diagnosis": run["diagnosis"],
        "remedy": run["remedy"],
        "timeline": [{"seq": e["seq"], "at": e["at"], "type": e["type"], "payload": e["payload"]} for e in events],
        "model_calls": [{k: c.get(k) for k in ("n", "ok", "model", "latency_ms", "usage", "finish_reason", "error",
                                                "tool_calls", "content")} for c in calls],
        "limitations": LIMITATIONS,
    }
    bundle["integrity"] = {"evidence_sha256": _digest(bundle["evidence"]), "timeline_sha256": _digest(bundle["timeline"])}
    if run["revealed"]:
        bundle["judge_reveal"] = {**manager.revealed_payload(run_id),
                                  "section": "JUDGE-ONLY GROUND TRUTH (revealed after the investigation was terminal)"}
    return bundle


def _fmt_hyp(h: dict) -> str:
    sup = ", ".join(h.get("supporting_evidence") or []) or "-"
    con = ", ".join(h.get("contradicting_evidence") or []) or "-"
    note = f" {h['note']}" if h.get("note") else ""
    return f"| {h['id']} | {h['status']} | {sup} | {con} |{note} |"


def markdown_report(b: dict) -> str:
    r = b["run"]
    c = r.get("counters") or {}
    lines = [
        f"# FAULTLINE investigation report - run {r['id']}",
        "",
        f"**Mode:** {b['mode_label']}  ",
        f"**Status:** {r['status']} ({r.get('status_reason') or ''})  ",
        f"**Model:** {(r.get('provider') or {}).get('model', '-')}  ",
        f"**Budget used:** {c.get('tool_calls', '-')} tool calls, {c.get('model_calls', '-')} model calls, "
        f"{c.get('elapsed_s', '-')} s; tokens {c.get('prompt_tokens', '-')} in / {c.get('completion_tokens', '-')} out; "
        f"estimated cost ${c.get('estimated_cost_usd', 0):.4f}",
        "",
        "## Warning",
    ]
    for w in b["context"]["warning"]:
        lines.append(f"- **{w['tag']}** {w['text']}")
    lines += ["", "## Site conditions"]
    for k, v in b["context"]["site"].items():
        lines.append(f"- {k}: {v}")
    lines += ["", "## Evidence (observations computed by the simulator)", ""]
    for e in b["evidence"]:
        lines.append(f"- **{e['evidence_id']}** ({e['kind']}, t={e['t_start_s']:.0f}..{e['t_end_s']:.0f} s): {e['summary']}")
    if b["predictions"]:
        lines += ["", "## Model-based expectations (not observations)", ""]
        for p in b["predictions"]:
            keys = [k for k in p if k.startswith("expected_")]
            lines.append(f"- **{p['prediction_id']}** if {p['hypothesis']}, {p['test']}: "
                         + "; ".join(f"{k}={p[k]}" for k in keys))
    interventions = [e for e in b["evidence"] if e["kind"] == "pump_stop_test"]
    lines += ["", "## Interventions", ""]
    lines += [f"- {e['evidence_id']}: {e['summary']}" for e in interventions] or ["- none"]
    d = b.get("diagnosis")
    lines += ["", "## Outcome", ""]
    if d:
        lines.append(f"**{d['outcome'].upper()}**" + (f": {d['primary_hypothesis']}" if d.get("primary_hypothesis") else "")
                     + f" (confidence: {d['confidence']})")
        lines += ["", d["summary"], ""]
        if d.get("requested_evidence"):
            lines += [f"Evidence requested: {d['requested_evidence']}", ""]
        lines += ["| hypothesis | status | supporting | contradicting | note |", "|---|---|---|---|---|"]
        lines += [_fmt_hyp(h) for h in d["hypotheses"]]
        lines += ["", f"Recommended remedy: `{d['recommended_remedy']}`"]
    else:
        lines.append("No diagnosis was submitted.")
    rem = b.get("remedy")
    if rem:
        lines += ["", "## Simulated maintenance", ""]
        if rem.get("approved"):
            lines.append(f"Approved `{rem['remedy']}` (maintenance action `{rem.get('maintenance_action', '-')}`).")
            o = rem.get("post_maintenance_observation")
            if o:
                s = o["summary"]
                alarms = ", ".join(a["tag"] for a in o.get("alarms_on_this_window", [])) or "none"
                lines.append(f"- Measured after maintenance (t={o['t_start_s']:.0f}..{o['t_end_s']:.0f} s): LT-101 "
                             f"{s['level_trend']['rate_mm_per_min']:+.2f} mm/min vs nominal balance "
                             f"{s['nominal_expected_rate_mm_per_min']:+.2f} mm/min; FT-102 {s['FT102_mean_L_s']:.2f} L/s; "
                             f"alarms on these readings: {alarms}. Public measurements, not ground truth.")
            if rem.get("independent_check"):
                lines.append(f"- {rem['independent_check']}")
            legacy = rem.get("verification")  # runs recorded before the check was sealed
            if legacy:
                lines.append(f"- Independent check recorded by an older version: "
                             f"**{'PASSED' if legacy['passed'] else 'FAILED'}**")
        else:
            lines.append(rem.get("note", "declined"))
    jr = b.get("judge_reveal")
    if jr and jr.get("remedy_check"):
        rc = jr["remedy_check"]
        lines += ["", "## Independent check of the simulated maintenance (judge-only, after reveal)", "",
                  f"**{'PASSED' if rc['passed'] else 'FAILED'}** ({rc['maintenance_action']}, {rc['horizon_s']:.0f} s, "
                  f"{rc.get('evaluator_version', '')})"]
        for chk in rc["checks"]:
            lines.append(f"- {chk['check']}: {'pass' if chk['passed'] else 'fail'} "
                         + ", ".join(f"{k}={v2}" for k, v2 in chk.items() if k not in ("check", "passed")))
    lines += ["", "## Ground truth", ""]
    if jr:
        g = jr["grade"]
        lines += [f"_{jr['section']}_", "", f"- True cause: **{jr['fault_family']}** ({jr['label']})",
                  f"- Identifiable with the permitted instruments: {jr['identifiability']['identifiable']}",
                  f"- Grade: **{g['category']}**"]
        if jr.get("twin"):
            lines.append(f"- Twin challenge: picked slot {jr['twin']['picked_slot']} of pair {jr['twin']['pair_id']}")
    else:
        lines.append("Not revealed. Ground truth is shown only after a judge reveals a terminal run.")
    lines += ["", "## Limitations", ""] + [f"- {x}" for x in b["limitations"]]
    lines += ["", f"Evidence SHA-256: `{b['integrity']['evidence_sha256']}`", ""]
    return "\n".join(lines)
