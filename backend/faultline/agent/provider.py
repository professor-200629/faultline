"""Chat-completion providers.

`NebiusProvider` calls NVIDIA Nemotron on Nebius Token Factory through the
OpenAI-compatible /v1/chat/completions endpoint. The API key lives only in
this object (never in events, logs or exceptions).

`ScriptedProvider` replays fixed assistant messages. It exists for unit tests
and is always labelled TEST FIXTURE; the application never falls back to it.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol

import httpx


class ProviderError(Exception):
    def __init__(self, kind: str, message: str, status: Optional[int] = None, retryable: bool = False):
        super().__init__(message)
        self.kind = kind
        self.status = status
        self.retryable = retryable

    def public(self) -> dict:
        return {"kind": self.kind, "status": self.status, "message": str(self)[:300], "retryable": self.retryable}


@dataclass
class ProviderResult:
    message: dict
    usage: dict
    model: str
    finish_reason: str
    latency_ms: int
    meta: dict = field(default_factory=dict)


class ChatProvider(Protocol):
    name: str
    model: str
    label: str

    async def complete(self, messages: list[dict], tools: list[dict], tool_choice: Any, max_tokens: int,
                       timeout_s: float) -> ProviderResult: ...


def _classify(status: int, body: str) -> ProviderError:
    snippet = body[:300]
    if status == 401:
        return ProviderError("auth", "Nebius rejected the API key (401)", status)
    if status == 402:
        return ProviderError("quota", "Nebius reports exhausted credit (402)", status)
    if status == 403:
        return ProviderError("forbidden", "Nebius refused the request (403)", status)
    if status == 404:
        return ProviderError("model_not_found", f"model or endpoint not found (404): {snippet}", status)
    if status in (400, 422):
        return ProviderError("bad_request", f"request rejected ({status}): {snippet}", status)
    if status == 429:
        return ProviderError("rate_limit", "rate limited (429)", status, retryable=True)
    if status >= 500:
        return ProviderError("server", f"provider error ({status})", status, retryable=True)
    return ProviderError("http", f"unexpected HTTP {status}", status)


class NebiusProvider:
    name = "nebius-token-factory"
    label = "LIVE"
    billable = True

    def __init__(self, api_key: str, base_url: str, model: str, reasoning: str = "default") -> None:
        if not api_key:
            raise ProviderError("config", "NEBIUS_API_KEY is not set")
        self._key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.reasoning = reasoning

    def __repr__(self) -> str:
        return f"NebiusProvider(model={self.model!r}, base_url={self.base_url!r}, key=<redacted>)"

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._key}", "Content-Type": "application/json"}

    async def list_models(self, timeout_s: float = 20.0) -> list[str]:
        try:
            async with httpx.AsyncClient(timeout=timeout_s) as c:
                r = await c.get(f"{self.base_url}/models", headers=self._headers())
        except httpx.TimeoutException:
            raise ProviderError("timeout", "model list timed out", retryable=True) from None
        except httpx.HTTPError as e:
            raise ProviderError("network", f"network error: {type(e).__name__}", retryable=True) from None
        if r.status_code != 200:
            raise _classify(r.status_code, r.text)
        return [m.get("id", "") for m in r.json().get("data", [])]

    async def complete(self, messages: list[dict], tools: list[dict], tool_choice: Any, max_tokens: int,
                       timeout_s: float) -> ProviderResult:
        body: dict = {"model": self.model, "messages": messages, "tools": tools, "tool_choice": tool_choice,
                      "max_tokens": max_tokens, "temperature": 0.2}
        if self.reasoning == "off":
            body["chat_template_kwargs"] = {"enable_thinking": False}
        t0 = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(timeout_s, connect=15.0)) as c:
                r = await c.post(f"{self.base_url}/chat/completions", headers=self._headers(), json=body)
        except httpx.TimeoutException:
            raise ProviderError("timeout", f"no response within {timeout_s:.0f} s", retryable=True) from None
        except httpx.HTTPError as e:
            raise ProviderError("network", f"network error: {type(e).__name__}", retryable=True) from None
        latency = int((time.monotonic() - t0) * 1000)
        if r.status_code != 200:
            raise _classify(r.status_code, r.text)
        try:
            j = r.json()
            choice = j["choices"][0]
            msg = choice["message"]
        except (ValueError, KeyError, IndexError, TypeError):
            raise ProviderError("bad_response", "response did not contain choices[0].message") from None
        usage = j.get("usage") or {}
        reasoning_tokens = ((usage.get("completion_tokens_details") or {}).get("reasoning_tokens"))
        clean = {"role": "assistant", "content": msg.get("content"), "tool_calls": msg.get("tool_calls") or []}
        return ProviderResult(
            message=clean,
            usage={"prompt_tokens": usage.get("prompt_tokens"), "completion_tokens": usage.get("completion_tokens"),
                   "total_tokens": usage.get("total_tokens"), "reasoning_tokens": reasoning_tokens},
            model=j.get("model") or self.model,
            finish_reason=choice.get("finish_reason") or "",
            latency_ms=latency,
            meta={"response_id": j.get("id"),
                  "had_reasoning_content": bool(msg.get("reasoning_content") or msg.get("reasoning"))},
        )


class ScriptedProvider:
    """TEST FIXTURE: returns pre-written assistant messages in order."""

    name = "scripted-test-fixture"
    label = "TEST FIXTURE"
    billable = False

    def __init__(self, script: list[dict], model: str = "test-fixture") -> None:
        self.script = list(script)
        self.model = model
        self.requests: list[dict] = []

    async def complete(self, messages, tools, tool_choice, max_tokens, timeout_s) -> ProviderResult:
        import copy

        self.requests.append({"messages": copy.deepcopy(messages), "tools": tools, "tool_choice": tool_choice})
        if not self.script:
            raise ProviderError("bad_response", "script exhausted")
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        return ProviderResult(message={"role": "assistant", "content": step.get("content"),
                                       "tool_calls": step.get("tool_calls", [])},
                              usage={"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120,
                                     "reasoning_tokens": None},
                              model=self.model, finish_reason="tool_calls", latency_ms=1)


def tool_call(name: str, args: dict, call_id: str = "") -> dict:
    """Helper for tests and the replay recorder: one OpenAI-format tool call."""
    import json
    import uuid

    return {"id": call_id or f"call-{uuid.uuid4().hex[:10]}", "type": "function",
            "function": {"name": name, "arguments": json.dumps(args)}}
