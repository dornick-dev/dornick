"""Oto model kipi: havuz süzme, istek şekli, sağlık puanı, ilk kurulum.

Buradaki her şey ağsız koşuyor: OpenRouter yanıtları sahte, saat enjekte.
Canlı davranış (gerçek /models yanıtı, gerçek anahtar doğrulama) ayrıca
elle doğrulandı — testin işi sözleşmeyi sabitlemek.
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
# sahte OpenRouter /models kayıtları


def _model(id: str, *, prompt: str = "0", completion: str = "0", tools: bool = True) -> dict:
    params = ["max_tokens", "temperature"]
    if tools:
        params.append("tools")
    return {
        "id": id,
        "pricing": {"prompt": prompt, "completion": completion},
        "supported_parameters": params,
    }


# -- (a) havuz süzme ----------------------------------------------------


def test_paid_models_are_filtered_out() -> None:
    entries = [
        _model("bedava/a"),
        _model("ucretli/b", prompt="0.000001"),
        _model("ucretli/c", completion="0.000002"),
        _model("bedava/d"),
    ]
    assert automode.suz(entries) == ["bedava/a", "bedava/d"]


def test_models_without_tool_support_are_filtered_out() -> None:
    """Araçsız bir modelle bu harness'ın yapabileceği bir şey yok."""
    entries = [_model("a/tools"), _model("b/naked", tools=False), _model("c/tools")]
    assert automode.suz(entries) == ["a/tools", "c/tools"]


def test_the_pool_keeps_only_the_first_six_in_listed_order() -> None:
    entries = [_model(f"m/{i}") for i in range(9)]
    assert automode.suz(entries) == [f"m/{i}" for i in range(6)]


def test_garbage_entries_do_not_crash_the_filter() -> None:
    entries = [None, "metin", {"id": ""}, {"id": "x", "pricing": {"prompt": "bozuk"}},
               _model("saglam/a")]
    assert automode.suz(entries) == ["saglam/a"]


# -- havuz önbelleği ----------------------------------------------------


def _fake_urlopen(payload: dict):
    class _Yanit:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps(payload).encode("utf-8")

    def _ac(url, timeout=0):
        return _Yanit()

    return _ac


def test_the_pool_is_cached_on_disk_and_survives_offline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = {"data": [_model("a/1"), _model("b/2")]}
    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen(payload))
    automode._BELLEK.clear()

    clock = [1_000.0]
    assert automode.havuz(tmp_path, simdi=lambda: clock[0]) == ["a/1", "b/2"]
    cache = json.loads((tmp_path / automode.POOL_FILE).read_text(encoding="utf-8"))
    assert cache["havuz"] == ["a/1", "b/2"]

    # Ağ öldü, önbellek taze: liste diskteki.
    def _patlat(url, timeout=0):
        raise urllib.error.URLError("ağ yok")

    monkeypatch.setattr("urllib.request.urlopen", _patlat)
    automode._BELLEK.clear()
    assert automode.havuz(tmp_path, simdi=lambda: clock[0] + 3600) == ["a/1", "b/2"]

    # 24 saat geçti, ağ hâlâ yok: bayat önbellek hiç yoktan iyi.
    automode._BELLEK.clear()
    assert automode.havuz(tmp_path, simdi=lambda: clock[0] + automode.FRESHNESS_S + 5) == ["a/1", "b/2"]


def test_no_network_and_no_cache_means_an_empty_pool(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _patlat(url, timeout=0):
        raise urllib.error.URLError("ağ yok")

    monkeypatch.setattr("urllib.request.urlopen", _patlat)
    automode._BELLEK.clear()
    assert automode.havuz(tmp_path) == []


# -- oto kipi tanımı ----------------------------------------------------


def test_oto_mode_needs_both_openrouter_and_the_oto_name() -> None:
    assert automode.oto_mu(ModelConfig())  # taze kurulumun varsayılanı
    assert automode.oto_mu(ModelConfig(name="Oto", base_url=OPENROUTER_URL + "/"))
    # Başka sağlayıcıda "oto" gerçek bir model adı olabilir; dokunulmaz.
    assert not automode.oto_mu(
        ModelConfig(name="oto", base_url="http://localhost:1234/v1")
    )
    assert not automode.oto_mu(ModelConfig(name="qwen/qwen3", base_url=OPENROUTER_URL))


# -- (b) istek gövdesi --------------------------------------------------

HAVUZ = ["h/1", "h/2", "h/3", "h/4", "h/5", "h/6"]


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
    def __init__(self, chunks=None, *, patla=False):
        self.seen: dict = {}
        self.patla = patla
        self.stream = _FakeStream(chunks or [_chunk("tamam", "stop")])
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, **kwargs):
        self.seen = kwargs
        if self.patla:
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
def sabit_havuz(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    monkeypatch.setattr(automode, "havuz", lambda *a, **k: list(HAVUZ))
    monkeypatch.setattr(automode, "write_last", lambda *a, **k: None)
    return HAVUZ


async def test_oto_request_carries_pool_fallbacks_and_privacy(sabit_havuz) -> None:
    """oto + openrouter: model havuzun başı, `models` yerel yedek zinciri,
    `provider` veri toplamayı reddediyor."""
    fake = _FakeOpenAI()
    be = _backend(ModelConfig(), fake)  # varsayılan: openrouter + oto

    result = await be.turn(_prepared(), [], cancel=asyncio.Event())

    assert result.error is None
    assert fake.seen["model"] == "h/1"
    extra = fake.seen["extra_body"]
    assert extra["models"] == ["h/2", "h/3", "h/4"]
    assert extra["provider"] == {"data_collection": "deny", "require_parameters": True}


async def test_other_providers_are_left_untouched(sabit_havuz) -> None:
    """Başka sağlayıcının isteğine models/provider alanı SIZMAMALI."""
    fake = _FakeOpenAI()
    be = _backend(
        ModelConfig(name="qwen/q3", base_url="http://localhost:1234/v1"), fake
    )
    await be.turn(_prepared(), [], cancel=asyncio.Event())

    assert fake.seen["model"] == "qwen/q3"
    extra = fake.seen.get("extra_body") or {}
    assert "models" not in extra and "provider" not in extra


async def test_a_named_openrouter_model_is_left_untouched(sabit_havuz) -> None:
    """OpenRouter'da belirli bir model seçiliyse oto alanları eklenmez."""
    fake = _FakeOpenAI()
    be = _backend(ModelConfig(name="qwen/qwen3", base_url=OPENROUTER_URL), fake)
    await be.turn(_prepared(), [], cancel=asyncio.Event())

    assert fake.seen["model"] == "qwen/qwen3"
    extra = fake.seen.get("extra_body") or {}
    assert "models" not in extra and "provider" not in extra


async def test_an_empty_pool_fails_with_words_not_a_404(monkeypatch) -> None:
    monkeypatch.setattr(automode, "havuz", lambda *a, **k: [])
    fake = _FakeOpenAI()
    be = _backend(ModelConfig(), fake)

    result = await be.turn(_prepared(), [], cancel=asyncio.Event())

    assert result.error and "havuz" in result.error.lower()
    assert not fake.seen, "havuzsuz istek atılmamalı"


async def test_failures_are_recorded_and_the_pool_rotates(sabit_havuz) -> None:
    """İki hata modeli havuzun sonuna itiyor; sıradaki istek h/2 ile çıkıyor.

    İstek hiç kurulamadığında (bağlantı reddi) hata yukarı fırlar — mevcut
    davranış; sağlık defteri yine de işlenmiş olmalı.
    """
    fake = _FakeOpenAI(patla=True)
    be = _backend(ModelConfig(), fake)

    for _ in range(automode.ERROR_THRESHOLD):
        with pytest.raises(ConnectionError):
            await be.turn(_prepared(), [], cancel=asyncio.Event())

    assert be._saglik.cezali("h/1")
    fake.patla = False
    await be.turn(_prepared(), [], cancel=asyncio.Event())
    assert fake.seen["model"] == "h/2"


# -- (c) sağlık puanı ---------------------------------------------------


def test_two_failures_bench_a_model_for_fifteen_minutes() -> None:
    clock = [0.0]
    saglik = automode.Saglik(clock=lambda: clock[0])

    saglik.save("m/1", ok=True)
    saglik.save("m/1", ok=False)
    assert saglik.rank(["m/1", "m/2"]) == ["m/1", "m/2"], "tek hata ceza değil"

    saglik.save("m/1", ok=False)
    assert saglik.rank(["m/1", "m/2"]) == ["m/2", "m/1"], "iki hata → sona"

    # 15 dakika dolmadan dönmüyor…
    clock[0] = automode.CEZA_SN - 1
    assert saglik.rank(["m/1", "m/2"]) == ["m/2", "m/1"]
    # …dolunca temiz sayfayla dönüyor.
    clock[0] = automode.CEZA_SN + 1
    assert saglik.rank(["m/1", "m/2"]) == ["m/1", "m/2"]
    assert not saglik.cezali("m/1")


def test_the_window_slides_old_failures_out() -> None:
    """Pencere 5 çağrı: eski hatalar sonsuza dek sırtında kalmıyor."""
    saglik = automode.Saglik(clock=lambda: 0.0)
    saglik.save("m", ok=False)
    for _ in range(automode.WINDOW):
        saglik.save("m", ok=True)
    saglik.save("m", ok=False)
    assert not saglik.cezali("m"), "pencereden çıkan hata sayılmamalı"


# -- (d) ilk kurulum yönlendirmesi -------------------------------------


class _Hub:
    def __init__(self):
        self.events: list[dict] = []

    def emit(self, payload: dict) -> None:
        self.events.append(payload)


def _anahtarsiz(monkeypatch: pytest.MonkeyPatch) -> None:
    for entry in settings.PROVIDERS:
        if entry["env"]:
            monkeypatch.delenv(entry["env"], raising=False)


async def test_an_unconfigured_setup_guides_instead_of_calling_the_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Anahtarsız kurulumda submit → model çağrısı YOK, sohbete yönlendirme
    düşüyor ve tur normal kapanıyor (gate turn_end bekliyor)."""
    from dornick.desktop import Bridge
    from dornick.events import EventLog
    from dornick.session import Session

    _anahtarsiz(monkeypatch)
    hub = _Hub()
    bridge = Bridge(hub, asyncio.get_running_loop())

    cagrildi = []

    async def _asla(*a, **k):
        cagrildi.append(True)

    session = Session(EventLog(tmp_path / "s.jsonl"), "test")
    config = Config.load(tmp_path)  # taze: openrouter + oto, anahtar yok
    bridge.agent = SimpleNamespace(config=config, session=session, run=_asla)

    await bridge._isle("merhaba", "")

    assert not cagrildi, "model çağrılmamalıydı"
    hints = [e for e in hub.events if e.get("type") == "setup_hint"]
    assert len(hints) == 1, "yönlendirme tam bir kez basılmalı"
    assert "OpenRouter" in hints[0]["text"]
    assert hub.events[-1]["type"] == "turn_end"

    # Yönlendirme oturuma asistan mesajı olarak da düşüyor: dış kapı ve
    # geçmiş dökümü oradan okuyor.
    roller = [(e.role, e.content) for e in session.log.messages()]
    assert roller[0][0] == "user"
    assert roller[1][0] == "assistant"

    # Kullanıcı tekrar yazarsa yeniden hatırlatılıyor (her mesajda bir kez).
    await bridge._isle("hâlâ orda mısın", "")
    hints = [e for e in hub.events if e.get("type") == "setup_hint"]
    assert len(hints) == 2


async def test_a_configured_setup_runs_the_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dornick.desktop import Bridge
    from dornick.events import EventLog
    from dornick.session import Session

    _anahtarsiz(monkeypatch)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    hub = _Hub()
    bridge = Bridge(hub, asyncio.get_running_loop())

    kosuldu = []

    async def _kos(text, image):
        kosuldu.append(text)

    session = Session(EventLog(tmp_path / "s.jsonl"), "test")
    bridge.agent = SimpleNamespace(config=Config.load(tmp_path), session=session, run=_kos)

    await bridge._isle("merhaba", "")

    assert kosuldu == ["merhaba"]
    assert not [e for e in hub.events if e.get("type") == "setup_hint"]


def test_unconfigured_definition_covers_key_and_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _anahtarsiz(monkeypatch)
    assert settings.yapilandirilmamis(ModelConfig())          # anahtar yok
    assert settings.yapilandirilmamis(ModelConfig(name=" "))  # ad boş

    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    assert not settings.yapilandirilmamis(ModelConfig())

    # Yerel sunucu anahtar istemiyor: adı olan yapılandırılmış sayılır.
    yerel = ModelConfig(name="qwen/q3", base_url="http://localhost:1234/v1",
                        api_key_env=None)
    assert not settings.yapilandirilmamis(yerel)


# -- (e) anahtar doğrulama ---------------------------------------------


@pytest.fixture()
def config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Config:
    _anahtarsiz(monkeypatch)
    cfg = Config(workspace=tmp_path, state_dir=tmp_path / ".dornick")
    cfg.ensure_dirs()
    return cfg


def test_a_401_key_is_rejected_and_nothing_is_written(
    config: Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _reddet(istek, timeout=0):
        raise urllib.error.HTTPError(istek.full_url, 401, "Unauthorized", {}, None)

    monkeypatch.setattr("urllib.request.urlopen", _reddet)

    with pytest.raises(ValueError, match="geçersiz"):
        settings.apply(config, {"keys": {"OPENROUTER_API_KEY": "sk-or-bozuk"}})

    assert not (config.state_dir / settings.KEYS_FILE).exists()


def test_no_network_saves_the_key_anyway(
    config: Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Çevrimdışı kurulum kilitlenmemeli: doğrulama atlanır, anahtar yazılır."""

    def _agsiz(istek, timeout=0):
        raise urllib.error.URLError("ağ yok")

    monkeypatch.setattr("urllib.request.urlopen", _agsiz)

    settings.apply(config, {"keys": {"OPENROUTER_API_KEY": "sk-or-cevrimdisi"}})
    keys = settings.load_keys(config.state_dir)
    assert keys["OPENROUTER_API_KEY"] == "sk-or-cevrimdisi"


def test_a_masked_or_foreign_key_skips_validation(
    config: Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Maske "değiştirilmedi" demek; başka sağlayıcının anahtarı da
    OpenRouter'a sorulmaz."""

    def _asla(*a, **k):  # pragma: no cover - çağrılmamalı
        raise AssertionError("doğrulama çağrılmamalıydı")

    monkeypatch.setattr("urllib.request.urlopen", _asla)
    settings.apply(config, {"keys": {"OPENROUTER_API_KEY": settings.MASK,
                                     "OPENAI_API_KEY": "sk-baska"}})


# -- katalog -----------------------------------------------------------


def test_the_catalog_opens_with_oto_on_openrouter(
    config: Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ağ yokken bile Oto listede: taze kurulumun varsayılanı bu."""
    monkeypatch.setattr(settings, "_openai_models_payload", lambda _c: (None, "ağ yok"))
    monkeypatch.setattr(settings.lmstudio, "models", lambda _u: [])

    entries = settings.scan_models(config)  # varsayılan: openrouter
    assert entries and entries[0]["id"] == "oto"

    yerel = Config(workspace=config.workspace, state_dir=config.state_dir)
    yerel.model = ModelConfig(name="q", base_url="http://localhost:1234/v1")
    assert all(e["id"] != "oto" for e in settings.scan_models(yerel))
