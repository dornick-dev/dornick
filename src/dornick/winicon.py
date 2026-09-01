"""Windows süreç simgesi: damgalı dornick.exe.

Görev çubuğu AppUserModelID + pencere ikonuna bakar; Görev Yöneticisi ve
WebView2 alt süreçleri ise ev sahibi PE'nin kaynağına. python.exe damgalı
olmadığı sürece orada Python yılanı kalır. Çözüm: pythonw.exe'yi aynı
klasöre dornick.exe diye kopyalayıp dornick.ico'yu RT_GROUP_ICON olarak yazmak —
DLL'ler yan yana kalır, yorumlayıcı adı değişmez, yalnız görünen kimlik
değişir. pythonw.exe'nin üstüne yazılmaz (venv/başka işler).
"""

from __future__ import annotations

import os
import struct
import sys
from pathlib import Path

HOST_NAME = "dornick.exe"
# Görev çubuğu + Windows bildirimi aynı kimlik: eşleşmezse toast Python
# yılanını gösterir, kısayol ikonu da bağlanmaz.
AUMID = "fatih.dornick.app"

# UpdateResource dil kodu: yansız + US English (pythonw 1033 taşır).
_LANG_NEUTRAL = 0
_RT_ICON = 3
_RT_GROUP_ICON = 14

# Relaunch: process tree'den kop (taskkill /T ebeveyni öldürünce çocuk kalır).
_CREATE_NEW_PROCESS_GROUP = 0x00000200
_CREATE_BREAKAWAY_FROM_JOB = 0x01000000

_SKIP_ENV = "DORNICK_KEEP_INTERPRETER"
_SKIP_PIDS_ENV = "DORNICK_REEXEC_SKIP"


def app_executable() -> Path:
    """Kısayol / kayıt hedefi: damgalı dornick.exe varsa o, yoksa pythonw."""
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
    """pythonw → dornick.exe kopyası + ico damgası. Yazılamazsa None.

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
    """python(w) ise damgalı dornick.exe olarak yeniden açılıp bu süreç biter.

    DORNICK_KEEP_INTERPRETER=1 geliştirme konsolunu korur. Program Files altındaki
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
    print("[dornick] pencere açılıyor…", flush=True)
    os._exit(0)


def _argv_tail() -> list[str]:
    """dornick.exe pythonw kopyasıdır: mutlaka `-m dornick …` ile açılır.

    `dornick --app` konsol betiğinde `sys.orig_argv` `[dornick.exe, --app]`
    oluyor. Bunu olduğu gibi vermek `pythonw --app` demek — geçersiz
    seçenek, konsolsuz süreç sessizce ölür, terminal de hemen boş prompt'a
    döner.
    """
    rest = list(sys.argv[1:])
    orig = getattr(sys, "orig_argv", None) or []
    # `python -m dornick …` / `python -m dornick.cli …` zaten doğru kuyruk.
    if (len(orig) >= 3 and orig[1] == "-m"
            and orig[2].replace("-", "_").startswith("dornick")):
        return list(orig[1:])
    return ["-m", "dornick", *rest]


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


def ensure_toast_identity() -> None:
    """Windows bildiriminin başlığı 'dornick', simgesi logo olsun.

    Toast, süreç AUMID'sine bakıyor. Eşleşen bir Başlat kısayolu ve
    DisplayName olmadan bildirim Python yılanıyla geliyor (ya da hiç
    gelmiyor). Kısayol ikonu + kayıt, pystray balonundan bağımsız.
    """
    if sys.platform != "win32":
        return
    from .logo import ico_path, png_path

    png = png_path()
    ico = ico_path()
    target = app_executable()
    programs = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    if not programs.is_dir():
        return
    lnk = programs / "dornick.lnk"
    args = " ".join(_argv_tail())
    _yaz_kisayol(lnk, target, args, ico)
    _kisayol_aumid_yaz(lnk, AUMID)
    _yaz_bildirim_kaydi(png)


def _yaz_kisayol(lnk: Path, target: Path, args: str, ico: Path) -> None:
    from . import ortam

    def q(s: str) -> str:
        return "'" + str(s).replace("'", "''") + "'"

    ps = (
        "$s = (New-Object -ComObject WScript.Shell).CreateShortcut(%s); "
        "$s.TargetPath = %s; $s.Arguments = %s; $s.WorkingDirectory = %s; "
        "$s.IconLocation = %s; $s.Save()"
        % (q(lnk), q(target), q(args), q(target.parent), q(str(ico) + ",0"))
    )
    try:
        import subprocess
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
            timeout=12, **ortam.sessiz_bayraklar(),
        )
    except Exception:
        return


def _yaz_bildirim_kaydi(png: Path) -> None:
    try:
        import winreg
        key = winreg.CreateKey(
            winreg.HKEY_CURRENT_USER,
            rf"Software\Classes\AppUserModelId\{AUMID}",
        )
        try:
            winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, "dornick")
            winreg.SetValueEx(key, "IconUri", 0, winreg.REG_SZ, png.resolve().as_uri())
        finally:
            winreg.CloseKey(key)
    except OSError:
        return


def _kisayol_aumid_yaz(lnk: Path, aumid: str) -> None:
    """Kısayola System.AppUserModel.ID yazar.

    WScript.Shell IconLocation yazar; AUMID yazmaz. Toast notifier o
    kimliği Start Menu kısayolunda arar — yoksa Python yılanı gelir.
    """
    if sys.platform != "win32" or not lnk.is_file():
        return
    try:
        import ctypes
        from ctypes import HRESULT, POINTER, byref, c_uint, c_ulong, c_void_p

        ole32 = ctypes.OleDLL("ole32")
        shell32 = ctypes.WinDLL("shell32")

        class GUID(ctypes.Structure):
            _fields_ = [
                ("Data1", ctypes.c_uint32),
                ("Data2", ctypes.c_uint16),
                ("Data3", ctypes.c_uint16),
                ("Data4", ctypes.c_ubyte * 8),
            ]

        class PROPERTYKEY(ctypes.Structure):
            _fields_ = [("fmtid", GUID), ("pid", ctypes.c_uint32)]

        class PROPVARIANT(ctypes.Structure):
            _fields_ = [
                ("vt", ctypes.c_ushort),
                ("wReserved1", ctypes.c_ushort),
                ("wReserved2", ctypes.c_ushort),
                ("wReserved3", ctypes.c_ushort),
                ("pszVal", c_void_p),
            ]

        class IPropertyStoreVtbl(ctypes.Structure):
            _fields_ = [
                ("QueryInterface", c_void_p),
                ("AddRef", c_void_p),
                ("Release", c_void_p),
                ("GetCount", c_void_p),
                ("GetAt", c_void_p),
                ("GetValue", c_void_p),
                ("SetValue", c_void_p),
                ("Commit", c_void_p),
            ]

        class IPropertyStore(ctypes.Structure):
            _fields_ = [("lpVtbl", POINTER(IPropertyStoreVtbl))]

        ole32.CLSIDFromString.argtypes = [ctypes.c_wchar_p, POINTER(GUID)]
        ole32.CLSIDFromString.restype = HRESULT
        iid = GUID()
        if ole32.CLSIDFromString("{886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99}", byref(iid)):
            return
        pkey_id = GUID()
        if ole32.CLSIDFromString("{9F4C285D-9F4C-4D6A-9D38-5D649E7B8B1B}", byref(pkey_id)):
            return
        pkey = PROPERTYKEY(pkey_id, 5)

        GPS_READWRITE = 2
        store = c_void_p()
        shell32.SHGetPropertyStoreFromParsingName.restype = HRESULT
        shell32.SHGetPropertyStoreFromParsingName.argtypes = [
            ctypes.c_wchar_p, c_void_p, c_uint, POINTER(GUID), POINTER(c_void_p),
        ]
        if shell32.SHGetPropertyStoreFromParsingName(
                str(lnk), None, GPS_READWRITE, byref(iid), byref(store)):
            return
        if not store.value:
            return

        obj = ctypes.cast(store, POINTER(IPropertyStore)).contents
        vtbl = obj.lpVtbl.contents
        set_value = ctypes.WINFUNCTYPE(
            HRESULT, c_void_p, POINTER(PROPERTYKEY), POINTER(PROPVARIANT),
        )(vtbl.SetValue)
        commit = ctypes.WINFUNCTYPE(HRESULT, c_void_p)(vtbl.Commit)
        release = ctypes.WINFUNCTYPE(c_ulong, c_void_p)(vtbl.Release)

        buf = ctypes.create_unicode_buffer(aumid)
        pv = PROPVARIANT()
        pv.vt = 31  # VT_LPWSTR
        pv.pszVal = ctypes.cast(buf, c_void_p)
        try:
            if set_value(store, byref(pkey), byref(pv)):
                return
            commit(store)
        finally:
            release(store)
    except Exception:
        return
