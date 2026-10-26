"""Run persistence, deterministic rebuild, export integrity, grading and remedy verification."""

import json
import time

import pytest
from fastapi.testclient import TestClient

from faultline.api import create_app
from faultline.instruments import InstrumentPanel
from faultline.judge.evaluator import grade, verify_remedy
from faultline.sim.presets import build_preset
from faultline.sim.twins import falling_level_pair, flat_reading_pair

H = {"x-faultline-judge": "1"}


def finish(c, rid, mode="reference"):
    c.post(f"/api/runs/{rid}/start", json={"mode": mode})
    for _ in range(300):
        v = c.get(f"/api/runs/{rid}").json()
        if v["status"] not in ("ready", "investigating"):
            return v
        time.sleep(0.02)
    raise AssertionError("run did not finish")


def test_run_survives_restart_and_rebuild_is_deterministic(tmp_path):
    db = tmp_path / "p.db"
    app = create_app(db)
    with TestClient(app) as c:
        c.post("/api/judge/session", headers=H)
        rid = c.post("/api/judge/blind-runs", json={"family": "tank_leak", "severity": "large", "site_profile": "standard"},
                     headers=H).json()["run_id"]
        v = finish(c, rid)
        tele = c.get(f"/api/runs/{rid}/telemetry").json()
    app2 = create_app(db)  # simulated server restart: in-memory runtimes are gone
    with TestClient(app2) as c2:
        v2 = c2.get(f"/api/runs/{rid}").json()
        assert v2["evidence"] == v["evidence"] and v2["diagnosis"] == v["diagnosis"]
        assert c2.get(f"/api/runs/{rid}/telemetry").json()["samples"] == tele["samples"]  # replayed from seed + actions
        assert v2["status"] == "awaiting_approval"
        res = c2.post(f"/api/runs/{rid}/remedy", json={"approve": True}).json()  # works after restart
        assert res["approved"] and "post_maintenance_observation" in res
        for hidden in ("value_L_s", "expected_L_s", "max_error_mm", "verification", "passed"):
            assert hidden not in json.dumps(res)  # true-plant check stays sealed before reveal
        c2.post("/api/judge/session", headers=H)
        rv = c2.post(f"/api/judge/runs/{rid}/reveal", headers=H).json()
        assert rv["remedy_check"]["passed"] and rv["fault_family"] == "tank_leak"


def test_exported_evidence_matches_recorded_observations(tmp_path):
    app = create_app(tmp_path / "e.db")
    with TestClient(app) as c:
        c.post("/api/judge/session", headers=H)
        rid = c.post("/api/judge/blind-runs", json={"family": "level_sensor_stuck", "severity": "true_level_rising",
                                                    "site_profile": "no_inlet_meter"}, headers=H).json()["run_id"]
        finish(c, rid)
        bundle = c.get(f"/api/runs/{rid}/export.json").json()
        samples = {s["t_s"]: s for s in c.get(f"/api/runs/{rid}/telemetry").json()["samples"]}
        view = c.get(f"/api/runs/{rid}").json()
    assert bundle["evidence"] == view["evidence"]
    assert "judge_reveal" not in bundle
    for ev in bundle["evidence"]:
        rows = ev["data"].get("rows_every_60s") or ev["data"].get("rows_every_30s") or []
        for t, lt, ft, cmd, fb in rows:
            s = samples[t]
            assert (lt, ft, cmd, fb) == (s["LT101_m"], s["FT102_L_s"], s["P101_command"], s["P101_run_feedback"])
        if ev["kind"] == "independent_level":
            assert ev["data"]["LT101_same_step_m"] == samples[ev["data"]["t_s"]]["LT101_m"]
    import hashlib

    assert bundle["integrity"]["evidence_sha256"] == hashlib.sha256(
        json.dumps(bundle["evidence"], sort_keys=True).encode()).hexdigest()


def test_server_restart_marks_running_investigations_failed(tmp_path):
    db = tmp_path / "r.db"
    app = create_app(db)
    store = app.state.manager.store
    store.create_run("abc", kind="blind", mode="live", public={"warning": []}, budgets={}, provider={})
    store.update_run("abc", status="investigating")
    create_app(db)
    assert store.get_run("abc")["status"] == "failed"


# ---------------- grading ----------------

HYPS = ("no_fault", "pump_delivery_reduced", "tank_leak", "level_sensor_stuck")


def D(outcome, primary=None, conf="medium", remedy="no_action", open_=("pump_delivery_reduced", "tank_leak")):
    return {"outcome": outcome, "primary_hypothesis": primary, "confidence": conf, "recommended_remedy": remedy,
            "hypotheses": [{"id": h, "status": "open" if h in open_ else "ruled_out"} for h in HYPS]}


@pytest.mark.parametrize("truth,ident,status,diag,cat,correct,cw", [
    ("tank_leak", True, "diagnosed", D("diagnosed", "tank_leak", remedy="repair_tank_leak"), "correct_diagnosis", True, False),
    ("tank_leak", True, "diagnosed", D("diagnosed", "pump_delivery_reduced", "high"), "wrong_diagnosis", False, True),
    ("tank_leak", True, "diagnosed", D("diagnosed", "pump_delivery_reduced", "low"), "wrong_diagnosis", False, False),
    ("tank_leak", False, "inconclusive", D("inconclusive"), "appropriate_inconclusive", True, False),
    ("tank_leak", True, "inconclusive", D("inconclusive"), "unnecessary_inconclusive", False, False),
    ("tank_leak", False, "diagnosed", D("diagnosed", "tank_leak", "high"), "unsupported_diagnosis", False, True),
    ("tank_leak", True, "failed", None, "no_result", False, False),
    ("tank_leak", False, "inconclusive", D("inconclusive", open_=("pump_delivery_reduced", "no_fault")),
     "wrong_inconclusive", False, False),
])
def test_grading_categories(truth, ident, status, diag, cat, correct, cw):
    g = grade(truth, ident, status, diag, ["pump_delivery_reduced"])
    assert (g["category"], g["correct"], g["confident_wrong"]) == (cat, correct, cw)


def test_lucky_guess_in_unidentifiable_case_is_not_counted_correct():
    g = grade("tank_leak", False, "diagnosed", D("diagnosed", "tank_leak"))
    assert g["category"] == "unsupported_diagnosis" and g["lucky_guess"] and not g["correct"]


# ---------------- remedy verification ----------------

def plant_at_t0(case):
    return InstrumentPanel(case, 1)._private_plant()


@pytest.mark.parametrize("case,right,wrong", [
    (falling_level_pair().members[0], "replace_or_repair_pump", "repair_tank_leak"),
    (falling_level_pair().members[1], "repair_tank_leak", "replace_or_repair_pump"),
    (flat_reading_pair().members[0], "replace_level_sensor", "replace_or_repair_pump"),
])
def test_correct_remedy_verifies_and_wrong_remedy_does_not(case, right, wrong):
    assert verify_remedy(plant_at_t0(case), right, case.fault.family)["passed"]
    assert not verify_remedy(plant_at_t0(case), wrong, case.fault.family)["passed"]


def test_no_action_on_healthy_plant_verifies_but_not_on_a_faulty_one():
    assert verify_remedy(plant_at_t0(build_preset("no_fault", "high_demand", "standard")), "no_action", "no_fault")["passed"]
    assert not verify_remedy(plant_at_t0(build_preset("tank_leak", "small", "standard")), "no_action", "tank_leak")["passed"]


def test_unnecessary_maintenance_on_a_healthy_plant_is_not_verified():
    r = verify_remedy(plant_at_t0(build_preset("no_fault", "high_demand", "standard")), "replace_or_repair_pump",
                      "no_fault")
    assert not r["passed"]
    assert [c["passed"] for c in r["checks"]] == [True, True, False]  # plant fine, but the repair was not needed


def test_replay_import_roundtrip_is_labelled_and_cannot_be_resumed(tmp_path):
    app = create_app(tmp_path / "rp.db")
    m = app.state.manager
    with TestClient(app) as c:
        c.post("/api/judge/session", headers=H)
        rid = c.post("/api/judge/blind-runs", json={"family": "tank_leak", "severity": "small", "site_profile": "standard"},
                     headers=H).json()["run_id"]
        finish(c, rid)
        c.post(f"/api/runs/{rid}/remedy", json={"approve": True})
        c.post(f"/api/judge/runs/{rid}/reveal", headers=H)
        bundle = c.get(f"/api/runs/{rid}/export.json").json()
        new = m.import_replay(bundle, "test.json")
        v = c.get(f"/api/runs/{new}").json()
        assert v["mode"] == "replay" and v["status"] == "diagnosed"
        assert v["evidence"] == bundle["evidence"] and v["diagnosis"] == bundle["diagnosis"]
        assert v["reveal"]["fault_family"] == "tank_leak"
        assert c.get(f"/api/runs/{new}/telemetry").json()["samples"] == bundle["telemetry"]
        assert c.post(f"/api/runs/{new}/start", json={"mode": "reference"}).status_code == 409
        assert c.post(f"/api/judge/runs/{new}/reveal", headers=H).status_code == 409
        assert [e["type"] for e in c.get(f"/api/runs/{new}").json()["events"]] == [e["type"] for e in bundle["timeline"]]


def test_dns_rebinding_and_cross_origin_writes_are_refused(tmp_path):
    app = create_app(tmp_path / "h.db")
    with TestClient(app) as c:
        assert c.get("/api/status", headers={"host": "evil.example:8000"}).status_code == 400
        assert c.post("/api/judge/session", headers={**H, "origin": "http://evil.example:8000"}).status_code == 403
        assert c.post("/api/guided", headers={"origin": "http://evil.example"}).status_code == 403
        assert c.post("/api/guided", headers={"origin": "http://127.0.0.1:8000"}).status_code == 200


def test_spend_ledger_is_shared_between_processes(tmp_path):
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eval"))
    from run_eval import Ledger

    path = tmp_path / "ledger.jsonl"
    a, b = Ledger(1.0, path), Ledger(1.0, path)
    a.add(0.6, "a")
    b.add(0.3, "b")
    assert a.total() == b.total() == 0.9
    assert a.allowed(0.1) and not b.allowed(0.2)


def test_markdown_report_after_approval_and_after_reveal(tmp_path):
    app = create_app(tmp_path / "md.db")
    with TestClient(app) as c:
        c.post("/api/judge/session", headers=H)
        rid = c.post("/api/judge/blind-runs", json={"family": "pump_delivery_reduced", "severity": "severe",
                                                    "site_profile": "standard"}, headers=H).json()["run_id"]
        finish(c, rid)
        c.post(f"/api/runs/{rid}/remedy", json={"approve": True})
        before = c.get(f"/api/runs/{rid}/report.md")
        assert before.status_code == 200 and "Measured after maintenance" in before.text
        assert "value_L_s" not in before.text and "judge-only" not in before.text
        c.post(f"/api/judge/runs/{rid}/reveal", headers=H)
        after = c.get(f"/api/runs/{rid}/report.md")
        assert after.status_code == 200 and "Independent check of the simulated maintenance" in after.text
        assert "**PASSED**" in after.text
