"""Sohbet yüzeyi eşdeğerliği: dosya bahsi, görevler, tur özeti, bütçe freni.

Buradaki her test bir arayüz sözünün ARKASINDAKİ gerçeği tutuyor: menü bir
şey vaat ediyorsa sunucuda o şeyin karşılığı olmalı ve doğru davranmalı.
Arayüz tarafı (durum makinesi, olay sözleşmesi) `test_static.py` içinde.
"""

from __future__ import annotations

import asyncio
import json
import urllib.request
from pathlib import Path
from types import SimpleNamespace

import pytest

from neocp.config import Config
from neocp.events import EventLog
from neocp.mind import Mind, open_mind
from neocp.tools.checkpoint import KLASOR, Defter
from neocp.web import MindServer


@pytest.fixture()
def mind(tmp_path: Path) -> Mind:
    return open_mind(tmp_path / "mind", tmp_path / "sessions", "cur")


def _kur(tmp_path: Path, mind: Mind, controller: object | None = None):
    """Ayağa kalkmış bir sunucu + kapatma çağrısı."""
    config = Config.load(tmp_path)
    config.ensure_dirs()
    log = EventLog(tmp_path / "s.jsonl")
    server = MindServer(mind, log, port=0, config=config, controller=controller)  # type: ignore[arg-type]
    server.start()
    return server, config, log


def _get(server: MindServer, yol: str) -> dict:
    with urllib.request.urlopen(server.url + yol.lstrip("/"), timeout=8) as answer:
        return json.loads(answer.read().decode("utf-8"))


def _post(server: MindServer, yol: str, govde: dict) -> dict:
    request = urllib.request.Request(
        server.url + yol.lstrip("/"),
        data=json.dumps(govde).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=8) as answer:
        return json.loads(answer.read().decode("utf-8"))


# -- `@` dosya bahsi ---------------------------------------------------


def test_the_file_search_finds_a_file_by_its_name(tmp_path: Path, mind: Mind) -> None:
    """`@` yazan kullanıcı dosyanın tam yolunu bilmiyor — adını biliyor."""
    server, config, log = _kur(tmp_path, mind)
    kok = Path(config.workspace)
    (kok / "derin" / "alt").mkdir(parents=True, exist_ok=True)
    (kok / "derin" / "alt" / "olcum-raporu.md").write_text("veri", encoding="utf-8")
    try:
        cevap = _get(server, "/api/files/search?q=olcum")
    finally:
        server.stop()
        log.close()

    yollar = [f["path"] for f in cevap["files"]]
    assert "derin/alt/olcum-raporu.md" in yollar
    # Ad da geliyor: cipte tam yol, listede okunur ad.
    assert any(f["name"] == "olcum-raporu.md" for f in cevap["files"])


def test_the_file_search_skips_tool_droppings_and_hidden_folders(
    tmp_path: Path, mind: Mind
) -> None:
    """`.git` ve `node_modules` içinde arama, listeyi çöple dolduruyor ve
    aranan dosyayı görünmez yapıyor."""
    server, config, log = _kur(tmp_path, mind)
    kok = Path(config.workspace)
    for kirli in (".git", "node_modules", "__pycache__", ".gizli"):
        (kok / kirli).mkdir(parents=True, exist_ok=True)
        (kok / kirli / "hedef.txt").write_text("x", encoding="utf-8")
    (kok / "hedef.txt").write_text("x", encoding="utf-8")
    try:
        cevap = _get(server, "/api/files/search?q=hedef")
    finally:
        server.stop()
        log.close()

    yollar = [f["path"] for f in cevap["files"]]
    assert yollar == ["hedef.txt"], yollar


def test_an_empty_query_offers_the_most_recently_touched_files(
    tmp_path: Path, mind: Mind
) -> None:
    """`@` yazan kullanıcı çoğu zaman üzerinde çalıştığı dosyayı istiyor."""
    import os
    import time

    server, config, log = _kur(tmp_path, mind)
    kok = Path(config.workspace)
    for ad in ("eski.txt", "yeni.txt"):
        (kok / ad).write_text("x", encoding="utf-8")
    simdi = time.time()
    os.utime(kok / "eski.txt", (simdi - 9000, simdi - 9000))
    os.utime(kok / "yeni.txt", (simdi, simdi))
    try:
        cevap = _get(server, "/api/files/search?q=")
    finally:
        server.stop()
        log.close()

    yollar = [f["path"] for f in cevap["files"]]
    assert yollar.index("yeni.txt") < yollar.index("eski.txt")


# -- koşan görevler ----------------------------------------------------


class SahteKoprü:
    """Görevler ucunun beklediği yüzey — köprünün minik bir taklidi."""

    def __init__(self) -> None:
        self.durdurulan: list[str] = []

    def snapshot(self) -> dict:
        return {"busy": False}

    def gorevler(self) -> dict:
        return {"gorevler": [{"id": "c:abc", "ad": "model eğitimi", "tur": "iş",
                              "durum": "kosuyor", "basladi": 1.0, "bitti": 0.0,
                              "ozet": "", "oturum": "", "durdurulabilir": True}],
                "kosan": 1}

    def gorev_durdur(self, gid: str) -> dict:
        self.durdurulan.append(gid)
        return {"ok": True, "id": gid}


def test_the_task_list_and_the_stop_button_reach_the_bridge(
    tmp_path: Path, mind: Mind
) -> None:
    koprü = SahteKoprü()
    server, _config, log = _kur(tmp_path, mind, koprü)
    try:
        liste = _get(server, "/api/gorevler")
        durdur = _post(server, "/api/gorevler/durdur", {"id": "c:abc"})
    finally:
        server.stop()
        log.close()

    assert liste["kosan"] == 1
    assert liste["gorevler"][0]["ad"] == "model eğitimi"
    assert durdur["ok"] is True
    assert koprü.durdurulan == ["c:abc"]


def test_a_bridge_without_the_task_surface_answers_honestly(
    tmp_path: Path, mind: Mind
) -> None:
    """Salt-gözlem köprüsü (önizleme) bu uçları uygulamak zorunda değil:
    500 değil, dürüst bir ok:false dönmeli."""
    server, _config, log = _kur(tmp_path, mind, SimpleNamespace(snapshot=lambda: {}))
    try:
        assert _get(server, "/api/gorevler") == {"gorevler": [], "kosan": 0}
        assert _post(server, "/api/gorevler/durdur", {"id": "c:x"})["ok"] is False
        assert _post(server, "/api/butce", {"usd": 5})["ok"] is False
        assert _post(server, "/api/compact", {})["ok"] is False
    finally:
        server.stop()
        log.close()


def test_a_helper_run_can_be_read_step_by_step(tmp_path: Path, mind: Mind) -> None:
    """Bir yardımcıya bakarken sorulan soru 'ne yaptı?' — metin turları
    değil, araç adımları."""
    server, config, log = _kur(tmp_path, mind)
    cocuk = Path(config.sessions_dir) / "yardimci1.jsonl"
    cocuk.parent.mkdir(parents=True, exist_ok=True)
    satirlar = [
        {"seq": 1, "kind": "meta", "role": None, "content": "tool_start",
         "meta": {"tool": "read_file", "input": {"path": "a.py"}}},
        {"seq": 2, "kind": "meta", "role": None, "content": "tool_end",
         "meta": {"tool": "read_file", "error": False, "ms": 12}},
        {"seq": 3, "kind": "message", "role": "assistant",
         "content": [{"type": "text", "text": "Dosyayı okudum."}], "meta": {}},
        {"seq": 4, "kind": "message", "role": "assistant",
         "content": [{"type": "text", "text": "iç not"}], "meta": {"internal": True}},
    ]
    cocuk.write_text("\n".join(json.dumps(s, ensure_ascii=False) for s in satirlar),
                     encoding="utf-8")
    try:
        cevap = _get(server, "/api/gorevler/dokum?oturum=yardimci1")
    finally:
        server.stop()
        log.close()

    assert cevap["ok"] is True
    adimlar = cevap["adimlar"]
    assert adimlar[0] == {"tur": "arac", "ad": "read_file", "hedef": "a.py",
                          "hata": False, "ms": 12}
    assert adimlar[1] == {"tur": "soz", "metin": "Dosyayı okudum."}
    # İç not sohbete çıkmıyorsa döküme de çıkmamalı.
    assert len(adimlar) == 2


def test_the_step_log_refuses_a_path_shaped_session_id(
    tmp_path: Path, mind: Mind
) -> None:
    server, _config, log = _kur(tmp_path, mind)
    try:
        cevap = _get(server, "/api/gorevler/dokum?oturum=../../gizli")
    finally:
        server.stop()
        log.close()
    assert cevap["ok"] is False


# -- "bu turda ne değişti" + geri al ------------------------------------


def _defter_yaz(config: Config, hedef: Path, eski: str, yeni: str) -> Defter:
    """Araç katmanının yaptığının aynısı: değiştirmeden ÖNCE görüntü al."""
    defter = Defter(Path(config.state_dir) / KLASOR, "cur")
    hedef.parent.mkdir(parents=True, exist_ok=True)
    hedef.write_text(eski, encoding="utf-8")
    defter.kaydet(hedef, "edit_file")
    hedef.write_text(yeni, encoding="utf-8")
    return defter


def test_the_ledger_lists_what_changed_and_from_where(
    tmp_path: Path, mind: Mind
) -> None:
    server, config, log = _kur(tmp_path, mind)
    hedef = Path(config.workspace) / "rapor.md"
    try:
        _defter_yaz(config, hedef, "bir\niki\n", "bir\nÜÇ\n")
        hepsi = _get(server, "/api/degisiklikler")
        assert hepsi["son"] == 1
        assert hepsi["kayitlar"][0]["ad"] == "rapor.md"
        assert hepsi["kayitlar"][0]["arac"] == "edit_file"
        assert hepsi["kayitlar"][0]["gerialinabilir"] is True

        # Tur sınırı: bu kayıttan SONRASI boş.
        assert _get(server, "/api/degisiklikler?since=1")["kayitlar"] == []

        # İkinci bir değişiklik yalnızca yeni kaydı getiriyor.
        _defter_yaz(config, hedef, "bir\nÜÇ\n", "bir\nDÖRT\n")
        sonra = _get(server, "/api/degisiklikler?since=1")
        assert [k["sira"] for k in sonra["kayitlar"]] == [2]
    finally:
        server.stop()
        log.close()


def test_the_diff_shows_the_snapshot_against_what_is_on_disk_now(
    tmp_path: Path, mind: Mind
) -> None:
    server, config, log = _kur(tmp_path, mind)
    hedef = Path(config.workspace) / "rapor.md"
    try:
        _defter_yaz(config, hedef, "eski hâl\n", "yeni hâl\n")
        fark = _get(server, "/api/degisiklikler/fark?sira=1")
    finally:
        server.stop()
        log.close()

    assert fark["ok"] is True and fark["metin"] is True
    assert fark["eski"] == "eski hâl\n"
    assert fark["yeni"] == "yeni hâl\n"


def test_undoing_the_turn_puts_the_files_back(tmp_path: Path, mind: Mind) -> None:
    """Geri alma `undo` aracının yolundan geçiyor: aynı defter, aynı sonuç."""
    server, config, log = _kur(tmp_path, mind)
    bir = Path(config.workspace) / "bir.txt"
    iki = Path(config.workspace) / "iki.txt"
    try:
        _defter_yaz(config, bir, "A", "A-değişti")
        _defter_yaz(config, iki, "B", "B-değişti")
        cevap = _post(server, "/api/degisiklikler/geri", {"n": 2})
        assert cevap["ok"] is True
        assert bir.read_text(encoding="utf-8") == "A"
        assert iki.read_text(encoding="utf-8") == "B"
    finally:
        server.stop()
        log.close()


def test_a_new_file_is_undone_by_deleting_it(tmp_path: Path, mind: Mind) -> None:
    """Defterde 'yoktu' kaydı: geri alma oluşturmayı geri alır."""
    server, config, log = _kur(tmp_path, mind)
    yeni = Path(config.workspace) / "taze.txt"
    try:
        defter = Defter(Path(config.state_dir) / KLASOR, "cur")
        defter.kaydet(yeni, "write_file")     # dosya henüz yok
        yeni.write_text("içerik", encoding="utf-8")
        kayit = _get(server, "/api/degisiklikler")["kayitlar"][0]
        assert kayit["yoktu"] is True
        assert _post(server, "/api/degisiklikler/geri", {"n": 1})["ok"] is True
        assert not yeni.exists()
    finally:
        server.stop()
        log.close()


# -- bütçe freni --------------------------------------------------------


class SahteFiyatliKoprü:
    """Bridge'in bütçe hesabını izole eden en küçük taklit.

    Gerçek Bridge asyncio döngüsü, hub ve ajan istiyor; burada sınanan şey
    yalnızca **karar**: elimizdeki sayaç ile elimizdeki fiyata bakıp
    "dur" demek ya da dememek.
    """

    from neocp.desktop import Bridge

    butce = Bridge.butce
    _harcanan = Bridge._harcanan
    _butce_freni = Bridge._butce_freni

    def __init__(self, girdi: int, cikti: int, fiyat: dict | None) -> None:
        self._oturum_kullanim = {"girdi": girdi, "cikti": cikti, "cagri": 1}
        self._fiyat = fiyat
        self._butce_usd = None
        self._butce_bildirildi = False


def test_the_brake_stays_silent_without_a_cap() -> None:
    koprü = SahteFiyatliKoprü(1_000_000, 0, {"girdi": 1e-5, "cikti": 3e-5})
    assert koprü._butce_freni() == ""


def test_the_brake_speaks_once_the_session_passes_the_cap() -> None:
    # 1M girdi × $10/M = $10 harcandı; sınır $5.
    koprü = SahteFiyatliKoprü(1_000_000, 0, {"girdi": 1e-5, "cikti": 3e-5})
    koprü.butce(5)
    mesaj = koprü._butce_freni()
    assert "Bütçe sınırına ulaşıldı ($5.00)" in mesaj
    assert "sınırı yükselt" in mesaj
    # Aynı satır tekrar tekrar basılmıyor.
    assert koprü._butce_freni() == ""
    # Sınır yükseltilince fren kalkıyor: iş kaldığı yerden sürebilmeli.
    koprü.butce(50)
    assert koprü._butce_freni() == ""


def test_the_brake_will_not_stop_work_on_a_made_up_price() -> None:
    """Fiyat bilinmiyorsa (yerel sunucu, katalog dışı model) uydurma bir
    dolar rakamıyla kullanıcının işini durdurmak, sınırı hiç koymamaktan
    kötü olurdu."""
    koprü = SahteFiyatliKoprü(10_000_000, 10_000_000, None)
    koprü.butce(1)
    assert koprü._butce_freni() == ""


def test_an_empty_or_zero_cap_means_no_cap() -> None:
    koprü = SahteFiyatliKoprü(1_000_000, 0, {"girdi": 1e-5, "cikti": 3e-5})
    assert koprü.butce("")["butce"] is None
    assert koprü.butce(0)["butce"] is None
    assert koprü.butce(-3)["butce"] is None
    assert koprü.butce("abc")["ok"] is False
    assert koprü.butce("2.5")["butce"] == 2.5


# -- fren gerçekten turu durduruyor mu ---------------------------------


def test_the_turn_stops_when_the_brake_speaks(tmp_path: Path) -> None:
    """Sahte kullanım: sınır aşılınca model BİR KEZ BİLE çağrılmıyor ve
    kullanıcı mesajı geçmişte duruyor — yarım iş kaybolmuyor."""
    from tests.test_loop import FakeClient, build_agent, text_turn
    from neocp.tools import ToolRegistry

    client = FakeClient(text_turn("koşmamalıydım"))
    agent = build_agent(tmp_path, client, ToolRegistry())
    notlar: list[str] = []
    agent.io.on_notice = notlar.append
    agent.io.butce_freni = lambda: "Bütçe sınırına ulaşıldı ($5.00) — devam etmek için sınırı yükselt."

    stats = asyncio.run(agent.run("bir şey yap"))

    assert client.seen_messages == []          # model hiç çağrılmadı
    assert stats.interrupted is True
    assert notlar and "Bütçe sınırına ulaşıldı" in notlar[0]
    # Mesaj geçmişte: sınır yükseltilince konuşma kaldığı yerden sürer.
    metinler = json.dumps(agent.session.messages(), ensure_ascii=False)
    assert "bir şey yap" in metinler


def test_the_turn_runs_normally_when_there_is_no_cap(tmp_path: Path) -> None:
    from tests.test_loop import FakeClient, build_agent, text_turn
    from neocp.tools import ToolRegistry

    client = FakeClient(text_turn("tamamdır"))
    agent = build_agent(tmp_path, client, ToolRegistry())

    stats = asyncio.run(agent.run("bir şey yap"))

    assert len(client.seen_messages) == 1
    assert stats.interrupted is False
