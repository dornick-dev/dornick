"""Internet tools.

Tested without going to the network: since fetching is gathered in a single
function, replacing that one is enough. The real work is in the reduction
anyway — raw HTML is the enemy of the context and every lost character here
takes the place of something the model would read.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from dornick.config import Config
from dornick.events import EventLog
from dornick.session import Session
from dornick.tools import ToolContext, ToolRegistry
from dornick.tools import web

PAGE = """<!doctype html>
<html><head>
  <title>Kripto Borsaları</title>
  <style>body { color: red }</style>
  <script>var tracker = 1;</script>
</head>
<body>
  <nav>Ana sayfa · İletişim</nav>
  <script>analytics();</script>
  <h1>24 Saatlik Hacim</h1>
  <p>Binance ilk sırada &amp; fark açık.</p>
  <ul><li>Binance</li><li>Coinbase</li></ul>
</body></html>"""


@pytest.fixture()
def ctx(tmp_path: Path) -> ToolContext:
    config = Config.load(tmp_path)
    config.ensure_dirs()
    return ToolContext(
        config=config,
        session=Session(EventLog(tmp_path / "s.jsonl"), "test"),
        cancel=asyncio.Event(),
    )


@pytest.fixture()
def registry() -> ToolRegistry:
    reg = ToolRegistry()
    web.register(reg)
    return reg


async def call(registry: ToolRegistry, name: str, ctx: ToolContext, **args):
    return await registry.get(name).handler(args, ctx)


def serving(monkeypatch: pytest.MonkeyPatch, body: str, kind: str = "text/html",
            final: str | None = None) -> list[str]:
    """A fixed reply instead of the network. The returned list holds the requested addresses."""
    asked: list[str] = []

    def fake(url: str) -> tuple[str, str, str]:
        asked.append(url)
        return body, kind, final or url

    monkeypatch.setattr(web, "_get", fake)
    return asked


# -- reduction ---------------------------------------------------------


def test_scripts_and_styles_do_not_reach_the_model() -> None:
    """190 KB of a 200 KB page is script, style and navigation."""
    text = web._readable(PAGE, "text/html")

    assert "tracker" not in text
    assert "color: red" not in text
    assert "analytics" not in text


def test_the_readable_parts_survive() -> None:
    text = web._readable(PAGE, "text/html")

    assert "24 Saatlik Hacim" in text
    assert "Binance ilk sırada & fark açık." in text   # entity resolved
    assert "Coinbase" in text


def test_blocks_do_not_run_into_each_other() -> None:
    """Looking only at the closing tag produced glued text like
    'menuBaşlık'."""
    text = web._readable(PAGE, "text/html")

    assert "İletişim24" not in text
    assert "BinanceCoinbase" not in text


def test_the_title_is_kept_once() -> None:
    """The title is inside `<head>`; it is taken before the head is
    discarded, and afterwards it must not appear a second time in the body."""
    text = web._readable(PAGE, "text/html")

    assert text.startswith("# Kripto Borsaları")
    assert text.count("Kripto Borsaları") == 1


def test_non_html_is_left_alone() -> None:
    """Trying to reduce JSON corrupts the data."""
    payload = '{"binance": {"volume": 412880}}'
    assert web._readable(payload, "application/json") == payload


# -- fetch -------------------------------------------------------------


async def test_fetch_returns_readable_text(
    registry: ToolRegistry, ctx: ToolContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    serving(monkeypatch, PAGE)
    result = await call(registry, "fetch", ctx, url="https://ornek.com/borsa")

    assert not result.is_error
    assert "24 Saatlik Hacim" in result.content
    assert "tracker" not in result.content


async def test_raw_skips_the_reduction(
    registry: ToolRegistry, ctx: ToolContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If it is going to write a selector, the model needs the raw HTML."""
    serving(monkeypatch, PAGE)
    result = await call(registry, "fetch", ctx, url="https://ornek.com", raw=True)

    assert "<h1>" in result.content


async def test_a_redirect_is_reported(
    registry: ToolRegistry, ctx: ToolContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The model must know which page it read."""
    serving(monkeypatch, PAGE, final="https://ornek.com/tr/borsa")
    result = await call(registry, "fetch", ctx, url="https://ornek.com/borsa")

    assert "→ https://ornek.com/tr/borsa" in result.content
    assert result.detail["url"] == "https://ornek.com/tr/borsa"


@pytest.mark.parametrize(
    "url",
    ["file:///C:/Windows/win.ini", "/etc/passwd", "javascript:alert(1)", "ftp://x/y", ""],
)
async def test_only_web_addresses_are_fetched(
    registry: ToolRegistry, ctx: ToolContext, url: str
) -> None:
    """`fetch` must not be a road for reading files: read_file passes
    through the permission gate, this does not."""
    result = await call(registry, "fetch", ctx, url=url)

    assert result.is_error
    assert "read_file" in result.content


async def test_a_huge_page_is_clipped(
    registry: ToolRegistry, ctx: ToolContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    serving(monkeypatch, "x" * (web.MAX_TEXT * 2), kind="text/plain")
    result = await call(registry, "fetch", ctx, url="https://ornek.com")

    assert "kırpıldı" in result.content
    assert len(result.content) < web.MAX_TEXT + 500


async def test_an_http_error_is_readable(
    registry: ToolRegistry, ctx: ToolContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    import urllib.error

    def boom(url: str):
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)  # type: ignore[arg-type]

    monkeypatch.setattr(web, "_get", boom)
    result = await call(registry, "fetch", ctx, url="https://ornek.com/yok")

    assert result.is_error
    assert "404" in result.content


# -- search ------------------------------------------------------------

RESULTS = """
<div class="result">
  <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fbir.com%2Fa&amp;rut=x">
    <b>Bir</b>inci sonuç
  </a>
  <a class="result__snippet" href="#">Birinci &amp; özet</a>
</div>
<div class="result">
  <a class="result__a" href="https://iki.com/b">İkinci sonuç</a>
  <a class="result__snippet" href="#">İkinci özet</a>
</div>
"""


async def test_search_lists_title_link_and_snippet(
    registry: ToolRegistry, ctx: ToolContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    serving(monkeypatch, RESULTS)
    result = await call(registry, "search", ctx, query="deneme")

    assert not result.is_error
    assert "Birinci sonuç" in result.content
    assert "Birinci & özet" in result.content
    assert "İkinci sonuç" in result.content


async def test_the_redirect_wrapper_is_unwrapped(
    registry: ToolRegistry, ctx: ToolContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A wrapped address is unreadable on the model's screen and, when given
    to `fetch`, means an extra hop."""
    serving(monkeypatch, RESULTS)
    result = await call(registry, "search", ctx, query="deneme")

    assert "https://bir.com/a" in result.content
    assert "duckduckgo.com/l/" not in result.content


async def test_the_limit_is_respected(
    registry: ToolRegistry, ctx: ToolContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    serving(monkeypatch, RESULTS)
    result = await call(registry, "search", ctx, query="deneme", limit=1)

    assert result.detail["results"] == 1


async def test_no_results_is_not_an_error(
    registry: ToolRegistry, ctx: ToolContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Finding nothing is not an error; returning an error pushes the model
    into needless 'fix-up' turns."""
    serving(monkeypatch, "<html><body>hiç sonuç yok</body></html>")
    result = await call(registry, "search", ctx, query="hiçbir şey")

    assert not result.is_error
    assert "bulunamadı" in result.content


async def test_an_empty_query_is_refused(registry: ToolRegistry, ctx: ToolContext) -> None:
    assert (await call(registry, "search", ctx, query="   ")).is_error


# -- fallback source ---------------------------------------------------

LITE_PAGE = """
<table>
  <tr><td>
    <a rel="nofollow" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fbir.com%2Fa" class='result-link'>Lite Birinci</a>
  </td></tr>
  <tr><td class='result-snippet'>Lite özet</td></tr>
  <tr><td>
    <a rel="nofollow" href="https://iki.com/b" class='result-link'>Lite İkinci</a>
  </td></tr>
</table>
"""


async def test_the_lite_fallback_catches_a_broken_primary(
    registry: ToolRegistry, ctx: ToolContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When html.duckduckgo breaks the search must not silently return
    empty; the fallback source must be tried."""
    import urllib.error

    asked: list[str] = []

    def fake(url: str) -> tuple[str, str, str]:
        asked.append(url)
        if "html.duckduckgo" in url:
            raise urllib.error.URLError("bağlantı reddedildi")
        return LITE_PAGE, "text/html", url

    monkeypatch.setattr(web, "_get", fake)
    result = await call(registry, "search", ctx, query="deneme")

    assert not result.is_error
    assert "Lite Birinci" in result.content
    assert "https://bir.com/a" in result.content        # redirector resolved
    assert "Lite özet" in result.content
    assert any("lite.duckduckgo" in u for u in asked)
    assert result.detail["source"] == web.LITE_URL


async def test_a_changed_format_is_an_error_not_silence(
    registry: ToolRegistry, ctx: ToolContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The page arrived but the pattern did not match: this is not 'no
    results' but 'the source changed its format' — the agent must know the
    difference."""
    serving(monkeypatch, "<html><body><div>bambaşka bir düzen</div></body></html>")
    result = await call(registry, "search", ctx, query="deneme")

    assert result.is_error
    assert "biçim değiştirmiş" in result.content


async def test_a_format_change_still_tries_the_fallback(
    registry: ToolRegistry, ctx: ToolContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake(url: str) -> tuple[str, str, str]:
        if "html.duckduckgo" in url:
            return "<html><body><div>tanınmaz düzen</div></body></html>", "text/html", url
        return LITE_PAGE, "text/html", url

    monkeypatch.setattr(web, "_get", fake)
    result = await call(registry, "search", ctx, query="deneme")

    assert not result.is_error
    assert "Lite Birinci" in result.content


async def test_network_failure_on_both_sources_is_explicit(
    registry: ToolRegistry, ctx: ToolContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    import urllib.error

    def boom(url: str):
        raise urllib.error.URLError("ağ kapalı")

    monkeypatch.setattr(web, "_get", boom)
    result = await call(registry, "search", ctx, query="deneme")

    assert result.is_error
    assert "ağ hatası" in result.content
    assert "html.duckduckgo" in result.content and "lite.duckduckgo" in result.content


def test_the_lite_parser_reads_the_table_layout() -> None:
    hits = web._lite_results(LITE_PAGE, 5)

    assert hits[0] == ("Lite Birinci", "https://bir.com/a", "Lite özet")
    assert hits[1][1] == "https://iki.com/b"


# -- registration ------------------------------------------------------


def test_reading_the_web_is_not_a_mutation(registry: ToolRegistry) -> None:
    """Reading from the network is like reading a local file. Something that
    **sends data** outward would enter the approval gate."""
    assert not registry.get("fetch").mutates
    assert not registry.get("search").mutates
