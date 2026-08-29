"""Ayarların okunması ve yazılması.

İki şey burada sessizce bozulabiliyor: API anahtarının tarayıcıya sızması
ve bozuk bir değerin diske yazılıp programı bir daha açılmaz hale
getirmesi. İkisi de test edilmezse fark edilmiyor.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from neocp import settings
from neocp.config import Config


@pytest.fixture()
def config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Config:
    # Kabuk ortamındaki gerçek anahtarlar testi kirletmesin.
    for entry in settings.PROVIDERS:
        if entry["env"]:
            monkeypatch.delenv(entry["env"], raising=False)
    # Anahtar doğrulama ağa çıkmasın: testte OpenRouter yok, sahte anahtar
    # canlı uca gidip 401 alırdı.
    monkeypatch.setattr("neocp.otomod.dogrula_anahtar", lambda _aday: "ok")
    cfg = Config(workspace=tmp_path, state_dir=tmp_path / ".neocp")
    cfg.ensure_dirs()
    return cfg


# -- görüntü -----------------------------------------------------------


def test_snapshot_never_carries_a_key(config: Config) -> None:
    """Ayar sayfası gerçek anahtarı hiç görmemeli."""
    settings.apply(config, {"keys": {"ANTHROPIC_API_KEY": "sk-gizli-deger"}})

    payload = json.dumps(settings.snapshot(config), ensure_ascii=False)
    assert "sk-gizli-deger" not in payload
    # Ama "var" bilgisi görünmeli, yoksa kullanıcı tekrar tekrar giriyor.
    entry = next(p for p in settings.snapshot(config)["providers"] if p["id"] == "anthropic")
    assert entry["has_key"]


def test_a_key_from_the_shell_counts_as_present(
    config: Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Kullanıcı anahtarı kabuğunda vermişse sayfa 'eksik' dememeli."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-kabuktan")
    entry = next(p for p in settings.snapshot(config)["providers"] if p["id"] == "openai")

    assert entry["has_key"] and entry["from_env"]


def test_provider_is_recognized_from_the_address(config: Config) -> None:
    """Birçok sağlayıcı 'openai' protokolünü konuşuyor; hangisinin seçili
    olduğu yalnızca adresten anlaşılıyor."""
    updated = settings.apply(config, {"provider": "lmstudio"})
    assert settings.snapshot(updated)["provider"] == "lmstudio"

    updated = settings.apply(updated, {"provider": "openrouter"})
    assert settings.snapshot(updated)["provider"] == "openrouter"

    updated = settings.apply(updated, {"provider": "gemini"})
    assert settings.snapshot(updated)["provider"] == "gemini"
    assert updated.model.base_url.endswith("/v1beta/openai")
    assert updated.model.api_key_env == "GEMINI_API_KEY"


# -- yazma -------------------------------------------------------------


def test_choosing_a_provider_sets_address_and_key_variable(config: Config) -> None:
    """Üçünü elle tutarlı tutmayı kullanıcıya bırakmak hataya davetiye."""
    updated = settings.apply(config, {"provider": "lmstudio"})

    assert updated.model.provider == "openai"
    assert updated.model.base_url == "http://localhost:1234/v1"
    assert updated.model.api_key_env is None

    nvidia = settings.apply(config, {"provider": "nvidia"})
    assert nvidia.model.base_url == "https://integrate.api.nvidia.com/v1"
    assert nvidia.model.api_key_env == "NVIDIA_API_KEY"

    deepseek = settings.apply(config, {"provider": "deepseek"})
    assert deepseek.model.base_url == "https://api.deepseek.com"
    assert deepseek.model.api_key_env == "DEEPSEEK_API_KEY"


def test_settings_survive_a_restart(config: Config) -> None:
    settings.apply(config, {
        "model": {"name": "qwen3.5-32b", "max_tokens": 8000, "context_window": 32_000},
        "permissions": {"mode": "yolo"},
    })

    reloaded = Config.load(config.workspace)
    assert reloaded.model.name == "qwen3.5-32b"
    assert reloaded.model.max_tokens == 8000
    assert reloaded.permissions.mode == "yolo"


def test_keys_are_stored_apart_from_the_config(config: Config) -> None:
    """config.json bir projeye girip sürüm kontrolüne düşebilir; anahtar
    oraya yazılmamalı."""
    settings.apply(config, {"keys": {"ANTHROPIC_API_KEY": "sk-gizli"}})

    assert "sk-gizli" not in (config.state_dir / "config.json").read_text(encoding="utf-8")
    assert "sk-gizli" in (config.state_dir / "keys.json").read_text(encoding="utf-8")


def test_the_mask_means_unchanged(config: Config) -> None:
    """Sayfa gerçek değeri görmediği için geri de gönderemiyor; maskeli
    gelen alanı boş sayıp anahtarı silmek veri kaybı olurdu."""
    settings.apply(config, {"keys": {"ANTHROPIC_API_KEY": "sk-gizli"}})
    settings.apply(config, {"keys": {"ANTHROPIC_API_KEY": settings.MASK}})

    assert settings.load_keys(config.state_dir)["ANTHROPIC_API_KEY"] == "sk-gizli"


def test_an_empty_value_deletes_the_key(config: Config) -> None:
    settings.apply(config, {"keys": {"ANTHROPIC_API_KEY": "sk-gizli"}})
    settings.apply(config, {"keys": {"ANTHROPIC_API_KEY": ""}})

    assert "ANTHROPIC_API_KEY" not in settings.load_keys(config.state_dir)


def test_saved_keys_reach_the_environment(
    config: Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Backend'ler anahtarı ortamdan okuyor; ikinci bir yol açmaya gerek yok."""
    settings.apply(config, {"keys": {"OPENROUTER_API_KEY": "sk-or-1"}})
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    assert settings.export_keys(config.state_dir) == 1
    import os

    assert os.environ["OPENROUTER_API_KEY"] == "sk-or-1"


def test_changing_a_key_reaches_the_environment_immediately(
    config: Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Kullanıcı ayarlardan anahtarı DEĞİŞTİRİNCE çalışan sürecin ortamına
    hemen ulaşmalı — eski bir değer set'li olsa bile. Aksi halde yeni anahtar
    yalnızca programı yeniden başlatınca etkili oluyordu (bu bir hataydı)."""
    import os

    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-eski")
    settings.apply(config, {"keys": {"OPENROUTER_API_KEY": "sk-yeni"}})
    assert os.environ["OPENROUTER_API_KEY"] == "sk-yeni"


def test_the_shell_wins_over_the_saved_key(
    config: Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings.apply(config, {"keys": {"OPENROUTER_API_KEY": "sk-dosyadan"}})
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-kabuktan")

    settings.export_keys(config.state_dir)
    import os

    assert os.environ["OPENROUTER_API_KEY"] == "sk-kabuktan"


# -- doğrulama ---------------------------------------------------------


@pytest.mark.parametrize(
    ("patch", "why"),
    [
        ({"permissions": {"mode": "sinirsiz"}}, "izin kipi"),
        ({"model": {"max_tokens": 10}}, "çok küçük max_tokens"),
        ({"model": {"max_tokens": 500_000}}, "pencereden büyük max_tokens"),
        ({"provider": "yok-boyle-bir-sey"}, "bilinmeyen sağlayıcı"),
        ({"model": {"uydurma_alan": 1}}, "bilinmeyen alan"),
    ],
)
def test_a_bad_value_is_refused_before_it_reaches_disk(
    config: Config, patch: dict, why: str
) -> None:
    """Bozuk bir ayar açılmayan bir programa dönüşüyor; doğrulama arayüzde
    değil burada, çünkü dosya elle de düzenlenebiliyor."""
    with pytest.raises(ValueError):
        settings.apply(config, patch)

    assert not (config.state_dir / "config.json").exists(), why


def test_a_partial_patch_leaves_the_rest_alone(config: Config) -> None:
    """Ayar sayfası kısmi yama gönderiyor ("yalnızca izin kipini
    değiştirdim"); ikinci çağrı elinde bayat bir Config tutsa bile
    dokunulmayan alanlar eski değerlerine dönmemeli — taban disk."""
    settings.apply(config, {"model": {"name": "ilk-model"}, "permissions": {"mode": "yolo"}})
    updated = settings.apply(config, {"permissions": {"mode": "ask"}})

    assert updated.permissions.mode == "ask"
    assert updated.model.name == "ilk-model"
    assert Config.load(config.workspace).model.name == "ilk-model"


# -- canlı model değişikliği -------------------------------------------
#
# "Kaydet"e basıp hiçbir şeyin değişmediğini görmek, sonra programı kapatıp
# açmak gerektiğini keşfetmek iyi bir ayar sayfası değil.


class _FakeAgent:
    def __init__(self, config) -> None:  # noqa: ANN001
        self.config = config
        self.client = object()
        from neocp.permissions import PermissionEngine

        self.permissions = PermissionEngine.from_config(config.permissions)
        self.policy = None
        self.lean = False
        self.reconfigured = 0

    def reconfigure(self, config) -> None:  # noqa: ANN001
        # Gerçek Agent.reconfigure'ın gözlemlenebilir sözleşmesi: config
        # güncellenir, çekirdek yeniden kurulur. Testte kaç kez çağrıldığını
        # da sayıyoruz — modelsiz kaydetmede de anında uygulanmalı.
        self.config = config
        self.reconfigured += 1


def _bridge(config):  # noqa: ANN001
    """Köprüyü döngüsüz kurar: burada bakılan şey karar, eşyordam değil."""
    import asyncio
    from dataclasses import replace

    from neocp.desktop import Bridge

    bridge = Bridge.__new__(Bridge)
    bridge.agent = _FakeAgent(config)
    bridge.hub = type("Hub", (), {"emit": lambda self, e: self.seen.append(e),
                                  "seen": []})()
    bridge.hub.seen = []
    bridge._busy = False
    bridge._wanted_model = None
    bridge._wanted_config = None
    bridge.loop = asyncio.new_event_loop()
    bridge.ear = None
    return bridge, replace


def test_changing_the_model_takes_effect_without_a_restart(tmp_path: Path) -> None:
    from dataclasses import replace

    from neocp.config import Config

    config = Config.load(tmp_path)
    bridge, _ = _bridge(config)
    before = bridge.agent.client

    bridge.reload(replace(config, model=replace(config.model, name="başka/model")))

    assert bridge.agent.client is not before
    assert bridge._wanted_model is None
    bridge.loop.close()


def test_a_change_mid_turn_waits_for_the_turn(tmp_path: Path) -> None:
    """Akan bir istemciyi altından çekmek o cevabı öldürür."""
    from dataclasses import replace

    from neocp.config import Config

    config = Config.load(tmp_path)
    bridge, _ = _bridge(config)
    bridge._busy = True
    before = bridge.agent.client

    bridge.reload(replace(config, model=replace(config.model, name="başka/model")))

    assert bridge.agent.client is before      # henüz değişmedi
    assert bridge._wanted_model is not None   # ama bekliyor

    bridge._busy = False
    bridge._swap_model()
    assert bridge.agent.client is not before
    bridge.loop.close()


def test_a_mode_change_reaches_the_page_as_an_event(tmp_path: Path) -> None:
    """Kip değişimi yalnız notice metniyle duyuruluyordu — metin makine
    okunur değil. Dock çipi ve plan-onay düğmesi gerçek kipi ancak ayrı
    bir `mode` olayıyla izleyebiliyor (ayar sayfası dışından — dış kapı,
    başka sekme — değişen kip de dahil)."""
    from dataclasses import replace

    from neocp.config import Config

    config = Config.load(tmp_path)
    bridge, _ = _bridge(config)

    bridge.reload(replace(config, permissions=replace(config.permissions, mode="plan")))

    assert {"type": "mode", "mode": "plan"} in bridge.hub.seen
    bridge.loop.close()


def test_settings_that_do_not_touch_the_model_leave_it_alone(tmp_path: Path) -> None:
    """Her kaydetmede istemciyi yeniden kurmak, bağlantıyı boşuna
    tazelemek demek."""
    from dataclasses import replace

    from neocp.config import Config

    config = Config.load(tmp_path)
    bridge, _ = _bridge(config)
    before = bridge.agent.client

    bridge.reload(replace(config, voice=replace(config.voice, enabled=True)))

    assert bridge.agent.client is before
    # İstemci tazelenmedi ama çekirdek yine de yeniden kuruldu: ses açıldı,
    # duyu değişti — bunlar yeniden başlatmadan bir sonraki tura girmeli.
    assert bridge.agent.reconfigured == 1
    assert bridge.agent.config.voice.enabled
    bridge.loop.close()


# -- oturum değiştirme: yeni / devam (canlı) ---------------------------


def _bridge_with_session(tmp_path):
    """Gerçek config/mind/session ile bir köprü; oturum değiştirmeyi sınar."""
    import asyncio
    from neocp.config import Config
    from neocp.desktop import Bridge
    from neocp.events import EventLog
    from neocp.mind import open_mind
    from neocp.permissions import PermissionEngine
    from neocp.session import Session

    config = Config.load(tmp_path)
    config.ensure_dirs()
    mind = open_mind(config.mind_dir, config.sessions_dir, "ilk")
    sess = Session.create(config.sessions_dir)

    agent = type("A", (), {})()
    agent.config = config
    agent.mind = mind
    agent.session = sess
    agent._last_encoded = "eski"
    agent.permissions = PermissionEngine.from_config(config.permissions)

    rebinds = []
    server = type("S", (), {"rebind": lambda self, s: rebinds.append(s.id)})()
    emits = []
    hub = type("H", (), {"emit": lambda self, e: emits.append(e)})()

    bridge = Bridge.__new__(Bridge)
    bridge.agent = agent
    bridge.server = server
    bridge.hub = hub
    bridge._busy = False
    bridge.loop = asyncio.new_event_loop()
    return bridge, agent, rebinds, emits


def test_new_session_swaps_and_rebinds(tmp_path):
    bridge, agent, rebinds, emits = _bridge_with_session(tmp_path)
    old_id = agent.session.id

    res = bridge.new_session()

    assert res["ok"] and res["id"] != old_id and not res["resumed"]
    assert agent.session.id == res["id"]
    assert agent.mind.session_id == res["id"]     # zihin kimliği de geçti
    assert agent._last_encoded == ""              # encode dedup sıfırlandı
    assert rebinds == [res["id"]]                 # olay akışı yeni günlüğe bağlandı
    assert any(e["type"] == "session_reset" for e in emits)   # kanal
    # anlık görüntüsü session_reset'ten sonra geliyor (orkestra tohumu)
    bridge.loop.close()


def test_resume_session_loads_existing(tmp_path):
    from neocp.events import EventLog
    bridge, agent, rebinds, emits = _bridge_with_session(tmp_path)
    # var olan bir oturum günlüğü
    log = EventLog(agent.config.sessions_dir / "20260610T090000Z.jsonl")
    log.append("message", role="user", content="çorum pompa verimi")
    log.close()

    res = bridge.resume_session("20260610T090000Z")

    assert res["ok"] and res["resumed"] and res["id"] == "20260610T090000Z"
    assert agent.session.id == "20260610T090000Z"
    assert agent.mind.session_id == "20260610T090000Z"
    assert rebinds[-1] == "20260610T090000Z"
    bridge.loop.close()


def test_resume_missing_session_is_reported(tmp_path):
    bridge, agent, *_ = _bridge_with_session(tmp_path)
    res = bridge.resume_session("yok_20990101T000000Z")
    assert not res["ok"] and "bulunamadı" in res["error"]
    bridge.loop.close()


def test_switching_away_while_busy_opens_a_parallel_lane(tmp_path):
    """Eski sözleşme reddetmekti ("neo meşgul; tur bitince dene") —
    canlı istekle değişti (29.08): koşan şeride dokunulmaz, yeni
    sohbet AYRI bir şeritte hemen açılır."""
    bridge, agent, rebinds, _ = _bridge_with_session(tmp_path)
    agent.client = object()          # şerit fabrikası istemciyi paylaşır
    eski_oturum = agent.session.id
    bridge._busy = True
    res = bridge.new_session()
    assert res["ok"], res
    # Koşan şerit yerinde: eski ajanın oturumu DEĞİŞMEDİ ve hâlâ meşgul.
    assert agent.session.id == eski_oturum
    assert bridge.seritler[eski_oturum].busy is True
    # Aktif şerit artık yeni oturum; ajanı başka bir ajan.
    assert bridge.agent is not agent
    assert res["id"] in bridge.seritler and rebinds[-1] == res["id"]
    bridge.loop.close()


def test_snapshot_surumu_tasir(config: Config) -> None:
    """Ayarlar › Makine'deki salt-okunur sürüm satırı buradan besleniyor.

    Sahada hangi sürümün kurulu olduğu görünmüyordu; alan pyproject'teki
    gerçek sürümle birebir aynı olmalı — ikinci bir sürüm kaynağı yok.
    """
    from neocp import ortam

    kar = settings.snapshot(config)
    assert kar["surum"] == ortam.surum()
    assert kar["surum"] not in ("", "0.0.0")


def test_catalog_providers_have_unique_ids_and_openai_urls() -> None:
    """Önayarlar çakışmasın; openai protokolü gerçek uç kalıbında olsun."""
    ids = [e["id"] for e in settings.PROVIDERS]
    assert len(ids) == len(set(ids))
    assert {"gemini", "nvidia", "deepseek", "groq", "mistral", "qwen"} <= set(ids)
    for entry in settings.PROVIDERS:
        if entry["provider"] != "openai" or not entry["base_url"]:
            continue
        url = str(entry["base_url"])
        assert url.startswith("http"), entry["id"]
        assert (
            "localhost" in url
            or url.rstrip("/").endswith("/v1")
            or url.rstrip("/").endswith("/openai")
            or "deepseek.com" in url
        ), entry


def test_openai_models_request_sends_bearer(
    config: Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Gemini / Groq gibi uçlar anahtarsız 401/404 verir; Bearer şart."""
    seen: dict[str, str] = {}

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b'{"data":[{"id":"gemini-2.5-flash"}]}'

    def fake_urlopen(req, timeout=0):  # noqa: ARG001
        seen["auth"] = req.get_header("Authorization") or ""
        seen["url"] = req.full_url
        return _Resp()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.setenv("GEMINI_API_KEY", "sk-test-gemini")
    updated = settings.apply(config, {"provider": "gemini", "name": "gemini-2.5-flash"})
    names = settings.available_models(updated)
    assert names == ["gemini-2.5-flash"]
    assert seen["auth"] == "Bearer sk-test-gemini"
    assert seen["url"].endswith("/v1beta/openai/models")

def test_background_lane_events_do_not_leak_into_the_active_chat(tmp_path):
    """Paralel şeritlerin görünmez direği: arka şeridin metin/araç
    olayları aktif sohbete sızmaz; onay istekleri ise HER şeritten
    geçer (yoksa arka tur sonsuza dek bekler)."""
    bridge, agent, rebinds, emits = _bridge_with_session(tmp_path)
    agent.client = object()
    bridge._busy = True
    res = bridge.new_session()
    assert res['ok']
    eski = bridge.seritler[agent.session.id]
    yeni = bridge.seritler[res['id']]
    emits.clear()
    # Arka şeridin io'su: metin olayı yayına DÜŞMEZ.
    arka_io = bridge.io(eski)
    arka_io.on_text('sizmamali')
    assert emits == []
    # Aktif şeridin io'su: aynı olay yayına düşer.
    on_io = bridge.io(yeni)
    on_io.on_text('gorunmeli')
    assert any(e.get('type') == 'assistant_delta' for e in emits)
    bridge.loop.close()

