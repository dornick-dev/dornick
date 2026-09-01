"""Araç katmanı."""

from __future__ import annotations

from typing import Any

from .base import (
    Block,
    Handler,
    JobFailed,
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
    "JobFailed",
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
        git_tool,
        hands,
        hearing,
        camera,
        jobs,
        kod,
        kosucu,
        learn,
        mail,
        place,
        plan_tool,
        search,
        shell,
        web,
        workflow,
    )

    registry = ToolRegistry()
    shell.register(registry)
    # Git: commit/push/GitHub — kabuğa `git commit` için düşülmesin.
    git_tool.register(registry)
    # Dosya araçları + `denetle`: yazılan kod, yazıldığı anda dilinin kendi
    # denetleyicisinden geçiyor ve sonuç aracın cevabına giriyor. Ayrı bir
    # kayıt satırı yok — tanı dosya yazmanın parçası, ayrı bir yetenek değil.
    files.register(registry)
    # İçerik arama: "X nerede geçiyor?" için dosya dosya okumak yerine tek araç.
    search.register(registry)
    # Yapısal arama: `grep` metin görür, `semboller` tanımı kullanımdan
    # ayırır — imzasını değiştireceğin fonksiyonun çağrılarını görmek için.
    kod.register(registry)
    # Değişiklik defteri: dosya araçlarının aldığı anlık görüntüleri listeler
    # ve geri alır (undo/redo).
    checkpoint.register(registry)
    # Test koşucusu: `denetle` sözdizimine bakar, `kos` kodu ÇALIŞTIRIR.
    # Tip/davranış hatalarını yakalayan tek şey bu.
    kosucu.register(registry)
    web.register(registry)
    jobs.register(registry)
    # İş akışı grafikleri: schedule tek prompt; workflow düğüm/kenar.
    workflow.register(registry)
    # Büyük iş planı (onay kapısı).
    plan_tool.register(registry)
    eyes.register(registry)
    # Kamera kesiti: opencv kuruluysa. Kayıt aracın kendi içinde
    # da denetleniyor; burada eksik bileşende listeye hiç girmiyor.
    from .. import watch as watching
    if watching.available():
        camera.register(registry)
    # Ekran ve el: yalnızca yakalama gerçekten mümkünse. Olmayan bir eli
    # listede göstermek, modeli boşa tıklatmak demek.
    if hands.available():
        hands.register(registry)
    # Tarayıcı (dornick chrome): Chrome/Edge kuruluysa kaydediliyor; kullanıcı
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
