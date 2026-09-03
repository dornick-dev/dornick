"""Plan tool — produces an approvable step list for big jobs."""

from __future__ import annotations

from typing import Any

from .. import plans as store
from .base import ToolContext, ToolRegistry, ToolResult, object_schema

DESCRIPTION = """
Plan YALNIZ gerçekten büyük işte: çok dosyalı/çok aşamalı, geri dönüşü
zor ya da kullanıcının onayına muhtaç bir kapsam varsa. Küçük ve orta işe
plan ÇİZME — doğrudan yap; plan turu token ve zaman yakar, kullanıcı
"hemen yapsana" diye bekler. Kararsızsan yapmaya başla.

Plan gerekiyorsa sohbete duvar metin yapıştırma: `plan` aracıyla
yapılandırılmış Plan oluştur; kullanıcı arayüzde Onayla / Düzenle / İptal
eder — adımlar kartta görünür. create sonrası en fazla 1–2 kısa cümle.

Onaydan sonra İLERLEMEYİ İŞLE: bir adıma başlarken
`step` (status=yapiliyor), bitirince `step` (status=bitti). Kart bunları
canlı gösterir — kullanıcı hangi aşamada olduğunu buradan izler. İş
bitince planın kendisini `update` (status=bitti) yap.

Eylemler:
  create  title + steps (metin listesi)
  list    bekleyen / son planlar
  update  id + steps/status/title (plan geneli)
  step    id + step (1'den başlayan sıra) + status — TEK adımın durumu
"""


def register(registry: ToolRegistry) -> None:
    @registry.tool(
        name="plan",
        description=DESCRIPTION,
        input_schema=object_schema(
            {
                "action": {
                    "type": "string",
                    "enum": ["create", "list", "update", "step"],
                },
                "id": {"type": "string"},
                "step": {"type": "integer",
                         "description": "Adım sırası (1'den başlar) — action=step için."},
                "title": {"type": "string"},
                # `items` is REQUIRED: when Gemini sees an array without
                # `items` it rejects the ENTIRE tool list
                # ("parameters.properties[steps].items: missing field").
                "steps": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Adımlar, sırayla; her biri tek satır.",
                },
                "status": {"type": "string"},
            },
            required=["action"],
        ),
        mutates=True,
        parallel_safe=False,
        safe_actions=("create", "list", "update", "step"),
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
            # Event: the UI card.
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
            # The event is REQUIRED: the card must update live. Its absence
            # was a measured wound — the user said "it is approved but the
            # card still says Approve, we cannot see which stage we are at"
            # (29.08).
            ctx.session.log.note(
                "plan",
                id=updated.id, title=updated.title, status=updated.status,
                steps=updated.steps,
            )
            return ToolResult(
                f"Plan güncellendi [{updated.id}] — {updated.status}",
                detail={"id": updated.id},
            )

        if action == "step":
            pid = str(args.get("id") or "").strip()
            index = int(args.get("step") or 0)
            status = str(args.get("status") or "bitti").strip()
            if not pid or index < 1:
                return ToolResult.error("id ve step (1'den başlar) gerekli")
            existing = store.get(state_dir, pid)
            if existing is None:
                return ToolResult.error(f"Plan yok: {pid}")
            if index > len(existing.steps):
                return ToolResult.error(
                    f"Plan {len(existing.steps)} adımlı; step={index} yok")
            steps = [dict(s) for s in existing.steps]
            steps[index - 1]["status"] = status
            try:
                updated = store.update(state_dir, pid, steps=steps)
            except store.PlanError as exc:
                return ToolResult.error(str(exc))
            ctx.session.log.note(
                "plan",
                id=updated.id, title=updated.title, status=updated.status,
                steps=updated.steps,
            )
            done = sum(1 for s in updated.steps if s.get("status") == "bitti")
            return ToolResult(
                f"Adım {index} → {status} ({done}/{len(updated.steps)} bitti)",
                detail={"id": updated.id, "step": index},
            )

        return ToolResult.error(f"Bilinmeyen işlem: {action}")
