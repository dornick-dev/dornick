"""Davranış refleksleri: plan kapısı ve kırmızıyken "bitti" deme kapısı.

İkisi de aynı dersten doğdu: **öğüt yetmiyor.** İstemde hem "büyük işte
önce modül planını yaz" hem de "bitti demeden doğrula" YAZIYOR; yedi
görevlik bir ölçümde yedisinde de plan yazılmadı ve bir görev kendi test
takımı kırmızıyken teslim edildi. Kalıcı hafıza yazma sorununda olduğu
gibi çözüm harness tarafında bir refleks: konuyu, tam gerektiği anda,
modelin önüne koymak.

Buradaki testler o reflekslerin **ne zaman ateşlenmediğini** de tutuyor —
her mesajda plan isteyen bir kapı, hiç plan istemeyen bir kapı kadar
kötüdür.
"""

from __future__ import annotations

import asyncio
import json
import urllib.request
from pathlib import Path
from typing import Any

import pytest

from neocp.config import Config
from neocp.events import EventLog
from neocp.loop import (
    KIRMIZI_NOTU,
    PLAN_NOTU,
    bitti_iddiasi,
    buyuk_is,
    kirmizi_iz,
)
from neocp.mind import Mind, open_mind
from neocp.prompt import build as build_prompt
from neocp.tools import ToolRegistry, build_registry
from neocp.web import MindServer

from .test_loop import FakeClient, build_agent, text_turn, tool_turn


# -- 1) plan refleksi: sinyal -------------------------------------------


@pytest.mark.parametrize("istek", [
    "gelişmiş bir yönetim paneli yap",
    "bana bir web sitesi yap, ürünleri listelesin",
    "Python ile küçük bir kısa-link servisi istiyorum, sen kur",
    "şöyle bir uygulama geliştir: kullanıcı girişi olsun",
    "create a dashboard for the sensor data",
])
def test_a_big_open_ended_request_is_recognised(istek: str) -> None:
    """Ölçek sözü + yapım fiili: ortada tek dosyalık bir betik yok."""
    assert buyuk_is(istek) is True


@pytest.mark.parametrize("istek", [
    "",
    "naber",
    "app.py'yi çalıştır",
    "şu fonksiyondaki hatayı düzelt",
    "bu dosyada kaç satır var?",
    "README'yi oku ve özetle",
    # Yapım fiili var ama ölçek yok: tek dosyalık küçük iş.
    "bir kenar boşluğu ekle",
    # Ölçek sözü var ama yapım fiili yok: soru soruyor.
    "panel neden açılmıyor?",
])
def test_a_small_request_never_asks_for_a_plan(istek: str) -> None:
    """Yanlış pozitifin bedeli gereksiz bir plan; her mesajda plan istemek
    kapının kendisini gürültüye çevirir."""
    assert buyuk_is(istek) is False


def test_a_long_multi_delivery_request_counts_even_without_a_scale_word() -> None:
    """Çoklu teslimat kendi başına büyüklük sinyali."""
    istek = (
        "şunları hazırla:\n"
        "- bir toplama betiği\n"
        "- bir temizleme betiği\n"
        "- bir de özet çıktısı\n"
    )
    assert buyuk_is(istek) is True


# -- 1) plan refleksi: döngüdeki davranış -------------------------------


def _harness_notlari(agent: Any) -> list[str]:
    """Oturumdaki iç (harness) notlarının metinleri."""
    out: list[str] = []
    for message in agent.session.messages():
        content = message.get("content")
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    out.append(str(block.get("text") or ""))
        elif isinstance(content, str):
            out.append(content)
    return out


def test_the_plan_note_lands_before_the_model_is_ever_called(tmp_path: Path) -> None:
    """Not İLK istekte modelin önünde olmalı: plan sıradan sonra yazılmaz."""
    client = FakeClient(text_turn("tamam"))
    agent = build_agent(tmp_path, client, ToolRegistry())

    asyncio.run(agent.run("gelişmiş bir yönetim paneli yap"))

    ilk_istek = json.dumps(client.seen_messages[0], ensure_ascii=False)
    assert PLAN_NOTU in ilk_istek
    assert "modül listesi" in ilk_istek


def test_the_plan_note_fires_once_per_turn(tmp_path: Path) -> None:
    """Tur boyunca bir kez: her araç turunda tekrarlanan bir not bıkkınlık."""
    client = FakeClient(
        tool_turn(("c1", "read_file", {"path": "x"})),
        text_turn("bitti"),
    )
    registry = ToolRegistry()
    agent = build_agent(tmp_path, client, registry)

    asyncio.run(agent.run("gelişmiş bir yönetim paneli yap"))

    kac = sum(1 for metin in _harness_notlari(agent) if PLAN_NOTU in metin)
    assert kac == 1


def test_a_small_request_leaves_the_context_untouched(tmp_path: Path) -> None:
    client = FakeClient(text_turn("baktım"))
    agent = build_agent(tmp_path, client, ToolRegistry())

    asyncio.run(agent.run("bu dosyada kaç satır var?"))

    assert PLAN_NOTU not in json.dumps(client.seen_messages, ensure_ascii=False)


def test_the_plan_note_never_reaches_the_conversation(tmp_path: Path) -> None:
    """İç not: kullanıcının yazmadığı bir metin sohbette mesaj gibi durmamalı."""
    client = FakeClient(text_turn("tamam"))
    agent = build_agent(tmp_path, client, ToolRegistry())
    asyncio.run(agent.run("gelişmiş bir panel yap"))

    plan_olaylari = [
        ev for ev in agent.session.log.messages()
        if PLAN_NOTU in json.dumps(ev.content, ensure_ascii=False)
    ]
    assert plan_olaylari, "not günlüğe hiç düşmemiş"
    assert all(ev.meta.get("internal") for ev in plan_olaylari)


# -- 2) kırmızı izi: sinyal ---------------------------------------------


def test_a_failing_run_is_red() -> None:
    """`kos` kırmızıyı kendisi işaretliyor (is_error)."""
    note = {"tool": "kos", "error": True,
            "summary": "1 test başarısız, 6 geçti", "detail": {"output": "…"}}
    assert kirmizi_iz("kos", note) == "1 test başarısız, 6 geçti"


def test_the_summary_drops_the_interface_volume_marker() -> None:
    """"(+22 satır)" aracın hükmü değil, arayüzün hacim izi — nota girmez."""
    note = {"tool": "kos", "error": True,
            "summary": "1 geçti, 1 kaldı.  (+22 satır)", "detail": {}}
    assert kirmizi_iz("kos", note) == "1 geçti, 1 kaldı."


def test_a_green_run_is_not_red() -> None:
    note = {"tool": "kos", "error": False, "summary": "7 test geçti", "detail": {}}
    assert kirmizi_iz("kos", note) == ""


def test_a_diagnostic_error_is_red_even_though_the_tool_did_not_fail() -> None:
    """`denetle` bir bulguyu is_error ile işaretlemiyor: bir denetim
    bulgusu yazmayı düşürmemeli. Kırmızı kendi metninde yazıyor."""
    note = {"tool": "denetle", "error": False,
            "summary": "Home.php — php -l, 1 hata:",
            "detail": {"output": "Home.php — php -l, 1 hata:\n  satır 12: syntax error"}}
    assert kirmizi_iz("denetle", note)


def test_a_clean_diagnostic_is_not_red() -> None:
    note = {"tool": "denetle", "error": False,
            "summary": "3 dosya denetlendi, hepsi temiz", "detail": {}}
    assert kirmizi_iz("denetle", note) == ""


def test_console_errors_and_failed_requests_are_red() -> None:
    """Tarayıcı dökümü hiç hata döndürmüyor; sayılar başlıkta."""
    konsol = {"tool": "browser", "error": False,
              "summary": "12 konsol kaydı (3 hata) — son 20 tanesi:", "detail": {}}
    assert "3 hata" in kirmizi_iz("browser", konsol)

    ag = {"tool": "browser", "error": False,
          "summary": "18 istek · 2 başarısız.", "detail": {}}
    assert "2 başarısız" in kirmizi_iz("browser", ag)

    temiz = {"tool": "browser", "error": False,
             "summary": "9 konsol kaydı (0 hata) — son 9 tanesi:", "detail": {}}
    assert kirmizi_iz("browser", temiz) == ""


def test_a_failing_read_is_not_a_red_run() -> None:
    """Kırmızı kavramı yalnız doğrulama araçları için tanımlı: başarısız bir
    okuma bir koşum değil."""
    note = {"tool": "read_file", "error": True, "summary": "Dosya yok", "detail": {}}
    assert kirmizi_iz("read_file", note) == ""


@pytest.mark.parametrize("cevap,beklenen", [
    ("Hazır, servis 8099'da çalışıyor.", True),
    ("Bitti.", True),
    ("Tamamlandı — testleri de yazdım.", True),
    ("All tests pass, done.", True),
    # Kırmızıyı zaten söyleyen cevap dürüsttür: dürtülmez.
    ("Bitti ama iki test hâlâ başarısız.", False),
    ("Hazır; şu an konsolda hata var, ona bakıyorum.", False),
    # Bitirme iddiası hiç yok.
    ("Şimdi testleri koşturuyorum.", False),
])
def test_the_done_claim_is_recognised_but_an_honest_report_is_not(
    cevap: str, beklenen: bool
) -> None:
    assert bitti_iddiasi(cevap) is beklenen


# -- 2) kırmızı kapısı: döngüdeki davranış -------------------------------


def _kirmizi_kos_araci(registry: ToolRegistry) -> None:
    """Her zaman kırmızı dönen sahte bir `kos`."""
    from neocp.tools import ToolResult, object_schema

    @registry.tool(name="kos", description="test koşucusu (sahte)",
                   input_schema=object_schema({"kok": {"type": "string"}}))
    async def kos(args: dict[str, Any], ctx: Any) -> ToolResult:
        return ToolResult("1 test başarısız, 6 geçti", is_error=True,
                          detail={"kalan": 1, "gecen": 6, "cikis_kodu": 1})


def _yesil_kos_araci(registry: ToolRegistry) -> None:
    from neocp.tools import ToolResult, object_schema

    @registry.tool(name="kos", description="test koşucusu (sahte)",
                   input_schema=object_schema({"kok": {"type": "string"}}))
    async def kos(args: dict[str, Any], ctx: Any) -> ToolResult:
        return ToolResult("7 test geçti", detail={"kalan": 0, "gecen": 7})


def test_saying_done_over_a_red_run_buys_one_more_turn(tmp_path: Path) -> None:
    """Ölçümde yaşanan tam hâli: takım kırmızıyken "hazır" denip teslim."""
    registry = ToolRegistry()
    _kirmizi_kos_araci(registry)
    client = FakeClient(
        tool_turn(("c1", "kos", {"kok": "."})),
        text_turn("Hazır, her şey çalışıyor."),
        text_turn("Haklısın — bir test kırmızı, düzeltiyorum."),
    )
    agent = build_agent(tmp_path, client, registry)

    stats = asyncio.run(agent.run("servisi yaz ve testlerini koştur"))

    notlar = [n for n in _harness_notlari(agent) if "[Doğrulama]" in n]
    assert len(notlar) == 1, notlar
    assert "kırmızıydı" in notlar[0]
    # Bir tur DAHA verildi: model kapatamadı.
    assert stats.turns == 3
    assert stats.kirmizi_uyarildi is True


def test_a_green_run_closes_the_turn_normally(tmp_path: Path) -> None:
    registry = ToolRegistry()
    _yesil_kos_araci(registry)
    client = FakeClient(
        tool_turn(("c1", "kos", {"kok": "."})),
        text_turn("Hazır, testler geçti."),
    )
    agent = build_agent(tmp_path, client, registry)

    stats = asyncio.run(agent.run("servisi yaz ve testlerini koştur"))

    assert not [n for n in _harness_notlari(agent) if "[Doğrulama]" in n]
    assert stats.turns == 2
    assert stats.kirmizi_uyarildi is False


def test_fixing_the_red_and_rerunning_green_reopens_the_door(tmp_path: Path) -> None:
    """Yeşile dönen koşum kaydı siliyor: düzeltip yeniden koşturan model
    kapıya çarpmamalı."""
    from neocp.tools import ToolResult, object_schema

    registry = ToolRegistry()
    sayac = {"n": 0}

    @registry.tool(name="kos", description="test koşucusu (sahte)",
                   input_schema=object_schema({"kok": {"type": "string"}}))
    async def kos(args: dict[str, Any], ctx: Any) -> ToolResult:
        sayac["n"] += 1
        if sayac["n"] == 1:
            return ToolResult("1 test başarısız", is_error=True, detail={"kalan": 1})
        return ToolResult("7 test geçti", detail={"kalan": 0})

    client = FakeClient(
        tool_turn(("c1", "kos", {"kok": "."})),
        tool_turn(("c2", "kos", {"kok": "."})),
        text_turn("Hazır, testler geçti."),
    )
    agent = build_agent(tmp_path, client, registry)

    stats = asyncio.run(agent.run("servisi yaz ve testlerini koştur"))

    assert not [n for n in _harness_notlari(agent) if "[Doğrulama]" in n]
    assert stats.kirmizi_uyarildi is False


def test_the_door_opens_at_most_once(tmp_path: Path) -> None:
    """Model ikinci turda yine bitirmek isterse bırakılıyor: sonsuz bir
    "hayır bitmedi" döngüsü yarım bir cevaptan kötü."""
    registry = ToolRegistry()
    _kirmizi_kos_araci(registry)
    client = FakeClient(
        tool_turn(("c1", "kos", {"kok": "."})),
        text_turn("Hazır."),
        text_turn("Yine de hazır diyorum."),
        text_turn("Ve yine."),
    )
    agent = build_agent(tmp_path, client, registry)

    stats = asyncio.run(agent.run("servisi yaz ve testlerini koştur"))

    notlar = [n for n in _harness_notlari(agent) if "[Doğrulama]" in n]
    assert len(notlar) == 1
    # Üçüncü tur kapandı: dördüncü cevap hiç istenmedi.
    assert stats.turns == 3


def test_an_honest_report_over_a_red_run_is_left_alone(tmp_path: Path) -> None:
    """Kırmızıyı söyleyen cevap dürüsttür — kapı ona çarpmaz."""
    registry = ToolRegistry()
    _kirmizi_kos_araci(registry)
    client = FakeClient(
        tool_turn(("c1", "kos", {"kok": "."})),
        text_turn("Servisi yazdım ama bir test hâlâ başarısız; sebebi şu."),
    )
    agent = build_agent(tmp_path, client, registry)

    stats = asyncio.run(agent.run("servisi yaz ve testlerini koştur"))

    assert not [n for n in _harness_notlari(agent) if "[Doğrulama]" in n]
    assert stats.turns == 2


def test_the_red_ledger_does_not_leak_into_the_next_turn(tmp_path: Path) -> None:
    """"Yalnız BU TURDA üretilmiş kırmızı sayılsın": geçen turun kırmızısı
    yeni bir isteği engellememeli."""
    registry = ToolRegistry()
    _kirmizi_kos_araci(registry)
    client = FakeClient(
        tool_turn(("c1", "kos", {"kok": "."})),
        text_turn("Bir test kırmızı."),
    )
    agent = build_agent(tmp_path, client, registry)
    asyncio.run(agent.run("testleri koştur"))
    assert agent._kirmizi, "ilk turda kırmızı kaydedilmemiş"

    client.script = [text_turn("Hazır.")]
    stats = asyncio.run(agent.run("teşekkürler"))

    assert not [n for n in _harness_notlari(agent) if "[Doğrulama]" in n]
    assert stats.kirmizi_uyarildi is False


def test_the_verification_note_never_reaches_the_conversation(tmp_path: Path) -> None:
    registry = ToolRegistry()
    _kirmizi_kos_araci(registry)
    client = FakeClient(
        tool_turn(("c1", "kos", {"kok": "."})),
        text_turn("Hazır."),
        text_turn("Peki, düzeltiyorum."),
    )
    agent = build_agent(tmp_path, client, registry)
    asyncio.run(agent.run("testleri koştur"))

    olaylar = [ev for ev in agent.session.log.messages()
               if "[Doğrulama]" in json.dumps(ev.content, ensure_ascii=False)]
    assert olaylar
    assert all(ev.meta.get("internal") for ev in olaylar)


def test_the_note_template_says_what_to_do_not_just_what_is_wrong() -> None:
    """Not bir suçlama değil bir sıra kuralı: düzelt ya da açıkça söyle."""
    metin = KIRMIZI_NOTU.format(ozet="1 test başarısız")
    assert "düzelt" in metin and "açıkça söyle" in metin


# -- 3) prompt eklemeleri ------------------------------------------------


@pytest.fixture()
def core(tmp_path: Path) -> str:
    config = Config.load(tmp_path)
    config.ensure_dirs()
    return build_prompt(config, build_registry()).core


def test_the_prompt_separates_syntax_checking_from_running(core: str) -> None:
    """`denetle` geçti demek çalışıyor demek değil — ölçümde tam olarak bu
    karışıklıkla teslim yapıldı."""
    assert "yalnız SÖZDİZİMİNE bakar" in core
    assert "ÇALIŞTIRMAKTIR" in core
    assert "`kos`" in core
    assert "koşulanların kapsadığı kadarı doğrulandı" in core
    assert "proje test taşımıyorsa" in core


def test_the_prompt_gives_the_real_web_verification_sequence(core: str) -> None:
    """"200 döndü" bir doğrulama değil: boş bir sayfa da 200 döner."""
    assert "200 dönmesine bakma" in core
    for adim in ("`konsol`", "`ag`", "`read`"):
        assert adim in core, adim
    assert 'hata varken "çalışıyor" deme' in core
    # Sayfaya yama atmak düzeltmek değil: yama yenileyince gider.
    assert "kaynağı düzelt" in core


def test_the_prompt_asks_for_callers_before_changing_a_signature(core: str) -> None:
    assert "`semboller`" in core
    assert "imzasını değiştirmeden önce" in core
    assert "`grep`" in core


def test_the_manifest_rule_says_where_and_how(core: str) -> None:
    assert "atolye/<uygulama>/app.json" in core
    assert "GÖRELİDİR" in core
    assert "`port`" in core


def test_the_prompt_forbids_restarting_neo(core: str) -> None:
    """Model kafası karışıp kendi programını yeniden başlatınca kullanıcı
    kendi uygulamasının klonuyla karşılaşıyor."""
    assert "asla yeniden başlatma" in core
    assert "neocp" in core


# -- 4) uyandırma rotası -------------------------------------------------


@pytest.fixture()
def mind(tmp_path: Path) -> Mind:
    return open_mind(tmp_path / "mind", tmp_path / "sessions", "cur")


class SahteKoprü:
    def __init__(self) -> None:
        self.uyandirildi = 0

    def snapshot(self) -> dict[str, Any]:
        return {"busy": False}

    def wake(self) -> None:
        self.uyandirildi += 1


def test_the_wake_word_can_raise_the_window(tmp_path: Path, mind: Mind) -> None:
    """Tarayıcı tarafındaki uyandırma sözünün tek yolu bu rotaydı ve rota
    YOKTU: istek sessizce 404 dönüyor, pencere gizli kalıyordu."""
    config = Config.load(tmp_path)
    config.ensure_dirs()
    log = EventLog(tmp_path / "s.jsonl")
    koprü = SahteKoprü()
    server = MindServer(mind, log, port=0, config=config, controller=koprü)  # type: ignore[arg-type]
    server.start()
    try:
        request = urllib.request.Request(
            server.url + "api/wake", data=b"{}",
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=8) as answer:
            body = json.loads(answer.read().decode("utf-8"))
    finally:
        server.stop()
        log.close()

    assert body["ok"] is True
    assert koprü.uyandirildi == 1


def test_a_bridge_that_cannot_wake_says_so(tmp_path: Path, mind: Mind) -> None:
    """"Yaptım" demek yapmamaktan kötü."""
    from types import SimpleNamespace

    config = Config.load(tmp_path)
    config.ensure_dirs()
    log = EventLog(tmp_path / "s.jsonl")
    server = MindServer(mind, log, port=0, config=config,
                        controller=SimpleNamespace(snapshot=lambda: {}))  # type: ignore[arg-type]
    server.start()
    try:
        request = urllib.request.Request(
            server.url + "api/wake", data=b"{}",
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=8) as answer:
            body = json.loads(answer.read().decode("utf-8"))
    finally:
        server.stop()
        log.close()

    assert body["ok"] is False


def test_the_page_still_calls_the_route_it_needs() -> None:
    """Çağrı ile rota birlikte yaşamalı: biri kalkarsa öteki ölü kod."""
    static = Path(__file__).resolve().parents[1] / "src" / "neocp" / "web" / "static"
    app_js = (static / "app.js").read_text(encoding="utf-8")
    server = (Path(__file__).resolve().parents[1] / "src" / "neocp" / "web"
              / "server.py").read_text(encoding="utf-8")
    assert '"/api/wake"' in app_js
    assert '"/api/wake"' in server
