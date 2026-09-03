"""Preferences at shutdown must not reset."""

from __future__ import annotations

import inspect
from pathlib import Path

from dornick import prefs


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
    """While maximised the box size must not be crushed — the next launch returns to the old size."""
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
    }, area=(0, 0, 1920, 1080))
    assert args["width"] == 1200
    assert args["x"] == 40


def test_maximized_omits_xy() -> None:
    """A maximised record + old x/y must not give create_window a position."""
    args = prefs.window_args({
        "window": {
            "maximized": True,
            "width": 1256,
            "height": 706,
            "x": 126,
            "y": 126,
        },
    }, area=(0, 0, 1707, 1019))
    assert args["maximized"] is True
    assert "x" not in args
    assert "y" not in args
    assert args["width"] == 1256
    assert args["height"] == 706


def test_offset_fullscreen_becomes_maximized() -> None:
    """Full-screen size but at (126,126) — broken; open maximised."""
    assert prefs.offset_fullscreen(126, 126, 1707, 1067, (0, 0, 1707, 1019))
    args = prefs.window_args({
        "window": {"width": 1707, "height": 1067, "x": 126, "y": 126},
    }, area=(0, 0, 1707, 1019))
    assert args == {"maximized": True}


def test_window_clamped_into_work_area() -> None:
    args = prefs.window_args({
        "window": {"width": 1200, "height": 800, "x": 5000, "y": -40},
    }, area=(0, 0, 1707, 1019))
    assert args["x"] == 1707 - 1200
    assert args["y"] == 0


def test_desktop_boot_forces_maximize_after_shell() -> None:
    from dornick import desktop
    src = inspect.getsource(desktop._titlebar_boot)
    assert "want_max" in src
    assert "_force_maximize" in src
    assert "_clamp_window_to_work" in inspect.getsource(desktop)
    run_src = inspect.getsource(desktop.run)
    assert "maximized=False" in run_src
    assert "want_max" in run_src


def test_desktop_heals_offset_maximize() -> None:
    """A drifted maximise (window near-full but at (100,100)) must settle
    on its own — the user must not have to shrink and reopen by hand.

    Live wound (31.08): at startup the desktop leaked in from the left/top,
    the content came clipped on the left. Three guards: the post-startup
    watch (_geometry_watch), a look when shown from the tray/wake, and the
    drift protection in the shell's zoom lock.
    """
    from dornick import desktop

    boot = inspect.getsource(desktop._titlebar_boot)
    assert "_geometry_watch" in boot
    heal = inspect.getsource(desktop._heal_geometry)
    assert "offset_fullscreen" in heal
    assert "IsZoomed" in heal
    assert "_monitor_work_area" in heal
    # The zoom lock only if the window really sits on the work area: in a
    # drifted zoom the screen-coordinate lock pushed the content negative.
    shell = inspect.getsource(desktop._install_shell_on)
    assert "rcWork.left) <= 64" in shell
    # Look again when it becomes visible from the tray / wake.
    run_src = inspect.getsource(desktop.run)
    assert "_heal_geometry" in run_src
    assert "_heal_geometry" in inspect.getsource(desktop._wake)


def test_single_strip_survives_a_hidden_start() -> None:
    """The single strip is set up even if the window is born HIDDEN.

    Live wound (02.09): when the app opens to the tray the window is born
    hidden; because `_dornick_windows()` counted only VISIBLE windows
    neither the styles nor the shell were ever set up, and when the window
    was shown later Windows' own title bar stayed ABOVE the app's strip —
    two strips on top of each other. Two defences: setup targets the hidden
    window too, and the show paths guarantee setup.
    """
    from dornick import desktop

    # The setups target the hidden window too.
    assert "gizli_de=True" in inspect.getsource(desktop._apply_native_styles)
    assert "gizli_de=True" in inspect.getsource(desktop._install_shell)

    # Guaranteed when shown: both the tray/wake path and the helper.
    run_src = inspect.getsource(desktop.run)
    assert "_ensure_native_chrome" in run_src
    guarantee = inspect.getsource(desktop._ensure_native_chrome)
    assert "_apply_native_styles" in guarantee and "_install_shell" in guarantee


def test_desktop_webview_is_not_private() -> None:
    """pywebview's default is private mode: theme/language reset on every launch."""
    from dornick import desktop
    src = inspect.getsource(desktop.run)
    assert "private_mode=False" in src
    assert "storage_path" in src


def test_ear_snooze_is_restored_from_prefs() -> None:
    """The microphone click must stay muted after a shutdown too."""
    from dornick import desktop
    src = inspect.getsource(desktop._boot)
    assert "hearing_snoozed" in src
    assert "sight_snoozed" in src
