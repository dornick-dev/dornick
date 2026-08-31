"""Kapanıştaki tercihler — tema/dil WebView'de, geri kalanı burada.

pywebview varsayılanı gizli kip: localStorage her açılışta boşalıyordu.
Pencere kutusu ve duyu susturması orada değil; `prefs.json` tutuyor.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

NAME = "prefs.json"
MIN_W, MIN_H = 900, 600
# Neredeyse çalışma alanı boyunda ama köşeden kaymış kutu = bozuk kayıt.
NEAR_FULL = 0.95
OFFSET_SLACK = 32


def _path(state_dir: Any) -> Path:
    return Path(state_dir) / NAME


def load(state_dir: Any) -> dict[str, Any]:
    """Kayıt yoksa / bozuksa boş tercihler."""
    path = _path(state_dir)
    raw: dict[str, Any] = {}
    if path.exists():
        try:
            got = json.loads(path.read_text(encoding="utf-8-sig"))
            if isinstance(got, dict):
                raw = got
        except (OSError, json.JSONDecodeError):
            raw = {}
    win = raw.get("window") if isinstance(raw.get("window"), dict) else {}
    return {
        "window": dict(win),
        "hearing_snoozed": bool(raw.get("hearing_snoozed")),
        "sight_snoozed": bool(raw.get("sight_snoozed")),
    }


def patch(state_dir: Any, **fields: Any) -> None:
    """Kısmi yama. `window` alt sözlüğü birleşir, sıfırlanmaz."""
    data = load(state_dir)
    if "window" in fields:
        extra = fields.pop("window")
        if isinstance(extra, dict):
            data["window"] = {**data["window"], **extra}
    data.update(fields)
    path = _path(state_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp.replace(path)


def work_area() -> tuple[int, int, int, int] | None:
    """Görev çubuğu hariç alan (x, y, genişlik, yükseklik); yoksa None."""
    if os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        rect = wintypes.RECT()
        if not ctypes.windll.user32.SystemParametersInfoW(
            0x0030, 0, ctypes.byref(rect), 0
        ):
            return None
        return (rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top)
    except Exception:
        return None


def offset_fullscreen(
    x: int, y: int, w: int, h: int,
    area: tuple[int, int, int, int] | None = None,
) -> bool:
    """Neredeyse tam ekran boyu ama köşeden kaymış — bozuk büyütme kaydı."""
    area = area if area is not None else work_area()
    if not area or w < MIN_W or h < MIN_H:
        return False
    ax, ay, aw, ah = area
    if w < aw * NEAR_FULL or h < ah * NEAR_FULL:
        return False
    return abs(x - ax) > OFFSET_SLACK or abs(y - ay) > OFFSET_SLACK


def window_args(
    data: dict[str, Any],
    area: tuple[int, int, int, int] | None = None,
) -> dict[str, Any]:
    """`webview.create_window` için kutu. Geçersiz kayıt → boş (varsayılan).

    Büyütülmüş kayıtta x/y VERİLMEZ: çerçevesiz pencerede maximized+offset
    birlikte gelince HWND (126,126) gibi kayıp açılıyordu; küçült/geri aç
    düzeltiyordu. Restore boyutu (width/height) kalabilir.
    """
    win = data.get("window") or {}
    out: dict[str, Any] = {}
    try:
        w, h = int(win.get("width") or 0), int(win.get("height") or 0)
    except (TypeError, ValueError):
        w, h = 0, 0
    x = y = None
    try:
        raw_x, raw_y = win.get("x"), win.get("y")
        if raw_x is not None and raw_y is not None:
            x, y = int(raw_x), int(raw_y)
    except (TypeError, ValueError):
        x = y = None

    if area is None:
        area = work_area()
    want_max = bool(win.get("maximized"))
    if x is not None and y is not None and offset_fullscreen(x, y, w, h, area):
        want_max = True

    if want_max:
        out["maximized"] = True
        if w >= MIN_W and h >= MIN_H and area:
            ax, ay, aw, ah = area
            # Restore kutusu tam ekran boyundaysa varsayılana bırak.
            if w < aw * NEAR_FULL or h < ah * NEAR_FULL:
                out["width"], out["height"] = w, h
        elif w >= MIN_W and h >= MIN_H:
            out["width"], out["height"] = w, h
        return out

    if w >= MIN_W and h >= MIN_H:
        if area is not None:
            ax, ay, aw, ah = area
            w = min(w, aw)
            h = min(h, ah)
            if x is not None and y is not None:
                x = max(ax, min(x, ax + max(aw - w, 0)))
                y = max(ay, min(y, ay + max(ah - h, 0)))
        out["width"], out["height"] = w, h
        if x is not None and y is not None:
            out["x"], out["y"] = x, y
    return out


def tell(cb: Any, off: bool) -> None:
    """Susturma kancası: yoksa / patlarsa sessiz."""
    if callable(cb):
        try:
            cb(bool(off))
        except Exception:
            pass
