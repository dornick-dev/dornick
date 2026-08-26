"""İnternet araçları.

Bunlar olmadan ajan her araştırma isteğinde kabuğa düşüp `Invoke-RestMethod`
ya da `curl` yazmak zorunda kalıyordu: her seferinde ayrı bir izin sorusu,
her seferinde ham HTML, her seferinde farklı bir hata biçimi. Tipli iki araç
bunu bitiriyor.

İki tanesi yeter:

    fetch    bir adresi getirir; HTML ise okunabilir metne indirger
    search   arama yapar; anahtar gerektirmeyen bir uç kullanır

Metne indirgeme burada yapılıyor çünkü ham HTML bağlamın düşmanı: 200 KB'lık
bir sayfanın 190 KB'ı betik, stil ve gezinme. Modelin okuması gereken şey
kalan 10 KB.

Ağ erişimi yerel dosya okumak gibi ele alınıyor: sistem durumunu
değiştirmiyor, o yüzden `mutates=False`. Dışarı **veri gönderen** bir şey
olsaydı (form gönderimi, POST) o zaman onay kapısına girerdi.
"""

from __future__ import annotations

import asyncio
import gzip
import html
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from .base import ToolContext, ToolRegistry, ToolResult, object_schema

TIMEOUT = 20.0
MAX_BYTES = 4 * 1024 * 1024
MAX_TEXT = 40_000
MAX_RESULTS = 10

# Bazı siteler tanımadığı istemciye 403 döndürüyor. Kimliği gizlemiyoruz,
# yalnızca tanınabilir bir ad veriyoruz.
USER_AGENT = "neo/1.0 (+local agent; https://github.com/)"

# Gövdesi tamamen atılan öğeler: betik ve stil sayfanın anlamına hiçbir şey
# katmıyor, ama karakter sayısının çoğunu onlar tutuyor.
_DROPPED = re.compile(
    r"<(script|style|noscript|template|svg|iframe|head)\b[^>]*>.*?</\1>", re.S | re.I
)
_TAG = re.compile(r"<[^>]+>")
# Blok öğeleri satır sonuna çevriliyor — hem açılışı hem kapanışı. Yalnızca
# kapanışa bakmak "menuBaşlık" gibi birbirine yapışmış metin üretiyordu.
_BREAK = re.compile(
    r"</?(p|div|section|article|aside|nav|header|footer|main|li|ul|ol|"
    r"tr|td|th|table|h[1-6]|blockquote|pre|hr|br)\b[^>]*>",
    re.I,
)
_BLANK = re.compile(r"\n{3,}")
_SPACES = re.compile(r"[ \t]{2,}")
_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.S | re.I)

# DuckDuckGo'nun betiksiz sürümü: anahtar istemiyor ve sonuçlar düz HTML.
SEARCH_URL = "https://html.duckduckgo.com/html/"
_RESULT = re.compile(
    r'<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', re.S | re.I
)
_SNIPPET = re.compile(r'class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</a>', re.S | re.I)


def register(registry: ToolRegistry) -> None:
    @registry.tool(
        name="fetch",
        description="""
Bir adresi getirir. HTML ise okunabilir metne indirger; JSON, metin ve kod
olduğu gibi döner.

Araştırma, dokümantasyon okuma, API'den veri çekme — hepsi bunun işi. Kabukta
`curl` ya da `Invoke-RestMethod` yazma, bunu kullan: çıktısı temiz gelir ve
hata biçimi tutarlıdır.
        """,
        input_schema=object_schema(
            {
                "url": {"type": "string", "description": "http:// ya da https:// adresi."},
                "raw": {
                    "type": "boolean",
                    "description": "HTML'i indirgemeden ham getir (seçici yazacaksan).",
                },
            },
            required=["url"],
        ),
    )
    async def fetch(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        url = str(args.get("url") or "").strip()
        if not _is_web(url):
            return ToolResult.error(
                f"Yalnızca http/https adresleri getirilebilir: {url!r}. "
                "Yerel dosya için read_file kullan."
            )

        try:
            body, kind, final = await asyncio.to_thread(_get, url)
        except urllib.error.HTTPError as exc:
            return ToolResult.error(f"{url} → HTTP {exc.code} {exc.reason}")
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            return ToolResult.error(f"{url} getirilemedi: {exc}")

        text = body if args.get("raw") else _readable(body, kind)
        clipped = len(text) > MAX_TEXT
        if clipped:
            text = text[:MAX_TEXT]

        header = final if final == url else f"{url} → {final}"
        note = f"\n\n[... kırpıldı, {MAX_TEXT} karakter gösterildi]" if clipped else ""
        return ToolResult(
            content=f"{header}\n\n{text}{note}",
            detail={"url": final, "type": kind, "chars": len(text)},
        )

    @registry.tool(
        name="search",
        description="""
Web'de arar ve başlık + adres + özet listesi döndürür. Anahtar gerektirmiyor.

Aradığını bulduktan sonra sayfanın kendisini `fetch` ile aç: buradaki özetler
yönlendirmek için, cevap vermek için değil.
        """,
        input_schema=object_schema(
            {
                "query": {"type": "string", "description": "Aranacak ifade."},
                "limit": {"type": "integer", "description": f"Azami sonuç (en fazla {MAX_RESULTS})."},
            },
            required=["query"],
        ),
    )
    async def search(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        query = str(args.get("query") or "").strip()
        if not query:
            return ToolResult.error("Boş arama. Ne aradığını `query` alanına yaz.")

        limit = max(1, min(int(args.get("limit") or 5), MAX_RESULTS))
        try:
            body, _, _ = await asyncio.to_thread(
                _get, SEARCH_URL + "?" + urllib.parse.urlencode({"q": query})
            )
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            return ToolResult.error(f"Arama yapılamadı: {exc}")

        hits = _results(body, limit)
        if not hits:
            return ToolResult(
                content=f"'{query}' için sonuç bulunamadı.",
                detail={"query": query, "results": 0},
            )

        lines = [f"'{query}' için {len(hits)} sonuç:", ""]
        for index, (title, link, snippet) in enumerate(hits, 1):
            lines.append(f"{index}. {title}")
            lines.append(f"   {link}")
            if snippet:
                lines.append(f"   {snippet}")
            lines.append("")
        return ToolResult(content="\n".join(lines), detail={"query": query, "results": len(hits)})


# -- getirme -----------------------------------------------------------


def _is_web(url: str) -> bool:
    try:
        scheme = urllib.parse.urlparse(url).scheme.lower()
    except ValueError:
        return False
    return scheme in ("http", "https")


def _get(url: str) -> tuple[str, str, str]:
    """Gövde, içerik türü ve (yönlendirme sonrası) son adres."""
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/json,text/plain,*/*",
            "Accept-Encoding": "gzip",
            "Accept-Language": "tr,en;q=0.8",
        },
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        raw = response.read(MAX_BYTES)
        if response.headers.get("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)
        kind = (response.headers.get_content_type() or "").lower()
        charset = response.headers.get_content_charset() or "utf-8"
        final = response.geturl()

    # Bozuk baytlar yüzünden koca bir sayfayı kaybetmek anlamsız.
    return raw.decode(charset, errors="replace"), kind, final


def _readable(body: str, kind: str) -> str:
    """HTML'i okunabilir metne indirger. HTML değilse dokunmaz.

    Ham HTML bağlamın düşmanı: 200 KB'lık bir sayfanın 190 KB'ı betik, stil
    ve gezinme. Burada yapılan iş kabaca "tarayıcıda seçip kopyalamak".
    """
    if "html" not in kind:
        return body.strip()

    # Başlık gövdeden önce alınıyor: `<head>` birazdan tamamen atılacak.
    title = ""
    if found := _TITLE.search(body):
        title = _collapse(html.unescape(_TAG.sub("", found.group(1))))

    text = _DROPPED.sub("\n", body)
    # Blok sonlarını satır sonuna çeviriyoruz; yoksa bütün sayfa tek satır.
    text = _BREAK.sub("\n", text)
    text = _TAG.sub("", text)
    text = html.unescape(text)
    text = _SPACES.sub(" ", text)
    text = "\n".join(line.strip() for line in text.splitlines())
    text = _BLANK.sub("\n\n", text).strip()

    return f"# {title}\n\n{text}" if title else text


def _collapse(text: str) -> str:
    return " ".join(text.split())


def _results(body: str, limit: int) -> list[tuple[str, str, str]]:
    snippets = [_collapse(html.unescape(_TAG.sub("", s))) for s in _SNIPPET.findall(body)]

    out: list[tuple[str, str, str]] = []
    for index, (href, title) in enumerate(_RESULT.findall(body)):
        if len(out) >= limit:
            break
        link = _unwrap(html.unescape(href))
        if not _is_web(link):
            continue
        out.append((
            _collapse(html.unescape(_TAG.sub("", title))),
            link,
            snippets[index] if index < len(snippets) else "",
        ))
    return out


def _unwrap(href: str) -> str:
    """DuckDuckGo bağlantıları kendi yönlendiricisinden geçiriyor.

    Gerçek adres `uddg` parametresinde; onu çıkarmazsak model ekranda
    okunmayan bir yönlendirme adresi görüyor.
    """
    if "duckduckgo.com/l/" not in href and not href.startswith("//duckduckgo.com/l/"):
        return href
    query = urllib.parse.urlparse(href).query
    target = urllib.parse.parse_qs(query).get("uddg")
    return target[0] if target else href
