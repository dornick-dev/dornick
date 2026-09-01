"""Maliyet çipinin veri yolu: fiyat kataloğu ve usage-olayı sözleşmesi.

İki katman test ediliyor:

  * `fiyat` modülü — OpenRouter kataloğundan fiyat tablosu; ağ disiplini
    (tur içinde asla ağ yok) ve önbellek sırası.
  * `Bridge._usage_yay` — arayüzdeki çipin okuduğu olay sözleşmesi:
    tur/oturum toplamları, fiyat etiketi, yeni turda sıfırlama.
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from dornick import fiyat
from dornick.config import OPENROUTER_URL, Config, ModelConfig

pytestmark = []


def _entry(mid: str, prompt, completion, **extra) -> dict:
    return {"id": mid, "pricing": {"prompt": prompt, "completion": completion}, **extra}


# -- katalog süzgeci ----------------------------------------------------


def test_the_price_table_is_parsed_from_strings() -> None:
    """OpenRouter fiyatı dize döndürüyor ("0.000003"); sayıya çevrilmeli."""
    tablo = fiyat.suz([
        _entry("acme/pahali", "0.000015", "0.000075"),
        _entry("acme/bedava", "0", "0.000000"),
    ])
    assert tablo["acme/pahali"] == {"girdi": 1.5e-05, "cikti": 7.5e-05}
    assert tablo["acme/bedava"] == {"girdi": 0.0, "cikti": 0.0}


def test_a_broken_entry_does_not_drop_the_table() -> None:
    """Tek bozuk kayıt (fiyatsız, sayı olmayan, negatif, kimliksiz)
    sessizce atlanır — tablo düşmez."""
    tablo = fiyat.suz([
        {"id": "x/fiyatsiz"},                       # pricing yok
        _entry("x/bozuk", "bedava", "çok"),          # sayı değil
        _entry("x/eksi", "-1", "0.1"),               # negatif: bozuk kayıt
        {"pricing": {"prompt": "0", "completion": "0"}},  # kimliksiz
        "dize",                                       # sözlük bile değil
        _entry("x/saglam", "0.000001", "0.000002"),
    ])
    assert list(tablo) == ["x/saglam"]


# -- önbellek sırası ve ağ disiplini ------------------------------------


def test_the_turn_path_never_touches_the_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`ag=False` (turun içindeki yol) hiçbir koşulda ağa çıkmaz."""

    def _patlar() -> dict:
        raise AssertionError("tur içinde ağ isteği yapıldı")

    monkeypatch.setattr(fiyat, "_indir", _patlar)
    assert fiyat.tablo(tmp_path, ag=False) == {}


def test_a_fresh_download_is_cached_to_disk_and_memory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sayac = []
    monkeypatch.setattr(
        fiyat, "_indir",
        lambda: sayac.append(1) or {"m/a": {"girdi": 1e-06, "cikti": 2e-06}},
    )

    once = fiyat.tablo(tmp_path, ag=True)
    assert once["m/a"]["cikti"] == 2e-06
    # Disk kaydı yazıldı ve ikinci çağrı ağa dönmüyor.
    kayit = json.loads((tmp_path / fiyat.FIYAT_DOSYA).read_text(encoding="utf-8"))
    assert kayit["fiyatlar"]["m/a"]["girdi"] == 1e-06
    assert fiyat.tablo(tmp_path, ag=True) == once
    assert len(sayac) == 1, "taze önbellek varken yeniden indirilmemeli"


def test_a_stale_table_still_serves_when_the_network_is_gone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ağ yokken bayat tablo hiç yoktan iyi — otomod havuz kalıbının aynısı."""
    (tmp_path / fiyat.FIYAT_DOSYA).write_text(json.dumps({
        "ts": time.time() - 2 * fiyat.TAZELIK_SN,
        "fiyatlar": {"m/eski": {"girdi": 3e-06, "cikti": 4e-06}},
    }), encoding="utf-8")
    monkeypatch.setattr(fiyat, "_indir", lambda: {})

    assert fiyat.tablo(tmp_path, ag=True)["m/eski"]["cikti"] == 4e-06


# -- etiket -------------------------------------------------------------


def _openrouter(name: str) -> ModelConfig:
    return ModelConfig(name=name, base_url=OPENROUTER_URL)


def test_the_label_only_speaks_for_openrouter(tmp_path: Path) -> None:
    """Yerel sunucunun modeli bu katalogda yok: None → çip token gösterir."""
    yerel = ModelConfig(name="qwen/q3", base_url="http://localhost:1234/v1")
    assert fiyat.etiket(yerel, tmp_path) is None


def test_the_free_pool_costs_zero(tmp_path: Path) -> None:
    """Oto kipi ücretsiz havuzla çalışıyor: fiyat sıfır, bilinmiyor değil."""
    assert fiyat.etiket(_openrouter("oto"), tmp_path) == {"girdi": 0.0, "cikti": 0.0}


def test_an_unknown_model_yields_none_a_known_one_its_price(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        fiyat, "_indir", lambda: {"m/a": {"girdi": 1e-06, "cikti": 2e-06}}
    )
    assert fiyat.etiket(_openrouter("m/a"), tmp_path, ag=True) == {
        "girdi": 1e-06, "cikti": 2e-06,
    }
    assert fiyat.etiket(_openrouter("m/yok"), tmp_path) is None


# -- usage-olayı sözleşmesi (Bridge) ------------------------------------


class _Hub:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def emit(self, payload: dict) -> None:
        self.events.append(payload)

    def only(self, kind: str) -> list[dict]:
        return [e for e in self.events if e.get("type") == kind]


def _rapor(prompt_total: int, output: int) -> dict:
    return {
        "cache_read": 0, "cache_write": 0, "uncached": prompt_total,
        "output": output, "prompt_total": prompt_total,
    }


def _bridge(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Sahte ajanla köprü: model çağrısı yok, fiyat için ağ yok."""
    from dornick import desktop as desktop_module
    from dornick.desktop import Bridge

    # Arka plan fiyat thread'i ağa çıkmasın; test etiketi kendisi verir.
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
    """Sözleşme: her usage olayında cache_report alanları + tur/oturum
    toplamları + fiyat etiketi (bilinmiyorsa None) birlikte gider."""
    bridge, hub = _bridge(tmp_path, monkeypatch)

    bridge._usage_yay(_rapor(1000, 50))
    bridge._usage_yay(_rapor(1400, 70))

    olaylar = hub.only("usage")
    assert len(olaylar) == 2
    son = olaylar[-1]
    # cache_report alanları aynen duruyor (bağlam göstergesi bunları okuyor).
    assert son["prompt_total"] == 1400 and son["output"] == 70
    # Toplamlar çağrı üstüne çağrı birikiyor.
    assert son["tur"] == {"girdi": 2400, "cikti": 120, "cagri": 2}
    assert son["oturum"] == son["tur"]
    # Fiyat bilinmiyor: None — çip token sayısına düşer, uydurma dolar yok.
    assert son["fiyat"] is None
    # Bağlam kutusunun kalem kalem kırılımı aynı olayda gider.
    assert {p["id"] for p in son["kirilim"]} == {
        "sistem", "arac", "ruh", "yetenek", "mcp", "yardimci", "sohbet"}
    assert sum(p["n"] for p in son["kirilim"]) == 1400


async def test_a_new_user_turn_resets_the_turn_total_not_the_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bridge, hub = _bridge(tmp_path, monkeypatch)

    async def _kos(text: str, image: str) -> None:
        bridge._usage_yay(_rapor(500, 20))

    bridge.agent.run = _kos
    monkeypatch.setattr(
        "dornick.settings.yapilandirilmamis", lambda model: False)

    await bridge._isle("ilk iş", "")
    await bridge._isle("ikinci iş", "")

    son = hub.only("usage")[-1]
    assert son["tur"] == {"girdi": 500, "cikti": 20, "cagri": 1}, \
        "yeni kullanıcı mesajı tur toplamını sıfırlamalı"
    assert son["oturum"] == {"girdi": 1000, "cikti": 40, "cagri": 2}, \
        "oturum toplamı sıfırlanmamalı"


async def test_the_price_label_arrives_in_the_background(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Etiket bulunduğunda `fiyat` olayı yayınlanır ve sonraki usage
    olayları etiketi taşır; ağa oturumda EN FAZLA bir kez çıkılır."""
    from dornick import desktop as desktop_module

    bridge, hub = _bridge(tmp_path, monkeypatch)
    sayac = []

    def _etiket(*a, **k):
        sayac.append(1)
        return {"girdi": 1e-06, "cikti": 2.5e-05}

    monkeypatch.setattr(desktop_module.fiyatlama, "etiket", _etiket)

    bridge._usage_yay(_rapor(1000, 50))
    # Arka plan thread'i bitene kadar bekle (anında dönüyor; sınır emniyet).
    for _ in range(200):
        if hub.only("fiyat"):
            break
        await asyncio.sleep(0.01)

    fiyat_olay = hub.only("fiyat")
    assert fiyat_olay and fiyat_olay[0]["fiyat"]["cikti"] == 2.5e-05

    bridge._usage_yay(_rapor(500, 10))
    assert hub.only("usage")[-1]["fiyat"] == {"girdi": 1e-06, "cikti": 2.5e-05}
    assert len(sayac) == 1, "fiyata oturumda bir kez bakılmalı"


async def test_the_snapshot_seeds_the_cost_chip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sayfa yenilenince çip sıfırdan değil kaldığı yerden başlar."""
    bridge, hub = _bridge(tmp_path, monkeypatch)
    bridge._usage_yay(_rapor(1000, 50))

    kare = bridge.snapshot()
    assert kare["kullanim"]["oturum"] == {"girdi": 1000, "cikti": 50, "cagri": 1}
    assert kare["kullanim"]["tur"]["cagri"] == 1
    assert kare["fiyat"] is None
