"""Artifact tool — persistent, updatable deliverable pages.

A drawing (`draw`) is a momentary presentation: it sits on screen that
turn, then blends into the stream. An artifact is the deliverable
itself: published once, given a short id, living at the same address
forever. In later turns the model grows the page by updating the same
id — instead of opening a new one each time and drowning the user in
duplicate pages.

The store is outside the workshop (`.dornick/artifacts/`), but writing
goes through this tool's own path: the id passes a strict pattern, the
path is not derived from request data. The workshop boundary binds the
file tools; there is no file tool here, and since `mutates=True` the
permission gate still asks.
"""

from __future__ import annotations

from typing import Any

from .. import artifacts as store
from .base import ToolContext, ToolRegistry, ToolResult, object_schema

DESCRIPTION = """
Kalıcı bir sayfa yayınlar ve günceller: rapor, pano, görselleştirme.

Genel kural: kalıcı ve paylaşılabilir olması gereken teslimatları (rapor,
pano, görselleştirme) artifact yap. Sohbet mesajı akıp gider; artifact
adresinde kalır ve güncellenir. Sonraki turlarda AYNI id ile `update` çağır,
yeni artifact yaratma.

Eylemler:
  - `publish`: `title` + `html` → yeni artifact. Kısa okunur bir id üretir
    (baslik-slug-4hex) ve sayfa `/artifact/<id>/` adresinde yaşamaya başlar.
  - `update`: `id` + `html` (istenirse yeni `title`) → aynı adrese yeni
    sürüm. Eski sürüm saklanır, sürüm sayacı ilerler.
  - `list`: yayınlanmış artifact'lar (id, başlık, sürüm, güncellenme).

Nasıl:
  - `html` TAM bir sayfa olmalı (<!DOCTYPE html> ile başlayan): stil ve
    betik satır içi, sayfa kendi başına yeter. Betik çalışır — etkileşim
    serbest.
  - Kullanıcı sayfayı sohbetteki karttan ve Uygulamalar panelindeki
    Artifact'lar bölümünden açıyor; sen ayrıca yol tarif etme, adresi söyle.
"""


def register(registry: ToolRegistry) -> None:
    @registry.tool(
        name="artifact",
        description=DESCRIPTION,
        input_schema=object_schema(
            {
                "action": {
                    "type": "string",
                    "enum": ["publish", "update", "list"],
                    "description": "publish: yeni sayfa · update: aynı id'ye yeni sürüm · list: yayınlananlar",
                },
                "id": {
                    "type": "string",
                    "description": "update için: publish'in döndürdüğü kimlik.",
                },
                "title": {
                    "type": "string",
                    "description": "Sayfanın adı. publish'te zorunlu; update'te verilirse ad da değişir.",
                },
                "html": {
                    "type": "string",
                    "description": "Tam HTML sayfası (<!DOCTYPE html> ile). publish ve update için zorunlu.",
                },
            },
            required=["action"],
        ),
        mutates=True,
        parallel_safe=False,
    )
    async def artifact(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        action = str(args.get("action") or "").strip()
        state_dir = ctx.config.state_dir

        if action == "list":
            rows = store.listing(state_dir)
            if not rows:
                return ToolResult(content="Henüz yayınlanmış artifact yok.")
            lines = [
                f"- {m['id']} · {m.get('title', '')} · v{m.get('surum', 1)}"
                f" · {store.address(m['id'])} · güncellenme {m.get('updated', '')}"
                for m in rows
            ]
            return ToolResult(content="Yayınlanmış artifact'lar:\n" + "\n".join(lines))

        if action == "publish":
            try:
                meta = store.publish(
                    state_dir, str(args.get("title") or ""), str(args.get("html") or "")
                )
            except (store.ArtifactError, OSError) as exc:
                return ToolResult.error(f"Artifact yayınlanamadı: {exc}")
            _announce(ctx, meta, "publish")
            return ToolResult(
                content=(
                    f"Artifact yayınlandı: {meta['id']} (v1) — {store.address(meta['id'])}\n"
                    "Kullanıcı sohbetteki karttan açıyor. Bu sayfayı sonraki "
                    f"turlarda `action=update, id={meta['id']}` ile güncelle; "
                    "aynı iş için yeni artifact yaratma."
                ),
                detail={"artifact": meta},
            )

        if action == "update":
            try:
                meta = store.update(
                    state_dir,
                    str(args.get("id") or ""),
                    str(args.get("html") or ""),
                    title=str(args.get("title") or "") or None,
                )
            except (store.ArtifactError, OSError) as exc:
                return ToolResult.error(
                    f"Artifact güncellenemedi: {exc}\n"
                    "Kimliği bilmiyorsan `action=list` ile yayınlananlara bak."
                )
            _announce(ctx, meta, "update")
            return ToolResult(
                content=(
                    f"Artifact güncellendi: {meta['id']} → v{meta['surum']} — "
                    f"adres aynı: {store.address(meta['id'])}"
                ),
                detail={"artifact": meta},
            )

        return ToolResult.error(
            f"Bilinmeyen eylem: {action!r}. Geçerli olanlar: publish, update, list."
        )


def _announce(ctx: ToolContext, meta: dict[str, Any], action: str) -> None:
    """The event that drops the card into the chat. Written to the log as
    a note; the server carries it to SSE via STREAMED_NOTES — inside the
    existing event-broadcast pattern, without reaching into the hub
    directly."""
    ctx.session.log.note(
        "artifact",
        id=meta["id"],
        title=meta.get("title", ""),
        surum=int(meta.get("surum", 1)),
        action=action,
        address=store.address(meta["id"]),
    )
