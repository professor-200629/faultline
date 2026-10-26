"""Evaluation harness: A (reference procedure), B (one-shot model), C (Faultline agent).

Examples (from the repo root):
  .venv\\Scripts\\python eval\\run_eval.py --set heldout-v2 --arm A --tag heldout-v2-A
  .venv\\Scripts\\python eval\\run_eval.py --set dev-v2 --arm C --ids D-falling-level-0-standard --tag smoke-C1
  .venv\\Scripts\\python eval\\run_eval.py --set heldout-v2 --arm C --tag heldout-v2-C --max-spend 3.00
  .venv\\Scripts\\python eval\\run_eval.py --set heldout-v2 --arm C --ids V04,V15,V19 --repeat 3 --tag variability-C

A and C use the same tools, observations (same seed per scenario), budgets and
evaluator. B sees only the alarm window and is an ablation with less
information. Arms B and C call Nemotron on Nebius Token Factory and need
NEBIUS_API_KEY; spend is tracked in eval/results/spend-ledger.jsonl and a hard
ceiling stops new model calls when it would be exceeded. Raw records are kept
per run; existing result folders are never overwritten.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from faultline.agent.baseline import ReferenceProcedure  # noqa: E402
from faultline.agent.loop import Budgets, NullRecorder, prices_known, run_investigation, run_oneshot  # noqa: E402
from faultline.agent.provider import NebiusProvider  # noqa: E402
from faultline.agent.tools import ToolExecutor  # noqa: E402
from faultline.config import PRICE_SOURCE, api_key, load_settings  # noqa: E402
from faultline.instruments import InstrumentPanel  # noqa: E402
from faultline.judge.evaluator import CORRECT_REMEDY, grade, verify_remedy  # noqa: E402
from faultline.runtime import public_context  # noqa: E402
from faultline.sim.case import CaseConfig  # noqa: E402
from faultline.sim.presets import SITUATION  # noqa: E402

RESULTS = ROOT / "eval" / "results"
LEDGER = RESULTS / "spend-ledger.jsonl"  # append-only; the total is re-read before every check


class Ledger:
    """Cumulative spend across eval processes. Each check re-reads the file under a lock."""

    def __init__(self, ceiling: float, path: Path = LEDGER) -> None:
        self.ceiling = ceiling
        self.path = path
        self.lock = path.with_suffix(".lock")

    def _locked(self):
        import contextlib
        import os

        @contextlib.contextmanager
        def cm():
            self.path.parent.mkdir(parents=True, exist_ok=True)
            deadline = time.time() + 10
            while True:
                try:
                    fd = os.open(str(self.lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                    break
                except FileExistsError:
                    if time.time() > deadline:
                        raise SystemExit(f"spend ledger lock {self.lock} held for 10 s; remove it if stale")
                    time.sleep(0.05)
            try:
                yield
            finally:
                os.close(fd)
                os.remove(str(self.lock))
        return cm()

    def total(self) -> float:
        if not self.path.exists():
            return 0.0
        return round(sum(json.loads(line)["usd"] for line in self.path.read_text().splitlines() if line.strip()), 6)

    def allowed(self, est: float) -> bool:
        with self._locked():
            return self.total() + est <= self.ceiling

    def add(self, usd: float, tag: str) -> None:
        with self._locked():
            with open(self.path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps({"at": time.time(), "tag": tag, "usd": round(usd, 8)}) + "\n")


class EvalRecorder(NullRecorder):
    def __init__(self, ledger: Ledger, tag: str) -> None:
        super().__init__()
        self.ledger, self.tag = ledger, tag

    def spend_allowed(self, est: float) -> bool:
        return self.ledger.allowed(est)

    def add_spend(self, usd: float) -> None:
        self.ledger.add(usd, self.tag)


def provider_for(arm: str, settings):
    if arm == "A":
        return ReferenceProcedure()
    key = api_key()
    if not key:
        raise SystemExit("Arms B and C need NEBIUS_API_KEY (run scripts\\set-nebius-key.ps1). Nothing was run.")
    if not (settings.price_in_per_m == settings.price_in_per_m and settings.price_out_per_m == settings.price_out_per_m):
        raise SystemExit(f"No price configured for {settings.model}; set FAULTLINE_PRICE_IN_PER_M/OUT_PER_M. "
                         "Nothing was run (the spending ceiling cannot be enforced without a price).")
    return NebiusProvider(key, settings.base_url, settings.model, settings.reasoning)


async def run_one(sc: dict, arm: str, rep: int, budgets: Budgets, settings, ledger: Ledger, tag: str) -> dict:
    case = CaseConfig.from_private_dict(sc["case"])
    panel = InstrumentPanel(case, sc["seed"])  # same observations for every arm and repeat
    ex = ToolExecutor(panel)
    ctx = public_context(panel, SITUATION)
    rec = EvalRecorder(ledger, tag)
    prov = provider_for(arm, settings)
    t0 = time.time()
    if arm == "B":
        res = await run_oneshot(ex, prov, ctx, budgets, rec)
    else:
        res = await run_investigation(ex, prov, ctx, budgets, rec)
    g = grade(sc["truth_family"], sc["identifiable"], res.status, res.diagnosis, sc.get("viable_alternatives"))
    remedy_check = None
    d = res.diagnosis or {}
    if res.status == "diagnosed" and d.get("recommended_remedy") in CORRECT_REMEDY.values():
        remedy_check = verify_remedy(panel._private_plant(), d["recommended_remedy"], sc["truth_family"])
    return {
        "scenario": sc["id"], "arm": arm, "rep": rep, "seed": sc["seed"], "tags": sc["tags"],
        "truth_family": sc["truth_family"], "identifiable": sc["identifiable"],
        "status": res.status, "reason": res.reason, "diagnosis": res.diagnosis, "grade": g,
        "remedy_check": remedy_check, "counters": asdict(res.counters), "model": res.model, "provider": res.provider,
        "versions": res.versions, "evidence": [e.public() for e in ex.evidence], "predictions": ex.predictions,
        "board": ex.board, "events": [{"type": t, "payload": p} for t, p in rec.events], "model_calls": rec.calls,
        "started_at": t0, "wall_s": round(time.time() - t0, 2),
    }


def summarise(records: list[dict], arm: str) -> dict:
    n = len(records)
    ident = [r for r in records if r["identifiable"]]
    unid = [r for r in records if not r["identifiable"]]
    cat = lambda rs, c: sum(1 for r in rs if r["grade"]["category"] == c)  # noqa: E731
    meas = [len([e for e in r["evidence"] if e["kind"] != "historian_window"]) for r in records]
    tests = [r["counters"]["tool_calls"] for r in records]
    return {
        "arm": arm, "runs": n,
        "identifiable_runs": len(ident), "unidentifiable_runs": len(unid),
        "correct_diagnoses": cat(ident, "correct_diagnosis"),
        "wrong_diagnoses": cat(records, "wrong_diagnosis"),
        "wrong_confident": sum(1 for r in records if r["grade"].get("confident_wrong")),
        "appropriate_inconclusive": cat(unid, "appropriate_inconclusive"),
        "wrong_inconclusive": cat(records, "wrong_inconclusive"),
        "unnecessary_inconclusive": cat(ident, "unnecessary_inconclusive"),
        "unsupported_diagnoses": cat(unid, "unsupported_diagnosis"),
        "no_result": cat(records, "no_result"),
        "remedy_verified": sum(1 for r in records if r["remedy_check"] and r["remedy_check"]["passed"]),
        "remedy_attempted": sum(1 for r in records if r["remedy_check"]),
        "mean_measurements_per_run": round(sum(meas) / n, 2) if n else None,
        "mean_tool_calls_per_run": round(sum(tests) / n, 2) if n else None,
        "mean_wall_s": round(sum(r["wall_s"] for r in records) / n, 2) if n else None,
        "prompt_tokens": sum(r["counters"]["prompt_tokens"] for r in records),
        "completion_tokens": sum(r["counters"]["completion_tokens"] for r in records),
        "reasoning_tokens": sum(r["counters"]["reasoning_tokens"] for r in records),
        "estimated_cost_usd": round(sum(r["counters"]["estimated_cost_usd"] for r in records), 4),
        "provider_failures": sum(r["counters"]["provider_failures"] for r in records),
        "by_tag": {t: {"runs": len(rs), "correct_or_appropriate": sum(1 for r in rs if r["grade"]["correct"])}
                   for t in sorted({t for r in records for t in r["tags"]})
                   for rs in [[r for r in records if t in r["tags"]]]},
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", choices=["heldout-v2", "dev-v2", "heldout-v1", "dev-v1"], default="heldout-v2")
    ap.add_argument("--arm", choices=["A", "B", "C"], required=True)
    ap.add_argument("--ids", default="")
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--tag", required=True)
    ap.add_argument("--max-spend", type=float, default=None, help="hard USD ceiling across all eval runs (ledger)")
    args = ap.parse_args()
    settings = load_settings()
    ceiling = args.max_spend if args.max_spend is not None else settings.max_spend_usd
    out_dir = RESULTS / args.tag
    if out_dir.exists():
        raise SystemExit(f"{out_dir} exists; choose a new --tag (results are never overwritten)")
    doc = json.loads((ROOT / "eval" / "scenarios" / f"{args.set}.json").read_text(encoding="utf-8"))
    scenarios = doc["scenarios"]
    if args.ids:
        want = set(args.ids.split(","))
        scenarios = [s for s in scenarios if s["id"] in want]
    budgets = Budgets(max_tool_calls=settings.max_tool_calls, max_model_calls=settings.max_model_calls,
                      wall_clock_s=settings.wall_clock_s, request_timeout_s=settings.request_timeout_s,
                      max_retries=settings.max_retries, max_output_tokens=settings.max_output_tokens,
                      price_in_per_m=settings.price_in_per_m, price_out_per_m=settings.price_out_per_m)
    ledger = Ledger(ceiling)
    out_dir.mkdir(parents=True)
    records = []
    for sc in scenarios:
        for rep in range(args.repeat):
            r = asyncio.run(run_one(sc, args.arm, rep, budgets, settings, ledger, args.tag))
            (out_dir / f"{sc['id']}-r{rep}.json").write_text(json.dumps(r, indent=1), encoding="utf-8")
            records.append(r)
            g = r["grade"]
            print(f"{sc['id']:<6} rep{rep} {r['status']:<13} {g['category']:<26} truth={sc['truth_family']:<22} "
                  f"agent={(r['diagnosis'] or {}).get('primary_hypothesis')} tools={r['counters']['tool_calls']} "
                  f"cost=${r['counters']['estimated_cost_usd']:.4f} wall={r['wall_s']}s", flush=True)
    summ = summarise(records, args.arm)
    summ.update({"set": args.set, "tag": args.tag, "model": records[0]["model"] if records else None,
                 "repeat": args.repeat, "budgets": asdict(budgets), "price_source": PRICE_SOURCE,
                 "scenario_file_sha256": __import__("hashlib").sha256(
                     (ROOT / "eval" / "scenarios" / f"{args.set}.json").read_bytes()).hexdigest(),
                 "spend_ledger_total_usd": ledger.total(), "finished_at": time.time()})
    (out_dir / "summary.json").write_text(json.dumps(summ, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in summ.items() if k not in ("by_tag", "budgets")}, indent=1))


if __name__ == "__main__":
    main()
