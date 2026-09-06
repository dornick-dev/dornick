"""The wire speaks English: routes, SSE event names and slash commands.

`test_english_names.py` guards the names in the code; this file guards the
names that leave the process — every `/api/...` route the server registers
and the browser calls, every SSE event type the browser switches on, and
the slash commands typed into the composer. A Turkish word in any of them
fails here, before it ships. The Turkish slash names are allowed in ONE
place, the alias table, and only as keys that point at an English command.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "src" / "dornick" / "web"
STATIC = WEB / "static"
SERVER = (WEB / "server.py").read_text(encoding="utf-8")
COMMAND_JS = (STATIC / "command.js").read_text(encoding="utf-8")
APP_JS = (STATIC / "app.js").read_text(encoding="utf-8")

# Route segments and event names the wire used until 1.5.3, plus the
# ordinary Turkish words a new route would most likely be made of. Whole
# segments only: `sira` is caught, `session` is not.
TURKISH = frozenset("""
indir bolgeler bolge degisiklikler degisiklik fark geri disari ac gorevler gorev devam dokum durdur
iptal rapor gozat guncelle guncelleme kimlik klasor olustur mizac surum uyku uyu kafein gece geceler
tanima dil butce yol ust ad ara sonra sira siralar oturum parcalar hedef metin ozet olay olaylar
bekleme araya karakter fiyat basinc esik borc ritim saatler bitti kayitlar yedek silinen durum
sonraki son yeni eski hata uyari engel dosya klasorler arac zaman yoktu atlandi gerialinabilir yapilan
adimlar tur kosan kosuyor basladi arka durdurulabilir surdurulebilir komut cumleler kelime kanit
sinir taban ulasilan kaldirac eksenler soguk sicak dunya hedefler yama hazir simdi sebep kip deneme
toplam saniye detay asama yuzde indirilen mevcut indirme boyut tahmin kirilim kullanim harcanan
gecmis yetki uygulamalar ayarlar sifirla yorgun uyuma yardim
""".split())


def _segments(path: str) -> list[str]:
    return [s for s in re.split(r"[/_\-]", path) if s]


def _turkish_in(path: str) -> set[str]:
    return {s for s in _segments(path) if s.lower() in TURKISH}


# -- routes ---------------------------------------------------------------


def _routes_in(source: str) -> set[str]:
    found = set(re.findall(r'"(/api/[A-Za-z0-9_/\-]*)', source))
    found |= set(re.findall(r'startswith\("(/[A-Za-z0-9_/\-]+)"\)', source))
    return {r for r in found if r not in ("/api/", "/")}


def test_every_registered_route_is_english() -> None:
    """The dispatcher in server.py is the registry: every `"/api/..."` it
    compares against, and every prefix it `startswith`-matches."""
    routes = _routes_in(SERVER)
    assert len(routes) > 60, "the route scan found too little — pattern gone stale?"
    bad = {r: _turkish_in(r) for r in routes if _turkish_in(r)}
    assert not bad, f"Turkish route segments: {bad}"


def test_every_route_the_browser_calls_is_english() -> None:
    """The static JS (and the desktop bridge's docstrings) must not keep an
    old address alive: the server changed outright, so would the 404."""
    bad: dict[str, set[str]] = {}
    for path in list(STATIC.glob("*.js")) + [ROOT / "src" / "dornick" / "desktop.py"]:
        for route in _routes_in(path.read_text(encoding="utf-8")):
            if _turkish_in(route):
                bad[f"{path.name}:{route}"] = _turkish_in(route)
    assert not bad, f"Turkish route segments in consumers: {bad}"


def test_the_report_page_prefix_is_english() -> None:
    assert '"/task-report/"' in SERVER
    assert "/gorev-rapor/" not in SERVER


# -- SSE event names ------------------------------------------------------


def test_the_sse_event_names_the_browser_switches_on_are_english() -> None:
    """The `handle()` dispatcher in app.js: `case "<type>":` — plus the
    event-type strings the server-side emitters publish."""
    cases = set(re.findall(r'case "([a-z_.]+)":', APP_JS))
    assert {"night", "recognition", "update", "price", "waiting", "interject"} <= cases
    bad = {c for c in cases if _turkish_in(c)}
    assert not bad, f"Turkish SSE event names in app.js: {sorted(bad)}"

    emitted: set[str] = set()
    for path in (ROOT / "src" / "dornick").rglob("*.py"):
        emitted |= set(re.findall(r'"type": "([a-z_.]+)"', path.read_text(encoding="utf-8")))
    bad = {e for e in emitted if _turkish_in(e)}
    assert not bad, f"Turkish SSE event names emitted by Python: {sorted(bad)}"


# -- slash commands -------------------------------------------------------


def _book() -> dict[str, str]:
    block = re.search(r"const BOOK = \[(.*?)\n  \];", COMMAND_JS, re.S)
    assert block, "command book not found — pattern gone stale?"
    return dict(re.findall(r'\{\s*name:\s*"([\w-]+)",\s*what:\s*"([^"]+)"', block.group(1)))


def _aliases() -> dict[str, str]:
    block = re.search(r"const ALIASES = \{(.*?)\n  \};", COMMAND_JS, re.S)
    assert block, "alias table not found — pattern gone stale?"
    return dict(re.findall(r'(\w+):\s*"(\w+)"', block.group(1)))


CANONICAL = {"new", "history", "model", "mode", "tasks", "apps", "artifact",
             "settings", "compact", "sleep", "nosleep", "tired", "stop", "help"}


def test_the_slash_commands_have_english_canonical_names() -> None:
    book = _book()
    assert set(book) == CANONICAL, sorted(book)
    bad = {name for name in book if name.lower() in TURKISH}
    assert not bad, f"Turkish command names in the book: {sorted(bad)}"


def test_the_old_turkish_names_live_only_in_the_alias_table() -> None:
    """Every old name maps to a command that exists; no old name is a
    command of its own; the table is the single place they appear."""
    book, aliases = _book(), _aliases()
    assert aliases == {
        "yeni": "new", "gecmis": "history", "yetki": "mode", "gorevler": "tasks",
        "uygulamalar": "apps", "ayarlar": "settings", "sifirla": "compact",
        "uyu": "sleep", "uyuma": "nosleep", "yorgun": "tired", "durdur": "stop",
        "yardim": "help",
    }
    assert set(aliases.values()) <= set(book)
    assert not (set(aliases) & set(book))
    # The menu resolves an alias through the table, not through a second list.
    assert "aliasesOf(k.name).some((old) => old.includes(want))" in COMMAND_JS
    assert "Command = (() =>" in COMMAND_JS and "ALIASES" in COMMAND_JS.split("return {")[-1]


def test_the_tooltips_name_the_commands_that_exist() -> None:
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    lang = (STATIC / "lang.js").read_text(encoding="utf-8")
    for text in (html, lang):
        assert "/sleep" in text and "/nosleep" in text
        assert "/uyu " not in text and "/uyuma " not in text
