"""Auto model mode: pool filtering, request shape, health score, first setup.

Everything here runs offline: OpenRouter responses are fake, the clock is
injected. Live behaviour (the real /models response, real key verification)
was verified by hand separately — the test's job is to pin the contract.
"""

from __future__ import annotations

import asyncio
import json
import urllib.error
from pathlib import Path
from types import SimpleNamespace

import pytest

from dornick import automode, settings
from dornick.config import OPENROUTER_URL, Config, ModelConfig
from dornick.context import Prepared

# ---------------------------------------------------------------------
# fake OpenRouter /models records


def _model(id: str, *, prompt: str = "0", completion: str = "0", tools: bool = True) -> dict:
    params = ["max_tokens", "temperature"]
    if tools:
        params.append("tools")
    return {
        "id": id,
        "pricing": {"prompt": prompt, "completion": completion},
        "supported_parameters": params,
    }


# -- (a) pool filtering -------------------------------------------------


def test_paid_models_are_filtered_out() -> None:
    entries = [
        _model("bedava/a"),
        _model("ucretli/b", prompt="0.000001"),
        _model("ucretli/c", completion="0.000002"),
        _model("bedava/d"),
    ]
    assert automode.sift(entries) == ["bedava/a", "bedava/d"]


def test_models_without_tool_support_are_filtered_out() -> None:
    """There is nothing this harness can do with a tool-less model."""
    entries = [_model("a/tools"), _model("b/naked", tools=False), _model("c/tools")]
    assert automode.sift(entries) == ["a/tools", "c/tools"]


def test_the_pool_keeps_only_the_first_six_in_listed_order() -> None:
    entries = [_model(f"m/{i}") for i in range(9)]
    assert automode.sift(entries) == [f"m/{i}" for i in range(6)]


def test_garbage_entries_do_not_crash_the_filter() -> None:
    entries = [None, "metin", {"id": ""}, {"id": "x", "pricing": {"prompt": "bozuk"}},
               _model("saglam/a")]
    assert automode.sift(entries) == ["saglam/a"]


# -- pool cache ---------------------------------------------------------


def _fake_urlopen(payload: dict):
    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps(payload).encode("utf-8")

    def _open(url, timeout=0):
        return _Response()

    return _open


def test_the_pool_is_cached_on_disk_and_survives_offline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = {"data": [_model("a/1"), _model("b/2")]}
    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen(payload))
    automode._MEMORY.clear()

    clock = [1_000.0]
    assert automode.pool(tmp_path, now=lambda: clock[0]) == ["a/1", "b/2"]
    cache = json.loads((tmp_path / automode.POOL_FILE).read_text(encoding="utf-8"))
    assert cache["havuz"] == ["a/1", "b/2"]

    # The network died, the cache is fresh: the list is the on-disk one.
    def _explode(url, timeout=0):
        raise urllib.error.URLError("ağ yok")

    monkeypatch.setattr("urllib.request.urlopen", _explode)
    automode._MEMORY.clear()
    assert automode.pool(tmp_path, now=lambda: clock[0] + 3600) == ["a/1", "b/2"]

    # 24 hours passed, still no network: a stale cache beats nothing.
    automode._MEMORY.clear()
    assert automode.pool(tmp_path, now=lambda: clock[0] + automode.FRESHNESS_S + 5) == ["a/1", "b/2"]


def test_no_network_and_no_cache_means_an_empty_pool(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _explode(url, timeout=0):
        raise urllib.error.URLError("ağ yok")

    monkeypatch.setattr("urllib.request.urlopen", _explode)
    automode._MEMORY.clear()
    assert automode.pool(tmp_path) == []


# -- auto mode definition -----------------------------------------------


def test_oto_mode_needs_both_openrouter_and_the_oto_name() -> None:
    assert automode.is_auto(ModelConfig())  # the fresh-install default
    assert automode.is_auto(ModelConfig(name="Oto", base_url=OPENROUTER_URL + "/"))
    # On another provider "oto" may be a real model name; left alone.
    assert not automode.is_auto(
        ModelConfig(name="oto", base_url="http://localhost:1234/v1")
    )
    assert not automode.is_auto(ModelConfig(name="qwen/qwen3", base_url=OPENROUTER_URL))


# -- (b) request body ---------------------------------------------------

POOL = ["h/1", "h/2", "h/3", "h/4", "h/5", "h/6"]


def _chunk(content=None, finish=None):
    delta = SimpleNamespace(content=content, tool_calls=None,
                            reasoning_content=None, model_extra={})
    return SimpleNamespace(
        choices=[SimpleNamespace(delta=delta, finish_reason=finish)], usage=None
    )


class _FakeStream:
    def __init__(self, chunks):
        self.chunks = chunks

    def __aiter__(self):
        async def gen():
            for c in self.chunks:
                yield c

        return gen()

    async def close(self):
        pass


class _FakeOpenAI:
    def __init__(self, chunks=None, *, explode=False):
        self.seen: dict = {}
        self.explode = explode
        self.stream = _FakeStream(chunks or [_chunk("tamam", "stop")])
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, **kwargs):
        self.seen = kwargs
        if self.explode:
            raise ConnectionError("uç kapalı")
        return self.stream

    async def close(self):
        pass


def _backend(model: ModelConfig, fake: _FakeOpenAI):
    from dornick.backends.openai_backend import OpenAIBackend

    return OpenAIBackend(model, client=fake)


def _prepared() -> Prepared:
    return Prepared(
        system=[{"type": "text", "text": "çekirdek"}],
        messages=[{"role": "user", "content": [{"type": "text", "text": "merhaba"}]}],
        betas=[],
        context_management=None,
    )


@pytest.fixture()
def fixed_pool(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    monkeypatch.setattr(automode, "pool", lambda *a, **k: list(POOL))
    monkeypatch.setattr(automode, "write_last", lambda *a, **k: None)
    return POOL


async def test_oto_request_carries_pool_fallbacks_and_privacy(fixed_pool) -> None:
    """oto + openrouter: the model is the head of the pool, `models` the
    local fallback chain, `provider` refuses data collection."""
    fake = _FakeOpenAI()
    be = _backend(ModelConfig(), fake)  # default: openrouter + oto

    result = await be.turn(_prepared(), [], cancel=asyncio.Event())

    assert result.error is None
    assert fake.seen["model"] == "h/1"
    extra = fake.seen["extra_body"]
    assert extra["models"] == ["h/2", "h/3", "h/4"]
    assert extra["provider"] == {"data_collection": "deny", "require_parameters": True}


async def test_other_providers_are_left_untouched(fixed_pool) -> None:
    """The models/provider fields must NOT LEAK into another provider's request."""
    fake = _FakeOpenAI()
    be = _backend(
        ModelConfig(name="qwen/q3", base_url="http://localhost:1234/v1"), fake
    )
    await be.turn(_prepared(), [], cancel=asyncio.Event())

    assert fake.seen["model"] == "qwen/q3"
    extra = fake.seen.get("extra_body") or {}
    assert "models" not in extra and "provider" not in extra


async def test_a_named_openrouter_model_is_left_untouched(fixed_pool) -> None:
    """With a specific model selected on OpenRouter the oto fields are not added."""
    fake = _FakeOpenAI()
    be = _backend(ModelConfig(name="qwen/qwen3", base_url=OPENROUTER_URL), fake)
    await be.turn(_prepared(), [], cancel=asyncio.Event())

    assert fake.seen["model"] == "qwen/qwen3"
    extra = fake.seen.get("extra_body") or {}
    assert "models" not in extra and "provider" not in extra


async def test_an_empty_pool_fails_with_words_not_a_404(monkeypatch) -> None:
    monkeypatch.setattr(automode, "pool", lambda *a, **k: [])
    fake = _FakeOpenAI()
    be = _backend(ModelConfig(), fake)

    result = await be.turn(_prepared(), [], cancel=asyncio.Event())

    assert result.error and "havuz" in result.error.lower()
    assert not fake.seen, "no request should be sent without a pool"


async def test_failures_are_recorded_and_the_pool_rotates(fixed_pool) -> None:
    """Two errors push the model to the end of the pool; the next request goes out with h/2.

    When the request cannot be set up at all (connection refused) the error
    propagates — existing behaviour; the health ledger must still have
    been updated.
    """
    fake = _FakeOpenAI(explode=True)
    be = _backend(ModelConfig(), fake)

    for _ in range(automode.ERROR_THRESHOLD):
        with pytest.raises(ConnectionError):
            await be.turn(_prepared(), [], cancel=asyncio.Event())

    assert be._health.cezali("h/1")
    fake.explode = False
    await be.turn(_prepared(), [], cancel=asyncio.Event())
    assert fake.seen["model"] == "h/2"


# -- (c) health score ---------------------------------------------------


def test_two_failures_bench_a_model_for_fifteen_minutes() -> None:
    clock = [0.0]
    health = automode.Health(clock=lambda: clock[0])

    health.save("m/1", ok=True)
    health.save("m/1", ok=False)
    assert health.rank(["m/1", "m/2"]) == ["m/1", "m/2"], "a single error is no penalty"

    health.save("m/1", ok=False)
    assert health.rank(["m/1", "m/2"]) == ["m/2", "m/1"], "two errors → to the end"

    # Does not return before the 15 minutes are up…
    clock[0] = automode.PENALTY_S - 1
    assert health.rank(["m/1", "m/2"]) == ["m/2", "m/1"]
    # …and returns with a clean slate once they are.
    clock[0] = automode.PENALTY_S + 1
    assert health.rank(["m/1", "m/2"]) == ["m/1", "m/2"]
    assert not health.cezali("m/1")


def test_the_window_slides_old_failures_out() -> None:
    """The window is 5 calls: old errors do not stay on its back forever."""
    health = automode.Health(clock=lambda: 0.0)
    health.save("m", ok=False)
    for _ in range(automode.WINDOW):
        health.save("m", ok=True)
    health.save("m", ok=False)
    assert not health.cezali("m"), "an error that left the window must not count"


# -- (d) first-setup guidance -------------------------------------------


class _Hub:
    def __init__(self):
        self.events: list[dict] = []

    def emit(self, payload: dict) -> None:
        self.events.append(payload)


def _keyless(monkeypatch: pytest.MonkeyPatch) -> None:
    for entry in settings.PROVIDERS:
        if entry["env"]:
            monkeypatch.delenv(entry["env"], raising=False)


async def test_an_unconfigured_setup_guides_instead_of_calling_the_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """On a keyless setup submit → NO model call, the guidance lands in the
    chat and the turn closes normally (the gate waits for turn_end)."""
    from dornick.desktop import Bridge
    from dornick.events import EventLog
    from dornick.session import Session

    _keyless(monkeypatch)
    hub = _Hub()
    bridge = Bridge(hub, asyncio.get_running_loop())

    called = []

    async def _never(*a, **k):
        called.append(True)

    session = Session(EventLog(tmp_path / "s.jsonl"), "test")
    config = Config.load(tmp_path)  # fresh: openrouter + oto, no key
    bridge.agent = SimpleNamespace(config=config, session=session, run=_never)

    await bridge._handle("merhaba", "")

    assert not called, "the model should not have been called"
    hints = [e for e in hub.events if e.get("type") == "setup_hint"]
    assert len(hints) == 1, "the guidance must be printed exactly once"
    assert "OpenRouter" in hints[0]["text"]
    assert hub.events[-1]["type"] == "turn_end"

    # The guidance also lands in the session as an assistant message: the
    # outer gate and the history transcript read it from there.
    roles = [(e.role, e.content) for e in session.log.messages()]
    assert roles[0][0] == "user"
    assert roles[1][0] == "assistant"

    # If the user writes again it is reminded again (once per message).
    await bridge._handle("hâlâ orda mısın", "")
    hints = [e for e in hub.events if e.get("type") == "setup_hint"]
    assert len(hints) == 2


async def test_a_configured_setup_runs_the_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dornick.desktop import Bridge
    from dornick.events import EventLog
    from dornick.session import Session

    _keyless(monkeypatch)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    hub = _Hub()
    bridge = Bridge(hub, asyncio.get_running_loop())

    ran = []

    async def _run(text, image):
        ran.append(text)

    session = Session(EventLog(tmp_path / "s.jsonl"), "test")
    bridge.agent = SimpleNamespace(config=Config.load(tmp_path), session=session, run=_run)

    await bridge._handle("merhaba", "")

    assert ran == ["merhaba"]
    assert not [e for e in hub.events if e.get("type") == "setup_hint"]


def test_unconfigured_definition_covers_key_and_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _keyless(monkeypatch)
    assert settings.unconfigured(ModelConfig())          # no key
    assert settings.unconfigured(ModelConfig(name=" "))  # name empty

    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    assert not settings.unconfigured(ModelConfig())

    # A local server wants no key: one with a name counts as configured.
    local = ModelConfig(name="qwen/q3", base_url="http://localhost:1234/v1",
                        api_key_env=None)
    assert not settings.unconfigured(local)


# -- (e) key verification -----------------------------------------------


@pytest.fixture()
def config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Config:
    _keyless(monkeypatch)
    cfg = Config(workspace=tmp_path, state_dir=tmp_path / ".dornick")
    cfg.ensure_dirs()
    return cfg


def test_a_401_key_is_rejected_and_nothing_is_written(
    config: Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _reject(request, timeout=0):
        raise urllib.error.HTTPError(request.full_url, 401, "Unauthorized", {}, None)

    monkeypatch.setattr("urllib.request.urlopen", _reject)

    with pytest.raises(ValueError, match="geçersiz"):
        settings.apply(config, {"keys": {"OPENROUTER_API_KEY": "sk-or-bozuk"}})

    assert not (config.state_dir / settings.KEYS_FILE).exists()


def test_no_network_saves_the_key_anyway(
    config: Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An offline setup must not lock up: verification is skipped, the key is written."""

    def _offline(request, timeout=0):
        raise urllib.error.URLError("ağ yok")

    monkeypatch.setattr("urllib.request.urlopen", _offline)

    settings.apply(config, {"keys": {"OPENROUTER_API_KEY": "sk-or-cevrimdisi"}})
    keys = settings.load_keys(config.state_dir)
    assert keys["OPENROUTER_API_KEY"] == "sk-or-cevrimdisi"


def test_a_masked_or_foreign_key_skips_validation(
    config: Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The mask means "unchanged"; another provider's key is not asked of
    OpenRouter either."""

    def _never(*a, **k):  # pragma: no cover - must not be called
        raise AssertionError("verification should not have been called")

    monkeypatch.setattr("urllib.request.urlopen", _never)
    settings.apply(config, {"keys": {"OPENROUTER_API_KEY": settings.MASK,
                                     "OPENAI_API_KEY": "sk-baska"}})


# -- catalogue ----------------------------------------------------------


def test_the_catalog_opens_with_oto_on_openrouter(
    config: Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Oto is on the list even without network: this is the fresh-install default."""
    monkeypatch.setattr(settings, "_openai_models_payload", lambda _c: (None, "ağ yok"))
    monkeypatch.setattr(settings.lmstudio, "models", lambda _u: [])

    entries = settings.scan_models(config)  # default: openrouter
    assert entries and entries[0]["id"] == "oto"

    local = Config(workspace=config.workspace, state_dir=config.state_dir)
    local.model = ModelConfig(name="q", base_url="http://localhost:1234/v1")
    assert all(e["id"] != "oto" for e in settings.scan_models(local))
