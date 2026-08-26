"""Duyu aracı — ajanın kendi kulağını ve gözünü yönetmesi.

Gerçek bir kayıtta kullanıcı "şu an beni dinleme, oyun oynuyorum" dedi;
ajan "anladım, kapalıyım" diye cevap verdi ve dinlemeye devam etti —
çünkü kulağını kapatacak hiçbir aracı yoktu. Aynı hata gözde de vardı:
"beni izleme" dendiğinde "izlemiyorum" diyor ama kamera kare almaya
devam ediyordu. Yapamadığı bir şeyi yaptım demek, en kötü tür yalan.

Bu araç iki duyuyu birden yönetiyor. Susturmak aygıtı koparmıyor —
kulakta ses yerelde dinlenmeye devam ediyor ama yalnızca uyandırma sözü
aranıyor; gözde kare almak duruyor ve eldeki kare de siliniyor.
Kullanıcı "neo" diyerek **ikisini birden** geri açabiliyor: "ben gelince
seslenirim" tek bir sesleniş demek, duyu duyu saymak değil.
"""

from __future__ import annotations

from typing import Any

from .base import ToolContext, ToolRegistry, ToolResult, object_schema

DESCRIPTION = """
Duyularını yönetir: kulağını ve gözünü sustur, geri aç, durumlarını gör.

**Kullanıcı "beni dinleme", "beni izleme", "sus", "oyun oynuyorum karışma"
dediğinde BUNU ÇAĞIR.** "Kapalıyım" deyip dinlemeye ya da izlemeye devam
etmek yalan söylemektir — kapalı olmak ancak bu araçla olur.

  action=pause    sustur. `minutes` verilirse o kadar; verilmezse kullanıcı
                  "neo" diyene ya da resume çağrılana kadar.
  action=resume   geri aç.
  action=status   şu anki hal.

  what=hearing    yalnız kulak — duyulan hiçbir şey sana gelmiyor.
  what=sight      yalnız göz — kare alınmıyor, eldeki kare siliniyor,
                  ağ kameraları da bildirmiyor.
  what=all        ikisi birden (varsayılan). "Beni dinleme ve izleme"
                  dendiğinde bu.

Kullanıcı "neo" diye seslendiğinde susturulan HER duyu geri açılır.
"""


def _senses(ctx: ToolContext, what: str) -> list[tuple[str, Any]]:
    picked: list[tuple[str, Any]] = []
    if what in ("hearing", "all") and ctx.ear is not None:
        picked.append(("kulak", ctx.ear))
    if what in ("sight", "all"):
        if ctx.lens is not None:
            picked.append(("göz", ctx.lens))
        if getattr(ctx, "watcher", None) is not None:
            picked.append(("ağ kameraları", ctx.watcher))
    return picked


def register(registry: ToolRegistry) -> None:
    @registry.tool(
        name="senses",
        description=DESCRIPTION,
        input_schema=object_schema(
            {
                "action": {
                    "type": "string",
                    "enum": ["pause", "resume", "status"],
                    "description": "pause: sustur. resume: geri aç. status: durum.",
                },
                "what": {
                    "type": "string",
                    "enum": ["hearing", "sight", "all"],
                    "description": "hearing: kulak. sight: göz. all: ikisi (varsayılan).",
                },
                "minutes": {
                    "type": "number",
                    "description": "pause için süre (dakika). Boşsa 'neo' denene kadar.",
                },
            },
            required=["action"],
        ),
        mutates=True,
        parallel_safe=False,
    )
    async def senses(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        what = str(args.get("what") or "all")
        picked = _senses(ctx, what)
        if not picked:
            return ToolResult.error(
                "Bu oturumda susturulacak bir duyu açık değil."
            )

        action = str(args.get("action") or "")

        if action == "pause":
            minutes = float(args.get("minutes") or 0)
            for _name, sense in picked:
                sense.snooze(minutes * 60)
            names = " ve ".join(name for name, _ in picked)
            how = (
                f"{minutes:g} dakika" if minutes > 0
                else 'kullanıcı "neo" diyene kadar'
            )
            return ToolResult(
                f"Susturuldu: {names} ({how}). Kullanıcı adınla seslenirse "
                "hepsi geri açılır. Cevabında yalnızca gerçekten kapananları "
                "söyle — süslemeden."
            )

        if action == "resume":
            for _name, sense in picked:
                sense.unsnooze()
            return ToolResult("Geri açıldı: " + " ve ".join(n for n, _ in picked) + ".")

        if action == "status":
            lines = []
            for name, sense in picked:
                if getattr(sense, "snoozed", False):
                    lines.append(f"{name}: susturulmuş")
                elif failure := getattr(sense, "failure", ""):
                    lines.append(f"{name}: arıza — {failure}")
                else:
                    lines.append(f"{name}: açık")
            return ToolResult("\n".join(lines))

        return ToolResult.error("`action` pause, resume ya da status olmalı.")
