"""Kapanıştaki tercihler — tema/dil WebView'de, geri kalanı burada.

pywebview varsayılanı gizli kip: localStorage her açılışta boşalıyordu.
Pencere kutusu ve duyu susturması orada değil; `prefs.json` tutuyor.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

NAME = "prefs.json"
MIN_W, MIN_H = 900, 600


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


def window_args(data: dict[str, Any]) -> dict[str, Any]:
    """`webview.create_window` için kutu. Geçersiz kayıt → boş (varsayılan)."""
    win = data.get("window") or {}
    out: dict[str, Any] = {}
    try:
        w, h = int(win.get("width") or 0), int(win.get("height") or 0)
    except (TypeError, ValueError):
        w, h = 0, 0
    if w >= MIN_W and h >= MIN_H:
        out["width"], out["height"] = w, h
    try:
        x, y = win.get("x"), win.get("y")
        if x is not None and y is not None:
            out["x"], out["y"] = int(x), int(y)
    except (TypeError, ValueError):
        pass
    if win.get("maximized"):
        out["maximized"] = True
    return out


def tell(cb: Any, off: bool) -> None:
    """Susturma kancası: yoksa / patlarsa sessiz."""
    if callable(cb):
        try:
            cb(bool(off))
        except Exception:
            pass
