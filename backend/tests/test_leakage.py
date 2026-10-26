"""Hidden-state boundary: nothing private reaches the model, the public API, logs or exports before reveal."""

import json
import logging
import re
import time

import pytest
from fastapi.testclient import TestClient

from faultline.agent.provider import ScriptedProvider, tool_call
from faultline.api import create_app
from faultline.instruments import InstrumentPanel
from faultline.runtime import public_context
from faultline.sim.case import CaseConfig
from faultline.sim.twins import falling_level_pair

H = {"x-faultline-judge": "1"}
HIDDEN_KEYS = ["pump_capacity_factor", "leak_coeff", "stuck_at_m", "initial_level_m", '"seed"', "true_level",
               "fault_family", "hidden_parameters", "true_state_trace", "slot_labels", "picked_slot", "mismatch",
               "truth_json", "grade_json"]
HIDDEN_LABEL_WORDS = ["worn impeller", "orifice leak", "stuck at 1.80 m", "delivering exactly the demand",
                      "calibrated to the same"]


@pytest.fixture()
def app(tmp_path):
    return create_app(tmp_path / "leak.db")


def scripted(_mode):
    return ScriptedProvider([
        {"tool_calls": [tool_call("read_observations", {"scope": "alarm_window", "purpose": "establish the balance"})]},
        {"tool_calls": [tool_call("measure_inlet_flow", {"duration_s": 60, "purpose": "pump vs leak"})]},
        {"tool_calls": [tool_call("request_independent_level_measurement", {"purpose": "sensor check"})]},
        {"tool_calls": [tool_call("submit_diagnosis", {
            "outcome": "inconclusive", "confidence": "low", "summary": "E1-E3 recorded; test fixture stops here.",
            "recommended_remedy": "none_until_more_evidence", "requested_evidence": "more data",
            "hypotheses": [{"id": h, "status": "open", "supporting_evidence": [], "contradicting_evidence": []}
                           for h in ("no_fault", "pump_delivery_reduced", "tank_leak", "level_sensor_stuck")]})]},
    ])


def hidden_values(truth: dict) -> list[str]:
    """Exact hidden numbers. The initial true level is excluded on purpose: a healthy LT-101 measures it."""
    f = truth["case"]["fault"]
    vals = [str(truth["seed"])]
    for x in (f["leak_coeff_m25_s"], f["pump_capacity_factor"]):
        if x not in (0.0, 1.0) and len(repr(x)) >= 5:
            vals.append(repr(x))
    return vals


def assert_clean(text: str, truth: dict, where: str):
    low = text.lower()
    for k in HIDDEN_KEYS:
        assert k.lower() not in low, f"hidden key {k} leaked in {where}"
    for w in HIDDEN_LABEL_WORDS:
        assert w not in low, f"hidden label {w!r} leaked in {where}"
    for v in hidden_values(truth):
        assert v not in text, f"hidden value {v} leaked in {where}"


def run_case(client, app, how):
    client.post("/api/judge/session", headers=H)
    if how == "twin":
        ch = client.post("/api/judge/twin-challenges", json={"pair_id": "falling-level"}, headers=H).json()
        assert_no_mapping(ch)
        rid = client.post(f"/api/judge/twin-challenges/{ch['challenge_id']}/pick", json={"slot": "random"},
                          headers=H).json()["run_id"]
    else:
        fam, sev = how
        rid = client.post("/api/judge/blind-runs", json={"family": fam, "severity": sev, "site_profile": "standard"},
                          headers=H).json()["run_id"]
    return rid


def assert_no_mapping(ch: dict):
    text = json.dumps(ch)
    for w in HIDDEN_LABEL_WORDS:
        assert w not in text
    for card in ch["cards"]:
        assert set(card) == {"slot", "samples", "summary", "alarms"}


@pytest.mark.parametrize("how", ["twin", ("tank_leak", "small"), ("pump_delivery_reduced", "severe"),
                                 ("level_sensor_stuck", "true_level_rising"), ("no_fault", "high_demand")])
def test_no_hidden_state_in_model_requests_api_logs_or_exports(app, how, caplog):
    caplog.set_level(logging.DEBUG)
    m = app.state.manager
    providers = []

    def make(mode):
        p = scripted(mode)
        providers.append(p)
        return p

    m.provider_for = make
    with TestClient(app) as c:
        rid = run_case(c, app, how)
        truth = m._sealed.get_truth(rid)
        assert re.fullmatch(r"[0-9a-f]{16}", rid)
        assert_clean(json.dumps(c.get(f"/api/runs/{rid}").json()), truth, "ready view")
        assert c.post(f"/api/runs/{rid}/start", json={"mode": "live"}).status_code == 200
        for _ in range(200):
            v = c.get(f"/api/runs/{rid}").json()
            if v["status"] not in ("ready", "investigating"):
                break
            time.sleep(0.02)
        assert v["status"] == "inconclusive"
        for path in (f"/api/runs/{rid}", f"/api/runs/{rid}/telemetry", "/api/runs", f"/api/runs/{rid}/export.json",
                     f"/api/runs/{rid}/report.md", "/api/status", "/api/catalog"):
            r = c.get(path)
            assert r.status_code == 200
            assert_clean(r.text, truth, path)
        for req in providers[0].requests:
            assert_clean(json.dumps(req), truth, "model request")
        assert_clean(caplog.text, truth, "logs")
        # after reveal the judge sees the truth, clearly separated
        rv = c.post(f"/api/judge/runs/{rid}/reveal", headers=H).json()
        assert rv["fault_family"] == truth["case"]["fault"]["family"]
        assert "judge_reveal" in c.get(f"/api/runs/{rid}/export.json").json()


def test_twin_briefs_differ_only_in_measured_numbers():
    """Same noise seed for both twins: after masking digits, the model's first messages are identical."""
    msgs = []
    for member in falling_level_pair().members:
        panel = InstrumentPanel(member, 4242)
        from faultline.agent.prompts import initial_user_message

        msgs.append(re.sub(r"\d", "#", initial_user_message(public_context(panel, "same"), {"b": 1})))
    assert msgs[0] == msgs[1]


def test_judge_endpoints_need_cookie_and_header(app):
    with TestClient(app) as c:
        assert c.post("/api/judge/blind-runs", json={"family": "tank_leak", "severity": "small"}).status_code == 403
        c.post("/api/judge/session", headers=H)
        assert c.post("/api/judge/blind-runs", json={"family": "tank_leak", "severity": "small"}).status_code == 403
        assert c.post("/api/judge/blind-runs", json={"family": "tank_leak", "severity": "small"},
                      headers=H).status_code == 200
        assert c.post("/api/judge/session").status_code == 403  # header required (CSRF guard)


def test_reveal_only_after_terminal_and_twin_challenge_single_use(app):
    with TestClient(app) as c:
        c.post("/api/judge/session", headers=H)
        ch = c.post("/api/judge/twin-challenges", json={"pair_id": "flat-reading"}, headers=H).json()
        rid = c.post(f"/api/judge/twin-challenges/{ch['challenge_id']}/pick", json={"slot": "alpha"}, headers=H).json()["run_id"]
        assert c.post(f"/api/judge/twin-challenges/{ch['challenge_id']}/pick", json={"slot": "beta"},
                      headers=H).status_code == 409
        assert c.post(f"/api/judge/runs/{rid}/reveal", headers=H).status_code == 409
        assert c.post(f"/api/runs/{rid}/reveal-guided").status_code == 403
        c.post(f"/api/runs/{rid}/cancel")
        assert c.get(f"/api/runs/{rid}").json()["status"] == "cancelled"
        assert c.post(f"/api/runs/{rid}/start", json={"mode": "reference"}).status_code == 409  # cannot resume blind
        assert c.post(f"/api/judge/runs/{rid}/reveal", headers=H).status_code == 200


def test_live_mode_without_key_is_refused_not_substituted(app, monkeypatch):
    monkeypatch.setattr("faultline.runtime.api_key", lambda: None)
    with TestClient(app) as c:
        c.post("/api/judge/session", headers=H)
        rid = c.post("/api/judge/blind-runs", json={"family": "tank_leak", "severity": "small"}, headers=H).json()["run_id"]
        r = c.post(f"/api/runs/{rid}/start", json={"mode": "live"})
        assert r.status_code == 409 and "NEBIUS_API_KEY" in r.json()["error"]
        assert c.get(f"/api/runs/{rid}").json()["status"] == "ready"


def test_private_objects_redact_their_repr():
    case = falling_level_pair().members[1]
    panel = InstrumentPanel(case, 77)
    assert "redacted" in repr(panel) and "redacted" in repr(panel._private_plant())
    assert "77" not in repr(panel._private_plant().noise)
    assert isinstance(CaseConfig.from_private_dict(case.to_private_dict()), CaseConfig)


def test_built_frontend_bundle_contains_no_private_case_labels():
    """Frontend data: the shipped bundle must not hard-code any hidden case description."""
    from pathlib import Path

    from faultline.sim.twins import all_pairs

    dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    if not dist.exists():
        pytest.skip("frontend not built")
    text = "".join(p.read_text(encoding="utf-8", errors="ignore") for p in dist.rglob("*") if p.suffix in (".js", ".html"))
    private = [lbl for pair in all_pairs().values() for lbl in pair.member_labels] + HIDDEN_LABEL_WORDS
    for phrase in private:
        assert phrase not in text, phrase
