"""Windows Explorer sağ tık: 'Neo ile aç'.

HKCU altına yazılır — yönetici hakkı yok. Kurulum ve Ayarlar › Makine
aynı yardımcıları kullanır; kaldırınca değerler silinir.
"""

from __future__ import annotations

import sys
from pathlib import Path

NAME = "NeoOpen"
LABEL = "Neo ile aç"

# Directory / * / Directory\Background
_KEYS = (
    rf"Software\Classes\*\shell\{NAME}",
    rf"Software\Classes\Directory\shell\{NAME}",
    rf"Software\Classes\Directory\Background\shell\{NAME}",
)


def available() -> bool:
    return sys.platform == "win32"


def command_line(*, open_arg: str = "%1") -> str:
    """Sağ tık komut satırı. `open_arg` Background için `%V` olur."""
    runner = Path(sys.executable)
    quiet = runner.with_name("pythonw.exe")
    if quiet.exists():
        runner = quiet
    # -m neocp.cli: kurulumda paket yolu PYTHONPATH'te.
    return f'"{runner}" -m neocp.cli --app --open "{open_arg}"'


def enabled() -> bool:
    if not available():
        return False
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _KEYS[0]):
            return True
    except OSError:
        return False


def enable() -> None:
    if not available():
        raise RuntimeError("Sağ tık menüsü yalnızca Windows'ta.")
    import winreg

    file_cmd = command_line("%1")
    bg_cmd = command_line("%V")
    for key, cmd in (
        (_KEYS[0], file_cmd),
        (_KEYS[1], file_cmd),
        (_KEYS[2], bg_cmd),
    ):
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key) as k:
            winreg.SetValueEx(k, None, 0, winreg.REG_SZ, LABEL)
            winreg.SetValueEx(k, "Icon", 0, winreg.REG_SZ, str(Path(sys.executable)))
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key + r"\command") as c:
            winreg.SetValueEx(c, None, 0, winreg.REG_SZ, cmd)


def disable() -> None:
    if not available():
        return
    import winreg

    for key in _KEYS:
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key + r"\command")
        except OSError:
            pass
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key)
        except OSError:
            pass


def apply(wanted: bool) -> None:
    if wanted:
        enable()
    else:
        disable()
