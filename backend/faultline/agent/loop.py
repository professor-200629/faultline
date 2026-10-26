"""The bounded investigation loop: one agent, structured tool calls, finite budgets.

The loop never sees the plant. It passes model tool calls to `ToolExecutor`,
which validates them in backend code. Every provider attempt (including
retries and nudges) is charged to the model-call and wall-clock budgets.

Budget rules:
  * one tool-call slot is always kept for `submit_diagnosis`; extra calls in a
    reply that would consume it are answered "not executed" and not charged;
  * the final turn (one tool call or one model call left) offers only
    `submit_diagnosis` and names it in `tool_choice`;
  * billable providers are checked against the spending ceiling before every
    attempt; an unknown price fails closed.
"""

from __future__ import annotations

import asyncio
import json
import math
import time
from dataclasses import asdict, dataclass, field
from typing import Optional, Protocol

from .prompts import FINAL_NUDGE, NUDGE, PROMPT_VERSION, SYSTEM_PROMPT, initial_user_message
from .provider import ChatProvider, ProviderError
from .tools import TOOL_VERSION, ToolExecutor

SUBMIT = "submit_diagnosis"


@dataclass(frozen=True)
class Budgets:
    max_tool_calls: int = 12
    max_model_calls: int = 16
    wall_clock_s: float = 120.0
    request_timeout_s: float = 60.0
    max_retries: int = 2
    max_output_tokens: int = 4096
    price_in_per_m: float = 0.30
    price_out_per_m: float = 0.90


@dataclass
class Counters:
    tool_calls: int = 0
    model_calls: int = 0
    provider_failures: int = 0
    rejected_tool_calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    reasoning_tokens: int = 0
    usage_reported_calls: int = 0
    estimated_cost_usd: float = 0.0
    elapsed_s: float = 0.0


@dataclass
class AgentResult:
    status: str  # diagnosed | inconclusive | failed | cancelled
    reason: str
    counters: Counters
    model: str
    provider: str
    diagnosis: Optional[dict] = None
    versions: dict = field(default_factory=dict)


class Recorder(Protocol):
    def event(self, type_: str, payload: dict) -> None: ...
    def model_call(self, record: dict) -> None: ...
    def spend_allowed(self, estimated_usd: float) -> bool: ...
    def add_spend(self, usd: float) -> None: ...


class NullRecorder:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []
        self.calls: list[dict] = []

    def event(self, type_, payload):
        self.events.append((type_, payload))

    def model_call(self, record):
        self.calls.append(record)

    def spend_allowed(self, estimated_usd):
        return True

    def add_spend(self, usd):
        pass


def prices_known(b: Budgets) -> bool:
    return not (math.isnan(b.price_in_per_m) or math.isnan(b.price_out_per_m))


def _budget_view(b: Budgets, c: Counters, ex: ToolExecutor, started: float) -> dict:
    return {
        "tool_calls_remaining": max(0, b.max_tool_calls - c.tool_calls),
        "model_calls_remaining": max(0, b.max_model_calls - c.model_calls),
        "wall_clock_remaining_s": round(max(0.0, b.wall_clock_s - (time.monotonic() - started)), 1),
        "simulated_time_remaining_s": ex.panel.time.remaining_s,
    }


class _Meter:
    """Usage, cost and the spending gate shared by both loops."""

    def __init__(self, provider: ChatProvider, budgets: Budgets, recorder: Recorder, c: Counters) -> None:
        self.provider, self.b, self.rec, self.c = provider, budgets, recorder, c
        self.billable = getattr(provider, "billable", True)
        self.last_prompt_tokens = 0

    def gate(self) -> Optional[str]:
        """Reason to refuse the next model call, or None."""
        if not self.billable:
            return None
        if not prices_known(self.b):
            return "model price unknown: set FAULTLINE_PRICE_IN_PER_M and FAULTLINE_PRICE_OUT_PER_M (fails closed)"
        est_prompt = (self.last_prompt_tokens or 3000) + 2500
        est = est_prompt * self.b.price_in_per_m / 1e6 + self.b.max_output_tokens * self.b.price_out_per_m / 1e6
        if not self.rec.spend_allowed(est):
            return "spending ceiling reached (FAULTLINE_MAX_SPEND_USD)"
        return None

    def account(self, usage: dict) -> None:
        pt, ct = int(usage.get("prompt_tokens") or 0), int(usage.get("completion_tokens") or 0)
        if usage.get("prompt_tokens") is not None:
            self.c.usage_reported_calls += 1
        self.c.prompt_tokens += pt
        self.c.completion_tokens += ct
        self.c.reasoning_tokens += int(usage.get("reasoning_tokens") or 0)
        self.last_prompt_tokens = pt or self.last_prompt_tokens
        if self.billable and prices_known(self.b):
            cost = pt * self.b.price_in_per_m / 1e6 + ct * self.b.price_out_per_m / 1e6
            self.c.estimated_cost_usd = round(self.c.estimated_cost_usd + cost, 6)
            self.rec.add_spend(cost)


def _tool_msg(call_id: str, name: str, payload: dict) -> dict:
    return {"role": "tool", "tool_call_id": call_id, "name": name, "content": json.dumps(payload)}


ONESHOT_NOTE = ("ONE-SHOT ABLATION: you cannot take measurements or run tests. Decide from the alarm-window "
                "observations below (evidence E1) and call submit_diagnosis now.")


async def run_oneshot(
    executor: ToolExecutor,
    provider: ChatProvider,
    public_context: dict,
    budgets: Budgets,
    recorder: Recorder,
    counters: Optional[Counters] = None,
) -> AgentResult:
    """Comparator B: the model sees only the alarm window and must submit at once.

    It has less information than the agent by design; it is an ablation, not a
    fair comparison of investigators. Up to two corrections are allowed if the
    backend rejects the submission; every attempt is charged. Any tool other
    than submit_diagnosis is refused without being executed.
    """
    versions = {"prompt": PROMPT_VERSION, "tools": TOOL_VERSION, "arm": "oneshot"}
    c = counters if counters is not None else Counters()
    meter = _Meter(provider, budgets, recorder, c)
    started = time.monotonic()
    read = executor.execute("read_observations", {"scope": "alarm_window", "purpose": "one-shot input"})
    recorder.event("tool_result", {"call_id": "oneshot-input", "name": "read_observations", "ok": read.ok,
                                   "evidence_id": read.evidence_id, "summary": executor.evidence[0].summary})
    brief = initial_user_message(dict(public_context), {"max_model_calls": 3})
    messages = [{"role": "system", "content": SYSTEM_PROMPT + "\n" + ONESHOT_NOTE},
                {"role": "user", "content": brief + "\n\nObservations (JSON):\n" + json.dumps(read.result)}]
    tools = executor.specs([SUBMIT])
    choice = {"type": "function", "function": {"name": SUBMIT}}

    def done(status: str, reason: str) -> AgentResult:
        c.elapsed_s = round(time.monotonic() - started, 2)
        return AgentResult(status, reason, c, provider.model, provider.name, executor.diagnosis, versions)

    attempts = 0
    while attempts < 3:
        remaining = budgets.wall_clock_s - (time.monotonic() - started)
        if remaining < 3:
            return done("failed", "wall-clock budget exhausted")
        refused = meter.gate()
        if refused:
            return done("failed", refused)
        attempts += 1
        c.model_calls += 1
        t_req = time.monotonic()
        try:
            res = await provider.complete(messages, tools, choice, budgets.max_output_tokens,
                                          min(budgets.request_timeout_s, remaining))
        except ProviderError as e:
            c.provider_failures += 1
            recorder.event("provider_error", {**e.public(), "attempt": attempts, "will_retry": e.retryable and attempts < 3})
            recorder.model_call({"n": c.model_calls, "ok": False, "error": e.public(),
                                 "latency_ms": int((time.monotonic() - t_req) * 1000)})
            if not e.retryable:
                return done("failed", f"provider failure: {e.kind} - {e}")
            await asyncio.sleep(min(2.0 * attempts, max(0.0, budgets.wall_clock_s - (time.monotonic() - started) - 5)))
            continue
        meter.account(res.usage)
        calls = res.message.get("tool_calls") or []
        recorder.model_call({"n": c.model_calls, "ok": True, "model": res.model, "usage": res.usage,
                             "latency_ms": res.latency_ms, "finish_reason": res.finish_reason,
                             "tool_calls": [tc.get("function") for tc in calls],
                             "content": (res.message.get("content") or "")[:2000]})
        messages.append({"role": "assistant", "content": res.message.get("content") or "",
                         **({"tool_calls": calls} if calls else {})})
        if not calls:
            messages.append({"role": "user", "content": "Call submit_diagnosis."})
            continue
        for tc in calls:
            fn = tc.get("function") or {}
            name, call_id = fn.get("name", ""), tc.get("id") or f"oneshot-{attempts}"
            if name != SUBMIT:
                c.rejected_tool_calls += 1
                recorder.event("tool_result", {"call_id": call_id, "name": name, "ok": False,
                                               "error": "not executed: the one-shot ablation may only submit"})
                messages.append(_tool_msg(call_id, name, {"error": "not executed: only submit_diagnosis is allowed"}))
                continue
            c.tool_calls += 1
            out = executor.execute(name, fn.get("arguments", "{}"))
            if not out.ok:
                c.rejected_tool_calls += 1
            recorder.event("tool_result", {"call_id": call_id, "name": name, "ok": out.ok,
                                           "error": out.result.get("error") if not out.ok else None})
            messages.append(_tool_msg(call_id, name, out.result))
            if out.terminal:
                return done(executor.diagnosis["outcome"], "one-shot diagnosis submitted")
    return done("failed", "one-shot model did not produce a valid submission")


async def run_investigation(
    executor: ToolExecutor,
    provider: ChatProvider,
    public_context: dict,
    budgets: Budgets,
    recorder: Recorder,
    cancel: Optional[asyncio.Event] = None,
    counters: Optional[Counters] = None,
) -> AgentResult:
    """Comparator C (and the app's LIVE mode); also runs the reference procedure (A).

    `counters` may be passed in so a caller can still read usage if the task is
    cancelled while awaiting the provider.
    """
    cancel = cancel or asyncio.Event()
    c = counters if counters is not None else Counters()
    meter = _Meter(provider, budgets, recorder, c)
    started = time.monotonic()
    versions = {"prompt": PROMPT_VERSION, "tools": TOOL_VERSION}
    messages: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": initial_user_message(public_context, {
            "max_tool_calls": budgets.max_tool_calls, "max_model_calls": budgets.max_model_calls,
            "wall_clock_s": budgets.wall_clock_s,
            "simulated_time_allowance_s": executor.panel.time.limit_s})},
    ]

    def done(status: str, reason: str) -> AgentResult:
        c.elapsed_s = round(time.monotonic() - started, 2)
        recorder.event("budget", {**asdict(c), **_budget_view(budgets, c, executor, started)})
        return AgentResult(status, reason, c, provider.model, provider.name, executor.diagnosis, versions)

    def remaining_wall() -> float:
        return budgets.wall_clock_s - (time.monotonic() - started)

    while True:
        if cancel.is_set():
            return done("cancelled", "cancelled by user")
        if c.tool_calls >= budgets.max_tool_calls:
            return done("failed", "tool-call budget exhausted before a diagnosis was submitted")
        if c.model_calls >= budgets.max_model_calls:
            return done("failed", "model-call budget exhausted before a diagnosis was submitted")
        if remaining_wall() < 3.0:
            return done("failed", "wall-clock budget exhausted before a diagnosis was submitted")

        tools_left = budgets.max_tool_calls - c.tool_calls
        final_turn = tools_left <= 1 or budgets.max_model_calls - c.model_calls <= 1
        tools = executor.specs([SUBMIT] if final_turn else None)
        tool_choice = {"type": "function", "function": {"name": SUBMIT}} if final_turn else "auto"
        if final_turn and not (messages[-1]["role"] == "user" and messages[-1]["content"] == FINAL_NUDGE):
            messages.append({"role": "user", "content": FINAL_NUDGE})

        # ---- one model call, with retries charged to the budget ----
        result = None
        attempt = 0
        while result is None:
            if cancel.is_set():
                return done("cancelled", "cancelled by user")
            if c.model_calls >= budgets.max_model_calls:
                return done("failed", "model-call budget exhausted by provider retries")
            refused = meter.gate()
            if refused:
                return done("failed", refused)
            timeout = min(budgets.request_timeout_s, remaining_wall())
            if timeout < 3.0:
                return done("failed", "wall-clock budget exhausted while waiting for the provider")
            c.model_calls += 1
            attempt += 1
            recorder.event("model_request", {"n": c.model_calls, "attempt": attempt, "forced_submit": final_turn,
                                             "tools_offered": [t["function"]["name"] for t in tools]})
            t_req = time.monotonic()
            try:
                result = await provider.complete(messages, tools, tool_choice, budgets.max_output_tokens, timeout)
            except asyncio.CancelledError:
                c.elapsed_s = round(time.monotonic() - started, 2)
                raise
            except ProviderError as e:
                c.provider_failures += 1
                will_retry = e.retryable and attempt <= budgets.max_retries
                recorder.event("provider_error", {**e.public(), "attempt": attempt, "will_retry": will_retry})
                recorder.model_call({"n": c.model_calls, "ok": False, "error": e.public(),
                                     "latency_ms": int((time.monotonic() - t_req) * 1000)})
                if not will_retry:
                    return done("failed", f"provider failure: {e.kind} - {e}")
                await asyncio.sleep(min(2.0 * attempt, max(0.0, remaining_wall() - 5.0)))

        meter.account(result.usage)
        calls = result.message.get("tool_calls") or []
        content = (result.message.get("content") or "").strip()
        recorder.model_call({"n": c.model_calls, "ok": True, "model": result.model, "latency_ms": result.latency_ms,
                             "usage": result.usage, "finish_reason": result.finish_reason, "meta": result.meta,
                             "tool_calls": [{"name": tc.get("function", {}).get("name"),
                                             "arguments": tc.get("function", {}).get("arguments")} for tc in calls],
                             "content": content[:2000]})
        recorder.event("model_response", {"n": c.model_calls, "latency_ms": result.latency_ms, "usage": result.usage,
                                          "finish_reason": result.finish_reason, "model": result.model,
                                          "note": content[:400],
                                          "tool_calls": [tc.get("function", {}).get("name") for tc in calls]})
        messages.append({"role": "assistant", "content": result.message.get("content") or "",
                         **({"tool_calls": calls} if calls else {})})

        if not calls:
            messages.append({"role": "user", "content": NUDGE})
            recorder.event("nudge", {"text": NUDGE})
            continue

        terminal = False
        for tc in calls:
            call_id = tc.get("id") or f"call-{c.model_calls}-{c.tool_calls + 1}"
            fn = tc.get("function") or {}
            name = fn.get("name", "")
            left = budgets.max_tool_calls - c.tool_calls
            reason = None
            if terminal:
                reason = "investigation already finished"
            elif final_turn and name != SUBMIT:
                reason = "only submit_diagnosis is allowed on the final turn"
            elif name != SUBMIT and left <= 1:
                reason = "the last tool-call slot is reserved for submit_diagnosis"
            elif left <= 0:
                reason = "tool-call budget exhausted"
            if reason:  # answered but not executed and not charged
                recorder.event("tool_result", {"call_id": call_id, "name": name, "ok": False,
                                               "error": f"not executed: {reason}"})
                messages.append(_tool_msg(call_id, name, {"error": f"not executed: {reason}"}))
                continue
            c.tool_calls += 1
            outcome = executor.execute(name, fn.get("arguments", "{}"))
            purpose = outcome.args.get("purpose") if isinstance(outcome.args, dict) else None
            recorder.event("tool_call", {"call_id": call_id, "name": name, "args": outcome.args, "purpose": purpose})
            if not outcome.ok:
                c.rejected_tool_calls += 1
            ev_payload = {"call_id": call_id, "name": name, "ok": outcome.ok, "evidence_id": outcome.evidence_id,
                          "prediction_id": outcome.prediction_id}
            if outcome.ok and outcome.evidence_id:
                ev = next(e for e in executor.evidence if e.eid == outcome.evidence_id)
                ev_payload["summary"] = ev.summary
            elif outcome.ok and outcome.prediction_id:
                ev_payload["prediction"] = outcome.result
            elif not outcome.ok:
                ev_payload["error"] = outcome.result.get("error", outcome.error)
            recorder.event("tool_result", ev_payload)
            if outcome.ok and name in ("update_hypotheses", SUBMIT):
                recorder.event("hypotheses", {"board": executor.board})
            body = dict(outcome.result)
            body["budget_remaining"] = _budget_view(budgets, c, executor, started)
            messages.append(_tool_msg(call_id, name, body))
            if outcome.terminal:
                terminal = True
                recorder.event("diagnosis", executor.diagnosis or {})
        recorder.event("budget", {**asdict(c), **_budget_view(budgets, c, executor, started)})
        if terminal:
            d = executor.diagnosis or {}
            return done(d.get("outcome", "failed"), "diagnosis submitted")
