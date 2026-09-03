"""Drawing on screen.

Some answers get lost when told in prose. "Tank level 62%" is a number;
a line sitting on a tank silhouette reads at a glance. Maps, layouts,
comparisons, timelines — all the same.

The agent writes the page itself. This is not a template library:
defining fifty ready-made chart types and saying "pick one of these"
blocks exactly what is wanted — a drawing specific to that job. The
agent can write HTML/SVG; what is done here is giving it a surface and
a frame.

Security is two-layered:

    here       the page is wrapped in a strict CSP: no network request,
               no external resource. Only inline style, inline script
               and embedded (data:) images.
    in the UI  it opens in an isolated frame (`sandbox="allow-scripts"`,
               no `allow-same-origin`): the page cannot reach the
               program's DOM, its cookies or the `/api` endpoints.

Both are necessary. A script written by the agent bypassing its own
permission gate would be the most expensive bug in this program.
"""

from __future__ import annotations

import re
from pathlib import Path

# The folder inside the workshop where drawings live.
FOLDER = "gorseller"

# File name: derived from the title, but the title is free text, not a file name.
_SLUG = re.compile(r"[^a-z0-9]+")

_TR = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")

# The page's frame. `default-src 'none'` shuts everything down; then only
# what is needed is opened one by one. An external font, a CDN script or a
# tracking pixel never loads under any condition.
SHELL = """<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; \
style-src 'unsafe-inline'; script-src 'unsafe-inline'; img-src data:; font-src data:">
<title>{title}</title>
<style>
  /* The program's own palette: the drawing sits inside the UI, not like
     a foreign white page floating above it. */
  :root {{
    --bg: #050a0f; --ink: #dceefc; --dim: #7fa0c0; --faint: #4b6684;
    --cyan: #4fe3ff; --mint: #5ce6a4; --amber: #ffc857; --rose: #ff7a90;
    --violet: #b39cff; --line: #4fe3ff22;
  }}
  * {{ box-sizing: border-box; }}
  html, body {{ margin: 0; height: 100%; }}
  body {{
    background: var(--bg); color: var(--ink);
    font: 14px/1.6 "Segoe UI Variable Text", -apple-system, system-ui, sans-serif;
    padding: 18px;
  }}
  h1, h2, h3 {{ font-weight: 300; letter-spacing: .01em; margin: 0 0 12px; }}
  h1 {{ font-size: 20px; }}
  svg {{ max-width: 100%; height: auto; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th, td {{ padding: 6px 10px; text-align: left; border-bottom: 1px solid var(--line); }}
  th {{ font: 10.5px "Cascadia Code", ui-monospace, monospace;
        letter-spacing: .16em; text-transform: uppercase; color: var(--cyan); }}
  .dim {{ color: var(--dim); }}
  .faint {{ color: var(--faint); }}
</style>
</head>
<body>
{body}
</body>
</html>
"""


def folder(sandbox_root: Path) -> Path:
    return Path(sandbox_root) / FOLDER


def slug(title: str, fallback: str = "cizim") -> str:
    """File name from the title. Turkish letters are simplified, the rest is dashed."""
    plain = (title or "").translate(_TR).lower()
    name = _SLUG.sub("-", plain).strip("-")
    return (name or fallback)[:48]


def wrap(title: str, body: str) -> str:
    """Seats the body the agent wrote into the frame.

    If the agent wrote a full document (starting with `<!DOCTYPE` or
    `<html`) it is left alone: it built its own frame. In that case the
    CSP is not added either unless it wrote one itself — forcing it would
    silently break a working page. The isolated frame is the second layer
    anyway.
    """
    text = (body or "").strip()
    if text[:200].lstrip().lower().startswith(("<!doctype", "<html")):
        return text
    return SHELL.format(title=_escape(title or "çizim"), body=text)


def _escape(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;")
                .replace(">", "&gt;").replace('"', "&quot;"))


def save(sandbox_root: Path, title: str, body: str) -> Path:
    """Writes the drawing into the workshop and returns its path."""
    root = folder(sandbox_root)
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{slug(title)}.html"
    path.write_text(wrap(title, body), encoding="utf-8")
    return path
