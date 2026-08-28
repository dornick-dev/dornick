"""İş akışı aracı — otomasyon grafiklerini kaydetmek ve koşturmak.

Zamanlanmış görev (`schedule`) tek bir prompt metnidir. Workflow ise
düğümlerden oluşan bir grafik: posta oku → HTTP → yetenek → ajan.
Bu araç o grafiği listeler, kaydeder, siler; `run` henüz koşucuya
bağlıysa çağırır, değilse dürüstçe stub döner.
"""

from __future__ import annotations

import json
from typing import Any

from .. import workflows as store
from .base import ToolContext, ToolRegistry, ToolResult, object_schema

DESCRIPTION = """
İş akışı (workflow) grafiklerini yönetir: listeler, okur, oluşturur,
günceller, siler, koşturur.

Ne zaman kullan: tekrarlayan iş birden fazla adımdan oluşuyorsa
(`mail_read` → `http` → `skill` → `agent`) bunu kaydet. Tek cümlelik
prompt için `schedule` yeterli.

ÖNCE BAK: yeni bir akış kurmadan `list` ile eldekilere bak — aynı işi
yapan bir akış varsa onu kullan ya da güncelle. Ama uymayan bir akışı
zorlama; işi gerçekten yapmıyorsa yenisini kurmak doğrusudur. Yarım
uyan bir akışı eğip bükmek, sıfırdan yazmaktan pahalıya patlıyor.

Zamana bağlamak için `schedule action=add workflow_id=<akış>`.

Eylemler:
  list    kayıtlı akışlar
  get     bir akışın tam grafiği (id zorunlu)
  create  yeni akış (title; istenirse nodes/edges)
  update  var olanı güncelle (id + title/nodes/edges)
  remove  sil (id)
  run     koştur (id) — koşucu bağlıysa çağırır, değilse stub

Düğüm türleri açık string: mail_read, http, skill, shell, agent, custom, …
"""


def register(registry: ToolRegistry) -> None:
    @registry.tool(
        name="workflow",
        description=DESCRIPTION,
        input_schema=object_schema(
            {
                "action": {
                    "type": "string",
                    "enum": ["list", "get", "create", "update", "remove", "run"],
                    "description": "Yapılacak işlem.",
                },
                "id": {"type": "string", "description": "get/update/remove/run için kimlik."},
                "title": {"type": "string", "description": "create/update için başlık."},
                # `items` ŞART: Gemini `items`siz bir array gördüğünde araç
                # listesinin TAMAMINI reddediyor. Şekli burada yazmak ayrıca
                # modelin alan adlarını tahmin etmesini de bitiriyor.
                "nodes": {
                    "type": "array",
                    "description": "Grafiğin düğümleri.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "title": {"type": "string"},
                            "type": {"type": "string",
                                     "description": "mail_read, http, skill, shell, agent, custom, …"},
                            "config": {"type": "object",
                                       "description": "Türe özel ayar (prompt, url, command, …)."},
                            "secrets_needed": {"type": "array", "items": {"type": "string"},
                                               "description": "Gizli alan ADLARI; değer YAZILMAZ."},
                            "skill": {"type": "string"},
                        },
                        "required": ["id"],
                    },
                },
                "edges": {
                    "type": "array",
                    "description": "Düğümler arası geçişler.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "from": {"type": "string"},
                            "to": {"type": "string"},
                            "on": {"type": "string",
                                   "description": "'ok', 'hata' ya da boş (her zaman)."},
                        },
                        "required": ["from", "to"],
                    },
                },
            },
            required=["action"],
        ),
        mutates=True,
        parallel_safe=False,
    )
    async def workflow(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        action = str(args.get("action") or "").strip()
        state_dir = ctx.config.state_dir

        if action == "list":
            rows = store.list_all(state_dir)
            if not rows:
                return ToolResult("Kayıtlı iş akışı yok.")
            lines = [f"{len(rows)} akış:"]
            for wf in rows:
                lines.append(
                    f"[{wf.id}] {wf.title} — {len(wf.nodes)} düğüm, {len(wf.edges)} kenar"
                )
            return ToolResult("\n".join(lines), detail={"count": len(rows)})

        if action == "create":
            payload = {
                "id": str(args.get("id") or "").strip(),
                "title": str(args.get("title") or "").strip(),
                "nodes": args.get("nodes") if isinstance(args.get("nodes"), list) else [],
                "edges": args.get("edges") if isinstance(args.get("edges"), list) else [],
            }
            if not payload["title"]:
                return ToolResult.error("create için title gerekli.")
            try:
                created = store.save(state_dir, payload)
            except store.WorkflowError as exc:
                return ToolResult.error(str(exc))
            _hatirla(ctx, created)
            return ToolResult(
                f"Oluşturuldu: [{created.id}] {created.title}",
                detail={"id": created.id},
            )

        workflow_id = str(args.get("id") or "").strip()
        if not workflow_id and action in ("get", "update", "remove", "run"):
            return ToolResult.error("Akış kimliği gerekli. Önce `action=list` ile bak.")

        if action == "get":
            wf = store.get(state_dir, workflow_id)
            if wf is None:
                return ToolResult.error(f"Akış yok: {workflow_id}")
            return ToolResult(
                json.dumps(store.to_dict(wf), ensure_ascii=False, indent=2),
                detail={"id": wf.id},
            )

        if action == "update":
            existing = store.get(state_dir, workflow_id)
            if existing is None:
                return ToolResult.error(f"Akış yok: {workflow_id}")
            payload = store.to_dict(existing)
            if "title" in args and args["title"] is not None and str(args["title"]).strip():
                payload["title"] = str(args["title"]).strip()
            if isinstance(args.get("nodes"), list):
                payload["nodes"] = args["nodes"]
            if isinstance(args.get("edges"), list):
                payload["edges"] = args["edges"]
            try:
                updated = store.save(state_dir, payload)
            except store.WorkflowError as exc:
                return ToolResult.error(str(exc))
            _hatirla(ctx, updated)
            return ToolResult(
                f"Güncellendi: [{updated.id}] {updated.title}",
                detail={"id": updated.id},
            )

        if action == "remove":
            if not store.remove(state_dir, workflow_id):
                return ToolResult.error(f"Akış yok: {workflow_id}")
            return ToolResult(f"[{workflow_id}] silindi.")

        if action == "run":
            wf = store.get(state_dir, workflow_id)
            if wf is None:
                return ToolResult.error(f"Akış yok: {workflow_id}")
            runner = getattr(ctx, "run_workflow", None)
            if callable(runner):
                try:
                    result = runner(wf.id)
                    if hasattr(result, "__await__"):
                        result = await result  # type: ignore[misc]
                except Exception as exc:  # koşucu hatası aracı düşürmemeli
                    return ToolResult.error(f"Akış koşturulamadı: {exc}")
                return ToolResult(
                    str(result or f"Akış koşturuldu: [{wf.id}] {wf.title}"),
                    detail={"id": wf.id},
                )
            return ToolResult(
                f"Akış kayıtlı [{wf.id}] {wf.title}, ama koşucu bu oturumda "
                f"bağlı değil (stub). {len(wf.nodes)} düğüm bekliyor.",
                detail={"id": wf.id, "stub": True},
            )

        return ToolResult.error(f"Bilinmeyen işlem: {action}")


def _hatirla(ctx: Any, wf: Any) -> None:
    """Kurulan/güncellenen akışı hafızaya yordam olarak yaz.

    Amaç aylar sonraki "bunu daha önce otomasyonda yapmıştım" anı: kayıt
    olmadan o an hiç gelmiyor. Hafıza yoksa sessiz — otomasyonun kendisi,
    hatırlanmasından önemli.
    """
    from .. import workflow_mind

    workflow_mind.akisi_hatirla(getattr(ctx, "mind", None), wf)
