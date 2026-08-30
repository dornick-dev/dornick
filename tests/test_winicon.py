"""Görev Yöneticisi simgesi: damgalı neo.exe, python yılanı değil."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

from neocp import logo, winicon


def test_app_executable_prefers_stamped_host(tmp_path: Path, monkeypatch) -> None:
    py = tmp_path / "python.exe"
    pyw = tmp_path / "pythonw.exe"
    host = tmp_path / "neo.exe"
    py.write_bytes(b"MZ")
    pyw.write_bytes(b"MZ")
    host.write_bytes(b"MZ")
    monkeypatch.setattr(sys, "executable", str(py))
    assert winicon.app_executable() == host.resolve()


def test_app_executable_falls_back_to_pythonw(tmp_path: Path, monkeypatch) -> None:
    py = tmp_path / "python.exe"
    pyw = tmp_path / "pythonw.exe"
    py.write_bytes(b"MZ")
    pyw.write_bytes(b"MZ")
    monkeypatch.setattr(sys, "executable", str(py))
    assert winicon.app_executable() == pyw.resolve()


def test_ico_has_multiple_sizes() -> None:
    images = winicon._read_ico(logo.ico_path().read_bytes())
    assert len(images) >= 2
    assert all(img["data"] for img in images)


def test_skip_pids_from_env(monkeypatch) -> None:
    monkeypatch.setenv("NEO_REEXEC_SKIP", "12, 34,x")
    assert winicon.skip_pids() == {12, 34}


def test_relaunch_argv_always_loads_the_module(monkeypatch) -> None:
    """Konsol betiği `neocp --app`: orig_argv [neocp.exe, --app].
    Bunu pythonw'ye vermek sessizce ölür, pencere hiç açılmaz."""
    monkeypatch.setattr(sys, "argv", [r"C:\venv\Scripts\neocp.exe", "--app"])
    monkeypatch.setattr(
        sys, "orig_argv", [r"C:\venv\Scripts\neocp.exe", "--app"], raising=False)
    assert winicon._argv_tail() == ["-m", "neocp", "--app"]
    monkeypatch.setattr(
        sys, "orig_argv",
        [r"C:\Python\python.exe", "-m", "neocp", "--app"], raising=False)
    monkeypatch.setattr(sys, "argv", ["-m", "neocp", "--app"])
    assert winicon._argv_tail()[0:3] == ["-m", "neocp", "--app"]


def test_installer_shortcuts_target_neo_exe() -> None:
    """Kısayol pythonw kalırsa Görev Yöneticisi yılanı gösterir."""
    iss = (Path(__file__).resolve().parents[1] / "installer" / "neo.iss").read_text(
        encoding="utf-8")
    assert r'{app}\python\neo.exe' in iss
    icons = iss.split("[Icons]", 1)[1].split("[Registry]", 1)[0]
    assert "pythonw.exe" not in icons


@pytest.mark.skipif(sys.platform != "win32", reason="PE damgası Windows")
def test_stamp_writes_group_icon(tmp_path: Path) -> None:
    dest = tmp_path / "neo.exe"
    shutil.copy2(sys.executable, dest)
    assert winicon.stamp_exe_icon(dest, logo.ico_path())
    blob = dest.read_bytes()
    assert blob[:2] == b"MZ"
    biggest = max(winicon._read_ico(logo.ico_path().read_bytes()),
                  key=lambda img: len(img["data"]))
    assert biggest["data"] in blob
