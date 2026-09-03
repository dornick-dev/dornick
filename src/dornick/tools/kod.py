"""`semboller` aracı: kodda yapısal gezinme.

`grep` metin görür, bu araç yapı görür. "Bu fonksiyon nerede tanımlı,
nereden çağrılıyor?" sorusunun cevabı `grep`te bir yığın eşleşmedir —
tanım, çağrı, yorum, dize ve benzer adlı başka semboller aynı listede.
Burada tanım ayrı, kullanım ayrı; her satır `dosya:satır: imza`.

Okuma aracı: `mutates=False`. Hiçbir şey çalıştırmıyor, hiçbir şey
yazmıyor — yalnızca kaynak dosyaları okuyup ayrıştırıyor.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from .. import symbols
from .base import ToolContext, ToolRegistry, ToolResult, object_schema


def register(registry: ToolRegistry) -> None:
    @registry.tool(
        name="semboller",
        description="""
Bir projede fonksiyon/sınıf/metot TANIMLARINI ve KULLANIMLARINI bulur.

Ne zaman kullan: "bu fonksiyon nerede tanımlı?", "burayı değiştirsem
nereler kırılır?", "bu sınıf nereden kuruluyor?" — yani bir ismin yapısal
karşılığını ararken. Değiştireceğin bir fonksiyonun çağrılarını görmeden
imzasını değiştirme.

Ne zaman kullanma: serbest metin ararken (`grep` daha uygun): bir hata
mesajı, bir CSS sınıfı, bir yapılandırma değeri.

Kapsam: Python `ast` ile ayrıştırılır — kesin. PHP, JS ve TS dikkatli
düzenli ifadeyle taranır — yorum satırları elenir ama dize içindeki bir
isim karışabilir; sonucun altında hangisinin geçerli olduğu yazar. Başka
dillerde yapısal arama YOKTUR ve araç bunu söyler; o durumda `grep` kullan.

`path` vermezsen atölye taranır. Tarama 3 klasör derinliğinde durur ve
bağımlılık klasörlerine (node_modules, vendor, .venv) hiç girmez.
        """,
        input_schema=object_schema(
            {
                "sorgu": {
                    "type": "string",
                    "description": "Aranan sembolün adı (fonksiyon, sınıf, metot).",
                },
                "path": {
                    "type": "string",
                    "description": "Taranacak klasör ya da içindeki bir dosya. "
                                   "Verilmezse atölye.",
                },
                "tur": {
                    "type": "string",
                    "enum": ["tanim", "kullanim", "hepsi"],
                    "description": "Yalnızca tanımlar, yalnızca kullanımlar ya "
                                   "da ikisi (varsayılan hepsi).",
                },
                "dil": {
                    "type": "string",
                    "enum": ["python", "php", "js", "ts"],
                    "description": "Yalnızca bu dildeki dosyalara bak "
                                   "(isteğe bağlı).",
                },
            },
            required=["sorgu"],
        ),
        mutates=False,
    )
    async def semboller_araci(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        sorgu = str(args.get("sorgu") or "").strip()
        if not sorgu:
            return ToolResult.error(
                "`sorgu` boş. Aradığın fonksiyon/sınıf adını ver."
            )
        # Bir sembol adı boşluk taşımaz; taşıyorsa model serbest metin
        # arıyor demektir ve doğru araç `grep`.
        if any(ch.isspace() for ch in sorgu):
            return ToolResult.error(
                f"'{sorgu}' bir sembol adı değil (boşluk içeriyor). Bu araç "
                "fonksiyon/sınıf adı arar; serbest metin için `grep` kullan."
            )

        kok = _root(args, ctx)
        if not kok.is_dir():
            return ToolResult.error(f"Klasör yok: {kok}")

        tur = str(args.get("tur") or "hepsi")
        dil = str(args.get("dil") or "") or None

        sonuc = await asyncio.to_thread(
            symbols.ara, kok, sorgu, tur=tur, dil=dil)
        return ToolResult(
            content=sonuc.metin(tur=tur),
            detail={
                "sorgu": sorgu,
                "kok": str(kok),
                "tanim": len(sonuc.tanimlar),
                "kullanim": len(sonuc.use_log),
                "taranan": sonuc.taranan,
                "kesin": sonuc.kesin,
            },
        )


def _root(args: dict[str, Any], ctx: ToolContext) -> Path:
    """Taranacak klasör: verilen yol (dosyaysa klasörü), yoksa atölye."""
    ham = str(args.get("path") or "").strip()
    if not ham:
        return ctx.sandbox.root if ctx.sandbox.enabled else ctx.workspace
    yol = Path(ham).expanduser()
    if not yol.is_absolute():
        temel = ctx.sandbox.root if ctx.sandbox.enabled else ctx.workspace
        yol = temel / yol
    return yol if yol.is_dir() else yol.parent
