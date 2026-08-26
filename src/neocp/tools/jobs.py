"""Zamanlanmış görev aracı.

Kullanıcı "her sabah borsayı kontrol et" dediğinde ajanın bunu bir kez yapıp
unutması değil, saatini kurması gerekiyor. Bu araç o kurmayı yapıyor.

Kurulan her görev ayar sayfasında görünüyor ve oradan durdurulabiliyor —
ajanın kurduğu bir otomasyonun kullanıcıdan gizli çalışması kabul edilemez.
"""

from __future__ import annotations

from typing import Any

from ..schedule import MIN_INTERVAL_S, Task
from .base import ToolContext, ToolRegistry, ToolResult, object_schema

DESCRIPTION = """
Zamanlanmış görevleri yönetir: kurar, listeler, durdurur, siler.

Kullanıcı tekrar eden bir iş istediğinde ("her sabah", "günde bir", "saat
başı") bunu kullan — işi bir kez yapıp geçme.

`prompt` alanını eksiksiz yaz. Görev tetiklendiğinde bu metin sana yeni bir
mesaj gibi gelecek ve o anki konuşmayı görmeyeceksin: neyi, nerede, nasıl
yapacağın orada yazmalı.

Tekrar biçimleri:
  every  — `every_s` saniyede bir (en az 60)
  daily  — her gün `at` saatinde ("09:00", yerel saat)
"""


def register(registry: ToolRegistry) -> None:
    @registry.tool(
        name="schedule",
        description=DESCRIPTION,
        input_schema=object_schema(
            {
                "action": {
                    "type": "string",
                    "enum": ["add", "list", "pause", "resume", "remove"],
                    "description": "Yapılacak işlem.",
                },
                "title": {"type": "string", "description": "Kısa ad; listede bu görünür."},
                "prompt": {
                    "type": "string",
                    "description": "Tetiklendiğinde sana gelecek eksiksiz yönerge.",
                },
                "kind": {"type": "string", "enum": ["every", "daily"]},
                "every_s": {"type": "integer", "description": f"Saniye (en az {MIN_INTERVAL_S})."},
                "at": {"type": "string", "description": "daily için 'HH:MM'."},
                "id": {"type": "string", "description": "pause/resume/remove için görev kimliği."},
            },
            required=["action"],
        ),
        mutates=True,
        parallel_safe=False,
    )
    async def schedule(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        book = ctx.schedule
        if book is None:
            return ToolResult.error("Zamanlayıcı bu oturumda çalışmıyor.")

        action = str(args.get("action") or "").strip()

        if action == "list":
            tasks = book.all()
            if not tasks:
                return ToolResult("Kurulu görev yok.")
            lines = [f"{len(tasks)} görev:"]
            for task in tasks:
                state = "" if task.enabled else " (durduruldu)"
                last = f" · son: {task.last_status}" if task.last_status else ""
                lines.append(f"[{task.id}] {task.title} — {task.describe()}{state}{last}")
            return ToolResult("\n".join(lines), detail={"count": len(tasks)})

        if action == "add":
            task = Task(
                id="",
                title=str(args.get("title") or "").strip() or _headline(args.get("prompt", "")),
                prompt=str(args.get("prompt") or ""),
                kind=str(args.get("kind") or "every"),
                every_s=int(args.get("every_s") or 3600),
                at=str(args.get("at") or "09:00"),
            )
            try:
                created = book.add(task)
            except ValueError as exc:
                return ToolResult.error(str(exc))
            return ToolResult(
                f"Kuruldu: [{created.id}] {created.title} — {created.describe()}. "
                f"İlk çalışma: {created.next_run}",
                detail={"id": created.id},
            )

        task_id = str(args.get("id") or "").strip()
        if not task_id:
            return ToolResult.error("Görev kimliği gerekli. Önce `action=list` ile bak.")

        if action == "remove":
            if not book.remove(task_id):
                return ToolResult.error(f"Görev yok: {task_id}")
            return ToolResult(f"[{task_id}] silindi.")

        if action in ("pause", "resume"):
            updated = book.update(task_id, enabled=action == "resume")
            if updated is None:
                return ToolResult.error(f"Görev yok: {task_id}")
            state = "sürdürüldü" if updated.enabled else "durduruldu"
            return ToolResult(f"[{task_id}] {state}.")

        return ToolResult.error(f"Bilinmeyen işlem: {action}")


def _headline(text: str, limit: int = 48) -> str:
    flat = " ".join(str(text).split())
    return flat if len(flat) <= limit else flat[:limit] + "…"
