"""`kamera` aracı — kayıtlı kameralardan modele anlık kesit.

Kullanıcının isteği (29.08): "soru sorduğumuzda kameralardan gerektiği
kadar kesit alıp modele gönderebilsin". Sürekli izleme ayrı (watch.Watcher,
hareket algılamalı); burası SORULDUĞUNDA bakma yolu.

NVIDIA GPU varsa kare önce yerelde analiz edilir (sight); sohbet modeli
o metni de görür. GPU yoksa yalnız kesit gider.

Mahremiyet: `kesit` mutates=True — model kendi kararıyla kamerayı
açamıyor; izin kipinde kullanıcı görüp onaylıyor. `liste` ve `yol`
serbest: isimler ve son özet görüntü almak değil.
"""

from __future__ import annotations

from typing import Any

from .. import watch
from .base import ToolContext, ToolRegistry, ToolResult, object_schema

BUILTIN = "Bilgisayar kamerası"

DESCRIPTION = """
Kayıtlı kameralara isimle bakarsın. İsimler sistem promptunda da durur.

Eylemler:
  liste   kayıtlı kameralar (ad, tür, host/yol — şifre yok) + dahili
  yol     kare GÖNDERMEDEN yol verisi: son hareket notu, last_seen,
          varsa canlı GPU özeti. "bahçede ne vardı", "kameralar ne diyor"
  kesit   kareler lazımsa: id veya name + adet (1-4). GPU metni de gelir.

Kullanıcı bir kameranın adını söylediyse o adla çağır; "dahili" /
"Bilgisayar kamerası" dahili webcam.
"""


def _builtin() -> watch.Camera:
    return watch.Camera(id="lens", name=BUILTIN, source="0", kind="usb")


def _line(cam: watch.Camera) -> str:
    """Modele giden satır: şifre yok."""
    bits = [f"  [{cam.id}] {cam.name}"]
    kind = (cam.kind or "usb").strip() or "usb"
    if cam.is_builtin():
        bits.append("usb dahili")
    elif cam.host.strip():
        port = int(cam.port or 0) or (554 if kind == "rtsp" else 80)
        path = cam.path.strip() or "/"
        bits.append(f"{kind} {cam.host.strip()}:{port}{path}")
    elif cam.source and cam.source not in ("0",):
        bits.append(f"kaynak {cam.source}")
    else:
        bits.append(kind)
    if cam.enabled:
        bits.append("izleme açık")
    if cam.analyze:
        bits.append("GPU açık")
    if cam.user:
        bits.append("kullanıcı var")
    line = " — ".join(bits[:2]) if len(bits) >= 2 else bits[0]
    extra = " · ".join(bits[2:])
    if extra:
        line += " · " + extra
    if cam.last_seen or cam.last_note:
        tail = cam.last_seen or "?"
        if cam.last_note:
            tail += f" · {cam.last_note}"
        line += f"\n    son: {tail}"
    return line


def _resolve(cameras: list[watch.Camera], args: dict[str, Any]
             ) -> watch.Camera | str:
    """Kamera kaydı veya hata metni."""
    cid = str(args.get("id") or "").strip()
    ad = str(args.get("name") or args.get("ad") or "").strip()
    kaynak = str(args.get("source") or "").strip()

    def by_id(key: str) -> watch.Camera | None:
        return next((c for c in cameras if c.id == key), None)

    if cid:
        if hit := by_id(cid):
            return hit
        if cid.casefold() in ("lens", "0", "dahili"):
            return next((c for c in cameras if c.is_builtin()), None) or _builtin()
        return f"Kamera yok: {cid} — önce liste çek."

    if ad:
        key = ad.casefold()
        if key in (BUILTIN.casefold(), "dahili kamera", "dahili",
                   "bilgisayar kamerasi"):
            return next((c for c in cameras if c.is_builtin()), None) or _builtin()
        exact = [c for c in cameras if c.name.casefold() == key]
        if len(exact) == 1:
            return exact[0]
        loose = [c for c in cameras if key in c.name.casefold()]
        if len(exact) > 1 or len(loose) > 1:
            adlar = ", ".join(c.name for c in (exact or loose))
            return f"Birden fazla kamera uydu ({adlar}); id ver."
        if len(loose) == 1:
            return loose[0]
        return f"Kamera yok: {ad} — önce liste çek."

    if kaynak:
        if kaynak in ("0",):
            return next((c for c in cameras if c.is_builtin()), None) or _builtin()
        hit = next((c for c in cameras if c.source == kaynak), None)
        if hit:
            return hit
        return watch.Camera(id="anon", name=kaynak, source=kaynak)

    return next((c for c in cameras if c.is_builtin()), None) or _builtin()


def _peek_frame(cam: watch.Camera, ctx: ToolContext) -> str:
    """Açık tampondan kare — kamerayı yeniden açmaz."""
    if cam.is_builtin() and ctx.lens is not None and getattr(ctx.lens, "live", False):
        frame, _age = ctx.lens.snapshot()
        return frame or ""
    watcher = ctx.watcher
    peek = getattr(watcher, "peek", None) if watcher is not None else None
    if callable(peek):
        return peek(cam.id) or ""
    return ""


def _frames(cam: watch.Camera, adet: int, ctx: ToolContext) -> list[str]:
    """Açık Lens/Watcher varsa ikinci kez açmaz."""
    import time

    if cam.is_builtin() and ctx.lens is not None and getattr(ctx.lens, "live", False):
        taken: list[str] = []
        for i in range(adet):
            if i:
                time.sleep(0.4)
            frame, _age = ctx.lens.snapshot()
            if not frame:
                break
            taken.append(frame)
        if taken:
            return taken
    if adet == 1:
        if peeked := _peek_frame(cam, ctx):
            return [peeked]
    return watch.snapshot(cam.connect_source(), adet)


def _yol_text(cam: watch.Camera, gpu: str = "") -> str:
    lines = [f"{cam.name} [{cam.id}]"]
    if cam.last_seen:
        lines.append(f"  son görülme: {cam.last_seen}")
    if cam.last_note:
        lines.append(f"  son not: {cam.last_note}")
    if not cam.last_note and not cam.last_seen:
        lines.append("  henüz hareket notu yok")
    if gpu:
        lines.append(f"  canlı GPU: {gpu}")
    return "\n".join(lines)


def register(registry: ToolRegistry) -> None:
    @registry.tool(
        name="kamera",
        description=DESCRIPTION,
        input_schema=object_schema(
            {
                "action": {"type": "string", "enum": ["liste", "yol", "kesit"]},
                "id": {"type": "string",
                       "description": "Kayıtlı kamera kimliği (liste'den)."},
                "name": {"type": "string",
                         "description": "Kamera adı (ör. bahçe, Bilgisayar kamerası)."},
                "source": {"type": "string",
                           "description": "Doğrudan kaynak: dahili için \"0\", "
                                          "ağ kamerası için tam adres."},
                "adet": {"type": "integer",
                         "description": "kesit: kaç kare (1-4, varsayılan 1)."},
            },
            required=["action"],
        ),
        mutates=True,
        parallel_safe=False,
        safe_actions=("liste", "yol"),
    )
    async def kamera(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        action = str(args.get("action") or "").strip()

        if not watch.available():
            return ToolResult.error(watch.hint())

        cameras = watch.load(ctx.config.state_dir)

        if action == "liste":
            shown = list(cameras)
            if not any(c.is_builtin() for c in shown):
                shown = [_builtin(), *shown]
            lines = [f"{len(shown)} kamera:"]
            lines.extend(_line(c) for c in shown)
            lines.append(
                "Özet için action=yol, kare için action=kesit — name veya id ver.")
            return ToolResult("\n".join(lines), detail={"count": len(shown)})

        if action == "yol":
            picked = any(str(args.get(k) or "").strip()
                         for k in ("id", "name", "ad", "source"))
            if not picked:
                shown = list(cameras)
                if not any(c.is_builtin() for c in shown):
                    shown = [_builtin(), *shown]
                return ToolResult(
                    "\n\n".join(_yol_text(c) for c in shown),
                    detail={"count": len(shown)},
                )

        if action in ("yol", "kesit"):
            found = _resolve(cameras, args)
            if isinstance(found, str):
                return ToolResult.error(found)
            cam = found

            if action == "yol":
                import asyncio
                from .. import sight

                gpu = ""
                if getattr(cam, "analyze", True):
                    frame = await asyncio.to_thread(_peek_frame, cam, ctx)
                    if frame:
                        gpu = await asyncio.to_thread(sight.analyze_url, frame)
                return ToolResult(
                    _yol_text(cam, gpu),
                    detail={"id": cam.id, "name": cam.name},
                )

            adet = max(1, min(int(args.get("adet") or 1), 4))
            import asyncio
            frames = await asyncio.to_thread(_frames, cam, adet, ctx)
            if not frames:
                return ToolResult.error(
                    f"{cam.name} açılamadı: kamera kapalı, meşgul ya da adres "
                    "ulaşılamaz olabilir.")
            from .. import sight

            analiz = await asyncio.to_thread(
                lambda: [sight.analyze_url(f) for f in frames])
            metin = (f"{cam.name} kamerasından {len(frames)} kesit alındı — "
                     "kareler bir sonraki mesajında gözünün önünde.")
            if any(analiz):
                satirlar = []
                for i, ozet in enumerate(analiz, 1):
                    if ozet:
                        satirlar.append(f"  kare {i}: {ozet}")
                metin += "\nYerel GPU analizi:\n" + "\n".join(satirlar)
            return ToolResult(
                metin,
                detail={"images": frames, "id": cam.id, "name": cam.name},
            )

        return ToolResult.error(f"Bilinmeyen işlem: {action}")
