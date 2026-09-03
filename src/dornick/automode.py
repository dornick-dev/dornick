"""Auto model mode — OpenRouter only.

When the user picks "oto" as the model name, requests go out with a small
pool of OpenRouter's free models: the first model is the primary, the next
few are OpenRouter's own fallback chain (the `models` field). So there is a
working setup the moment the key is entered, without spending a cent.

The pool comes from the live list and is cached on disk (24 hours fresh; a
stale cache still works when offline). The filter has three layers:

  * free: pricing.prompt == 0 AND pricing.completion == 0,
  * tool-capable: supported_parameters contains "tools" — there is nothing
    this harness can do with a tool-less model,
  * popularity order: the list is requested with `order=top-weekly`; the
    parameter was verified against the live response (max_price=0 returned
    19 models, no paid leakage) but is not trusted blindly — the returned
    list is filtered once more locally, and if the endpoint breaks one day
    the full list is fetched and filtered.

Free endpoints have a known temperament: they can slow down, return empty,
disappear. `Health` counts the last few calls per model; a model that errors
back-to-back is pushed to the end of the pool for a while — the user does
not live through "why do I keep getting the same error". In-memory is
enough: when the process restarts everyone returns with a clean slate.

No field here TOUCHES another provider's request: request shaping only kicks
in when `is_auto` is true.
"""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from pathlib import Path
from typing import Any, Callable

from .config import OPENROUTER_URL, OTO_MODEL, ModelConfig

# Pool cache: .dornick/oto_havuz.json
POOL_FILE = "oto_havuz.json"
POOL_SIZE = 6
FRESHNESS_S = 24 * 3600

# The list request must be cut short: waiting half a minute for the model
# list means making the first answer wait half a minute.
LIST_TIMEOUT = 20.0
KEY_TIMEOUT = 10.0

# Health: a sliding window of the last WINDOW calls; ERROR_THRESHOLD errors
# push the model to the end of the pool for PENALTY_S.
WINDOW = 5
ERROR_THRESHOLD = 2
PENALTY_S = 15 * 60


def is_auto(model: ModelConfig) -> bool:
    """Is this configuration auto mode?

    Both conditions at once: the address is OpenRouter AND the name is
    "oto". Another provider may have a real model named "oto"; it is left
    alone.
    """
    return (
        (model.base_url or "").rstrip("/") == OPENROUTER_URL
        and (model.name or "").strip().lower() == OTO_MODEL
    )


# -- pool --------------------------------------------------------------


def sift(entries: list[Any]) -> list[str]:
    """The first POOL_SIZE free + tool-capable ids from the model list.

    Order is preserved: if the list was requested in popularity order the
    pool is too. The price comparison is numeric — OpenRouter can return
    "0" as well as "0.000000", a string comparison would miss one of them.
    """
    pool: list[str] = []
    for entry in entries:
        if not isinstance(entry, dict) or not entry.get("id"):
            continue
        pricing = entry.get("pricing") or {}
        try:
            free = (
                float(pricing.get("prompt") or "1") == 0.0
                and float(pricing.get("completion") or "1") == 0.0
            )
        except (TypeError, ValueError):
            continue
        if not free:
            continue
        if "tools" not in (entry.get("supported_parameters") or []):
            continue
        ident = str(entry["id"])
        # Batch-only ids 404 in live chat — keep them out of the pool.
        if ident.rsplit(":", 1)[-1].lower() == "batch" and ":" in ident:
            continue
        pool.append(ident)
        if len(pool) >= POOL_SIZE:
            break
    return pool


def _download() -> list[str]:
    """Builds the pool from the live list. Empty list when offline.

    First the filtered + popularity-sorted endpoint; if the parameters break
    one day the full list is fetched and filtered locally. Both responses
    pass through `sift`: trusting the server's filter would mean a paid
    model leaking in.
    """
    for url in (
        OPENROUTER_URL + "/models?max_price=0&order=top-weekly",
        OPENROUTER_URL + "/models",
    ):
        try:
            with urllib.request.urlopen(url, timeout=LIST_TIMEOUT) as response:
                payload = json.load(response)
        except (urllib.error.URLError, OSError, ValueError, TimeoutError):
            continue
        data = payload.get("data") if isinstance(payload, dict) else None
        if isinstance(data, list) and (pool := sift(data)):
            return pool
    return []


def _state_dir() -> Path:
    """Home of the cache. Environment variable > pinned home."""
    env = os.getenv("DORNICK_STATE_DIR")
    if env:
        return Path(env)
    from .config import _resolve_workspace

    return _resolve_workspace(None) / ".dornick"


# So we do not hit disk/network a second time within the process. Keyed by
# file path: tests pass separate state_dirs and they must not bleed into each other.
_LOCK = threading.Lock()
_MEMORY: dict[str, tuple[float, list[str]]] = {}


def pool(state_dir: Path | str | None = None, *, now: Callable[[], float] = time.time) -> list[str]:
    """The free model pool (at most POOL_SIZE ids).

    Order: in-memory (fresh) > cache on disk (fresh) > live list >
    stale cache (better than nothing when offline) > empty list.
    """
    home = Path(state_dir) if state_dir else _state_dir()
    file = home / POOL_FILE

    with _LOCK:
        ts, held = _MEMORY.get(str(file), (0.0, []))
    if held and now() - ts < FRESHNESS_S:
        return list(held)

    record = _read(file)
    if record.get("havuz") and now() - float(record.get("ts") or 0) < FRESHNESS_S:
        with _LOCK:
            _MEMORY[str(file)] = (float(record["ts"]), list(record["havuz"]))
        return list(record["havuz"])

    fresh = _download()
    if fresh:
        record.update({"ts": now(), "havuz": fresh})
        _write(file, record)
        with _LOCK:
            _MEMORY[str(file)] = (now(), list(fresh))
        return fresh

    # No network: a stale cache beats a setup that does not work.
    return list(record.get("havuz") or [])


def write_last(model: str, state_dir: Path | str | None = None) -> None:
    """Notes the last selected model in the cache file.

    For diagnostics: in auto mode the answer to "which model did I talk to"
    lives here. Failing to write must never bring a turn down.
    """
    try:
        home = Path(state_dir) if state_dir else _state_dir()
        file = home / POOL_FILE
        record = _read(file)
        record["son"] = {"model": model, "ts": time.time()}
        _write(file, record)
    except Exception:
        pass


def _read(file: Path) -> dict[str, Any]:
    try:
        data = json.loads(file.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write(file: Path, record: dict[str, Any]) -> None:
    try:
        file.parent.mkdir(parents=True, exist_ok=True)
        temp = file.with_suffix(file.suffix + ".tmp")
        temp.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(file)
    except OSError:
        pass  # if the cache cannot be written it is retried on the next start


# -- health ------------------------------------------------------------


class Health:
    """Per-model health score: the record of the last WINDOW calls.

    Timeout, empty response and error are in the same basket: the call
    failed. A model that accumulates ERROR_THRESHOLD failures in the window
    is pushed to the end of the pool for PENALTY_S; when the time is up it
    returns with a clean slate.

    `clock` is injectable — tests should not wait 15 minutes.
    """

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self.clock = clock
        self._record: dict[str, deque[bool]] = {}
        self._penalty: dict[str, float] = {}

    def save(self, model: str, ok: bool) -> None:
        window = self._record.setdefault(model, deque(maxlen=WINDOW))
        window.append(bool(ok))
        if sum(1 for succeeded in window if not succeeded) >= ERROR_THRESHOLD:
            self._penalty[model] = self.clock() + PENALTY_S
            # Penalty written; the window is reset so the model does not
            # carry old errors on its back when it returns.
            window.clear()

    def cezali(self, model: str) -> bool:
        return self._penalty.get(model, 0.0) > self.clock()

    def rank(self, pool: list[str]) -> list[str]:
        """Pushes penalised models to the end; leaves the order of the rest alone."""
        healthy = [m for m in pool if not self.cezali(m)]
        sick = [m for m in pool if self.cezali(m)]
        return healthy + sick


# -- key verification --------------------------------------------------


def verify_key(switches: str) -> str:
    """Probes the OpenRouter key with GET /key.

    The return value is one of three states:
        "ok"        key valid
        "gecersiz"  401 — key wrong, must not be saved
        "belirsiz"  no network or unexpected answer — verification may be skipped
    """
    request = urllib.request.Request(
        OPENROUTER_URL + "/key",
        headers={"Authorization": f"Bearer {switches}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=KEY_TIMEOUT):
            return "ok"
    except urllib.error.HTTPError as exc:
        return "gecersiz" if exc.code == 401 else "belirsiz"
    except (urllib.error.URLError, OSError, TimeoutError):
        return "belirsiz"
