"""The workshop boundary.

The single rule here — read anywhere, write only in the workshop — can be
silently punctured in three places: climbing up with `..`, escaping
through a symbolic link, and miscalculating where a file that does not
exist yet would be. All three are below.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from dornick.config import Config
from dornick.events import EventLog
from dornick.sandbox import OutsideSandbox, Sandbox
from dornick.session import Session
from dornick.tools import ToolContext, ToolRegistry
from dornick.tools import files as file_tools


@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    (tmp_path / "gizli.txt").write_text("kullanıcının dosyası", encoding="utf-8")
    return tmp_path


@pytest.fixture()
def ctx(workspace: Path) -> ToolContext:
    config = Config.load(workspace)
    config.ensure_dirs()
    session = Session(EventLog(workspace / ".dornick" / "s.jsonl"), "test")
    return ToolContext(config=config, session=session, cancel=asyncio.Event())


@pytest.fixture()
def registry() -> ToolRegistry:
    reg = ToolRegistry()
    file_tools.register(reg)
    return reg


async def call(registry: ToolRegistry, name: str, ctx: ToolContext, **args):
    return await registry.get(name).handler(args, ctx)


# -- boundary calculation ----------------------------------------------


def test_a_path_that_does_not_exist_yet_is_still_placed(tmp_path: Path) -> None:
    """Writes mostly go to a file that does not exist yet; the boundary
    check cannot depend on the file's existence."""
    box = Sandbox.open(tmp_path)

    assert box.contains(box.root / "site" / "index.html")
    assert not box.contains(tmp_path / "baska" / "index.html")


def test_climbing_out_with_dot_dot_is_caught(tmp_path: Path) -> None:
    box = Sandbox.open(tmp_path)

    with pytest.raises(OutsideSandbox):
        box.check(box.root / ".." / "kacak.txt")


def test_a_symlink_pointing_outside_is_caught(tmp_path: Path) -> None:
    """If compared without resolving the link, the boundary stays on paper."""
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
    """Disabling is a deliberate decision; while disabled the restriction must never apply."""
    box = Sandbox.open(tmp_path, enabled=False)
    assert box.check(tmp_path / "her" / "yer.txt")


def test_an_absolute_directory_can_be_used(tmp_path: Path) -> None:
    elsewhere = tmp_path / "baska" / "yer"
    box = Sandbox.open(tmp_path / "ws", str(elsewhere))

    assert box.root == elsewhere.resolve()
    assert box.root.is_dir()


# -- tools -------------------------------------------------------------


async def test_relative_writes_land_in_the_workshop(
    registry: ToolRegistry, ctx: ToolContext
) -> None:
    """When the agent writes "site/index.html" it expects that to be in its
    own folder; landing at the root of the workspace means mixing into the
    user's files."""
    result = await call(registry, "write_file", ctx, path="site/index.html", content="<h1>x</h1>")

    assert not result.is_error
    assert (ctx.sandbox.root / "site" / "index.html").read_text(encoding="utf-8") == "<h1>x</h1>"


async def test_writing_outside_is_refused_with_a_way_forward(
    registry: ToolRegistry, ctx: ToolContext, workspace: Path
) -> None:
    """Saying "no permission" is not enough: the model must know what to do
    on the next turn, otherwise it repeats the same call."""
    result = await call(
        registry, "write_file", ctx, path=str(workspace / "gizli.txt"), content="ezildi"
    )

    assert result.is_error
    assert "copy_in" in result.content
    assert workspace.joinpath("gizli.txt").read_text(encoding="utf-8") == "kullanıcının dosyası"


async def test_editing_outside_is_refused_too(
    registry: ToolRegistry, ctx: ToolContext, workspace: Path
) -> None:
    """If write_file is closed but edit_file stays open there is no boundary at all."""
    target = str(workspace / "gizli.txt")
    await call(registry, "read_file", ctx, path=target)

    result = await call(registry, "edit_file", ctx, path=target, old="kullanıcının", new="benim")

    assert result.is_error
    assert workspace.joinpath("gizli.txt").read_text(encoding="utf-8") == "kullanıcının dosyası"


async def test_reading_outside_stays_free(
    registry: ToolRegistry, ctx: ToolContext, workspace: Path
) -> None:
    """The restriction is on writing; the agent must be able to see everything on the computer."""
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
    """This process wrote the copy a moment ago; the staleness check must
    not force the model into a needless read_file turn."""
    await call(registry, "copy_in", ctx, path=str(workspace / "gizli.txt"), to="calisma.txt")

    result = await call(registry, "edit_file", ctx, path="calisma.txt",
                        old="kullanıcının", new="benim")

    assert not result.is_error
    assert (ctx.sandbox.root / "calisma.txt").read_text(encoding="utf-8") == "benim dosyası"


async def test_copy_in_cannot_be_used_to_escape(
    registry: ToolRegistry, ctx: ToolContext, workspace: Path
) -> None:
    """The target must pass the boundary check too; otherwise copying is an escape route."""
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
    """If the rule is not in the system prompt the model hits the wall on
    every write and learns by trial and error."""
    briefing = Sandbox.open(tmp_path).briefing()

    assert "atolye" in briefing.lower()
    assert "copy_in" in briefing


def test_a_disabled_sandbox_says_nothing(tmp_path: Path) -> None:
    assert Sandbox.open(tmp_path, enabled=False).briefing() == ""


async def test_the_workshop_name_is_not_nested(
    registry: ToolRegistry, ctx: ToolContext
) -> None:
    """The model adds the workshop's name to the path itself.

    The full path of the folder is in the system prompt and it infers from
    there, saying "atolye/merhaba.txt". Joining as-is produced
    `atolye/atolye/...` — in a real run exactly this happened and the file
    landed in a subfolder.
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
    """The trimming is only on the first part; inside there can be a folder
    with the same name and it must stay."""
    name = ctx.sandbox.root.name
    await call(registry, "write_file", ctx, path=f"proje/{name}/not.txt", content="x")

    assert (ctx.sandbox.root / "proje" / name / "not.txt").exists()


def test_the_briefing_says_relative_paths_land_here(tmp_path: Path) -> None:
    briefing = Sandbox.open(tmp_path).briefing()
    assert "Göreli yol" in briefing


# -- project mode ------------------------------------------------------
#
# "If I'm going to vibe-code in my own project I need to pick the folder."
# Copying a TREE into the workshop makes the job impossible: the copy is
# not the original. When the user explicitly picks a folder it becomes
# writable too — the choice itself is the approval. The workshop stays
# open in every case.

from dornick import sandbox as sandbox_module   # noqa: E402


def test_a_chosen_project_becomes_writable(tmp_path: Path) -> None:
    project = tmp_path / "musteri-projesi"
    project.mkdir()
    box = Sandbox.open(tmp_path, "atolye", project=str(project))

    assert box.contains(project / "src" / "yeni.py")     # a file that does not exist yet, too
    assert box.check(project / "app.py") is not None
    # The workshop does not disappear: dornick's own work keeps going there.
    assert box.contains(box.root / "deneme.txt")
    assert box.project == project.resolve()
    assert box.roots[0] == box.root                     # the workshop is always first


def test_everything_outside_the_open_roots_is_still_refused(tmp_path: Path) -> None:
    project = tmp_path / "proje"
    project.mkdir()
    (tmp_path / "baska").mkdir()
    box = Sandbox.open(tmp_path, "atolye", project=str(project))

    with pytest.raises(OutsideSandbox) as caught:
        box.check(tmp_path / "baska" / "dosya.txt")
    # The error must say what to do; "no permission" alone opens no path.
    assert "Ayarlar › Proje" in str(caught.value)
    assert str(project.resolve()) in str(caught.value)


def test_without_a_project_the_old_rule_holds(tmp_path: Path) -> None:
    box = Sandbox.open(tmp_path, "atolye")
    assert box.project is None
    assert box.roots == (box.root,)
    with pytest.raises(OutsideSandbox):
        box.check(tmp_path / "disarida.txt")


def test_dangerous_roots_are_refused_with_a_reason(tmp_path: Path) -> None:
    r"""Even if the user picks it, some roots are unacceptable: picking `C:\`
    is the long way of saying "you may write anywhere"."""
    root = Path(tmp_path.anchor or "/")
    assert sandbox_module.root_block(root) is not None

    home = Path.home()
    assert sandbox_module.root_block(home) is not None, "kullanıcı klasörü fazla geniş"
    # BELOW the home directory is free: the real projects live there.
    sub = tmp_path / "kod" / "proje"
    sub.mkdir(parents=True)
    assert sandbox_module.root_block(sub) is None

    # Non-existent and non-folder paths are refused with a reason too.
    assert sandbox_module.root_block(tmp_path / "yok") is not None
    file = tmp_path / "dosya.txt"
    file.write_text("x", encoding="utf-8")
    assert sandbox_module.root_block(file) is not None


def test_system_folders_are_refused(tmp_path: Path) -> None:
    """Operating system folders: the name is evidence enough, they need not exist."""
    fake = tmp_path / "Windows"
    fake.mkdir()
    assert "işletim sistemi" in (sandbox_module.root_block(fake) or "")


def test_an_invalid_project_falls_back_instead_of_breaking(tmp_path: Path) -> None:
    """The settings file may have been edited by hand or the folder deleted:
    the program must not become UNABLE TO OPEN, it should silently fall
    back to the workshop."""
    box = Sandbox.open(tmp_path, "atolye", project=str(tmp_path / "silinmis"))
    assert box.project is None
    assert box.contains(box.root / "x.txt")


def test_covering_neos_own_state_warns_but_does_not_block(tmp_path: Path) -> None:
    """Having dornick fix its own code is a legitimate request — this repo
    is developed exactly that way. A warning, not a block."""
    status = tmp_path / ".dornick"
    status.mkdir()
    box = Sandbox.open(tmp_path / "ws", "atolye", project=str(tmp_path),
                       state_dir=status)
    assert box.project == tmp_path.resolve()      # not blocked
    assert "hafızasına" in box.note               # but said


def test_the_briefing_tells_the_model_which_folder_is_which(tmp_path: Path) -> None:
    """The model must know which is which, otherwise it leaves its own
    experiments in the user's project."""
    project = tmp_path / "musteri"
    project.mkdir()

    plain = Sandbox.open(tmp_path, "atolye").briefing()
    assert "yazma yalnızca bu klasörde" in plain
    assert "Çalışılan proje" not in plain

    with_project = Sandbox.open(tmp_path, "atolye", project=str(project)).briefing()
    assert f"Çalışılan proje: {project.resolve()}" in with_project
    assert "yazma serbest" in with_project
    # The workshop keeps showing too: the two are separate jobs.
    assert str(Sandbox.open(tmp_path, "atolye").root) in with_project
    assert "kendi işlerin" in with_project


def test_relative_paths_resolve_against_the_nearest_open_root(tmp_path: Path) -> None:
    project = tmp_path / "proje"
    (project / "src").mkdir(parents=True)
    box = Sandbox.open(tmp_path, "atolye", project=str(project))
    assert box.relative(project / "src" / "app.py") == "src/app.py"
    assert box.relative(box.root / "not.md") == "not.md"


def test_recent_projects_are_remembered_in_order(tmp_path: Path) -> None:
    """Recent projects are for one-click switching; the most recently picked first."""
    status = tmp_path / ".dornick"
    assert sandbox_module.son_projeler(status) == []

    sandbox_module.proje_hatirla(status, "C:/a")
    sandbox_module.proje_hatirla(status, "C:/b")
    assert sandbox_module.son_projeler(status) == ["C:/b", "C:/a"]

    # The same project is not listed twice, it moves to the front.
    sandbox_module.proje_hatirla(status, "C:/a")
    assert sandbox_module.son_projeler(status) == ["C:/a", "C:/b"]

    # The ledger is bounded: the list does not grow forever.
    for i in range(20):
        sandbox_module.proje_hatirla(status, f"C:/p{i}")
    assert len(sandbox_module.son_projeler(status)) == sandbox_module.MAX_RECENT


def test_a_corrupt_recent_file_does_not_break_settings(tmp_path: Path) -> None:
    status = tmp_path / ".dornick"
    status.mkdir()
    (status / sandbox_module.PROJECTS_FILE).write_text("{bozuk", encoding="utf-8")
    assert sandbox_module.son_projeler(status) == []


def test_the_project_survives_a_settings_round_trip(tmp_path: Path) -> None:
    from dornick import settings

    project = tmp_path / "musteri"
    project.mkdir()
    config = Config.load(tmp_path)
    config.ensure_dirs()

    updated = settings.apply(config, {"sandbox": {"project": str(project)}})
    assert updated.sandbox.project == str(project)
    assert Config.load(tmp_path).sandbox.project == str(project)
    # The choice lands in the recent-projects ledger too.
    assert str(project) in sandbox_module.son_projeler(updated.state_dir)
    # And it is really writable.
    assert updated.open_sandbox().contains(project / "yeni.py")


def test_settings_refuses_a_dangerous_project_with_a_reason(tmp_path: Path) -> None:
    """Validation is here, not in the UI: an invalid root would only blow up
    when the agent tried to write there, and that is too late."""
    from dornick import settings

    config = Config.load(tmp_path)
    config.ensure_dirs()
    with pytest.raises(ValueError) as caught:
        settings.apply(config, {"sandbox": {"project": str(Path(tmp_path.anchor or "/"))}})
    assert "sürücü kökü" in str(caught.value) or "işletim sistemi" in str(caught.value)
    # The refused choice must not be written to disk.
    assert Config.load(tmp_path).sandbox.project == ""
