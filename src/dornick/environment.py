"""Runtime environment: installed layout or developer repo?

In the tree set up by the installer wizard Python is embedded
(<root>\\python\\...) and the wizard drops setup.json (formerly
kurulum.json) at the root. In the developer repo there is an ordinary
pip-installed Python.

This distinction changes user-visible texts: telling a developer
"pip install ..." for a missing feature is right, telling someone who came
through the installer wizard is meaningless — they are told to re-run the
wizard.

Then there is the console matter: the installed app runs under pythonw
(no console). Every console child process started without flags from a
console-less process (powershell, netstat, taskkill...) flashes a cmd
window on screen. `quiet_flags()` gives the subprocess switches that
suppress that window.

Version is this module's job too: which copy is running was invisible in
the field. The single source of truth is pyproject.toml — since the
installed tree mirrors the repo layout exactly and build.ps1 puts
pyproject at the package root, it is read from the same place in both layouts.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def is_installed() -> bool:
    """Are we in the layout set up by the installer wizard?

    Two independent traces suffice: the embedded Python's ._pth file (the
    wizard package always installs with it) and the setup.json /
    kurulum.json the wizard leaves in the install. Neither exists in the
    developer repo.
    """
    try:
        exe = Path(sys.executable).resolve()
    except OSError:  # pragma: no cover - broken sys.executable
        return False
    if next(exe.parent.glob("python3*._pth"), None) is not None:
        return True
    root = exe.parent.parent
    return (root / "setup.json").exists() or (root / "kurulum.json").exists()


def _root() -> Path:
    """Root of the application tree: two levels above src/Dornick.

    The repo root in the developer repo, {app} in the installed layout —
    both carry pyproject.toml at this level (build.ps1 puts it there when installed).
    """
    return Path(__file__).resolve().parents[2]


@lru_cache(maxsize=1)
def version() -> str:
    """Version of the running copy — single source of truth pyproject.toml.

    If pyproject cannot be read (a hand-broken tree) we fall back to pip
    metadata; if that is missing too, "0.0.0" — at least the UI is not blank.
    """
    try:
        import tomllib

        with open(_root() / "pyproject.toml", "rb") as f:
            value = tomllib.load(f).get("project", {}).get("version")
        if value:
            return str(value)
    except (OSError, ValueError):
        pass
    try:
        from importlib.metadata import PackageNotFoundError, version

        return version("dornick")
    except Exception:  # pragma: no cover - no metadata either
        return "0.0.0"


# The update check is triggered MANUALLY (Settings › Machine); there is
# deliberately no check that goes to the network on its own in the
# background — privacy and simplicity.
UPDATE_API = "https://api.github.com/repos/dornick-dev/dornick/releases/latest"
UPDATE_TIMEOUT = 6.0


def _parse_version(text: str) -> tuple[int, ...]:
    """"v0.2.10" → (0, 2, 10). If no number is found, an empty tuple — the
    comparison falls to the no-new-version side, never blows up."""
    return tuple(int(p) for p in re.findall(r"\d+", text)[:4])


def check_update(*, _ac=urllib.request.urlopen) -> dict:
    """Asks GitHub for the latest release and compares it with the current one.

    The returned dict is everything the UI draws:
      ok      did the request reach its destination
      mevcut  the running version
      yeni    if a newer release exists its version, otherwise ""
      url     the new version's release page (opened in the browser)
      indirme direct link to the installer file (.exe) attached to the release;
              "" if the release has no installer — the UI then falls back
              to the release page
      hata    polite, human-language error text (while ok=False)
    """
    current = version()
    request = urllib.request.Request(
        UPDATE_API, headers={"Accept": "application/vnd.github+json",
                                 "User-Agent": f"dornick/{current}"})
    try:
        with _ac(request, timeout=UPDATE_TIMEOUT) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            # Repo/release not visible: no release may have been published yet.
            return {"ok": False, "mevcut": current, "yeni": "", "url": "",
                    "indirme": "", "hata": "Yayınlanmış sürüm bulunamadı"}
        return {"ok": False, "mevcut": current, "yeni": "", "url": "",
                "indirme": "",
                "hata": f"Sürüm servisi cevap vermedi (HTTP {exc.code})"}
    except Exception:
        return {"ok": False, "mevcut": current, "yeni": "", "url": "",
                "indirme": "",
                "hata": "Ağa ulaşılamadı — internet bağlantısını denetle"}

    remote = str(data.get("tag_name") or data.get("name") or "").strip()
    url = str(data.get("html_url") or "")
    if _parse_version(remote) > _parse_version(current):
        download, size, name = _installer_asset(data)
        return {"ok": True, "mevcut": current, "yeni": remote.lstrip("vV"),
                "url": url, "indirme": download, "boyut": size, "ad": name,
                "hata": ""}
    return {"ok": True, "mevcut": current, "yeni": "", "url": "",
            "indirme": "", "boyut": 0, "ad": "", "hata": ""}


def _installer_asset(data: dict) -> tuple[str, int, str]:
    """The installer file among the release assets: (download_url, size, name).

    The .exe (installer wizard) attached to the GitHub release is looked
    for; with several .exes the one with "setup"/"kurulum" in its name is
    preferred. If none is found ("", 0, "") — the UI falls back to the
    release-page link, nothing breaks. The size travels along for the
    progress bar and the integrity check during download.
    """
    assets = data.get("assets") or []
    if not isinstance(assets, list):
        return ("", 0, "")
    exes = []
    for v in assets:
        if not isinstance(v, dict):
            continue
        name = str(v.get("name") or "")
        download = str(v.get("browser_download_url") or "")
        size = int(v.get("size") or 0)
        if name.lower().endswith(".exe") and download:
            exes.append((name, download, size))
    for name, download, size in exes:
        if "setup" in name.lower() or "kurulum" in name.lower():
            return (download, size, name)
    if exes:
        return (exes[0][1], exes[0][2], exes[0][0])
    return ("", 0, "")


# The ONLY place a download may come from: the official GitHub release
# infrastructure. The address comes from the server's API response (the
# client does not supply it) and additionally passes the host filter here
# — a poisoned address cannot be downloaded and executed.
def _guvenilir_indirme(url: str) -> bool:
    try:
        host = (urllib.parse.urlparse(url).hostname or "").lower()
    except ValueError:
        return False
    if urllib.parse.urlparse(url).scheme != "https":
        return False
    return host == "github.com" or host.endswith(".githubusercontent.com")


def download_update(url: str, target_dir, *, expected_size: int = 0,
                     name: str = "", progress=None,
                     _ac=urllib.request.urlopen):
    """Downloads the installer file from the trusted GitHub address.

    Returns: the Path of the downloaded file. Security:
      * the address must be https and github.com / *.githubusercontent.com
      * the FINAL address after redirects passes the same filter
      * the file must be an .exe; if the size is known it must roughly match
    `progress(downloaded, total)` is called on every chunk (the UI bar).
    """
    import shutil
    import urllib.parse
    from pathlib import Path

    if not _guvenilir_indirme(url):
        raise ValueError(f"Güvenilmeyen indirme adresi: {url!r}")

    file_name = name or Path(urllib.parse.urlparse(url).path).name or "dornick-setup.exe"
    if not file_name.lower().endswith(".exe"):
        raise ValueError("Kurulum dosyası .exe olmalı")
    target = Path(target_dir)
    target.mkdir(parents=True, exist_ok=True)
    path = target / file_name

    request = urllib.request.Request(
        url, headers={"User-Agent": f"dornick/{version()}",
                      "Accept": "application/octet-stream"})
    with _ac(request, timeout=60) as response:
        # The final address after redirects must be trusted too.
        final = getattr(response, "url", None) or response.geturl()
        if not _guvenilir_indirme(final):
            raise ValueError(f"Yönlendirme güvenilmeyen adrese gitti: {final!r}")
        total = int(response.headers.get("Content-Length") or expected_size or 0)
        downloaded = 0
        temp = path.with_suffix(path.suffix + ".indiriliyor")
        with open(temp, "wb") as f:
            while True:
                chunk = response.read(1024 * 256)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                if progress is not None:
                    try:
                        progress(downloaded, total)
                    except Exception:
                        pass
    # Integrity: if the size is known it must roughly match (a truncated download must not run).
    if expected_size and abs(downloaded - expected_size) > max(1024, expected_size // 100):
        temp.unlink(missing_ok=True)
        raise ValueError(
            f"İndirme eksik: {downloaded} bayt geldi, {expected_size} bekleniyordu")
    if downloaded < 1024 * 1024:   # under 1 MB cannot be an installer wizard
        temp.unlink(missing_ok=True)
        raise ValueError(f"İndirilen dosya fazla küçük ({downloaded} bayt)")
    shutil.move(str(temp), str(path))
    return path


def start_update(path) -> None:
    """Starts the downloaded installer wizard (Windows).

    The installer closes the running app itself and replaces the files
    (dornick.iss `CloseApplications`). Here we only open the wizard; the
    caller (UI → tray) manages the app's shutdown.
    """
    import os
    from pathlib import Path

    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(str(path))
    if sys.platform == "win32":
        os.startfile(str(path))  # type: ignore[attr-defined]
    else:  # pragma: no cover - the installer wizard is Windows only
        subprocess.Popen([str(path)])


def quiet_flags() -> dict:
    """subprocess switches that do not open a console window on Windows.

    Every console child process whose output is piped or never shown must
    be opened with this flag; otherwise under pythonw each call flashes a
    cmd window on screen. Launches that WANT their own window (opening the
    user's app in a new console, say) deliberately use CREATE_NEW_CONSOLE
    — leave those alone.
    """
    if sys.platform == "win32":
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    return {}


async def kill_tree(proc) -> None:
    """Terminates a child process and THOSE BENEATH IT.

    Just saying `proc.kill()` is not enough, and this was seen by
    measurement in two separate places (the test runner and hooks). For a
    command started through the shell `proc` is powershell/cmd/bash; the
    real work is its CHILD. Killing the shell leaves the real process
    (npm, pytest, the user's hook) running on the machine — and since it
    keeps the pipes open, the caller keeps waiting for it to finish.
    Measurement: a 2-second timeout turned into a 60-second wait.

    There are no process groups on Windows; the whole tree is brought down
    with `taskkill /T`. On POSIX the caller starts the process in its own
    session (`start_new_session`) and the group falls with a single signal.
    """
    import asyncio

    if proc.returncode is not None:
        return
    if sys.platform == "win32":
        try:
            tree = await asyncio.create_subprocess_exec(
                "taskkill", "/T", "/F", "/PID", str(proc.pid),
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                **quiet_flags(),
            )
            await asyncio.wait_for(tree.wait(), 10)
        except (OSError, ValueError, asyncio.TimeoutError):  # pragma: no cover
            pass
    else:  # pragma: no cover - the POSIX path does not run on Windows
        import os
        import signal

        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (OSError, ProcessLookupError):
            pass
    try:
        proc.kill()
    except (ProcessLookupError, OSError):
        pass
    try:
        await asyncio.wait_for(proc.wait(), 10)
    except (asyncio.TimeoutError, ProcessLookupError):  # pragma: no cover
        pass
