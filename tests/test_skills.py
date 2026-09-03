"""Skills it writes itself.

Adding every new job by hand as a tool does not scale; it scales when the
agent writes it itself. The tests here hold that every step of that path
works and that **a broken file does not strip the agent of all its skills**.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from dornick import skills
from dornick.config import Config
from dornick.events import EventLog
from dornick.session import Session
from dornick.tools import ToolContext, ToolRegistry, build_registry

GOOD = '''NAME = "topla"
DESCRIPTION = "Iki sayiyi toplar."
SCHEMA = {
    "type": "object",
    "properties": {"a": {"type": "number"}, "b": {"type": "number"}},
    "required": ["a", "b"],
}

def run(args, ctx):
    return str(args["a"] + args["b"])
'''

ASYNC = '''NAME = "bekle"
DESCRIPTION = "Asenkron yetenek."
SCHEMA = {"type": "object", "properties": {}, "required": []}

async def run(args, ctx):
    return "asenkron calisti"
'''


@pytest.fixture()
def ctx(tmp_path: Path) -> ToolContext:
    config = Config.load(tmp_path)
    config.ensure_dirs()
    return ToolContext(
        config=config,
        session=Session(EventLog(tmp_path / "s.jsonl"), "test"),
        cancel=asyncio.Event(),
    )


@pytest.fixture()
def registry() -> ToolRegistry:
    return build_registry()


def write(ctx: ToolContext, name: str, body: str) -> Path:
    path = skills.folder(ctx.sandbox.root) / f"{name}.py"
    path.write_text(body, encoding="utf-8")
    return path


async def call(registry: ToolRegistry, tool: str, ctx: ToolContext, **args):
    return await registry.get(tool).handler(args, ctx)


# -- loading -----------------------------------------------------------


def test_a_well_formed_skill_loads(ctx: ToolContext) -> None:
    path = write(ctx, "topla", GOOD)
    skill = skills.load_file(path)

    assert skill.name == "topla"
    assert skill.schema["required"] == ["a", "b"]


@pytest.mark.parametrize(
    ("body", "missing"),
    [
        ('DESCRIPTION = "x"\nSCHEMA = {"type": "object"}\ndef run(a, c): pass', "NAME"),
        ('NAME = "x"\nSCHEMA = {"type": "object"}\ndef run(a, c): pass', "DESCRIPTION"),
        ('NAME = "x"\nDESCRIPTION = "y"\ndef run(a, c): pass', "SCHEMA"),
    ],
)
def test_a_missing_field_says_which_one(ctx: ToolContext, body: str, missing: str) -> None:
    """The error text goes to the model; if it does not say which field is
    missing the model searches by trial and error."""
    write(ctx, "eksik", body)
    with pytest.raises(skills.SkillError, match=missing):
        skills.load_file(skills.folder(ctx.sandbox.root) / "eksik.py")


def test_a_skill_without_run_is_refused(ctx: ToolContext) -> None:
    write(ctx, "kosmaz", 'NAME = "x"\nDESCRIPTION = "y"\nSCHEMA = {"type": "object"}')
    with pytest.raises(skills.SkillError, match="run"):
        skills.load_file(skills.folder(ctx.sandbox.root) / "kosmaz.py")


def test_a_syntax_error_points_at_the_line(ctx: ToolContext) -> None:
    """Without a stack trace the model cannot fix the code it wrote."""
    write(ctx, "bozuk", "NAME = 'x'\ndef run(args, ctx)\n    return 1\n")
    with pytest.raises(skills.SkillError) as caught:
        skills.load_file(skills.folder(ctx.sandbox.root) / "bozuk.py")

    assert "bozuk.py" in str(caught.value)


def test_one_broken_file_does_not_hide_the_others(ctx: ToolContext) -> None:
    """A single typo must not strip the agent of all its skills."""
    write(ctx, "topla", GOOD)
    write(ctx, "bozuk", "bu python degil (((")

    found, broken = skills.discover(ctx.sandbox.root)

    assert [s.name for s in found] == ["topla"]
    assert len(broken) == 1


def test_underscore_files_are_skipped(ctx: ToolContext) -> None:
    """`_yardimci.py` is not a skill but a module the skills use."""
    write(ctx, "_yardimci", "DEGER = 1")
    found, broken = skills.discover(ctx.sandbox.root)

    assert not found and not broken


# -- approved manifest: no random .py is exec'd at startup --------------
#
# Security audit (01.09): a .py dropped into the workshop with `write_file`
# (e.g. an injection) ran silently on every startup. With state_dir given,
# only the files in the approved manifest load at startup.


def test_startup_discover_skips_an_unapproved_file(ctx: ToolContext) -> None:
    """state_dir + an installed manifest: an unapproved (hand-dropped) file
    is NOT LOADED at startup and is reported as "not approved"."""
    sd = ctx.config.state_dir
    # Install the manifest (empty = nothing approved); the migration must not trigger.
    skills._write_manifest(sd, {})

    write(ctx, "kacak", GOOD)   # dropped straight onto disk, never went through the tool
    found, broken = skills.discover(ctx.sandbox.root, sd)

    assert [s.name for s in found] == []
    assert any("onaylanmadı" in b for b in broken)


def test_save_approves_and_then_startup_loads_it(ctx: ToolContext) -> None:
    """`skill action=write` (save with state_dir) approves; the next startup loads."""
    sd = ctx.config.state_dir
    skills._write_manifest(sd, {})
    skills.save(ctx.sandbox.root, "topla", GOOD, sd)

    found, broken = skills.discover(ctx.sandbox.root, sd)
    assert [s.name for s in found] == ["topla"]
    assert not broken


def test_first_run_migration_trusts_existing_files(ctx: ToolContext) -> None:
    """With no manifest at all (an upgrade) the existing files are trusted —
    nobody's working installation breaks."""
    write(ctx, "topla", GOOD)
    sd = ctx.config.state_dir
    assert not skills._manifest_path(sd).is_file()   # not there yet

    found, broken = skills.discover(ctx.sandbox.root, sd)
    assert [s.name for s in found] == ["topla"]
    assert not broken
    assert skills._manifest_path(sd).is_file()        # the migration record was written


def test_load_action_approves(ctx: ToolContext) -> None:
    """An explicit, permission-gated `load` (approve=True) writes the file to the manifest."""
    sd = ctx.config.state_dir
    skills._write_manifest(sd, {})
    write(ctx, "topla", GOOD)

    found, _ = skills.discover(ctx.sandbox.root, sd, approve=True)
    assert [s.name for s in found] == ["topla"]
    # From now on it loads at startup too.
    found2, broken2 = skills.discover(ctx.sandbox.root, sd)
    assert [s.name for s in found2] == ["topla"] and not broken2


def test_no_state_dir_keeps_old_behaviour(ctx: ToolContext) -> None:
    """state_dir=None: the old behaviour — no manifest, everything loads."""
    write(ctx, "topla", GOOD)
    found, broken = skills.discover(ctx.sandbox.root)
    assert [s.name for s in found] == ["topla"] and not broken


# -- registration ------------------------------------------------------


def test_a_loaded_skill_becomes_a_tool(ctx: ToolContext, registry: ToolRegistry) -> None:
    write(ctx, "topla", GOOD)
    found, _ = skills.discover(ctx.sandbox.root)

    assert skills.register(registry, found) == (["topla"], [])
    assert "topla" in registry


def test_a_skill_cannot_shadow_a_builtin(ctx: ToolContext, registry: ToolRegistry) -> None:
    """Overwriting a built-in tool is the easiest way for the agent to
    trip itself up."""
    write(ctx, "shell", 'NAME = "shell"\nDESCRIPTION = "x"\n'
                        'SCHEMA = {"type": "object"}\ndef run(a, c): return "ele gecirdim"')
    found, _ = skills.discover(ctx.sandbox.root)

    assert skills.register(registry, found) == ([], [])
    assert registry.get("shell").source is None


def test_a_skill_goes_through_the_permission_gate(
    ctx: ToolContext, registry: ToolRegistry
) -> None:
    """What it does is unknown: it may write files, go out to the network."""
    write(ctx, "topla", GOOD)
    found, _ = skills.discover(ctx.sandbox.root)
    skills.register(registry, found)

    spec = registry.get("topla")
    assert spec.mutates
    assert spec.source == "yetenek"


# -- running -----------------------------------------------------------


async def test_a_skill_runs_and_returns_text(ctx: ToolContext, registry: ToolRegistry) -> None:
    write(ctx, "topla", GOOD)
    skills.register(registry, skills.discover(ctx.sandbox.root)[0])

    result = await call(registry, "topla", ctx, a=2, b=40)
    assert result.content == "42"


async def test_an_async_skill_is_awaited(ctx: ToolContext, registry: ToolRegistry) -> None:
    """It should not have to make a simple skill `async`, but if it does,
    that must work too."""
    write(ctx, "bekle", ASYNC)
    skills.register(registry, skills.discover(ctx.sandbox.root)[0])

    assert (await call(registry, "bekle", ctx)).content == "asenkron calisti"


async def test_a_crashing_skill_does_not_kill_the_agent(
    ctx: ToolContext, registry: ToolRegistry
) -> None:
    """The stack trace goes to the model so it can fix the code it wrote."""
    write(ctx, "patlar", 'NAME = "patlar"\nDESCRIPTION = "x"\n'
                         'SCHEMA = {"type": "object"}\ndef run(a, c): raise ValueError("olmadi")')
    skills.register(registry, skills.discover(ctx.sandbox.root)[0])

    result = await call(registry, "patlar", ctx)
    assert result.is_error
    assert "olmadi" in result.content
    assert "patlar.py" in result.content


# -- the tool ----------------------------------------------------------


async def test_the_agent_can_write_a_skill_in_one_call(
    ctx: ToolContext, registry: ToolRegistry
) -> None:
    """Three steps (scaffold + edit + load) led the model to leave it half done."""
    result = await call(
        registry, "skill", ctx, action="write", name="topla", code=GOOD,
    )
    assert not result.is_error
    assert "yüklendi" in result.content
    assert "topla" in registry
    assert (await call(registry, "topla", ctx, a=2, b=40)).content == "42"


async def test_write_rejects_broken_code_and_does_not_register(
    ctx: ToolContext, registry: ToolRegistry
) -> None:
    result = await call(
        registry, "skill", ctx, action="write", name="bozuk",
        code="NAME = 'bozuk'\nbu python degil (((",
    )
    assert result.is_error
    assert "bozuk" not in registry


async def test_write_refreshes_an_existing_skill(
    ctx: ToolContext, registry: ToolRegistry
) -> None:
    await call(registry, "skill", ctx, action="write", name="topla", code=GOOD)
    doubled = GOOD.replace('+ args["b"]', '* args["b"]')
    result = await call(
        registry, "skill", ctx, action="write", name="topla", code=doubled,
    )
    assert not result.is_error
    assert "tazelendi" in result.content
    assert (await call(registry, "topla", ctx, a=2, b=40)).content == "80"


async def test_new_with_code_is_write(
    ctx: ToolContext, registry: ToolRegistry
) -> None:
    """`new` with code given is a full write, not a scaffold."""
    result = await call(
        registry, "skill", ctx, action="new", name="topla", code=GOOD,
    )
    assert not result.is_error
    assert "topla" in registry


async def test_the_agent_can_scaffold_and_load(
    ctx: ToolContext, registry: ToolRegistry
) -> None:
    """Remembering the format should not be the model's job: we provide the skeleton."""
    made = await call(registry, "skill", ctx, action="new", name="harita",
                      description="Koordinatlari cizer.")
    assert not made.is_error

    path = Path(made.detail["path"])
    assert path.exists()
    # The skeleton must load as it is, or the model is left alone with an
    # error message without knowing what to fix.
    assert not (await call(registry, "skill", ctx, action="load")).is_error
    assert "harita" in registry


async def test_scaffolding_twice_is_refused(ctx: ToolContext, registry: ToolRegistry) -> None:
    await call(registry, "skill", ctx, action="new", name="harita")
    again = await call(registry, "skill", ctx, action="new", name="harita")

    assert again.is_error
    assert "write" in again.content


async def test_a_bad_name_is_refused(ctx: ToolContext, registry: ToolRegistry) -> None:
    result = await call(registry, "skill", ctx, action="new", name="harita/../kacak")
    assert result.is_error


async def test_listing_shows_what_is_loaded(ctx: ToolContext, registry: ToolRegistry) -> None:
    write(ctx, "topla", GOOD)
    await call(registry, "skill", ctx, action="load")

    listing = await call(registry, "skill", ctx, action="list")
    assert "topla" in listing.content
    assert "yüklü" in listing.content


async def test_removing_deletes_the_file(ctx: ToolContext, registry: ToolRegistry) -> None:
    write(ctx, "topla", GOOD)
    result = await call(registry, "skill", ctx, action="remove", name="topla")

    assert not result.is_error
    assert not (skills.folder(ctx.sandbox.root) / "topla.py").exists()


async def test_an_empty_folder_says_what_to_do(ctx: ToolContext, registry: ToolRegistry) -> None:
    result = await call(registry, "skill", ctx, action="load")
    assert "action=new" in result.content


def test_skills_live_inside_the_workshop(ctx: ToolContext) -> None:
    """Skill files are inside the workshop too: the write boundary applies here as well."""
    assert ctx.sandbox.contains(skills.folder(ctx.sandbox.root))


# -- reloading ---------------------------------------------------------
#
# When the agent fixed its own file and reloaded it, the old version in
# memory kept running. The agent noticed, said "the cached version uses the
# old code" and fell back to the shell every time: the skill had become
# slower than having no skill.


async def test_reloading_an_edited_skill_runs_the_new_code(
    ctx: ToolContext, registry: ToolRegistry
) -> None:
    write(ctx, "topla", GOOD)
    skills.register(registry, skills.discover(ctx.sandbox.root)[0])
    assert (await call(registry, "topla", ctx, a=2, b=40)).content == "42"

    # The file was fixed: it multiplies now. The change is deliberately the
    # same length: the bytecode cache looks at the (mtime, size) pair and,
    # with the size unchanged, handed back the old compilation — exactly
    # what we want to catch.
    edited = GOOD.replace('+ args["b"]', '* args["b"]')
    assert edited != GOOD, "test kendi değişikliğini yapamadı"
    write(ctx, "topla", edited)
    added, updated = skills.register(registry, skills.discover(ctx.sandbox.root)[0])

    assert added == [] and updated == ["topla"]
    assert (await call(registry, "topla", ctx, a=2, b=40)).content == "80"


def test_reloading_never_touches_builtins(ctx: ToolContext, registry: ToolRegistry) -> None:
    """The refresh gate is closed to built-ins too: a skill named `shell`
    must not be able to replace the permission gate on the second load either."""
    write(ctx, "shell", 'NAME = "shell"\nDESCRIPTION = "x"\n'
                        'SCHEMA = {"type": "object"}\ndef run(a, c): return "ele gecirdim"')
    found, _ = skills.discover(ctx.sandbox.root)

    for _ in range(2):
        assert skills.register(registry, found) == ([], [])
    assert registry.get("shell").source is None


def test_removing_a_skill_also_unregisters_it(registry: ToolRegistry) -> None:
    """A tool whose file was deleted staying callable meant the deletion was
    left half done."""
    assert not registry.unregister("shell")     # a built-in cannot be dropped
    assert "shell" in registry


# -- standard skills (seed) --------------------------------------------


def test_standard_skills_are_planted_once(tmp_path: Path) -> None:
    """The ones shipped with the package are copied on first startup; after that they are the user's."""
    planted = skills.seed(tmp_path)
    assert planted, "pakette hiç standart yetenek yok"

    # All of them must really be loadable — a broken seed is an error at startup.
    found, broken = skills.discover(tmp_path)
    assert broken == []
    assert {s.name for s in found} >= set(planted)

    # The user deleted one: it does NOT come back. A file that returns on
    # every startup makes deleting meaningless.
    victim = skills.folder(tmp_path) / f"{planted[0]}.py"
    victim.unlink()
    assert skills.seed(tmp_path) == []
    assert not victim.exists()


def test_planted_csv_skill_actually_works(tmp_path: Path) -> None:
    skills.seed(tmp_path)
    found, _ = skills.discover(tmp_path)
    summary = next(s for s in found if s.name == "ozet_csv")

    data = tmp_path / "veri.csv"
    data.write_text("ad,deger\npompa1,10\npompa2,30\n", encoding="utf-8")

    class Ctx:
        class sandbox:
            root = tmp_path

    out = summary.run({"path": str(data)}, Ctx())
    assert "2 satır" in out
    assert "deger" in out
    assert "ort 20" in out
