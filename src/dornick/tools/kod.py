"""The `semboller` tool: structural navigation in code.

`grep` sees text, this tool sees structure. The answer to "where is this
function defined, where is it called from?" is a pile of matches in
`grep` — definition, call, comment, string and other similarly named
symbols all in one list. Here definitions are separate from uses; every
line is `file:line: signature`.

A read tool: `mutates=False`. It runs nothing, writes nothing — it only
reads and parses source files.
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
    async def symbols_tool(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        query = str(args.get("sorgu") or "").strip()
        if not query:
            return ToolResult.error(
                "`sorgu` boş. Aradığın fonksiyon/sınıf adını ver."
            )
        # A symbol name carries no whitespace; if it does, the model is
        # searching free text and the right tool is `grep`.
        if any(ch.isspace() for ch in query):
            return ToolResult.error(
                f"'{query}' bir sembol adı değil (boşluk içeriyor). Bu araç "
                "fonksiyon/sınıf adı arar; serbest metin için `grep` kullan."
            )

        root = _root(args, ctx)
        if not root.is_dir():
            return ToolResult.error(f"Klasör yok: {root}")

        kind = str(args.get("tur") or "hepsi")
        lang = str(args.get("dil") or "") or None

        result = await asyncio.to_thread(
            symbols.ara, root, query, tur=kind, dil=lang)
        return ToolResult(
            content=result.metin(tur=kind),
            detail={
                "sorgu": query,
                "kok": str(root),
                "tanim": len(result.tanimlar),
                "kullanim": len(result.use_log),
                "taranan": result.taranan,
                "kesin": result.kesin,
            },
        )


def _root(args: dict[str, Any], ctx: ToolContext) -> Path:
    """The folder to scan: the given path (its folder if a file), else the workshop."""
    raw = str(args.get("path") or "").strip()
    if not raw:
        return ctx.sandbox.root if ctx.sandbox.enabled else ctx.workspace
    path = Path(raw).expanduser()
    if not path.is_absolute():
        base = ctx.sandbox.root if ctx.sandbox.enabled else ctx.workspace
        path = base / path
    return path if path.is_dir() else path.parent
