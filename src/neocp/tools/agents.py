"""Alt ajan aracı.

Ajanın kendine yardımcı çıkarabilmesi bir kolaylık değil, bağlam meselesi.
"Şu klasördeki yirmi dosyayı gez ve hangisinde şu geçiyor bul" gibi bir iş
otuz araç çağrısı üretiyor ve otuzunun çıktısı da ana konuşmanın penceresine
yığılıyor. Oysa geriye kalması gereken tek şey cevabın kendisi.

Alt ajan kendi oturumunda, kendi geçmişiyle çalışıyor; ana ajana yalnızca son
sözü dönüyor. Yani bu araç işi bölmekten çok **bağlamı bölüyor**.

İki sınır var:

    derinlik   Alt ajanın alt ajanı olmuyor. Olsaydı tek bir istek ağaç gibi
               açılır ve ne kadar iş yapıldığını kimse bilemezdi.
    izin       Alt ajan aynı izin motoruna bağlı. "Ben alt ajanım" diyerek
               atlanabilen bir kapı, kapı değildir.
"""

from __future__ import annotations

from typing import Any

from .base import ToolContext, ToolRegistry, ToolResult, object_schema

DESCRIPTION = """
Bir işi kendi bağlamında yürütmesi için alt ajan başlatır. Alt ajan senin
araçlarınla çalışır, kendi oturumunda ilerler ve sana yalnızca sonucu döner —
ara adımları senin bağlamını doldurmaz.

Ne zaman kullan:
- Arama/tarama işleri: "şu dizinde X geçen dosyaları bul"
- Çok adımlı ama sonucu kısa işler: "bu üç kaynağı oku ve karşılaştır"
- Birbirinden bağımsız parçalar: birkaç alt ajanı aynı turda başlat, paralel
  çalışırlar

Ne zaman kullanma:
- Tek araç çağrısıyla biten iş: doğrudan yap, alt ajan pahalı
- Kullanıcıyla konuşulması gereken iş: alt ajan kullanıcıyı göremiyor

`task` alanını eksiksiz yaz: alt ajan bu konuşmayı görmüyor, yalnızca senin
verdiğin metni görüyor. Ne aradığını, nerede arayacağını ve neyi döndürmesini
istediğini açıkça söyle.
"""


def register(registry: ToolRegistry) -> None:
    @registry.tool(
        name="task",
        description=DESCRIPTION,
        input_schema=object_schema(
            {
                "title": {
                    "type": "string",
                    "description": "Kısa etiket; arayüzde bu görünüyor.",
                },
                "task": {
                    "type": "string",
                    "description": (
                        "Alt ajana verilecek eksiksiz yönerge. Bu konuşmayı "
                        "görmüyor; gereken bağlamı buraya yaz."
                    ),
                },
                "model": {
                    "type": "string",
                    "description": (
                        "Alt ajanın kullanacağı model. Boşsa seninkini "
                        "kullanır. Basit tarama işini küçük ve hızlı bir "
                        "modele, görüntü gerektiren işi görüntü okuyan bir "
                        "modele ver — hangi modellerin ne yapabildiğini "
                        "`models` ile öğren."
                    ),
                },
            },
            required=["task"],
        ),
        # Yan etkisi araçları üzerinden oluyor ve onların hepsi zaten izin
        # kapısından geçiyor; aracın kendisi bir şey değiştirmiyor.
        mutates=False,
        # Bağımsız alt ajanlar aynı turda paralel koşabilmeli — asıl kazanç
        # burada.
        parallel_safe=True,
    )
    async def task(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        if ctx.spawn is None:
            return ToolResult.error(
                "Alt ajan başlatılamıyor: en fazla bir seviye derinlik var ve "
                "sen zaten bir alt ajansın. İşi kendin yap."
            )

        instruction = str(args.get("task") or "").strip()
        if not instruction:
            return ToolResult.error("Boş görev. Alt ajanın ne yapacağını `task` alanına yaz.")

        title = str(args.get("title") or "").strip() or _headline(instruction)

        answer = await ctx.spawn(title, instruction, str(args.get("model") or ""))
        if not answer.strip():
            return ToolResult.error(
                f"'{title}' alt ajanı bir sonuç döndürmeden bitti. "
                "Görevi daha açık yazıp tekrar dene."
            )
        return ToolResult(content=answer, detail={"title": title})


def _headline(text: str, limit: int = 60) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[:limit] + "…"
