"""Alt ajan araçları.

Ajanın kendine yardımcı çıkarabilmesi bir kolaylık değil, bağlam meselesi.
"Şu klasördeki yirmi dosyayı gez ve hangisinde şu geçiyor bul" gibi bir iş
otuz araç çağrısı üretiyor ve otuzunun çıktısı da ana konuşmanın penceresine
yığılıyor. Oysa geriye kalması gereken tek şey cevabın kendisi.

Alt ajan kendi oturumunda, kendi geçmişiyle çalışıyor; ana ajana yalnızca
sonucu dönüyor. Yani bu araç işi bölmekten çok **bağlamı bölüyor**.

İki kip var:

    bekleyerek  (varsayılan) `task` sonucu gelene kadar bekler — kısa,
                sonucu hemen gereken işler için.
    arka plan   `task` hemen döner, yardımcı arkada koşar; bitince sonucu
                ana ajana bildirilir. Uzun soluklu ya da sonucu hemen
                gerekmeyen işler için. Koşan yardımcıya `task_say` ile yön
                verilir, `task_status` ile durum sorulur.

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
Bir işi kendi bağlamında yürütmesi için alt ajan (yardımcı) başlatır.
Yardımcı senin araçlarınla çalışır, kendi oturumunda ilerler ve ara
adımları senin bağlamını doldurmaz — sana sonucu döner: bekleyerek
başlattıysan hemen, arka planda başlattıysan bittiğinde bildirilerek.

Ne zaman kullan (genel kural: bağımsız, paralelleştirilebilir ya da uzun
soluklu işleri yardımcılara devret):
- Arama/tarama işleri: "şu dizinde X geçen dosyaları bul"
- Çok adımlı ama sonucu kısa işler: "bu üç kaynağı oku ve karşılaştır"
- Birbirinden bağımsız parçalar: birkaç yardımcıyı aynı turda başlat,
  paralel çalışırlar
- Sonucuna hemen ihtiyacın yoksa `arka_plan: true` ver ve beklemeden kendi
  işine devam et — bitince haber gelir. Koşan yardımcıya `task_say` ile
  yön verebilirsin.

Ne zaman kullanma:
- Tek araç çağrısıyla biten iş: doğrudan yap, yardımcı pahalı
- Kullanıcıyla konuşulması gereken iş: yardımcı kullanıcıyı göremiyor

`task` alanını eksiksiz yaz: yardımcı bu konuşmayı görmüyor, yalnızca senin
verdiğin metni görüyor. Ne aradığını, nerede arayacağını ve neyi döndürmesini
istediğini açıkça söyle.
"""

SAY_DESCRIPTION = """
Koşan ya da bitmiş bir yardımcıya mesaj gönderir. Koşana: mesaj yardımcının
bir sonraki adımına not olarak girer (yön değiştirme, ek bilgi, kapsam
daraltma). Bitmişe: yardımcının oturumu diskten açılır ve mesajla arka
planda sürdürülür — bitince sonucu sana bildirilir. Kimlikleri `task`
başlatırken aldın; unuttuysan `task_status` ile bak.
"""

STATUS_DESCRIPTION = """
Yardımcıların durum özetini verir: kimlik, başlık, durum (koşuyor · bitti ·
hata) ve bitmişlerde sonucun başı. `id` verirsen yalnız o yardımcıyı gösterir.
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
                "arka_plan": {
                    "type": "boolean",
                    "description": (
                        "true: yardımcı arka planda koşar, bu araç hemen "
                        "döner ve sen beklemeden devam edersin; sonucu "
                        "bitince sana bildirilir. Varsayılan false: sonuç "
                        "gelene kadar beklenir."
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
        model = str(args.get("model") or "")

        if bool(args.get("arka_plan")) and ctx.spawn_bg is not None:
            handle = ctx.spawn_bg(title, instruction, model)
            return ToolResult(
                content=(
                    f"yardımcı başlatıldı · id={handle.id} · başlık={handle.title} — "
                    "bitince sonucu sana bildirilecek; beklemeden işine devam et. "
                    "Koşarken `task_say` ile yön verebilir, `task_status` ile "
                    "durumunu sorabilirsin."
                ),
                detail={"title": handle.title, "id": handle.id, "arka_plan": True},
            )

        answer = await ctx.spawn(title, instruction, model)
        if not answer.strip():
            return ToolResult.error(
                f"'{title}' alt ajanı bir sonuç döndürmeden bitti. "
                "Görevi daha açık yazıp tekrar dene."
            )
        return ToolResult(content=answer, detail={"title": title})

    @registry.tool(
        name="task_say",
        description=SAY_DESCRIPTION,
        input_schema=object_schema(
            {
                "id": {
                    "type": "string",
                    "description": "Yardımcının kimliği (task başlatırken verildi).",
                },
                "message": {
                    "type": "string",
                    "description": "İletilecek mesaj: yön, ek bilgi, yeni istek.",
                },
            },
            required=["id", "message"],
        ),
        mutates=False,
        parallel_safe=True,
    )
    async def task_say(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        if ctx.child_say is None:
            return ToolResult.error(
                "Yardımcıya mesaj gönderilemiyor: sen zaten bir alt ajansın."
            )
        message = str(args.get("message") or "").strip()
        if not message:
            return ToolResult.error("Boş mesaj. Ne iletmek istediğini `message` alanına yaz.")
        ok, text = ctx.child_say(str(args.get("id") or ""), message)
        return ToolResult(content=text) if ok else ToolResult.error(text)

    @registry.tool(
        name="task_status",
        description=STATUS_DESCRIPTION,
        input_schema=object_schema(
            {
                "id": {
                    "type": "string",
                    "description": "Boşsa tüm yardımcılar; doluysa yalnız o kimlik.",
                },
            },
        ),
        mutates=False,
        parallel_safe=True,
    )
    async def task_status(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        if ctx.child_status is None:
            return ToolResult.error("Durum sorulamıyor: sen zaten bir alt ajansın.")
        return ToolResult(content=ctx.child_status(str(args.get("id") or "")))


def _headline(text: str, limit: int = 60) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[:limit] + "…"
