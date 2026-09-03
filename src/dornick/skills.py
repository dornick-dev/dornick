"""Skills it writes itself.

Adding every new job by hand as a tool does not scale. Drawing a map,
reading a value from a PLC address, probing a device that arrived over USB,
opening the second camera — what these have in common is that all of them
are small enough for **the agent itself to write**. The long and hard ones
we provide as tools; the rest it should write.

A skill is a Python file sitting in the `yetenekler/` folder of the workshop:

    NAME = "harita"
    DESCRIPTION = "Koordinatları haritaya işler ve PNG üretir."
    SCHEMA = {"type": "object", "properties": {...}, "required": [...]}

    def run(args, ctx):
        ...
        return "harita/rota.png yazıldı"

Once the file is written, `skill action=load` turns it into a tool and from
that turn on it goes to the model together with its schema. On the next
startup it loads by itself.

Honesty about authority is needed: a skill runs in the same process, with
full Python. So it grants no more authority than the `shell` tool — both can
do whatever they like on the computer. It opens no new door, it tidies the
existing one: the job becomes named, schema'd and reusable. The write
location stays inside the workshop.
"""

from __future__ import annotations

import hashlib
import json
import sys
import traceback
import types
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# The folder inside the workshop where skills live.
FOLDER = "yetenekler"

# The approved-skills manifest (inside .dornick): {file_name: sha256}. Only
# files whose digest matches the one HERE are exec'd automatically AT
# STARTUP. A skill file runs with full Python in the same process; a random
# .py dropped into the workshop with `write_file` (e.g. an injection)
# running silently on every startup was unacceptable (security audit,
# 01.09). The manifest is in .dornick and guards.py closes it to tool
# writes — otherwise the same injection would write both the file and the
# digest and bypass the protection.
MANIFEST = "skills_onayli.json"


def _manifest_path(state_dir: Path | str) -> Path:
    return Path(state_dir) / MANIFEST


def _read_manifest(state_dir: Path | str) -> dict[str, str] | None:
    """The approved digest map; None if the file does not exist at all (migration signal)."""
    path = _manifest_path(state_dir)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}


def _write_manifest(state_dir: Path | str, mapping: dict[str, str]) -> None:
    try:
        _manifest_path(state_dir).write_text(
            json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _approve(state_dir: Path | str, path: Path) -> None:
    """Adds a file to the approved manifest (trusted creation/loading)."""
    mapping = _read_manifest(state_dir) or {}
    try:
        mapping[path.name] = _digest(path)
    except OSError:
        return
    _write_manifest(state_dir, mapping)

# The fields looked for in a skill file.
REQUIRED = ("NAME", "DESCRIPTION", "SCHEMA")

TEMPLATE = '''"""{title}

Bunu Dornick kendisi yazdı. Değiştirebilir, silebilirsin.
"""

NAME = "{name}"
DESCRIPTION = """{description}"""

SCHEMA = {{
    "type": "object",
    "properties": {{}},
    "required": [],
}}


def run(args, ctx):
    """Yeteneğin gövdesi.

    args: şemaya göre gelen sözlük.
    ctx:  ToolContext — `ctx.sandbox.root` atölyen, `ctx.config` ayarlar.

    Dönen değer metin olmalı: modele o metin gidiyor.
    """
    return "henüz bir şey yapmıyor"
'''


class SkillError(Exception):
    """The skill could not be loaded. The message goes to the model; it must teach."""


@dataclass(slots=True)
class Skill:
    name: str
    description: str
    schema: dict[str, Any]
    run: Any
    path: Path


def folder(sandbox_root: Path) -> Path:
    place = sandbox_root / FOLDER
    place.mkdir(parents=True, exist_ok=True)
    return place


# The seed tracking file: which standard skills were copied is recorded
# here. Whether the folder is empty could not be used — the user may have
# deliberately deleted a standard skill, and having it come back on every
# startup would make deleting meaningless.
SEEDED = ".tohumlar"


def seed(sandbox_root: Path, state_dir: Path | str | None = None) -> list[str]:
    """Copies the standard skills shipped with the package into the workshop — once.

    A copied file now belongs to the user: edited, deleted, it does not come
    back. If a new version brings a new standard skill only that one is
    added (copied if its name is not in the tracking file).
    """
    source = Path(__file__).parent / "assets" / "skills"
    if not source.is_dir():
        return []

    place = folder(sandbox_root)
    marker = place / SEEDED
    already = set()
    if marker.is_file():
        already = {line.strip() for line in marker.read_text(encoding="utf-8").splitlines()}

    planted: list[str] = []
    for packed in sorted(source.glob("*.py")):
        if packed.name in already:
            continue
        target = place / packed.name
        if not target.exists():
            target.write_text(packed.read_text(encoding="utf-8"), encoding="utf-8")
            planted.append(packed.stem)
            # A skill shipped with the package is trusted: record it in the
            # approved manifest so it can load at startup (otherwise it
            # would say "not approved").
            if state_dir is not None:
                _approve(state_dir, target)
        already.add(packed.name)

    marker.write_text("\n".join(sorted(already)) + "\n", encoding="utf-8")
    return planted


def load_file(path: Path) -> Skill:
    """Loads a single file as a skill.

    The module name is made unique by the file path: two files with the
    same name in two different folders must not overwrite each other.
    """
    if not path.is_file():
        raise SkillError(f"Dosya yok: {path}")

    key = f"dornick_skill_{abs(hash(str(path)))}"

    # The source is read and compiled by hand — NOT importlib's loader.
    #
    # The loader looks at `__pycache__`, and the cache is keyed by the
    # (mtime, size) pair: a fix turning "a + b" into "a * b" keeps the same
    # size and, if it lands on the same mtime tick, the old bytecode comes
    # back. The agent lived exactly this — it fixed its file, reloaded, and
    # fell back to the shell every time saying "the cached version still
    # uses the old code".
    try:
        source = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SkillError(f"{path.name} okunamadı: {exc}") from exc

    module = types.ModuleType(key)
    module.__file__ = str(path)
    # The module is put into sys.modules: if it holds a dataclass or typing
    # it needs to be able to resolve its own name.
    sys.modules[key] = module
    try:
        exec(compile(source, str(path), "exec"), module.__dict__)
    except Exception as exc:
        sys.modules.pop(key, None)
        # The stack trace goes to the model: without seeing which line blew
        # up it cannot fix it.
        raise SkillError(
            f"{path.name} çalıştırılamadı:\n{traceback.format_exc(limit=3)}"
        ) from exc

    missing = [field for field in REQUIRED if not hasattr(module, field)]
    if missing:
        raise SkillError(
            f"{path.name} eksik: {', '.join(missing)}. "
            "Bir yetenek dosyası NAME, DESCRIPTION, SCHEMA ve run(args, ctx) içermeli."
        )
    if not callable(getattr(module, "run", None)):
        raise SkillError(f"{path.name} içinde `run(args, ctx)` fonksiyonu yok.")

    name = str(module.NAME).strip()
    if not name.replace("_", "").isalnum():
        raise SkillError(
            f"Geçersiz ad: {name!r}. Yalnızca harf, rakam ve alt çizgi kullan."
        )

    schema = module.SCHEMA
    if not isinstance(schema, dict) or schema.get("type") != "object":
        raise SkillError(f"{path.name}: SCHEMA bir JSON Schema nesnesi olmalı.")

    return Skill(
        name=name,
        description=str(module.DESCRIPTION).strip(),
        schema=schema,
        run=module.run,
        path=path,
    )


def discover(sandbox_root: Path, state_dir: Path | str | None = None,
             *, onayla: bool = False) -> tuple[list[Skill], list[str]]:
    """Loads the skills in the folder. (loaded ones, errors)

    A broken file does not block the others: the error goes into the list
    and the program keeps running. Otherwise a single typo strips the agent
    of all its skills.

    Security (when state_dir is given): only files in the approved manifest
    (digest matching) are loaded. If the manifest does not exist at all this
    is the FIRST-RUN migration — the existing files are considered trusted
    and recorded (nobody's installation breaks on upgrade). With
    `onayla=True` (an explicit `write`/`load` through the tool, a human
    action that passed the permission gate) the valid files found are
    written to the manifest; at startup (onayla=False) an unapproved file is
    not loaded and is reported as "not approved".

    state_dir=None: the old behaviour — everything loads (for tests and
    observation-only callers).
    """
    found: list[Skill] = []
    broken: list[str] = []
    files = [p for p in sorted(folder(sandbox_root).glob("*.py"))
             if not p.name.startswith("_")]

    manifest: dict[str, str] | None = None
    migrated = False
    if state_dir is not None:
        manifest = _read_manifest(state_dir)
        if manifest is None:
            # First run: the existing files are trusted. Record and load.
            manifest = {}
            for p in files:
                try:
                    manifest[p.name] = _digest(p)
                except OSError:
                    pass
            _write_manifest(state_dir, manifest)
            migrated = True

    for path in files:
        if manifest is not None and not migrated:
            try:
                current = _digest(path)
            except OSError:
                continue
            if not onayla and manifest.get(path.name) != current:
                broken.append(
                    f"{path.name}: onaylanmadı — bu dosya `skill` aracıyla "
                    "yazılmadı ya da elle değişti; güvenlik gereği açılışta "
                    "kendiliğinden yüklenmedi. Onaylamak için içeriğini "
                    "`skill action=write` ile yeniden yaz ya da `skill "
                    "action=load` de (ikisi de izin kapısından geçer)."
                )
                continue
        try:
            skill = load_file(path)
        except SkillError as exc:
            broken.append(str(exc))
            continue
        found.append(skill)
        if onayla and state_dir is not None:
            _approve(state_dir, path)
    return found, broken


def _clean_name(name: str) -> str:
    clean = name.strip().lower().replace(" ", "_")
    if not clean.replace("_", "").isalnum():
        raise SkillError(f"Geçersiz ad: {name!r}. Harf, rakam ve alt çizgi kullan.")
    return clean


def scaffold(sandbox_root: Path, name: str, description: str) -> Path:
    """Writes an empty skill file and returns its path.

    We provide the skeleton because remembering the format should not be
    the model's job: a file written with a wrong field name does not load,
    and the reason only becomes clear when it is tried.
    """
    clean = _clean_name(name)
    path = folder(sandbox_root) / f"{clean}.py"
    if path.exists():
        raise SkillError(
            f"{path.name} zaten var. Değiştirmek için `skill action=write` kullan."
        )

    path.write_text(
        TEMPLATE.format(
            title=description.strip() or clean,
            name=clean,
            description=description.strip() or clean,
        ),
        encoding="utf-8",
    )
    return path


def save(sandbox_root: Path, name: str, code: str,
         state_dir: Path | str | None = None) -> Skill:
    """Writes the full skill file and validates it.

    If the format is broken the file stays on disk (so it can be fixed) but
    SkillError is raised — broken code does not enter the tool registry.

    If `state_dir` is given the file is recorded in the approved manifest:
    this is the `skill action=write` path that passed the permission gate —
    trusted creation. If validation fails it does NOT enter the manifest
    (broken code must not count as approved).
    """
    clean = _clean_name(name)
    if not (code or "").strip():
        raise SkillError("`code` boş olamaz. NAME, DESCRIPTION, SCHEMA ve run(args, ctx) yaz.")

    path = folder(sandbox_root) / f"{clean}.py"
    path.write_text(code, encoding="utf-8")
    skill = load_file(path)   # validation first; if it blows up nothing is written to the manifest
    if state_dir is not None:
        _approve(state_dir, path)
    return skill


def register(registry: Any, skills: list[Skill]) -> tuple[list[str], list[str]]:
    """Adds the skills to the tool registry. (newly added, refreshed)

    An already-loaded skill is **refreshed**, not skipped. The earlier
    version skipped, and when the agent fixed its own file and reloaded it
    the old version in memory kept running — the agent noticed, said "the
    cached version uses the old code" and fell back to the shell every time:
    the skill had become slower than having no skill.

    A skill whose name collides with a built-in tool is still skipped: a
    skill named `shell` would replace the permission gate.
    """
    from .tools.base import ToolResult, ToolSpec

    added: list[str] = []
    updated: list[str] = []
    for skill in skills:
        existing = registry.get(skill.name)
        if existing is not None and existing.source != "yetenek":
            continue

        spec = ToolSpec(
            name=skill.name,
            description=skill.description,
            input_schema=skill.schema,
            handler=_handler(skill, ToolResult),
            # What it does is unknown: it may write files, go out to the
            # network. It has to pass the permission gate.
            mutates=True,
            parallel_safe=False,
            source="yetenek",
        )
        if existing is None:
            registry.register(spec)
            added.append(skill.name)
        else:
            registry.replace(spec)
            updated.append(skill.name)
    return added, updated


def _handler(skill: Skill, ToolResult: Any) -> Any:
    """Wraps the skill in the tool interface.

    `run` may be sync or async: the agent should not have to make a simple
    skill it wrote `async`. A sync one runs in a separate thread, otherwise
    a long-running skill locks the whole loop.
    """
    import asyncio
    import inspect

    async def call(args: dict[str, Any], ctx: Any) -> Any:
        try:
            if inspect.iscoroutinefunction(skill.run):
                answer = await skill.run(args, ctx)
            else:
                answer = await asyncio.to_thread(skill.run, args, ctx)
        except Exception:
            # A crashing skill must not bring the agent down; the stack
            # trace goes to the model so it can fix the code it wrote.
            return ToolResult.error(
                f"'{skill.name}' hata verdi:\n{traceback.format_exc(limit=4)}\n"
                f"Dosya: {skill.path}"
            )

        if isinstance(answer, ToolResult):
            return answer
        return ToolResult(content=str(answer) if answer is not None else "(boş sonuç)")

    return call
