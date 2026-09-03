"""Content search: `grep`.

Until now the agent answered "where does X occur?" either by dropping to
the shell (findstr, Select-String — different on every platform, a
permission question every time) or by reading files one by one. A single
typed tool ends that: pure Python (re + os.walk), no external binary, the
output format always the same.

Since reading is free everywhere, searching is free everywhere too —
`mutates=False`, it does not hit the permission gate.
"""

from __future__ import annotations

import asyncio
import fnmatch
import os
import re
from pathlib import Path
from typing import Any

from .base import ToolContext, ToolRegistry, ToolResult, object_schema
from .files import _resolve

# Directories skipped while scanning: tool debris, version control, the
# recycle bin (same reasoning as transfer._ATLA / gate._ATLA). .dornick is
# here too: session logs and change snapshots fill a search with junk.
_SKIP = frozenset({".git", "__pycache__", "node_modules", ".venv",
                   ".mypy_cache", ".geri-donusum", ".dornick"})

DEFAULT_RESULTS = 50
RESULT_CAP = 200
PER_FILE = 20                # a single file must not swallow the whole budget
OUTPUT_CAP = 60_000          # characters
FILE_SIZE_CAP = 4 * 1024 * 1024
_SNIFF = 8192                # head read for the binary heuristic


def register(registry: ToolRegistry) -> None:
    @registry.tool(
        name="grep",
        description="""
Dosyaların İÇİNDE metin arar (düzenli ifadeyle) ve eşleşmeleri
`yol:satır: içerik` biçiminde döndürür. Bir şeyin nerede geçtiğini bulmak
için dosyaları tek tek okuma; önce bununla ara, sonra ilgili dosyayı
read_file ile aç.

Varsayılan kök atölyendir; `path` ile herhangi bir dizinde ya da tek bir
dosyada arayabilirsin (okuma her yerde serbest). `glob` dosyaları süzer:
"**/*.py" gibi bir desen hem alt dizinlerde hem kökte çalışır. İkili
dosyalar ve araç artığı dizinler (.git, node_modules, __pycache__...)
kendiliğinden atlanır.
        """,
        input_schema=object_schema(
            {
                "pattern": {
                    "type": "string",
                    "description": "Aranacak düzenli ifade (Python re sözdizimi).",
                },
                "path": {
                    "type": "string",
                    "description": "Aranacak dizin ya da dosya (varsayılan: atölye kökü).",
                },
                "glob": {
                    "type": "string",
                    "description": 'Dosya süzgeci, ör. "**/*.py" ya da "*.md" (varsayılan: tümü).',
                },
                "context": {
                    "type": "integer",
                    "description": "Eşleşmenin çevresinden gösterilecek satır sayısı (0-3, varsayılan 0).",
                },
                "max_results": {
                    "type": "integer",
                    "description": f"Azami eşleşme sayısı (varsayılan {DEFAULT_RESULTS}, tavan {RESULT_CAP}).",
                },
            },
            required=["pattern"],
        ),
    )
    async def grep(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        pattern = str(args.get("pattern") or "")
        if not pattern:
            return ToolResult.error("Boş desen. Ne aradığını `pattern` alanına yaz.")
        try:
            rx = re.compile(pattern)
        except re.error as exc:
            return ToolResult.error(
                f"Düzenli ifade derlenemedi: {exc}. Özel karakterleri (( ) [ ] . * + ?) "
                "kaçırmayı unutma; düz metin arıyorsan re.escape edilmiş halini gönder."
            )

        root = _resolve(str(args.get("path") or "."), ctx)
        if not root.exists():
            return ToolResult.error(f"Yol yok: {root}")

        context = max(0, min(int(args.get("context") or 0), 3))
        cap = max(1, min(int(args.get("max_results") or DEFAULT_RESULTS), RESULT_CAP))

        def _scan() -> tuple[list[str], int, int, bool]:
            return _search(root, rx, args.get("glob"), context, cap, ctx.cancel)

        try:
            blocks, matches, file_count, clipped = await asyncio.to_thread(_scan)
        except OSError as exc:
            return ToolResult.error(f"Aranamadı: {exc}")

        if not matches:
            return ToolResult(
                content=f"'{pattern}' için eşleşme yok ({root}).",
                detail={"pattern": pattern, "matches": 0},
            )

        heading = f"'{pattern}' için {matches} eşleşme ({file_count} dosya):"
        if clipped:
            heading += " (kırpıldı — daraltmak için glob ya da daha özgül bir desen ver)"
        body = "\n\n".join(blocks)
        if len(body) > OUTPUT_CAP:
            body = body[:OUTPUT_CAP] + "\n… çıktı tavanı aşıldı, gerisi kırpıldı."
        return ToolResult(
            content=f"{heading}\n\n{body}",
            detail={"pattern": pattern, "matches": matches, "files": file_count},
        )


# -- scanning ----------------------------------------------------------


def _search(
    root: Path,
    rx: re.Pattern[str],
    glob: str | None,
    context: int,
    cap: int,
    cancel: asyncio.Event,
) -> tuple[list[str], int, int, bool]:
    """Walks the files; returns (file blocks, matches, file count, clipped?)."""
    blocks: list[str] = []
    total = 0
    files_hit = 0
    clipped = False
    chars = 0

    for path, rel in _files(root, glob):
        if cancel.is_set() or total >= cap or chars >= OUTPUT_CAP:
            clipped = clipped or total >= cap
            break
        lines = _read_lines(path)
        if lines is None:
            continue

        block: list[str] = []
        in_file = 0
        for no, line in enumerate(lines, 1):
            if not rx.search(line):
                continue
            in_file += 1
            total += 1
            if in_file > PER_FILE:
                block.append(f"{rel}: … dosyada daha fazla eşleşme var, kırpıldı.")
                clipped = True
                total -= 1  # the clipped match does not count
                break
            if context:
                start = max(0, no - 1 - context)
                for i in range(start, no - 1):
                    block.append(f"{rel}-{i + 1}- {lines[i].rstrip()}")
            block.append(f"{rel}:{no}: {line.rstrip()}")
            if context:
                end = min(len(lines), no + context)
                for i in range(no, end):
                    block.append(f"{rel}-{i + 1}- {lines[i].rstrip()}")
            if total >= cap:
                clipped = True
                break
        if block:
            files_hit += 1
            piece = "\n".join(block)
            chars += len(piece)
            blocks.append(piece)

    return blocks, total, files_hit, clipped


def _files(root: Path, glob: str | None):
    """Yields the files to search in order: (absolute path, displayed path)."""
    if root.is_file():
        yield root, str(root)
        return
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in _SKIP)
        for name in sorted(filenames):
            path = Path(dirpath) / name
            rel = path.relative_to(root).as_posix()
            # "**/*.py" does not match a file at the root in fnmatch; also
            # checking the bare name rescues both that and short patterns
            # like "*.py".
            if glob and not (fnmatch.fnmatch(rel, glob) or fnmatch.fnmatch(name, glob)):
                continue
            yield path, rel


def _read_lines(path: Path) -> list[str] | None:
    """The lines of a text file; None for a binary or a huge file."""
    try:
        if path.stat().st_size > FILE_SIZE_CAP:
            return None
        with path.open("rb") as f:
            head = f.read(_SNIFF)
        if b"\0" in head:  # binary heuristic: a null byte never occurs in text
            return None
        return path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
