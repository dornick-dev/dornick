"""dornick chrome — driving the browser through the DevTools protocol.

The native counterpart of Claude's Chrome extension: dornick starts Chrome
or Edge with the debugging port (`--remote-debugging-port`) and talks over
the DevTools protocol (CDP) — sees tabs, opens pages, reads the text, takes
screenshots.

The browser opens **with Dornick's own profile** (`.dornick/chrome/`):
attaching to the user's everyday Chrome is not possible because that one
starts with the port closed. The separate profile is also a boundary — the
user sees only the sites they signed in to through dornick, and those
sessions persist in the profile folder: a site signed in once can be
entered the next day too.

CDP has two faces:
    http  tab list, opening/closing tabs — plain JSON endpoints
    ws    the inside of the page (running JavaScript, screenshots)

The stdlib has no WebSocket client; the `Wire` here does just enough:
single connection, masked text frames, fragmented messages and ping/pong.
Too small a job to be worth a library dependency.
"""

from __future__ import annotations

import base64
import json
import os
import socket
import struct
import subprocess
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import environment

DEFAULT_PORT = 9222

# The browser opening the port can be slow on first setup.
BOOT_WAIT_S = 20.0

# Wait for a single CDP answer. A screenshot can take a few seconds on a
# large page.
CALL_TIMEOUT_S = 30.0


class BrowseError(RuntimeError):
    """Browser error — the message goes to the model, it must be instructive."""


def executable() -> str | None:
    """Installed Chrome/Edge. If not on PATH, known locations are checked."""
    import shutil

    for name in ("chrome", "msedge", "chromium", "google-chrome", "brave"):
        if found := shutil.which(name):
            return found

    trunk = os.environ.get("ProgramFiles", r"C:\Program Files")
    branch = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    local = os.environ.get("LOCALAPPDATA", "")
    for spot in (
        rf"{trunk}\Google\Chrome\Application\chrome.exe",
        rf"{branch}\Google\Chrome\Application\chrome.exe",
        rf"{local}\Google\Chrome\Application\chrome.exe",
        rf"{trunk}\Microsoft\Edge\Application\msedge.exe",
        rf"{branch}\Microsoft\Edge\Application\msedge.exe",
    ):
        if spot and Path(spot).is_file():
            return spot
    return None


def available() -> bool:
    return executable() is not None


# Process-wide single browser. The main agent and the subagents carry
# separate tool registries; if each built its own Browser they would try to
# open the same port at once and race. One instance: all drive the same
# Chrome, all see the same tabs.
_shared: dict[tuple[str, int], "Browser"] = {}
_shared_lock: Any = None


def shared(state_dir: Path | str, port: int = DEFAULT_PORT) -> "Browser":
    import threading

    global _shared_lock
    if _shared_lock is None:
        _shared_lock = threading.Lock()
    key = (str(state_dir), int(port))
    with _shared_lock:
        box = _shared.get(key)
        if box is None:
            box = Browser(state_dir, port)
            _shared[key] = box
        return box


# -- WebSocket wire -----------------------------------------------------


class Wire:
    """As much of RFC 6455 as CDP needs — client side.

    Client frames must go masked; the server's arrive bare. If the length
    does not fit in 7 bits there is a 16- or 64-bit extension — a
    screenshot really uses the 64-bit path.
    """

    def __init__(self, url: str, timeout: float = CALL_TIMEOUT_S) -> None:
        from urllib.parse import urlsplit

        parts = urlsplit(url)
        host = parts.hostname or "127.0.0.1"
        port = parts.port or 80
        path = parts.path or "/"

        self.sock = socket.create_connection((host, port), timeout=timeout)
        self.sock.settimeout(timeout)

        key = base64.b64encode(os.urandom(16)).decode("ascii")
        self.sock.sendall(
            (
                f"GET {path} HTTP/1.1\r\n"
                f"Host: {host}:{port}\r\n"
                "Upgrade: websocket\r\n"
                "Connection: Upgrade\r\n"
                f"Sec-WebSocket-Key: {key}\r\n"
                "Sec-WebSocket-Version: 13\r\n\r\n"
            ).encode("ascii")
        )
        answer = b""
        while b"\r\n\r\n" not in answer:
            piece = self.sock.recv(4096)
            if not piece:
                raise BrowseError("El sıkışma yarıda kesildi.")
            answer += piece
        if b" 101 " not in answer.split(b"\r\n", 1)[0]:
            raise BrowseError("Tarayıcı WebSocket'e geçmeyi kabul etmedi.")

    def send(self, text: str) -> None:
        payload = text.encode("utf-8")
        head = bytearray([0x81])  # FIN + text
        size = len(payload)
        if size < 126:
            head.append(0x80 | size)
        elif size < 1 << 16:
            head.append(0x80 | 126)
            head += struct.pack(">H", size)
        else:
            head.append(0x80 | 127)
            head += struct.pack(">Q", size)
        mask = os.urandom(4)
        head += mask
        veiled = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        self.sock.sendall(bytes(head) + veiled)

    def recv(self) -> str:
        """One message — reassembled if fragmented."""
        gathered = b""
        while True:
            first, second = self._exactly(2)
            fin = bool(first & 0x80)
            opcode = first & 0x0F
            size = second & 0x7F
            if size == 126:
                (size,) = struct.unpack(">H", self._exactly(2))
            elif size == 127:
                (size,) = struct.unpack(">Q", self._exactly(8))
            # The server does not mask; if it does, it is still read.
            mask = self._exactly(4) if second & 0x80 else b""
            body = self._exactly(size) if size else b""
            if mask:
                body = bytes(b ^ mask[i % 4] for i, b in enumerate(body))

            if opcode == 0x9:  # ping → pong, with the same body
                pong = bytearray([0x8A, 0x80 | len(body)])
                veil = os.urandom(4)
                pong += veil + bytes(b ^ veil[i % 4] for i, b in enumerate(body))
                self.sock.sendall(bytes(pong))
                continue
            if opcode == 0x8:
                raise BrowseError("Tarayıcı bağlantıyı kapattı.")
            if opcode == 0xA:  # pong — unasked for but harmless
                continue

            gathered += body
            if fin:
                return gathered.decode("utf-8", "replace")

    def _exactly(self, count: int) -> bytes:
        data = b""
        while len(data) < count:
            piece = self.sock.recv(count - len(data))
            if not piece:
                raise BrowseError("Bağlantı koptu.")
            data += piece
        return data

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass


# -- event buffer -------------------------------------------------------
#
# Proven wound: dornick builds a web app, opens the page, reads the text and
# says "it works". Yet JavaScript may have blown up on the page — a red
# stack trace in the console, a request returning 500 on the network. These
# are INVISIBLE in `document.body.innerText`; the page is half-drawn but
# silent. The user finds out when they open the browser.
#
# `read` cannot solve this alone, because a console message is an EVENT: it
# happens at a moment in the past and is gone. It cannot be asked for
# afterwards, only listened for. So while the page is being opened a
# persistent listener attaches to the tab and the events accumulate here.
#
# Honesty rule: if the listener attached AFTER the page loaded, earlier
# messages were missed. We do not make that up — we say so with the `eksik`
# flag, because the difference between "console clean" and "I was late to
# look" is whether the user finds the bug.

# Maximum records kept per tab. A page erroring in a loop produces hundreds
# of lines a second; the freshest are the most useful anyway.
TAMPON = 300

# Number of records shown to the model by default.
DEFAULT_N = 20

# Common names of the CDP levels. "warning" and "warn" are the same thing.
_LEVELS = {
    "log": "log", "info": "info", "debug": "debug", "verbose": "debug",
    "warning": "uyari", "warn": "uyari", "error": "hata", "assert": "hata",
    "trace": "log", "dir": "log", "table": "log",
}


@dataclass(slots=True)
class ConsoleLine:
    """A single console message or uncaught exception."""

    seviye: str            # log | info | debug | uyari | hata
    metin: str
    location: str = ""     # file:line
    source: str = "konsol"  # konsol | istisna | tarayici

    def format(self) -> str:
        label = {"hata": "HATA", "uyari": "UYARI"}.get(self.seviye, self.seviye)
        tail = f"  ({self.location})" if self.location else ""
        return f"[{label}] {self.metin}{tail}"


@dataclass(slots=True)
class Request:
    """A single network request: path, method, status, duration."""

    url: str
    method: str = "GET"
    status: int = 0
    kind: str = ""
    duration_ms: float = 0.0
    error: str = ""
    _t0: float = 0.0

    @property
    def failed(self) -> bool:
        return bool(self.error) or self.status >= 400

    def format(self) -> str:
        from urllib.parse import urlsplit

        parts = urlsplit(self.url)
        short = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
        if len(short) > 80:
            short = short[:77] + "…"
        if self.error:
            return f"{self.method} {short} — BAŞARISIZ: {self.error}"
        status = self.status or "?"
        duration = f"{self.duration_ms:.0f} ms" if self.duration_ms else "—"
        return f"{self.method} {short} → {status} · {duration}"


def _arg_text(arg: dict[str, Any]) -> str:
    """Turns a CDP RemoteObject into readable text.

    If `value` exists that is it; otherwise Chrome's own description
    (`description`) — for an Error object the whole stack trace sits there.
    """
    if "value" in arg:
        value = arg["value"]
        if isinstance(value, (dict, list)):
            try:
                return json.dumps(value, ensure_ascii=False)[:400]
            except (TypeError, ValueError):  # pragma: no cover
                return str(value)[:400]
        return str(value)
    for key in ("description", "unserializableValue", "className"):
        if arg.get(key):
            return str(arg[key])
    return str(arg.get("type") or "?")


def _location(url: Any, line: Any) -> str:
    """"http://x/app.js:41" — empty if neither is present."""
    text = str(url or "").strip()
    if not text:
        return ""
    short = text.rsplit("/", 1)[-1] or text
    try:
        n = int(line)
    except (TypeError, ValueError):
        return short
    return f"{short}:{n + 1}"


class Record:
    """A listener persistently attached to a tab: console and network buffer.

    Holds its own WebSocket connection and reads in the background. The
    `Browser`'s other calls open a fresh connection every time (`_call`);
    modern Chrome accepts multiple clients on the same target, so the two
    can live side by side. If we cannot connect it is not a disaster: `hata`
    is filled and the tool says "listener could not be set up" — opening the
    page still goes ahead.
    """

    def __init__(self, ws_url: str, *, limit: int = TAMPON) -> None:
        import threading

        self.konsol: deque[ConsoleLine] = deque(maxlen=limit)
        self.istekler: deque[Request] = deque(maxlen=limit)
        self.hata = ""
        # If the listener attached after the page loaded: the first messages
        # were missed. The model must know.
        self.eksik = False
        self.started = time.monotonic()
        self._open: dict[str, Request] = {}
        self._closed = False
        self._wire: Wire | None = None
        self._seq = 1000
        # Which main-frame navigation are we in? The first is the load of
        # the page we are waiting for; we do not clear that one.
        self._navigations = 0

        try:
            wire = Wire(ws_url, timeout=CALL_TIMEOUT_S)
            # Listening is indefinite: a timeout would cut in the middle of a
            # frame and break the stream. The connection ends with `close()`.
            wire.sock.settimeout(None)
            self._wire = wire
            for domain in ("Runtime.enable", "Log.enable", "Network.enable",
                           "Page.enable"):
                self._seq += 1
                wire.send(json.dumps({"id": self._seq, "method": domain,
                                      "params": {}}))
        except Exception as exc:
            self.hata = f"{type(exc).__name__}: {exc}"
            return

        self._thread = threading.Thread(target=self._listen, daemon=True)
        self._thread.start()

    @property
    def running(self) -> bool:
        return self._wire is not None and not self._closed

    def clear(self) -> None:
        """Moved to a new page: the old page's records are noise."""
        self.konsol.clear()
        self.istekler.clear()
        self._open.clear()
        self.eksik = False
        self._navigations = 0
        self.started = time.monotonic()

    def close(self) -> None:
        self._closed = True
        if self._wire is not None:
            self._wire.close()

    # -- event loop ----------------------------------------------------

    def _listen(self) -> None:
        wire = self._wire
        assert wire is not None
        while not self._closed:
            try:
                raw = wire.recv()
            except Exception:
                return  # connection closed or dropped; end quietly
            try:
                message = json.loads(raw)
            except ValueError:  # pragma: no cover - broken frame
                continue
            method = message.get("method")
            if not method:
                continue  # the answer to our own `enable` calls
            try:
                self._handle(str(method), message.get("params") or {})
            except Exception:  # pragma: no cover - one event must not break everything
                continue

    def _handle(self, method: str, p: dict[str, Any]) -> None:
        if method == "Runtime.consoleAPICalled":
            level = _LEVELS.get(str(p.get("type") or "log"), "log")
            text = " ".join(_arg_text(a) for a in (p.get("args") or [])
                            if isinstance(a, dict))
            frames = ((p.get("stackTrace") or {}).get("callFrames") or [])
            first = frames[0] if frames else {}
            self.konsol.append(ConsoleLine(
                level, text.strip() or "(boş mesaj)",
                _location(first.get("url"), first.get("lineNumber")), "konsol"))

        elif method == "Runtime.exceptionThrown":
            details = p.get("exceptionDetails") or {}
            obj = details.get("exception") or {}
            # `description` carries the stack trace too; otherwise `text` remains.
            text = str(obj.get("description") or details.get("text")
                       or "yakalanmamış istisna")
            self.konsol.append(ConsoleLine(
                "hata", text.strip(),
                _location(details.get("url"), details.get("lineNumber")), "istisna"))

        elif method == "Log.entryAdded":
            # The browser's own log: "Failed to load resource: 404", CSP
            # violations, mixed-content warnings. Lines that show in the
            # page's console but are NOT `console.*` calls live here.
            entry = p.get("entry") or {}
            level = _LEVELS.get(str(entry.get("level") or "info"), "log")
            self.konsol.append(ConsoleLine(
                level, str(entry.get("text") or "").strip() or "(boş kayıt)",
                _location(entry.get("url"), entry.get("lineNumber")), "tarayici"))

        elif method == "Network.requestWillBeSent":
            request = p.get("request") or {}
            record = Request(
                url=str(request.get("url") or ""),
                method=str(request.get("method") or "GET"),
                kind=str(p.get("type") or ""),
                _t0=float(p.get("timestamp") or 0.0),
            )
            ident = str(p.get("requestId") or "")
            if ident:
                self._open[ident] = record
            self.istekler.append(record)

        elif method == "Network.responseReceived":
            if (record := self._open.get(str(p.get("requestId") or ""))) is None:
                return
            response = p.get("response") or {}
            record.status = int(response.get("status") or 0)
            if kind := str(p.get("type") or ""):
                record.kind = kind

        elif method in ("Network.loadingFinished", "Network.loadingFailed"):
            ident = str(p.get("requestId") or "")
            if (record := self._open.pop(ident, None)) is None:
                return
            end = float(p.get("timestamp") or 0.0)
            if record._t0 and end > record._t0:
                record.duration_ms = (end - record._t0) * 1000.0
            if method == "Network.loadingFailed":
                cancelled = bool(p.get("canceled"))
                record.error = str(p.get("errorText") or
                                   ("iptal edildi" if cancelled else "yüklenemedi"))

        elif method == "Page.frameNavigated":
            # New document: the old page's records are now noise — the model
            # must not write page A's errors against page B.
            #
            # BUT the first navigation is not cleared, and this was learnt by
            # measuring: the listener attaches before the page loads, then
            # the document's own commit arrives as `frameNavigated` and was
            # sweeping away the requests accumulated until then (the
            # document itself, the first scripts, the first 404s). In a live
            # trial the network list came back with 2 requests instead of 4.
            # So only the SECOND and later navigations clear: the first is
            # the page we were waiting for anyway.
            if (p.get("frame") or {}).get("parentId"):
                return  # an iframe navigation does not change the page
            self._navigations += 1
            if self._navigations > 1:
                self.konsol.clear()
                self.istekler.clear()
                self._open.clear()


# -- browser ------------------------------------------------------------


class Browser:
    """A Chrome/Edge with the debugging port open, and its tabs."""

    def __init__(self, state_dir: Path | str, port: int = DEFAULT_PORT) -> None:
        import threading

        self.state_dir = Path(state_dir)
        self.port = port
        self._proc: subprocess.Popen[bytes] | None = None
        # On the shared instance two subagents may try to launch at once;
        # let the launch happen once.
        self._boot_lock = threading.Lock()
        # Tab id → listener. One listener per tab is enough.
        self._records: dict[str, Record] = {}

    # -- http face -----------------------------------------------------

    def _http(self, path: str, method: str = "GET") -> Any:
        import urllib.request

        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}", method=method
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            raw = response.read().decode("utf-8", "replace")
        return json.loads(raw) if raw.strip() else {}

    def alive(self) -> bool:
        try:
            return bool(self._http("/json/version"))
        except Exception:
            return False

    def ensure(self) -> None:
        """Leaves the browser alone if it is up; otherwise launches it with its own profile."""
        if self.alive():
            return
        with self._boot_lock:
            # Someone else may have launched while we waited for the lock.
            if self.alive():
                return
            self._launch()

    def _launch(self) -> None:
        exe = executable()
        if exe is None:
            raise BrowseError(
                "Chrome ya da Edge bulunamadı. Biri kuruluysa PATH'e ekli olmalı."
            )
        profile = self.state_dir / "chrome"
        profile.mkdir(parents=True, exist_ok=True)
        self._proc = subprocess.Popen(
            [
                exe,
                f"--remote-debugging-port={self.port}",
                f"--user-data-dir={profile}",
                "--no-first-run",
                "--no-default-browser-check",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            # Chrome/Edge is already a windowed (GUI) process; the flag
            # guarantees no cmd flash even when launched from a console
            # wrapper.
            **environment.quiet_flags(),
        )
        deadline = time.monotonic() + BOOT_WAIT_S
        while time.monotonic() < deadline:
            if self.alive():
                return
            time.sleep(0.4)
        raise BrowseError("Tarayıcı açıldı ama hata ayıklama kapısı cevap vermiyor.")

    def tabs(self) -> list[dict[str, Any]]:
        found = self._http("/json/list")
        return [t for t in found if isinstance(t, dict) and t.get("type") == "page"]

    def open(self, url: str) -> dict[str, Any]:
        """Opens an address in a new tab — navigating AFTER the listener attaches.

        The tab could be opened directly with the target address
        (`/json/new?<url>`) and it was at first; but then the load is well
        under way by the time we attach the listener. The result was
        measured in a live trial: the document's own request and the first
        script's 404 NEVER showed in the network list. So the tab opens
        blank, the listener attaches, and the navigation starts after that —
        everything is on record from the first byte.
        """
        from urllib.parse import quote

        spot = "/json/new?" + quote("about:blank", safe=":/?&=%")
        try:
            # New Chrome wants PUT; the old one accepted GET.
            made = self._http(spot, method="PUT")
        except Exception:
            made = self._http(spot)
        if not isinstance(made, dict) or not made.get("id"):
            raise BrowseError("Sekme açılamadı.")

        self.listen(made, fresh=True)
        try:
            self._call(made, "Page.navigate", {"url": url})
        except BrowseError:
            # If the navigation could not be set up, try opening the tab
            # with the address: not opening the page at all for the sake of
            # a half listener is a bad trade.
            fallback = "/json/new?" + quote(url, safe=":/?&=%")
            try:
                made = self._http(fallback, method="PUT")
            except Exception:
                made = self._http(fallback)
            self.listen(made, fresh=True)
        made["url"] = url
        return made

    def close_tab(self, tab_id: str) -> None:
        if (record := self._records.pop(str(tab_id), None)) is not None:
            record.close()
        try:
            self._http(f"/json/close/{tab_id}")
        except Exception:
            pass

    # -- listener ------------------------------------------------------

    def listen(self, tab: dict[str, Any], *, fresh: bool = False) -> Record:
        """Attaches a persistent listener to the tab; returns the existing one if present.

        `fresh=True` announces a move to a new page: the old page's records
        are cleared and the "I was late" flag drops.

        If the listener CANNOT be set up nothing collapses — `Record.hata`
        is filled and the tool says so honestly. Failing to open the page is
        worse than opening it and not being able to listen to the console.
        """
        ident = str(tab.get("id") or "")
        record = self._records.get(ident)
        if record is not None and record.running:
            if fresh:
                record.clear()
            return record
        if record is not None:
            record.close()

        spot = str(tab.get("webSocketDebuggerUrl") or "")
        if not spot:
            record = Record.__new__(Record)   # connectionless shell
            record.konsol, record.istekler = deque(), deque()
            record.hata = "sekmenin hata ayıklama adresi yok"
            record.eksik = True
            record._closed = True
            record._wire = None
            self._records[ident] = record
            return record

        record = Record(spot)
        # If not fresh the page may already be loaded: the first messages
        # were missed and we do not hide that.
        record.eksik = not fresh
        self._records[ident] = record
        return record

    def kayit(self, tab: dict[str, Any]) -> Record:
        """The tab's listener; set up now if missing (as a late one).

        (Name kept: tools/browser.py calls it.)
        """
        return self.listen(tab)

    # -- inside the page (ws) ------------------------------------------

    def _call(self, tab: dict[str, Any], method: str, params: dict[str, Any]) -> dict[str, Any]:
        spot = tab.get("webSocketDebuggerUrl")
        if not spot:
            raise BrowseError("Sekmenin hata ayıklama adresi yok (başka istemci bağlı olabilir).")
        wire = Wire(str(spot))
        try:
            wire.send(json.dumps({"id": 1, "method": method, "params": params}))
            deadline = time.monotonic() + CALL_TIMEOUT_S
            while time.monotonic() < deadline:
                answer = json.loads(wire.recv())
                if answer.get("id") != 1:
                    continue  # event notification; not our answer
                if "error" in answer:
                    raise BrowseError(str(answer["error"].get("message") or "CDP hatası"))
                result = answer.get("result")
                return result if isinstance(result, dict) else {}
            raise BrowseError(f"Cevap gelmedi: {method}")
        finally:
            wire.close()

    def eval(self, tab: dict[str, Any], expression: str) -> Any:
        answer = self._call(tab, "Runtime.evaluate", {
            "expression": expression,
            "returnByValue": True,
        })
        if "exceptionDetails" in answer:
            raise BrowseError(
                "Sayfa betiği hata verdi: "
                + str(answer["exceptionDetails"].get("text") or "")
            )
        return (answer.get("result") or {}).get("value")

    def read(self, tab: dict[str, Any], limit: int = 6000) -> dict[str, Any]:
        """The page's visible text. Waits a short while for it to load.

        `readyState` alone is not enough: a newly opened tab is
        `about:blank` for a moment and that page is instantly "complete" —
        the empty page was being read before the navigation even started.
        The address must settle too.
        """
        deadline = time.monotonic() + 8.0
        while time.monotonic() < deadline:
            state = self.eval(tab, "document.readyState")
            spot = str(self.eval(tab, "location.href") or "")
            if state == "complete" and spot not in ("", "about:blank"):
                break
            time.sleep(0.4)
        text = str(self.eval(
            tab, "document.body ? document.body.innerText : ''"
        ) or "").strip()
        title = str(self.eval(tab, "document.title") or "")
        spot = str(self.eval(tab, "location.href") or tab.get("url") or "")
        clipped = len(text) > limit
        return {
            "title": title,
            "url": spot,
            "text": text[:limit] + ("\n… (kırpıldı)" if clipped else ""),
            # Framework error page — a separate field if present. A
            # "Whoops!" heading lost inside the text was being overlooked.
            "hata": self.error_page(tab),
        }

    def error_page(self, tab: dict[str, Any]) -> dict[str, Any] | None:
        """Is the page a framework error page? If so its gist, else None.

        Why a separate field: CodeIgniter's "Whoops!", Django's yellow error
        page, Werkzeug's stack trace — all flow through `innerText` as
        ORDINARY text. The model failed to notice the exception class in the
        middle of a long page text and said "page opened".

        Detection is evidence-based: the framework's own signature (a DOM
        marker or a title pattern) is looked for. If none matches, None —
        labelling a page an "error page" is reporting an error that is not
        there.
        """
        try:
            finding = self.eval(tab, _ERROR_JS)
        except BrowseError:  # pragma: no cover - stay quiet if the page cannot be read
            return None
        return finding if isinstance(finding, dict) and finding.get("tur") else None

    def js(self, tab: dict[str, Any], expression: str) -> dict[str, Any]:
        """Runs a small expression on the page and returns the RESULT (diagnosis).

        If the result can be turned into JSON it comes as its value,
        otherwise as text: a DOM node or a function does not serialise with
        `returnByValue` and the bare call was blowing up there.

        The expression's own exception is not a TOOL error, it is a
        FINDING: it goes back to the model as "this error at that line",
        because that is what it asked.
        """
        answer = self.eval(tab, _JS_WRAP % json.dumps(expression))
        if not isinstance(answer, dict):  # pragma: no cover - the wrapper always returns a dict
            return {"tip": "?", "deger": answer}
        if answer.get("hata"):
            return {"tip": "hata", "deger": str(answer["hata"])}
        return {"tip": str(answer.get("tip") or "?"), "deger": answer.get("deger")}

    def screenshot(self, tab: dict[str, Any]) -> str:
        """Image of the visible area, as a data: URL."""
        answer = self._call(tab, "Page.captureScreenshot", {
            "format": "jpeg",
            "quality": 72,
        })
        data = str(answer.get("data") or "")
        if not data:
            raise BrowseError("Görüntü alınamadı.")
        return "data:image/jpeg;base64," + data

    # -- phase 2: interacting with the page ----------------------------

    def navigate(self, tab: dict[str, Any], url: str) -> dict[str, Any]:
        """Goes to another address in the same tab and reads the new page."""
        # Listener BEFORE navigating: the new page's first error must be caught too.
        self.listen(tab, fresh=True)
        self._call(tab, "Page.navigate", {"url": url})
        return self.read(tab)

    def click(self, tab: dict[str, Any], text: str) -> str:
        """Clicks a button or link by its text.

        Text, not pixels: the model sees the "Giriş" button, not its
        coordinates. The clickables on the page (button, link, role=button,
        input) are scanned and the best text match is clicked. An invisible
        match is skipped — clicking a hidden link does nothing.
        """
        want = json.dumps(text)
        found = self.eval(tab, _CLICK_JS % want)
        if not found:
            raise BrowseError(
                f"'{text}' ile eşleşen tıklanabilir bir şey bulunamadı. "
                "`read` ile sayfadaki bağlantı/düğme metinlerine bak."
            )
        return str(found)

    def type(self, tab: dict[str, Any], text: str, into: str = "") -> str:
        """Types text into a field.

        With `into` given the field is chosen by its label/placeholder; if
        empty the currently focused field (or the first empty text field) is
        used. Typing is not straight into the DOM but with real key events:
        some pages listen to the `input` event and do not see a direct value
        assignment.
        """
        focused = self.eval(tab, _FOCUS_JS % json.dumps(into))
        if not focused:
            raise BrowseError(
                (f"'{into}' alanı bulunamadı." if into else "Yazılacak bir alan bulunamadı.")
                + " `read` ile forma bak."
            )
        # Send the characters to the focused field as real key events.
        for ch in text:
            self._call(tab, "Input.dispatchKeyEvent", {"type": "keyDown", "text": ch})
            self._call(tab, "Input.dispatchKeyEvent", {"type": "keyUp", "text": ch})
        return str(focused)

    def press(self, tab: dict[str, Any], key: str) -> None:
        """A single special key: Enter, Tab, Escape…"""
        spec = _KEYS.get(key.lower())
        if spec is None:
            raise BrowseError(f"Bilinmeyen tuş: {key}. (Enter, Tab, Escape…)")
        for phase in ("keyDown", "keyUp"):
            self._call(tab, "Input.dispatchKeyEvent", {"type": phase, **spec})

    def fill(
        self,
        tab: dict[str, Any],
        text: str,
        *,
        selector: str = "",
        label: str = "",
        name: str = "",
        placeholder: str = "",
    ) -> str:
        """Finds a form field, clears it and writes the value.

        The difference from `type` is that it is targeted: the field is
        chosen by CSS selector or by visible label / name / placeholder.
        Writing is not a direct `value` assignment — frameworks (React etc.)
        do not count the value without seeing the native setter + `input`
        and `change` events; the in-page helper does both. If several fields
        match, the error lists the candidates; nothing is written silently
        to the wrong field.
        """
        if not (selector or label or name or placeholder):
            raise BrowseError(
                "Alan belirt: `selector`, `label`, `name` ya da `placeholder` gerekli. "
                "`read` ile formdaki alanlara bak."
            )
        spec = json.dumps({
            "selector": selector, "label": label,
            "name": name, "placeholder": placeholder,
        })
        return _outcome(self.eval(tab, _FILL_JS % (spec, json.dumps(text))),
                        "Alan doldurulamadı.")

    def submit(self, tab: dict[str, Any], selector: str = "") -> str:
        """Submits the form.

        With a selector, that form or button; without one, the focused
        field's form, failing that the only form on the page. If there is a
        submit button it is clicked (so the page's own flow runs); otherwise
        `requestSubmit` — that fires the `submit` event too, bare
        `form.submit()` would not.
        """
        return _outcome(self.eval(tab, _SUBMIT_JS % json.dumps(selector)),
                        "Form gönderilemedi.")


def _outcome(answer: Any, fallback: str) -> str:
    """The common contract of the page helpers: {ok} or {err, adaylar}."""
    if not isinstance(answer, dict):
        raise BrowseError(fallback + " (Sayfa beklenmedik bir cevap verdi.)")
    if answer.get("err"):
        message = str(answer["err"])
        candidates = answer.get("adaylar") or []
        if candidates:
            message += " Adaylar: " + "; ".join(str(c) for c in candidates)
        raise BrowseError(message)
    return str(answer.get("ok") or "tamam")


# -- helpers that run inside the page -----------------------------------
#
# Clicking and field selection are resolved in the page's own DOM:
# computing coordinates is fragile (scroll, scale, hidden layer) and the
# model thinks in text anyway — "the Giriş button", "the e-mail field".
# Matching is exact first, then containing; invisible candidates are
# skipped.

_CLICK_JS = """(() => {
  const want = %s.trim().toLowerCase();
  const seen = (el) => {
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  };
  const nodes = [...document.querySelectorAll(
    "a,button,[role=button],input[type=submit],input[type=button],[onclick]")];
  const label = (el) => (
    el.innerText || el.value || el.getAttribute("aria-label") || el.title || ""
  ).trim().toLowerCase();
  let hit = nodes.find((el) => seen(el) && label(el) === want)
         || nodes.find((el) => seen(el) && label(el).includes(want));
  if (!hit) return "";
  hit.click();
  return (hit.innerText || hit.value || hit.getAttribute("aria-label") || "tıklandı").trim().slice(0, 80);
})()"""

_FOCUS_JS = """(() => {
  const want = %s.trim().toLowerCase();
  const seen = (el) => {
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0 && !el.disabled && !el.readOnly;
  };
  const fields = [...document.querySelectorAll(
    "input:not([type=hidden]):not([type=submit]):not([type=button]),textarea,[contenteditable=true]")]
    .filter(seen);
  if (!fields.length) return "";
  let pick;
  if (want) {
    const near = (el) => {
      let t = (el.getAttribute("aria-label") || el.placeholder || el.name || el.id || "").toLowerCase();
      if (el.labels && el.labels.length) t += " " + el.labels[0].innerText.toLowerCase();
      return t;
    };
    pick = fields.find((el) => near(el).includes(want));
    if (!pick) return "";
  } else {
    pick = (document.activeElement && fields.includes(document.activeElement))
      ? document.activeElement
      : fields.find((el) => !el.value) || fields[0];
  }
  pick.focus();
  return (pick.getAttribute("aria-label") || pick.placeholder || pick.name || pick.id || "alan").slice(0, 80);
})()"""

# Field lookup + filling also lives in the page. Contract: returns
# {ok: "..."} or {err: "...", adaylar: [...]} — the Python side unpacks it
# with `_outcome`. The value is written with the native setter (to get past
# React's own value tracking) and then with input+change events: that is
# the path frameworks listen to. Forms inside iframes cannot be reached from
# here; the error message says so.

_FILL_JS = """(() => { // dornick:fill
  const spec = %s;
  const text = %s;
  const desc = (el) => {
    const parts = [];
    if (el.labels && el.labels.length && el.labels[0].innerText.trim())
      parts.push(el.labels[0].innerText.trim());
    if (el.name) parts.push("name=" + el.name);
    if (el.placeholder) parts.push("placeholder=" + el.placeholder);
    if (!parts.length && el.id) parts.push("#" + el.id);
    if (!parts.length) parts.push(el.tagName.toLowerCase());
    return parts.join(" / ").slice(0, 80);
  };
  const seen = (el) => {
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0 && !el.disabled && !el.readOnly;
  };
  const iframeNote = document.querySelector("iframe")
    ? " Sayfada iframe var; iframe içindeki formlar bu sürümde kapsam dışı." : "";
  let hits;
  if (spec.selector) {
    let found;
    try { found = [...document.querySelectorAll(spec.selector)]; }
    catch (e) { return {err: "Geçersiz CSS seçici: " + spec.selector}; }
    if (!found.length)
      return {err: "'" + spec.selector + "' hiçbir öğeyle eşleşmedi." + iframeNote};
    hits = found.filter((el) =>
      el.matches("input,textarea,select,[contenteditable=true],[contenteditable='']"));
    if (!hits.length)
      return {err: "'" + spec.selector + "' eşleşti ama doldurulabilir bir alan değil."};
  } else {
    const all = [...document.querySelectorAll(
      "input:not([type=hidden]):not([type=submit]):not([type=button]),textarea,select,[contenteditable=true]")]
      .filter(seen);
    let fields = all;
    const narrow = (want, get) => {
      const w = want.trim().toLowerCase();
      const exact = fields.filter((el) => get(el).trim().toLowerCase() === w);
      fields = exact.length
        ? exact
        : fields.filter((el) => get(el).toLowerCase().includes(w));
    };
    if (spec.label) narrow(spec.label, (el) => {
      let t = el.getAttribute("aria-label") || "";
      if (el.labels && el.labels.length) t = el.labels[0].innerText + " " + t;
      return t;
    });
    if (spec.name) narrow(spec.name, (el) => el.name || "");
    if (spec.placeholder) narrow(spec.placeholder, (el) => el.placeholder || "");
    if (!fields.length)
      return {err: "Eşleşen alan bulunamadı." + iframeNote,
              adaylar: all.map(desc).slice(0, 8)};
    hits = fields;
  }
  if (hits.length > 1)
    return {err: "Birden çok alan eşleşti; hedefi daralt.",
            adaylar: hits.map(desc).slice(0, 8)};
  const el = hits[0];
  if (!seen(el))
    return {err: "Alan bulundu ama görünür/etkin değil: " + desc(el)};
  el.focus();
  if (el.tagName === "SELECT") {
    const opt = [...el.options].find((o) => o.value === text || o.text.trim() === text);
    if (!opt) return {err: "Seçenek bulunamadı: " + text,
                      adaylar: [...el.options].map((o) => o.text.trim()).slice(0, 12)};
    el.value = opt.value;
    el.dispatchEvent(new Event("input", {bubbles: true}));
    el.dispatchEvent(new Event("change", {bubbles: true}));
  } else if (el.isContentEditable) {
    el.textContent = text;
    el.dispatchEvent(new Event("input", {bubbles: true}));
  } else {
    const proto = el.tagName === "TEXTAREA"
      ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    const setter = (Object.getOwnPropertyDescriptor(proto, "value") || {}).set;
    if (setter) setter.call(el, text); else el.value = text;
    el.dispatchEvent(new Event("input", {bubbles: true}));
    el.dispatchEvent(new Event("change", {bubbles: true}));
  }
  return {ok: desc(el)};
})()"""

_SUBMIT_JS = """(() => { // dornick:submit
  const sel = %s;
  const desc = (f) => {
    const parts = [];
    if (f.id) parts.push("#" + f.id);
    if (f.getAttribute("name")) parts.push("name=" + f.getAttribute("name"));
    if (f.getAttribute("action")) parts.push("→ " + f.getAttribute("action"));
    return parts.join(" ") || "form";
  };
  const fire = (form) => {
    const btn = form.querySelector(
      "button[type=submit],input[type=submit],button:not([type])");
    if (btn) {
      btn.click();
      return ((btn.innerText || btn.value || "").trim() || "düğme").slice(0, 60);
    }
    if (form.requestSubmit) form.requestSubmit(); else form.submit();
    return desc(form);
  };
  const iframeNote = document.querySelector("iframe")
    ? " Sayfada iframe var; iframe içindeki formlar bu sürümde kapsam dışı." : "";
  if (sel) {
    let el;
    try { el = document.querySelector(sel); }
    catch (e) { return {err: "Geçersiz CSS seçici: " + sel}; }
    if (!el) return {err: "'" + sel + "' bulunamadı." + iframeNote};
    if (el.tagName === "FORM") return {ok: fire(el)};
    if (el.matches("button,input[type=submit],input[type=button],[role=button]")) {
      el.click();
      return {ok: ((el.innerText || el.value || "").trim() || "düğme").slice(0, 60)};
    }
    if (el.form) return {ok: fire(el.form)};
    return {err: "'" + sel + "' bir form ya da düğme değil."};
  }
  const active = document.activeElement;
  let form = active && active.form ? active.form : null;
  if (!form) {
    const forms = [...document.forms];
    if (!forms.length) return {err: "Sayfada form yok." + iframeNote};
    if (forms.length > 1)
      return {err: "Birden çok form var; `selector` ile birini seç.",
              adaylar: forms.map(desc).slice(0, 8)};
    form = forms[0];
  }
  return {ok: fire(form)};
})()"""

# Wrapper for the diagnostic expression. `eval` is deliberate: the model
# sometimes sends not a single expression but a two-line probe, and plain
# `Runtime.evaluate` counted that as a syntax error. If the result cannot
# be turned into JSON it falls back to text — DOM nodes and functions do
# not serialise.
_JS_WRAP = """(function () { // dornick:js
  let r;
  try { r = eval(%s); }
  catch (e) { return {hata: String((e && (e.stack || e.message)) || e)}; }
  const t = (r === null) ? "null" : typeof r;
  try { return {tip: t, deger: JSON.parse(JSON.stringify(r === undefined ? null : r))}; }
  catch (e) { return {tip: t, deger: String(r).slice(0, 2000)}; }
})()"""

# Signatures of framework error pages. Every item is a marker really found
# on the page that framework produces; a generic "does 'error' appear on the
# page" scan is deliberately ABSENT — it would declare an ordinary blog post
# an error page.
_ERROR_JS = """(() => { // dornick:hata
  const kes = (s, n) => (s || "").trim().replace(/\\s+/g, " ").slice(0, n || 300);
  const q = (s) => document.querySelector(s);
  const baslik = document.title || "";

  // CodeIgniter 4 — "Whoops!" heading, .header h1 carries the exception class.
  if (q(".container.text-center h1") && /whoops/i.test(document.body.innerText.slice(0, 400))) {
    const h = q("h1"), p = q(".header p") || q("p");
    return {tur: "CodeIgniter 4 hata sayfası", baslik: kes(h && h.innerText, 200),
            mesaj: kes(p && p.innerText, 300),
            yer: kes((q(".source") || {}).innerText, 200)};
  }
  if (/whoops/i.test(baslik) || q("#exception-card") || q(".exception__message")) {
    const h = q(".exception__title, .exception-message, h1");
    return {tur: "PHP çerçeve hata sayfası (Whoops/Ignition)",
            baslik: kes(h && h.innerText, 200), mesaj: kes(baslik, 200), yer: ""};
  }
  // Django debug page: "TypeError at /path"
  if (q("#summary") && q("#traceback") && / at \\//.test(baslik)) {
    const h = q("#summary h1"), p = q("#summary pre.exception_value");
    return {tur: "Django hata sayfası", baslik: kes(h && h.innerText, 200),
            mesaj: kes(p && p.innerText, 300), yer: ""};
  }
  // Flask/Werkzeug debugger
  if (/werkzeug debugger/i.test(baslik) || q(".traceback .frame")) {
    const h = q("h1"), p = q(".errormsg") || q(".detail .errormsg");
    return {tur: "Werkzeug (Flask) hata ayıklayıcı", baslik: kes(h && h.innerText, 200),
            mesaj: kes(p && p.innerText, 300), yer: ""};
  }
  // Bare PHP: "Fatal error:" / "Parse error:" / "Warning:" at the head of the body
  const bas = (document.body ? document.body.innerText : "").slice(0, 500);
  const m = bas.match(/(Fatal error|Parse error|Warning|Notice|Deprecated):\\s*([^\\n]+)/);
  if (m) return {tur: "PHP " + m[1], baslik: kes(m[1], 60), mesaj: kes(m[2], 300),
                 yer: kes((bas.match(/ in (.+ on line \\d+)/) || [])[1], 200)};
  // Node/Express default error page
  if (q("pre") && /^\\s*(Error|TypeError|ReferenceError):/.test(q("pre").innerText || ""))
    return {tur: "Node/Express hata sayfası", baslik: kes(q("pre").innerText.split("\\n")[0], 200),
            mesaj: "", yer: ""};
  return null;
})()"""

# CDP key definitions for the special keys.
_KEYS = {
    "enter": {"key": "Enter", "code": "Enter", "windowsVirtualKeyCode": 13},
    "tab": {"key": "Tab", "code": "Tab", "windowsVirtualKeyCode": 9},
    "escape": {"key": "Escape", "code": "Escape", "windowsVirtualKeyCode": 27},
    "esc": {"key": "Escape", "code": "Escape", "windowsVirtualKeyCode": 27},
    "backspace": {"key": "Backspace", "code": "Backspace", "windowsVirtualKeyCode": 8},
}
