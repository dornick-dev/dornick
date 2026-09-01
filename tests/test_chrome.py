"""dornick chrome — CDP istemcisi.

Gerçek tarayıcı testte yok; olmaması testin değerini düşürmüyor çünkü
kırılgan olan kısım protokol: WebSocket çerçeveleri (maske, 16/64 bitlik
uzunluklar, parçalı mesaj) ve CDP'nin istek/cevap eşleşmesi. İkisi de
burada gerçek soketlerle, sahte bir sunucuya karşı sürülüyor.
"""

from __future__ import annotations

import base64
import hashlib
import json
import socket
import struct
import threading
from typing import Any, Callable

import pytest

from dornick import chrome

GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


# -- sahte WebSocket sunucusu -------------------------------------------


def _accept_key(key: str) -> str:
    digest = hashlib.sha1((key + GUID).encode("ascii")).digest()
    return base64.b64encode(digest).decode("ascii")


def _read_frame(conn: socket.socket) -> tuple[int, bytes]:
    head = conn.recv(2)
    if len(head) < 2:
        raise ConnectionError("kapandı")
    opcode = head[0] & 0x0F
    size = head[1] & 0x7F
    if size == 126:
        (size,) = struct.unpack(">H", conn.recv(2))
    elif size == 127:
        (size,) = struct.unpack(">Q", conn.recv(8))
    mask = conn.recv(4) if head[1] & 0x80 else b""
    body = b""
    while len(body) < size:
        piece = conn.recv(size - len(body))
        if not piece:
            raise ConnectionError("kapandı")
        body += piece
    if mask:
        body = bytes(b ^ mask[i % 4] for i, b in enumerate(body))
    return opcode, body


def _send_text(conn: socket.socket, payload: bytes) -> None:
    # Sunucu çerçevesi maskesiz gider.
    head = bytearray([0x81])
    if len(payload) < 126:
        head.append(len(payload))
    elif len(payload) < 1 << 16:
        head.append(126)
        head += struct.pack(">H", len(payload))
    else:
        head.append(127)
        head += struct.pack(">Q", len(payload))
    conn.sendall(bytes(head) + payload)


def ws_server(answer: Callable[[bytes], bytes]) -> tuple[str, threading.Thread, socket.socket]:
    """Sahte sunucu: her bağlantıyla el sıkışır, her mesaja `answer` döner.

    Bağlantı başına değil döngüyle: `Browser` her CDP çağrısı için taze
    bir bağlantı açıyor — tek `accept` ikinci çağrıda asılı kalıyordu.
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
                if opcode in (0x1, 0x2):
                    _send_text(conn, answer(body))
        except (ConnectionError, OSError):
            pass

    def serve() -> None:
        while True:
            try:
                conn, _ = box.accept()
            except OSError:
                return  # kutu kapandı, test bitti
            threading.Thread(target=talk, args=(conn,), daemon=True).start()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    return f"ws://127.0.0.1:{port}/dev", thread, box


# -- tel ----------------------------------------------------------------


def test_the_wire_echoes_small_and_giant_frames() -> None:
    """7, 16 ve 64 bitlik uzunluk yolları — ekran görüntüsü 64'lüğü
    gerçekten kullanıyor, o yol test edilmeden bırakılamaz."""
    url, _thread, box = ws_server(lambda body: body)
    wire = chrome.Wire(url, timeout=10)
    try:
        for size in (5, 300, 70_000):
            message = "a" * size
            wire.send(message)
            assert wire.recv() == message
    finally:
        wire.close()
        box.close()


def test_the_wire_refuses_a_non_websocket_answer() -> None:
    box = socket.socket()
    box.bind(("127.0.0.1", 0))
    box.listen(1)
    port = box.getsockname()[1]

    def deny() -> None:
        try:
            conn, _ = box.accept()
            conn.recv(4096)
            conn.sendall(b"HTTP/1.1 404 Not Found\r\n\r\n")
            conn.close()
        except OSError:
            pass

    threading.Thread(target=deny, daemon=True).start()
    with pytest.raises(chrome.BrowseError):
        chrome.Wire(f"ws://127.0.0.1:{port}/x", timeout=5)
    box.close()


# -- sahte CDP ----------------------------------------------------------


# Sahte CDP'nin gördüğü tuş vuruşları — press/type testleri bunu okuyor.
KEYSTROKES: list[dict[str, Any]] = []

# Sahte CDP'ye giden sayfa betikleri — fill/submit testleri, gönderilen
# JS'in doğru ölçütleri ve olayları taşıdığını buradan denetliyor.
EXPRESSIONS: list[str] = []

# fill/submit yardımcılarının sayfa sözleşmesi ({ok} / {err, adaylar});
# test, senaryosuna göre bu kutuları dolduruyor.
FILL_OUTCOME: dict[str, Any] = {}
SUBMIT_OUTCOME: dict[str, Any] = {}


def cdp_answer(body: bytes) -> bytes:
    """Runtime.evaluate, screenshot, navigate ve Input.* bilen minicik CDP."""
    message = json.loads(body)
    method = message.get("method")
    params = message.get("params") or {}
    if method == "Runtime.evaluate":
        source = params["expression"]
        EXPRESSIONS.append(source)
        value: Any = {
            "document.readyState": "complete",
            "document.title": "Deneme Sayfası",
            "location.href": "http://ornek/",
        }.get(source, "MERHABA DÜNYA")
        # click/focus yardımcıları uzun IIFE; eşleşen metni geri döndür.
        if "hit.click()" in source:
            value = "Giriş"
        elif "// dornick:fill" in source:
            value = dict(FILL_OUTCOME)
        elif "// dornick:submit" in source:
            value = dict(SUBMIT_OUTCOME)
        elif "pick.focus()" in source:
            value = "e-posta"
        result = {"result": {"value": value}}
    elif method == "Page.captureScreenshot":
        result = {"data": base64.b64encode(b"sahte-jpeg").decode("ascii")}
    elif method == "Page.navigate":
        result = {"frameId": "1"}
    elif method == "Input.dispatchKeyEvent":
        KEYSTROKES.append(params)
        result = {}
    else:
        result = {}
    return json.dumps({"id": message.get("id"), "result": result}).encode("utf-8")


class FakeCdpHttp:
    """CDP'nin http yüzü: /json/version, /json/list, /json/new."""

    def __init__(self, ws_url: str) -> None:
        from http.server import BaseHTTPRequestHandler, HTTPServer

        tabs = [{
            "id": "TAB1", "type": "page", "title": "Deneme Sayfası",
            "url": "http://ornek/", "webSocketDebuggerUrl": ws_url,
        }]

        class Handler(BaseHTTPRequestHandler):
            def _json(self, payload: Any) -> None:
                raw = json.dumps(payload).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(raw)

            def do_GET(self) -> None:  # noqa: N802
                if self.path.startswith("/json/version"):
                    self._json({"Browser": "Sahte/1.0"})
                elif self.path.startswith("/json/list"):
                    self._json(tabs)
                else:
                    self.send_error(404)

            def do_PUT(self) -> None:  # noqa: N802
                if self.path.startswith("/json/new"):
                    self._json(tabs[0])
                else:
                    self.send_error(404)

            def log_message(self, *args: Any) -> None:
                pass

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def stop(self) -> None:
        self.server.shutdown()
        self.server.server_close()


def test_the_browser_reads_and_shoots_through_fake_cdp(tmp_path) -> None:
    """tabs → read → screenshot, gerçek soketlerle sahte sunucuya karşı."""
    ws_url, _thread, ws_box = ws_server(cdp_answer)
    http = FakeCdpHttp(ws_url)
    try:
        box = chrome.Browser(tmp_path, port=http.port)
        assert box.alive()

        tabs = box.tabs()
        assert tabs and tabs[0]["id"] == "TAB1"

        seen = box.read(tabs[0])
        assert seen["title"] == "Deneme Sayfası"
        assert "MERHABA" in seen["text"]

        frame = box.screenshot(tabs[0])
        assert frame.startswith("data:image/jpeg;base64,")

        made = box.open("http://ornek/yeni")
        assert made["id"] == "TAB1"
    finally:
        http.stop()
        ws_box.close()


def test_click_type_press_drive_the_page(tmp_path) -> None:
    """Faz 2: metne göre tıklama, alana yazma ve özel tuş — hepsi gerçek
    CDP çağrılarına dönüşüyor."""
    KEYSTROKES.clear()
    ws_url, _thread, ws_box = ws_server(cdp_answer)
    http = FakeCdpHttp(ws_url)
    try:
        box = chrome.Browser(tmp_path, port=http.port)
        tab = box.tabs()[0]

        assert box.click(tab, "Giriş") == "Giriş"

        box.type(tab, "ab", into="e-posta")
        # İki karakter → dört olay (her biri keyDown + keyUp).
        typed = [k for k in KEYSTROKES if k.get("text") in ("a", "b")]
        assert len(typed) == 4

        KEYSTROKES.clear()
        box.press(tab, "Enter")
        assert [k["type"] for k in KEYSTROKES] == ["keyDown", "keyUp"]
        assert KEYSTROKES[0]["key"] == "Enter"

        seen = box.navigate(tab, "http://ornek/baska")
        assert seen["title"] == "Deneme Sayfası"
    finally:
        http.stop()
        ws_box.close()


def test_fill_carries_the_target_and_the_events_to_the_page(tmp_path) -> None:
    """fill'in sayfaya yolladığı betik hedef ölçütlerini (label/name/
    placeholder/selector) taşımalı ve çerçevelerin dinlediği input+change
    olaylarını tetiklemeli — yoksa React'li bir form değeri hiç görmez."""
    EXPRESSIONS.clear()
    FILL_OUTCOME.clear()
    FILL_OUTCOME["ok"] = "E-posta / name=email"
    ws_url, _thread, ws_box = ws_server(cdp_answer)
    http = FakeCdpHttp(ws_url)
    try:
        box = chrome.Browser(tmp_path, port=http.port)
        tab = box.tabs()[0]

        where = box.fill(tab, "ali@ornek.com", label="E-posta")
        assert where == "E-posta / name=email"

        source = next(s for s in EXPRESSIONS if "// dornick:fill" in s)
        # Hedef ölçütleri sayfaya gitmiş olmalı.
        assert '"E-posta"' in source and '"ali@ornek.com"' in source
        # Etiket, name ve placeholder eşlemesi sayfa betiğinde.
        for needle in ("labels", "aria-label", "el.name", "el.placeholder"):
            assert needle in source
        # Yerli ayarlayıcı + input/change olayları: çerçeveler bunu dinliyor.
        assert "getOwnPropertyDescriptor" in source
        assert 'new Event("input"' in source and 'new Event("change"' in source
    finally:
        http.stop()
        ws_box.close()


def test_a_crowded_fill_match_names_the_candidates(tmp_path) -> None:
    """Birden çok alan eşleşince sessizce ilkine yazılmaz: hata, adayları
    sayar ki model hedefi daraltabilsin."""
    FILL_OUTCOME.clear()
    FILL_OUTCOME.update({
        "err": "Birden çok alan eşleşti; hedefi daralt.",
        "adaylar": ["Ad / name=ad", "Soyad / name=soyad"],
    })
    ws_url, _thread, ws_box = ws_server(cdp_answer)
    http = FakeCdpHttp(ws_url)
    try:
        box = chrome.Browser(tmp_path, port=http.port)
        tab = box.tabs()[0]
        with pytest.raises(chrome.BrowseError) as caught:
            box.fill(tab, "x", name="ad")
        assert "name=ad" in str(caught.value)
        assert "name=soyad" in str(caught.value)
    finally:
        http.stop()
        ws_box.close()


def test_fill_without_a_target_is_refused_before_touching_the_page(tmp_path) -> None:
    box = chrome.Browser(tmp_path, port=1)  # sunucu yok; çağrı da olmamalı
    with pytest.raises(chrome.BrowseError):
        box.fill({"webSocketDebuggerUrl": "ws://127.0.0.1:1/x"}, "metin")


def test_submit_finds_the_form_and_reports_the_button(tmp_path) -> None:
    """submit iki yolu da bilmeli: düğme varsa tıklama, yoksa requestSubmit.
    Seçici verilirse sayfaya taşınmalı; çoklu form hatası adaylarıyla gelmeli."""
    EXPRESSIONS.clear()
    SUBMIT_OUTCOME.clear()
    SUBMIT_OUTCOME["ok"] = "Giriş Yap"
    ws_url, _thread, ws_box = ws_server(cdp_answer)
    http = FakeCdpHttp(ws_url)
    try:
        box = chrome.Browser(tmp_path, port=http.port)
        tab = box.tabs()[0]

        assert box.submit(tab) == "Giriş Yap"
        source = next(s for s in EXPRESSIONS if "// dornick:submit" in s)
        # İki gönderim yolu da sayfa betiğinde: düğme tıklama + requestSubmit.
        assert "btn.click()" in source and "requestSubmit" in source

        EXPRESSIONS.clear()
        assert box.submit(tab, "#giris-formu") == "Giriş Yap"
        assert any('"#giris-formu"' in s for s in EXPRESSIONS)

        SUBMIT_OUTCOME.clear()
        SUBMIT_OUTCOME.update({
            "err": "Birden çok form var; `selector` ile birini seç.",
            "adaylar": ["#giris → /giris", "#arama → /ara"],
        })
        with pytest.raises(chrome.BrowseError) as caught:
            box.submit(tab)
        assert "#giris" in str(caught.value) and "#arama" in str(caught.value)
    finally:
        http.stop()
        ws_box.close()


def test_an_unknown_key_is_refused(tmp_path) -> None:
    ws_url, _thread, ws_box = ws_server(cdp_answer)
    http = FakeCdpHttp(ws_url)
    try:
        box = chrome.Browser(tmp_path, port=http.port)
        tab = box.tabs()[0]
        with pytest.raises(chrome.BrowseError):
            box.press(tab, "F13")
    finally:
        http.stop()
        ws_box.close()


# -- araç kapısı --------------------------------------------------------


def test_every_registry_shares_one_browser(tmp_path) -> None:
    """Ana ajan ve alt ajanlar ayrı araç defterleri taşıyor; hepsi AYNI
    tarayıcıyı sürmeli — yoksa her defter kendi Chrome'unu açıp aynı kapıda
    yarışır."""
    a = chrome.shared(tmp_path, port=9999)
    b = chrome.shared(tmp_path, port=9999)
    assert a is b
    # Farklı profil/kapı ayrı tarayıcı: iki proje çakışmasın.
    assert chrome.shared(tmp_path, port=9998) is not a


def test_the_browser_tool_is_in_the_subagent_registry() -> None:
    """"Alt ajanlar da görsün": browser yerleşik, alt ajan defterinde de var."""
    from dornick.tools import build_registry

    if not chrome.available():
        import pytest as _p
        _p.skip("bu makinede tarayıcı yok")
    assert "browser" in build_registry(subagents=False)


def test_the_tool_offers_fill_and_submit() -> None:
    """Form doldurma araç yüzeyinde olmalı: dornick, ürettiği uygulamada giriş
    yapamazsa giriş-sonrası sayfaları hiç doğrulayamıyor."""
    from dornick.tools import ToolRegistry
    from dornick.tools import browser as surf

    registry = ToolRegistry()
    surf.register(registry)
    spec = registry.get("browser")
    assert spec is not None
    actions = spec.input_schema["properties"]["action"]["enum"]
    assert "fill" in actions and "submit" in actions
    for prop in ("selector", "label", "name", "placeholder"):
        assert prop in spec.input_schema["properties"]


def test_the_tool_stays_shut_until_the_user_opens_it(tmp_path) -> None:
    """Kapalı tarayıcı bir eksiklik değil, bir tercih: araç bunu söylemeli
    ve kendiliğinden açmamalı."""
    import asyncio

    from dornick.config import Config
    from dornick.events import EventLog
    from dornick.session import Session
    from dornick.tools import ToolContext, ToolRegistry
    from dornick.tools import browser as surf

    registry = ToolRegistry()
    surf.register(registry)
    spec = registry.get("browser")
    assert spec is not None
    assert spec.mutates is True   # sayfa açmak dışa dönük bir eylem

    config = Config.load(tmp_path)
    ctx = ToolContext(
        config=config,
        session=Session(EventLog(tmp_path / "s.jsonl"), "test"),
        cancel=asyncio.Event(),
    )
    answer = asyncio.run(spec.handler({"action": "tabs"}, ctx))
    assert answer.is_error
    assert "Ayarlar" in answer.content
