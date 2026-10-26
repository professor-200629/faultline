"""Agent tools: typed schemas, validation outside the model, and execution.

The executor holds an `InstrumentPanel` (the only path to the plant) and an
evidence ledger. Every argument is validated here, in backend code, before
anything touches the simulator. Results returned to the model are built from
public observation dictionaries only.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from ..analysis import level_trend, mean_demand_L_s, window_summary, evaluate_alarms
from ..instruments import InstrumentError, InstrumentPanel
from ..sim.plant import WINDOW_START_S
from .public_model import HYPOTHESES, TESTS, PredictionError, predict

TOOL_VERSION = "tools-v1"
REMEDIES = ("replace_or_repair_pump", "repair_tank_leak", "replace_level_sensor", "no_action",
            "none_until_more_evidence")
STATUSES = ("open", "supported", "weakened", "ruled_out")

Purpose = Field(..., min_length=3, max_length=240, description="What this step could distinguish")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ReadObservationsArgs(_Strict):
    scope: Literal["alarm_window", "latest_15_min"] = "alarm_window"
    purpose: str = Purpose


def _grid(v: Optional[int]) -> Optional[int]:
    if v is not None and v % 10:
        raise ValueError("must be a multiple of 10 s (the historian interval)")
    return v


class MeasureInletArgs(_Strict):
    duration_s: int = Field(..., ge=30, le=300)
    purpose: str = Purpose

    @field_validator("duration_s")
    @classmethod
    def on_grid(cls, v):
        return _grid(v)


class IndependentLevelArgs(_Strict):
    purpose: str = Purpose


class SetPumpArgs(_Strict):
    state: Literal["off"]
    hold_s: int = Field(..., ge=60, le=600)
    purpose: str = Purpose

    @field_validator("hold_s")
    @classmethod
    def on_grid(cls, v):
        return _grid(v)


class AdvanceArgs(_Strict):
    duration_s: int = Field(..., ge=30, le=1800)
    purpose: str = Purpose

    @field_validator("duration_s")
    @classmethod
    def on_grid(cls, v):
        return _grid(v)


class PredictArgs(_Strict):
    hypothesis: Literal["no_fault", "pump_delivery_reduced", "tank_leak", "level_sensor_stuck"]
    test: Literal["inlet_flow", "independent_level", "pump_stop_test", "wait"]
    duration_s: Optional[int] = Field(None, ge=30, le=1800)
    purpose: str = Purpose

    @field_validator("duration_s")
    @classmethod
    def on_grid(cls, v):
        return _grid(v)


class HypothesisEntry(_Strict):
    id: Literal["no_fault", "pump_delivery_reduced", "tank_leak", "level_sensor_stuck"]
    status: Literal["open", "supported", "weakened", "ruled_out"]
    supporting_evidence: list[str] = Field(default_factory=list, max_length=8)
    contradicting_evidence: list[str] = Field(default_factory=list, max_length=8)
    note: str = Field("", max_length=300)


class UpdateHypothesesArgs(_Strict):
    hypotheses: list[HypothesisEntry] = Field(..., min_length=1, max_length=4)
    next_step: str = Field("", max_length=240)

    @field_validator("hypotheses")
    @classmethod
    def unique_ids(cls, v):
        ids = [h.id for h in v]
        if len(ids) != len(set(ids)):
            raise ValueError("each hypothesis id may appear once")
        return v


class SubmitDiagnosisArgs(_Strict):
    outcome: Literal["diagnosed", "inconclusive"]
    primary_hypothesis: Optional[Literal["no_fault", "pump_delivery_reduced", "tank_leak", "level_sensor_stuck"]] = None
    hypotheses: list[HypothesisEntry] = Field(..., min_length=4, max_length=4)
    confidence: Literal["low", "medium", "high"]
    summary: str = Field(..., min_length=10, max_length=700)
    recommended_remedy: Literal["replace_or_repair_pump", "repair_tank_leak", "replace_level_sensor", "no_action",
                                "none_until_more_evidence"]
    requested_evidence: str = Field("", max_length=300)


def _fn(name: str, description: str, properties: dict, required: list[str]) -> dict:
    return {"type": "function", "function": {"name": name, "description": description, "parameters": {
        "type": "object", "properties": properties, "required": required, "additionalProperties": False}}}


_P = {"type": "string", "description": "One sentence: what this step could distinguish."}
_H = {"type": "string", "enum": list(HYPOTHESES)}
_ENTRY = {
    "type": "object",
    "properties": {
        "id": _H,
        "status": {"type": "string", "enum": list(STATUSES)},
        "supporting_evidence": {"type": "array", "items": {"type": "string"}, "description": "Evidence IDs like E2"},
        "contradicting_evidence": {"type": "array", "items": {"type": "string"}},
        "note": {"type": "string", "description": "Short factual note citing evidence IDs"},
    },
    "required": ["id", "status", "supporting_evidence", "contradicting_evidence"],
    "additionalProperties": False,
}

TOOL_SPECS: dict[str, dict] = {
    "read_observations": _fn(
        "read_observations",
        "Read logged historian data (LT-101 level, FT-102 demand flow, P-101 command and run feedback) with a "
        "computed trend and the public alarm evaluation. Takes no simulated time.",
        {"scope": {"type": "string", "enum": ["alarm_window", "latest_15_min"]}, "purpose": _P},
        ["scope", "purpose"],
    ),
    "measure_inlet_flow": _fn(
        "measure_inlet_flow",
        "Have a technician fit the FT-101 clamp-on meter on the P-101 discharge (30 s to fit and settle), then "
        "average for duration_s (30-300 s, a multiple of 10). Returns delivered pump flow with its stated "
        "uncertainty.",
        {"duration_s": {"type": "integer", "minimum": 30, "maximum": 300, "multipleOf": 10}, "purpose": _P},
        ["duration_s", "purpose"],
    ),
    "request_independent_level_measurement": _fn(
        "request_independent_level_measurement",
        "Ask a technician for a manual dip-tape level reading (DIP-101), independent of LT-101. Takes 120 s of "
        "simulated time and returns the LT-101 reading logged at the same simulation step.",
        {"purpose": _P},
        ["purpose"],
    ),
    "set_simulated_pump": _fn(
        "set_simulated_pump",
        "Bounded diagnostic intervention: stop P-101 for hold_s seconds of simulated time, log LT-101 and FT-102, "
        "then automatically restart it. A low-level interlock acting on the LT-101 reading aborts the test.",
        {"state": {"type": "string", "enum": ["off"]},
         "hold_s": {"type": "integer", "minimum": 60, "maximum": 600, "multipleOf": 10}, "purpose": _P},
        ["state", "hold_s", "purpose"],
    ),
    "advance_simulation": _fn(
        "advance_simulation",
        "Wait duration_s seconds of simulated time (a multiple of 10) with no intervention and return the newly "
        "logged data with its trend.",
        {"duration_s": {"type": "integer", "minimum": 30, "maximum": 1800, "multipleOf": 10}, "purpose": _P},
        ["duration_s", "purpose"],
    ),
    "predict_under_hypothesis": _fn(
        "predict_under_hypothesis",
        "Compute what a test would show IF a candidate hypothesis were true, using only the public datasheet "
        "model and the alarm window you have read. Returns a model-based expectation, never an observation; "
        "predictions cannot be cited as evidence. Takes no simulated time.",
        {"hypothesis": _H, "test": {"type": "string", "enum": list(TESTS)},
         "duration_s": {"type": "integer", "minimum": 30, "maximum": 1800, "multipleOf": 10}, "purpose": _P},
        ["hypothesis", "test", "purpose"],
    ),
    "update_hypotheses": _fn(
        "update_hypotheses",
        "Record the current status of hypotheses with the evidence IDs that support or contradict each.",
        {"hypotheses": {"type": "array", "items": _ENTRY, "minItems": 1, "maxItems": 4},
         "next_step": {"type": "string"}},
        ["hypotheses"],
    ),
    "submit_diagnosis": _fn(
        "submit_diagnosis",
        "Finish the investigation. Use outcome 'diagnosed' only when one hypothesis is supported by evidence and "
        "every other hypothesis is weakened or ruled out by cited evidence. Use 'inconclusive' when the "
        "available evidence cannot separate the remaining hypotheses, and say what evidence would.",
        {
            "outcome": {"type": "string", "enum": ["diagnosed", "inconclusive"]},
            "primary_hypothesis": _H,
            "hypotheses": {"type": "array", "items": _ENTRY, "minItems": 4, "maxItems": 4,
                           "description": "All four hypotheses with final status and evidence IDs"},
            "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
            "summary": {"type": "string", "description": "Concise evidence summary citing evidence IDs"},
            "recommended_remedy": {"type": "string", "enum": list(REMEDIES)},
            "requested_evidence": {"type": "string", "description": "For inconclusive: the measurement that would decide"},
        },
        ["outcome", "hypotheses", "confidence", "summary", "recommended_remedy"],
    ),
}

ARG_MODELS = {
    "read_observations": ReadObservationsArgs,
    "measure_inlet_flow": MeasureInletArgs,
    "request_independent_level_measurement": IndependentLevelArgs,
    "set_simulated_pump": SetPumpArgs,
    "advance_simulation": AdvanceArgs,
    "predict_under_hypothesis": PredictArgs,
    "update_hypotheses": UpdateHypothesesArgs,
    "submit_diagnosis": SubmitDiagnosisArgs,
}


def _thin(samples: list[dict], every_s: float = 60.0) -> list[list]:
    """Compact rows for the model: every `every_s` seconds plus the last sample."""
    rows, last_t = [], None
    for s in samples:
        if last_t is None or s["t_s"] - last_t >= every_s - 1e-9:
            rows.append([s["t_s"], s["LT101_m"], s["FT102_L_s"], s["P101_command"], s["P101_run_feedback"]])
            last_t = s["t_s"]
    if samples and rows[-1][0] != samples[-1]["t_s"]:
        s = samples[-1]
        rows.append([s["t_s"], s["LT101_m"], s["FT102_L_s"], s["P101_command"], s["P101_run_feedback"]])
    return rows


COLUMNS = ["t_s", "LT101_m", "FT102_L_s", "P101_command", "P101_run_feedback"]


@dataclass
class Evidence:
    eid: str
    kind: str
    tool: str
    t_start_s: float
    t_end_s: float
    data: dict
    summary: str

    def public(self) -> dict:
        return {"evidence_id": self.eid, "kind": self.kind, "tool": self.tool, "t_start_s": self.t_start_s,
                "t_end_s": self.t_end_s, "summary": self.summary, "data": self.data}


@dataclass
class ToolOutcome:
    ok: bool
    name: str
    args: dict
    result: dict  # what the model receives
    error: str = ""
    evidence_id: Optional[str] = None
    prediction_id: Optional[str] = None
    terminal: bool = False


@dataclass
class ToolExecutor:
    panel: InstrumentPanel
    evidence: list[Evidence] = field(default_factory=list)
    predictions: list[dict] = field(default_factory=list)
    board: list[dict] = field(default_factory=lambda: [
        {"id": h, "status": "open", "supporting_evidence": [], "contradicting_evidence": [], "note": ""}
        for h in HYPOTHESES])
    diagnosis: Optional[dict] = None
    alarm_summary: Optional[dict] = None
    last_read_t: float = WINDOW_START_S - 1

    def __repr__(self) -> str:
        return "ToolExecutor(<redacted>)"

    # ---------- helpers ----------
    def _add_evidence(self, kind: str, tool: str, t0: float, t1: float, data: dict, summary: str) -> Evidence:
        ev = Evidence(f"E{len(self.evidence) + 1}", kind, tool, t0, t1, data, summary)
        self.evidence.append(ev)
        return ev

    def _evidence_ids(self) -> set[str]:
        return {e.eid for e in self.evidence}

    def _check_refs(self, entries: list[HypothesisEntry]) -> None:
        known = self._evidence_ids()
        for h in entries:
            for ref in h.supporting_evidence + h.contradicting_evidence:
                if ref.startswith("P"):
                    raise ValueError(f"{ref} is a model-based prediction, not evidence; cite observation IDs (E#)")
                if ref not in known:
                    raise ValueError(f"unknown evidence id {ref!r}; known ids: {sorted(known) or 'none yet'}")

    def specs(self, only: Optional[list[str]] = None) -> list[dict]:
        names = only or list(TOOL_SPECS)
        return [TOOL_SPECS[n] for n in names]

    # ---------- dispatcher ----------
    def execute(self, name: str, raw_args: Any) -> ToolOutcome:
        if name not in ARG_MODELS:
            return ToolOutcome(False, name, {}, {"error": f"unknown tool {name!r}"}, error="unknown tool")
        try:
            args = json.loads(raw_args) if isinstance(raw_args, str) else dict(raw_args or {})
            if not isinstance(args, dict):
                raise ValueError("arguments must be a JSON object")
        except (json.JSONDecodeError, ValueError) as e:
            return ToolOutcome(False, name, {}, {"error": f"arguments are not valid JSON: {e}"}, error="bad json")
        try:
            parsed = ARG_MODELS[name].model_validate(args)
        except ValidationError as e:
            msg = "; ".join(f"{'.'.join(str(x) for x in err['loc'])}: {err['msg']}" for err in e.errors()[:6])
            return ToolOutcome(False, name, args, {"error": f"invalid arguments: {msg}"}, error="validation")
        try:
            return getattr(self, f"_t_{name}")(parsed, args)
        except (InstrumentError, PredictionError, ValueError) as e:
            return ToolOutcome(False, name, args, {"error": str(e)}, error="rejected")
        except Exception as e:  # a tool defect must not end the investigation or leak internals
            import logging

            logging.getLogger("faultline").error("tool %s failed with %s", name, type(e).__name__)
            return ToolOutcome(False, name, args, {"error": "internal tool error; the call was not completed"},
                               error="internal")

    # ---------- tools ----------
    def _t_read_observations(self, a: ReadObservationsArgs, raw: dict) -> ToolOutcome:
        now = self.panel.now_s
        if a.scope == "alarm_window":
            samples = self.panel.historian(WINDOW_START_S, 0.0)
        else:
            samples = self.panel.historian(now - 900.0, now)
        summ = window_summary(samples)
        alarms = evaluate_alarms(samples) if a.scope == "alarm_window" else []
        if a.scope == "alarm_window":
            self.alarm_summary = summ
        tr = summ["level_trend"]
        text = (f"LT-101 {tr['first_m']:.3f}->{tr['last_m']:.3f} m, {tr['rate_mm_per_min']:+.2f} ± "
                f"{tr['rate_se_mm_per_min']:.2f} mm/min over t={samples[0]['t_s']:.0f}..{samples[-1]['t_s']:.0f} s; "
                f"FT-102 mean {summ['FT102_mean_L_s']:.3f} L/s; P-101 command ON fraction "
                f"{summ['P101_command_on_fraction']:.2f}; nominal balance expects "
                f"{summ['nominal_expected_rate_mm_per_min']:+.2f} mm/min")
        data = {"columns": COLUMNS, "rows_every_60s": _thin(samples), "summary": summ, "alarms": alarms}
        ev = self._add_evidence("historian_window", "read_observations", samples[0]["t_s"], samples[-1]["t_s"],
                                data, text)
        return ToolOutcome(True, "read_observations", raw, ev.public(), evidence_id=ev.eid)

    def _t_measure_inlet_flow(self, a: MeasureInletArgs, raw: dict) -> ToolOutcome:
        r = self.panel.measure_inlet_flow(a.duration_s)
        text = (f"FT-101 mean delivered flow {r['mean_inlet_flow_L_s']:.3f} ± {r['stated_uncertainty_sd_L_s']:.3f} L/s "
                f"(1 sd) averaged over t={r['t_start_s']:.0f}..{r['t_end_s']:.0f} s (clamp fitted from "
                f"t={r['t_fit_start_s']:.0f} s) with P-101 command "
                f"{'ON' if r['P101_command_during'] else 'OFF'}; rated delivery is 1.200 L/s")
        ev = self._add_evidence("inlet_flow_measurement", "measure_inlet_flow", r["t_fit_start_s"], r["t_end_s"],
                                r, text)
        return ToolOutcome(True, "measure_inlet_flow", raw, ev.public(), evidence_id=ev.eid)

    def _t_request_independent_level_measurement(self, a: IndependentLevelArgs, raw: dict) -> ToolOutcome:
        r = self.panel.independent_level()
        lt = r["LT101_same_step_m"]
        diff_mm = (r["dip_level_m"] - lt) * 1000 if lt is not None else None
        r = dict(r, dip_minus_LT_mm=round(diff_mm, 1) if diff_mm is not None else None,
                 comparison_sd_mm=round(((0.005 ** 2 + 0.003 ** 2) ** 0.5) * 1000, 1))
        when = "the same step" if r["LT101_sample_t_s"] == r["t_s"] else f"t={r['LT101_sample_t_s']:.0f} s"
        text = (f"DIP-101 {r['dip_level_m']:.3f} m at t={r['t_s']:.0f} s vs LT-101 {lt:.3f} m logged at {when}: "
                f"difference {diff_mm:+.0f} mm (comparison sd about {r['comparison_sd_mm']:.0f} mm)")
        ev = self._add_evidence("independent_level", "request_independent_level_measurement", r["t_start_s"],
                                r["t_s"], r, text)
        return ToolOutcome(True, "request_independent_level_measurement", raw, ev.public(), evidence_id=ev.eid)

    def _t_set_simulated_pump(self, a: SetPumpArgs, raw: dict) -> ToolOutcome:
        r = self.panel.pump_stop_test(a.hold_s)
        samples = r["samples"]
        stop_samples = [s for s in samples if s["P101_command"] == 0] or samples
        tr = level_trend(stop_samples) if len(stop_samples) >= 3 else None
        data = {
            "t_start_s": r["t_start_s"], "t_end_s": r["t_end_s"], "requested_hold_s": a.hold_s,
            "aborted_by_low_level_interlock": r["aborted_by_low_level_interlock"],
            "columns": COLUMNS, "rows_every_30s": _thin(samples, 30.0),
            "LT101_change_m": round(samples[-1]["LT101_m"] - samples[0]["LT101_m"], 4),
            "LT101_trend_while_stopped": tr,
            "FT102_mean_L_s": mean_demand_L_s(samples),
            "note": r["note"],
        }
        text = (f"P-101 stopped t={r['t_start_s']:.0f}..{r['t_end_s']:.0f} s: LT-101 changed "
                f"{data['LT101_change_m'] * 1000:+.0f} mm"
                + (f", {tr['rate_mm_per_min']:+.2f} ± {tr['rate_se_mm_per_min']:.2f} mm/min while stopped" if tr else "")
                + f"; FT-102 mean {data['FT102_mean_L_s']:.3f} L/s"
                + ("; ABORTED by low-level interlock" if data["aborted_by_low_level_interlock"] else ""))
        ev = self._add_evidence("pump_stop_test", "set_simulated_pump", r["t_start_s"], r["t_end_s"], data, text)
        return ToolOutcome(True, "set_simulated_pump", raw, ev.public(), evidence_id=ev.eid)

    def _t_advance_simulation(self, a: AdvanceArgs, raw: dict) -> ToolOutcome:
        r = self.panel.advance(a.duration_s)
        samples = self.panel.historian(r["t_start_s"], r["t_end_s"])
        tr = level_trend(samples)
        data = {"t_start_s": r["t_start_s"], "t_end_s": r["t_end_s"], "columns": COLUMNS,
                "rows_every_60s": _thin(samples), "LT101_trend": tr, "FT102_mean_L_s": mean_demand_L_s(samples)}
        text = (f"Waited t={r['t_start_s']:.0f}..{r['t_end_s']:.0f} s: LT-101 {tr['first_m']:.3f}->{tr['last_m']:.3f} m, "
                f"{tr['rate_mm_per_min']:+.2f} ± {tr['rate_se_mm_per_min']:.2f} mm/min; FT-102 mean "
                f"{data['FT102_mean_L_s']:.3f} L/s")
        ev = self._add_evidence("observation_wait", "advance_simulation", r["t_start_s"], r["t_end_s"], data, text)
        return ToolOutcome(True, "advance_simulation", raw, ev.public(), evidence_id=ev.eid)

    def _t_predict_under_hypothesis(self, a: PredictArgs, raw: dict) -> ToolOutcome:
        if self.alarm_summary is None:
            raise ValueError("call read_observations with scope 'alarm_window' first; predictions use that window")
        p = predict(a.hypothesis, a.test, self.alarm_summary, self.panel.now_s, a.duration_s)
        pid = f"P{len(self.predictions) + 1}"
        p = {"prediction_id": pid, **p}
        self.predictions.append(p)
        return ToolOutcome(True, "predict_under_hypothesis", raw, p, prediction_id=pid)

    def _t_update_hypotheses(self, a: UpdateHypothesesArgs, raw: dict) -> ToolOutcome:
        self._check_refs(a.hypotheses)
        by_id = {h["id"]: h for h in self.board}
        for h in a.hypotheses:
            by_id[h.id] = h.model_dump()
        self.board = [by_id[h] for h in HYPOTHESES]
        return ToolOutcome(True, "update_hypotheses", raw, {"recorded": True, "board": self.board})

    def _t_submit_diagnosis(self, a: SubmitDiagnosisArgs, raw: dict) -> ToolOutcome:
        self._check_refs(a.hypotheses)
        if sorted(h.id for h in a.hypotheses) != sorted(HYPOTHESES):
            raise ValueError("hypotheses must list each of the four catalogue hypotheses exactly once")
        by = {h.id: h for h in a.hypotheses}
        if a.outcome == "diagnosed":
            if not a.primary_hypothesis:
                raise ValueError("a diagnosis needs primary_hypothesis")
            prim = by[a.primary_hypothesis]
            if prim.status != "supported" or not prim.supporting_evidence:
                raise ValueError("the primary hypothesis must be 'supported' with at least one supporting evidence ID")
            for h in a.hypotheses:
                if h.id == a.primary_hypothesis:
                    continue
                if h.status not in ("weakened", "ruled_out") or not h.contradicting_evidence:
                    raise ValueError(f"{h.id} is not weakened or ruled out by cited evidence; gather evidence that "
                                     "separates it, or submit 'inconclusive'")
            if a.recommended_remedy == "none_until_more_evidence":
                raise ValueError("a diagnosis must recommend a remedy or 'no_action'")
        else:
            if a.recommended_remedy != "none_until_more_evidence":
                raise ValueError("an inconclusive outcome must use recommended_remedy 'none_until_more_evidence'")
            if not a.requested_evidence:
                raise ValueError("an inconclusive outcome must say which evidence would decide (requested_evidence)")
            remaining = [h for h in a.hypotheses if h.status in ("open", "supported")]
            if len(remaining) < 2:
                raise ValueError("inconclusive needs at least two hypotheses still open or supported")
            for h in a.hypotheses:
                if h.status in ("weakened", "ruled_out") and not h.contradicting_evidence:
                    raise ValueError(f"{h.id} is marked {h.status} without contradicting evidence; cite it or "
                                     "leave the hypothesis open")
        self.diagnosis = a.model_dump()
        self.board = [by[h].model_dump() for h in HYPOTHESES]
        return ToolOutcome(True, "submit_diagnosis", raw, {"accepted": True}, terminal=True)
