"""Araç katmanı."""

from __future__ import annotations

from typing import Any

from .base import (
    Block,
    Handler,
    ToolContext,
    ToolRegistry,
    ToolResult,
    ToolSpec,
    object_schema,
)
from .executor import execute

__all__ = [
    "Block",
    "Handler",
    "ToolContext",
    "ToolRegistry",
    "ToolResult",
    "ToolSpec",
    "build_registry",
    "execute",
    "object_schema",
]


def build_registry(mind: Any = None, *, subagents: bool = True) -> ToolRegistry:
    """Yerleşik araçlarla dolu bir kayıt defteri kurar.

    `mind` verilirse zihin araçları da eklenir — ajan kendi belleğini,
    hedeflerini ve geçmiş oturumlarını araçla gezebilir hale gelir.

    `subagents=False` alt ajanın kendi defterini kurarken kullanılıyor: alt
    ajanın alt ajanı olmuyor. Aracın hiç kaydedilmemesi, kaydedilip
    reddedilmesinden iyi — model olmayan bir yeteneği denemesin.

    MCP sunucularından gelen araçlar sonradan aynı deftere eklenir; döngü
    aracın nereden geldiğini bilmez.
    """
    from . import (
        artifacts,
        browser,
        canvas,
        checkpoint,
        devices,
        eyes,
        files,
        hands,
        hearing,
        jobs,
        learn,
        mail,
        place,
        search,
        shell,
        web,
    )

    registry = ToolRegistry()
    shell.register(registry)
    files.register(registry)
    # İçerik arama: "X nerede geçiyor?" için dosya dosya okumak yerine tek araç.
    search.register(registry)
    # Değişiklik defteri: dosya araçlarının aldığı anlık görüntüleri listeler
    # ve geri alır (undo/redo).
    checkpoint.register(registry)
    web.register(registry)
    jobs.register(registry)
    eyes.register(registry)
    # Ekran ve el: yalnızca yakalama gerçekten mümkünse. Olmayan bir eli
    # listede göstermek, modeli boşa tıklatmak demek.
    if hands.available():
        hands.register(registry)
    # Tarayıcı (neo chrome): Chrome/Edge kuruluysa kaydediliyor; kullanıcı
    # açmadıysa araç kendisi "kapalı" diyor.
    from .. import chrome as chromium

    if chromium.available():
        browser.register(registry)
    learn.register(registry)
    # Cihazlar: kullanıcının bir kez tarif ettiği PLC, kamera, seri port.
    # Konuşmanın içinde kalırsa bir sonraki oturumda yok oluyor.
    devices.register(registry)
    # Konum: "yarın hava nasıl?" sorusunun cevabı buna bağlı ve model
    # bunu hiçbir yerden öğrenemiyordu.
    place.register(registry)
    # Ekrana çizim: bazı cevaplar yazıyla anlatılınca kayboluyor.
    canvas.register(registry)
    # Artifact: kalıcı teslimat sayfaları — sohbet akar, artifact adreste
    # kalır ve aynı kimlikle güncellenir.
    artifacts.register(registry)
    # Kulak yönetimi: "beni dinleme" gerçek bir eylem olabilmeli.
    hearing.register(registry)
    # Model listesi yalnizca alt ajan varken ise yariyor: alt ajan
    # yoksa secilecek bir sey de yok.
    if subagents:
        learn.register_models(registry)
    # Posta araçları yalnızca hesap tanımlıysa: tanımsız bir aracı
    # listede göstermek modeli olmayan bir yeteneğe yönlendiriyor.
    if mail.configured():
        mail.register(registry)

    if subagents:
        from . import agents

        agents.register(registry)

    if mind is not None:
        from ..mind import register as register_mind

        register_mind(registry, mind)

    return registry
