"""Starting on its own when the computer boots.

An agent that lives in the tray and wakes on "hey dornick" is not
autonomous if it has to be started by hand on every boot.

The registration place is `HKCU\\...\\Run`: for this user only, without
admin rights, with a single value. We do not write system-wide (HKLM) —
one user's preference must not bind the whole machine.

Turning it off is the same place: deleting the value is enough. The user
can also see it in `regedit` or in Task Manager › Startup if they wish;
we leave nothing hidden.
"""

from __future__ import annotations

import sys

# The name in the registry. This is what shows in Task Manager's startup list.
NAME = "dornick"

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def available() -> bool:
    """Windows only. The setting is not shown elsewhere."""
    return sys.platform == "win32"


def command() -> str:
    """The line to run at boot.

    The stamped `dornick.exe` (or `pythonw` if absent) is chosen:
    `python` opens a console window and a black box appears in the middle
    of the screen on every boot. Task Manager also shows the host PE's
    icon, so the stamped copy is needed instead of pythonw.
    """
    from .winicon import app_executable

    runner = app_executable()
    return f'"{runner}" -m dornick.cli --app'


def enabled() -> bool:
    if not available():
        return False
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _kind = winreg.QueryValueEx(key, NAME)
    except OSError:
        return False
    return bool(value)


def current() -> str:
    """The line sitting in the registry. The settings page shows this: the
    user must be able to see what was written."""
    if not available():
        return ""
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _kind = winreg.QueryValueEx(key, NAME)
    except OSError:
        return ""
    return str(value)


def enable() -> str:
    """Adds to startup. Returns the written line."""
    if not available():
        raise RuntimeError("Otomatik başlatma yalnızca Windows'ta.")
    import winreg

    line = command()
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
        winreg.SetValueEx(key, NAME, 0, winreg.REG_SZ, line)
    return line


def disable() -> None:
    """Removes from startup. Passes silently if absent."""
    if not available():
        return
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, NAME)
    except OSError:
        pass


def apply(on: bool) -> str:
    if on:
        return enable()
    disable()
    return ""
