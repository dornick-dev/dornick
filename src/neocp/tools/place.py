"""Konum aracı.

Model konumu ancak sorunca öğreniyor: her isteme gömmek, konumun hiç
gerekmediği yüzlerce tur boyunca boşuna yer kaplardı. Gerektiğinde
soruluyor.

Dönen metin güven derecesini taşıyor. Bu kasıtlı: "ipucu" olan bir şehri
model cevaba gerçek gibi gömerse — "yarın İstanbul'da 23–30°C" — kullanıcı
orada değilse yanlış bir cevabı doğru gibi sunmuş olur ve yanlış olduğu
bile anlaşılmaz.
"""

from __future__ import annotations

from typing import Any

from .. import place as where
from .base import ToolContext, ToolRegistry, ToolResult, object_schema

DESCRIPTION = """
Kullanıcının nerede olduğunu söyler.

Ne zaman kullan: cevabın konuma bağlı olduğu her yerde — hava durumu,
"yakınımda", yerel saat, ülkeye göre değişen bir kural. Şehri tahmin etme.

Dönen cevap güven derecesi taşıyor:
  kesin   kullanıcı kendi söylemiş — kullanabilirsin
  ülke    saat diliminden; şehir yok, şehir gerekiyorsa sor
  ipucu   IP'den; **kesin değil**, teyit etmeden cevaba gömme
  yok     kapalı ya da bulunamadı — kullanıcıya sor

Öğrendiğin kesin konumu `mind_memory` ile zihnine yaz; aynı şeyi ikinci
kez sormak, ilk kez sormaktan kötü.
"""


def register(registry: ToolRegistry) -> None:
    @registry.tool(
        name="location",
        description=DESCRIPTION,
        input_schema=object_schema({}, required=[]),
    )
    async def location(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        config = getattr(ctx, "config", None)
        setting = getattr(config, "place", None) or where.PlaceConfig()
        found = where.locate(setting)
        return ToolResult(
            content=where.describe(found),
            detail={"where": found.where, "trust": found.trust, "source": found.source},
        )
