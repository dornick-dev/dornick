"""Çizim aracı — ajanın ekranı kullanması.

Bazı cevaplar yazıyla anlatılınca kayboluyor. "Depo seviyesi %62" bir
sayı; depo silueti üzerinde duran bir çizgi bir bakışta okunuyor.

Hazır grafik türleri yok. Elli şablon tanımlayıp "birini seç" demek, tam
da istenen şeyi engelliyor: o işe özel bir çizim. Ajan HTML/SVG yazıyor,
burada ona bir yüzey veriliyor.
"""

from __future__ import annotations

from typing import Any

from .. import canvas
from .base import ToolContext, ToolRegistry, ToolResult, object_schema

DESCRIPTION = """
Ekrana bir çizim koyar. Sayfayı sen yazıyorsun: HTML ve SVG.

Ne zaman kullan:
  - Kullanıcı istediğinde ("çiz", "göster", "şekille anlat").
  - Görsel anlatmanın gerçekten daha iyi olduğu yerlerde: bir seviye, bir
    yerleşim, bir harita üzerinde bir nokta, bir zaman çizelgesi, bir
    karşılaştırma, bir akış.

Ne zaman kullanma:
  - Cevap bir sayı ya da bir cümleyse. "BTC 77.986$" için çizim gereksiz.
  - Her cevaba bir grafik iliştirme. Süs değil, anlatım aracı.

Nasıl:
  - `body` bir HTML parçası. Çerçeve, palet ve yazı tipi hazır geliyor —
    yalnızca içeriği yaz.
  - Değişkenler kullanılabilir: var(--cyan), var(--mint), var(--amber),
    var(--rose), var(--violet), var(--ink), var(--dim), var(--faint).
  - Etkileşim serbest: `<script>` çalışıyor. Tıklanabilir, sürüklenebilir,
    canlanan şeyler yapabilirsin.
  - **Ağ yok.** Dış resim, dış yazı tipi, CDN betiği yüklenmiyor; sayfa
    katı bir CSP ile sarılıyor. Her şey satır içi ya da gömülü olmalı
    (SVG çiz, resmi `data:` olarak göm).

Çizim atölyendeki `gorseller/` klasörüne yazılıyor; sonra da düzenleyip
yeniden gösterebilirsin.
"""

EXAMPLE = """Örnek (depo seviyesi):
  <h1>Depo 1 — %62</h1>
  <svg viewBox="0 0 120 200">
    <rect x="20" y="10" width="80" height="180" rx="6"
          fill="none" stroke="var(--faint)"/>
    <rect x="20" y="78" width="80" height="112" rx="6" fill="var(--cyan)"
          opacity=".35"/>
    <line x1="20" y1="78" x2="100" y2="78" stroke="var(--cyan)"
          stroke-width="2"/>
  </svg>
"""


def register(registry: ToolRegistry) -> None:
    @registry.tool(
        name="draw",
        description=DESCRIPTION + "\n" + EXAMPLE,
        input_schema=object_schema(
            {
                "title": {
                    "type": "string",
                    "description": "Çizimin adı. Dosya adı da bundan türüyor.",
                },
                "body": {
                    "type": "string",
                    "description": "HTML/SVG gövdesi. Çerçeve ve palet hazır geliyor.",
                },
            },
            required=["title", "body"],
        ),
        mutates=True,
        parallel_safe=False,
    )
    async def draw(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        body = str(args.get("body") or "").strip()
        if not body:
            return ToolResult.error("`body` boş. Çizilecek bir şey yaz.")

        try:
            path = canvas.save(ctx.sandbox.root, str(args.get("title") or ""), body)
        except OSError as exc:
            return ToolResult.error(f"Çizim yazılamadı: {exc}")

        return ToolResult(
            content=(
                f"Çizim ekranda: {ctx.sandbox.relative(path)}\n"
                "Kullanıcı görüyor — cevabında çizimi baştan anlatma, "
                "yalnızca okunması gereken şeyi söyle."
            ),
            detail={"path": str(path)},
        )
