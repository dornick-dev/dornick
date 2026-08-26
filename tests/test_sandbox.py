"""Atölye sınırı.

Buradaki tek kural — okuma her yerde, yazma yalnızca atölyede — sessizce
delinebilecek üç yer var: `..` ile yukarı çıkmak, sembolik bağ üzerinden
dışarı taşmak, ve henüz var olmayan bir dosyanın nerede olduğunun yanlış
hesaplanması. Üçü de aşağıda.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from neocp.config import Config
from neocp.events import EventLog
from neocp.sandbox import OutsideSandbox, Sandbox
from neocp.session import Session
from neocp.tools import ToolContext, ToolRegistry
from neocp.tools import files as file_tools


@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    (tmp_path / "gizli.txt").write_text("kullanıcının dosyası", encoding="utf-8")
    return tmp_path


@pytest.fixture()
def ctx(workspace: Path) -> ToolContext:
    config = Config.load(workspace)
    config.ensure_dirs()
    session = Session(EventLog(workspace / ".neocp" / "s.jsonl"), "test")
    return ToolContext(config=config, session=session, cancel=asyncio.Event())


@pytest.fixture()
def registry() -> ToolRegistry:
    reg = ToolRegistry()
    file_tools.register(reg)
    return reg


async def call(registry: ToolRegistry, name: str, ctx: ToolContext, **args):
    return await registry.get(name).handler(args, ctx)


# -- sınır hesabı ------------------------------------------------------


def test_a_path_that_does_not_exist_yet_is_still_placed(tmp_path: Path) -> None:
    """Yazma çoğunlukla henüz olmayan bir dosyaya yapılıyor; sınır kontrolü
    dosyanın varlığına bağlı olamaz."""
    box = Sandbox.open(tmp_path)

    assert box.contains(box.root / "site" / "index.html")
    assert not box.contains(tmp_path / "baska" / "index.html")


def test_climbing_out_with_dot_dot_is_caught(tmp_path: Path) -> None:
    box = Sandbox.open(tmp_path)

    with pytest.raises(OutsideSandbox):
        box.check(box.root / ".." / "kacak.txt")


def test_a_symlink_pointing_outside_is_caught(tmp_path: Path) -> None:
    """Bağ çözülmeden karşılaştırılırsa sınır kâğıt üstünde kalıyor."""
    box = Sandbox.open(tmp_path)
    outside = tmp_path / "disarisi"
    outside.mkdir()
    try:
        (box.root / "kopru").symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("bu sistemde sembolik bağ kurulamıyor")

    with pytest.raises(OutsideSandbox):
        box.check(box.root / "kopru" / "kacak.txt")


def test_the_root_itself_counts_as_inside(tmp_path: Path) -> None:
    box = Sandbox.open(tmp_path)
    assert box.contains(box.root)


def test_a_disabled_sandbox_lets_everything_through(tmp_path: Path) -> None:
    """Kapatmak bilinçli bir karar; kapalıyken kısıt hiç uygulanmamalı."""
    box = Sandbox.open(tmp_path, enabled=False)
    assert box.check(tmp_path / "her" / "yer.txt")


def test_an_absolute_directory_can_be_used(tmp_path: Path) -> None:
    elsewhere = tmp_path / "baska" / "yer"
    box = Sandbox.open(tmp_path / "ws", str(elsewhere))

    assert box.root == elsewhere.resolve()
    assert box.root.is_dir()


# -- araçlar -----------------------------------------------------------


async def test_relative_writes_land_in_the_workshop(
    registry: ToolRegistry, ctx: ToolContext
) -> None:
    """Ajan "site/index.html" yazdığında bunun kendi klasöründe olmasını
    bekliyor; çalışma alanının köküne düşmesi kullanıcının dosyalarının
    arasına karışmak demek."""
    result = await call(registry, "write_file", ctx, path="site/index.html", content="<h1>x</h1>")

    assert not result.is_error
    assert (ctx.sandbox.root / "site" / "index.html").read_text(encoding="utf-8") == "<h1>x</h1>"


async def test_writing_outside_is_refused_with_a_way_forward(
    registry: ToolRegistry, ctx: ToolContext, workspace: Path
) -> None:
    """"İzin yok" demek yetmiyor: model bir sonraki turda ne yapacağını
    bilmeli, yoksa aynı çağrıyı tekrarlıyor."""
    result = await call(
        registry, "write_file", ctx, path=str(workspace / "gizli.txt"), content="ezildi"
    )

    assert result.is_error
    assert "copy_in" in result.content
    assert workspace.joinpath("gizli.txt").read_text(encoding="utf-8") == "kullanıcının dosyası"


async def test_editing_outside_is_refused_too(
    registry: ToolRegistry, ctx: ToolContext, workspace: Path
) -> None:
    """write_file kapatılıp edit_file açık kalırsa sınır hiç yok demektir."""
    target = str(workspace / "gizli.txt")
    await call(registry, "read_file", ctx, path=target)

    result = await call(registry, "edit_file", ctx, path=target, old="kullanıcının", new="benim")

    assert result.is_error
    assert workspace.joinpath("gizli.txt").read_text(encoding="utf-8") == "kullanıcının dosyası"


async def test_reading_outside_stays_free(
    registry: ToolRegistry, ctx: ToolContext, workspace: Path
) -> None:
    """Kısıt yazmada; ajan bilgisayardaki her şeyi görebilmeli."""
    result = await call(registry, "read_file", ctx, path=str(workspace / "gizli.txt"))

    assert not result.is_error
    assert "kullanıcının dosyası" in result.content


async def test_copy_in_brings_a_file_without_touching_the_original(
    registry: ToolRegistry, ctx: ToolContext, workspace: Path
) -> None:
    result = await call(registry, "copy_in", ctx, path=str(workspace / "gizli.txt"))

    assert not result.is_error
    copy = ctx.sandbox.root / "gizli.txt"
    assert copy.read_text(encoding="utf-8") == "kullanıcının dosyası"
    assert workspace.joinpath("gizli.txt").exists()


async def test_the_copy_is_immediately_editable(
    registry: ToolRegistry, ctx: ToolContext, workspace: Path
) -> None:
    """Kopyayı az önce bu süreç yazdı; bayatlık kontrolü modeli gereksiz bir
    read_file turuna zorlamamalı."""
    await call(registry, "copy_in", ctx, path=str(workspace / "gizli.txt"), to="calisma.txt")

    result = await call(registry, "edit_file", ctx, path="calisma.txt",
                        old="kullanıcının", new="benim")

    assert not result.is_error
    assert (ctx.sandbox.root / "calisma.txt").read_text(encoding="utf-8") == "benim dosyası"


async def test_copy_in_cannot_be_used_to_escape(
    registry: ToolRegistry, ctx: ToolContext, workspace: Path
) -> None:
    """Hedef de sınır kontrolünden geçmeli; yoksa kopyalama bir kaçış yolu."""
    result = await call(
        registry, "copy_in", ctx, path=str(workspace / "gizli.txt"), to="../kacak.txt"
    )

    assert result.is_error
    assert not (workspace / "kacak.txt").exists()


async def test_copy_in_does_not_overwrite(
    registry: ToolRegistry, ctx: ToolContext, workspace: Path
) -> None:
    await call(registry, "copy_in", ctx, path=str(workspace / "gizli.txt"), to="a.txt")
    result = await call(registry, "copy_in", ctx, path=str(workspace / "gizli.txt"), to="a.txt")

    assert result.is_error
    assert "zaten var" in result.content


async def test_a_whole_directory_can_be_copied(
    registry: ToolRegistry, ctx: ToolContext, workspace: Path
) -> None:
    source = workspace / "proje"
    (source / "src").mkdir(parents=True)
    (source / "src" / "a.py").write_text("print(1)", encoding="utf-8")
    (source / "okuma.md").write_text("# proje", encoding="utf-8")

    result = await call(registry, "copy_in", ctx, path=str(source), to="proje")

    assert not result.is_error
    assert (ctx.sandbox.root / "proje" / "src" / "a.py").exists()
    assert result.detail["files"] == 2


# -- prompt ------------------------------------------------------------


def test_the_agent_is_told_where_it_lives(tmp_path: Path) -> None:
    """Kural sistem promptunda yazmazsa model her yazmada duvara çarpıp
    deneme yanılmayla öğreniyor."""
    briefing = Sandbox.open(tmp_path).briefing()

    assert "atolye" in briefing.lower()
    assert "copy_in" in briefing


def test_a_disabled_sandbox_says_nothing(tmp_path: Path) -> None:
    assert Sandbox.open(tmp_path, enabled=False).briefing() == ""


async def test_the_workshop_name_is_not_nested(
    registry: ToolRegistry, ctx: ToolContext
) -> None:
    """Model atölyenin adını yola kendisi ekliyor.

    Sistem promptunda klasörün tam yolu yazıyor ve oradan çıkarım yapıp
    "atolye/merhaba.txt" diyor. Olduğu gibi birleştirmek `atolye/atolye/...`
    üretiyordu — gerçek bir koşuda tam olarak bu oldu ve dosya bir alt
    klasöre düştü.
    """
    name = ctx.sandbox.root.name
    result = await call(registry, "write_file", ctx, path=f"{name}/merhaba.txt", content="selam")

    assert not result.is_error
    assert (ctx.sandbox.root / "merhaba.txt").read_text(encoding="utf-8") == "selam"
    assert not (ctx.sandbox.root / name).exists()


async def test_a_deeper_path_keeps_its_shape(
    registry: ToolRegistry, ctx: ToolContext
) -> None:
    name = ctx.sandbox.root.name
    await call(registry, "write_file", ctx, path=f"{name}/site/index.html", content="<h1>x</h1>")

    assert (ctx.sandbox.root / "site" / "index.html").exists()


async def test_a_folder_that_only_shares_the_name_is_untouched(
    registry: ToolRegistry, ctx: ToolContext
) -> None:
    """Kırpma yalnızca ilk parçada; içeride aynı adı taşıyan bir klasör
    olabilir ve o kalmalı."""
    name = ctx.sandbox.root.name
    await call(registry, "write_file", ctx, path=f"proje/{name}/not.txt", content="x")

    assert (ctx.sandbox.root / "proje" / name / "not.txt").exists()


def test_the_briefing_says_relative_paths_land_here(tmp_path: Path) -> None:
    briefing = Sandbox.open(tmp_path).briefing()
    assert "Göreli yol" in briefing
