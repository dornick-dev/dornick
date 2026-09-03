"""Model price tag — from the OpenRouter catalogue.

For the cost chip: the selected model's input/output price (USD/token).
OpenRouter's /models response carries each model's `pricing` field; the
catalogue request is expensive (hundreds of models + network), so it is
cached both in memory and on disk following the automode pool-cache
pattern (24 hours fresh; a stale table beats nothing when offline).

Two rules protect turn speed:

  * `etiket(ag=False)` NEVER goes to the network — memory + disk. It may
    be called from inside a turn.
  * The only path to the network is `etiket(ag=True)`; the bridge calls
    it on a background thread, once per session.

If the price cannot be known (another provider, a model missing from the
catalogue, no network) None is returned: the UI chip shows a token count
instead of dollars — better than printing a wrong figure.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

from .config import OPENROUTER_URL, OTO_MODEL, ModelConfig
from .automode import LIST_TIMEOUT, FRESHNESS_S, _read, _state_dir, _write

# Price table cache: .dornick/fiyat.json
PRICE_FILE = "fiyat.json"

# So we do not hit the disk a second time within the process; keyed by file
# path (tests pass separate state_dirs and they must not bleed into each other).
_LOCK = threading.Lock()
_MEMORY: dict[str, tuple[float, dict[str, dict[str, float]]]] = {}


def sift(entries: list[Any]) -> dict[str, dict[str, float]]:
    """Price table from the model list: {id: {"girdi": $, "cikti": $}}.

    Prices are USD/token; OpenRouter returns strings ("0.000003") and any
    entry that cannot be parsed to a number is skipped silently — a single
    broken entry must not bring the table down.
    """
    table: dict[str, dict[str, float]] = {}
    for entry in entries:
        if not isinstance(entry, dict) or not entry.get("id"):
            continue
        pricing = entry.get("pricing") or {}
        try:
            prompt_price = float(pricing.get("prompt"))
            completion_price = float(pricing.get("completion"))
        except (TypeError, ValueError):
            continue
        if prompt_price < 0 or completion_price < 0:
            continue   # negative price: broken entry
        table[str(entry["id"])] = {"girdi": prompt_price, "cikti": completion_price}
    return table


def _download() -> dict[str, dict[str, float]]:
    """Price table from the live catalogue. Empty dict when offline."""
    try:
        with urllib.request.urlopen(
            OPENROUTER_URL + "/models", timeout=LIST_TIMEOUT
        ) as response:
            payload = json.load(response)
    except (urllib.error.URLError, OSError, ValueError, TimeoutError):
        return {}
    data = payload.get("data") if isinstance(payload, dict) else None
    return sift(data) if isinstance(data, list) else {}


def table(
    state_dir: Path | str | None = None,
    *,
    ag: bool = False,
    now: Callable[[], float] = time.time,
) -> dict[str, dict[str, float]]:
    """Price table. Order: memory (fresh) > disk (fresh) > [network] > stale disk.

    `ag=False` never touches the network — safe to call from inside a turn.
    """
    home = Path(state_dir) if state_dir else _state_dir()
    file = home / PRICE_FILE

    with _LOCK:
        ts, held = _MEMORY.get(str(file), (0.0, {}))
    if held and now() - ts < FRESHNESS_S:
        return dict(held)

    record = _read(file)
    if record.get("fiyatlar") and now() - float(record.get("ts") or 0) < FRESHNESS_S:
        with _LOCK:
            _MEMORY[str(file)] = (float(record["ts"]), dict(record["fiyatlar"]))
        return dict(record["fiyatlar"])

    if ag:
        fresh = _download()
        if fresh:
            record.update({"ts": now(), "fiyatlar": fresh})
            _write(file, record)
            with _LOCK:
                _MEMORY[str(file)] = (now(), dict(fresh))
            return fresh

    # No network, or network forbidden: a stale table beats nothing.
    return dict(record.get("fiyatlar") or {})


def etiket(
    model: ModelConfig,
    state_dir: Path | str | None = None,
    *,
    ag: bool = False,
    now: Callable[[], float] = time.time,
) -> dict[str, float] | None:
    """The selected model's price tag: {"girdi": USD/token, "cikti": USD/token}.

    Only meaningful on OpenRouter: another provider's (local server,
    Anthropic) price is not in this catalogue → None. "Oto" mode runs on
    the free pool → zero price (true: not a cent is spent). A model missing
    from the catalogue → None; the chip falls back to the token count.
    """
    if (model.base_url or "").rstrip("/") != OPENROUTER_URL:
        return None
    name = (model.name or "").strip()
    if name.lower() == OTO_MODEL:
        return {"girdi": 0.0, "cikti": 0.0}
    return table(state_dir, ag=ag, now=now).get(name)
