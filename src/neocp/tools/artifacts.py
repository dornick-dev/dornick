"""Artifact aracı — kalıcı, güncellenebilir teslimat sayfaları.

Çizim (`draw`) anlık bir sunum: o turda ekranda durur, sonra akıntıya
karışır. Artifact ise teslimatın kendisi: bir kez yayınlanır, kısa bir
kimlik alır ve hep aynı adreste yaşar. Model sonraki turlarda aynı kimliği
güncelleyerek sayfayı büyütür — her seferinde yenisini açıp kullanıcıyı
kopya sayfalara boğmaz.

Depo atölye dışında (`.neocp/artifacts/`) ama yazma bu aracın kendi yolu
üzerinden yapılıyor: kimlik sıkı bir desenden geçiyor, yol istek verisinden
türetilmiyor. Atölye sınırı dosya araçlarını bağlar; burada dosya aracı yok,
`mutates=True` olduğu için izin kapısı yine de soruyor.
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
    """Kartı sohbete düşüren olay. Günlüğe not olarak yazılıyor; sunucu
    STREAMED_NOTES üzerinden SSE'ye taşıyor — hub'a doğrudan el atmadan
    mevcut olay yayma kalıbının içinden."""
    ctx.session.log.note(
        "artifact",
        id=meta["id"],
        title=meta.get("title", ""),
        surum=int(meta.get("surum", 1)),
        action=action,
        address=store.address(meta["id"]),
    )
