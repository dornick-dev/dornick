"""Location tool.

The model learns the location only when it asks: embedding it in every
prompt would waste space through hundreds of turns where the location is
never needed. It is asked for when required.

The returned text carries the trust level. This is deliberate: if the
model bakes a "hint" city into an answer as fact — "tomorrow in Istanbul
23–30°C" — and the user is not there, it has presented a wrong answer as
right, and it is not even noticeable that it is wrong.
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
