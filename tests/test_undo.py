"""Çoklu düzenleme ve değişiklik defteri (checkpoint + undo).

İki vaat sınanıyor:

  * `edits` ATOMİK: biri bile tutmazsa dosyaya tek harf dokunulmaz ve hangi
    maddenin neden tutmadığı söylenir.
  * Her yazma öncesi anlık görüntü alınır; `undo` bunları listeler, tersine
    uygular ve geri almanın kendisi de kayıtlıdır (redo mümkün).
"""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path

import pytest

from dornick.config import Config
from dornick.events import EventLog
from dornick.session import Session
from dornick.tools import ToolContext, ToolRegistry
from dornick.tools import checkpoint
from dornick.tools import files as file_tools


@pytest.fixture()
def ctx(tmp_path: Path) -> ToolContext:
    config = Config.load(tmp_path)
    config.ensure_dirs()
    return ToolContext(
        config=config,
        session=Session(EventLog(tmp_path / ".dornick" / "s.jsonl"), "test-undo"),
        cancel=asyncio.Event(),
    )


@pytest.fixture()
def registry() -> ToolRegistry:
    reg = ToolRegistry()
    file_tools.register(reg)
    checkpoint.register(reg)
    return reg


async def call(registry: ToolRegistry, name: str, ctx: ToolContext, **args):
    return await registry.get(name).handler(args, ctx)


async def kur(registry: ToolRegistry, ctx: ToolContext, ad: str, icerik: str) -> Path:
    """Dosyayı araçla yazar ve okur — edit_file'ın bayatlık kontrolü için."""
    await call(registry, "write_file", ctx, path=ad, content=icerik)
    await call(registry, "read_file", ctx, path=ad)
    return ctx.sandbox.root / ad


# -- çoklu düzenleme ---------------------------------------------------


async def test_three_edits_land_in_one_write(
    registry: ToolRegistry, ctx: ToolContext
) -> None:
    path = await kur(registry, ctx, "a.txt", "bir\niki\nüç\n")

    result = await call(
        registry, "edit_file", ctx, path="a.txt",
        edits=[
            {"old": "iki", "new": "2"},
            {"old": "üç", "new": "3"},
            {"old": "bir", "new": "1"},
        ],
    )

    assert not result.is_error
    assert "3 değişiklik" in result.content
    assert path.read_text(encoding="utf-8") == "1\n2\n3\n"


async def test_the_line_is_the_first_change_in_file_order(
    registry: ToolRegistry, ctx: ToolContext
) -> None:
    """Arayüz sözleşmesi: diff kartı ilk değişikliğin satırından başlar —
    maddelerin veriliş sırası değil, dosyadaki konum belirler."""
    await kur(registry, ctx, "a.txt", "bir\niki\nüç\n")

    result = await call(
        registry, "edit_file", ctx, path="a.txt",
        edits=[{"old": "üç", "new": "3"}, {"old": "iki", "new": "2"}],
    )

    assert result.detail["line"] == 2


async def test_one_bad_item_stops_everything(
    registry: ToolRegistry, ctx: ToolContext
) -> None:
    path = await kur(registry, ctx, "a.txt", "bir\niki\n")

    result = await call(
        registry, "edit_file", ctx, path="a.txt",
        edits=[{"old": "bir", "new": "1"}, {"old": "boyle-bir-sey-yok", "new": "x"}],
    )

    assert result.is_error
    assert "2. madde" in result.content
    assert "Hiçbir değişiklik uygulanmadı" in result.content
    assert path.read_text(encoding="utf-8") == "bir\niki\n"  # dosya el değmemiş


async def test_an_ambiguous_item_names_itself(
    registry: ToolRegistry, ctx: ToolContext
) -> None:
    path = await kur(registry, ctx, "a.txt", "ayni\nayni\nbaska\n")

    result = await call(
        registry, "edit_file", ctx, path="a.txt",
        edits=[{"old": "baska", "new": "b"}, {"old": "ayni", "new": "x"}],
    )

    assert result.is_error
    assert "2. madde" in result.content
    assert path.read_text(encoding="utf-8") == "ayni\nayni\nbaska\n"


async def test_overlapping_items_are_a_conflict(
    registry: ToolRegistry, ctx: ToolContext
) -> None:
    """İki madde aynı bölgeye dokunursa sonuç sıraya bağlı olurdu — bu bir
    belirsizlik ve sırasından bağımsız yakalanmalı."""
    path = await kur(registry, ctx, "a.txt", "bir iki üç\n")

    result = await call(
        registry, "edit_file", ctx, path="a.txt",
        edits=[{"old": "bir iki", "new": "x"}, {"old": "iki üç", "new": "y"}],
    )

    assert result.is_error
    assert "çakışıyor" in result.content
    assert path.read_text(encoding="utf-8") == "bir iki üç\n"


async def test_the_single_old_new_form_still_works(
    registry: ToolRegistry, ctx: ToolContext
) -> None:
    path = await kur(registry, ctx, "a.txt", "eski hal\n")

    result = await call(registry, "edit_file", ctx, path="a.txt", old="eski", new="yeni")

    assert not result.is_error
    assert result.detail["line"] == 1
    assert path.read_text(encoding="utf-8") == "yeni hal\n"


async def test_neither_form_given_is_explained(
    registry: ToolRegistry, ctx: ToolContext
) -> None:
    await kur(registry, ctx, "a.txt", "x\n")

    result = await call(registry, "edit_file", ctx, path="a.txt")

    assert result.is_error
    assert "edits" in result.content


# -- değişiklik defteri ------------------------------------------------


async def test_write_then_edit_leaves_two_records(
    registry: ToolRegistry, ctx: ToolContext
) -> None:
    await kur(registry, ctx, "a.txt", "ilk\n")
    await call(registry, "edit_file", ctx, path="a.txt", old="ilk", new="son")

    result = await call(registry, "undo", ctx, action="list")

    assert not result.is_error
    assert result.detail["count"] == 2
    assert "write_file" in result.content
    assert "edit_file" in result.content
    assert "yeni oluşturuldu" in result.content  # ilk kayıt "yoktu" kaydı


async def test_restore_undoes_the_last_change(
    registry: ToolRegistry, ctx: ToolContext
) -> None:
    path = await kur(registry, ctx, "a.txt", "ilk\n")
    await call(registry, "edit_file", ctx, path="a.txt", old="ilk", new="son")
    assert path.read_text(encoding="utf-8") == "son\n"

    result = await call(registry, "undo", ctx, action="restore", n=1)

    assert not result.is_error
    assert path.read_text(encoding="utf-8") == "ilk\n"


async def test_restoring_a_restore_is_redo(
    registry: ToolRegistry, ctx: ToolContext
) -> None:
    """Geri alma kendini kaydeder; yanlış geri alan bir kez daha restore
    diyerek ileri döner."""
    path = await kur(registry, ctx, "a.txt", "ilk\n")
    await call(registry, "edit_file", ctx, path="a.txt", old="ilk", new="son")

    await call(registry, "undo", ctx, action="restore", n=1)
    assert path.read_text(encoding="utf-8") == "ilk\n"

    result = await call(registry, "undo", ctx, action="restore", n=1)

    assert not result.is_error
    assert path.read_text(encoding="utf-8") == "son\n"


async def test_restoring_a_creation_deletes_the_file(
    registry: ToolRegistry, ctx: ToolContext
) -> None:
    path = await kur(registry, ctx, "yeni.txt", "içerik\n")
    assert path.exists()

    result = await call(registry, "undo", ctx, action="restore", n=1)

    assert not result.is_error
    assert "silindi" in result.content
    assert not path.exists()


async def test_a_deleted_creation_can_come_back(
    registry: ToolRegistry, ctx: ToolContext
) -> None:
    path = await kur(registry, ctx, "yeni.txt", "içerik\n")
    await call(registry, "undo", ctx, action="restore", n=1)
    assert not path.exists()

    await call(registry, "undo", ctx, action="restore", n=1)

    assert path.read_text(encoding="utf-8") == "içerik\n"


async def test_a_two_step_restore_walks_backwards(
    registry: ToolRegistry, ctx: ToolContext
) -> None:
    path = await kur(registry, ctx, "a.txt", "v1\n")
    await call(registry, "edit_file", ctx, path="a.txt", old="v1", new="v2")
    await call(registry, "read_file", ctx, path="a.txt")
    await call(registry, "edit_file", ctx, path="a.txt", old="v2", new="v3")

    result = await call(registry, "undo", ctx, action="restore", n=2)

    assert not result.is_error
    assert path.read_text(encoding="utf-8") == "v1\n"


async def test_a_big_file_is_not_snapshotted_and_undo_says_so(
    registry: ToolRegistry, ctx: ToolContext
) -> None:
    """2 MB üstü dosyada görüntü atlanır; yazma DURMAZ ama undo o kaydı
    geri alamayacağını dürüstçe söyler."""
    buyuk = "x" * (checkpoint.GORUNTU_TAVANI + 1)
    path = await kur(registry, ctx, "dev.txt", buyuk)
    await call(registry, "write_file", ctx, path="dev.txt", content="küçüldü\n")
    assert path.read_text(encoding="utf-8") == "küçüldü\n"

    listing = await call(registry, "undo", ctx, action="list")
    assert "görüntü alınmadı" in listing.content

    result = await call(registry, "undo", ctx, action="restore", n=1)

    assert result.is_error
    assert "geri alınamaz" in result.content
    assert path.read_text(encoding="utf-8") == "küçüldü\n"  # yarım iş yok


async def test_restoring_more_than_recorded_is_refused(
    registry: ToolRegistry, ctx: ToolContext
) -> None:
    await kur(registry, ctx, "a.txt", "x\n")

    result = await call(registry, "undo", ctx, action="restore", n=99)

    assert result.is_error


async def test_files_outside_the_workshop_are_not_recorded(
    registry: ToolRegistry, ctx: ToolContext, tmp_path: Path
) -> None:
    """Defter atölyenin defteri: sandbox kapalıyken dışarı yazılan dosya
    kayda girmez (girseydi undo başkasının dosyasını değiştirebilirdi)."""
    ctx.sandbox.enabled = False
    disari = tmp_path / "disari.txt"
    await call(registry, "write_file", ctx, path=str(disari), content="x\n")

    result = await call(registry, "undo", ctx, action="list")

    assert "kayıtlı değişiklik yok" in result.content


async def test_old_session_folders_are_swept(
    ctx: ToolContext, tmp_path: Path
) -> None:
    kok = Path(ctx.config.state_dir) / checkpoint.KLASOR
    eski = kok / "bayat-oturum"
    eski.mkdir(parents=True)
    (eski / "kayit.jsonl").write_text("{}", encoding="utf-8")
    bayat = time.time() - (checkpoint.CLEANUP_DAYS + 1) * 86400
    os.utime(eski, (bayat, bayat))
    checkpoint._temizlenen.discard(kok)  # süreç bayrağını bu kök için sıfırla

    checkpoint.defter(ctx).save(ctx.sandbox.root / "olmayan.txt", "write_file")

    assert not eski.exists()


def test_the_ledger_never_travels(tmp_path: Path) -> None:
    """Transfer paketi .dornick'yi (dolayısıyla değişiklik görüntülerini)
    hiçbir koşulda taşımaz."""
    from dornick import transfer

    assert ".dornick" in transfer._ATLA
