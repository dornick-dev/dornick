"""neo chrome — tarayıcıyı DevTools protokolüyle sürmek.

Claude'un Chrome eklentisinin yerlisi: neo, Chrome ya da Edge'i hata
ayıklama kapısıyla (`--remote-debugging-port`) başlatıyor ve DevTools
protokolü (CDP) üzerinden konuşuyor — sekmeleri görüyor, sayfa açıyor,
metni okuyor, ekran görüntüsü alıyor.

Tarayıcı **neo'nun kendi profiliyle** açılıyor (`.neocp/chrome/`):
kullanıcının gündelik Chrome'una bağlanmak mümkün değil çünkü o kapı
kapalı açılıyor. Ayrı profil aynı zamanda bir sınır — kullanıcı hangi
sitelere giriş verdiyse neo yalnızca onları görüyor ve o oturumlar
profil klasöründe kalıcı: bir kez giriş yapılan siteye ertesi gün de
girilebiliyor.

CDP'nin iki yüzü var:
    http  sekme listesi, sekme açma/kapama — düz JSON uçları
    ws    sayfanın içi (JavaScript çalıştırma, ekran görüntüsü)

stdlib'de WebSocket istemcisi yok; buradaki `Wire` gereken kadarını
yapıyor: tek bağlantı, maskeli metin çerçeveleri, parçalı mesaj ve
ping/pong. Bir kütüphane bağımlılığına değmeyecek kadar küçük bir iş.
"""

from __future__ import annotations

import base64
import json
import os
import socket
import struct
import subprocess
import time
from pathlib import Path
from typing import Any

DEFAULT_PORT = 9222

# Tarayıcının kapıyı açması ilk kurulumda yavaş olabiliyor.
BOOT_WAIT_S = 20.0

# Tek bir CDP cevabı için bekleme. Ekran görüntüsü büyük bir sayfada
# birkaç saniye sürebiliyor.
CALL_TIMEOUT_S = 30.0


class BrowseError(RuntimeError):
    """Tarayıcı hatası — mesaj modele gidiyor, öğretici olmalı."""


def executable() -> str | None:
    """Kurulu Chrome/Edge. PATH'te yoksa bilinen konumlara bakılıyor."""
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


# Süreç-geneli tek tarayıcı. Ana ajan ve alt ajanlar ayrı araç defterleri
# taşıyor; her biri kendi Browser'ını kursaydı aynı anda aynı kapıyı açmaya
# çalışıp yarışırlardı. Tek örnek: hepsi aynı Chrome'u sürüyor, aynı
# sekmeleri görüyor.
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


# -- WebSocket teli -----------------------------------------------------


class Wire:
    """RFC 6455'in CDP için gereken kadarı — istemci tarafı.

    İstemci çerçeveleri maskeli gitmek zorunda; sunucununkiler çıplak
    geliyor. Uzunluk 7 bite sığmazsa 16 ya da 64 bitlik ek alan var —
    ekran görüntüsü 64 bitlik yolu gerçekten kullanıyor.
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
        head = bytearray([0x81])  # FIN + metin
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
        """Bir mesaj — parçalıysa birleştirilmiş hali."""
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
            # Sunucu maskelemez; maskeliyse yine de okunur.
            mask = self._exactly(4) if second & 0x80 else b""
            body = self._exactly(size) if size else b""
            if mask:
                body = bytes(b ^ mask[i % 4] for i, b in enumerate(body))

            if opcode == 0x9:  # ping → pong, aynı gövdeyle
                pong = bytearray([0x8A, 0x80 | len(body)])
                veil = os.urandom(4)
                pong += veil + bytes(b ^ veil[i % 4] for i, b in enumerate(body))
                self.sock.sendall(bytes(pong))
                continue
            if opcode == 0x8:
                raise BrowseError("Tarayıcı bağlantıyı kapattı.")
            if opcode == 0xA:  # pong — istemedik ama zararsız
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


# -- tarayıcı -----------------------------------------------------------


class Browser:
    """Hata ayıklama kapısı açık bir Chrome/Edge ve onun sekmeleri."""

    def __init__(self, state_dir: Path | str, port: int = DEFAULT_PORT) -> None:
        import threading

        self.state_dir = Path(state_dir)
        self.port = port
        self._proc: subprocess.Popen[bytes] | None = None
        # Paylaşılan örnekte iki alt ajan aynı anda başlatmaya kalkabilir;
        # başlatma tek seferde olsun.
        self._boot_lock = threading.Lock()

    # -- http yüzü -----------------------------------------------------

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
        """Tarayıcı ayaktaysa dokunmaz; değilse kendi profiliyle başlatır."""
        if self.alive():
            return
        with self._boot_lock:
            # Kilidi beklerken başkası başlatmış olabilir.
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
        from urllib.parse import quote

        spot = "/json/new?" + quote(url, safe=":/?&=%")
        try:
            # Yeni Chrome PUT istiyor; eskisi GET kabul ediyordu.
            made = self._http(spot, method="PUT")
        except Exception:
            made = self._http(spot)
        if not isinstance(made, dict) or not made.get("id"):
            raise BrowseError("Sekme açılamadı.")
        return made

    def close_tab(self, tab_id: str) -> None:
        try:
            self._http(f"/json/close/{tab_id}")
        except Exception:
            pass

    # -- sayfanın içi (ws) ---------------------------------------------

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
                    continue  # olay bildirimi; bizim cevabımız değil
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
        """Sayfanın görünen metni. Yüklenmesini kısa bir süre bekliyor.

        Yalnızca `readyState` yetmiyor: yeni açılan sekme bir an
        `about:blank` oluyor ve o sayfa anında "complete" — gezinme daha
        başlamadan boş sayfa okunuyordu. Adres de yerine oturmalı.
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
        }

    def screenshot(self, tab: dict[str, Any]) -> str:
        """Görünen alanın görüntüsü, data: adresi olarak."""
        answer = self._call(tab, "Page.captureScreenshot", {
            "format": "jpeg",
            "quality": 72,
        })
        data = str(answer.get("data") or "")
        if not data:
            raise BrowseError("Görüntü alınamadı.")
        return "data:image/jpeg;base64," + data

    # -- faz 2: sayfayla etkileşim -------------------------------------

    def navigate(self, tab: dict[str, Any], url: str) -> dict[str, Any]:
        """Aynı sekmede başka adrese gider ve yeni sayfayı okur."""
        self._call(tab, "Page.navigate", {"url": url})
        return self.read(tab)

    def click(self, tab: dict[str, Any], text: str) -> str:
        """Metnine göre bir düğme ya da bağlantıya tıklar.

        Piksel değil metin: model "Giriş" düğmesini görüyor, koordinatını
        değil. Sayfadaki tıklanabilirler (buton, bağlantı, role=button,
        input) taranıyor ve metni en iyi eşleşen tıklanıyor. Görünmeyen
        eşleşme atlanıyor — gizli bir bağlantıya tıklamak işe yaramaz.
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
        """Bir alana metin yazar.

        `into` verilirse etiketine/placeholder'ına göre alan seçilir; boşsa
        o an odakta olan (ya da ilk boş metin) alan kullanılıyor. Yazma DOM'a
        doğrudan değil, gerçek tuş olaylarıyla: bazı sayfalar `input`
        olayını dinliyor ve doğrudan değer atamayı görmüyor.
        """
        focused = self.eval(tab, _FOCUS_JS % json.dumps(into))
        if not focused:
            raise BrowseError(
                (f"'{into}' alanı bulunamadı." if into else "Yazılacak bir alan bulunamadı.")
                + " `read` ile forma bak."
            )
        # Odaklı alana karakterleri gerçek tuş olayı olarak gönder.
        for ch in text:
            self._call(tab, "Input.dispatchKeyEvent", {"type": "keyDown", "text": ch})
            self._call(tab, "Input.dispatchKeyEvent", {"type": "keyUp", "text": ch})
        return str(focused)

    def press(self, tab: dict[str, Any], key: str) -> None:
        """Tek bir özel tuş: Enter, Tab, Escape…"""
        spec = _KEYS.get(key.lower())
        if spec is None:
            raise BrowseError(f"Bilinmeyen tuş: {key}. (Enter, Tab, Escape…)")
        for phase in ("keyDown", "keyUp"):
            self._call(tab, "Input.dispatchKeyEvent", {"type": phase, **spec})


# -- sayfa içinde çalışan yardımcılar -----------------------------------
#
# Tıklama ve alan seçimi sayfanın kendi DOM'unda çözülüyor: koordinat
# hesaplamak kırılgan (kaydırma, ölçek, gizli katman) ve model zaten metin
# düşünüyor — "Giriş düğmesi", "e-posta alanı". Eşleşme önce birebir, sonra
# içeren; görünmeyen aday atlanıyor.

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

# Özel tuşlar için CDP anahtar tanımları.
_KEYS = {
    "enter": {"key": "Enter", "code": "Enter", "windowsVirtualKeyCode": 13},
    "tab": {"key": "Tab", "code": "Tab", "windowsVirtualKeyCode": 9},
    "escape": {"key": "Escape", "code": "Escape", "windowsVirtualKeyCode": 27},
    "esc": {"key": "Escape", "code": "Escape", "windowsVirtualKeyCode": 27},
    "backspace": {"key": "Backspace", "code": "Backspace", "windowsVirtualKeyCode": 8},
}
