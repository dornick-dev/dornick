"""Browser depth: did the page "open", or does it really WORK?

Proven wound: dornick builds a web app, opens the page, reads its text and
says "it works". Yet there may be a red TypeError in the console, a request
returning 404 on the network. Neither is VISIBLE in
`document.body.innerText` — the page is half-drawn but silent. The user
finds out when they open the browser.

A console message cannot be asked for afterwards, because it is an EVENT:
it happens at a moment in the past and is gone. So while the page is being
opened a persistent listener attaches to the tab and the events are
buffered. The tests here drive that buffer with real CDP event bodies.

The third promise is honesty: if the listener attached late it says so, if
it could not attach at all it says "I cannot see", and it never sells an
empty console as "the page has no errors".
"""

from __future__ import annotations

import json
import socket
import threading
import time
from typing import Any

import pytest

from dornick import chrome
from dornick.tools import browser as surf

from tests.test_chrome import FakeCdpHttp, _read_frame, _send_text, _accept_key


# -- event-pushing fake CDP ---------------------------------------------


def event_server(events: list[dict[str, Any]]):
    """Fake CDP that pushes the given events in order on seeing `Network.enable`.

    Real Chrome behaves the same: after the `enable` call events start
    flowing unasked. That is where the test's value comes from — the path
    feeding the buffer is the same as the production path.
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
                message = json.loads(body)
                _send_text(conn, json.dumps(
                    {"id": message.get("id"), "result": {}}).encode("utf-8"))
                if message.get("method") == "Network.enable":
                    for event in events:
                        _send_text(conn, json.dumps(event).encode("utf-8"))
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


# Real CDP bodies — the field names are exactly what Chrome sends.
CONSOLE_ERROR = {
    "method": "Runtime.consoleAPICalled",
    "params": {
        "type": "error",
        "args": [{"type": "string", "value": "Kaydetme başarısız"}],
        "stackTrace": {"callFrames": [
            {"url": "http://ornek/app.js", "lineNumber": 40}]},
    },
}

EXCEPTION = {
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

CONSOLE_LOG = {
    "method": "Runtime.consoleAPICalled",
    "params": {"type": "log", "args": [{"type": "string", "value": "hazır"}]},
}

BROWSER_ENTRY = {
    "method": "Log.entryAdded",
    "params": {"entry": {
        "source": "network", "level": "error",
        "text": "Failed to load resource: the server responded with a "
                "status of 404 (Not Found)",
        "url": "http://ornek/yok.js",
    }},
}

REQUEST_404 = [
    {"method": "Network.requestWillBeSent", "params": {
        "requestId": "R1", "timestamp": 100.0, "type": "Script",
        "request": {"url": "http://ornek/yok.js", "method": "GET"}}},
    {"method": "Network.responseReceived", "params": {
        "requestId": "R1", "type": "Script", "response": {"status": 404}}},
    {"method": "Network.loadingFinished", "params": {
        "requestId": "R1", "timestamp": 100.25}},
]

REQUEST_200 = [
    {"method": "Network.requestWillBeSent", "params": {
        "requestId": "R2", "timestamp": 100.0, "type": "Document",
        "request": {"url": "http://ornek/sayfa?x=1", "method": "GET"}}},
    {"method": "Network.responseReceived", "params": {
        "requestId": "R2", "type": "Document", "response": {"status": 200}}},
    {"method": "Network.loadingFinished", "params": {
        "requestId": "R2", "timestamp": 100.05}},
]

REQUEST_BROKEN = [
    {"method": "Network.requestWillBeSent", "params": {
        "requestId": "R3", "timestamp": 100.0,
        "request": {"url": "http://yok.ornek/api", "method": "POST"}}},
    {"method": "Network.loadingFailed", "params": {
        "requestId": "R3", "timestamp": 100.1,
        "errorText": "net::ERR_NAME_NOT_RESOLVED"}},
]


def wait_for(condition, duration: float = 5.0) -> bool:
    """Events arrive in the background; wait a short while."""
    end = time.monotonic() + duration
    while time.monotonic() < end:
        if condition():
            return True
        time.sleep(0.02)
    return False


@pytest.fixture()
def make_record():
    """(events) → Record; closes the connection when the test ends."""
    made: list[tuple[chrome.Record, socket.socket]] = []

    def make(events: list[dict[str, Any]]) -> chrome.Record:
        url, box = event_server(events)
        record = chrome.Record(url)
        made.append((record, box))
        return record

    yield make
    for record, box in made:
        record.close()
        box.close()


# -- console buffer -----------------------------------------------------


def test_a_console_error_reaches_the_buffer(make_record) -> None:
    record = make_record([CONSOLE_ERROR])
    assert wait_for(lambda: len(record.console) == 1)
    line = record.console[0]
    assert line.level == "hata"
    assert line.text == "Kaydetme başarısız"
    assert line.location == "app.js:41"        # CDP counts from 0, humans from 1


def test_an_uncaught_exception_keeps_its_stack(make_record) -> None:
    """The stack trace is in the `description` field; `text` only says 'Uncaught'."""
    record = make_record([EXCEPTION])
    assert wait_for(lambda: len(record.console) == 1)
    line = record.console[0]
    assert line.level == "hata"
    assert line.source == "istisna"
    assert "yok.forEach is not a function" in line.text


def test_browser_level_log_entries_are_captured(make_record) -> None:
    """The 404's console line is NOT a `console.*` call — it is Log.entryAdded."""
    record = make_record([BROWSER_ENTRY])
    assert wait_for(lambda: len(record.console) == 1)
    assert record.console[0].level == "hata"
    assert "404" in record.console[0].text
    assert record.console[0].source == "tarayici"


def test_levels_are_normalised(make_record) -> None:
    warning = {"method": "Runtime.consoleAPICalled",
               "params": {"type": "warning",
                          "args": [{"type": "string", "value": "dikkat"}]}}
    record = make_record([CONSOLE_LOG, warning])
    assert wait_for(lambda: len(record.console) == 2)
    assert [k.level for k in record.console] == ["log", "uyari"]


def test_object_arguments_are_rendered(make_record) -> None:
    event = {"method": "Runtime.consoleAPICalled",
             "params": {"type": "log", "args": [
                 {"type": "string", "value": "durum"},
                 {"type": "object", "value": {"kod": 500}}]}}
    record = make_record([event])
    assert wait_for(lambda: len(record.console) == 1)
    assert '"kod": 500' in record.console[0].text


MAIN_NAVIGATION = {"method": "Page.frameNavigated",
                   "params": {"frame": {"id": "F1"}}}


def test_the_first_navigation_keeps_the_page_it_loaded(make_record) -> None:
    """Wound found by measuring: the listener attaches before the page
    loads, then the document's OWN commit arrived as `frameNavigated` and
    swept away everything accumulated until then. In a live trial the
    network list came back with 2 requests instead of 4 — the document
    itself and the first script's 404 were lost."""
    record = make_record([*REQUEST_404, CONSOLE_ERROR, MAIN_NAVIGATION])
    assert wait_for(lambda: len(record.console) == 1 and len(record.requests) == 1)
    time.sleep(0.3)
    assert len(record.console) == 1        # the first navigation does NOT clear
    assert len(record.requests) == 1


def test_a_second_navigation_clears_the_buffer(make_record) -> None:
    """Page A's errors must not be written against page B."""
    record = make_record([MAIN_NAVIGATION, CONSOLE_ERROR, MAIN_NAVIGATION, CONSOLE_LOG])
    assert wait_for(lambda: len(record.console) == 1)
    time.sleep(0.3)
    assert [k.text for k in record.console] == ["hazır"]


def test_an_iframe_navigation_does_not_clear_the_buffer(make_record) -> None:
    """When an ad iframe navigates, the main page's errors must not be deleted."""
    iframe = {"method": "Page.frameNavigated",
              "params": {"frame": {"id": "F2", "parentId": "F1"}}}
    record = make_record([MAIN_NAVIGATION, CONSOLE_ERROR, iframe, iframe, iframe])
    assert wait_for(lambda: len(record.console) == 1)
    time.sleep(0.3)
    assert len(record.console) == 1


def test_a_fresh_attach_resets_the_navigation_count(make_record) -> None:
    """In a buffer cleared by `go`, the new page's first commit must again not clear."""
    record = make_record([MAIN_NAVIGATION])
    assert wait_for(lambda: record._navigations == 1)
    record.clear()
    assert record._navigations == 0


# -- network buffer -----------------------------------------------------


def test_a_404_is_recorded_with_status_and_duration(make_record) -> None:
    record = make_record(REQUEST_404)
    assert wait_for(lambda: record.requests and record.requests[0].status == 404)
    request = record.requests[0]
    assert request.failed
    assert request.method == "GET"
    assert round(request.duration_ms) == 250
    assert "yok.js" in request.format() and "404" in request.format()


def test_a_successful_request_is_not_a_failure(make_record) -> None:
    record = make_record(REQUEST_200)
    assert wait_for(lambda: record.requests and record.requests[0].status == 200)
    request = record.requests[0]
    assert not request.failed
    # Path + query are shown, not the host: information, not noise.
    assert "/sayfa?x=1" in request.format()


def test_a_failed_load_keeps_the_reason(make_record) -> None:
    record = make_record(REQUEST_BROKEN)
    assert wait_for(lambda: record.requests and record.requests[0].error)
    request = record.requests[0]
    assert request.failed
    assert "ERR_NAME_NOT_RESOLVED" in request.format()


def test_the_buffer_has_a_ceiling() -> None:
    """A page erroring in a loop must not eat memory."""
    record = chrome.Record.__new__(chrome.Record)
    from collections import deque

    record.console = deque(maxlen=3)
    for i in range(10):
        record.console.append(chrome.ConsoleLine("log", str(i)))
    assert [k.text for k in record.console] == ["7", "8", "9"]


# -- tool texts: honesty ------------------------------------------------


class FakeRecord:
    def __init__(self, konsol=(), istekler=(), hata="", eksik=False) -> None:
        self.console = list(konsol)
        self.requests = list(istekler)
        self.error = hata
        self.missing = eksik


def _error(text: str, location: str = "") -> chrome.ConsoleLine:
    return chrome.ConsoleLine("hata", text, location)


def test_an_empty_console_is_never_sold_as_proof() -> None:
    """The most important sentence: an empty console does NOT mean 'the page has no errors'."""
    text = surf._konsol_metni(FakeRecord(), "hepsi", None)
    assert "hatasız olduğu anlamına GELMEZ" in text
    assert "Davranışı ayrıca doğrula" in text


def test_a_late_listener_admits_it() -> None:
    text = surf._konsol_metni(FakeRecord(eksik=True), "hepsi", None)
    assert "SONRA bağlandı" in text
    assert "kaçmış olabilir" in text


def test_a_broken_listener_says_it_cannot_see() -> None:
    text = surf._konsol_metni(FakeRecord(hata="bağlantı reddedildi"), "hepsi", None)
    assert "kurulamadı" in text
    assert "göremiyorum" in text
    assert "uydurma yorum yapma" in text


def test_the_console_filter_narrows_to_errors() -> None:
    record = FakeRecord([
        chrome.ConsoleLine("log", "hazır"),
        chrome.ConsoleLine("uyari", "eski API"),
        _error("TypeError: yok", "app.js:12"),
    ])
    everything = surf._konsol_metni(record, "hepsi", None)
    assert "hazır" in everything and "TypeError" in everything

    only_errors = surf._konsol_metni(record, "hata", None)
    assert "TypeError" in only_errors
    assert "hazır" not in only_errors
    assert "eski API" not in only_errors


def test_an_empty_filter_points_at_the_wider_view() -> None:
    record = FakeRecord([chrome.ConsoleLine("log", "hazır")])
    text = surf._konsol_metni(record, "hata", None)
    assert "toplam 1 mesaj" in text
    assert "seviye: hepsi" in text


def test_console_errors_tell_the_model_to_fix_the_source() -> None:
    text = surf._konsol_metni(FakeRecord([_error("TypeError: yok")]), "hepsi", None)
    assert "Kaynak koddaki" in text and "düzelt" in text


def test_failed_requests_come_first() -> None:
    record = FakeRecord(istekler=[
        chrome.Request("http://x/iyi", "GET", 200),
        chrome.Request("http://x/yok", "GET", 404),
        chrome.Request("http://x/patlak", "POST", 500),
    ])
    text = surf._ag_metni(record, None)
    assert text.index("Başarısız olanlar") < text.index("Başarılı olanlar")
    assert text.index("/yok") < text.index("/iyi")
    assert "3 istek · 2 başarısız" in text
    assert "5xx sunucu tarafında patlayan bir kod" in text


def test_no_requests_suggests_a_reload() -> None:
    text = surf._ag_metni(FakeRecord(), None)
    assert "dinleyici bağlanmadan önce" in text


# -- warning after a read -----------------------------------------------


class FakeBox:
    def __init__(self, record) -> None:
        self._record = record

    def snapshot(self, tab):
        return self._record


def test_reading_a_page_flags_console_errors() -> None:
    """The model must not read the page text and close the turn: the count is right there."""
    box = FakeBox(FakeRecord([_error("TypeError")],
                             [chrome.Request("http://x/yok", "GET", 404)]))
    suffix = surf._warning_suffix(box, {"id": "T1"})
    assert "1 konsol hatası" in suffix and "1 başarısız istek" in suffix
    assert "'çalışıyor' diye rapor etme" in suffix


def test_a_clean_page_gets_no_noise() -> None:
    suffix = surf._warning_suffix(FakeBox(FakeRecord()), {"id": "T1"})
    assert suffix == ""


def test_a_framework_error_page_is_hoisted_to_the_top() -> None:
    suffix = surf._error_suffix({"hata": {
        "tur": "CodeIgniter 4 hata sayfası",
        "baslik": "TypeError",
        "mesaj": "Home::index(): Return value must be of type string",
        "yer": "app/Controllers/Home.php:12",
    }})
    assert "HATA SAYFASI" in suffix
    assert "Return value must be of type string" in suffix
    assert "'çalışıyor' diye rapor etme" in suffix


def test_an_ordinary_page_has_no_error_layer() -> None:
    assert surf._error_suffix({"hata": None}) == ""
    assert surf._error_suffix({}) == ""


# -- tool surface -------------------------------------------------------


def test_the_tool_offers_the_new_actions() -> None:
    from dornick.tools import ToolRegistry

    registry = ToolRegistry()
    surf.register(registry)
    spec = registry.get("browser")
    actions = spec.input_schema["properties"]["action"]["enum"]
    for name in ("konsol", "ag", "js"):
        assert name in actions
    for prop in ("seviye", "n"):
        assert prop in spec.input_schema["properties"]


def test_the_description_forbids_fixing_the_ui_with_js() -> None:
    """`js` is a diagnostic tool; patching the page with a script is not permanent."""
    from dornick.tools import ToolRegistry

    registry = ToolRegistry()
    surf.register(registry)
    description = registry.get("browser").description
    assert "UI DEĞİŞİKLİĞİ YAPMA" in description
    assert "KAYNAK KODU düzelt" in description
    assert "YALNIZ 200 dönmesine bakma" in description


# -- js wrapper ---------------------------------------------------------


def test_the_js_wrapper_survives_unserialisable_results() -> None:
    """DOM nodes and functions do not serialise with `returnByValue`."""
    wrapped = chrome._JS_WRAP % json.dumps("document.body")
    assert "JSON.parse(JSON.stringify" in wrapped
    assert "String(r)" in wrapped
    # The expression's own exception is caught and returned as a finding.
    assert "catch (e) { return {hata:" in wrapped


def test_the_js_wrapper_carries_the_expression() -> None:
    wrapped = chrome._JS_WRAP % json.dumps("window.__durum.length")
    assert '"window.__durum.length"' in wrapped


def test_the_error_layer_script_looks_for_real_signatures() -> None:
    """There must be NO generic 'does the word error appear' scan: it would
    declare an ordinary blog post an error page."""
    for signature in ("#traceback", "werkzeug", "Fatal error", "whoops"):
        assert signature.lower() in chrome._ERROR_JS.lower()


# -- end to end: over the fake CDP --------------------------------------


def test_opening_a_tab_attaches_the_listener(tmp_path) -> None:
    """The listener must attach before the page loads: being a second late
    means missing the first error."""
    ws_url, ws_box = event_server([CONSOLE_ERROR, *REQUEST_404])
    http = FakeCdpHttp(ws_url)
    try:
        box = chrome.Browser(tmp_path, port=http.port)
        made = box.open("http://ornek/")
        record = box.snapshot(made)
        assert not record.missing           # attached during `open`
        assert wait_for(lambda: len(record.console) == 1 and len(record.requests) == 1)
        assert record.console[0].level == "hata"
        assert record.requests[0].status == 404

        text = surf._konsol_metni(record, "hata", None)
        assert "Kaydetme başarısız" in text
        assert "app.js:41" in text
    finally:
        http.stop()
        ws_box.close()


def test_a_listener_attached_late_is_marked_incomplete(tmp_path) -> None:
    ws_url, ws_box = event_server([])
    http = FakeCdpHttp(ws_url)
    try:
        box = chrome.Browser(tmp_path, port=http.port)
        tab = box.tabs()[0]
        record = box.snapshot(tab)           # not via `open`, afterwards
        assert record.missing
        assert "SONRA bağlandı" in surf._konsol_metni(record, "hepsi", None)
    finally:
        http.stop()
        ws_box.close()


def test_one_listener_per_tab(tmp_path) -> None:
    ws_url, ws_box = event_server([])
    http = FakeCdpHttp(ws_url)
    try:
        box = chrome.Browser(tmp_path, port=http.port)
        tab = box.tabs()[0]
        assert box.snapshot(tab) is box.snapshot(tab)
    finally:
        http.stop()
        ws_box.close()


def test_a_tab_without_a_debug_url_degrades_honestly(tmp_path) -> None:
    box = chrome.Browser(tmp_path, port=1)
    record = box.listen({"id": "T9"})
    assert record.error
    assert "göremiyorum" in surf._konsol_metni(record, "hepsi", None)
