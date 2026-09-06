"""Hooks: the user plugging their own commands into the tool lifecycle.

The promise under test: a command written into `.dornick/hooks.json`
must run before or after the tool; if `arac_oncesi` returns a non-zero
code the tool must NOT run at all and the reason must go to the model.

The second and more important promise is SECURITY: hooks run outside the
permission engine (they are the user's own command), so the model must NOT
be able to modify them. If it could, it would bypass the permission gate
entirely by deleting the hook that blocks it.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

from dornick import hooks
from dornick.config import Config
from dornick.events import EventLog
from dornick.permissions import PermissionEngine
from dornick.session import PendingToolUse, Session
from dornick.tools import ToolContext, ToolRegistry, ToolResult, execute, object_schema
from dornick.tools import files as file_tools

PY = sys.executable


@pytest.fixture(autouse=True)
def clean_cache():
    hooks.clear_cache()
    yield
    hooks.clear_cache()


def write_hooks(state_dir: Path, entries: list[dict]) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "hooks.json").write_text(
        json.dumps(entries, ensure_ascii=False), encoding="utf-8")


def script(code: str) -> str:
    """A small Python line that will run as the hook command."""
    return f'& "{PY}" -c "{code}"'


# -- reading the configuration -----------------------------------------


def test_no_file_means_no_hooks(tmp_path: Path) -> None:
    """A user who does not use hooks must pay nothing."""
    assert hooks.load(tmp_path) == []


def test_hooks_are_parsed(tmp_path: Path) -> None:
    write_hooks(tmp_path, [{"event": "before_tool", "tool": "write_file",
                            "command": "echo x", "timeout": 5}])
    (hook,) = hooks.load(tmp_path)
    assert hook.event == "before_tool"
    assert hook.command == "echo x"
    assert hook.timeout == 5


def test_broken_entries_drop_but_good_ones_survive(tmp_path: Path) -> None:
    """A typo must not stop the whole tool layer."""
    write_hooks(tmp_path, [
        {"event": "yanlis_olay", "command": "echo a"},     # unknown event
        {"event": "before_tool"},                        # no command
        "düz metin",                                    # not even an entry
        {"event": "after_tool", "command": "echo b"},    # sound
    ])
    loaded = hooks.load(tmp_path)
    assert [h.command for h in loaded] == ["echo b"]


def test_broken_json_disables_hooks_but_is_reportable(tmp_path: Path) -> None:
    (tmp_path).mkdir(parents=True, exist_ok=True)
    (tmp_path / "hooks.json").write_text("{bozuk", encoding="utf-8")
    assert hooks.load(tmp_path) == []
    assert "geçerli JSON değil" in hooks.broken_reason(tmp_path)


def test_a_missing_file_is_not_broken(tmp_path: Path) -> None:
    assert hooks.broken_reason(tmp_path) == ""


def test_the_cache_follows_the_user_edit(tmp_path: Path) -> None:
    """When the user edits the file no restart should be needed."""
    write_hooks(tmp_path, [{"event": "before_tool", "command": "echo bir"}])
    assert [h.command for h in hooks.load(tmp_path)] == ["echo bir"]
    write_hooks(tmp_path, [{"event": "before_tool", "command": "echo iki"}])
    assert [h.command for h in hooks.load(tmp_path)] == ["echo iki"]


def test_the_timeout_is_capped(tmp_path: Path) -> None:
    write_hooks(tmp_path, [{"event": "before_tool", "command": "echo x",
                            "timeout": 99999}])
    assert hooks.load(tmp_path)[0].timeout == hooks.MAX_TIMEOUT


# -- fnmatch matching --------------------------------------------------


@pytest.mark.parametrize("pattern,tool,expected", [
    ("write_file", "write_file", True),
    ("write_file", "edit_file", False),
    ("*", "shell", True),
    ("*_file", "write_file", True),
    ("*_file", "shell", False),
    ("write_file|edit_file", "edit_file", True),
    ("write_file|edit_file", "shell", False),
    ("write_file | edit_file", "edit_file", True),   # whitespace tolerance
])
def test_tool_patterns(pattern: str, tool: str, expected: bool) -> None:
    hook = hooks.Hook("before_tool", pattern, "echo x")
    assert hook.matches(tool) is expected


def test_matching_respects_the_event(tmp_path: Path) -> None:
    write_hooks(tmp_path, [
        {"event": "before_tool", "tool": "*", "command": "echo once"},
        {"event": "after_tool", "tool": "*", "command": "echo sonra"},
    ])
    before = hooks.matching(tmp_path, "before_tool", "shell")
    assert [h.command for h in before] == ["echo once"]


# -- arac_oncesi: veto -------------------------------------------------


async def test_a_zero_exit_lets_the_tool_run(tmp_path: Path) -> None:
    write_hooks(tmp_path, [{"event": "before_tool", "tool": "write_file",
                            "command": script("pass")}])
    decision = await hooks.before_tool(tmp_path, "write_file", {}, cwd=tmp_path)
    assert decision.allowed
    assert decision.reason == ""


async def test_a_nonzero_exit_blocks_the_tool(tmp_path: Path) -> None:
    """The core scenario: block writing to a forbidden file."""
    write_hooks(tmp_path, [{"event": "before_tool", "tool": "write_file",
                            "command": script("import sys; print('uretim dosyasi, dokunma'); "
                                            "sys.exit(1)")}])
    decision = await hooks.before_tool(tmp_path, "write_file", {}, cwd=tmp_path)
    assert not decision.allowed
    assert "Kanca reddetti" in decision.reason
    assert "uretim dosyasi, dokunma" in decision.reason
    # The source is named so the model does not try to get around the rule.
    assert "kullanıcının kendi kuralı" in decision.reason


async def test_an_unmatched_tool_is_untouched(tmp_path: Path) -> None:
    write_hooks(tmp_path, [{"event": "before_tool", "tool": "write_file",
                            "command": script("import sys; sys.exit(1)")}])
    decision = await hooks.before_tool(tmp_path, "read_file", {}, cwd=tmp_path)
    assert decision.allowed


async def test_the_first_refusal_stops_the_chain(tmp_path: Path) -> None:
    """Once the decision is made there is no point asking a second gatekeeper."""
    trace = tmp_path / "iz.txt"
    write_hooks(tmp_path, [
        {"event": "before_tool", "tool": "*",
         "command": script("import sys; print('ilk'); sys.exit(3)")},
        {"event": "before_tool", "tool": "*",
         "command": script(f"open(r'{trace}', 'w').write('kostum')")},
    ])
    decision = await hooks.before_tool(tmp_path, "shell", {}, cwd=tmp_path)
    assert not decision.allowed
    assert "çıkış kodu 3" in decision.reason
    assert not trace.exists()          # the second hook never ran


async def test_a_timeout_blocks_on_the_safe_side(tmp_path: Path) -> None:
    """If the gatekeeper does not answer, saying 'it would probably have
    allowed it' removes the gatekeeper."""
    write_hooks(tmp_path, [{"event": "before_tool", "tool": "*",
                            "command": script("import time; time.sleep(60)"),
                            "timeout": 2}])
    import time as _t

    start = _t.monotonic()
    decision = await hooks.before_tool(tmp_path, "shell", {}, cwd=tmp_path)
    elapsed = _t.monotonic() - start
    assert not decision.allowed
    assert "cevap vermedi" in decision.reason
    assert "güvenli taraf" in decision.reason
    # The timeout must REALLY return within the timeout: killing the shell
    # and leaving the real process behind (the pipes stay open) turned a
    # 2-second limit into a 60-second wait.
    assert elapsed < 20, f"kanca zaman aşımı {elapsed:.0f} sn asılı kaldı"


async def test_a_hook_that_cannot_start_is_skipped_and_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The hook's own fault must not kill the tool — but must not be hidden either."""
    async def crash(*_a, **_k):
        raise OSError("kabuk bulunamadı")

    monkeypatch.setattr(hooks, "_launch", crash)
    write_hooks(tmp_path, [{"event": "before_tool", "tool": "*", "command": "her neyse"}])
    decision = await hooks.before_tool(tmp_path, "shell", {}, cwd=tmp_path)
    assert decision.allowed                    # the tool keeps running
    assert decision.notes
    assert "çalıştırılamadı" in decision.notes[0]
    assert "uygulanmadı" in decision.notes[0]


# -- environment variables ---------------------------------------------


async def test_the_hook_receives_its_context_in_the_environment(tmp_path: Path) -> None:
    """Embedding JSON in the command line is escaping hell; an environment variable is not.

    The hook is set up like a real user hook: a separate script file,
    reading from `os.environ`.
    """
    target = tmp_path / "cikti.json"
    hook_py = tmp_path / "bekci.py"
    hook_py.write_text(
        "import json, os, pathlib\n"
        "pathlib.Path(r'''" + str(target) + "''').write_text(json.dumps({\n"
        "    'tool': os.environ.get('DORNICK_TOOL'),\n"
        "    'args': os.environ.get('DORNICK_ARGS'),\n"
        "    'path': os.environ.get('DORNICK_PATH'),\n"
        "    'session': os.environ.get('DORNICK_SESSION'),\n"
        "    'legacy': [os.environ.get('DORNICK_ARAC'), os.environ.get('DORNICK_YOL'),\n"
        "               os.environ.get('DORNICK_OTURUM')],\n"
        "}), encoding='utf-8')\n",
        encoding="utf-8")
    write_hooks(tmp_path, [{"event": "before_tool", "tool": "*",
                            "command": f'& "{PY}" "{hook_py}"'}])

    await hooks.before_tool(
        tmp_path, "write_file",
        {"path": "C:/proje/app.py", "content": "x = 1"},
        session="20260101T0000Z", cwd=tmp_path)

    seen = json.loads(target.read_text(encoding="utf-8"))
    assert seen["tool"] == "write_file"
    assert seen["path"] == "C:/proje/app.py"
    assert seen["session"] == "20260101T0000Z"
    # The pre-1.5.5 names stay set: a hook written against them keeps working.
    assert seen["legacy"] == ["write_file", "C:/proje/app.py", "20260101T0000Z"]
    # The full arguments are passed as JSON as well.
    assert json.loads(seen["args"])["content"] == "x = 1"


async def test_a_pathless_call_still_defines_the_variable(tmp_path: Path) -> None:
    """If `$DORNICK_YOL` were undefined the user's hook would blow up."""
    target = tmp_path / "yol.txt"
    hook_py = tmp_path / "yoku.py"
    hook_py.write_text(
        "import os, pathlib\n"
        "pathlib.Path(r'''" + str(target) + "''').write_text("
        "repr(os.environ.get('DORNICK_YOL')))\n",
        encoding="utf-8")
    write_hooks(tmp_path, [{"event": "before_tool", "tool": "*",
                            "command": f'& "{PY}" "{hook_py}"'}])
    await hooks.before_tool(tmp_path, "shell", {"command": "ls"}, cwd=tmp_path)
    assert target.read_text() == "''"


# -- arac_sonrasi: information -----------------------------------------


async def test_a_post_hook_reports_its_output(tmp_path: Path) -> None:
    write_hooks(tmp_path, [{"event": "after_tool", "tool": "write_file",
                            "command": script("print('bicimlendirildi')")}])
    notes = await hooks.after_tool(tmp_path, "write_file", {}, cwd=tmp_path)
    assert notes == ["kanca: bicimlendirildi"]


async def test_a_post_hook_cannot_veto(tmp_path: Path) -> None:
    """The work is already done; 'I refuse' has no consequence."""
    write_hooks(tmp_path, [{"event": "after_tool", "tool": "*",
                            "command": script("import sys; print('begenmedim'); sys.exit(2)")}])
    notes = await hooks.after_tool(tmp_path, "shell", {}, cwd=tmp_path)
    assert len(notes) == 1
    assert "çıkış 2" in notes[0] and "begenmedim" in notes[0]


async def test_a_silent_post_hook_says_nothing(tmp_path: Path) -> None:
    """Producing no noise is essential: an empty line under every write makes
    the real warnings go unread too."""
    write_hooks(tmp_path, [{"event": "after_tool", "tool": "*", "command": script("pass")}])
    assert await hooks.after_tool(tmp_path, "shell", {}, cwd=tmp_path) == []


async def test_multiline_output_becomes_one_line(tmp_path: Path) -> None:
    write_hooks(tmp_path, [{"event": "after_tool", "tool": "*",
                            "command": script("print('bir'); print('iki')")}])
    (note,) = await hooks.after_tool(tmp_path, "shell", {}, cwd=tmp_path)
    assert "\n" not in note
    assert "bir iki" in note


async def test_stderr_is_used_when_stdout_is_empty(tmp_path: Path) -> None:
    write_hooks(tmp_path, [{"event": "after_tool", "tool": "*",
                            "command": script("import sys; print('uyari', file=sys.stderr)")}])
    (note,) = await hooks.after_tool(tmp_path, "shell", {}, cwd=tmp_path)
    assert "uyari" in note


async def test_post_hook_timeout_is_reported_not_fatal(tmp_path: Path) -> None:
    write_hooks(tmp_path, [{"event": "after_tool", "tool": "*",
                            "command": script("import time; time.sleep(60)"),
                            "timeout": 2}])
    (note,) = await hooks.after_tool(tmp_path, "shell", {}, cwd=tmp_path)
    assert "bitmedi ve durduruldu" in note


# -- protecting the hook file ------------------------------------------


@pytest.mark.parametrize("path,protected", [
    (".dornick/hooks.json", True),
    (".dornick/HOOKS.JSON", True),
    ("proje/.dornick/hooks.json", True),       # another project's file too
    (".dornick/kancalar.json", True),       # the pre-1.5.1 name stays fenced
    (".dornick/ayarlar.json", False),
    ("hooks.json", False),                   # not under .dornick
    ("src/hooks.json", False),
])
def test_which_paths_are_protected(path: str, protected: bool) -> None:
    assert hooks.is_protected(Path(path)) is protected


@pytest.fixture()
def ctx(tmp_path: Path) -> ToolContext:
    config = Config.load(tmp_path)
    config.ensure_dirs()
    return ToolContext(
        config=config,
        session=Session(EventLog(tmp_path / ".dornick" / "s.jsonl"), "test-kanca"),
        cancel=asyncio.Event(),
    )


@pytest.fixture()
def registry() -> ToolRegistry:
    reg = ToolRegistry()
    file_tools.register(reg)
    return reg


async def test_the_model_cannot_write_the_hook_file(
    registry: ToolRegistry, ctx: ToolContext, tmp_path: Path
) -> None:
    """The backbone of security. If the model could write this file it would
    bypass the permission gate entirely by deleting the hook that blocks it."""
    target = ctx.config.state_dir / "hooks.json"
    result = await registry.get("write_file").handler(
        {"path": str(target), "content": "[]"}, ctx)
    assert result.is_error
    assert "yazmaya kapalıdır" in result.content
    assert "kendin düzenleme" in result.content
    assert not target.exists()


async def test_the_model_cannot_edit_the_hook_file(
    registry: ToolRegistry, ctx: ToolContext
) -> None:
    target = ctx.config.state_dir / "hooks.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text('[{"event": "before_tool", "command": "x"}]', encoding="utf-8")
    await registry.get("read_file").handler({"path": str(target)}, ctx)
    result = await registry.get("edit_file").handler(
        {"path": str(target), "old": "before_tool", "new": "hicbirsey"}, ctx)
    assert result.is_error
    assert "yazmaya kapalıdır" in result.content
    # The file stands as it was.
    assert "before_tool" in target.read_text(encoding="utf-8")


def _shell_registry() -> tuple[ToolRegistry, list[str]]:
    """A one-tool registry behaving like the shell: NOT a write tool, `mutates`."""
    traces: list[str] = []
    reg = ToolRegistry()

    @reg.tool(name="shell", description="deneme",
              input_schema=object_schema({"command": {"type": "string"}}),
              mutates=True)
    async def _run_command(args, _ctx) -> ToolResult:
        traces.append(str(args.get("command")))
        return ToolResult("koştu")

    @reg.tool(name="list_dir", description="deneme",
              input_schema=object_schema({"path": {"type": "string"}}))
    async def _list(args, _ctx) -> ToolResult:
        traces.append(str(args.get("path")))
        return ToolResult("listelendi")

    return reg, traces


async def test_the_model_cannot_reach_the_hook_file_through_the_shell(
    ctx: ToolContext
) -> None:
    """The write tools' gate did not cover the shell — that was the real hole.

    `write_file` was blocked, but `Set-Content .dornick/hooks.json` went
    through no gate at all; the model could tear down the fence that stops
    it with the shell.
    """
    registry, traces = _shell_registry()
    blocks = await execute(
        [PendingToolUse(id="c1", name="shell", input={
            "command": "Set-Content .dornick/hooks.json '[]'"})],
        registry=registry,
        permissions=PermissionEngine("yolo", [], []),
        ctx=ctx,
        approve=lambda *_: asyncio.sleep(0, result=True),
    )
    assert blocks[0]["is_error"]
    assert "kanca dosyası" in blocks[0]["content"]
    assert "read_file" in blocks[0]["content"], "okumanın yolu gösterilmeli"
    assert traces == [], "komut HİÇ çalışmamalı"


async def test_an_unrelated_command_is_untouched(ctx: ToolContext) -> None:
    """A user who does not use hooks must never see this gate."""
    registry, traces = _shell_registry()
    blocks = await execute(
        [PendingToolUse(id="c1", name="shell",
                        input={"command": "py -m pytest -q"})],
        registry=registry,
        permissions=PermissionEngine("yolo", [], []),
        ctx=ctx,
        approve=lambda *_: asyncio.sleep(0, result=True),
    )
    assert not blocks[0]["is_error"]
    assert traces == ["py -m pytest -q"]


async def test_a_read_only_tool_may_still_name_the_hook_file(
    ctx: ToolContext
) -> None:
    """The gate is only for MUTATING tools: the model must be able to read its rule."""
    registry, traces = _shell_registry()
    blocks = await execute(
        [PendingToolUse(id="c1", name="list_dir",
                        input={"path": ".dornick/hooks.json"})],
        registry=registry,
        permissions=PermissionEngine("yolo", [], []),
        ctx=ctx,
        approve=lambda *_: asyncio.sleep(0, result=True),
    )
    assert not blocks[0]["is_error"]
    assert traces == [".dornick/hooks.json"]


async def test_the_model_can_still_read_the_hook_file(
    registry: ToolRegistry, ctx: ToolContext
) -> None:
    """Reading is not forbidden: the model must know which rule it works under."""
    target = ctx.config.state_dir / "hooks.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("[]", encoding="utf-8")
    result = await registry.get("read_file").handler({"path": str(target)}, ctx)
    assert not result.is_error


# -- end to end with the executor --------------------------------------


def _registry() -> tuple[ToolRegistry, list[str]]:
    """A one-tool registry that leaves a trace when it runs."""
    traces: list[str] = []
    reg = ToolRegistry()

    @reg.tool(name="write_file", description="deneme",
              input_schema=object_schema({"path": {"type": "string"}}),
              mutates=True)
    async def _write(args, _ctx) -> ToolResult:
        traces.append(str(args.get("path")))
        return ToolResult(f"{args.get('path')} yazıldı.")

    return reg, traces


async def _run(registry: ToolRegistry, ctx: ToolContext, args: dict) -> dict:
    blocks = await execute(
        [PendingToolUse(id="c1", name="write_file", input=args)],
        registry=registry,
        permissions=PermissionEngine("yolo", [], []),
        ctx=ctx,
        approve=lambda *_: asyncio.sleep(0, result=True),
    )
    return blocks[0]


async def test_the_executor_blocks_a_refused_call(ctx: ToolContext) -> None:
    write_hooks(ctx.config.state_dir, [{
        "event": "before_tool", "tool": "write_file",
        "command": script("import sys; print('bu depoda yazma'); sys.exit(1)")}])
    registry, traces = _registry()
    block = await _run(registry, ctx, {"path": "app.py"})
    assert block["is_error"]
    assert "bu depoda yazma" in block["content"]
    assert traces == []              # the tool NEVER ran


async def test_the_executor_lets_an_approved_call_through(ctx: ToolContext) -> None:
    write_hooks(ctx.config.state_dir, [{
        "event": "before_tool", "tool": "write_file", "command": script("pass")}])
    registry, traces = _registry()
    block = await _run(registry, ctx, {"path": "app.py"})
    assert not block["is_error"]
    assert traces == ["app.py"]


async def test_the_executor_appends_post_hook_output(ctx: ToolContext) -> None:
    write_hooks(ctx.config.state_dir, [{
        "event": "after_tool", "tool": "write_file",
        "command": script("print('black ile bicimlendirildi')")}])
    registry, _traces = _registry()
    block = await _run(registry, ctx, {"path": "app.py"})
    assert "app.py yazıldı." in block["content"]
    assert "kanca: black ile bicimlendirildi" in block["content"]


async def test_without_a_hook_file_nothing_changes(ctx: ToolContext) -> None:
    """For a user without hooks the output must not change by a single letter."""
    registry, traces = _registry()
    block = await _run(registry, ctx, {"path": "app.py"})
    assert block["content"] == "app.py yazıldı."
    assert traces == ["app.py"]


async def test_a_broken_hook_layer_never_kills_the_tool(
    ctx: ToolContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The hook layer's own crash must not bring the tool down."""
    async def crash(*_a, **_k):
        raise RuntimeError("kanca katmanı bozuldu")

    monkeypatch.setattr(hooks, "before_tool", crash)
    registry, traces = _registry()
    block = await _run(registry, ctx, {"path": "app.py"})
    assert traces == ["app.py"]
    assert "kanca katmanı çalışmadı" in block["content"]


def test_a_same_size_rewrite_inside_one_timestamp_tick_is_seen(tmp_path: Path) -> None:
    """mtime and size identical, content different: the digest must catch it.
    This was the flake of 2026-09-04 (one run in twelve)."""
    import os

    write_hooks(tmp_path, [{"event": "before_tool", "command": "echo bir"}])
    assert [h.command for h in hooks.load(tmp_path)] == ["echo bir"]
    path = hooks.file_path(tmp_path)
    stamp = path.stat().st_mtime_ns
    write_hooks(tmp_path, [{"event": "before_tool", "command": "echo iki"}])
    os.utime(path, ns=(stamp, stamp))               # force the same tick
    assert path.stat().st_mtime_ns == stamp
    assert [h.command for h in hooks.load(tmp_path)] == ["echo iki"]
