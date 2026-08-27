"""Tarayıcı derinliği: sayfa "açıldı" mı, yoksa gerçekten ÇALIŞIYOR mu?

Kanıtlanmış yara: neo bir web uygulaması yapıyor, sayfayı açıyor, metnini
okuyor ve "çalışıyor" diyor. Oysa konsolda kırmızı bir TypeError, ağda 404
dönen bir istek olabilir. İkisi de `document.body.innerText`te GÖRÜNMEZ —
sayfa yarım çizilmiş ama sessizdir. Kullanıcı tarayıcıyı açınca öğreniyor.

Konsol mesajı sonradan sorulamaz, çünkü bir OLAYDIR: geçmişte bir an olur
ve kaybolur. O yüzden sayfa açılırken sekmeye kalıcı bir dinleyici bağlanıp
olaylar tamponlanıyor. Buradaki testler o tamponu gerçek CDP olay
gövdeleriyle sürüyor.

Üçüncü vaat dürüstlük: dinleyici geç bağlandıysa bunu söylüyor, hiç
bağlanamadıysa "göremiyorum" diyor ve boş konsolu asla "sayfa hatasız"
diye satmıyor.
"""

from __future__ import annotations

import json
import socket
import threading
import time
from typing import Any

import pytest

from neocp import chrome
from neocp.tools import browser as surf

from tests.test_chrome import FakeCdpHttp, _read_frame, _send_text, _accept_key


# -- olay basan sahte CDP ----------------------------------------------


def olay_sunucusu(olaylar: list[dict[str, Any]]):
    """`Network.enable` görünce verilen olayları sırayla iten sahte CDP.

    Gerçek Chrome da böyle davranıyor: `enable` çağrısından sonra olaylar
    istenmeden akmaya başlıyor. Testin değeri buradan geliyor — tamponu
    besleyen yol, üretimdeki yolun aynısı.
    """
    box = socket.socket()
    box.bind(("127.0.0.1", 0))
    box.listen(8)
    port = box.getsockname()[1]

    def talk(conn: socket.socket) -> None:
        try:
            raw = b""
            while b"\r\n\r\n" not in raw:
                raw += conn.recv(4096)
            key = next(line.split(b":", 1)[1].strip()
                       for line in raw.split(b"\r\n")
                       if line.lower().startswith(b"sec-websocket-key"))
            conn.sendall((
                "HTTP/1.1 101 Switching Protocols\r\n"
                "Upgrade: websocket\r\nConnection: Upgrade\r\n"
                f"Sec-WebSocket-Accept: {_accept_key(key.decode())}\r\n\r\n"
            ).encode("ascii"))
            while True:
                opcode, body = _read_frame(conn)
                if opcode == 0x8:
                    return
                if opcode not in (0x1, 0x2):
                    continue
                mesaj = json.loads(body)
                _send_text(conn, json.dumps(
                    {"id": mesaj.get("id"), "result": {}}).encode("utf-8"))
                if mesaj.get("method") == "Network.enable":
                    for olay in olaylar:
                        _send_text(conn, json.dumps(olay).encode("utf-8"))
        except (ConnectionError, OSError):
            pass

    def serve() -> None:
        while True:
            try:
                conn, _ = box.accept()
            except OSError:
                return
            threading.Thread(target=talk, args=(conn,), daemon=True).start()

    threading.Thread(target=serve, daemon=True).start()
    return f"ws://127.0.0.1:{port}/dev", box


# Gerçek CDP gövdeleri — alan adları Chrome'un yolladığının aynısı.
KONSOL_HATASI = {
    "method": "Runtime.consoleAPICalled",
    "params": {
        "type": "error",
        "args": [{"type": "string", "value": "Kaydetme başarısız"}],
        "stackTrace": {"callFrames": [
            {"url": "http://ornek/app.js", "lineNumber": 40}]},
    },
}

ISTISNA = {
    "method": "Runtime.exceptionThrown",
    "params": {"exceptionDetails": {
        "text": "Uncaught",
        "url": "http://ornek/app.js",
        "lineNumber": 11,
        "exception": {
            "className": "TypeError",
            "description": "TypeError: yok.forEach is not a function\n"
                           "    at http://ornek/app.js:12:9",
        },
    }},
}

KONSOL_LOGU = {
    "method": "Runtime.consoleAPICalled",
    "params": {"type": "log", "args": [{"type": "string", "value": "hazır"}]},
}

TARAYICI_KAYDI = {
    "method": "Log.entryAdded",
    "params": {"entry": {
        "source": "network", "level": "error",
        "text": "Failed to load resource: the server responded with a "
                "status of 404 (Not Found)",
        "url": "http://ornek/yok.js",
    }},
}

ISTEK_404 = [
    {"method": "Network.requestWillBeSent", "params": {
        "requestId": "R1", "timestamp": 100.0, "type": "Script",
        "request": {"url": "http://ornek/yok.js", "method": "GET"}}},
    {"method": "Network.responseReceived", "params": {
        "requestId": "R1", "type": "Script", "response": {"status": 404}}},
    {"method": "Network.loadingFinished", "params": {
        "requestId": "R1", "timestamp": 100.25}},
]

ISTEK_200 = [
    {"method": "Network.requestWillBeSent", "params": {
        "requestId": "R2", "timestamp": 100.0, "type": "Document",
        "request": {"url": "http://ornek/sayfa?x=1", "method": "GET"}}},
    {"method": "Network.responseReceived", "params": {
        "requestId": "R2", "type": "Document", "response": {"status": 200}}},
    {"method": "Network.loadingFinished", "params": {
        "requestId": "R2", "timestamp": 100.05}},
]

ISTEK_KOPUK = [
    {"method": "Network.requestWillBeSent", "params": {
        "requestId": "R3", "timestamp": 100.0,
        "request": {"url": "http://yok.ornek/api", "method": "POST"}}},
    {"method": "Network.loadingFailed", "params": {
        "requestId": "R3", "timestamp": 100.1,
        "errorText": "net::ERR_NAME_NOT_RESOLVED"}},
]


def bekle(kosul, sure: float = 5.0) -> bool:
    """Olaylar arka planda geliyor; kısa bir süre bekle."""
    son = time.monotonic() + sure
    while time.monotonic() < son:
        if kosul():
            return True
        time.sleep(0.02)
    return False


@pytest.fixture()
def kayit_kur():
    """(olaylar) → Kayit; test bitince bağlantıyı kapatır."""
    kurulan: list[tuple[chrome.Kayit, socket.socket]] = []

    def kur(olaylar: list[dict[str, Any]]) -> chrome.Kayit:
        url, box = olay_sunucusu(olaylar)
        kayit = chrome.Kayit(url)
        kurulan.append((kayit, box))
        return kayit

    yield kur
    for kayit, box in kurulan:
        kayit.kapat()
        box.close()


# -- konsol tamponu -----------------------------------------------------


def test_a_console_error_reaches_the_buffer(kayit_kur) -> None:
    kayit = kayit_kur([KONSOL_HATASI])
    assert bekle(lambda: len(kayit.konsol) == 1)
    satir = kayit.konsol[0]
    assert satir.seviye == "hata"
    assert satir.metin == "Kaydetme başarısız"
    assert satir.yer == "app.js:41"        # CDP 0'dan sayar, insan 1'den


def test_an_uncaught_exception_keeps_its_stack(kayit_kur) -> None:
    """Yığın izi `description` alanında; `text` yalnız 'Uncaught' diyor."""
    kayit = kayit_kur([ISTISNA])
    assert bekle(lambda: len(kayit.konsol) == 1)
    satir = kayit.konsol[0]
    assert satir.seviye == "hata"
    assert satir.kaynak == "istisna"
    assert "yok.forEach is not a function" in satir.metin


def test_browser_level_log_entries_are_captured(kayit_kur) -> None:
    """404'ün konsoldaki satırı `console.*` çağrısı DEĞİL — Log.entryAdded."""
    kayit = kayit_kur([TARAYICI_KAYDI])
    assert bekle(lambda: len(kayit.konsol) == 1)
    assert kayit.konsol[0].seviye == "hata"
    assert "404" in kayit.konsol[0].metin
    assert kayit.konsol[0].kaynak == "tarayici"


def test_levels_are_normalised(kayit_kur) -> None:
    uyari = {"method": "Runtime.consoleAPICalled",
             "params": {"type": "warning",
                        "args": [{"type": "string", "value": "dikkat"}]}}
    kayit = kayit_kur([KONSOL_LOGU, uyari])
    assert bekle(lambda: len(kayit.konsol) == 2)
    assert [k.seviye for k in kayit.konsol] == ["log", "uyari"]


def test_object_arguments_are_rendered(kayit_kur) -> None:
    olay = {"method": "Runtime.consoleAPICalled",
            "params": {"type": "log", "args": [
                {"type": "string", "value": "durum"},
                {"type": "object", "value": {"kod": 500}}]}}
    kayit = kayit_kur([olay])
    assert bekle(lambda: len(kayit.konsol) == 1)
    assert '"kod": 500' in kayit.konsol[0].metin


ANA_GEZINME = {"method": "Page.frameNavigated",
               "params": {"frame": {"id": "F1"}}}


def test_the_first_navigation_keeps_the_page_it_loaded(kayit_kur) -> None:
    """Ölçülerek bulunan yara: dinleyici sayfa yüklenmeden bağlanıyor, sonra
    belgenin KENDİ commit'i `frameNavigated` olarak geliyordu ve o ana kadar
    biriken her şeyi süpürüyordu. Canlı denemede ağ listesi 4 istek yerine
    2 ile geldi — belgenin kendisi ve ilk betiğin 404'ü kayboldu."""
    kayit = kayit_kur([*ISTEK_404, KONSOL_HATASI, ANA_GEZINME])
    assert bekle(lambda: len(kayit.konsol) == 1 and len(kayit.istekler) == 1)
    time.sleep(0.3)
    assert len(kayit.konsol) == 1        # ilk gezinme SİLMEZ
    assert len(kayit.istekler) == 1


def test_a_second_navigation_clears_the_buffer(kayit_kur) -> None:
    """A sayfasının hataları B sayfasına yazılmasın."""
    kayit = kayit_kur([ANA_GEZINME, KONSOL_HATASI, ANA_GEZINME, KONSOL_LOGU])
    assert bekle(lambda: len(kayit.konsol) == 1)
    time.sleep(0.3)
    assert [k.metin for k in kayit.konsol] == ["hazır"]


def test_an_iframe_navigation_does_not_clear_the_buffer(kayit_kur) -> None:
    """Reklam iframe'i gezinince ana sayfanın hataları silinmemeli."""
    iframe = {"method": "Page.frameNavigated",
              "params": {"frame": {"id": "F2", "parentId": "F1"}}}
    kayit = kayit_kur([ANA_GEZINME, KONSOL_HATASI, iframe, iframe, iframe])
    assert bekle(lambda: len(kayit.konsol) == 1)
    time.sleep(0.3)
    assert len(kayit.konsol) == 1


def test_a_fresh_attach_resets_the_navigation_count(kayit_kur) -> None:
    """`go` ile temizlenen tamponda yeni sayfanın ilk commit'i yine silmemeli."""
    kayit = kayit_kur([ANA_GEZINME])
    assert bekle(lambda: kayit._gezinme == 1)
    kayit.temizle()
    assert kayit._gezinme == 0


# -- ağ tamponu ---------------------------------------------------------


def test_a_404_is_recorded_with_status_and_duration(kayit_kur) -> None:
    kayit = kayit_kur(ISTEK_404)
    assert bekle(lambda: kayit.istekler and kayit.istekler[0].durum == 404)
    istek = kayit.istekler[0]
    assert istek.basarisiz
    assert istek.yontem == "GET"
    assert round(istek.sure_ms) == 250
    assert "yok.js" in istek.bicim() and "404" in istek.bicim()


def test_a_successful_request_is_not_a_failure(kayit_kur) -> None:
    kayit = kayit_kur(ISTEK_200)
    assert bekle(lambda: kayit.istekler and kayit.istekler[0].durum == 200)
    istek = kayit.istekler[0]
    assert not istek.basarisiz
    # Yol + sorgu gösteriliyor, host değil: gürültü değil bilgi.
    assert "/sayfa?x=1" in istek.bicim()


def test_a_failed_load_keeps_the_reason(kayit_kur) -> None:
    kayit = kayit_kur(ISTEK_KOPUK)
    assert bekle(lambda: kayit.istekler and kayit.istekler[0].hata)
    istek = kayit.istekler[0]
    assert istek.basarisiz
    assert "ERR_NAME_NOT_RESOLVED" in istek.bicim()


def test_the_buffer_has_a_ceiling() -> None:
    """Döngüde hata basan bir sayfa belleği yemesin."""
    kayit = chrome.Kayit.__new__(chrome.Kayit)
    from collections import deque

    kayit.konsol = deque(maxlen=3)
    for i in range(10):
        kayit.konsol.append(chrome.KonsolSatiri("log", str(i)))
    assert [k.metin for k in kayit.konsol] == ["7", "8", "9"]


# -- araç metinleri: dürüstlük -----------------------------------------


class SahteKayit:
    def __init__(self, konsol=(), istekler=(), hata="", eksik=False) -> None:
        self.konsol = list(konsol)
        self.istekler = list(istekler)
        self.hata = hata
        self.eksik = eksik


def _hata(metin: str, yer: str = "") -> chrome.KonsolSatiri:
    return chrome.KonsolSatiri("hata", metin, yer)


def test_an_empty_console_is_never_sold_as_proof() -> None:
    """En önemli cümle: boş konsol 'sayfa hatasız' demek DEĞİLDİR."""
    metin = surf._konsol_metni(SahteKayit(), "hepsi", None)
    assert "hatasız olduğu anlamına GELMEZ" in metin
    assert "Davranışı ayrıca doğrula" in metin


def test_a_late_listener_admits_it() -> None:
    metin = surf._konsol_metni(SahteKayit(eksik=True), "hepsi", None)
    assert "SONRA bağlandı" in metin
    assert "kaçmış olabilir" in metin


def test_a_broken_listener_says_it_cannot_see() -> None:
    metin = surf._konsol_metni(SahteKayit(hata="bağlantı reddedildi"), "hepsi", None)
    assert "kurulamadı" in metin
    assert "göremiyorum" in metin
    assert "uydurma yorum yapma" in metin


def test_the_console_filter_narrows_to_errors() -> None:
    kayit = SahteKayit([
        chrome.KonsolSatiri("log", "hazır"),
        chrome.KonsolSatiri("uyari", "eski API"),
        _hata("TypeError: yok", "app.js:12"),
    ])
    hepsi = surf._konsol_metni(kayit, "hepsi", None)
    assert "hazır" in hepsi and "TypeError" in hepsi

    yalniz = surf._konsol_metni(kayit, "hata", None)
    assert "TypeError" in yalniz
    assert "hazır" not in yalniz
    assert "eski API" not in yalniz


def test_an_empty_filter_points_at_the_wider_view() -> None:
    kayit = SahteKayit([chrome.KonsolSatiri("log", "hazır")])
    metin = surf._konsol_metni(kayit, "hata", None)
    assert "toplam 1 mesaj" in metin
    assert "seviye: hepsi" in metin


def test_console_errors_tell_the_model_to_fix_the_source() -> None:
    metin = surf._konsol_metni(SahteKayit([_hata("TypeError: yok")]), "hepsi", None)
    assert "Kaynak koddaki" in metin and "düzelt" in metin


def test_failed_requests_come_first() -> None:
    kayit = SahteKayit(istekler=[
        chrome.Istek("http://x/iyi", "GET", 200),
        chrome.Istek("http://x/yok", "GET", 404),
        chrome.Istek("http://x/patlak", "POST", 500),
    ])
    metin = surf._ag_metni(kayit, None)
    assert metin.index("Başarısız olanlar") < metin.index("Başarılı olanlar")
    assert metin.index("/yok") < metin.index("/iyi")
    assert "3 istek · 2 başarısız" in metin
    assert "5xx sunucu tarafında patlayan bir kod" in metin


def test_no_requests_suggests_a_reload() -> None:
    metin = surf._ag_metni(SahteKayit(), None)
    assert "dinleyici bağlanmadan önce" in metin


# -- okuma sonrası uyarı ------------------------------------------------


class SahteKutu:
    def __init__(self, kayit) -> None:
        self._kayit = kayit

    def kayit(self, tab):
        return self._kayit


def test_reading_a_page_flags_console_errors() -> None:
    """Model sayfa metnini okuyup turu kapatmasın: sayım hemen orada."""
    kutu = SahteKutu(SahteKayit([_hata("TypeError")],
                                [chrome.Istek("http://x/yok", "GET", 404)]))
    ek = surf._uyari_eki(kutu, {"id": "T1"})
    assert "1 konsol hatası" in ek and "1 başarısız istek" in ek
    assert "'çalışıyor' diye rapor etme" in ek


def test_a_clean_page_gets_no_noise() -> None:
    ek = surf._uyari_eki(SahteKutu(SahteKayit()), {"id": "T1"})
    assert ek == ""


def test_a_framework_error_page_is_hoisted_to_the_top() -> None:
    ek = surf._hata_eki({"hata": {
        "tur": "CodeIgniter 4 hata sayfası",
        "baslik": "TypeError",
        "mesaj": "Home::index(): Return value must be of type string",
        "yer": "app/Controllers/Home.php:12",
    }})
    assert "HATA SAYFASI" in ek
    assert "Return value must be of type string" in ek
    assert "'çalışıyor' diye rapor etme" in ek


def test_an_ordinary_page_has_no_error_layer() -> None:
    assert surf._hata_eki({"hata": None}) == ""
    assert surf._hata_eki({}) == ""


# -- araç yüzeyi --------------------------------------------------------


def test_the_tool_offers_the_new_actions() -> None:
    from neocp.tools import ToolRegistry

    registry = ToolRegistry()
    surf.register(registry)
    spec = registry.get("browser")
    actions = spec.input_schema["properties"]["action"]["enum"]
    for ad in ("konsol", "ag", "js"):
        assert ad in actions
    for alan in ("seviye", "n"):
        assert alan in spec.input_schema["properties"]


def test_the_description_forbids_fixing_the_ui_with_js() -> None:
    """`js` bir teşhis aracı; sayfaya betikle yama atmak kalıcı değil."""
    from neocp.tools import ToolRegistry

    registry = ToolRegistry()
    surf.register(registry)
    aciklama = registry.get("browser").description
    assert "UI DEĞİŞİKLİĞİ YAPMA" in aciklama
    assert "KAYNAK KODU düzelt" in aciklama
    assert "YALNIZ 200 dönmesine bakma" in aciklama


# -- js sargısı ---------------------------------------------------------


def test_the_js_wrapper_survives_unserialisable_results() -> None:
    """DOM düğümü ve fonksiyon `returnByValue` ile serileşmiyor."""
    sargi = chrome._JS_SARGI % json.dumps("document.body")
    assert "JSON.parse(JSON.stringify" in sargi
    assert "String(r)" in sargi
    # İfadenin kendi istisnası yakalanıp bulgu olarak dönüyor.
    assert "catch (e) { return {hata:" in sargi


def test_the_js_wrapper_carries_the_expression() -> None:
    sargi = chrome._JS_SARGI % json.dumps("window.__durum.length")
    assert '"window.__durum.length"' in sargi


def test_the_error_layer_script_looks_for_real_signatures() -> None:
    """Genel bir 'error kelimesi geçiyor mu' taraması OLMAMALI: sıradan bir
    blog yazısını hata sayfası ilan ederdi."""
    for imza in ("#traceback", "werkzeug", "Fatal error", "whoops"):
        assert imza.lower() in chrome._HATA_JS.lower()


# -- uçtan uca: sahte CDP üstünden ------------------------------------


def test_opening_a_tab_attaches_the_listener(tmp_path) -> None:
    """Dinleyici sayfa yüklenmeden bağlanmalı: bir saniye geç kalmak, ilk
    hatayı kaçırmak demek."""
    ws_url, ws_box = olay_sunucusu([KONSOL_HATASI, *ISTEK_404])
    http = FakeCdpHttp(ws_url)
    try:
        box = chrome.Browser(tmp_path, port=http.port)
        made = box.open("http://ornek/")
        kayit = box.kayit(made)
        assert not kayit.eksik           # `open` sırasında bağlandı
        assert bekle(lambda: len(kayit.konsol) == 1 and len(kayit.istekler) == 1)
        assert kayit.konsol[0].seviye == "hata"
        assert kayit.istekler[0].durum == 404

        metin = surf._konsol_metni(kayit, "hata", None)
        assert "Kaydetme başarısız" in metin
        assert "app.js:41" in metin
    finally:
        http.stop()
        ws_box.close()


def test_a_listener_attached_late_is_marked_incomplete(tmp_path) -> None:
    ws_url, ws_box = olay_sunucusu([])
    http = FakeCdpHttp(ws_url)
    try:
        box = chrome.Browser(tmp_path, port=http.port)
        tab = box.tabs()[0]
        kayit = box.kayit(tab)           # `open` üzerinden değil, sonradan
        assert kayit.eksik
        assert "SONRA bağlandı" in surf._konsol_metni(kayit, "hepsi", None)
    finally:
        http.stop()
        ws_box.close()


def test_one_listener_per_tab(tmp_path) -> None:
    ws_url, ws_box = olay_sunucusu([])
    http = FakeCdpHttp(ws_url)
    try:
        box = chrome.Browser(tmp_path, port=http.port)
        tab = box.tabs()[0]
        assert box.kayit(tab) is box.kayit(tab)
    finally:
        http.stop()
        ws_box.close()


def test_a_tab_without_a_debug_url_degrades_honestly(tmp_path) -> None:
    box = chrome.Browser(tmp_path, port=1)
    kayit = box.dinle({"id": "T9"})
    assert kayit.hata
    assert "göremiyorum" in surf._konsol_metni(kayit, "hepsi", None)
