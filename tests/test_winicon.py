"""Görev Yöneticisi simgesi: damgalı dornick.exe, python yılanı değil."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

from dornick import logo, winicon


def test_app_executable_prefers_stamped_host(tmp_path: Path, monkeypatch) -> None:
    py = tmp_path / "python.exe"
    pyw = tmp_path / "pythonw.exe"
    host = tmp_path / "dornick.exe"
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
    monkeypatch.setenv("DORNICK_REEXEC_SKIP", "12, 34,x")
    assert winicon.skip_pids() == {12, 34}


def test_relaunch_argv_always_loads_the_module(monkeypatch) -> None:
    """Konsol betiği `dornick --app`: orig_argv [dornick.exe, --app].
    Bunu pythonw'ye vermek sessizce ölür, pencere hiç açılmaz."""
    monkeypatch.setattr(sys, "argv", [r"C:\venv\Scripts\dornick.exe", "--app"])
    monkeypatch.setattr(
        sys, "orig_argv", [r"C:\venv\Scripts\dornick.exe", "--app"], raising=False)
    assert winicon._argv_tail() == ["-m", "dornick", "--app"]
    monkeypatch.setattr(
        sys, "orig_argv",
        [r"C:\Python\python.exe", "-m", "dornick", "--app"], raising=False)
    monkeypatch.setattr(sys, "argv", ["-m", "dornick", "--app"])
    assert winicon._argv_tail()[0:3] == ["-m", "dornick", "--app"]


def test_installer_shortcuts_target_neo_exe() -> None:
    """Kısayol pythonw kalırsa Görev Yöneticisi yılanı gösterir."""
    iss = (Path(__file__).resolve().parents[1] / "installer" / "dornick.iss").read_text(
        encoding="utf-8")
    assert r'{app}\python\dornick.exe' in iss
    icons = iss.split("[Icons]", 1)[1].split("[Registry]", 1)[0]
    assert "pythonw.exe" not in icons
    assert 'AppUserModelID: "fatih.dornick.app"' in icons


def test_toast_aumid_matches_process_identity() -> None:
    """Bildirim kimliği süreç AUMID'siyle aynı olmazsa Windows yılan basar."""
    assert winicon.AUMID == "fatih.dornick.app"
    desktop = (Path(__file__).resolve().parents[1] / "src" / "dornick" / "desktop.py")
    text = desktop.read_text(encoding="utf-8")
    assert "ensure_toast_identity" in text
    assert "SetCurrentProcessExplicitAppUserModelID" in text


def test_png_is_a_real_png() -> None:
    data = logo.png_path().read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"


@pytest.mark.skipif(sys.platform != "win32", reason="PE damgası Windows")
def test_stamp_writes_group_icon(tmp_path: Path) -> None:
    dest = tmp_path / "dornick.exe"
    shutil.copy2(sys.executable, dest)
    assert winicon.stamp_exe_icon(dest, logo.ico_path())
    blob = dest.read_bytes()
    assert blob[:2] == b"MZ"
    biggest = max(winicon._read_ico(logo.ico_path().read_bytes()),
                  key=lambda img: len(img["data"]))
    assert biggest["data"] in blob
