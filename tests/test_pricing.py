"""The cost chip's data path: price catalogue and the usage-event contract.

Two layers are tested:

  * the `pricing` module — the price table from the OpenRouter catalogue;
    network discipline (never network inside a turn) and cache order.
  * `Bridge._usage_yay` — the event contract the chip in the UI reads:
    turn/session totals, price tag, reset on a new turn.
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from dornick import pricing
from dornick.config import OPENROUTER_URL, Config, ModelConfig

pytestmark = []


def _entry(mid: str, prompt, completion, **extra) -> dict:
    return {"id": mid, "pricing": {"prompt": prompt, "completion": completion}, **extra}


# -- catalogue filter ---------------------------------------------------


def test_the_price_table_is_parsed_from_strings() -> None:
    """OpenRouter returns the price as a string ("0.000003"); it must be parsed to a number."""
    table = pricing.sift([
        _entry("acme/pahali", "0.000015", "0.000075"),
        _entry("acme/bedava", "0", "0.000000"),
    ])
    assert table["acme/pahali"] == {"girdi": 1.5e-05, "cikti": 7.5e-05}
    assert table["acme/bedava"] == {"girdi": 0.0, "cikti": 0.0}


def test_a_broken_entry_does_not_drop_the_table() -> None:
    """A single broken entry (priceless, non-numeric, negative, id-less)
    is skipped silently — the table does not fall."""
    table = pricing.sift([
        {"id": "x/fiyatsiz"},                       # no pricing
        _entry("x/bozuk", "bedava", "çok"),          # not a number
        _entry("x/eksi", "-1", "0.1"),               # negative: broken entry
        {"pricing": {"prompt": "0", "completion": "0"}},  # id-less
        "dize",                                       # not even a dict
        _entry("x/saglam", "0.000001", "0.000002"),
    ])
    assert list(table) == ["x/saglam"]


# -- cache order and network discipline ---------------------------------


def test_the_turn_path_never_touches_the_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`ag=False` (the path inside the turn) never goes to the network under any condition."""

    def _explodes() -> dict:
        raise AssertionError("a network request was made inside the turn")

    monkeypatch.setattr(pricing, "_download", _explodes)
    assert pricing.table(tmp_path, ag=False) == {}


def test_a_fresh_download_is_cached_to_disk_and_memory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    counter = []
    monkeypatch.setattr(
        pricing, "_download",
        lambda: counter.append(1) or {"m/a": {"girdi": 1e-06, "cikti": 2e-06}},
    )

    first = pricing.table(tmp_path, ag=True)
    assert first["m/a"]["cikti"] == 2e-06
    # The disk record was written and the second call does not go back to the network.
    record = json.loads((tmp_path / pricing.PRICE_FILE).read_text(encoding="utf-8"))
    assert record["fiyatlar"]["m/a"]["girdi"] == 1e-06
    assert pricing.table(tmp_path, ag=True) == first
    assert len(counter) == 1, "must not re-download while the cache is fresh"


def test_a_stale_table_still_serves_when_the_network_is_gone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When offline a stale table beats nothing — the same as the automode pool pattern."""
    (tmp_path / pricing.PRICE_FILE).write_text(json.dumps({
        "ts": time.time() - 2 * pricing.FRESHNESS_S,
        "fiyatlar": {"m/eski": {"girdi": 3e-06, "cikti": 4e-06}},
    }), encoding="utf-8")
    monkeypatch.setattr(pricing, "_download", lambda: {})

    assert pricing.table(tmp_path, ag=True)["m/eski"]["cikti"] == 4e-06


# -- tag ----------------------------------------------------------------


def _openrouter(name: str) -> ModelConfig:
    return ModelConfig(name=name, base_url=OPENROUTER_URL)


def test_the_label_only_speaks_for_openrouter(tmp_path: Path) -> None:
    """A local server's model is not in this catalogue: None → the chip shows tokens."""
    local = ModelConfig(name="qwen/q3", base_url="http://localhost:1234/v1")
    assert pricing.etiket(local, tmp_path) is None


def test_the_free_pool_costs_zero(tmp_path: Path) -> None:
    """Oto mode runs on the free pool: the price is zero, not unknown."""
    assert pricing.etiket(_openrouter("oto"), tmp_path) == {"girdi": 0.0, "cikti": 0.0}


def test_an_unknown_model_yields_none_a_known_one_its_price(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        pricing, "_download", lambda: {"m/a": {"girdi": 1e-06, "cikti": 2e-06}}
    )
    assert pricing.etiket(_openrouter("m/a"), tmp_path, ag=True) == {
        "girdi": 1e-06, "cikti": 2e-06,
    }
    assert pricing.etiket(_openrouter("m/yok"), tmp_path) is None


# -- usage-event contract (Bridge) --------------------------------------


class _Hub:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def emit(self, payload: dict) -> None:
        self.events.append(payload)

    def only(self, kind: str) -> list[dict]:
        return [e for e in self.events if e.get("type") == kind]


def _report(prompt_total: int, output: int) -> dict:
    return {
        "cache_read": 0, "cache_write": 0, "uncached": prompt_total,
        "output": output, "prompt_total": prompt_total,
    }


def _bridge(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """A bridge with a fake agent: no model call, no network for the price."""
    from dornick import desktop as desktop_module
    from dornick.desktop import Bridge

    # The background price thread must not go to the network; the test gives the tag itself.
    monkeypatch.setattr(desktop_module.fiyatlama, "etiket",
                        lambda *a, **k: None)
    hub = _Hub()
    bridge = Bridge(hub, asyncio.get_running_loop())
    bridge.agent = SimpleNamespace(
        config=Config.load(tmp_path),
        session=SimpleNamespace(id="s1"),
        permissions=SimpleNamespace(mode="auto"),
        registry={},
        mind=None,
    )
    return bridge, hub


async def test_usage_events_carry_turn_and_session_totals(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Contract: every usage event carries the cache_report fields + the
    turn/session totals + the price tag (None if unknown) together."""
    bridge, hub = _bridge(tmp_path, monkeypatch)

    bridge._usage_yay(_report(1000, 50))
    bridge._usage_yay(_report(1400, 70))

    events = hub.only("usage")
    assert len(events) == 2
    last = events[-1]
    # The cache_report fields stay as they are (the context indicator reads them).
    assert last["prompt_total"] == 1400 and last["output"] == 70
    # The totals accumulate call over call.
    assert last["tur"] == {"girdi": 2400, "cikti": 120, "cagri": 2}
    assert last["oturum"] == last["tur"]
    # Price unknown: None — the chip falls back to the token count, no invented dollars.
    assert last["fiyat"] is None
    # The context box's item-by-item breakdown goes in the same event.
    assert {p["id"] for p in last["kirilim"]} == {
        "sistem", "arac", "ruh", "yetenek", "mcp", "yardimci", "sohbet"}
    assert sum(p["n"] for p in last["kirilim"]) == 1400


async def test_a_new_user_turn_resets_the_turn_total_not_the_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bridge, hub = _bridge(tmp_path, monkeypatch)

    async def _run(text: str, image: str) -> None:
        bridge._usage_yay(_report(500, 20))

    bridge.agent.run = _run
    monkeypatch.setattr(
        "dornick.settings.yapilandirilmamis", lambda model: False)

    await bridge._isle("ilk iş", "")
    await bridge._isle("ikinci iş", "")

    last = hub.only("usage")[-1]
    assert last["tur"] == {"girdi": 500, "cikti": 20, "cagri": 1}, \
        "a new user message must reset the turn total"
    assert last["oturum"] == {"girdi": 1000, "cikti": 40, "cagri": 2}, \
        "the session total must not be reset"


async def test_the_price_label_arrives_in_the_background(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When the tag is found a `fiyat` event is published and the following
    usage events carry the tag; the network is hit AT MOST once per session."""
    from dornick import desktop as desktop_module

    bridge, hub = _bridge(tmp_path, monkeypatch)
    counter = []

    def _tag(*a, **k):
        counter.append(1)
        return {"girdi": 1e-06, "cikti": 2.5e-05}

    monkeypatch.setattr(desktop_module.fiyatlama, "etiket", _tag)

    bridge._usage_yay(_report(1000, 50))
    # Wait for the background thread to finish (returns instantly; the bound is a safety net).
    for _ in range(200):
        if hub.only("fiyat"):
            break
        await asyncio.sleep(0.01)

    price_events = hub.only("fiyat")
    assert price_events and price_events[0]["fiyat"]["cikti"] == 2.5e-05

    bridge._usage_yay(_report(500, 10))
    assert hub.only("usage")[-1]["fiyat"] == {"girdi": 1e-06, "cikti": 2.5e-05}
    assert len(counter) == 1, "the price must be looked up once per session"


async def test_the_snapshot_seeds_the_cost_chip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """On page refresh the chip starts from where it left off, not from zero."""
    bridge, hub = _bridge(tmp_path, monkeypatch)
    bridge._usage_yay(_report(1000, 50))

    frame = bridge.snapshot()
    assert frame["kullanim"]["oturum"] == {"girdi": 1000, "cikti": 50, "cagri": 1}
    assert frame["kullanim"]["tur"]["cagri"] == 1
    assert frame["fiyat"] is None
