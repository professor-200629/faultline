"""Run lifecycle and the capability boundary between judge, agent and evaluator.

* The JUDGE side (create sealed runs, reveal) handles `CaseConfig` and seeds.
* The AGENT side receives only a `ToolExecutor` wrapping an `InstrumentPanel`,
  a public context dict and a public `Recorder`.
* The EVALUATOR runs only after a run is terminal.

Run IDs are random hex with no meaning. Hidden configuration is stored in the
sealed table and never copied into public run records or events.
"""

from __future__ import annotations

import asyncio
import logging
import random
import secrets
import time
from dataclasses import asdict, dataclass, field
from typing import Optional

from .agent.baseline import ReferenceProcedure
from .agent.loop import Budgets, Counters, Recorder, prices_known, run_investigation
from .agent.provider import ChatProvider, NebiusProvider, ProviderError
from .agent.tools import ToolExecutor
from .analysis import evaluate_alarms, window_summary
from .config import Settings, api_key
from .instruments import InstrumentPanel
from .judge.evaluator import grade, verify_remedy
from .judge.identifiability import identifiability, window_deviation
from .sim.case import CaseConfig
from .sim.plant import WINDOW_START_S
from .sim.presets import SITUATION, build_preset
from .sim.spec import NOMINAL
from .sim.twins import all_pairs
from .store import TERMINAL, SealedStore, Store

log = logging.getLogger("faultline")
SIM_VERSION = "sim-v1"
PENDING_REMEDIES = ("replace_or_repair_pump", "repair_tank_leak", "replace_level_sensor")


class RunError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def new_run_id() -> str:
    return secrets.token_hex(8)


def public_context(panel: InstrumentPanel, situation: str) -> dict:
    window = panel.historian(WINDOW_START_S, 0.0)
    alarms = evaluate_alarms(window)
    return {
        "warning": alarms or [{"tag": "OPS", "text": "Operator asked for a check of T-101 behaviour"}],
        "situation": situation,
        "site": panel.site.public_dict(),
        "nominal": NOMINAL.public_dict(),
        "now_s": panel.now_s,
    }


@dataclass
class Runtime:
    panel: InstrumentPanel
    executor: ToolExecutor
    task: Optional[asyncio.Task] = None
    cancel: asyncio.Event = field(default_factory=asyncio.Event)


class StoreRecorder:
    def __init__(self, store: Store, run_id: str, max_spend: float):
        self.store, self.run_id, self.max_spend = store, run_id, max_spend

    def event(self, type_: str, payload: dict) -> None:
        self.store.add_event(self.run_id, type_, payload)

    def model_call(self, record: dict) -> None:
        self.store.add_model_call(self.run_id, record)

    def spend_allowed(self, estimated_usd: float) -> bool:
        return self.store.total_spend() + estimated_usd <= self.max_spend

    def add_spend(self, usd: float) -> None:
        self.store.add_spend(self.run_id, usd)


class RunManager:
    def __init__(self, store: Store, sealed: SealedStore, settings: Settings) -> None:
        self.store = store
        self._sealed = sealed
        self.settings = settings
        self._runtimes: dict[str, Runtime] = {}
        self._challenges: dict[str, dict] = {}
        self._revealed_cache: dict[str, dict] = {}
        self._rng = random.SystemRandom()
        for r in store.list_runs(10_000):
            if r["status"] == "investigating":
                store.update_run(r["id"], status="failed", status_reason="server restarted during the investigation")

    def __repr__(self) -> str:
        return "RunManager(<redacted>)"

    def budgets(self) -> Budgets:
        s = self.settings
        return Budgets(max_tool_calls=s.max_tool_calls, max_model_calls=s.max_model_calls, wall_clock_s=s.wall_clock_s,
                       request_timeout_s=s.request_timeout_s, max_retries=s.max_retries,
                       max_output_tokens=s.max_output_tokens, price_in_per_m=s.price_in_per_m,
                       price_out_per_m=s.price_out_per_m)

    # ================= judge side =================
    def create_sealed_run(self, case: CaseConfig, kind: str, situation: str, label: str, extra: Optional[dict] = None,
                          seed: Optional[int] = None) -> str:
        run_id = new_run_id()
        seed = self._rng.randrange(1, 2**31) if seed is None else seed
        panel = InstrumentPanel(case, seed)
        self._runtimes[run_id] = Runtime(panel=panel, executor=ToolExecutor(panel))
        self._sealed.put_truth(run_id, {"case": case.to_private_dict(), "seed": seed, "label": label,
                                        "kind": kind, **(extra or {})})
        self.store.create_run(run_id, kind=kind, mode="unstarted", public=public_context(panel, situation),
                              budgets=asdict(self.budgets()), provider={})
        self.store.add_event(run_id, "created", {"kind": kind, "note": "sealed case created; agent has not started"})
        return run_id

    def create_blind_run(self, family: str, severity: str, site_profile: str) -> str:
        case = build_preset(family, severity, site_profile)
        return self.create_sealed_run(case, "blind", SITUATION, f"{family} / {severity}",
                                      {"preset": {"family": family, "severity": severity, "site_profile": site_profile}})

    def create_guided_run(self) -> str:
        """Teaching example: one of the four twin members (drawn at random), every instrument available.

        Its truth is chosen by the app (not a judge) and, because it is a teaching
        example, it may be revealed without a judge session once terminal.
        """
        pairs = all_pairs()
        options = [(pid, i) for pid in ("flat-reading", "falling-level") for i in (0, 1)]
        pid, i = self._rng.choice(options)
        pair = pairs[pid]
        return self.create_sealed_run(pair.members[i], "guided", pair.situation, pair.member_labels[i],
                                      {"guided": True})

    def create_twin_challenge(self, pair_id: str, site_profile: str = "standard") -> dict:
        from .sim.presets import SITE_PROFILES

        pairs = all_pairs()
        if pair_id not in pairs:
            raise RunError("unknown twin pair", 404)
        site = SITE_PROFILES.get(site_profile)
        if site is None:
            raise RunError("unknown site profile", 400)
        from dataclasses import replace

        pair = pairs[pair_id]
        members = [replace(m, site=site) for m in pair.members]
        order = [0, 1]
        self._rng.shuffle(order)
        cid = new_run_id()
        slots = {"alpha": order[0], "beta": order[1]}
        cards = []
        for slot, idx in slots.items():
            preview_seed = self._rng.randrange(1, 2**31)
            p = InstrumentPanel(members[idx], preview_seed)
            w = p.historian(WINDOW_START_S, 0.0)
            cards.append({"slot": slot, "samples": w, "summary": window_summary(w), "alarms": evaluate_alarms(w)})
        dev = window_deviation(members[0], members[1])
        self._challenges[cid] = {"pair_id": pair_id, "slots": slots, "members": members, "site_profile": site_profile,
                                 "labels": pair.member_labels, "created": time.time(), "used": False}
        return {
            "challenge_id": cid, "pair_id": pair_id, "title": pair.title, "situation": pair.situation,
            "candidate_causes": sorted({m.fault.family for m in members}),
            "site": site.public_dict(), "cards": cards,
            "match": {"noise_free_max_LT101_difference_mm": round(dev["max_LT101_diff_m"] * 1000, 2),
                      "tolerance_mm": 2.0, "FT102_identical": dev["max_FT102_diff_L_s"] == 0.0,
                      "pump_signals_identical": not dev["pump_command_differs"],
                      "note": "Previews use independent noise seeds; the investigated run uses a fresh seed."},
        }

    def pick_twin(self, cid: str, slot: str) -> str:
        ch = self._challenges.get(cid)
        if not ch:
            raise RunError("unknown or expired twin challenge", 404)
        if ch["used"]:
            raise RunError("this twin challenge has already been used; create a new one", 409)
        if slot == "random":
            slot = self._rng.choice(["alpha", "beta"])
        if slot not in ("alpha", "beta"):
            raise RunError("slot must be alpha, beta or random", 400)
        idx = ch["slots"][slot]
        ch["used"] = True
        pair = all_pairs()[ch["pair_id"]]
        return self.create_sealed_run(
            ch["members"][idx], "twin", pair.situation, ch["labels"][idx],
            {"twin": {"pair_id": ch["pair_id"], "picked_slot": slot,
                      "slot_labels": {s: ch["labels"][i] for s, i in ch["slots"].items()},
                      "challenge_id": cid}})

    # ================= agent side =================
    def provider_for(self, mode: str) -> ChatProvider:
        if mode == "live":
            key = api_key()
            if not key:
                raise RunError("LIVE mode unavailable: NEBIUS_API_KEY is not configured on the server. "
                               "No scripted substitute is used.", 409)
            if not prices_known(self.budgets()):
                raise RunError(f"LIVE mode refused: no price is configured for {self.settings.model}, so the "
                               "spending ceiling cannot be enforced. Set FAULTLINE_PRICE_IN_PER_M and "
                               "FAULTLINE_PRICE_OUT_PER_M.", 409)
            return NebiusProvider(key, self.settings.base_url, self.settings.model, self.settings.reasoning)
        if mode == "reference":
            return ReferenceProcedure()
        raise RunError("mode must be 'live' or 'reference'", 400)

    def start(self, run_id: str, mode: str) -> None:
        run = self._require(run_id)
        if run["mode"] == "replay":
            raise RunError("replays are recordings and cannot be started", 409)
        if run["status"] != "ready":
            raise RunError(f"run is {run['status']}; only a ready run can start", 409)
        rt = self._runtimes.get(run_id)
        if rt is None:
            raise RunError("run state is not loaded (server restarted before it started); create a new run", 409)
        provider = self.provider_for(mode)
        self.store.update_run(run_id, status="investigating", mode=mode,
                              provider_json={"name": provider.name, "model": provider.model, "label": provider.label,
                                        "base_url": getattr(provider, "base_url", None)})
        self.store.add_event(run_id, "status", {"status": "investigating", "mode": mode, "provider": provider.name,
                                                "model": provider.model, "label": provider.label})
        rt.task = asyncio.create_task(self._run(run_id, rt, provider))

    async def _run(self, run_id: str, rt: Runtime, provider: ChatProvider) -> None:
        rec = StoreRecorder(self.store, run_id, self.settings.max_spend_usd)
        run = self.store.get_run(run_id)
        live_counters = Counters()
        try:
            res = await run_investigation(rt.executor, provider, run["public"], self.budgets(), rec, rt.cancel,
                                          counters=live_counters)
            status, reason = res.status, res.reason
            counters = asdict(res.counters)
            versions = {**res.versions, "sim": SIM_VERSION}
        except asyncio.CancelledError:
            status, reason = "cancelled", "cancelled by user"
            counters, versions = asdict(live_counters), {"sim": SIM_VERSION}
        except Exception as e:  # never leak internals: record the type only
            log.exception("investigation crashed for run %s", run_id)
            status, reason, counters, versions = "failed", f"internal error ({type(e).__name__})", {}, {}
        ex = rt.executor
        diag = ex.diagnosis
        if status == "diagnosed" and diag and diag.get("recommended_remedy") in PENDING_REMEDIES:
            status_to_store = "awaiting_approval"
        else:
            status_to_store = status
        self.store.update_run(run_id, status=status_to_store, status_reason=reason, counters_json=counters,
                              diagnosis_json=diag, board_json=ex.board,
                              evidence_json=[e.public() for e in ex.evidence], predictions_json=ex.predictions,
                              versions_json=versions)
        self.store.add_event(run_id, "status", {"status": status_to_store, "reason": reason})

    def cancel(self, run_id: str) -> None:
        run = self._require(run_id)
        rt = self._runtimes.get(run_id)
        if run["status"] == "ready":
            self.store.update_run(run_id, status="cancelled", status_reason="cancelled before start")
            self.store.add_event(run_id, "status", {"status": "cancelled", "reason": "cancelled before start"})
            return
        if run["status"] != "investigating" or not rt:
            raise RunError(f"run is {run['status']}; nothing to cancel", 409)
        rt.cancel.set()
        if rt.task:
            rt.task.cancel()

    def decide_remedy(self, run_id: str, approve: bool) -> dict:
        run = self._require(run_id)
        if run["status"] != "awaiting_approval":
            raise RunError("no simulated maintenance action is awaiting approval", 409)
        rt = self._runtimes.get(run_id) or self._rebuild(run_id)
        remedy = (run["diagnosis"] or {}).get("recommended_remedy")
        if not approve:
            result = {"approved": False, "remedy": remedy, "note": "Technician declined; no simulated maintenance applied."}
            reason = "diagnosis submitted; simulated maintenance declined"
        else:
            truth = self._sealed.get_truth(run_id)
            check = verify_remedy(rt.panel._private_plant(), remedy, truth["case"]["fault"]["family"])
            self._sealed.put_remedy_check(run_id, check)  # true-plant numbers stay sealed until reveal
            obs = rt.panel.post_maintenance_observation(300.0)
            result = {"approved": True, "remedy": remedy, "maintenance_action": check["maintenance_action"],
                      "post_maintenance_observation": obs,
                      "independent_check": "Done by the evaluator on the true plant; sealed until the judge reveals "
                                           "this run."}
            reason = "diagnosis submitted; simulated maintenance applied"
        self.store.update_run(run_id, status="diagnosed", remedy_json=result, status_reason=reason)
        self.store.add_event(run_id, "remedy", result)
        self.store.add_event(run_id, "status", {"status": "diagnosed"})
        return result

    def _rebuild(self, run_id: str) -> Runtime:
        """Reconstruct a run's plant deterministically from its seed and public action log."""
        truth = self._sealed.get_truth(run_id)
        case = CaseConfig.from_private_dict(truth["case"])
        panel = InstrumentPanel(case, truth["seed"])
        ex = ToolExecutor(panel)
        for e in self.store.events(run_id):
            if e["type"] == "tool_call":
                ex.execute(e["payload"]["name"], e["payload"]["args"])
        rt = Runtime(panel=panel, executor=ex)
        self._runtimes[run_id] = rt
        return rt

    # ================= replays =================
    def public_telemetry(self, run_id: str) -> list[dict]:
        run = self._require(run_id)
        if run["mode"] == "replay":
            return (self.store.get_replay(run_id) or {}).get("telemetry") or []
        rt = self._runtimes.get(run_id) or self._rebuild(run_id)
        return rt.panel.historian(WINDOW_START_S)

    def import_replay(self, bundle: dict, source_name: str) -> str:
        """Store a recorded evidence bundle as a REPLAY run. It can be watched, never resumed."""
        if bundle.get("format") != "faultline-evidence-v1":
            raise RunError("not a FAULTLINE evidence bundle", 400)
        src = bundle["run"]
        if src.get("status") not in TERMINAL:
            raise RunError("only terminal runs can be replayed", 400)
        run_id = new_run_id()
        self.store.create_run(run_id, kind=src.get("kind", "blind"), mode="replay", public=bundle["context"],
                              budgets=src.get("budgets") or {}, provider=src.get("provider") or {},
                              replay_of=src.get("id"))
        self.store.put_replay(run_id, source_name, bundle)
        for e in bundle.get("timeline", []):
            self.store.add_event(run_id, e["type"], e["payload"])
        self.store.update_run(run_id, status=src["status"], status_reason=src.get("status_reason") or "",
                              counters_json=src.get("counters") or {}, diagnosis_json=bundle.get("diagnosis"),
                              board_json=bundle.get("hypothesis_board"), evidence_json=bundle.get("evidence") or [],
                              predictions_json=bundle.get("predictions") or [], remedy_json=bundle.get("remedy"),
                              versions_json={**(src.get("versions") or {}), "recorded_at": src.get("created_at"),
                                             "recorded_mode": src.get("mode")},
                              revealed=1 if bundle.get("judge_reveal") else 0)
        return run_id

    # ================= evaluator / reveal =================
    def _compute_reveal(self, run_id: str, run: dict) -> dict:
        truth = self._sealed.get_truth(run_id)
        case = CaseConfig.from_private_dict(truth["case"])
        ident = identifiability(case)
        viable = [a["family"] for a in ident["alternatives"] if a["viable"]]
        g = grade(case.fault.family, ident["identifiable"], run["status"], run["diagnosis"], viable)
        self._sealed.put_grade(run_id, g)
        rt = self._runtimes.get(run_id) or self._rebuild(run_id)
        return {
            "fault_family": case.fault.family,
            "label": truth["label"],
            "hidden_parameters": {k: v for k, v in truth["case"]["fault"].items() if k != "family"},
            "initial_true_level_m": case.initial_level_m,
            "model_mismatch": truth["case"].get("mismatch"),
            "grade": g,
            "identifiability": ident,
            "twin": truth.get("twin"),
            "remedy_check": self._sealed.get_remedy_check(run_id),
            "true_state_trace": rt.panel._private_plant().truth_log,
        }

    def reveal(self, run_id: str) -> dict:
        run = self._require(run_id)
        if run["mode"] == "replay":
            raise RunError("a replay shows only what was revealed when it was recorded", 409)
        if run["status"] not in TERMINAL:
            raise RunError("ground truth is revealed only after the investigation is terminal", 409)
        if run_id not in self._revealed_cache:
            self._revealed_cache[run_id] = self._compute_reveal(run_id, run)
        if not run["revealed"]:
            self.store.update_run(run_id, revealed=1)
            self.store.add_event(run_id, "revealed", {"note": "ground truth revealed to the judge"})
        return self._revealed_cache[run_id]

    def revealed_payload(self, run_id: str) -> Optional[dict]:
        run = self._require(run_id)
        if not run["revealed"]:
            return None
        if run["mode"] == "replay":
            jr = (self.store.get_replay(run_id) or {}).get("judge_reveal")
            return {k: v for k, v in jr.items() if k != "section"} if jr else None
        if run_id not in self._revealed_cache:
            self._revealed_cache[run_id] = self._compute_reveal(run_id, run)
        return self._revealed_cache[run_id]

    def _require(self, run_id: str) -> dict:
        run = self.store.get_run(run_id)
        if not run:
            raise RunError("unknown run", 404)
        return run
