"""Plan aracı — büyük işlerde onaylanabilir adım listesi üretir."""

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
                # `items` ŞART: Gemini `items`siz bir array gördüğünde
                # araç listesinin TAMAMINI reddediyor
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
            # Olay ŞART: kart canlı güncellenmeli. Eksikliği ölçülen bir
            # yaraydı — kullanıcı "onaylandı ama kart hâlâ Onayla diyor,
            # hangi aşamadayız görünmüyor" dedi (29.08).
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
            sira = int(args.get("step") or 0)
            durum = str(args.get("status") or "bitti").strip()
            if not pid or sira < 1:
                return ToolResult.error("id ve step (1'den başlar) gerekli")
            mevcut = store.get(state_dir, pid)
            if mevcut is None:
                return ToolResult.error(f"Plan yok: {pid}")
            if sira > len(mevcut.steps):
                return ToolResult.error(
                    f"Plan {len(mevcut.steps)} adımlı; step={sira} yok")
            adimlar = [dict(s) for s in mevcut.steps]
            adimlar[sira - 1]["status"] = durum
            try:
                updated = store.update(state_dir, pid, steps=adimlar)
            except store.PlanError as exc:
                return ToolResult.error(str(exc))
            ctx.session.log.note(
                "plan",
                id=updated.id, title=updated.title, status=updated.status,
                steps=updated.steps,
            )
            biten = sum(1 for s in updated.steps if s.get("status") == "bitti")
            return ToolResult(
                f"Adım {sira} → {durum} ({biten}/{len(updated.steps)} bitti)",
                detail={"id": updated.id, "step": sira},
            )

        return ToolResult.error(f"Bilinmeyen işlem: {action}")
