"""Dosya araçları.

Kabuktan `cat`/`echo` yerine bunları terfi ettirmenin sebebi: harness'a
tipli argümanlar verirler. Böylece yazma öncesi bayatlık kontrolü yapılabilir,
izin kuralları yola göre yazılabilir, arayüz diff gösterebilir. Opak bir
kabuk dizesinde bunların hiçbiri mümkün değil.
"""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path
from typing import Any

from ..sandbox import OutsideSandbox
from .base import ToolContext, ToolRegistry, ToolResult, object_schema

MAX_READ_CHARS = 60_000
MAX_LIST_ENTRIES = 400


def _resolve(raw: str, ctx: ToolContext) -> Path:
    """Göreli yolları atölyeye, mutlak yolları olduğu gibi çözer.

    Göreli yolun atölyeye düşmesi bilinçli: ajan çoğu zaman kendi işini
    yapıyor ve "site/index.html" yazdığında bunun kendi klasöründe olmasını
    bekliyor. Dışarıdaki bir dosyaya mutlak yolla erişiliyor — okumak zaten
    her yerde serbest.
    """
    path = Path(raw).expanduser()
    if path.is_absolute():
        return path
    if not ctx.sandbox.enabled:
        return ctx.workspace / path

    root = ctx.sandbox.root
    # Model atölyenin adını yola kendisi ekliyor ("atolye/site/index.html"):
    # sistem promptunda klasörün tam yolu yazıyor ve oradan çıkarım yapıyor.
    # Olduğu gibi birleştirmek `atolye/atolye/...` üretiyordu — dosya doğru
    # yere değil bir alt klasöre düşüyor ve kullanıcı aradığını bulamıyor.
    parts = path.parts
    if parts and parts[0] == root.name:
        path = Path(*parts[1:]) if len(parts) > 1 else Path()
    return root / path


def _guard(path: Path, ctx: ToolContext) -> ToolResult | None:
    """Yazma sınırı. İhlal varsa hatayı döndürür, yoksa None.

    Hata metni ne yapılacağını da söylüyor: modelin bir sonraki turda
    `copy_in`e yönelmesi için "izin yok" demek yetmiyor.
    """
    try:
        ctx.sandbox.check(path)
    except OutsideSandbox as exc:
        return ToolResult.error(str(exc))
    return None


def register(registry: ToolRegistry) -> None:
    # Yazma öncesi bayatlık kontrolü için: yol -> son okunduğundaki mtime_ns.
    seen: dict[Path, int] = {}

    @registry.tool(
        name="read_file",
        description="""
Bir metin dosyasını okur. Uzun dosyalar için `offset` ve `limit` ile
satır aralığı verilebilir; çıktı satır numaralı gelir.
        """,
        input_schema=object_schema(
            {
                "path": {"type": "string", "description": "Dosya yolu (göreli ya da mutlak)."},
                "offset": {"type": "integer", "description": "Başlangıç satırı (1'den başlar)."},
                "limit": {"type": "integer", "description": "Okunacak satır sayısı."},
            },
            required=["path"],
        ),
    )
    async def read_file(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        path = _resolve(args["path"], ctx)
        if not path.exists():
            return ToolResult.error(f"Dosya yok: {path}")
        if path.is_dir():
            return ToolResult.error(f"{path} bir dizin. İçeriği için list_dir kullan.")

        def _read() -> tuple[str, int]:
            data = path.read_text(encoding="utf-8", errors="replace")
            return data, path.stat().st_mtime_ns

        try:
            text, mtime = await asyncio.to_thread(_read)
        except OSError as exc:
            return ToolResult.error(f"Okunamadı: {exc}")

        seen[path] = mtime

        lines = text.splitlines()
        offset = max(1, int(args.get("offset") or 1))
        limit = int(args.get("limit") or len(lines))
        window = lines[offset - 1 : offset - 1 + limit]

        numbered = "\n".join(f"{offset + i:>6}\t{line}" for i, line in enumerate(window))
        if len(numbered) > MAX_READ_CHARS:
            numbered = (
                numbered[:MAX_READ_CHARS]
                + f"\n\n... kırpıldı. Devamı için offset={offset + len(window) // 2} kullan."
            )

        footer = ""
        if offset > 1 or offset - 1 + limit < len(lines):
            footer = f"\n\n[{len(lines)} satırın {offset}-{offset + len(window) - 1} arası]"

        return ToolResult(content=(numbered or "(dosya boş)") + footer)

    @registry.tool(
        name="write_file",
        description="""
Dosyayı verilen içerikle yazar; yoksa oluşturur, varsa üzerine yazar.

Var olan bir dosyanın üzerine yazmadan önce onu read_file ile okumuş olman
gerekir. Bu, senin görmediğin değişiklikleri sessizce ezmeni engeller.
Küçük değişiklikler için write_file yerine edit_file kullan.
        """,
        input_schema=object_schema(
            {
                "path": {"type": "string", "description": "Dosya yolu."},
                "content": {"type": "string", "description": "Dosyanın tam yeni içeriği."},
            },
            required=["path", "content"],
        ),
        mutates=True,
        parallel_safe=False,
    )
    async def write_file(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        path = _resolve(args["path"], ctx)
        if refused := _guard(path, ctx):
            return refused
        content = args.get("content", "")

        if path.exists():
            if path not in seen:
                return ToolResult.error(
                    f"{path} zaten var ve bu oturumda okunmadı. "
                    "Üzerine yazmadan önce read_file ile oku."
                )
            if path.stat().st_mtime_ns != seen[path]:
                return ToolResult.error(
                    f"{path} sen okuduktan sonra değişti. Tekrar oku, sonra yaz."
                )

        def _write() -> int:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            return path.stat().st_mtime_ns

        try:
            seen[path] = await asyncio.to_thread(_write)
        except OSError as exc:
            return ToolResult.error(f"Yazılamadı: {exc}")

        return ToolResult(
            content=f"{path} yazıldı ({len(content.splitlines())} satır).",
            detail={"path": str(path), "bytes": len(content.encode("utf-8"))},
        )

    @registry.tool(
        name="edit_file",
        description="""
Bir dosyada tam metin değişimi yapar. `old` metni dosyada tam olarak bir kez
geçmelidir — sıfır ya da birden fazla eşleşmede işlem yapılmaz ve hata döner.
Benzersiz kılmak için etrafından yeterince bağlam al.

Dosyayı önce read_file ile okumuş olman gerekir.
        """,
        input_schema=object_schema(
            {
                "path": {"type": "string", "description": "Dosya yolu."},
                "old": {"type": "string", "description": "Değiştirilecek tam metin."},
                "new": {"type": "string", "description": "Yerine yazılacak metin."},
            },
            required=["path", "old", "new"],
        ),
        mutates=True,
        parallel_safe=False,
    )
    async def edit_file(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        path = _resolve(args["path"], ctx)
        if refused := _guard(path, ctx):
            return refused
        old, new = args["old"], args["new"]

        if not path.exists():
            return ToolResult.error(f"Dosya yok: {path}")
        if path not in seen:
            return ToolResult.error(f"{path} bu oturumda okunmadı. Önce read_file ile oku.")

        text = await asyncio.to_thread(path.read_text, encoding="utf-8")
        count = text.count(old)
        if count == 0:
            return ToolResult.error(
                "Aranan metin dosyada yok. Girintiyi ve satır sonlarını birebir eşleştir; "
                "emin değilsen dosyayı tekrar oku."
            )
        if count > 1:
            return ToolResult.error(
                f"Aranan metin {count} kez geçiyor, hangisi olduğu belirsiz. "
                "Öncesinden/sonrasından bağlam ekleyerek benzersizleştir."
            )

        def _apply() -> int:
            path.write_text(text.replace(old, new, 1), encoding="utf-8")
            return path.stat().st_mtime_ns

        seen[path] = await asyncio.to_thread(_apply)
        return ToolResult(content=f"{path} güncellendi.", detail={"path": str(path)})

    @registry.tool(
        name="copy_in",
        description="""
Dışarıdaki bir dosyayı ya da klasörü atölyene kopyalar. Orijinaline
dokunulmaz. Atölye dışına yazamadığın için, üzerinde çalışman gereken bir
dosya varsa yolu budur.

`to` verilmezse dosya atölyenin köküne kendi adıyla düşer.
        """,
        input_schema=object_schema(
            {
                "path": {"type": "string", "description": "Kopyalanacak kaynak yolu."},
                "to": {
                    "type": "string",
                    "description": "Atölye içinde hedef yol (göreli).",
                },
            },
            required=["path"],
        ),
        mutates=True,
        parallel_safe=False,
    )
    async def copy_in(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        source = Path(args["path"]).expanduser()
        if not source.is_absolute():
            source = ctx.workspace / source
        if not source.exists():
            return ToolResult.error(f"Kaynak yok: {source}")

        target = _resolve(args.get("to") or source.name, ctx)
        if refused := _guard(target, ctx):
            return refused
        if target.exists():
            return ToolResult.error(
                f"{target} zaten var. Üzerine yazmak istiyorsan başka bir ad ver "
                "ya da önce sil."
            )

        def _copy() -> int:
            target.parent.mkdir(parents=True, exist_ok=True)
            if source.is_dir():
                shutil.copytree(source, target)
                return sum(1 for _ in target.rglob("*") if _.is_file())
            shutil.copy2(source, target)
            return 1

        try:
            count = await asyncio.to_thread(_copy)
        except OSError as exc:
            return ToolResult.error(f"Kopyalanamadı: {exc}")

        # Kopya okunmuş sayılıyor: az önce bu süreç yazdı, bayatlık kontrolü
        # burada modeli gereksiz bir read_file turuna zorlardı.
        if target.is_file():
            seen[target] = target.stat().st_mtime_ns

        return ToolResult(
            content=f"{source} → {target} ({count} dosya).",
            detail={"path": str(target), "files": count},
        )

    @registry.tool(
        name="list_dir",
        description="""
Bir dizinin içeriğini listeler. `pattern` verilirse glob deseniyle özyinelemeli
arar (örn. "**/*.py"). Dizinler sonunda / ile gösterilir.
        """,
        input_schema=object_schema(
            {
                "path": {"type": "string", "description": "Dizin yolu."},
                "pattern": {"type": "string", "description": "Özyinelemeli glob deseni."},
            },
            required=["path"],
        ),
    )
    async def list_dir(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        root = _resolve(args["path"], ctx)
        if not root.is_dir():
            return ToolResult.error(f"Dizin yok: {root}")

        pattern = args.get("pattern")

        def _scan() -> list[str]:
            entries = sorted(root.glob(pattern)) if pattern else sorted(root.iterdir())
            return [
                f"{p.relative_to(root)}{'/' if p.is_dir() else ''}"
                for p in entries[:MAX_LIST_ENTRIES]
            ]

        try:
            names = await asyncio.to_thread(_scan)
        except OSError as exc:
            return ToolResult.error(f"Listelenemedi: {exc}")

        if not names:
            return ToolResult(content="(boş)")

        body = "\n".join(names)
        if len(names) == MAX_LIST_ENTRIES:
            body += f"\n\n... ilk {MAX_LIST_ENTRIES} girdi gösterildi, daha var."
        return ToolResult(content=f"{root}\n{body}")
