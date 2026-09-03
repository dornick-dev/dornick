"""Scheduled task tool.

When the user says "check the stock market every morning", the agent
must not do it once and forget — it must set the clock. This tool does
that setting.

Every task that gets set shows up on the settings page and can be
stopped there — an automation the agent set up running hidden from the
user is unacceptable.
"""

from __future__ import annotations

from typing import Any

from ..schedule import MIN_INTERVAL_S, Task
from .base import ToolContext, ToolRegistry, ToolResult, object_schema

DESCRIPTION = """
Zamanlanmış görevleri yönetir: kurar, listeler, günceller, durdurur, siler.

Kullanıcı tekrar eden bir iş istediğinde ("her sabah", "günde bir", "saat
başı") bunu kullan — işi bir kez yapıp geçme.

`prompt` alanını eksiksiz yaz. Tetiklenince bu metin sohbet balonu değil
arka plan yardımcıya gider; rapor Orkestra'da açılır. O anki konuşmayı
görmez: neyi, nerede, nasıl yapacağı orada yazmalı.

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
                    "enum": ["add", "list", "update", "pause", "resume", "remove"],
                    "description": "Yapılacak işlem.",
                },
                "title": {"type": "string", "description": "Kısa ad; listede bu görünür."},
                "prompt": {
                    "type": "string",
                    "description": "Tetiklenince yardımcıya gidecek eksiksiz yönerge.",
                },
                "kind": {"type": "string", "enum": ["every", "daily"]},
                "every_s": {"type": "integer", "description": f"Saniye (en az {MIN_INTERVAL_S})."},
                "at": {"type": "string", "description": "daily için 'HH:MM'."},
                "id": {"type": "string", "description": "update/pause/resume/remove için kimlik."},
                "workflow_id": {
                    "type": "string",
                    "description": (
                        "Bir iş akışını (workflow) zamana bağlamak için akış "
                        "kimliği. Verildiğinde görev otomasyon olur ve "
                        "tetiklenince `prompt` değil O AKIŞ koşar. Tek bir "
                        "yönerge yetiyorsa boş bırak — akış kurmak çok "
                        "adımlı, dallanan iş içindir."
                    ),
                },
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
            # If a workflow id was given, the task is an automation: when
            # triggered, the graph itself runs, not the `prompt`. It is
            # derived from a single field so the two can never contradict
            # (a record like workflow_id set + kind_ui="simple" would mean
            # the runner silently falling back to the prompt).
            flow_id = str(args.get("workflow_id") or "").strip()
            task = Task(
                id="",
                title=str(args.get("title") or "").strip() or _headline(args.get("prompt", "")),
                prompt=str(args.get("prompt") or ""),
                kind=str(args.get("kind") or "every"),
                every_s=int(args.get("every_s") or 3600),
                at=str(args.get("at") or "09:00"),
                kind_ui="automation" if flow_id else "simple",
                workflow_id=flow_id,
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

        if action == "update":
            fields = {}
            for key in ("title", "prompt", "kind", "every_s", "at", "workflow_id"):
                if key in args and args[key] is not None and args[key] != "":
                    fields[key] = args[key]
            # Binding a workflow must change the kind too; if the two drift
            # apart, the task falls into an inconsistent state like "not an
            # automation, but has a workflow".
            if fields.get("workflow_id"):
                fields["kind_ui"] = "automation"
            if not fields:
                return ToolResult.error(
                    "Güncellenecek alan yok (title/prompt/kind/every_s/at/workflow_id).")
            try:
                updated = book.update(task_id, **fields)
            except ValueError as exc:
                return ToolResult.error(str(exc))
            if updated is None:
                return ToolResult.error(f"Görev yok: {task_id}")
            return ToolResult(
                f"Güncellendi: [{updated.id}] {updated.title} — {updated.describe()}.",
                detail={"id": updated.id},
            )

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
