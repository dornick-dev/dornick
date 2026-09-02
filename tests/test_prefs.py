"""Kapanıştaki tercihler sıfırlanmasın."""

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
    }, area=(0, 0, 1920, 1080))
    assert args["width"] == 1200
    assert args["x"] == 40


def test_maximized_omits_xy() -> None:
    """Büyütülmüş kayıt + eski x/y create_window'a konum vermesin."""
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
    """Tam ekran boyu ama (126,126) — bozuk; büyütülmüş aç."""
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
    """Kaymış büyütme (pencere near-full ama (100,100)'de) kendiliğinden
    oturmalı — kullanıcı elle küçültüp geri açmak zorunda kalmasın.

    Canlı yara (31.08): açılışta sol/üstten masaüstü sızıyor, içerik solda
    kırpık geliyordu. Üç bekçi: açılış sonrası nöbet (_geometry_watch),
    tepsiden/uyandırmadan gösterince bakış ve kabuğun zoom kilidinde
    kaymışlık koruması.
    """
    from dornick import desktop

    boot = inspect.getsource(desktop._titlebar_boot)
    assert "_geometry_watch" in boot
    heal = inspect.getsource(desktop._heal_geometry)
    assert "offset_fullscreen" in heal
    assert "IsZoomed" in heal
    assert "_monitor_work_area" in heal
    # Zoom kilidi yalnız pencere gerçekten work-area'ya oturuyorsa: kaymış
    # zoom'da ekran koordinatlı kilit içeriği eksiye kaydırıyordu.
    shell = inspect.getsource(desktop._install_shell_on)
    assert "rcWork.left) <= 64" in shell
    # Tepsiden / uyandırmadan görünür olunca da bak.
    run_src = inspect.getsource(desktop.run)
    assert "_heal_geometry" in run_src
    assert "_heal_geometry" in inspect.getsource(desktop._wake)


def test_single_strip_survives_a_hidden_start() -> None:
    """Tek şerit, pencere GİZLİ doğsa da kurulur.

    Canlı yara (02.09): uygulama tepsiye açıldığında pencere gizli doğuyor;
    `_dornick_windows()` yalnız GÖRÜNÜR pencereleri saydığı için stiller de
    kabuk da hiç kurulmuyordu ve pencere sonradan gösterildiğinde Windows'un
    kendi başlık çubuğu uygulamanın şeridinin ÜSTÜNDE kalıyordu — üst üste
    iki şerit. İki savunma: kurulum gizli pencereyi de hedefler, ve gösterme
    yolları kurulumu garanti eder.
    """
    from dornick import desktop

    # Kurulumlar gizli pencereyi de hedefliyor.
    assert "gizli_de=True" in inspect.getsource(desktop._apply_native_styles)
    assert "gizli_de=True" in inspect.getsource(desktop._install_shell)

    # Gösterildiğinde garanti: hem tepsi/uyandırma yolu hem yardımcı.
    run_src = inspect.getsource(desktop.run)
    assert "_ensure_native_chrome" in run_src
    garanti = inspect.getsource(desktop._ensure_native_chrome)
    assert "_apply_native_styles" in garanti and "_install_shell" in garanti


def test_desktop_webview_is_not_private() -> None:
    """pywebview varsayılanı gizli kip: tema/dil her açılışta sıfırlanıyordu."""
    from dornick import desktop
    src = inspect.getsource(desktop.run)
    assert "private_mode=False" in src
    assert "storage_path" in src


def test_ear_snooze_is_restored_from_prefs() -> None:
    """Mikrofon tıklaması kapanıştan sonra da susturulmuş kalsın."""
    from dornick import desktop
    src = inspect.getsource(desktop._boot)
    assert "hearing_snoozed" in src
    assert "sight_snoozed" in src
