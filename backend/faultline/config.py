"""Server-side configuration. Secrets stay here and are never logged."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("FAULTLINE_DATA_DIR", REPO_ROOT / "data"))

DEFAULT_BASE_URL = "https://api.tokenfactory.nebius.com/v1"
DEFAULT_MODEL = "nvidia/nemotron-3-super-120b-a12b"

# Prices for the default model, USD per 1M tokens, from the official public catalog
# https://tokenfactory.nebius.com/api/public/models_info (read 2026-10-26). Re-check before quoting.
PRICE_SOURCE = "https://tokenfactory.nebius.com/api/public/models_info (read 2026-10-26)"
DEFAULT_PRICES = {
    "nvidia/nemotron-3-super-120b-a12b": (0.30, 0.90),
    "nvidia/Nemotron-3-Ultra-550b-a55b": (1.00, 3.00),
    "nvidia/Nemotron-3_5-Lightning": (0.06, 0.24),
    "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B": (0.06, 0.24),
}


def _windows_user_env(name: str) -> str | None:
    """Read a per-user environment variable set via setx / scripts\\set-nebius-key.ps1.

    Processes started before the variable was set do not inherit it, so the
    server looks it up in the registry as a fallback.
    """
    if sys.platform != "win32":
        return None
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
            value, _ = winreg.QueryValueEx(k, name)
            return str(value) if value else None
    except OSError:
        return None


def _dotenv() -> dict[str, str]:
    """Optional KEY=VALUE file at the repo root (gitignored). Never logged."""
    path = REPO_ROOT / ".env"
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def _env(name: str, default: str | None = None) -> str | None:
    """Lookup order: process environment, repo-root .env, Windows per-user environment."""
    v = os.environ.get(name)
    if v:
        return v
    v = _dotenv().get(name)
    if v:
        return v
    return _windows_user_env(name) or default


@dataclass(frozen=True)
class Settings:
    base_url: str
    model: str
    price_in_per_m: float
    price_out_per_m: float
    max_spend_usd: float
    max_tool_calls: int
    max_model_calls: int
    wall_clock_s: float
    request_timeout_s: float
    max_retries: int
    max_output_tokens: int
    reasoning: str  # "default" or "off"

    @property
    def has_key(self) -> bool:
        return bool(api_key())


def api_key() -> str | None:
    key = _env("NEBIUS_API_KEY")
    return key.strip() if key else None


def load_settings() -> Settings:
    model = _env("FAULTLINE_MODEL", DEFAULT_MODEL) or DEFAULT_MODEL
    pin, pout = DEFAULT_PRICES.get(model, (float("nan"), float("nan")))
    return Settings(
        base_url=(_env("NEBIUS_BASE_URL", DEFAULT_BASE_URL) or DEFAULT_BASE_URL).rstrip("/"),
        model=model,
        price_in_per_m=float(_env("FAULTLINE_PRICE_IN_PER_M", str(pin))),
        price_out_per_m=float(_env("FAULTLINE_PRICE_OUT_PER_M", str(pout))),
        max_spend_usd=float(_env("FAULTLINE_MAX_SPEND_USD", "3.00")),
        max_tool_calls=int(_env("FAULTLINE_MAX_TOOL_CALLS", "12")),
        max_model_calls=int(_env("FAULTLINE_MAX_MODEL_CALLS", "16")),
        wall_clock_s=float(_env("FAULTLINE_WALL_CLOCK_S", "120")),
        request_timeout_s=float(_env("FAULTLINE_REQUEST_TIMEOUT_S", "60")),
        max_retries=int(_env("FAULTLINE_MAX_RETRIES", "2")),
        max_output_tokens=int(_env("FAULTLINE_MAX_OUTPUT_TOKENS", "4096")),
        reasoning=_env("FAULTLINE_REASONING", "default") or "default",
    )
