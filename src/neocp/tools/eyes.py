"""Bakma aracı — ajanın gözünü kullanması.

Kamera sürekli açık ve kare alıyor ama **hiçbiri kendiliğinden modele
gitmiyor**. Her kareyi göndermek dakikada onlarca istek, saniyede binlerce
token demek: kullanılamaz.

Bunun yerine kareler Python tarafında, bellekte duruyor. Model bakmaya karar
verdiğinde buradan tek bir kare alıyor.

İkinci ve daha ucuz soru "az önce bir şey oldu mu": onun cevabı hareket
geçmişinden geliyor ve modele hiç uğramıyor. Boş bir odada "bir şey oldu mu"
sorusu tek bir görüntü bile göndermeden cevaplanabiliyor.
"""

from __future__ import annotations

from typing import Any

from .base import ToolContext, ToolRegistry, ToolResult, object_schema

DESCRIPTION = """
Kameraya bakar. Kamera sürekli açık ama kareler sana kendiliğinden gelmiyor —
bakmaya sen karar veriyorsun.

  now     şu anki kareyi al ve gör. Kullanıcı "beni görüyor musun",
          "elimde ne var", "şu an ne görüyorsun" dediğinde bunu kullan.
          Kullanıcı bir şeyi gösterip indirmiş olabilir ("az önce ne
          gösterdim", "buna baktın mı") — o zaman `back_seconds` ver:
          son saniyelerin en net karesi seçilir.
  motion  son N saniyede hareket oldu mu — **görüntü almadan**. "Bir şey
          oldu mu", "biri geldi mi" gibi sorularda önce buna bak; sessizse
          kare almaya gerek yok.

Her karede bakmaya kalkma: bir görüntü bağlamda 1.5–4.8k token. Bakman
gereken bir sebep varsa bak.
"""


def register(registry: ToolRegistry) -> None:
    @registry.tool(
        name="look",
        description=DESCRIPTION,
        input_schema=object_schema(
            {
                "action": {
                    "type": "string",
                    "enum": ["now", "motion"],
                    "description": "now: kareyi gör. motion: hareket özeti (görüntüsüz).",
                },
                "seconds": {
                    "type": "integer",
                    "description": "motion için geriye bakılacak süre (varsayılan 60).",
                },
                "back_seconds": {
                    "type": "integer",
                    "description": (
                        "now için: kaç saniye öncesine bakılacağı (0 = şu an, "
                        "en fazla 10). Kullanıcı gösterdiği şeyi indirmiş "
                        "olabilirse 3-5 ver."
                    ),
                },
            },
            required=["action"],
        ),
    )
    async def look(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        lens = ctx.lens
        # Susturulmuş göz "kamera kapalı" değil: kullanıcı istedi diye
        # bakılmıyor. Ayrımı söylemek gerekiyor — model aksi halde kamerayı
        # açtırmaya çalışıyor.
        if lens is not None and getattr(lens, "snoozed", False):
            return ToolResult.error(
                "Göz kapalı: kullanıcı izlememeni istedi. Kendiliğinden açma; "
                "üstteki kamera ikonundan veya sohbette 'kamerayı aç' deyince açılır."
            )
        if lens is None or not lens.live:
            # Ayarlardan kapatılmışsa bu bir tercih, bir eksiklik değil —
            # model kullanıcıyı kamerayı açmaya ikna etmeye çalışmamalı.
            if not bool(getattr(getattr(ctx.config, "camera", None), "enabled", False)):
                return ToolResult.error(
                    "Kamera kapalı. Bakılmaz ve varmış gibi davranılmaz; "
                    "üstteki ikondan veya 'kamerayı aç' deyince açılır."
                )
            return ToolResult.error(
                "Kamera açık değil. Üstteki kamera ikonundan açılabilir."
            )

        action = str(args.get("action") or "")

        if action == "motion":
            seconds = max(5, min(int(args.get("seconds") or 60), 120))
            seen = lens.motion(seconds)
            if seen["quiet"]:
                return ToolResult(
                    f"Son {seconds} saniyede hareket yok. Kameraya bakmaya gerek "
                    "olmayabilir.",
                    detail=seen,
                )
            return ToolResult(
                f"Son {seconds} saniyede hareket var: {seen['busy']}/{seen['frames']} "
                f"karede, en yüksek değişim %{int(seen['peak'] * 100)}. "
                "Ne olduğunu görmek için `look action=now`.",
                detail=seen,
            )

        if action == "now":
            back = max(0, min(int(args.get("back_seconds") or 0), 10))
            if back and hasattr(lens, "recall"):
                frame, age = lens.recall(float(back))
            else:
                frame, age = lens.snapshot()
            if not frame:
                return ToolResult.error("Kare alınamadı; kamera henüz ısınıyor olabilir.")

            # Görüntü araç sonucunda taşınamıyor: OpenAI sözleşmesi role=tool
            # içeriğinin dize olmasını istiyor. Bu yüzden kare `detail` ile
            # döngüye veriliyor ve bir sonraki kullanıcı turuna iliştiriliyor.
            from .. import sight

            ozet = sight.analyze_url(frame)
            metin = f"Kare alındı ({age:.0f} saniye önce). Aşağıda görüyorsun."
            if ozet:
                metin += f"\nYerel GPU analizi: {ozet}"
            return ToolResult(
                metin, detail={"image": frame, "age": round(age, 1)},
            )

        return ToolResult.error("`action` now ya da motion olmalı.")
