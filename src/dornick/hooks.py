"""Hooks: the user plugging their own commands into the tool lifecycle.

Why it exists: what Dornick does and does not do was decided in two places —
the system prompt (PERSUADES the model) and the permission engine (looks at
the tool name and its argument). There is a gap between the two: "never write
to the `main` branch in this repo", "run `black` after every Python file is
written", "warn me first if the production configuration is going to be
touched". These are the user's own rules and none of them fits into the
prompt or a permission pattern.

A hook fills that gap: the user writes their own command into the
`.dornick/hooks.json` file, and the command runs before or after the tool.

    [
      {"event": "before_tool", "tool": "write_file",
       "command": "py .dornick/guard.py", "timeout": 10},
      {"event": "after_tool", "tool": "write_file|edit_file",
       "command": "black -q \\"%DORNICK_PATH%\\" && echo formatted"}

A file written before 1.5.5 (`olay`/`arac`/`komut`/`zaman_asimi`,
`arac_oncesi`/`arac_sonrasi`, `%DORNICK_YOL%`) still loads: the keys and
event names are read through `legacy_values`, and the old environment
variable names are set beside the new ones.
    ]

`before_tool` has VETO power: if the command returns with a non-zero exit
code the tool does not run at all and the command's output goes to the model
as the reason. `after_tool` only informs; its output is appended to the
tool result as a single line.

SECURITY — two deliberate decisions and their rationale:

  1. **Hooks run OUTSIDE the permission engine.** No approval window pops
     up; they run even in `plan` mode. This is not an oversight: a hook is
     the user's OWN command, written by their own hand into their own file
     on their own disk. Asking them every time "shall I run your own rule?"
     would make the rule useless — especially when the rule's job is to
     block the model.
  2. **The model CANNOT modify hooks.** The first decision is only safe with
     this one: if the model could write the file, it would bypass the
     permission engine entirely by deleting the hook that blocks it or by
     putting its own command there. That is why `.dornick/hooks.json` is
     closed to the file-writing tools (`_guard` in `tools/files.py`) and its
     only editor is the user.

If the file does not exist nothing happens: the hook layer is silently off.
"""

from __future__ import annotations

import asyncio
import fnmatch
import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import legacy_values, legacy_names

from . import environment

FILE_NAME = "hooks.json"
# The pre-1.5.1 name: adopted once by `legacy_names`, but a write aimed at it
# is refused all the same — the fence must not have a hole named "old".
LEGACY_FILE_NAME = "kancalar.json"
PROTECTED_NAMES = (FILE_NAME, LEGACY_FILE_NAME)

# Default time given to a hook. Since the hook stands in front of the tool it
# cannot be generous: 30 seconds added to every `write_file` makes the turn
# unbearable.
DEFAULT_TIMEOUT = 20.0
MAX_TIMEOUT = 120.0

# The trimmed form of the hook output that goes to the model. A hook writes
# a reason, not a report.
MAX_OUTPUT = 1200

EVENTS = ("before_tool", "after_tool")


@dataclass(slots=True)
class Hook:
    """A single hook definition."""

    event: str
    tool: str                   # fnmatch pattern; several joined with "|"
    command: str
    timeout: float = DEFAULT_TIMEOUT

    def matches(self, tool: str) -> bool:
        """Is this hook for `tool`?

        The pattern is split on `|`: "write_file|edit_file" is two separate
        patterns. Having to write separate lines would push the user into
        copy-paste, and the copies would drift apart.
        """
        for part in self.tool.split("|"):
            if fnmatch.fnmatch(tool, part.strip()):
                return True
        return False


@dataclass(slots=True)
class Output:
    """The result of one hook run."""

    hook: Hook
    code: int = 0
    text: str = ""
    status: str = "ran"          # ran | timeout | failed_to_start

    @property
    def blocks(self) -> bool:
        """For `before_tool`: should the tool NOT run?

        A timeout blocks too. That is the safe side: if the user wrote a
        gatekeeper and the gatekeeper does not answer, saying "it would
        probably have allowed it" removes the gatekeeper's reason to exist.
        """
        return self.status == "timeout" or (self.status == "ran" and self.code != 0)


@dataclass(slots=True)
class Verdict:
    """The combined result of the `before_tool` hooks."""

    allowed: bool = True
    reason: str = ""
    # Things that do not block but must be said (a broken hook, for instance).
    notes: list[str] = field(default_factory=list)


# -- configuration ------------------------------------------------------


def file_path(state_dir: Path | str) -> Path:
    path = Path(state_dir) / FILE_NAME
    legacy_names.adopt(Path(state_dir) / LEGACY_FILE_NAME, path)
    return path


def is_protected(path: Path | str) -> bool:
    """Is this path a hook file? (the write tools look at this)

    We look not only at the active `.dornick` folder but at `hooks.json`
    under ANY folder NAMED `.dornick`. The model must not be able to write
    another project's hook file either — and a caller that does not know
    `state_dir` must still be protected.
    """
    path = Path(path)
    return (path.name.lower() in PROTECTED_NAMES
            and path.parent.name.lower() == ".dornick")


def call_touches_hook(tool: str, payload: Any) -> bool:
    """Does this MUTATING call reach the hook file? (the executor asks)

    `is_protected` closes the path for the write tools; but the shell is not a
    write tool, and a command like `Set-Content .dornick/hooks.json`
    never went through that gate. That was the hole in the claim "the model
    cannot tear down the fence that stops it".

    The executor asks this only for `mutates` tools; `read_file`, `grep`,
    `list_dir` are unaffected — the model must be able to read which rule it
    is working under. Reading through the shell is closed too (the shell
    both reads and writes, and the two cannot be told apart from the command
    text); the refusal message points at `read_file`.

    This is NOT A PRISON, it is an intent gate: a command that hides the
    name (assigning to a variable, building it piece by piece, base64) gets
    past it — there is no race to be won by parsing the shell command. What
    it closes is the real failure mode: the model saying "let me remove that
    hook so the job goes through" and writing directly. The fence against a
    deliberate adversary is the permission engine.
    """
    if tool in {"write_file", "edit_file", "copy_in"}:
        return False  # they have their own gates (`is_protected`); their messages are better
    if not isinstance(payload, dict):
        return False
    return any(isinstance(v, str) and any(name in v.lower() for name in PROTECTED_NAMES)
               for v in payload.values())


def _parse_entries(raw: Any) -> list[Hook]:
    """The hook list from the JSON body. Broken entries drop SILENTLY.

    Why silently: the hook file is in the user's hands, and stopping the
    whole tool layer because of a typo is disproportionate. An unknown event
    name or an empty command means a hook that does not exist — that is all.
    """
    if not isinstance(raw, list):
        return []
    found: list[Hook] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        entry = legacy_values.keys(entry, legacy_values.HOOK_KEYS)
        event = str(entry.get("event") or "").strip()
        event = legacy_values.HOOK_EVENTS.get(event, event)
        command = str(entry.get("command") or "").strip()
        if event not in EVENTS or not command:
            continue
        try:
            seconds = float(entry.get("timeout") or DEFAULT_TIMEOUT)
        except (TypeError, ValueError):
            seconds = DEFAULT_TIMEOUT
        found.append(Hook(
            event=event,
            tool=str(entry.get("tool") or "*").strip() or "*",
            command=command,
            timeout=max(1.0, min(seconds, MAX_TIMEOUT)),
        ))
    return found


# A small cache so the file does not look like it is read on every tool
# call: (path) -> (mtime_ns, size, digest, hooks). The moment the user edits
# the file the mtime changes and the cache drops by itself — no restart
# needed. The digest is the tie-breaker: two same-size writes inside one
# filesystem timestamp tick (a few ms on NTFS) leave mtime AND size equal,
# and the cache served the old hooks — a flake that fired in one run of
# twelve all day (2026-09-04). The file is a few hundred bytes; reading it
# costs less than the stat we already pay for.
_cache: dict[str, tuple[int, int, bytes, list[Hook]]] = {}


def load(state_dir: Path | str) -> list[Hook]:
    """The hooks inside `.dornick/hooks.json`; an empty list if the file is absent.

    The ABSENCE of the file is the normal case: users of hooks are a
    minority and those who do not use them must pay nothing. So the fast
    path is a single `stat`.
    """
    path = file_path(state_dir)
    try:
        info = path.stat()
    except OSError:
        _cache.pop(str(path), None)
        return []

    key = str(path)
    try:
        data = path.read_bytes()
    except OSError:
        _cache.pop(key, None)
        return []
    digest = hashlib.blake2b(data, digest_size=16).digest()
    if (previous := _cache.get(key)) is not None:
        if (previous[0] == info.st_mtime_ns and previous[1] == info.st_size
                and previous[2] == digest):
            return previous[3]

    try:
        raw = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        # Broken JSON: run without hooks. Not silent — the caller can ask
        # with `broken_reason` and tell the user.
        _cache[key] = (info.st_mtime_ns, info.st_size, digest, [])
        return []

    hooks = _parse_entries(raw)
    _cache[key] = (info.st_mtime_ns, info.st_size, digest, hooks)
    return hooks


def broken_reason(state_dir: Path | str) -> str:
    """If the file exists but cannot be read, the human-readable error; else an empty string."""
    path = file_path(state_dir)
    if not path.is_file():
        return ""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        return f"{path} okunamadı ({exc.strerror or exc})"
    except ValueError as exc:
        return f"{path} geçerli JSON değil ({exc})"
    if not isinstance(raw, list):
        return f"{path} bir liste olmalı (köşeli parantezle başlamalı)"
    return ""


def clear_cache() -> None:
    """For tests: empties the file cache."""
    _cache.clear()


def matching(state_dir: Path | str, event: str, tool: str) -> list[Hook]:
    return [h for h in load(state_dir) if h.event == event and h.matches(tool)]


# -- running ------------------------------------------------------------


def _environment(tool: str, args: dict[str, Any], session: str) -> dict[str, str]:
    """Context reaches the hook through ENVIRONMENT VARIABLES.

    Embedding JSON in the command line is escaping hell: its quotes fight
    the shell's quotes, on Windows `cmd` and PowerShell want different
    escaping rules, and the user's hook silently breaks the first time it
    sees a backslash in a path. An environment variable never raises that
    problem.
    """
    env = dict(os.environ)
    env["DORNICK_TOOL"] = env["DORNICK_ARAC"] = tool
    env["DORNICK_SESSION"] = env["DORNICK_OTURUM"] = session
    try:
        env["DORNICK_ARGS"] = json.dumps(args, ensure_ascii=False)[:32_000]
    except (TypeError, ValueError):  # pragma: no cover - unserialisable argument
        env["DORNICK_ARGS"] = "{}"
    # The most used field separately and bare: being able to write
    # `$DORNICK_PATH` without parsing JSON is what makes one-line hooks
    # possible.
    path = args.get("path") or args.get("target") or ""
    env["DORNICK_PATH"] = env["DORNICK_YOL"] = str(path) if isinstance(path, str) else ""
    return env


def _trim(text: str) -> str:
    text = text.strip()
    if len(text) <= MAX_OUTPUT:
        return text
    return text[:MAX_OUTPUT] + "\n… [kanca çıktısı kırpıldı]"


async def _launch(command: str, common: dict[str, Any]):
    """Starts the command in the platform's shell.

    On Windows PowerShell is called explicitly (as the `shell` tool does):
    `create_subprocess_shell` falls back to `cmd.exe` there, and the command
    the user wrote into the hook file ran in a different shell from the one
    Dornick uses everywhere else — the same line worked in one place and
    not here.
    """
    import sys

    if sys.platform == "win32":
        import shutil

        exe = shutil.which("pwsh") or shutil.which("powershell") or "powershell.exe"
        # EXIT CODE FIDELITY. The hook's contract rests on the exit code
        # ("non-zero: do not run the tool") and PowerShell keeps its own
        # exit code apart from a native program's: a hook calling `python -c
        # "sys.exit(3)"` looked like 1 from outside. The blocking decision
        # still came out right, but the reason sent to the model carried the
        # wrong code. If `$LASTEXITCODE` is set we exit with it; if not (only
        # cmdlets ran) PowerShell's own code stands.
        wrapped = f"{command}\nif ($null -ne $LASTEXITCODE) {{ exit $LASTEXITCODE }}"
        return await asyncio.create_subprocess_exec(
            exe, "-NoProfile", "-NonInteractive", "-Command", wrapped, **common)
    # POSIX: start in its own session so that on timeout the whole tree
    # falls with one signal.
    common.setdefault("start_new_session", True)  # pragma: no cover
    return await asyncio.create_subprocess_shell(command, **common)  # pragma: no cover


async def run(
    hook: Hook,
    *,
    tool: str,
    args: dict[str, Any],
    session: str,
    cwd: Path | str,
) -> Output:
    """Runs a single hook.

    Through the shell: the user writes a real command line with pipes, `&&`
    and variables into the hook file. Opens no console window
    (`environment.quiet_flags`) — while dornick runs under pythonw every
    write used to flash a cmd on the screen.
    """
    common: dict[str, Any] = dict(
        cwd=str(cwd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=_environment(tool, args, session),
        **environment.quiet_flags(),
    )
    try:
        proc = await _launch(hook.command, common)
    except (OSError, ValueError) as exc:
        # The hook's own fault must not kill the tool: this is a
        # configuration problem, not an obstacle to the user's work.
        return Output(hook, status="failed_to_start",
                      text=f"{type(exc).__name__}: {exc}")

    job = asyncio.ensure_future(proc.communicate())
    try:
        out, err = await asyncio.wait_for(asyncio.shield(job), hook.timeout)
    except asyncio.TimeoutError:
        # Kill the process TREE. Killing only the shell left the user's real
        # hook command running on the machine and, since it kept the pipes
        # open, this spot kept waiting: measured, a 2-second timeout turned
        # into a 60-second wait.
        await environment.kill_tree(proc)
        try:
            await asyncio.wait_for(job, 5)
        except (asyncio.TimeoutError, asyncio.CancelledError, OSError):
            job.cancel()
        return Output(hook, status="timeout")

    raw = (out or b"").decode("utf-8", errors="replace").strip()
    if not raw:
        raw = (err or b"").decode("utf-8", errors="replace").strip()
    return Output(hook, code=proc.returncode or 0, text=_trim(raw))


async def before_tool(
    state_dir: Path | str,
    tool: str,
    args: dict[str, Any],
    *,
    session: str = "",
    cwd: Path | str = ".",
) -> Verdict:
    """Hooks that run BEFORE the tool. If one refuses, the tool does not run.

    We stop at the first refusal: there is no point asking a second
    gatekeeper, the decision has already been made and running the rest
    only costs time (and possible side effects).
    """
    decision = Verdict()
    for hook in matching(state_dir, "before_tool", tool):
        result = await run(hook, tool=tool, args=args, session=session, cwd=cwd)

        if result.status == "failed_to_start":
            # A broken hook does not block the tool, but it is not hidden
            # either: the user must know their rule never ran.
            decision.notes.append(
                f"kanca çalıştırılamadı (`{hook.command}`): {result.text} — "
                "bu kural bu çağrıda uygulanmadı."
            )
            continue

        if result.status == "timeout":
            decision.allowed = False
            decision.reason = (
                f"Kanca reddetti: `{hook.command}` {hook.timeout:.0f} "
                "saniyede cevap vermedi. Kullanıcının bu araç için bir bekçisi "
                "var ve bekçi cevap vermiyor; güvenli taraf çalıştırmamak. "
                "Kullanıcıya bildir — kancayı ancak o düzeltebilir."
            )
            return decision

        if result.code != 0:
            decision.allowed = False
            explanation = result.text or "(kanca bir açıklama yazmadı)"
            decision.reason = (
                f"Kanca reddetti (çıkış kodu {result.code}): {explanation}\n"
                "Bu, kullanıcının kendi kuralı — sistem promptunda ya da "
                "izin listesinde değil, kendi kanca dosyasında. Kuralı aşmaya "
                "çalışma; başka bir yol dene ya da kullanıcıya sor."
            )
            return decision
    return decision


async def after_tool(
    state_dir: Path | str,
    tool: str,
    args: dict[str, Any],
    *,
    session: str = "",
    cwd: Path | str = ".",
) -> list[str]:
    """Hooks that run AFTER the tool. NO veto power.

    They cannot change the result because the work is already done: the
    file landed on disk, the command ran. Since "I refuse" has no
    consequence, the exit code only goes in as a note.
    """
    lines: list[str] = []
    for hook in matching(state_dir, "after_tool", tool):
        result = await run(hook, tool=tool, args=args, session=session, cwd=cwd)
        if result.status == "failed_to_start":
            lines.append(f"kanca çalıştırılamadı (`{hook.command}`): {result.text}")
            continue
        if result.status == "timeout":
            lines.append(
                f"kanca `{hook.command}` {hook.timeout:.0f} saniyede "
                "bitmedi ve durduruldu.")
            continue
        if result.text:
            prefix = "kanca" if result.code == 0 else f"kanca (çıkış {result.code})"
            lines.append(f"{prefix}: {_one_line(result.text)}")
        elif result.code != 0:
            lines.append(
                f"kanca `{hook.command}` {result.code} koduyla bitti (çıktı yok).")
    return lines


def _one_line(text: str, limit: int = 300) -> str:
    """Makes multi-line hook output fit into the tool result."""
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[:limit] + "…"
