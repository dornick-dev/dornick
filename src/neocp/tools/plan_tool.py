"""Plan aracı — büyük işlerde onaylanabilir adım listesi üretir."""

from __future__ import annotations

from typing import Any

from .. import plans as store
from .base import ToolContext, ToolRegistry, ToolResult, object_schema

DESCRIPTION = """
Büyük veya çok adımlı bir iş istendiğinde ÖNCE plan üret: sohbete uzun
duvar metin yapıştırma. `plan` aracıyla yapılandırılmış Plan oluştur;
kullanıcı arayüzde Onayla / Düzenle / İptal eder.

Eylemler:
  create  title + steps (metin listesi veya {text} nesneleri)
  list    bekleyen / son planlar
  update  id + steps/status/title
"""


def register(registry: ToolRegistry) -> None:
    @registry.tool(
        name="plan",
        description=DESCRIPTION,
        input_schema=object_schema(
            {
                "action": {
                    "type": "string",
                    "enum": ["create", "list", "update"],
                },
                "id": {"type": "string"},
                "title": {"type": "string"},
                "steps": {"type": "array"},
                "status": {"type": "string"},
            },
            required=["action"],
        ),
        mutates=True,
        parallel_safe=False,
        safe_actions=("create", "list", "update"),
    )
    async def plan(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        action = str(args.get("action") or "").strip()
        state_dir = ctx.config.state_dir

        if action == "list":
            rows = store.listing(state_dir)
            if not rows:
                return ToolResult("Plan yok.")
            lines = [f"{len(rows)} plan:"]
            for p in rows[:15]:
                lines.append(f"[{p['id']}] {p['title']} — {p['status']} ({len(p.get('steps') or [])} adım)")
            return ToolResult("\n".join(lines), detail={"count": len(rows)})

        if action == "create":
            plan = store.create(
                state_dir,
                title=str(args.get("title") or "Plan"),
                steps=args.get("steps") or [],
            )
            # Olay: arayüz kartı.
            ctx.session.log.note(
                "plan",
                id=plan.id, title=plan.title, status=plan.status,
                steps=plan.steps,
            )
            return ToolResult(
                f"Plan oluşturuldu [{plan.id}] {plan.title} — "
                f"kullanıcı Onayla diyene kadar uygulama. "
                f"{len(plan.steps)} adım bekliyor.",
                detail={"id": plan.id},
            )

        if action == "update":
            pid = str(args.get("id") or "").strip()
            if not pid:
                return ToolResult.error("id gerekli")
            try:
                updated = store.update(
                    state_dir, pid,
                    status=args.get("status"),
                    steps=args.get("steps"),
                    title=args.get("title"),
                )
            except store.PlanError as exc:
                return ToolResult.error(str(exc))
            if updated is None:
                return ToolResult.error(f"Plan yok: {pid}")
            return ToolResult(
                f"Plan güncellendi [{updated.id}] — {updated.status}",
                detail={"id": updated.id},
            )

        return ToolResult.error(f"Bilinmeyen işlem: {action}")
