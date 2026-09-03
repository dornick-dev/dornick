"""Content search tool (`grep`).

The tool's promise is simple: an answer to "where does X occur?" without
reading file by file, without an external binary, always in the same
format. The tests guard the limits of that promise: context lines, the
glob filter, binary/debris skipping, the limits.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from dornick.config import Config
from dornick.events import EventLog
from dornick.session import Session
from dornick.tools import ToolContext, ToolRegistry
from dornick.tools import search as search_tools


@pytest.fixture()
def ctx(tmp_path: Path) -> ToolContext:
    config = Config.load(tmp_path)
    config.ensure_dirs()
    return ToolContext(
        config=config,
        session=Session(EventLog(tmp_path / ".dornick" / "s.jsonl"), "test"),
        cancel=asyncio.Event(),
    )


@pytest.fixture()
def registry() -> ToolRegistry:
    reg = ToolRegistry()
    search_tools.register(reg)
    return reg


@pytest.fixture()
def workshop(ctx: ToolContext) -> Path:
    """A small file tree to search in."""
    root = ctx.sandbox.root
    (root / "notlar.md").write_text(
        "# Sınav notları\nsinav yarın\nbaşka bir satır\nsinav bitti\n",
        encoding="utf-8",
    )
    (root / "alt").mkdir()
    (root / "alt" / "kod.py").write_text(
        "def sinav():\n    return 42\n", encoding="utf-8"
    )
    (root / "alt" / "veri.bin").write_bytes(b"sinav\x00ikili")
    (root / "node_modules").mkdir()
    (root / "node_modules" / "paket.js").write_text("sinav", encoding="utf-8")
    return root


async def call(registry: ToolRegistry, ctx: ToolContext, **args):
    return await registry.get("grep").handler(args, ctx)


# -- matching ----------------------------------------------------------


async def test_matches_come_as_path_line_content(
    registry: ToolRegistry, ctx: ToolContext, workshop: Path
) -> None:
    result = await call(registry, ctx, pattern="sinav")

    assert not result.is_error
    assert "notlar.md:2: sinav yarın" in result.content
    assert "alt/kod.py:1: def sinav():" in result.content
    assert result.detail["matches"] == 3  # 2 in the md + 1 in the py


async def test_the_default_root_is_the_workshop(
    registry: ToolRegistry, ctx: ToolContext, workshop: Path, tmp_path: Path
) -> None:
    """Without `path` the search happens in the workshop, not in the user's home."""
    (tmp_path / "disarida.txt").write_text("sinav", encoding="utf-8")
    result = await call(registry, ctx, pattern="sinav")

    assert "disarida.txt" not in result.content


async def test_a_single_file_can_be_searched(
    registry: ToolRegistry, ctx: ToolContext, workshop: Path
) -> None:
    result = await call(registry, ctx, pattern="sinav", path=str(workshop / "notlar.md"))

    assert result.detail["matches"] == 2


async def test_context_lines_surround_the_match(
    registry: ToolRegistry, ctx: ToolContext, workshop: Path
) -> None:
    result = await call(registry, ctx, pattern="başka", context=1)

    assert "notlar.md-2- sinav yarın" in result.content
    assert "notlar.md:3: başka bir satır" in result.content
    assert "notlar.md-4- sinav bitti" in result.content


async def test_glob_filters_files(
    registry: ToolRegistry, ctx: ToolContext, workshop: Path
) -> None:
    result = await call(registry, ctx, pattern="sinav", glob="**/*.py")

    assert "kod.py" in result.content
    assert "notlar.md" not in result.content


async def test_a_short_glob_still_matches_at_the_root(
    registry: ToolRegistry, ctx: ToolContext, workshop: Path
) -> None:
    """Someone writing "*.md" means the file at the root; fnmatch's
    distinction should not be the model's problem."""
    result = await call(registry, ctx, pattern="sinav", glob="*.md")

    assert "notlar.md" in result.content


# -- skipping ----------------------------------------------------------


async def test_binary_files_are_skipped(
    registry: ToolRegistry, ctx: ToolContext, workshop: Path
) -> None:
    """A file with a null byte is not text; dumping lines from it produces junk."""
    result = await call(registry, ctx, pattern="sinav")

    assert "veri.bin" not in result.content


async def test_tool_debris_directories_are_skipped(
    registry: ToolRegistry, ctx: ToolContext, workshop: Path
) -> None:
    result = await call(registry, ctx, pattern="sinav")

    assert "node_modules" not in result.content


# -- limits ------------------------------------------------------------


async def test_the_total_limit_is_respected_and_reported(
    registry: ToolRegistry, ctx: ToolContext, workshop: Path
) -> None:
    for i in range(5):
        (workshop / f"cok{i}.txt").write_text("hedef\n" * 3, encoding="utf-8")

    result = await call(registry, ctx, pattern="hedef", max_results=4)

    assert result.detail["matches"] == 4
    assert "kırpıldı" in result.content


async def test_a_file_cannot_eat_the_whole_budget(
    registry: ToolRegistry, ctx: ToolContext, workshop: Path
) -> None:
    (workshop / "dev.txt").write_text("hedef\n" * 100, encoding="utf-8")
    (workshop / "ufak.txt").write_text("hedef\n", encoding="utf-8")

    result = await call(registry, ctx, pattern="hedef", max_results=200)

    assert "dosyada daha fazla eşleşme var" in result.content
    assert "ufak.txt:1: hedef" in result.content  # the next file got its turn


# -- errors ------------------------------------------------------------


async def test_no_match_is_not_an_error(
    registry: ToolRegistry, ctx: ToolContext, workshop: Path
) -> None:
    result = await call(registry, ctx, pattern="boyle-bir-sey-yok")

    assert not result.is_error
    assert "eşleşme yok" in result.content


async def test_a_broken_regex_teaches(
    registry: ToolRegistry, ctx: ToolContext, workshop: Path
) -> None:
    result = await call(registry, ctx, pattern="hedef(")

    assert result.is_error
    assert "derlenemedi" in result.content


async def test_a_missing_path_is_an_error(
    registry: ToolRegistry, ctx: ToolContext, workshop: Path
) -> None:
    result = await call(registry, ctx, pattern="x", path=str(workshop / "yok-dizin"))

    assert result.is_error


# -- registration ------------------------------------------------------


def test_searching_is_not_a_mutation(registry: ToolRegistry) -> None:
    """Reading is free everywhere; searching is reading and does not hit the permission gate."""
    spec = registry.get("grep")
    assert spec is not None
    assert not spec.mutates
    assert spec.parallel_safe
