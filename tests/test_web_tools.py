"""İnternet araçları.

Ağa çıkmadan test ediliyor: getirme tek bir fonksiyonda toplandığı için
onu değiştirmek yetiyor. Asıl iş zaten indirgemede — ham HTML bağlamın
düşmanı ve buradaki her kayıp karakter modelin okuyacağı bir şeyin yerini
alıyor.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from neocp.config import Config
from neocp.events import EventLog
from neocp.session import Session
from neocp.tools import ToolContext, ToolRegistry
from neocp.tools import web

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
    """Ağ yerine sabit bir cevap. Dönen liste istenen adresleri tutuyor."""
    asked: list[str] = []

    def fake(url: str) -> tuple[str, str, str]:
        asked.append(url)
        return body, kind, final or url

    monkeypatch.setattr(web, "_get", fake)
    return asked


# -- indirgeme ---------------------------------------------------------


def test_scripts_and_styles_do_not_reach_the_model() -> None:
    """200 KB'lık bir sayfanın 190 KB'ı betik, stil ve gezinme."""
    text = web._readable(PAGE, "text/html")

    assert "tracker" not in text
    assert "color: red" not in text
    assert "analytics" not in text


def test_the_readable_parts_survive() -> None:
    text = web._readable(PAGE, "text/html")

    assert "24 Saatlik Hacim" in text
    assert "Binance ilk sırada & fark açık." in text   # varlık çözülmüş
    assert "Coinbase" in text


def test_blocks_do_not_run_into_each_other() -> None:
    """Yalnızca kapanış etiketine bakmak 'menuBaşlık' gibi yapışmış metin
    üretiyordu."""
    text = web._readable(PAGE, "text/html")

    assert "İletişim24" not in text
    assert "BinanceCoinbase" not in text


def test_the_title_is_kept_once() -> None:
    """Başlık `<head>` içinde; head atılmadan önce alınıyor, sonra da
    gövdede ikinci kez görünmemeli."""
    text = web._readable(PAGE, "text/html")

    assert text.startswith("# Kripto Borsaları")
    assert text.count("Kripto Borsaları") == 1


def test_non_html_is_left_alone() -> None:
    """JSON'u indirgemeye kalkmak veriyi bozar."""
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
    """Seçici yazacaksa modelin ham HTML'e ihtiyacı var."""
    serving(monkeypatch, PAGE)
    result = await call(registry, "fetch", ctx, url="https://ornek.com", raw=True)

    assert "<h1>" in result.content


async def test_a_redirect_is_reported(
    registry: ToolRegistry, ctx: ToolContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Model hangi sayfayı okuduğunu bilmeli."""
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
    """`fetch` bir dosya okuma yolu olmamalı: read_file izin kapısından
    geçiyor, bu geçmiyor."""
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
    """Sarmalanmış adres modelin ekranında okunmuyor ve `fetch`e verilince
    fazladan bir atlama demek."""
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
    """Bulamamak bir hata değil; hata döndürmek modeli gereksiz yere
    'düzeltme' turlarına sokuyor."""
    serving(monkeypatch, "<html><body>hiç sonuç yok</body></html>")
    result = await call(registry, "search", ctx, query="hiçbir şey")

    assert not result.is_error
    assert "bulunamadı" in result.content


async def test_an_empty_query_is_refused(registry: ToolRegistry, ctx: ToolContext) -> None:
    assert (await call(registry, "search", ctx, query="   ")).is_error


# -- kayıt -------------------------------------------------------------


def test_reading_the_web_is_not_a_mutation(registry: ToolRegistry) -> None:
    """Ağdan okumak yerel dosya okumak gibi. Dışarı **veri gönderen** bir şey
    olsaydı onay kapısına girerdi."""
    assert not registry.get("fetch").mutates
    assert not registry.get("search").mutates
