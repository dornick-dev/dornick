"""Windows süreç simgesi: damgalı neo.exe.

Görev çubuğu AppUserModelID + pencere ikonuna bakar; Görev Yöneticisi ve
WebView2 alt süreçleri ise ev sahibi PE'nin kaynağına. python.exe damgalı
olmadığı sürece orada Python yılanı kalır. Çözüm: pythonw.exe'yi aynı
klasöre neo.exe diye kopyalayıp neo.ico'yu RT_GROUP_ICON olarak yazmak —
DLL'ler yan yana kalır, yorumlayıcı adı değişmez, yalnız görünen kimlik
değişir. pythonw.exe'nin üstüne yazılmaz (venv/başka işler).
"""

from __future__ import annotations

import os
import struct
import sys
from pathlib import Path

HOST_NAME = "neo.exe"

# UpdateResource dil kodu: yansız + US English (pythonw 1033 taşır).
_LANG_NEUTRAL = 0
_RT_ICON = 3
_RT_GROUP_ICON = 14

# Relaunch: process tree'den kop (taskkill /T ebeveyni öldürünce çocuk kalır).
_CREATE_NEW_PROCESS_GROUP = 0x00000200
_CREATE_BREAKAWAY_FROM_JOB = 0x01000000

_SKIP_ENV = "NEO_KEEP_INTERPRETER"
_SKIP_PIDS_ENV = "NEO_REEXEC_SKIP"


def app_executable() -> Path:
    """Kısayol / kayıt hedefi: damgalı neo.exe varsa o, yoksa pythonw."""
    exe = Path(sys.executable).resolve()
    if sys.platform != "win32":
        return exe
    host = exe.with_name(HOST_NAME)
    if host.exists():
        return host
    quiet = exe.with_name("pythonw.exe")
    return quiet if quiet.exists() else exe


def skip_pids() -> set[int]:
    """Relaunch ebeveyni: hayalet avı /T ile çocuğu da öldürmesin."""
    raw = os.environ.get(_SKIP_PIDS_ENV, "")
    found: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            found.add(int(part))
    return found


def ensure_host() -> Path | None:
    """pythonw → neo.exe kopyası + ico damgası. Yazılamazsa None.

    Çalışan görüntüye yazılmaz. Damga sürümü logo._SURUM ile kilitli:
    çizim değişince sidecar uyuşmaz, pythonw serbestse yeniden kopyalanır.
    """
    if sys.platform != "win32":
        return None
    exe = Path(sys.executable).resolve()
    dest = exe.with_name(HOST_NAME)
    if exe.name.lower() == HOST_NAME:
        return exe
    source = exe.with_name("pythonw.exe")
    if not source.exists():
        source = exe
    if source.name.lower() == HOST_NAME:
        return dest if dest.exists() else None

    from .logo import _SURUM, ico_path

    bekci = Path(str(dest) + ".surum")
    need = True
    if dest.exists():
        try:
            if bekci.read_text(encoding="utf-8").strip() == _SURUM:
                if dest.stat().st_mtime >= source.stat().st_mtime:
                    need = False
        except OSError:
            pass
    if need:
        try:
            import shutil

            shutil.copy2(source, dest)
            if stamp_exe_icon(dest, ico_path()):
                bekci.write_text(_SURUM, encoding="utf-8")
        except OSError:
            if not dest.exists():
                return None
    return dest if dest.exists() else None


def relaunch_as_host() -> None:
    """python(w) ise damgalı neo.exe olarak yeniden açılıp bu süreç biter.

    NEO_KEEP_INTERPRETER=1 geliştirme konsolunu korur. Program Files altındaki
    sistem Python'u yazılamazsa sessizce mevcut yorumlayıcıyla devam eder.
    """
    if sys.platform != "win32":
        return
    if os.environ.get(_SKIP_ENV, "").strip() in ("1", "true", "yes"):
        return
    if Path(sys.executable).name.lower() == HOST_NAME:
        return
    host = ensure_host()
    if host is None:
        return
    try:
        if host.resolve() == Path(sys.executable).resolve():
            return
    except OSError:
        return
    import subprocess

    env = os.environ.copy()
    env[_SKIP_PIDS_ENV] = str(os.getpid())
    try:
        subprocess.Popen(
            [str(host), *_argv_tail()],
            cwd=os.getcwd(),
            env=env,
            close_fds=True,
            creationflags=_CREATE_NEW_PROCESS_GROUP | _CREATE_BREAKAWAY_FROM_JOB,
        )
    except OSError:
        return
    print("[neo] pencere açılıyor…", flush=True)
    os._exit(0)


def _argv_tail() -> list[str]:
    """neo.exe pythonw kopyasıdır: mutlaka `-m neocp …` ile açılır.

    `neocp --app` konsol betiğinde `sys.orig_argv` `[neocp.exe, --app]`
    oluyor. Bunu olduğu gibi vermek `pythonw --app` demek — geçersiz
    seçenek, konsolsuz süreç sessizce ölür, terminal de hemen boş prompt'a
    döner.
    """
    rest = list(sys.argv[1:])
    orig = getattr(sys, "orig_argv", None) or []
    # `python -m neocp …` / `python -m neocp.cli …` zaten doğru kuyruk.
    if (len(orig) >= 3 and orig[1] == "-m"
            and orig[2].replace("-", "_").startswith("neocp")):
        return list(orig[1:])
    return ["-m", "neocp", *rest]


def stamp_exe_icon(exe: Path, ico: Path) -> bool:
    """ICO görüntülerini PE'nin RT_ICON / RT_GROUP_ICON kaynaklarına yazar.

    Tip/ad tamsayı ID'dir (MAKEINTRESOURCE). ctypes argtype LPCWSTR olursa
    ID=1 adres 1'den string okunur → access violation. c_void_p kullanılır.
    Dil 0 ve 1033: pythonw genelde US English taşır; ikisine de yazınca
    Görev Yöneticisi eski yılanı seçmez.
    """
    if sys.platform != "win32":
        return False
    try:
        images = _read_ico(ico.read_bytes())
    except (OSError, ValueError):
        return False
    if not images:
        return False
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.BeginUpdateResourceW.argtypes = [wintypes.LPCWSTR, wintypes.BOOL]
    kernel32.BeginUpdateResourceW.restype = wintypes.HANDLE
    kernel32.UpdateResourceW.argtypes = [
        wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p,
        wintypes.WORD, wintypes.LPVOID, wintypes.DWORD,
    ]
    kernel32.UpdateResourceW.restype = wintypes.BOOL
    kernel32.EndUpdateResourceW.argtypes = [wintypes.HANDLE, wintypes.BOOL]
    kernel32.EndUpdateResourceW.restype = wintypes.BOOL

    group = bytearray(struct.pack("<HHH", 0, 1, len(images)))
    payloads: list[bytes] = []
    for idx, img in enumerate(images, start=1):
        data = img["data"]
        payloads.append(data)
        group += struct.pack(
            "<BBBBHHIH",
            img["width"], img["height"], img["colors"], 0,
            img["planes"], img["bits"], len(data), idx,
        )
    group_bytes = bytes(group)

    handle = kernel32.BeginUpdateResourceW(str(exe), False)
    if not handle:
        return False
    ended = False
    try:
        for lang in (_LANG_NEUTRAL, 0x0409):
            for idx, data in enumerate(payloads, start=1):
                buf = (ctypes.c_char * len(data)).from_buffer_copy(data)
                if not kernel32.UpdateResourceW(
                        handle, _RT_ICON, idx, lang, buf, len(data)):
                    return False
            gbuf = (ctypes.c_char * len(group_bytes)).from_buffer_copy(group_bytes)
            if not kernel32.UpdateResourceW(
                    handle, _RT_GROUP_ICON, 1, lang, gbuf, len(group_bytes)):
                return False
        ok = bool(kernel32.EndUpdateResourceW(handle, False))
        ended = True
        return ok
    finally:
        if not ended:
            kernel32.EndUpdateResourceW(handle, True)


def _read_ico(data: bytes) -> list[dict]:
    if len(data) < 6:
        raise ValueError("ico too small")
    reserved, kind, count = struct.unpack_from("<HHH", data, 0)
    if reserved != 0 or kind != 1 or count < 1:
        raise ValueError("not an icon")
    images: list[dict] = []
    off = 6
    for _ in range(count):
        width, height, colors, _res, planes, bits, size, offset = struct.unpack_from(
            "<BBBBHHII", data, off)
        off += 16
        payload = data[offset:offset + size]
        if len(payload) != size:
            raise ValueError("truncated ico")
        planes, bits = _planes_and_bits(planes, bits, payload)
        images.append({
            "width": width,
            "height": height,
            "colors": colors,
            "planes": planes,
            "bits": bits,
            "data": payload,
        })
    return images


def _planes_and_bits(planes: int, bits: int, payload: bytes) -> tuple[int, int]:
    if planes and bits:
        return planes, bits
    if payload[:8] == b"\x89PNG\r\n\x1a\n":
        return 1, 32
    if len(payload) >= 16:
        dib_planes, dib_bits = struct.unpack_from("<HH", payload, 12)
        return dib_planes or 1, dib_bits or 32
    return 1, 32
