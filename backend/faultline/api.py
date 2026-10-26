"""HTTP API.

Route groups:
  /api/*        public: anything the investigation screen needs. Never returns
                hidden configuration; ground truth only after a judge reveal.
  /api/judge/*  require the judge session cookie, which is issued only to
                loopback clients and requires a custom header (CSRF guard).
The agent has no HTTP access at all: it acts only through validated tools.
"""

from __future__ import annotations

import logging
import secrets
import time
import uuid
from pathlib import Path
from typing import Literal, Optional

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel

from .agent.provider import NebiusProvider, ProviderError
from .config import DATA_DIR, PRICE_SOURCE, REPO_ROOT, Settings, api_key, load_settings
from .export import export_bundle, markdown_report
from .runtime import RunError, RunManager
from .sim.plant import WINDOW_START_S
from .sim.presets import preset_menu
from .sim.twins import all_pairs
from .store import open_stores

log = logging.getLogger("faultline")
JUDGE_COOKIE = "faultline_judge"
JUDGE_HEADER = "x-faultline-judge"
LOOPBACK = {"127.0.0.1", "::1", "localhost", "testclient"}


class StartBody(BaseModel):
    mode: Literal["live", "reference"]


class BlindBody(BaseModel):
    family: str
    severity: str
    site_profile: str = "standard"


class TwinBody(BaseModel):
    pair_id: str
    site_profile: str = "standard"


class PickBody(BaseModel):
    slot: Literal["alpha", "beta", "random"]


class RemedyBody(BaseModel):
    approve: bool


def create_app(db_path: Optional[Path] = None, settings: Optional[Settings] = None) -> FastAPI:
    settings = settings or load_settings()
    store, sealed = open_stores(db_path or DATA_DIR / "faultline.db")
    manager = RunManager(store, sealed, settings)
    judge_token = secrets.token_urlsafe(24)
    replay_dir = REPO_ROOT / "replays"
    if replay_dir.is_dir():
        import json as _json

        known = store.replay_sources()
        for f in sorted(replay_dir.glob("*.json")):
            if f.name in known:
                continue
            try:
                manager.import_replay(_json.loads(f.read_text(encoding="utf-8")), f.name)
            except (RunError, KeyError, ValueError) as e:
                log.warning("skipped replay %s: %s", f.name, e)
    app = FastAPI(title="FAULTLINE", version="0.1.0", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.manager = manager
    app.state.integration = {"last_check": None}
    # Only loopback host names are served (defeats DNS rebinding to 127.0.0.1)...
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "::1", "[::1]", "testserver"])

    @app.middleware("http")
    async def same_origin_writes(request: Request, call_next):
        # ...and state-changing requests from a browser must come from a loopback origin.
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            origin = request.headers.get("origin")
            if origin:
                from urllib.parse import urlparse

                if (urlparse(origin).hostname or "") not in ("127.0.0.1", "localhost", "::1"):
                    return JSONResponse({"error": "cross-origin request refused"}, status_code=403)
        return await call_next(request)

    @app.exception_handler(RunError)
    async def run_error(_: Request, exc: RunError):
        return JSONResponse({"error": str(exc)}, status_code=exc.status)

    @app.exception_handler(Exception)
    async def unexpected(_: Request, exc: Exception):
        error_id = uuid.uuid4().hex[:8]
        log.error("unhandled %s (error id %s)", type(exc).__name__, error_id)
        return JSONResponse({"error": "internal error", "error_id": error_id}, status_code=500)

    def require_judge(request: Request) -> None:
        if request.cookies.get(JUDGE_COOKIE) != judge_token or request.headers.get(JUDGE_HEADER) != "1":
            raise HTTPException(403, "judge session required")

    # ------------------------------------------------------------------ status
    @app.get("/api/status")
    def status():
        s = manager.settings
        return {
            "provider": {"name": "Nebius Token Factory", "base_url": s.base_url, "model": s.model,
                         "key_configured": bool(api_key()), "reasoning": s.reasoning,
                         "last_check": app.state.integration["last_check"]},
            "budgets": {"max_tool_calls": s.max_tool_calls, "max_model_calls": s.max_model_calls,
                        "wall_clock_s": s.wall_clock_s, "request_timeout_s": s.request_timeout_s,
                        "max_retries": s.max_retries},
            "spend": {"estimated_total_usd": round(store.total_spend(), 6), "ceiling_usd": s.max_spend_usd,
                      "price_in_per_m": s.price_in_per_m, "price_out_per_m": s.price_out_per_m,
                      "price_source": PRICE_SOURCE},
        }

    @app.post("/api/status/check")
    async def check_integration():
        key = api_key()
        if not key:
            res = {"ok": False, "at": time.time(), "error": "NEBIUS_API_KEY is not configured on the server"}
        else:
            try:
                ids = await NebiusProvider(key, manager.settings.base_url, manager.settings.model).list_models()
                listed = manager.settings.model in ids
                res = {"ok": listed, "at": time.time(), "model_listed": listed,
                       "nvidia_models": sorted(i for i in ids if i.lower().startswith("nvidia/"))}
                if not listed:
                    res["error"] = f"{manager.settings.model} is not in this account's /v1/models list"
            except ProviderError as e:
                res = {"ok": False, "at": time.time(), "error": e.public()}
        app.state.integration["last_check"] = res
        return res

    # ------------------------------------------------------------------ catalog
    @app.get("/api/catalog")
    def catalog():
        from .agent.public_model import HYPOTHESES
        from .agent.tools import TOOL_SPECS
        from .sim.spec import NOMINAL

        return {"hypotheses": HYPOTHESES, "tools": [t["function"] for t in TOOL_SPECS.values()],
                "nominal": NOMINAL.public_dict(),
                "twin_pairs": [{"pair_id": p.pair_id, "title": p.title, "situation": p.situation}
                               for p in all_pairs().values()]}

    # ------------------------------------------------------------------ runs (public)
    def public_view(run_id: str, after: int = 0) -> dict:
        run = manager._require(run_id)
        rt = manager._runtimes.get(run_id)
        live = rt is not None and run["status"] == "investigating"
        view = {k: run[k] for k in ("id", "kind", "mode", "status", "status_reason", "created_at", "terminal_at",
                                     "public", "budgets", "provider", "counters", "diagnosis", "board", "remedy",
                                     "versions", "revealed")}
        if live:
            ex = rt.executor
            view["evidence"] = [e.public() for e in ex.evidence]
            view["board"] = ex.board
            view["predictions"] = ex.predictions
        else:
            view["evidence"] = run["evidence"]
            view["predictions"] = run["predictions"]
        view["simulated_time"] = ({"now_s": rt.panel.now_s, "used_s": rt.panel.time.used_s,
                                   "limit_s": rt.panel.time.limit_s} if rt else None)
        view["events"] = store.events(run_id, after)
        if live:
            latest = [e for e in store.events(run_id) if e["type"] == "budget"]
            view["live_counters"] = latest[-1]["payload"] if latest else None
        view["reveal"] = manager.revealed_payload(run_id) if run["revealed"] else None
        return view

    @app.get("/api/runs")
    def list_runs():
        out = []
        for r in store.list_runs(200):
            d = r.get("diagnosis") or {}
            out.append({"id": r["id"], "kind": r["kind"], "mode": r["mode"], "status": r["status"],
                        "recorded_mode": (r.get("versions") or {}).get("recorded_mode"),
                        "created_at": r["created_at"], "revealed": r["revealed"],
                        "provider": r["provider"], "outcome": d.get("outcome"),
                        "primary_hypothesis": d.get("primary_hypothesis"),
                        "warning": [w["tag"] for w in r["public"]["warning"]]})
        return out

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str, after: int = 0):
        return public_view(run_id, after)

    @app.post("/api/guided")
    def guided():
        return {"run_id": manager.create_guided_run()}

    @app.post("/api/runs/{run_id}/reveal-guided")
    def reveal_guided(run_id: str):
        run = manager._require(run_id)
        if run["kind"] != "guided":
            raise HTTPException(403, "only guided examples can be revealed without a judge session")
        return manager.reveal(run_id)

    @app.get("/api/runs/{run_id}/telemetry")
    def telemetry(run_id: str):
        samples = manager.public_telemetry(run_id)
        return {"samples": samples, "now_s": samples[-1]["t_s"] if samples else 0.0,
                "note": "Logged LT-101 / FT-102 / P-101 readings only. True plant state is not included."}

    @app.post("/api/runs/{run_id}/start")
    async def start(run_id: str, body: StartBody):
        manager.start(run_id, body.mode)
        return {"ok": True}

    @app.post("/api/runs/{run_id}/cancel")
    async def cancel(run_id: str):
        manager.cancel(run_id)
        return {"ok": True}

    @app.post("/api/runs/{run_id}/remedy")
    def remedy(run_id: str, body: RemedyBody):
        return manager.decide_remedy(run_id, body.approve)

    @app.get("/api/runs/{run_id}/export.json")
    def export_json(run_id: str):
        bundle = export_bundle(manager, run_id)
        return JSONResponse(bundle, headers={"Content-Disposition": f'attachment; filename="faultline-{run_id}.json"'})

    @app.get("/api/runs/{run_id}/report.md")
    def export_md(run_id: str):
        bundle = export_bundle(manager, run_id)
        return PlainTextResponse(markdown_report(bundle), media_type="text/markdown",
                                 headers={"Content-Disposition": f'attachment; filename="faultline-{run_id}.md"'})

    # ------------------------------------------------------------------ judge
    @app.get("/api/judge/available")
    def judge_available(request: Request):
        host = request.client.host if request.client else ""
        return {"available": host in LOOPBACK,
                "reason": None if host in LOOPBACK else "judge controls are available only on the server's computer"}

    @app.post("/api/judge/session")
    def judge_session(request: Request, response: Response):
        host = request.client.host if request.client else ""
        if host not in LOOPBACK:
            raise HTTPException(403, "judge controls are available only on this computer")
        if request.headers.get(JUDGE_HEADER) != "1":
            raise HTTPException(403, "missing judge header")
        response.set_cookie(JUDGE_COOKIE, judge_token, httponly=True, samesite="strict")
        return {"ok": True}

    @app.get("/api/judge/presets", dependencies=[Depends(require_judge)])
    def presets():
        return preset_menu()

    @app.post("/api/judge/blind-runs", dependencies=[Depends(require_judge)])
    def blind(body: BlindBody):
        try:
            run_id = manager.create_blind_run(body.family, body.severity, body.site_profile)
        except ValueError:
            raise RunError("unknown preset", 400) from None
        return {"run_id": run_id}

    @app.post("/api/judge/twin-challenges", dependencies=[Depends(require_judge)])
    def twin(body: TwinBody):
        return manager.create_twin_challenge(body.pair_id, body.site_profile)

    @app.post("/api/judge/twin-challenges/{cid}/pick", dependencies=[Depends(require_judge)])
    def pick(cid: str, body: PickBody):
        return {"run_id": manager.pick_twin(cid, body.slot)}

    @app.post("/api/judge/runs/{run_id}/reveal", dependencies=[Depends(require_judge)])
    def reveal(run_id: str):
        return manager.reveal(run_id)

    # ------------------------------------------------------------------ frontend
    dist = REPO_ROOT / "frontend" / "dist"
    if dist.exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{path:path}")
        def spa(path: str):
            f = dist / path
            if path and f.is_file() and dist in f.resolve().parents:
                return FileResponse(f)
            return FileResponse(dist / "index.html")

    return app
