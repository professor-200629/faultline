"""Bounded agent loop: budgets, forced final submission, retries, cancellation, spend ceiling."""

import asyncio
import json

import pytest

from faultline.agent.loop import Budgets, NullRecorder, run_investigation
from faultline.agent.provider import ProviderError, ScriptedProvider, tool_call
from faultline.agent.tools import ToolExecutor
from faultline.instruments import InstrumentPanel
from faultline.runtime import public_context
from faultline.sim.twins import falling_level_pair

READ = tool_call("read_observations", {"scope": "alarm_window", "purpose": "establish the balance"})
INLET = tool_call("measure_inlet_flow", {"duration_s": 60, "purpose": "pump vs leak"})


def board(primary):
    return [{"id": h, "status": "supported" if h == primary else "ruled_out",
             "supporting_evidence": ["E2"] if h == primary else [], "contradicting_evidence": [] if h == primary else ["E1", "E2"]}
            for h in ("no_fault", "pump_delivery_reduced", "tank_leak", "level_sensor_stuck")]


SUBMIT = tool_call("submit_diagnosis", {"outcome": "diagnosed", "primary_hypothesis": "pump_delivery_reduced",
                                        "hypotheses": board("pump_delivery_reduced"), "confidence": "medium",
                                        "summary": "E2 shows 0.76 L/s delivered vs 1.20 rated; closes E1 balance.",
                                        "recommended_remedy": "replace_or_repair_pump"})


def setup(member=0, seed=3):
    panel = InstrumentPanel(falling_level_pair().members[member], seed)
    return ToolExecutor(panel), public_context(panel, "test")


def run(script, budgets=Budgets(), recorder=None, cancel=None, member=0):
    ex, ctx = setup(member)
    prov = ScriptedProvider(script)
    rec = recorder or NullRecorder()
    res = asyncio.run(run_investigation(ex, prov, ctx, budgets, rec, cancel))
    return res, prov, rec, ex


def test_happy_path_diagnosis_with_real_measurements():
    res, prov, rec, ex = run([{"tool_calls": [READ]}, {"tool_calls": [INLET]}, {"tool_calls": [SUBMIT]}])
    assert res.status == "diagnosed"
    assert res.counters.tool_calls == 3 and res.counters.model_calls == 3
    assert [e.eid for e in ex.evidence] == ["E1", "E2"]
    assert ex.evidence[1].data["mean_inlet_flow_L_s"] == pytest.approx(0.75, abs=0.08)  # simulator value, not scripted
    tool_msgs = [m for m in prov.requests[-1]["messages"] if m["role"] == "tool"]
    assert all("budget_remaining" in json.loads(m["content"]) for m in tool_msgs)


def test_reply_without_tool_call_is_nudged_and_charged():
    res, prov, rec, _ = run([{"content": "thinking aloud"}, {"tool_calls": [READ]}, {"tool_calls": [INLET]},
                             {"tool_calls": [SUBMIT]}])
    assert any(t == "nudge" for t, _ in rec.events)
    assert res.counters.model_calls == 4 and res.status == "diagnosed"


def test_rejected_calls_are_charged_and_last_turn_forces_submit():
    script = [{"tool_calls": [READ]}, {"tool_calls": [tool_call("measure_inlet_flow", {"duration_s": 1, "purpose": "bad"})]},
              {"tool_calls": [SUBMIT]}]
    res, prov, rec, _ = run(script, Budgets(max_tool_calls=3))
    assert res.counters.rejected_tool_calls >= 1
    final = prov.requests[-1]
    assert final["tool_choice"] == {"type": "function", "function": {"name": "submit_diagnosis"}}
    assert [t["function"]["name"] for t in final["tools"]] == ["submit_diagnosis"]
    assert res.status == "failed"  # the forced submission cites E2, which was never created
    results = [p for t, p in rec.events if t == "tool_result"]
    assert results[1]["ok"] is False and "duration_s" in results[1]["error"]
    assert results[2]["ok"] is False and "unknown evidence id" in results[2]["error"]


def test_a_model_that_never_submits_fails_honestly_within_budget():
    res, prov, rec, _ = run([{"tool_calls": [READ]}] * 5, Budgets(max_tool_calls=2, max_model_calls=5))
    assert res.status == "failed" and "budget" in res.reason
    assert res.counters.tool_calls <= 2


def test_parallel_calls_cannot_consume_the_reserved_submit_slot():
    # finding: [READ, INLET] then [READ, update] used to jump 4 -> 2 -> 0 and skip the forced submit
    upd = tool_call("update_hypotheses", {"hypotheses": [{"id": "tank_leak", "status": "open",
                                                           "supporting_evidence": [], "contradicting_evidence": []}]})
    res, prov, rec, ex = run([{"tool_calls": [READ, INLET]}, {"tool_calls": [READ, upd]}, {"tool_calls": [SUBMIT]}],
                             Budgets(max_tool_calls=4))
    assert res.status == "diagnosed"
    assert prov.requests[-1]["tool_choice"] == {"type": "function", "function": {"name": "submit_diagnosis"}}
    skipped = [p for t, p in rec.events if t == "tool_result" and "reserved" in (p.get("error") or "")]
    assert skipped, "a call that would use the reserved slot must be answered, not executed"


def test_on_the_final_turn_a_submit_after_a_rejected_call_still_counts():
    upd = tool_call("update_hypotheses", {"hypotheses": []})
    res, prov, rec, ex = run([{"tool_calls": [READ]}, {"tool_calls": [INLET]}, {"tool_calls": [upd, SUBMIT]}],
                             Budgets(max_tool_calls=3))
    assert res.status == "diagnosed" and res.counters.tool_calls == 3


def test_final_turn_is_also_forced_when_model_calls_run_out():
    res, prov, *_ = run([{"content": "hm"}, {"tool_calls": [READ]}, {"tool_calls": [INLET]}, {"tool_calls": [SUBMIT]}],
                        Budgets(max_model_calls=4))
    assert prov.requests[-1]["tool_choice"]["function"]["name"] == "submit_diagnosis"
    assert res.status == "diagnosed"


def test_reference_procedure_is_not_blocked_by_the_spending_ceiling():
    from faultline.agent.baseline import ReferenceProcedure

    class Broke(NullRecorder):
        def spend_allowed(self, estimated_usd):
            return False

    ex, ctx = setup()
    res = asyncio.run(run_investigation(ex, ReferenceProcedure(), ctx, Budgets(), Broke()))
    assert res.status == "diagnosed"


def test_unknown_price_fails_closed_for_billable_providers():
    class Billable(ScriptedProvider):
        billable = True

    ex, ctx = setup()
    res = asyncio.run(run_investigation(ex, Billable([{"tool_calls": [READ]}]), ctx,
                                        Budgets(price_in_per_m=float("nan")), NullRecorder()))
    assert res.status == "failed" and "price unknown" in res.reason


def test_cancellation_keeps_the_counters_used_so_far():
    from faultline.agent.loop import Counters

    class SlowSecond(ScriptedProvider):
        async def complete(self, *a, **k):
            if self.requests:
                self.requests.append({})
                await asyncio.sleep(60)
            return await super().complete(*a, **k)

    async def main():
        ex, ctx = setup()
        counters = Counters()
        t = asyncio.create_task(run_investigation(ex, SlowSecond([{"tool_calls": [READ]}]), ctx, Budgets(),
                                                  NullRecorder(), counters=counters))
        await asyncio.sleep(0.2)
        t.cancel()
        with pytest.raises(asyncio.CancelledError):
            await t
        return counters

    c = asyncio.run(main())
    assert c.model_calls == 2 and c.tool_calls == 1


def test_oneshot_never_executes_measurement_tools():
    from faultline.agent.loop import run_oneshot

    ex, ctx = setup()
    prov = ScriptedProvider([{"tool_calls": [INLET]}, {"tool_calls": [INLET]}, {"tool_calls": [INLET]}])
    res = asyncio.run(run_oneshot(ex, prov, ctx, Budgets(), NullRecorder()))
    assert res.status == "failed"
    assert [e.eid for e in ex.evidence] == ["E1"] and ex.panel.now_s == 0  # no measurement, no simulated time


def test_oneshot_respects_the_spending_ceiling():
    from faultline.agent.loop import run_oneshot

    class Billable(ScriptedProvider):
        billable = True

    class Broke(NullRecorder):
        def spend_allowed(self, estimated_usd):
            return False

    ex, ctx = setup()
    prov = Billable([{"tool_calls": [SUBMIT]}])
    res = asyncio.run(run_oneshot(ex, prov, ctx, Budgets(), Broke()))
    assert res.status == "failed" and "spending ceiling" in res.reason and prov.requests == []


def test_retryable_provider_failure_is_retried_and_charged():
    script = [ProviderError("rate_limit", "429", 429, retryable=True), {"tool_calls": [READ]}, {"tool_calls": [INLET]},
              {"tool_calls": [SUBMIT]}]
    res, prov, rec, _ = run(script)
    assert res.status == "diagnosed"
    assert res.counters.provider_failures == 1 and res.counters.model_calls == 4
    errs = [p for t, p in rec.events if t == "provider_error"]
    assert errs and errs[0]["kind"] == "rate_limit" and errs[0]["will_retry"]


def test_non_retryable_provider_failure_stops_without_substitute():
    res, *_ = run([ProviderError("auth", "Nebius rejected the API key (401)", 401)])
    assert res.status == "failed" and "auth" in res.reason


def test_cancel_event_stops_before_next_model_call():
    cancel = asyncio.Event()
    cancel.set()
    res, prov, *_ = run([{"tool_calls": [READ]}], cancel=cancel)
    assert res.status == "cancelled" and prov.requests == []


def test_task_cancellation_interrupts_a_pending_model_call():
    class Hang(ScriptedProvider):
        async def complete(self, *a, **k):
            await asyncio.sleep(60)

    async def main():
        ex, ctx = setup()
        t = asyncio.create_task(run_investigation(ex, Hang([]), ctx, Budgets(), NullRecorder()))
        await asyncio.sleep(0.05)
        t.cancel()
        with pytest.raises(asyncio.CancelledError):
            await t

    asyncio.run(main())


def test_wall_clock_budget_is_enforced():
    res, prov, *_ = run([{"tool_calls": [READ]}], Budgets(wall_clock_s=2.0))
    assert res.status == "failed" and "wall-clock" in res.reason and prov.requests == []


def test_spending_ceiling_stops_before_the_call():
    class Broke(NullRecorder):
        def spend_allowed(self, estimated_usd):
            return False

    class Billable(ScriptedProvider):
        billable = True

    ex, ctx = setup()
    prov = Billable([{"tool_calls": [READ]}])
    res = asyncio.run(run_investigation(ex, prov, ctx, Budgets(), Broke()))
    assert res.status == "failed" and "spending ceiling" in res.reason and prov.requests == []


def test_parallel_tool_calls_each_get_a_result_message():
    res, prov, rec, ex = run([{"tool_calls": [READ, INLET]}, {"tool_calls": [SUBMIT]}])
    assert res.status == "diagnosed"
    msgs = prov.requests[-1]["messages"]
    ids = {m["tool_call_id"] for m in msgs if m["role"] == "tool"}
    assert {READ["id"], INLET["id"]} <= ids
