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
    assert "TEK doğrulama turu" in core or "`read`" in core
    assert "`konsol`" in core and "`ag`" in core
    assert '"çalışıyor" deme' in core
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


# -- 3) teslim edileni ÇALIŞTIRMA kapısı --------------------------------
#
# Ölçümün en keskin sonucu: 14 geçen test, 18 gerçek iddia, kod sağlığı
# 20/20 — ve istemin asıl istediği komut satırı hiç çalışmıyor. Testler iç
# fonksiyonları çağırıyor, kullanıcı ise komutu yazıyor. Kırmızı kapısı bu
# vakayı yakalayamaz: takım YEŞİLDİ.


def _yazan_arac(registry: ToolRegistry, kok: Path) -> None:
    """Gerçekten dosya yazan sahte bir `write_file`."""
    from neocp.tools import ToolResult, object_schema

    @registry.tool(name="write_file", description="yaz",
                   input_schema=object_schema({"path": {"type": "string"},
                                               "content": {"type": "string"}}),
                   mutates=True)
    async def _yaz(args, _ctx) -> ToolResult:
        yol = Path(args["path"])
        yol.parent.mkdir(parents=True, exist_ok=True)
        yol.write_text(args.get("content", ""), encoding="utf-8")
        return ToolResult(f"{yol.name} yazıldı.")


def _kabuk_araci(registry: ToolRegistry) -> None:
    from neocp.tools import ToolResult, object_schema

    @registry.tool(name="shell", description="koş",
                   input_schema=object_schema({"command": {"type": "string"}}),
                   mutates=True)
    async def _kos(args, _ctx) -> ToolResult:
        return ToolResult("çıkış 0")


CLI_KAYNAK = (
    "import sys\n\n"
    "def bul(kelime):\n    return []\n\n"
    'if __name__ == "__main__":\n'
    "    print(sys.argv)\n"
)
KUTUPHANE_KAYNAK = "def topla(a, b):\n    return a + b\n"


def test_a_written_entry_point_that_was_never_run_buys_one_more_turn(
    tmp_path: Path,
) -> None:
    """Yaşanmış vaka: CLI yazıldı, testler yeşil, komut hiç çalıştırılmadı."""
    registry = ToolRegistry()
    _yazan_arac(registry, tmp_path)
    hedef = tmp_path / "ara.py"
    client = FakeClient(
        tool_turn(("c1", "write_file", {"path": str(hedef), "content": CLI_KAYNAK})),
        text_turn("Hazır, arama aracı çalışıyor."),
        text_turn("Haklısın — komutu çalıştırıp çıktısına bakıyorum."),
    )
    agent = build_agent(tmp_path, client, registry)

    stats = asyncio.run(agent.run("bir not arama aracı yaz"))

    notlar = [n for n in _harness_notlari(agent) if "[Doğrulama]" in n]
    assert len(notlar) == 1, notlar
    assert "ara.py" in notlar[0]
    assert "ÇALIŞTIRMADIN" in notlar[0]
    assert stats.turns == 3
    assert stats.giris_uyarildi is True


def test_running_the_entry_point_closes_the_turn_normally(tmp_path: Path) -> None:
    """Kullanıcının yazacağı komutu çalıştıran model dürtülmüyor."""
    registry = ToolRegistry()
    _yazan_arac(registry, tmp_path)
    _kabuk_araci(registry)
    hedef = tmp_path / "ara.py"
    client = FakeClient(
        tool_turn(("c1", "write_file", {"path": str(hedef), "content": CLI_KAYNAK})),
        tool_turn(("c2", "shell", {"command": f'py {hedef.name} bul "salmastra"'})),
        text_turn("Hazır — komutu koşturdum, doğru notu buluyor."),
    )
    agent = build_agent(tmp_path, client, registry)

    stats = asyncio.run(agent.run("bir not arama aracı yaz"))

    assert not [n for n in _harness_notlari(agent) if "[Doğrulama]" in n]
    assert stats.giris_uyarildi is False


def test_a_library_module_is_never_nagged(tmp_path: Path) -> None:
    """Kütüphane modülünü doğrudan koşmak zaten yanlış olurdu: kapı susar.

    Yanlış pozitifin bedeli gerçek: her yazmadan sonra "bunu çalıştır" diyen
    bir kapı, hiç uyarmayan bir kapı kadar kötüdür.
    """
    registry = ToolRegistry()
    _yazan_arac(registry, tmp_path)
    hedef = tmp_path / "hesap.py"
    client = FakeClient(
        tool_turn(("c1", "write_file",
                   {"path": str(hedef), "content": KUTUPHANE_KAYNAK})),
        text_turn("Hazır, modül yazıldı."),
    )
    agent = build_agent(tmp_path, client, registry)

    stats = asyncio.run(agent.run("toplama modülü yaz"))

    assert not [n for n in _harness_notlari(agent) if "[Doğrulama]" in n]
    assert stats.giris_uyarildi is False


def test_an_honest_report_about_an_unrun_entry_point_is_left_alone(
    tmp_path: Path,
) -> None:
    """Çalıştırmadığını kendi söyleyen cevap dürtülmez."""
    registry = ToolRegistry()
    _yazan_arac(registry, tmp_path)
    hedef = tmp_path / "ara.py"
    client = FakeClient(
        tool_turn(("c1", "write_file", {"path": str(hedef), "content": CLI_KAYNAK})),
        text_turn("Dosyayı yazdım ama komutu henüz çalıştırmadım, eksik."),
    )
    agent = build_agent(tmp_path, client, registry)

    stats = asyncio.run(agent.run("bir not arama aracı yaz"))

    assert not [n for n in _harness_notlari(agent) if "[Doğrulama]" in n]
    assert stats.giris_uyarildi is False


@pytest.mark.parametrize("kaynak,giris", [
    (CLI_KAYNAK, True),
    ('import argparse\np = argparse.ArgumentParser()\n', True),
    ("const [,, komut] = process.argv;\n", True),
    ("<?php\n$ad = $argv[1];\n", True),
    (KUTUPHANE_KAYNAK, False),
    ("class Kutu:\n    pass\n", False),
    ("{\n  \"ad\": \"deneme\"\n}\n", False),
])
def test_which_files_declare_an_entry_point(kaynak: str, giris: bool) -> None:
    from neocp.loop import giris_noktasi_mi

    assert giris_noktasi_mi(kaynak) is giris


# -- kabul-listesi kapısı ----------------------------------------------
#
# Ölçülen yara (CMS koşusu, 28.08): plan maddesinde "zengin metin editörü"
# yazarken teslim düz textarea çıktı ve hiçbir kapı yakalamadı — madde
# sessizce düşmüştü. Kapı: iş defterinde AÇIK madde dururken araçsız bir
# "bitti" cevabı BİR kez geri çevrilir.


def _akilli_agent(tmp_path: Path, client: Any, registry: ToolRegistry, hedefler: list[str]):
    """Zihinli ajan: defterine hedef yazılmış halde."""
    from neocp.mind import open_mind
    from neocp.loop import Agent, AgentIO
    from neocp.permissions import PermissionEngine
    from neocp.session import Session
    from .test_loop import _always_yes

    config = Config.load(tmp_path)
    config.ensure_dirs()
    mind = open_mind(config.mind_dir, config.sessions_dir, "test")
    for hedef in hedefler:
        mind.push_goal(hedef)
    session = Session(EventLog(tmp_path / "s.jsonl"), "test")
    return Agent(
        config=config,
        session=session,
        registry=registry,
        client=client,
        io=AgentIO(approve=_always_yes),
        permissions=PermissionEngine("yolo", allow=[], deny=[]),
        mind=mind,
    )


def test_open_goals_block_a_done_claim(tmp_path: Path) -> None:
    registry = ToolRegistry()
    client = FakeClient(
        text_turn("Bitti, her şey hazır."),
        text_turn("Haklısın — zengin metin editörü maddesi açık kalmış, ekliyorum."),
    )
    agent = _akilli_agent(tmp_path, client, registry,
                          ["M4: zengin metin editörü", "M5: sitemap"])

    stats = asyncio.run(agent.run("cms'i bitir"))

    notlar = [n for n in _harness_notlari(agent) if "[Kabul]" in n]
    assert len(notlar) == 1, notlar
    assert "zengin metin editörü" in notlar[0]
    assert stats.turns == 2
    assert stats.kabul_uyarildi is True


def test_no_open_goals_no_kabul_gate(tmp_path: Path) -> None:
    registry = ToolRegistry()
    client = FakeClient(text_turn("Bitti, her şey hazır."))
    agent = _akilli_agent(tmp_path, client, registry, [])

    stats = asyncio.run(agent.run("küçük işi yap"))

    assert not [n for n in _harness_notlari(agent) if "[Kabul]" in n]
    assert stats.turns == 1


def test_kabul_gate_fires_at_most_once(tmp_path: Path) -> None:
    """İkinci "bitti" bırakılır: sonsuz "hayır bitmedi" döngüsü yarım
    cevaptan kötü (kırmızı kapısıyla aynı sözleşme)."""
    registry = ToolRegistry()
    client = FakeClient(
        text_turn("Bitti."),
        text_turn("Yine de bitti diyorum."),
    )
    agent = _akilli_agent(tmp_path, client, registry, ["açık madde"])

    stats = asyncio.run(agent.run("işi yap"))

    notlar = [n for n in _harness_notlari(agent) if "[Kabul]" in n]
    assert len(notlar) == 1
    assert stats.turns == 2


def test_an_honest_open_items_report_is_not_a_done_claim(tmp_path: Path) -> None:
    """Dürüst "şunlar açık kaldı" cevabı dürtülmez — kapı yalnız bitti
    İDDİASINDA açılır."""
    registry = ToolRegistry()
    client = FakeClient(text_turn("İki madde açık kaldı: editör ve sitemap; yarın sürerim."))
    agent = _akilli_agent(tmp_path, client, registry, ["editör", "sitemap"])

    stats = asyncio.run(agent.run("işi yap"))

    assert not [n for n in _harness_notlari(agent) if "[Kabul]" in n]
    assert stats.turns == 1


# -- küçük-aile diyeti --------------------------------------------------


def test_small_family_is_recognised_and_briefed() -> None:
    from neocp import prompt as p

    assert p.kucuk_aile("z-ai/glm-5.3-flash")
    assert p.kucuk_aile("gemini-2.5-flash-lite")
    assert not p.kucuk_aile("claude-opus-5")
    assert not p.kucuk_aile("z-ai/glm-5.3")


def test_small_family_gets_the_brevity_block_and_brief_schemas(tmp_path: Path) -> None:
    from dataclasses import replace
    from neocp import prompt as p

    config = Config.load(tmp_path)
    config.ensure_dirs()
    config.model = replace(config.model, name="z-ai/glm-5.3-flash")
    registry = ToolRegistry()
    sistem = p.build(config, registry)
    assert "Kısalık sözleşmesi" in sistem.core

    agent = build_agent_with_config(tmp_path, FakeClient(text_turn("ok")), registry, config)
    assert agent.kisa_sema is True

    config.model = replace(config.model, name="claude-opus-5")
    sistem2 = p.build(config, registry)
    assert "Kısalık sözleşmesi" not in sistem2.core


def build_agent_with_config(tmp_path: Path, client: Any, registry: ToolRegistry, config):
    from neocp.loop import Agent, AgentIO
    from neocp.permissions import PermissionEngine
    from neocp.session import Session
    from .test_loop import _always_yes

    session = Session(EventLog(tmp_path / "s2.jsonl"), "test")
    return Agent(
        config=config,
        session=session,
        registry=registry,
        client=client,
        io=AgentIO(approve=_always_yes),
        permissions=PermissionEngine("yolo", allow=[], deny=[]),
    )


# -- öğretici kabuk hataları --------------------------------------------


def test_known_shell_traps_teach_the_way_out() -> None:
    from neocp.tools.shell import kabuk_ipucu

    assert "betiğe yaz" in kabuk_ipucu("At line:1 char:9 ... Unexpected token '|' in expression")
    assert "sürüm komutuyla" in kabuk_ipucu(
        "'gh' is not recognized as the name of a cmdlet, function...")
    assert "list_dir" in kabuk_ipucu("Cannot find path 'D:\yok\yer'")
    assert kabuk_ipucu("normal çıktı, sorun yok") == ""


# -- model oturum başlığı ----------------------------------------------
#
# Canlı şikâyet: sohbet listesi kullanıcı cümlesinin ilk 30 karakteriyle
# doluyor ("bana profesonel bir cms yapa ama..."). Başlığı ilk alışveriş
# bitince model koyar; elle verilmiş ad ASLA ezilmez.


def test_model_names_unnamed_session(tmp_path: Path) -> None:
    registry = ToolRegistry()
    client = FakeClient(
        text_turn("CMS iskeleti kuruldu, model katmanı hazır."),
        text_turn("CMS iskeleti kurulumu"),   # başlık çağrısının cevabı
    )
    agent = _akilli_agent(tmp_path, client, registry, [])

    asyncio.run(agent.run("bana profesyonel bir cms yap"))

    meta = agent.mind.session_meta()
    assert meta["test"]["ad"] == "CMS iskeleti kurulumu"
    # Başlık çağrısı araçsız gider ve sistemi ana istem değil kısa yönerge.
    assert client.seen_tools[-1] == []
    assert "başlık" in client.seen_system[-1][0]["text"].lower()


def test_named_session_is_not_retitled(tmp_path: Path) -> None:
    registry = ToolRegistry()
    client = FakeClient(text_turn("tamam, yaptım."))
    agent = _akilli_agent(tmp_path, client, registry, [])
    agent.mind.set_session_meta("test", ad="Elle verilen ad")

    asyncio.run(agent.run("küçük bir iş"))

    assert agent.mind.session_meta()["test"]["ad"] == "Elle verilen ad"
    # Ek başlık çağrısı hiç gitmedi: tek tur görüldü.
    assert len(client.seen_messages) == 1


# -- plan dürtüsü işin ortasında susar ---------------------------------
#
# Canlı saçmalık (28.08): 240 turluk koşunun ortasında, 97 dosya değişmiş
# ve iş listesi doluyken "sıfırdan" plan kartı çıktı. Plan işin BAŞININ
# işi: defterde açık madde ya da önceki alışveriş varsa dürtü susar.


def _plan_notu_dustu_mu(agent) -> bool:
    return any("plan" in str(n.data).lower()
               for n in agent.session.log.notes("plan_refleksi"))


def test_plan_nudge_fires_on_fresh_big_request(tmp_path: Path) -> None:
    registry = ToolRegistry()
    client = FakeClient(text_turn("plan geliyor"))
    agent = _akilli_agent(tmp_path, client, registry, [])

    asyncio.run(agent.run("bana profesyonel bir cms projesi yap baştan sona"))

    assert len(agent.session.log.notes("plan_refleksi")) == 1


def test_plan_nudge_is_silent_while_goals_are_open(tmp_path: Path) -> None:
    registry = ToolRegistry()
    client = FakeClient(text_turn("devam ediyorum"),
                        text_turn("Madde kapatıldı."))
    agent = _akilli_agent(tmp_path, client, registry,
                          ["M3: yazılar CRUD", "M4: medya"])

    asyncio.run(agent.run("bana profesyonel bir cms projesi yap baştan sona"))

    assert not agent.session.log.notes("plan_refleksi")


def test_plan_nudge_is_silent_mid_conversation(tmp_path: Path) -> None:
    registry = ToolRegistry()
    client = FakeClient(text_turn("ilk cevap"), text_turn("ikinci cevap"),
                        text_turn("başlık"), text_turn("başlık2"))
    agent = _akilli_agent(tmp_path, client, registry, [])

    asyncio.run(agent.run("merhaba, kısa bir soru"))
    asyncio.run(agent.run("şimdi bana profesyonel bir cms projesi yap baştan sona"))

    assert not agent.session.log.notes("plan_refleksi")


# -- kabuk: stdin kapalı, zaman aşımı ağacı öldürür --------------------
#
# Canlı yakalanan yara (28.08 üçlü kıyas): ajanın yazdığı rapor.py stdin
# bekliyordu; çocuk stdin'i miras aldığı için tur dakikalarca asıldı ve
# "durduruldu" denen sürecin torunu 7,5 dk yaşadı. stdin DEVNULL →
# input() anında EOFError; taskkill /T → ağaç komple iner.


def test_shell_child_gets_no_stdin(tmp_path: Path) -> None:
    import time
    from neocp.tools.shell import _run_shell

    async def kos():
        t0 = time.monotonic()
        durum, text, code = await _run_shell(
            'py -c "input()"', tmp_path, "t", 20, asyncio.Event())
        return durum, code, time.monotonic() - t0

    durum, code, gecen = asyncio.run(kos())
    assert durum == "ok" and code != 0     # EOFError ile hemen düştü
    assert gecen < 10, f"stdin bekledi: {gecen:.1f} sn"


def test_shell_timeout_kills_the_process_tree(tmp_path: Path) -> None:
    import time
    from neocp.tools.shell import _run_shell

    async def kos():
        t0 = time.monotonic()
        durum, _, _ = await _run_shell(
            'py -c "import time; time.sleep(60)"', tmp_path, "t", 3,
            asyncio.Event())
        return durum, time.monotonic() - t0

    durum, gecen = asyncio.run(kos())
    assert durum == "timeout"
    assert gecen < 15, f"ağaç ölmedi, bekleme sürdü: {gecen:.1f} sn"


# -- edit_file boşluk toleransı ----------------------------------------
#
# Ölçülen yara (üçlü kıyas z1): 18 hatalı aracın 7'si "aranan metin yok"
# ve hepsi boşluk/girinti farkıydı. Tolerans: satır sonu, kuyruk boşluğu,
# tek-tip girinti kayması — hepsinde eşleşme TEK olmak şartıyla.


from neocp.tools.files import _esnek_esle

NL = chr(10)
CRLF = chr(13) + NL


def test_esnek_esle_kuyruk_boslugu() -> None:
    text = NL.join(['a = 1   ', 'b = 2', 'c = 3', ''])
    hit = _esnek_esle(text, NL.join(['a = 1', 'b = 2']),
                      NL.join(['a = 9', 'b = 2']))
    assert hit and hit[3] == 'kuyruk boşlukları göz ardı edildi'
    b, e, yeni, _ = hit
    assert text[b:e] == NL.join(['a = 1   ', 'b = 2'])


def test_esnek_esle_girinti_kaymasi_new_de_kayar() -> None:
    text = NL.join(['def f():', '    if x:', '        git()', ''])
    # Model bir seviye eksik girintiyle hatırlamış:
    hit = _esnek_esle(text, NL.join(['if x:', '    git()']),
                      NL.join(['if x:', '    kal()']))
    assert hit and 'girinti' in hit[3]
    b, e, yeni, _ = hit
    assert text[b:e] == NL.join(['    if x:', '        git()'])
    assert yeni == NL.join(['    if x:', '        kal()'])


def test_esnek_esle_crlf() -> None:
    text = NL.join(['x = 1', 'y = 2', ''])
    hit = _esnek_esle(text, CRLF.join(['x = 1', 'y = 2']),
                      CRLF.join(['x = 1', 'y = 3']))
    assert hit and hit[3] == 'satır sonları normalize edildi'
    assert hit[2] == NL.join(['x = 1', 'y = 3'])


def test_esnek_esle_coklu_aday_belirsiz() -> None:
    # Aynı içerik iki farklı tek-tip kaymayla iki yerde: hangisi olduğu
    # belirsiz — dokunma, hata döndür.
    text = NL.join(['  x()', '  y()', 'ara', '    x()', '    y()', ''])
    hit = _esnek_esle(text, NL.join(['x()', 'y()']), NL.join(['x()', 'z()']))
    assert hit == ('coklu', 2)


def test_esnek_esle_icerik_farki_hosgorulmez() -> None:
    assert _esnek_esle('a = 1' + NL, 'a = 2', 'a = 3') is None


# -- sohbete özel model ------------------------------------------------
#
# Eski tesisat sohbet pinini settings.apply'dan geçiriyordu: pin DİSKE,
# küresel varsayılanın üzerine yazılıyordu ve başka sohbete geçince eski
# model geri gelmiyordu. Artık taban her zaman diskteki ayar; pin bellekte
# üstüne biner, silinince taban döner.


def _kopru(tmp_path: Path):
    import json
    from neocp.desktop import Bridge
    from neocp.mind import open_mind

    config = Config.load(tmp_path)
    config.ensure_dirs()
    (tmp_path / ".neocp" / "config.json").write_text(
        json.dumps({"model": {"name": "kuresel-model"}}), encoding="utf-8")
    from dataclasses import replace
    config = replace(config, model=replace(config.model, name="kuresel-model"))

    mind = open_mind(config.mind_dir, config.sessions_dir, "s1")
    kopru = Bridge.__new__(Bridge)
    uygulananlar: list[str] = []

    class _Ajan:
        pass
    ajan = _Ajan()
    ajan.config = config
    ajan.mind = mind
    kopru.agent = ajan

    def _reload(updated, force=False):
        ajan.config = updated
        uygulananlar.append(updated.model.name)
    kopru.reload = _reload
    return kopru, ajan, mind, uygulananlar, tmp_path / ".neocp" / "config.json"


def test_session_model_pin_applies_in_memory_only(tmp_path: Path) -> None:
    import json
    kopru, ajan, mind, uygulanan, disk = _kopru(tmp_path)
    mind.set_session_meta("s1", model="sohbet-modeli")

    kopru._apply_session_context("s1")

    assert ajan.config.model.name == "sohbet-modeli"
    # Küresel varsayılan diskte DEĞİŞMEDİ — pin sohbetin, kurulumun değil.
    assert json.loads(disk.read_text(encoding="utf-8"))["model"]["name"] == "kuresel-model"


def test_clearing_session_model_returns_to_global(tmp_path: Path) -> None:
    kopru, ajan, mind, uygulanan, disk = _kopru(tmp_path)
    mind.set_session_meta("s1", model="sohbet-modeli")
    kopru._apply_session_context("s1")
    assert ajan.config.model.name == "sohbet-modeli"

    mind.set_session_meta("s1", model="")
    kopru._apply_session_context("s1")
    assert ajan.config.model.name == "kuresel-model"


# -- kendiliğinden hatırlama: kısa-tek-zemin sızıntısı -----------------
#
# Ölçülen yara (28.08 hafıza deneyi, C kolu): 50 alakasız saha notu, o1
# görev istemiyle yalnız "ay" ↔ "ayında" örtüşmesi üzerinden önyüklemeye
# sızdı (+%28 token, +1 çağrı). Kural: zengin sorguda tek ve ≤3 harflik
# gövdeyle tutunan kayıt girmez; gerçek anı (çok gövdeli) girmeye devam eder.


O1_ISTEMI = ("Atölyede satislar.csv var: tarih, urun, adet, birim_fiyat. "
             "Rapor çıkaran bir araç istiyorum: her ayın toplam cirosunu "
             "ve en çok ciro yapan 3 ürünü yazsın. --ay 2026-03 deyince "
             "sadece o ayı göstersin.")


def _hafizali(tmp_path: Path):
    from neocp.mind import open_mind
    config = Config.load(tmp_path)
    config.ensure_dirs()
    return open_mind(config.mind_dir, config.sessions_dir, "t")


def test_prime_rejects_junk_grounded_on_one_short_stem(tmp_path: Path) -> None:
    from neocp.loop import select_prime
    mind = _hafizali(tmp_path)
    for i in range(12):
        mind.remember(f"Kayseri sahasında {i} numaralı pompa istasyonunun "
                      f"salmastra bakımı {i % 9 + 1} ayında yapıldı.",
                      kind="fact", title=f"saha notu {i}")

    hits = select_prime(mind, O1_ISTEMI)

    assert hits == [], [h.item.title for h in hits]


def test_prime_still_surfaces_the_truly_relevant_memory(tmp_path: Path) -> None:
    from neocp.loop import select_prime
    mind = _hafizali(tmp_path)
    mind.remember("satislar.csv düzeni: tarih,urun,adet,birim_fiyat "
                  "sütunları; ürünler Sensor, Kablo, PLC, Pompa.",
                  kind="fact", title="satislar.csv düzeni")
    for i in range(12):
        mind.remember(f"Kayseri sahasında {i} numaralı pompa istasyonunun "
                      f"salmastra bakımı {i % 9 + 1} ayında yapıldı.",
                      kind="fact", title=f"saha notu {i}")

    hits = select_prime(mind, O1_ISTEMI)

    basliklar = [h.item.title for h in hits]
    assert "satislar.csv düzeni" in basliklar, basliklar
    assert not any("saha notu" in b for b in basliklar), basliklar


# -- hafıza köprüleri: hata dersi + iş kapsülü -------------------------
#
# Kullanıcının önerisi ("araç hatalarını da hafızada tut") + ölçülen kazanç
# (kapsül = B kolunun −%24 tokeni). İkisi de mekanik: modelden metin
# istenmez, uydurma riski yok.


def _kabuk_hatali_turlar(n: int):
    turlar = []
    for i in range(n):
        turlar.append(tool_turn((f"c{i}", "shell",
                                 {"command": f"py - <<EOF deneme{i}"})))
    turlar.append(text_turn("bitti"))
    return turlar


class _HataliKabukKayit(ToolRegistry):
    pass


def test_repeated_error_pattern_becomes_a_lesson(tmp_path: Path) -> None:
    from neocp.tools.base import ToolResult, object_schema

    registry = ToolRegistry()

    @registry.tool(name="shell", description="d",
                   input_schema=object_schema({"command": {"type": "string"}}))
    async def shell(args, ctx):
        return ToolResult(
            content=("Çıkış kodu 1" + NL + NL
                     + "Missing file specification after redirection "
                     + "operator." + NL
                     + "İpucu: PowerShell tırnak/kaçış kırılgandır: "
                     + "karmaşık komutu write_file ile bir betiğe yaz ve "
                     + "dosyayı koş; $ içeren metinlerde tek tırnak kullan."),
            is_error=True)

    client = FakeClient(*_kabuk_hatali_turlar(2))
    agent = _akilli_agent(tmp_path, client, registry, [])

    asyncio.run(agent.run("karmaşık bir betik koştur"))

    dersler = [h.item for h in agent.mind.recall("araç dersi", limit=5)
               if str(h.item.title).startswith("araç dersi:")]
    assert len(dersler) == 1, [d.title for d in dersler]
    assert dersler[0].kind == "lesson"


def test_past_lesson_is_attached_to_a_fresh_error(tmp_path: Path) -> None:
    from neocp.tools.base import ToolResult, object_schema

    registry = ToolRegistry()

    @registry.tool(name="edit_file", description="d",
                   input_schema=object_schema({"path": {"type": "string"}}))
    async def edit_file(args, ctx):
        return ToolResult(content="Aranan metin dosyada yok.", is_error=True)

    client = FakeClient(
        tool_turn(("c1", "edit_file", {"path": "x.py"})),
        text_turn("tamam"))
    agent = _akilli_agent(tmp_path, client, registry, [])
    # Geçmiş OTURUMDAN ders (farklı session_id ile yazılmış olmalı).
    agent.mind.store.remember(
        "edit_file'a old metnini dosyanın GERÇEK halinden kopyala.",
        kind="lesson", title="araç dersi: edit-anchor", session="eski-oturum")

    asyncio.run(agent.run("dosyayı düzelt"))

    govde = json.dumps(agent.session.messages(), ensure_ascii=False)
    assert "[Hafıza]" in govde


def test_a_run_that_writes_files_leaves_a_capsule(tmp_path: Path) -> None:
    from neocp.tools.base import ToolResult, object_schema

    registry = ToolRegistry()

    @registry.tool(name="write_file", description="d",
                   input_schema=object_schema({"path": {"type": "string"}}))
    async def write_file(args, ctx):
        return ToolResult(content="yazıldı")

    @registry.tool(name="shell", description="d",
                   input_schema=object_schema({"command": {"type": "string"}}))
    async def shell(args, ctx):
        return ToolResult(content="çıkış 0")

    client = FakeClient(
        tool_turn(("c1", "write_file", {"path": "rapor.py"})),
        tool_turn(("c2", "shell", {"command": "py rapor.py satislar.csv"})),
        text_turn("bitti, rapor.py hazır"))
    agent = _akilli_agent(tmp_path, client, registry, [])

    asyncio.run(agent.run("bana satislar.csv için rapor aracı yaz"))

    kapsuller = [h.item for h in agent.mind.recall("iş kapsülü satislar", limit=5)
                 if str(h.item.title).startswith("iş kapsülü:")]
    assert len(kapsuller) == 1, [k.title for k in kapsuller]
    assert "rapor.py" in kapsuller[0].content
    assert "py rapor.py satislar.csv" in kapsuller[0].content


def test_a_chat_only_run_leaves_no_capsule(tmp_path: Path) -> None:
    registry = ToolRegistry()
    client = FakeClient(text_turn("selam!"))
    agent = _akilli_agent(tmp_path, client, registry, [])

    asyncio.run(agent.run("merhaba"))

    assert not [h for h in agent.mind.recall("iş kapsülü", limit=5)
                if str(h.item.title).startswith("iş kapsülü:")]


# -- test kapısı: yazılan test koşulmadan tur kapanmaz -----------------
#
# Ölçülen yara (28.08 dokuz-görev, o2-servis): test dosyası yazıldı, hiç
# koşulmadı, KIRMIZI çıktı ve teslim edildi — kırmızı kapısı yalnız
# koşulan testi görür. Kapı bir kez dürter; pytest/node --test gibi toplu
# koşucular dosya adı geçmese de koşulmuş sayılır.


def _yazan_ve_koan_ajan(tmp_path, turlar):
    from neocp.tools.base import ToolResult, object_schema
    registry = ToolRegistry()

    @registry.tool(name="write_file", description="d",
                   input_schema=object_schema({"path": {"type": "string"}}))
    async def write_file(args, ctx):
        return ToolResult(content="yazıldı")

    @registry.tool(name="shell", description="d",
                   input_schema=object_schema({"command": {"type": "string"}}))
    async def shell(args, ctx):
        return ToolResult(content="7 passed")

    client = FakeClient(*turlar)
    return build_agent(tmp_path, client, registry), client


def test_unrun_test_file_blocks_the_done_claim(tmp_path: Path) -> None:
    agent, client = _yazan_ve_koan_ajan(tmp_path, [
        tool_turn(("c1", "write_file", {"path": "servis.py"}),
                  ("c2", "write_file", {"path": "test_servis.py"})),
        text_turn("Bitti, servis ve testleri hazır."),
        text_turn("Haklısın — pytest koşuyorum."),
    ])

    asyncio.run(agent.run("küçük bir servis yaz, testlerini de yaz"))

    notlar = [n for n in _harness_notlari(agent) if "[Doğrulama]" in n and "KOŞMADIN" in n]
    assert len(notlar) == 1, notlar


def test_bare_pytest_counts_as_running_the_tests(tmp_path: Path) -> None:
    agent, client = _yazan_ve_koan_ajan(tmp_path, [
        tool_turn(("c1", "write_file", {"path": "test_servis.py"})),
        tool_turn(("c2", "shell", {"command": "py -m pytest -q"})),
        text_turn("Bitti — 7 test yeşil."),
    ])

    asyncio.run(agent.run("testleri yaz ve koş"))

    assert not [n for n in _harness_notlari(agent) if "KOŞMADIN" in n]

# -- kosulsuz-top istisnasi yalniz genc zihinde -------------------------
#
# Dis inceleme kok nedeni: _gecer'i gecen TEK kayit, skoru tabanin
# altinda olsa bile her turda enjekte ediliyordu — ilgisiz 9-gorev
# dizisindeki +%9 istem tokeni buradan geliyordu. Istisna, yazilma
# sebebi olan GENC zihinle sinirlandi.


def _sahte_zihin(kayit_sayisi, skor):
    from types import SimpleNamespace
    item = SimpleNamespace(id='n1', kind='fact', title='rapor notu',
                           content='rapor dosyasi hakkinda kisa not',
                           tags=[])
    hit = SimpleNamespace(item=item, score=skor)
    adim = SimpleNamespace(node='n1', hop=0)
    return SimpleNamespace(
        recall=lambda q, limit=8: [hit],
        last_trace=[adim],
        store=SimpleNamespace(count=lambda: kayit_sayisi))


def test_mature_mind_does_not_prime_below_the_floor() -> None:
    from neocp.loop import select_prime
    zihin = _sahte_zihin(200, skor=0.05)   # taban 0.12'nin altinda
    assert select_prime(zihin, 'rapor dosyasina bak') == []


def test_young_mind_keeps_the_top_exemption() -> None:
    from neocp.loop import select_prime
    zihin = _sahte_zihin(3, skor=0.05)     # genc korpus: bm25 cokuk
    hits = select_prime(zihin, 'rapor dosyasina bak')
    assert len(hits) == 1


def test_above_floor_still_primes_in_a_mature_mind() -> None:
    from neocp.loop import select_prime
    zihin = _sahte_zihin(200, skor=0.9)
    assert len(select_prime(zihin, 'rapor dosyasina bak')) == 1

def _dosya_ctx(tmp_path):
    import asyncio
    from neocp.config import Config
    from neocp.events import EventLog
    from neocp.session import Session
    from neocp.tools.base import ToolContext
    config = Config(workspace=tmp_path, state_dir=tmp_path)
    session = Session(EventLog(tmp_path / 'events.jsonl'), 'test')
    return ToolContext(config=config, session=session,
                       cancel=asyncio.Event())


# -- read_many: dizi-argumanli toplu okuma ------------------------------
#
# 9-gorev kosusu 0.97 arac/cagri olctu — paralel altyapi hazirken kucuk
# model 'bagimsiz okumalari tek turda cagir' ogudunu yok sayiyor. Sema
# talimattan guclu: N kesif turu tek gidis-donuse iner.


def test_read_many_reads_several_files_in_one_call(tmp_path) -> None:
    import asyncio
    from neocp.tools.base import ToolRegistry
    from neocp.tools import files as files_mod
    ctx = _dosya_ctx(tmp_path)
    kok = ctx.sandbox.root
    kok.mkdir(parents=True, exist_ok=True)
    (kok / 'a.py').write_text('x = 1', encoding='utf-8')
    (kok / 'b.py').write_text('y = 2', encoding='utf-8')
    reg = ToolRegistry()
    files_mod.register(reg)
    r = asyncio.run(reg.get('read_many').handler(
        {'paths': ['a.py', 'b.py', 'yok.py']}, ctx))
    assert not r.is_error
    assert 'x = 1' in r.content
    assert 'y = 2' in r.content
    assert 'dosya yok' in r.content   # yok.py   # eksik dosya cagriyi dusurmez


def test_read_many_counts_as_reading_for_the_write_gate(tmp_path) -> None:
    import asyncio
    from neocp.tools.base import ToolRegistry
    from neocp.tools import files as files_mod
    ctx = _dosya_ctx(tmp_path)
    kok = ctx.sandbox.root
    kok.mkdir(parents=True, exist_ok=True)
    (kok / 'a.py').write_text('x = 1', encoding='utf-8')
    (kok / 'b.py').write_text('y = 2', encoding='utf-8')
    reg = ToolRegistry()
    files_mod.register(reg)
    asyncio.run(reg.get('read_many').handler(
        {'paths': ['a.py', 'b.py']}, ctx))
    r = asyncio.run(reg.get('write_file').handler(
        {'path': 'a.py', 'content': 'x = 3'}, ctx))
    assert not r.is_error, 'read_many okumasi yazma kapisini acmali'

# -- acilis brifingi: calisma alaninin sig dokumu ------------------------


def test_workspace_brief_lists_shallow_and_freezes(tmp_path) -> None:
    from neocp.config import Config
    from neocp import prompt
    (tmp_path / 'app.py').write_text('x', encoding='utf-8')
    alt = tmp_path / 'site'
    alt.mkdir()
    (alt / 'index.html').write_text('y', encoding='utf-8')
    (tmp_path / '__pycache__').mkdir()
    c = Config(workspace=tmp_path, state_dir=tmp_path)
    b = prompt._workspace_brief(c)
    assert 'app.py' in b and 'site/' in b and 'index.html' in b
    assert '__pycache__' not in b
    # Donukluk: sonradan eklenen dosya briefe girmez (onbellek capasi).
    (tmp_path / 'yeni.py').write_text('z', encoding='utf-8')
    assert 'yeni.py' not in prompt._workspace_brief(c)


def test_workspace_brief_absent_in_lean_prompt(tmp_path) -> None:
    from neocp.config import Config
    from neocp import prompt
    from neocp.tools.base import ToolRegistry
    (tmp_path / 'ipucu-dosyasi.py').write_text('x', encoding='utf-8')
    c = Config(workspace=tmp_path, state_dir=tmp_path)
    genis = prompt.build(c, ToolRegistry()).core
    assert 'ipucu-dosyasi.py' in genis
    import dataclasses
    dar = dataclasses.replace(c, model=dataclasses.replace(
        c.model, context_window=4096))
    assert 'ipucu-dosyasi.py' not in prompt.build(dar, ToolRegistry()).core

def test_cloud_consent_flag_survives_the_toggle_roundtrip(tmp_path) -> None:
    # Bayrak tanima.json'da yasar; on/off cevrimleri onu SILMEMELI
    # (config.json'a konmamasinin sebebi tam da settings'in bilinmeyen
    # anahtari dusurmesiydi — ayni tuzak burada tekrarlanmamali).
    from neocp import tanima
    tanima.bulut_onayi_ayarla(tmp_path, True)
    assert tanima.durum(tmp_path)['learn_cloud_ok'] is True
    tanima.ayarla(tmp_path, True)
    tanima.ayarla(tmp_path, False)
    assert tanima.durum(tmp_path)['learn_cloud_ok'] is True
    tanima.bulut_onayi_ayarla(tmp_path, False)
    assert tanima.durum(tmp_path)['learn_cloud_ok'] is False

def test_shell_cwd_strips_the_workshop_prefix(tmp_path) -> None:
    # Olculdu (29.08 supurumu): 3 hatali cagrinin kalibi 'Calisma dizini
    # yok: atolye/X' — model klasor adini yola kendisi ekliyor.
    import asyncio
    from neocp.tools.base import ToolRegistry
    from neocp.tools import shell as shell_mod
    ctx = _dosya_ctx(tmp_path)
    kok = ctx.sandbox.root
    (kok / 'gorev').mkdir(parents=True)
    reg = ToolRegistry()
    shell_mod.register(reg)
    r = asyncio.run(reg.get('shell').handler(
        {'command': 'echo ok', 'cwd': 'atolye/gorev'}, ctx))
    assert not r.is_error, r.content
    assert r.detail.get('cwd', '').endswith('gorev')

# -- kesif dususu (B5): salt-okur kuyruktan sonra dusuk caba + tavan -----


def _kuyruk(*son_araclar, kuyruk_rolu='tool'):
    mesajlar = [
        {'role': 'system', 'content': 'sen neo'},
        {'role': 'user', 'content': 'raporu yaz'},
        {'role': 'assistant', 'content': '',
         'tool_calls': [{'id': f'c{i}', 'type': 'function',
                         'function': {'name': ad, 'arguments': '{}'}}
                        for i, ad in enumerate(son_araclar)]},
    ]
    for i, _ in enumerate(son_araclar):
        mesajlar.append({'role': 'tool', 'tool_call_id': f'c{i}',
                         'content': 'icerik'})
    if kuyruk_rolu != 'tool':
        mesajlar.append({'role': kuyruk_rolu, 'content': 'not'})
    return mesajlar


def test_discovery_turn_detected_only_after_pure_read_results() -> None:
    from neocp.backends.openai_backend import _kesif_turu
    assert _kesif_turu(_kuyruk('read_file', 'list_dir')) is True
    assert _kesif_turu(_kuyruk('read_many')) is True
    # Yazma karisan kuyruk kesif degil: caba kisilmaz.
    assert _kesif_turu(_kuyruk('read_file', 'write_file')) is False
    assert _kesif_turu(_kuyruk('shell')) is False
    # Kuyrukta taze kullanici/sistem mesaji varsa dokunulmaz.
    assert _kesif_turu(_kuyruk('read_file', kuyruk_rolu='user')) is False
    assert _kesif_turu(_kuyruk('read_file', kuyruk_rolu='system')) is False
    assert _kesif_turu([{'role': 'user', 'content': 'selam'}]) is False


def test_discovery_downshift_lowers_effort_for_small_family() -> None:
    from neocp.backends.openai_backend import OpenAIBackend
    from neocp.config import ModelConfig
    m = ModelConfig(name='z-ai/glm-5.3-flash', base_url='http://x',
                    thinking=True, effort='high')
    b = OpenAIBackend(m, client=object())
    assert b._reasoning() == {'effort': 'medium'}   # kucuk-aile tavani
    assert b._reasoning(kesif=True) == {'effort': 'low'}
    # Dusunmesi kapali modelde kesif bayragi bir sey acmaz.
    m2 = ModelConfig(name='z-ai/glm-5.3-flash', base_url='http://x',
                    thinking=False)
    b2 = OpenAIBackend(m2, client=object())
    assert b2._reasoning(kesif=True) == {'enabled': False}

def test_read_result_advertises_unread_siblings(tmp_path) -> None:
    # Sema + aciklama yetmedi (20 kosuda 0 read_many cagrisi): duyuru
    # modelin en dikkatli okudugu kanala, arac SONUCUNA tasindi.
    import asyncio
    from neocp.tools.base import ToolRegistry
    from neocp.tools import files as files_mod
    ctx = _dosya_ctx(tmp_path)
    kok = ctx.sandbox.root
    kok.mkdir(parents=True, exist_ok=True)
    for ad in ('a.py', 'b.py', 'c.js'):
        (kok / ad).write_text('x = 1', encoding='utf-8')
    reg = ToolRegistry()
    files_mod.register(reg)
    r = asyncio.run(reg.get('read_file').handler({'path': 'a.py'}, ctx))
    assert 'read_many' in r.content and 'b.py' in r.content
    # Kardesler okununca duyuru susar: gurultu birikmez.
    asyncio.run(reg.get('read_many').handler(
        {'paths': ['b.py', 'c.js']}, ctx))
    r2 = asyncio.run(reg.get('read_file').handler({'path': 'a.py'}, ctx))
    assert 'read_many tek turda' not in r2.content

