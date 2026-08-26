"""Shared settings, teacher-LLM client and budget guard for the training rig.

The teacher (a cheap hosted LLM via OpenRouter) generates and labels the
synthetic corpus. The guard counts the usage of EVERY request and hard-stops
at HARD_LIMIT_USD — a provider-side spending limit on the key should be the
last line of defense, not the first.

API key resolution, in order:
  1. the OPENROUTER_API_KEY environment variable
  2. a `.env` file next to this module (see `.env.example`; git-ignored)
"""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
CHECKPOINTS = ROOT / "checkpoints"

# Tried in order: if the first returns 404, fall through to the next.
TEACHERS = ("google/gemini-3.1-flash-lite", "google/gemini-2.5-flash-lite")

# $/1M tokens (flash-lite pricing at the time of training).
INPUT_USD = 0.25
OUTPUT_USD = 1.50

# Budget guard: override with TEACHER_BUDGET_USD if your key allows more.
HARD_LIMIT_USD = float(os.environ.get("TEACHER_BUDGET_USD", "12"))
SPEND_FILE = DATA / "spend.json"

_lock = threading.Lock()


def _api_key() -> str:
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if key:
        return key
    env_file = ROOT / ".env"
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("OPENROUTER_API_KEY="):
                return line.split("=", 1)[1].strip()
    raise RuntimeError(
        "No OPENROUTER_API_KEY: set the environment variable or create "
        f"{env_file} (see .env.example)")


def spend() -> dict:
    try:
        return json.loads(SPEND_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"giris": 0, "cikis": 0, "usd": 0.0, "istek": 0}


def _add_spend(input_tokens: int, output_tokens: int) -> float:
    # Field names in spend.json ("giris"/"cikis"/"istek") predate the
    # English rename and are kept so existing spend files keep counting.
    with _lock:
        s = spend()
        s["giris"] += input_tokens
        s["cikis"] += output_tokens
        s["istek"] += 1
        s["usd"] = s["giris"] / 1e6 * INPUT_USD + s["cikis"] / 1e6 * OUTPUT_USD
        DATA.mkdir(parents=True, exist_ok=True)
        SPEND_FILE.write_text(json.dumps(s, indent=1), encoding="utf-8")
        return s["usd"]


class BudgetExceeded(RuntimeError):
    pass


_chosen_teacher: list[str] = []


def ask_teacher(messages: list[dict], *, max_tokens: int = 400,
                temperature: float = 0.0, retries: int = 3) -> str:
    """One teacher call: budget-guarded, with retries and model fallback."""
    if spend()["usd"] >= HARD_LIMIT_USD:
        raise BudgetExceeded(f"Budget limit reached: ${HARD_LIMIT_USD}")

    candidates = _chosen_teacher or list(TEACHERS)
    last_error: Exception | None = None
    for model in candidates:
        for attempt in range(retries):
            body = json.dumps({
                "model": model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
            }).encode()
            req = urllib.request.Request(
                "https://openrouter.ai/api/v1/chat/completions", data=body,
                headers={"Authorization": f"Bearer {_api_key()}",
                         "Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=120) as r:
                    out = json.load(r)
                usage = out.get("usage") or {}
                _add_spend(int(usage.get("prompt_tokens") or 0),
                           int(usage.get("completion_tokens") or 0))
                if not _chosen_teacher:
                    _chosen_teacher.append(model)
                return (out["choices"][0]["message"]["content"] or "").strip()
            except urllib.error.HTTPError as exc:
                if exc.code == 404:
                    last_error = exc
                    break  # model not offered; try the next one
                last_error = exc
                time.sleep(1.5 * (attempt + 1))
            except Exception as exc:  # network hiccup
                last_error = exc
                time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"Teacher did not answer: {last_error}")
