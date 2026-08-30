"""Duyu aracı — ajanın kendi kulağını ve gözünü yönetmesi.

Gerçek bir kayıtta kullanıcı "şu an beni dinleme, oyun oynuyorum" dedi;
ajan "anladım, kapalıyım" diye cevap verdi ve dinlemeye devam etti —
çünkü kulağını kapatacak hiçbir aracı yoktu. Aynı hata gözde de vardı:
"beni izleme" dendiğinde "izlemiyorum" diyor ama kamera kare almaya
devam ediyordu. Yapamadığı bir şeyi yaptım demek, en kötü tür yalan.

Bu araç iki duyuyu birden yönetiyor. Susturmak kulağı koparmıyor: ses yerelde dinlenmeye devam ediyor ama
yalnızca uyandırma sözü aranıyor. Kamera kapanınca aygıt bırakılır
(LED söner). Kullanıcı "neo" deyince yalnız kulak geri açılır; kamera
üstteki ikon veya "kamerayı aç" ile açılır.
"""

from __future__ import annotations

from typing import Any

from .base import ToolContext, ToolRegistry, ToolResult, object_schema

DESCRIPTION = """
Duyularını yönetir: kulağını ve gözünü kapat, geri aç, durumlarını gör.

**Kullanıcı "beni dinleme", "kamerayı kapat", "beni izleme", "sus"
dediğinde BUNU ÇAĞIR.** "Kapalıyım" deyip devam etmek yalandır.

  action=pause    kapat. Kulak: `minutes` veya "neo" deyene kadar.
                  Kamera: aygıt bırakılır, LED söner (üstteki ikonla aynı).
  action=resume   geri aç. Kamera için LED yeniden yanar.
  action=status   şu anki hal.

  what=hearing    yalnız kulak
  what=sight      yalnız kamera
  what=all        ikisi (varsayılan)

Kulak kapanınca "neo" demek kulağı açar. Kamera kendiliğinden açılmaz —
üstteki kamera ikonu veya "kamerayı aç" gerekir.
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
        power = getattr(ctx, "camera_power", None)
        picked = _senses(ctx, what)
        if not picked and not (power and what in ("sight", "all")):
            return ToolResult.error(
                "Bu oturumda kapatılacak bir duyu açık değil."
            )

        action = str(args.get("action") or "")

        if action == "pause":
            minutes = float(args.get("minutes") or 0)
            msgs: list[str] = []
            if what in ("hearing", "all") and ctx.ear is not None:
                ctx.ear.snooze(minutes * 60)
                how = (
                    f"{minutes:g} dakika" if minutes > 0
                    else 'kullanıcı "neo" diyene kadar'
                )
                msgs.append(f"kulak kapatıldı ({how}).")
            if what in ("sight", "all"):
                if power:
                    msgs.append(power(False))
                else:
                    for name, sense in _senses(ctx, "sight"):
                        sense.snooze(minutes * 60)
                        msgs.append(f"{name} susturuldu.")
            if not msgs:
                return ToolResult.error("Kapatılacak duyu yok.")
            return ToolResult(
                " ".join(msgs) + " Cevabında yalnızca gerçekten kapananları söyle."
            )

        if action == "resume":
            msgs = []
            if what in ("hearing", "all") and ctx.ear is not None:
                ctx.ear.unsnooze()
                msgs.append("kulak açık.")
            if what in ("sight", "all"):
                if power:
                    msgs.append(power(True))
                else:
                    for name, sense in _senses(ctx, "sight"):
                        sense.unsnooze()
                        msgs.append(f"{name} açık.")
            if not msgs:
                return ToolResult.error("Açılacak duyu yok.")
            return ToolResult(" ".join(msgs))

        if action == "status":
            lines = []
            for name, sense in picked:
                if getattr(sense, "snoozed", False):
                    lines.append(f"{name}: kapalı")
                elif failure := getattr(sense, "failure", ""):
                    lines.append(f"{name}: arıza — {failure}")
                else:
                    lines.append(f"{name}: açık")
            if power and what in ("sight", "all") and not any(
                    n == "göz" for n, _ in picked):
                lines.append("kamera: kapalı")
            return ToolResult("\n".join(lines) or "durum yok")

        return ToolResult.error("`action` pause, resume ya da status olmalı.")
