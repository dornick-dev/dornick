"""Hand and screen — the agent using the computer itself.

`shell` runs commands but does not see what happens on screen; `fetch`
reads pages but cannot drive an open browser session. The two tools here
close that gap:

    screen   looks: screenshot, open windows                 (read)
    hand     touches: mouse, keyboard, window, application   (mutation)

They are split in two because of the permission gate: looking is
harmless, touching is not. As a single tool either every screenshot
would need approval, or no click would ever ask.

The coordinate contract: `screen` delivers the image scaled down and
stores the last frame's geometry; `hand` takes the click in **that
image's** pixels and converts to the real screen itself. The model
clicks wherever it is looking in the picture it saw — the scale math is
not left to it, because when it was, it got it wrong, and a wrong click
cannot be undone.

Single dependency: Pillow for screen capture. Mouse and keyboard go
straight to user32 via `ctypes` — no extra package.
"""

from __future__ import annotations

import asyncio
import base64
import importlib.util
import io
import sys
import time
from typing import Any

from .base import ToolContext, ToolRegistry, ToolResult, object_schema

# The long edge of the image sent. Above this is token waste: the model
# already sees anything bigger than 1568 downscaled.
MAX_EDGE = 1400

JPEG_QUALITY = 72

# The geometry of the last screenshot: (left, top) corner, scale, size.
# `hand` converts an image pixel to the real screen with this.
_frame: dict[str, Any] | None = None

_dpi_set = False


def available() -> bool:
    """Only on Windows with Pillow installed. Otherwise the tools are never
    registered — the model must not try an ability that does not exist, and
    the organ shows as 'absent' on the scene."""
    if sys.platform != "win32":
        return False
    try:
        return importlib.util.find_spec("PIL") is not None
    except Exception:
        return False


def _dpi_aware() -> None:
    """Makes the process DPI-aware — once.

    Without it, on scaled displays (125%, 150%) the captured image and
    the real coordinates drift, and every click lands to the left of the
    target.
    """
    global _dpi_set
    if _dpi_set:
        return
    import ctypes

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass
    _dpi_set = True


def _monitors() -> list[tuple[int, int, int, int]]:
    """The monitors' rectangles on the virtual desktop (left, top, right, bottom).

    If the second monitor is on the left or above, coordinates can be
    negative; so 0,0 cannot be assumed, it really has to be asked.
    """
    import ctypes
    from ctypes import wintypes

    rects: list[tuple[int, int, int, int]] = []
    proc = ctypes.WINFUNCTYPE(
        ctypes.c_int, wintypes.HMONITOR, wintypes.HDC,
        ctypes.POINTER(wintypes.RECT), wintypes.LPARAM,
    )

    def keep(_h: Any, _dc: Any, rect: Any, _lp: Any) -> int:
        r = rect.contents
        rects.append((r.left, r.top, r.right, r.bottom))
        return 1

    ctypes.windll.user32.EnumDisplayMonitors(0, 0, proc(keep), 0)
    if not rects:
        user32 = ctypes.windll.user32
        rects.append((0, 0, user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)))

    # Primary monitor first. EnumDisplayMonitors guarantees no order, and
    # in a real run the right-hand monitor came at index 0: `screen look`
    # captured the wrong monitor, not the primary one the user was looking
    # at. The primary monitor's top-left is always (0,0) on the virtual
    # desktop.
    rects.sort(key=lambda r: (r[0] != 0 or r[1] != 0, r[0], r[1]))
    return rects


def to_screen(x: float, y: float, frame: dict[str, Any]) -> tuple[int, int]:
    """Converts an image pixel to a real screen coordinate. Pure — testable."""
    ox, oy = frame["origin"]
    scale = frame["scale"] or 1.0
    return int(ox + round(x / scale)), int(oy + round(y / scale))


# ---------------------------------------------------------------- screen


def _grab(display: int) -> tuple[str, str]:
    """Captures one monitor. Returns (content text, data-url)."""
    from PIL import Image, ImageGrab

    global _frame
    _dpi_aware()

    rects = _monitors()
    display = max(0, min(display, len(rects) - 1))
    left, top, right, bottom = rects[display]
    image = ImageGrab.grab(bbox=(left, top, right, bottom), all_screens=True)

    width, height = image.size
    scale = min(1.0, MAX_EDGE / max(width, height))
    if scale < 1.0:
        image = image.resize(
            (round(width * scale), round(height * scale)), Image.LANCZOS
        )

    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="JPEG", quality=JPEG_QUALITY)
    payload = base64.b64encode(buffer.getvalue()).decode("ascii")

    _frame = {
        "origin": (left, top),
        "scale": scale,
        "size": image.size,
        "display": display,
    }

    text = (
        f"Ekran {display} görüntüsü aşağıda ({image.size[0]}×{image.size[1]}"
        + (f", gerçek {width}×{height}" if scale < 1.0 else "")
        + f"){' — toplam ' + str(len(rects)) + ' ekran var' if len(rects) > 1 else ''}. "
        "Tıklamak için koordinatı BU görüntünün pikselleriyle ver "
        "(`hand action=click x=... y=...`); gerçek ekrana çeviri bende."
    )
    return text, f"data:image/jpeg;base64,{payload}"


def _windows() -> list[tuple[str, bool]]:
    """Visible top-level windows: (title, is it in front)."""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    front = user32.GetForegroundWindow()
    found: list[tuple[str, bool]] = []
    proc = ctypes.WINFUNCTYPE(ctypes.c_int, wintypes.HWND, wintypes.LPARAM)

    def keep(hwnd: Any, _lp: Any) -> int:
        if not user32.IsWindowVisible(hwnd):
            return 1
        length = user32.GetWindowTextLengthW(hwnd)
        if not length:
            return 1
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        found.append((buffer.value, hwnd == front))
        return 1

    user32.EnumWindows(proc(keep), 0)
    return found


SCREEN_DESCRIPTION = """
Bilgisayarın ekranına bakar. Kendi gözünle: kullanıcı bir şey göndermiyor,
sen bakıyorsun.

  look     ekran görüntüsü al ve gör (`display` ile ekran seç, 0 = birincil)
  windows  açık pencerelerin listesi — görüntü almadan, ucuz

Birden fazla monitör varsa `display` 0 birincil ekran; aradığın pencere
görünmüyorsa öteki ekranı dene (`display=1`). Yakaladığın görüntüde pencere
yoksa muhtemelen başka monitördedir.

"Ekranda ne var", "şu pencerede ne yazıyor", bir uygulamayı sürerken her
adımın sonucunu görmek: önce `windows` ile ucuzca yokla, gerekiyorsa `look`.
Bir görüntü bağlamda 1.5-4k token — her adımda değil, karar gerektiren
adımda bak.
"""


HAND_DESCRIPTION = """
Fareyi ve klavyeyi kullanır — kullanıcının yaptığı her şeyi yapabilirsin:
uygulama açmak, tıklamak, yazmak, tarayıcıda gezinmek.

  click / double / right   tıkla (x, y: son `screen look` görüntüsünün pikseli)
  move                     imleci taşı
  drag                     x,y'den x2,y2'ye sürükle
  scroll                   kaydır (amount: pozitif yukarı, negatif aşağı)
  type                     metin yaz (text) — odaklı alana, Türkçe dahil
  key                      kısayol bas (keys: "enter", "ctrl+c", "alt+tab", "win+r")
  focus                    başlığı eşleşen pencereyi öne getir (target)
  open                     uygulama, dosya ya da adres aç (target)

Çalışma düzeni: `screen look` ile bak → hedefi görüntüde bul → `hand` ile
dokun → tekrar `screen look` ile sonucu doğrula. Bakmadan tıklama: ekran
senin sandığın halde olmayabilir ve yanlış tıklama geri alınamaz.
Yazmadan önce doğru alanın odaklı olduğundan emin ol (gerekirse önce tıkla).
"""


def register(registry: ToolRegistry) -> None:
    @registry.tool(
        name="screen",
        description=SCREEN_DESCRIPTION,
        input_schema=object_schema(
            {
                "action": {
                    "type": "string",
                    "enum": ["look", "windows"],
                    "description": "look: ekran görüntüsü. windows: pencere listesi.",
                },
                "display": {
                    "type": "integer",
                    "description": "Bakılacak ekran (0'dan başlar, varsayılan 0).",
                },
            },
            required=["action"],
        ),
    )
    async def screen(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        action = str(args.get("action") or "look")

        if action == "windows":
            rows = await asyncio.to_thread(_windows)
            if not rows:
                return ToolResult("Görünür pencere yok.")
            lines = [f"{len(rows)} pencere:"]
            for title, front in rows:
                lines.append(f"- {title}" + (" ← önde" if front else ""))
            return ToolResult("\n".join(lines))

        if action == "look":
            display = int(args.get("display") or 0)
            try:
                text, image = await asyncio.to_thread(_grab, display)
            except Exception as exc:
                return ToolResult.error(f"Ekran görüntüsü alınamadı: {exc}")
            return ToolResult(text, detail={"image": image, "display": display})

        return ToolResult.error("`action` look ya da windows olmalı.")

    @registry.tool(
        name="hand",
        description=HAND_DESCRIPTION,
        input_schema=object_schema(
            {
                "action": {
                    "type": "string",
                    "enum": [
                        "click", "double", "right", "move", "drag",
                        "scroll", "type", "key", "focus", "open",
                    ],
                    "description": "Yapılacak hareket.",
                },
                "x": {"type": "integer", "description": "Görüntü pikseli (son screen look)."},
                "y": {"type": "integer", "description": "Görüntü pikseli (son screen look)."},
                "x2": {"type": "integer", "description": "drag için varış noktası."},
                "y2": {"type": "integer", "description": "drag için varış noktası."},
                "amount": {
                    "type": "integer",
                    "description": "scroll adımı: pozitif yukarı, negatif aşağı (varsayılan -3).",
                },
                "text": {"type": "string", "description": "type için yazılacak metin."},
                "keys": {
                    "type": "string",
                    "description": 'key için kısayol: "enter", "ctrl+c", "alt+tab".',
                },
                "target": {
                    "type": "string",
                    "description": "focus: pencere başlığı (parça yeter). open: uygulama/dosya/adres.",
                },
            },
            required=["action"],
        ),
        mutates=True,
        parallel_safe=False,
    )
    async def hand(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        action = str(args.get("action") or "")
        try:
            return await asyncio.to_thread(_hand_action, action, args)
        except Exception as exc:
            return ToolResult.error(f"{type(exc).__name__}: {exc}")


# ---------------------------------------------------------------- hand


def _hand_action(action: str, args: dict[str, Any]) -> ToolResult:
    _dpi_aware()

    if action == "open":
        return _open(str(args.get("target") or ""))
    if action == "focus":
        return _focus(str(args.get("target") or ""))
    if action == "type":
        return _type(str(args.get("text") or ""))
    if action == "key":
        return _press(str(args.get("keys") or ""))

    if action in ("click", "double", "right", "move", "drag", "scroll"):
        return _pointer(action, args)

    return ToolResult.error(
        "`action` şunlardan biri olmalı: click, double, right, move, drag, "
        "scroll, type, key, focus, open."
    )


def _pointer(action: str, args: dict[str, Any]) -> ToolResult:
    import ctypes

    user32 = ctypes.windll.user32

    if action == "scroll" and args.get("x") is None:
        # Scrolling without coordinates applies where the cursor is.
        amount = int(args.get("amount") or -3)
        user32.mouse_event(0x0800, 0, 0, amount * 120, 0)  # MOUSEEVENTF_WHEEL
        return ToolResult(
            f"Kaydırıldı ({amount:+d}). Sonucu görmek için `screen action=look`."
        )

    if _frame is None:
        return ToolResult.error(
            "Elinde güncel bir ekran görüntüsü yok. Önce `screen action=look` "
            "ile bak — koordinatlar o görüntünün pikselleriyle veriliyor."
        )
    if args.get("x") is None or args.get("y") is None:
        return ToolResult.error("`x` ve `y` gerekli — son görüntünün pikselleriyle.")

    sx, sy = to_screen(int(args["x"]), int(args["y"]), _frame)
    user32.SetCursorPos(sx, sy)
    time.sleep(0.03)

    if action == "move":
        return ToolResult(f"İmleç taşındı ({sx}, {sy}).")

    if action == "scroll":
        amount = int(args.get("amount") or -3)
        user32.mouse_event(0x0800, 0, 0, amount * 120, 0)
        return ToolResult(
            f"({sx}, {sy}) üzerinde kaydırıldı ({amount:+d}). "
            "Sonucu görmek için `screen action=look`."
        )

    if action == "drag":
        if args.get("x2") is None or args.get("y2") is None:
            return ToolResult.error("drag için `x2` ve `y2` de gerekli.")
        ex, ey = to_screen(int(args["x2"]), int(args["y2"]), _frame)
        user32.mouse_event(0x0002, 0, 0, 0, 0)  # LEFTDOWN
        # Dropping in a single jump does not start a drag in most apps;
        # the intermediate steps mimic a real hand movement.
        steps = 12
        for i in range(1, steps + 1):
            user32.SetCursorPos(sx + (ex - sx) * i // steps, sy + (ey - sy) * i // steps)
            time.sleep(0.015)
        user32.mouse_event(0x0004, 0, 0, 0, 0)  # LEFTUP
        return ToolResult(f"Sürüklendi: ({sx}, {sy}) → ({ex}, {ey}).")

    down, up = (0x0008, 0x0010) if action == "right" else (0x0002, 0x0004)
    user32.mouse_event(down, 0, 0, 0, 0)
    user32.mouse_event(up, 0, 0, 0, 0)
    if action == "double":
        time.sleep(0.05)
        user32.mouse_event(down, 0, 0, 0, 0)
        user32.mouse_event(up, 0, 0, 0, 0)

    name = {"click": "Tıklandı", "double": "Çift tıklandı", "right": "Sağ tıklandı"}[action]
    return ToolResult(
        f"{name} ({sx}, {sy}). Ekran değişmiş olabilir — emin değilsen "
        "`screen action=look` ile doğrula."
    )


# Keys resolved by name in shortcuts. Single letters come from VkKeyScanW —
# it gives the right virtual key for the keyboard layout (Turkish Q/F).
VK = {
    "ctrl": 0x11, "control": 0x11, "alt": 0x12, "shift": 0x10,
    "win": 0x5B, "meta": 0x5B, "enter": 0x0D, "return": 0x0D,
    "tab": 0x09, "esc": 0x1B, "escape": 0x1B, "space": 0x20,
    "backspace": 0x08, "delete": 0x2E, "del": 0x2E, "insert": 0x2D,
    "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22,
    "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
    **{f"f{i}": 0x6F + i for i in range(1, 13)},
}


def parse_keys(combo: str) -> list[int]:
    """"ctrl+shift+t" -> list of virtual keys, in press order. Pure — testable."""
    out: list[int] = []
    for token in (t.strip().lower() for t in combo.split("+")):
        if not token:
            continue
        if token in VK:
            out.append(VK[token])
        elif len(token) == 1:
            out.append(_vk_of_char(token))
        else:
            raise ValueError(f"Bilinmeyen tuş: {token!r}")
    return out


def _vk_of_char(char: str) -> int:
    if sys.platform == "win32":
        import ctypes

        code = ctypes.windll.user32.VkKeyScanW(ord(char))
        if code != -1:
            return code & 0xFF
    return ord(char.upper())


def _press(combo: str) -> ToolResult:
    import ctypes

    if not combo.strip():
        return ToolResult.error('`keys` gerekli — örn. "enter", "ctrl+c".')
    try:
        keys = parse_keys(combo)
    except ValueError as exc:
        return ToolResult.error(str(exc))

    user32 = ctypes.windll.user32
    for vk in keys:
        user32.keybd_event(vk, 0, 0, 0)
        time.sleep(0.02)
    for vk in reversed(keys):
        user32.keybd_event(vk, 0, 2, 0)  # KEYEVENTF_KEYUP
        time.sleep(0.02)
    return ToolResult(f"Basıldı: {combo}.")


def _type(text: str) -> ToolResult:
    """Types the text into the focused field.

    Via KEYEVENTF_UNICODE: independent of keyboard layout, everything
    including Turkish characters goes as UTF-16 units. A newline is
    pressed as a real Enter — most fields ignore U+000A.
    """
    import ctypes

    if not text:
        return ToolResult.error("`text` gerekli.")

    user32 = ctypes.windll.user32

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", ctypes.c_ushort), ("wScan", ctypes.c_ushort),
            ("dwFlags", ctypes.c_ulong), ("time", ctypes.c_ulong),
            ("dwExtraInfo", ctypes.c_size_t),
        ]

    class INPUT(ctypes.Structure):
        _fields_ = [("type", ctypes.c_ulong), ("ki", KEYBDINPUT),
                    ("pad", ctypes.c_ubyte * 8)]

    def send(scan: int, flags: int) -> None:
        item = INPUT(type=1, ki=KEYBDINPUT(0, scan, flags, 0, 0))
        user32.SendInput(1, ctypes.byref(item), ctypes.sizeof(INPUT))

    for char in text:
        if char in ("\n", "\r"):
            user32.keybd_event(0x0D, 0, 0, 0)
            user32.keybd_event(0x0D, 0, 2, 0)
            time.sleep(0.02)
            continue
        for scan in _utf16_units(char):
            send(scan, 0x0004)          # KEYEVENTF_UNICODE
            send(scan, 0x0004 | 0x0002)  # | KEYEVENTF_KEYUP
        time.sleep(0.01)

    shown = text if len(text) <= 60 else text[:57] + "..."
    return ToolResult(f"Yazıldı: {shown!r}")


def _utf16_units(char: str) -> list[int]:
    raw = char.encode("utf-16-le")
    return [int.from_bytes(raw[i : i + 2], "little") for i in range(0, len(raw), 2)]


def _focus(target: str) -> ToolResult:
    import ctypes

    if not target.strip():
        return ToolResult.error("`target` gerekli — pencere başlığından bir parça.")

    wanted = target.strip().lower()
    rows = _windows()
    match = next((title for title, _f in rows if wanted in title.lower()), None)
    if match is None:
        listing = "\n".join(f"- {t}" for t, _f in rows[:15])
        return ToolResult.error(
            f"{target!r} ile eşleşen pencere yok. Açık pencereler:\n{listing}"
        )

    import ctypes.wintypes as wintypes

    user32 = ctypes.windll.user32
    hwnd_found: list[int] = []
    proc = ctypes.WINFUNCTYPE(ctypes.c_int, wintypes.HWND, wintypes.LPARAM)

    def keep(hwnd: Any, _lp: Any) -> int:
        length = user32.GetWindowTextLengthW(hwnd)
        if length and user32.IsWindowVisible(hwnd):
            buffer = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buffer, length + 1)
            if buffer.value == match:
                hwnd_found.append(hwnd)
                return 0
        return 1

    user32.EnumWindows(proc(keep), 0)
    if not hwnd_found:
        return ToolResult.error(f"Pencere bulunamadı: {match!r}")

    if _to_front(hwnd_found[0]):
        return ToolResult(f"Öne getirildi: {match}. Görmek için `screen action=look`.")
    # If it did not come to the front, SAY SO: failing silently sends the
    # typing and clicking to the wrong window. Exactly this happened in a
    # real run — Notepad stayed in the background, the text went to the
    # browser in front.
    return ToolResult.error(
        f"{match!r} öne getirilemedi (Windows odak kilidi). Görev çubuğunda "
        "yanıp sönüyor olabilir; kullanıcıdan bir kez tıklamasını iste ya da "
        "`hand action=key keys=alt+tab` ile geçmeyi dene. `screen action=look` "
        "ile hangi pencerenin önde olduğunu doğrulamadan yazma."
    )


def _to_front(hwnd: int) -> bool:
    """Really brings a window to the front and verifies it got there.

    Windows prevents a background process from stealing focus with
    `SetForegroundWindow`: the call fails silently, the window only
    blinks on the taskbar. In a real run this sent the typed text to the
    wrong (frontmost) window.

    Three measures together beat the lock:
      1. Reset the focus-lock timeout (SPI_SETFOREGROUNDLOCKTIMEOUT).
      2. Attach the calling thread's input to both the foreground and
         the target window's thread (AttachThreadInput) — for that
         moment we count as "the foreground application" and gain the
         right.
      3. A short ALT tap: tricks Windows into thinking user interaction
         happened, loosening the lock.

    The result is actually verified: if GetForegroundWindow does not
    show the target, False is returned so the caller does not type into
    the wrong window.
    """
    import ctypes

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    SW_RESTORE = 9
    SPI_SETFOREGROUNDLOCKTIMEOUT = 0x2001
    ALT = 0x12

    try:
        user32.SystemParametersInfoW(SPI_SETFOREGROUNDLOCKTIMEOUT, 0, 0, 0)
    except Exception:
        pass

    SW_MINIMIZE = 6

    cur = kernel32.GetCurrentThreadId()
    fg = user32.GetForegroundWindow()
    fg_tid = user32.GetWindowThreadProcessId(fg, None) if fg else 0
    tgt_tid = user32.GetWindowThreadProcessId(hwnd, None)

    attached = []
    for tid in {fg_tid, tgt_tid}:
        if tid and tid != cur and user32.AttachThreadInput(cur, tid, True):
            attached.append(tid)

    # The ALT tap loosens the focus lock.
    user32.keybd_event(ALT, 0, 0, 0)
    user32.keybd_event(ALT, 0, 2, 0)

    # Minimize then restore earns real foreground rights. SetForegroundWindow
    # alone does not raise a window buried behind a covering one (like a
    # fullscreen browser) — even when GetForegroundWindow said "it came",
    # the keystrokes went to the old window. Minimize→restore is the only
    # reliable way past this trap. Already in front and normal: we do not touch it.
    if not user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_MINIMIZE)
        time.sleep(0.02)
    user32.ShowWindow(hwnd, SW_RESTORE)
    user32.BringWindowToTop(hwnd)
    user32.SetForegroundWindow(hwnd)
    user32.SetActiveWindow(hwnd)
    user32.SetFocus(hwnd)

    time.sleep(0.08)
    ok = user32.GetForegroundWindow() == hwnd

    for tid in attached:
        user32.AttachThreadInput(cur, tid, False)
    return bool(ok)


def _open(target: str) -> ToolResult:
    import os
    import webbrowser

    if not target.strip():
        return ToolResult.error("`target` gerekli — uygulama, dosya ya da adres.")

    target = target.strip()
    if target.startswith(("http://", "https://")):
        webbrowser.open(target)
        return ToolResult(
            f"Tarayıcıda açıldı: {target}. Sayfayı görmek için birkaç saniye "
            "sonra `screen action=look`."
        )

    try:
        os.startfile(target)  # a file, a folder, or an application on PATH
    except OSError as exc:
        return ToolResult.error(
            f"Açılamadı: {target!r} ({exc}). Tam yol dene ya da `shell` ile "
            "`start {target}` çalıştır."
        )
    return ToolResult(f"Açıldı: {target}. Görmek için `screen action=look`.")
