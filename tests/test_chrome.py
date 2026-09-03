"""dornick chrome — the CDP client.

No real browser in the test; its absence does not lower the test's value
because the fragile part is the protocol: WebSocket frames (mask, 16/64-bit
lengths, fragmented messages) and CDP's request/answer matching. Both are
driven here with real sockets, against a fake server.
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


# -- fake WebSocket server ----------------------------------------------


def _accept_key(key: str) -> str:
    digest = hashlib.sha1((key + GUID).encode("ascii")).digest()
    return base64.b64encode(digest).decode("ascii")


def _read_frame(conn: socket.socket) -> tuple[int, bytes]:
    head = conn.recv(2)
    if len(head) < 2:
        raise ConnectionError("closed")
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
            raise ConnectionError("closed")
        body += piece
    if mask:
        body = bytes(b ^ mask[i % 4] for i, b in enumerate(body))
    return opcode, body


def _send_text(conn: socket.socket, payload: bytes) -> None:
    # Server frames go unmasked.
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
    """Fake server: shakes hands with every connection, returns `answer` for every message.

    A loop, not one per connection: `Browser` opens a fresh connection for
    every CDP call — a single `accept` hung on the second call.
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
                return  # the box closed, the test is over
            threading.Thread(target=talk, args=(conn,), daemon=True).start()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    return f"ws://127.0.0.1:{port}/dev", thread, box


# -- wire ---------------------------------------------------------------


def test_the_wire_echoes_small_and_giant_frames() -> None:
    """The 7-, 16- and 64-bit length paths — a screenshot really uses the
    64-bit one, that path cannot be left untested."""
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


# -- fake CDP -----------------------------------------------------------


# Keystrokes the fake CDP saw — the press/type tests read this.
KEYSTROKES: list[dict[str, Any]] = []

# Page scripts sent to the fake CDP — the fill/submit tests check from here
# that the JS sent carries the right criteria and events.
EXPRESSIONS: list[str] = []

# The page contract of the fill/submit helpers ({ok} / {err, adaylar});
# the test fills these boxes according to its scenario.
FILL_OUTCOME: dict[str, Any] = {}
SUBMIT_OUTCOME: dict[str, Any] = {}


def cdp_answer(body: bytes) -> bytes:
    """A tiny CDP that knows Runtime.evaluate, screenshot, navigate and Input.*."""
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
        # The click/focus helpers are long IIFEs; return the matched text.
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
        result = {"data": base64.b64encode(b"fake-jpeg").decode("ascii")}
    elif method == "Page.navigate":
        result = {"frameId": "1"}
    elif method == "Input.dispatchKeyEvent":
        KEYSTROKES.append(params)
        result = {}
    else:
        result = {}
    return json.dumps({"id": message.get("id"), "result": result}).encode("utf-8")


class FakeCdpHttp:
    """CDP's http face: /json/version, /json/list, /json/new."""

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
                    self._json({"Browser": "Fake/1.0"})
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
    """tabs → read → screenshot, with real sockets against the fake server."""
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
    """Phase 2: clicking by text, typing into a field and a special key —
    all turn into real CDP calls."""
    KEYSTROKES.clear()
    ws_url, _thread, ws_box = ws_server(cdp_answer)
    http = FakeCdpHttp(ws_url)
    try:
        box = chrome.Browser(tmp_path, port=http.port)
        tab = box.tabs()[0]

        assert box.click(tab, "Giriş") == "Giriş"

        box.type(tab, "ab", into="e-posta")
        # Two characters → four events (keyDown + keyUp each).
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
    """The script fill sends to the page must carry the target criteria
    (label/name/placeholder/selector) and fire the input+change events the
    frameworks listen to — otherwise a React form never sees the value."""
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
        # The target criteria must have gone to the page.
        assert '"E-posta"' in source and '"ali@ornek.com"' in source
        # Label, name and placeholder matching are in the page script.
        for needle in ("labels", "aria-label", "el.name", "el.placeholder"):
            assert needle in source
        # Native setter + input/change events: frameworks listen to these.
        assert "getOwnPropertyDescriptor" in source
        assert 'new Event("input"' in source and 'new Event("change"' in source
    finally:
        http.stop()
        ws_box.close()


def test_a_crowded_fill_match_names_the_candidates(tmp_path) -> None:
    """When several fields match, the first is not written silently: the
    error lists the candidates so the model can narrow the target."""
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
    box = chrome.Browser(tmp_path, port=1)  # no server; there must be no call either
    with pytest.raises(chrome.BrowseError):
        box.fill({"webSocketDebuggerUrl": "ws://127.0.0.1:1/x"}, "metin")


def test_submit_finds_the_form_and_reports_the_button(tmp_path) -> None:
    """submit must know both routes: click if there is a button, otherwise
    requestSubmit. A given selector must reach the page; the multi-form
    error must come with candidates."""
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
        # Both submission routes are in the page script: button click + requestSubmit.
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


# -- tool gate ----------------------------------------------------------


def test_every_registry_shares_one_browser(tmp_path) -> None:
    """The main agent and the subagents carry separate tool registries; all
    must drive the SAME browser — otherwise every registry opens its own
    Chrome and races on the same port."""
    a = chrome.shared(tmp_path, port=9999)
    b = chrome.shared(tmp_path, port=9999)
    assert a is b
    # A different profile/port is a separate browser: two projects must not clash.
    assert chrome.shared(tmp_path, port=9998) is not a


def test_the_browser_tool_is_in_the_subagent_registry() -> None:
    """"Subagents should see it too": browser is built in, present in the subagent registry as well."""
    from dornick.tools import build_registry

    if not chrome.available():
        import pytest as _p
        _p.skip("no browser on this machine")
    assert "browser" in build_registry(subagents=False)


def test_the_tool_offers_fill_and_submit() -> None:
    """Form filling must be on the tool surface: if dornick cannot log in
    to the app it built, it can never verify the post-login pages."""
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
    """A closed browser is not a deficiency, it is a preference: the tool
    must say so and must not open it on its own."""
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
    assert spec.mutates is True   # opening a page is an outward-facing action

    config = Config.load(tmp_path)
    ctx = ToolContext(
        config=config,
        session=Session(EventLog(tmp_path / "s.jsonl"), "test"),
        cancel=asyncio.Event(),
    )
    answer = asyncio.run(spec.handler({"action": "tabs"}, ctx))
    assert answer.is_error
    assert "Ayarlar" in answer.content
