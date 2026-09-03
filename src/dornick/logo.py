"""Dornick's logo — single source.

Hearth identity: a "net-woven n" on a dark-charcoal rounded square — four
chalk knots, an amber top knot. The same mark as the brand SVG in the top
strip; window icon, taskbar, tray and tab all use the SAME drawing.

Drawn in code instead of a vector file: in the packaged app the thing that
breaks most often is the asset path — if the drawing is code the icon is
never blank. PIL is already required for the tray; if it is missing the
caller gives up silently.
"""

from __future__ import annotations

from pathlib import Path

# Hearth colours (same token family as app.css).
_GROUND = (27, 24, 20)         # --panel: dark charcoal
_EDGE = (62, 55, 44)           # thin edge — stays visible on a dark taskbar too
_STROKE = (239, 232, 220)      # chalk: the thread of the n and the lower knots
_TOP = (240, 160, 32)          # amber: top knot (--cyan)

# Geometry of the mark on a 32-unit grid — identical to the brand SVG in
# index.html: a "d" out of net weave (knot-d). Stem + bowl, three chalk
# knot squares, an amber knot at the top.
_STEM = ((21.5, 7.0), (21.5, 23.5))
_BOWL = (9.7, 13.3, 21.5, 26.3)          # rounded-corner frame
_BOWL_R = 2.8
_KNOTS = [(7.4, 11.2), (7.4, 21.9), (19.3, 24.1)]   # 4.4-unit squares
_TOP_DOT = (21.5, 5.6, 3.3)              # cx, cy, r

# When the drawing changes the packaged .ico should refresh itself: version
# sentinel. (Name kept: winicon.py imports it.)
_SURUM = "dugum-1"


def draw(size: int):
    """size×size logo (PIL Image): dark rounded square + woven n.

    We supersample 4× and shrink: edges stay clean even at 16px.
    """
    from PIL import Image, ImageDraw

    s = size * 4
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    u = s / 32.0                 # 32-unit grid → pixels

    # Ground: rounded square tile. A tile instead of a transparent ground:
    # the same readable identity on a light taskbar and in the dark theme.
    margin = s * 0.02
    d.rounded_rectangle((margin, margin, s - margin, s - margin), radius=s * 0.21,
                        fill=(*_GROUND, 255), outline=(*_EDGE, 255),
                        width=max(1, int(s * 0.012)))

    # The d thread: stem + rounded-corner bowl (same weight as the SVG path).
    w = max(2, int(3.6 * u))
    (x1, y1), (x2, y2) = _STEM
    d.line([(x1 * u, y1 * u), (x2 * u, y2 * u)], fill=(*_STROKE, 255), width=w)
    r = w / 2
    for x, y in _STEM:
        d.ellipse((x * u - r, y * u - r, x * u + r, y * u + r), fill=(*_STROKE, 255))
    kx1, ky1, kx2, ky2 = (v * u for v in _BOWL)
    d.rounded_rectangle((kx1, ky1, kx2, ky2), radius=_BOWL_R * u,
                        outline=(*_STROKE, 255), width=w)

    # Knot squares: chalk, rounded.
    for x, y in _KNOTS:
        d.rounded_rectangle((x * u, y * u, (x + 4.4) * u, (y + 4.4) * u),
                            radius=1.2 * u, fill=(*_STROKE, 255))

    # Top knot: amber.
    cx, cy, cr = _TOP_DOT
    d.ellipse(((cx - cr) * u, (cy - cr) * u, (cx + cr) * u, (cy + cr) * u),
              fill=(*_TOP, 255))

    return img.resize((size, size), Image.LANCZOS)


def ensure_ico(path: Path) -> bool:
    """Produces the multi-size .ico file (if missing). Returns success."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        # Version sentinel: if the drawing changed (like the hearth migration)
        # the old .ico must not linger silently — regenerate. The side file
        # sits next to the .ico.
        sentinel = path.with_suffix(".ico.surum")
        if path.exists():
            try:
                if sentinel.read_text(encoding="utf-8").strip() == _SURUM:
                    return True
            except OSError:
                pass
        base = draw(256)
        base.save(path, format="ICO",
                  sizes=[(16, 16), (20, 20), (24, 24), (32, 32),
                         (40, 40), (48, 48), (64, 64), (128, 128), (256, 256)])
        try:
            sentinel.write_text(_SURUM, encoding="utf-8")
        except OSError:
            pass
        return True
    except Exception:
        return False


def ico_path() -> Path:
    """Icon path inside the package (generated if needed)."""
    path = Path(__file__).parent / "assets" / "dornick.ico"
    ensure_ico(path)
    return path


def ensure_png(path: Path, size: int = 256) -> bool:
    """PNG for the Windows toast and the tab. ICO is not accepted as a WinRT src."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        sentinel = path.with_suffix(".png.surum")
        if path.exists():
            try:
                if sentinel.read_text(encoding="utf-8").strip() == _SURUM:
                    return True
            except OSError:
                pass
        draw(size).save(path, format="PNG")
        try:
            sentinel.write_text(_SURUM, encoding="utf-8")
        except OSError:
            pass
        return True
    except Exception:
        return False


def png_path(size: int = 256) -> Path:
    """PNG path inside the package (generated if needed)."""
    path = Path(__file__).parent / "assets" / "dornick.png"
    ensure_png(path, size)
    return path
