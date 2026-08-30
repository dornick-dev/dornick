"""Kapanıştaki tercihler sıfırlanmasın."""

from __future__ import annotations

import inspect
from pathlib import Path

from neocp import prefs


def test_prefs_roundtrip(tmp_path: Path) -> None:
    prefs.patch(tmp_path, hearing_snoozed=True, sight_snoozed=False)
    got = prefs.load(tmp_path)
    assert got["hearing_snoozed"] is True
    assert got["sight_snoozed"] is False


def test_broken_prefs_file_is_empty(tmp_path: Path) -> None:
    (tmp_path / prefs.NAME).write_text("{degil json", encoding="utf-8")
    got = prefs.load(tmp_path)
    assert got["hearing_snoozed"] is False
    assert got["window"] == {}


def test_window_patch_keeps_restore_size(tmp_path: Path) -> None:
    """Büyütülüyken kutu boyutu ezilmesin — sonraki açılış eski boyuta döner."""
    prefs.patch(
        tmp_path,
        window={"x": 10, "y": 20, "width": 1100, "height": 720},
    )
    prefs.patch(tmp_path, window={"maximized": True})
    win = prefs.load(tmp_path)["window"]
    assert win["width"] == 1100
    assert win["x"] == 10
    assert win["maximized"] is True


def test_tiny_window_is_ignored() -> None:
    assert prefs.window_args({"window": {"width": 200, "height": 200}}) == {}
    args = prefs.window_args({
        "window": {"width": 1200, "height": 800, "x": 40, "y": 50},
    })
    assert args["width"] == 1200
    assert args["x"] == 40


def test_desktop_webview_is_not_private() -> None:
    """pywebview varsayılanı gizli kip: tema/dil her açılışta sıfırlanıyordu."""
    from neocp import desktop
    src = inspect.getsource(desktop.run)
    assert "private_mode=False" in src
    assert "storage_path" in src


def test_ear_snooze_is_restored_from_prefs() -> None:
    """Mikrofon tıklaması kapanıştan sonra da susturulmuş kalsın."""
    from neocp import desktop
    src = inspect.getsource(desktop._boot)
    assert "hearing_snoozed" in src
    assert "sight_snoozed" in src
