"""Apps: the layer that makes what the agent produces runnable.

The agent builds a dashboard in the workshop, writes a script, makes a
desktop tool — but while these stay as files they are no different from a
file explorer for the user. This module reads the workshop as an
**application catalogue**: it gives everything as a hierarchical tree,
classifies every file by kind (a website, a runnable script, a document)
and extracts its title. The UI shows this in a panel and opens it on click:
a web one inside a frame within the app, a running script as its own process.

Two sources together: **automatic classification** (extension + content)
solves most of it; if the agent wants to say more it can leave an
`app.json` manifest (name, kind, entry file, run command, address). If the
manifest exists it wins — the agent can say "this is a web app, on that
port" itself.

Security: running is free **only for files inside the workshop**. The
agent's own product; we do not launch the user's files from here.
"""

from __future__ import annotations

import json
import re
import os
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from . import environment

# Noise skipped in the scan. Showing these makes the catalogue unusable.
SKIP = {"__pycache__", ".git", ".venv", "node_modules", ".idea", ".vscode"}
# Dornick's own infrastructure folders sit in the workshop but are NOT
# projects: showing them as a "run tool" card pollutes the panel (the user:
# "projects, not a pile of files"). yetenekler=skills, gelen=inbox,
# gorseller=images, cihazlar=device records.
INTERNAL = {"yetenekler", "gelen", "gorseller", "görseller", "cihazlar"}
# Files that are NOT an app: build residue, office/binary documents, temp/lock.
# These do not appear as cards (they are reachable directly from the workshop folder).
SKIP_SUFFIX = {".pyc", ".pyo", ".log.migrated", ".docx", ".doc", ".xlsx",
               ".xls", ".pptx", ".ppt", ".tmp", ".bak", ".lock", ".swp"}

# Catalogue depth. An infinitely deep tree is both slow and unreadable; the
# workshop is expected to hold one subfolder per project, this is enough.
MAX_DEPTH = 5

# Extension → app kind.
#   web   a page opened in the browser/frame
#   run   runnable: script, desktop tool, command file
#   doc   something read: data, report, log
#
# The workshop is not single-language: the agent produces Node, PHP, .NET,
# Java as readily as Python. If the runtime is missing on the machine,
# launch says so with a clear error.
WEB = {".html", ".htm"}
RUN = {".py", ".pyw", ".ps1", ".bat", ".cmd", ".exe", ".sh",
       ".js", ".mjs", ".cjs", ".php", ".rb", ".jar"}
DOC = {".md", ".txt", ".csv", ".tsv", ".json", ".jsonl", ".yaml", ".yml",
       ".toml", ".xml", ".svg"}

# Name of the manifest file. If present the folder counts as a single app.
MANIFEST = "app.json"

# How many levels discovery descends. An app can sit at the bottom of the
# workshop (`site/panolar/kuyu/app.json`); looking one level down made it
# invisible. Three levels catch every hand-made layout, deeper becomes
# library/build junk.
PROJECT_DEPTH = 3

# Folders never entered during deep discovery: dependency/build/junk. An
# `app.json` inside these is not the user's app but a package's own
# manifest — showing it as a card pollutes the catalogue.
DISCOVERY_SKIP = SKIP | {"vendor", "dist", "build", "site-packages", ".geri-donusum",
                         "bower_components", "target", "obj", "bin"}

# The text returned to the MODEL when the manifest is written in the wrong
# place or validation fails. It gives a RECIPE, not a rule: where, relative
# to what, with an example. Kept in one place so the model can read this
# sentence and move the manifest to the right place.
MANIFEST_OGRETICI = (
    "Uygulama manifesti uygulamanın KENDİ klasöründe `app.json` olmalı; "
    "`entry` o klasöre göreli. Örnek: atolye/borsa-ara/app.json → "
    '{"entry": "static/index.html", "run": "py app.py"}'
)

_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_NAME = re.compile(r"""^\s*NAME\s*=\s*["'](.+?)["']""", re.MULTILINE)
_DESC = re.compile(r"""^\s*DESCRIPTION\s*=\s*["'](.+?)["']""", re.MULTILINE)


@dataclass(slots=True)
class App:
    """A node in the catalogue: folder or file."""

    name: str                       # the name shown on screen
    path: str                       # path relative to the workshop (posix)
    type: str                       # folder | web | run | doc
    title: str = ""                 # title extracted from the file
    run: str = ""                   # run command (for the run kind)
    url: str = ""                   # the web app's address (if the manifest gives one)
    children: list["App"] = field(default_factory=list)


@dataclass(slots=True)
class Project:
    """A PROJECT in the workshop — not a file, a unit of work.

    When dornick produces something (like the Modbus web client) a folder
    appears: backend, frontend, README. For the user the real unit is this
    project; not the individual files. The panel shows these as cards; on
    click "how to run" + Run appears.
    """

    name: str
    path: str                 # relative to the workshop (folder or single file)
    scope: str = ""           # "in-app" | "external" | "" (dornick should ask)
    kind: str = "tool"        # web | service | tool | doc
    entry: str = ""           # opening file (web: index.html)
    run: str = ""             # run command
    url: str = ""             # live address if the manifest gives one
    desc: str = ""            # one sentence: WHAT this app DOES (top of the card)
    howto: str = ""           # README / how to run (short)
    single: bool = False      # single-file (not a folder)
    # Validation: if the manifest promises something and does not deliver
    # the app is NOT DROPPED from the list — it stays with an "eksik" badge
    # and its REASON. Silently vanishing ("I made my app but it isn't in the
    # panel") was exactly the flaw fixed. (Wire keys: `eksik`, `neden`.)
    eksik: bool = False
    neden: str = ""
    # Live state: is there a running process belonging to this app.
    pid: int = 0
    address: str = ""         # "http://127.0.0.1:8090"
    port: int = 0             # detected/declared port
    stoppable: bool = False   # can it be stopped from the panel (not Dornick itself)


def projects(sandbox_root: Path, base: Path | None = None) -> list[dict[str, Any]]:
    """Turns the workshop into PROJECT units (not a file tree).

    Backwards-compatible surface: only the project list. A caller that also
    wants the stray-manifest warnings uses `katalog()`.
    """
    return katalog(sandbox_root, base)["projects"]


def katalog(sandbox_root: Path, base: Path | None = None,
            live: bool = True) -> dict[str, Any]:
    """The workshop's app catalogue: projects + manifest problems.

    An app = a FOLDER containing `app.json` (at most `PROJECT_DEPTH` levels
    deep) or a self-contained file (a pano.html, a script). Top-level
    folders without a manifest also count as projects by intuition — the
    workshop must be usable without writing manifests.

    Manifests at the workshop ROOT are NOT apps: the workshop is not an app,
    it is where apps live. Stray files like `app.json` or
    `llm-donanim-app.json` at the root are ignored and reported under
    `sorunlar` WITH THE REASON — when the model writes the manifest in the
    wrong place it gets an instructive warning, not silence.
    """
    root = sandbox_root.resolve()
    ref = (base or root).resolve()
    if not root.is_dir():
        return {"projects": [], "sorunlar": []}

    problems = _stray_manifests(root)
    stray = {s["path"] for s in problems}

    out: list[Project] = []
    try:
        entries = sorted(root.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
    except OSError:
        return {"projects": [], "sorunlar": problems}

    for path in entries:
        # Hidden, internal infrastructure, or temp/lock files (~$Word.docx,
        # ~backup) must not appear among the projects.
        if path.name in SKIP or path.name.startswith(".") or path.name.startswith("~"):
            continue
        if path.is_dir():
            if path.name in INTERNAL or path.name in DISCOVERY_SKIP:
                continue
            out.extend(_folder_projects(path, ref))
        elif path.is_file() and path.suffix.lower() not in SKIP_SUFFIX \
                and path.name != MANIFEST and path.name not in stray:
            out.append(_project_from_file(path, ref))

    if live:
        _mark_live(out, root, ref)
    return {"projects": [asdict(p) for p in out], "sorunlar": problems}


def _stray_manifests(root: Path) -> list[dict[str, str]]:
    """Manifests sitting at the workshop ROOT that belong to no app.

    Two cases: (1) `atolye/app.json` — describes the whole workshop as a
    single app; (2) `atolye/llm-donanim-app.json` — a folder-less manifest
    with a made-up name. Neither enters discovery; a one-line warning +
    `MANIFEST_OGRETICI` is returned to the user and the model.
    """
    out: list[dict[str, str]] = []
    try:
        entries = sorted(root.iterdir(), key=lambda p: p.name.lower())
    except OSError:
        return out
    for path in entries:
        if not path.is_file():
            continue
        name = path.name
        if name != MANIFEST and not name.lower().endswith("-app.json"):
            continue
        out.append({
            "path": name,
            "uyari": f"atolye/{name} geçersiz — manifest uygulamanın kendi "
                     "klasöründe olmalı",
            "ogretici": MANIFEST_OGRETICI,
        })
    return out


def _folder_projects(folder: Path, ref: Path) -> list[Project]:
    """The project(s) coming out of one top-level folder.

    If it has its own manifest: a single project, that one. Otherwise
    manifest-bearing folders beneath it (at most `PROJECT_DEPTH` levels) are
    looked for; if found, the real apps are THOSE — the parent folder is
    only a container and is not repeated as a card. With no manifest at all
    the old behaviour: the folder itself is a project by intuition.
    """
    if (folder / MANIFEST).is_file():
        return [_project_from_folder(folder, ref)]
    inner = _manifest_folders(folder, PROJECT_DEPTH - 1)
    if inner:
        return [_project_from_folder(p, ref) for p in inner]
    return [_project_from_folder(folder, ref)]


def _manifest_folders(folder: Path, remaining: int) -> list[Path]:
    """Folders under `folder` carrying a manifest (at most `remaining` levels)."""
    if remaining <= 0:
        return []
    out: list[Path] = []
    try:
        entries = sorted(folder.iterdir(), key=lambda p: p.name.lower())
    except OSError:
        return out
    for path in entries:
        if not path.is_dir() or path.name.startswith(".") or path.name in DISCOVERY_SKIP:
            continue
        if (path / MANIFEST).is_file():
            out.append(path)          # a manifest-bearing folder is not descended INTO
            continue
        out.extend(_manifest_folders(path, remaining - 1))
    return out


def _project_from_folder(folder: Path, root: Path) -> Project:
    manifest = _manifest_data(folder)
    kind, entry, run = _detect(folder)
    howto = _read_howto(folder)

    if manifest:
        scope = _scope(manifest.get("scope"))
        entry_rel = str(manifest.get("entry") or entry or "")
        run_cmd = str(manifest.get("run") or run)
        # The agent often writes a GUI/.NET app as `tool` → the UI says "script".
        # The real WinExe/desktop intuition on disk wins.
        mkind = str(manifest.get("type") or manifest.get("kind") or kind)
        if kind == "desktop" and mkind in ("tool", "service", "betik", "script"):
            mkind = "desktop"
            if not run_cmd.strip() and run:
                run_cmd = run
            if not entry_rel and entry:
                entry_rel = entry
        reason = _validate(folder, entry_rel, run_cmd)
        return Project(
            name=str(manifest.get("name") or folder.name),
            path=_rel(folder, root),
            scope=scope,
            kind=mkind,
            entry=_rel(folder / entry_rel, root) if entry_rel else "",
            run=run_cmd,
            url=str(manifest.get("url") or ""),
            desc=str(manifest.get("desc") or "") or _first_line(howto),
            howto=str(manifest.get("howto") or howto),
            eksik=bool(reason),
            neden=reason,
            port=_port_hint(folder, manifest, entry_rel),
        )

    return Project(
        name=folder.name,
        path=_rel(folder, root),
        scope="",                        # no manifest → dornick should ask about scope
        kind=kind,
        entry=_rel(folder / entry, root) if entry else "",
        run=run,
        desc=_first_line(howto),
        howto=howto,
        port=_port_hint(folder, None, entry),
    )


def _validate(folder: Path, entry_rel: str, run_cmd: str) -> str:
    """Does the manifest keep its promise? If not, the REASON (else empty text).

    The app does not drop from the list — it stays with the "eksik" badge
    and its reason. A mistyped `entry` ("site/llm-donanım.html" while the
    file is `llm-donanim.html`) used to silently become an empty Open
    button; now the reason is written on the card.
    """
    if entry_rel:
        try:
            if not (folder / entry_rel).exists():
                return f"entry bulunamadı: {entry_rel}"
        except OSError:
            return f"entry okunamadı: {entry_rel}"
    if run_cmd.strip() and not _command_makes_sense(run_cmd, folder):
        return f"run komutu anlaşılmadı: {run_cmd.strip()}"
    if not entry_rel and not run_cmd.strip():
        return "ne `entry` ne `run` var — uygulama nasıl açılacağı belirsiz"
    return ""


# Tools that count as meaningful as the first word of a run command. The
# list is cautious: a command we do not recognise still counts as valid if
# it is on PATH or corresponds to a file in the folder — the aim is not
# false alarms but catching the blatantly broken command ("run something").
_KNOWN_COMMANDS = {"npm", "npx", "yarn", "pnpm", "dotnet", "java", "make",
                   "cargo", "go", "deno", "bun", "flask", "uvicorn",
                   "gunicorn", "streamlit", "rails", "composer"}


def _command_makes_sense(run_cmd: str, folder: Path) -> bool:
    import shutil as _shutil

    tokens = run_cmd.split()
    if not tokens:
        return False
    head = tokens[0].lower().removesuffix(".exe")
    if head in _SIMPLE_RUNNERS or head in _KNOWN_COMMANDS:
        return True
    try:
        if (folder / tokens[0]).exists():
            return True
    except OSError:
        pass
    return bool(_shutil.which(tokens[0]))


# A port declared in source/text. Patterns tried in order; all tied to the
# word "port" or to an address — a bare number is not captured (mistaking a
# version number for a port would produce a false live badge).
_PORT_PATTERNS = (
    re.compile(r"""port\s*[=:]\s*["']?(\d{4,5})""", re.IGNORECASE),
    re.compile(r"""--port[\s=]+(\d{4,5})"""),
    re.compile(r"""\.listen\(\s*(\d{4,5})"""),
    re.compile(r"""(?:localhost|127\.0\.0\.1|0\.0\.0\.0)[:/](\d{4,5})"""),
)


def _port_hint(folder: Path, manifest: dict[str, Any] | None, entry_rel: str) -> int:
    """Which port this app lives on — declared or written in source.

    Order: `port`/`url` in the manifest, then the `run`/`howto` text, last
    the source of the entry or server file (`app.run(..., port=8090)`). The
    live badge looks at whether this port is really LISTENED on; proof,
    not a guess.
    """
    if manifest:
        try:
            declared = int(str(manifest.get("port") or "").strip() or 0)
            if 1 <= declared <= 65535:
                return declared
        except ValueError:
            pass
        for key in ("url", "run", "howto", "desc"):
            found = _port_from(str(manifest.get(key) or ""))
            if found:
                return found

    candidates: list[Path] = []
    if entry_rel:
        candidates.append(folder / entry_rel)
    for name in ("app.py", "main.py", "server.py", "run.py",
                 "server.js", "app.js", "index.js", "main.js"):
        candidates.append(folder / name)
    for candidate in candidates:
        try:
            if not candidate.is_file() or candidate.suffix.lower() not in RUN:
                continue
        except OSError:
            continue
        found = _port_from(_head(candidate, 20000))
        if found:
            return found
    return 0


def _port_from(text: str) -> int:
    for pattern in _PORT_PATTERNS:
        match = pattern.search(text or "")
        if match:
            value = int(match.group(1))
            if 1024 <= value <= 65535:
                return value
    return 0


def _project_from_file(path: Path, root: Path) -> Project:
    suffix = path.suffix.lower()
    if suffix in WEB:
        title = _html_title(path)
        return Project(name=path.name, path=_rel(path, root), kind="web",
                       entry=_rel(path, root), scope="in-app", single=True,
                       desc=_first_line(title), howto=title)
    if suffix in RUN:
        title = _script_title(path)
        return Project(name=path.name, path=_rel(path, root), kind="tool",
                       entry=_rel(path, root), run=_run_line(path), single=True,
                       desc=_first_line(title), howto=title)
    return Project(name=path.name, path=_rel(path, root), kind="doc",
                   entry=_rel(path, root), single=True)


def _first_line(text: str, limit: int = 110) -> str:
    """The one-sentence summary shown on the card: the text's first meaningful line.

    Heading markers (#) are stripped; trimmed if long. This line answers
    "I pressed Run but I don't know WHAT this app DOES".
    """
    for line in str(text or "").splitlines():
        line = line.strip().lstrip("#").strip()
        if line:
            return line if len(line) <= limit else line[: limit - 1] + "…"
    return ""


def _manifest_data(folder: Path) -> dict[str, Any] | None:
    path = folder / MANIFEST
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _scope(value: Any) -> str:
    v = str(value or "").lower().replace("_", "-")
    if v in ("in-app", "internal", "sistem-ici", "sistem-içi", "içeride", "iceride"):
        return "in-app"
    if v in ("external", "dis", "dış", "dis-proje"):
        return "external"
    return ""


def _skipped_path(path: Path) -> bool:
    """Build/dependency junk — the entry file is not picked from here."""
    return any(part in DISCOVERY_SKIP or part == "__pycache__" for part in path.parts)


def _csproj_is_desktop(csproj: Path) -> bool:
    """WinExe / WinForms / WPF — a desktop app, not a console service."""
    try:
        text = csproj.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False
    return any(signature in text for signature in (
        "WinExe", "UseWindowsForms", "UseWPF",
        "Microsoft.NET.Sdk.WindowsDesktop",
    ))


def _desktop_exe(folder: Path) -> Path | None:
    """The folder's real GUI .exe — preferably at the root, not from bin/obj noise.

    In .NET WinExe projects like ScadaStudio 'Start' was most of the time
    bound to the wrong script or a silent process; the real exe must be
    opened with `os.startfile`.
    """
    if not folder.is_dir():
        return None
    name = folder.name
    direct = folder / f"{name}.exe"
    if direct.is_file():
        return direct
    candidates: list[Path] = []
    try:
        for path in folder.rglob("*.exe"):
            if not path.is_file() or _skipped_path(path):
                continue
            # obj/ intermediate outputs and vshost noise.
            if "obj" in path.parts or ".vshost." in path.name.lower():
                continue
            candidates.append(path)
    except OSError:
        return None
    if not candidates:
        return None
    # Name match > publish > Release > newest.
    def score(p: Path) -> tuple:
        parts = {x.lower() for x in p.parts}
        return (
            0 if p.stem.lower() == name.lower() else 1,
            0 if "publish" in parts else 1,
            0 if "release" in parts else 1,
            -p.stat().st_mtime,
        )
    candidates.sort(key=score)
    return candidates[0]


def _detect(folder: Path) -> tuple[str, str, str]:
    """Senses the folder's kind, entry file and run command.

    web       index.html (+ optional server)
    service   server script / Node / API
    desktop   WinExe / GUI .exe (desktop app)
    tool      console script
    doc       document

    Intuition is kept minimal: if the agent knows better it says so with an
    `app.json` manifest and the manifest always wins — but the agent writing
    a GUI app as `tool` is softly corrected (see the project builder).
    """
    index = _find(folder, ("index.html", "index.htm"))
    server = _find(folder, ("app.py", "main.py", "server.py", "run.py",
                            "server.js", "app.js", "index.js", "main.js",
                            "index.php"))
    run = _package_run(folder) or (_run_line(server) if server else "")
    csproj = _find(folder, None, {".csproj"})
    if csproj and _csproj_is_desktop(csproj):
        exe = _desktop_exe(folder)
        if exe:
            return "desktop", _rel(exe, folder), ""
        return "desktop", _rel(csproj, folder), f'dotnet run --project "{csproj.name}"'
    if not run and csproj:
        return "service", _rel(csproj, folder), "dotnet run"
    if index and (server or run):
        return "web", _rel(index, folder), run
    if index:
        return "web", _rel(index, folder), ""
    if server or run:
        entry = _rel(server, folder) if server else ""
        return "service", entry, run
    # GUI exe (no csproj / publish folder): desktop, not a script.
    exe = _desktop_exe(folder)
    if exe:
        return "desktop", _rel(exe, folder), ""
    any_run = _find(folder, None, RUN)
    if any_run:
        return "tool", _rel(any_run, folder), _run_line(any_run)
    page = _newest(folder, WEB)
    if page:
        return "web", _rel(page, folder), ""
    return "doc", "", ""


def _find(folder: Path, names: tuple[str, ...] | None, suffixes: set[str] | None = None) -> Path | None:
    """The first matching file in the folder (a few levels) — build junk excluded."""
    try:
        for path in sorted(folder.rglob("*")):
            if not path.is_file() or path.name in SKIP or _skipped_path(path):
                continue
            if names and path.name.lower() in names:
                return path
            if suffixes and path.suffix.lower() in suffixes:
                return path
    except OSError:
        return None
    return None


def _package_run(folder: Path) -> str:
    """Run command if package.json exists: the start or dev script.

    The Node project's own manifest knows best how it is started; more
    accurate than trying to sense individual files.
    """
    path = folder / "package.json"
    if not path.is_file():
        return ""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    scripts = data.get("scripts") if isinstance(data, dict) else None
    if not isinstance(scripts, dict):
        return ""
    if "start" in scripts:
        return "npm start"
    if "dev" in scripts:
        return "npm run dev"
    main = str(data.get("main") or "").strip()
    return f"node {main}" if main else ""


def _newest(folder: Path, suffixes: set[str]) -> Path | None:
    """The newest matching file in the folder (a few levels)."""
    best: Path | None = None
    best_t = -1.0
    try:
        for path in folder.rglob("*"):
            if not path.is_file() or _skipped_path(path):
                continue
            if path.suffix.lower() not in suffixes:
                continue
            t = path.stat().st_mtime
            if t > best_t:
                best, best_t = path, t
    except OSError:
        return None
    return best


def _read_howto(folder: Path) -> str:
    """The first part of the README — for "how to run"."""
    for name in ("README.md", "README.txt", "readme.md", "OKU.md", "KULLANIM.md"):
        path = folder / name
        if path.is_file():
            return _head(path, 2000).strip()
    return ""


def catalog(sandbox_root: Path, base: Path | None = None) -> App:
    """Turns the workshop into a hierarchical app tree.

    The root is always a folder node; files and subfolders beneath it.
    Empty folders show too — if the agent opened a folder for a project and
    has not filled it yet, that is a state as well.

    `base` determines what the paths are relative to. The UI's file-reading
    endpoint (`/api/files`) resolves against the workspace; so the server
    passes the workspace as base so a web app really opens on click. If not
    given, the workshop itself — the tests use this plain form.
    """
    root = sandbox_root
    ref = (base or root).resolve()
    node = App(name=root.name or "atolye", path=_rel(root, ref), type="folder")
    if root.is_dir():
        node.children = _scan(root, ref, 0)
    return node


def _scan(folder: Path, root: Path, depth: int) -> list[App]:
    if depth >= MAX_DEPTH:
        return []
    out: list[App] = []
    try:
        entries = sorted(folder.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
    except OSError:
        return []

    for path in entries:
        if path.name in SKIP or path.name.startswith("."):
            continue
        if path.is_dir():
            # A manifest-bearing folder is a single app: instead of listing
            # its insides one by one we show the app the agent described.
            manifest = _manifest(path, root)
            if manifest is not None:
                out.append(manifest)
                continue
            node = App(name=path.name, path=_rel(path, root), type="folder")
            node.children = _scan(path, root, depth + 1)
            out.append(node)
        elif path.is_file():
            if path.suffix.lower() in SKIP_SUFFIX or path.name == MANIFEST:
                continue
            app = _file(path, root)
            if app is not None:
                out.append(app)
    return out


def _file(path: Path, root: Path) -> App | None:
    suffix = path.suffix.lower()
    if suffix in WEB:
        return App(name=path.name, path=_rel(path, root), type="web",
                   title=_html_title(path))
    if suffix in RUN:
        return App(name=path.name, path=_rel(path, root), type="run",
                   title=_script_title(path), run=_run_line(path))
    if suffix in DOC:
        return App(name=path.name, path=_rel(path, root), type="doc")
    # An unrecognised extension counts as a document too: the viewer opens it as source.
    return App(name=path.name, path=_rel(path, root), type="doc")


def _manifest(folder: Path, root: Path) -> App | None:
    """If `app.json` exists, reads the folder as a single app.

    The agent's own description overrides automatic classification: so it
    can say "this is a web app, its entry is site/index.html, it runs at
    that address". A broken manifest does not drop the folder — None is
    returned and the normal scan continues.
    """
    path = folder / MANIFEST
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None

    kind = str(data.get("type") or "").lower()
    kind = kind if kind in ("web", "run", "doc") else "run"
    entry = str(data.get("entry") or "").strip()
    entry_path = (folder / entry) if entry else folder
    return App(
        name=str(data.get("name") or folder.name),
        path=_rel(entry_path, root),
        type=kind,
        title=str(data.get("description") or ""),
        run=str(data.get("run") or (_run_line(entry_path) if kind == "run" else "")),
        url=str(data.get("url") or ""),
    )


# -- title extraction ---------------------------------------------------


def _html_title(path: Path) -> str:
    head = _head(path, 4000)
    match = _TITLE.search(head)
    return _clean(match.group(1)) if match else ""


def _script_title(path: Path) -> str:
    head = _head(path, 2000)
    # A skill file carries NAME/DESCRIPTION; an ordinary script a docstring.
    if (m := _DESC.search(head)):
        return _clean(m.group(1))
    if (m := _NAME.search(head)):
        return _clean(m.group(1))
    return _docstring(head)


def _docstring(head: str) -> str:
    stripped = head.lstrip()
    for quote in ('"""', "'''"):
        if stripped.startswith(quote):
            end = stripped.find(quote, 3)
            body = stripped[3:end if end > 0 else None]
            return _clean(next((ln for ln in body.splitlines() if ln.strip()), ""))
    # Without a docstring the first meaningful COMMENT line: scripts written
    # by Dornick (and by people) mostly start with "# Does this" — the card
    # summary comes from there.
    for line in stripped.splitlines()[:12]:
        line = line.strip()
        if not line:
            continue
        if line.startswith("#!") or "coding" in line[:24]:
            continue   # shebang / encoding declaration is not a summary
        if line.startswith(("#", "//", "<#")):
            text = line.lstrip("#/<").strip()
            if len(text) > 3:
                return _clean(text)
            continue
        break   # we reached code: there was no summary comment
    return ""


def _run_line(path: Path) -> str:
    """The readable form of the command that runs this file (shown in the UI)."""
    suffix = path.suffix.lower()
    if suffix in (".py", ".pyw"):
        return f"python {path.name}"
    if suffix == ".ps1":
        return f"powershell {path.name}"
    if suffix in (".bat", ".cmd", ".exe"):
        return path.name
    if suffix == ".sh":
        return f"bash {path.name}"
    if suffix in (".js", ".mjs", ".cjs"):
        return f"node {path.name}"
    if suffix == ".php":
        return f"php {path.name}"
    if suffix == ".rb":
        return f"ruby {path.name}"
    if suffix == ".jar":
        return f"java -jar {path.name}"
    return path.name


# -- running ------------------------------------------------------------


# Launched processes: PID → record. The UI reads the "running" state, the
# live address and stopping from here. Those opened with `os.startfile`
# (exe/bat) give no handle and cannot be tracked; only Popen-started ones are here.
_PROCS: dict[int, dict[str, Any]] = {}


def launch(sandbox_root: Path, rel_path: str, base: Path | None = None) -> dict[str, Any]:
    """Starts a script/tool/project in the workshop as its own process.

    The path must be inside the workshop: what runs is the agent's own
    product, not the user's files. `base` is what the path is resolved
    against (same as the catalogue); the boundary is the workshop in any
    case. The process is detached — the UI does not wait for it, it reports
    that it started. Trackable ones are recorded in `_PROCS` so that
    state/address/stop are possible later.

    If the path is a FOLDER it starts as a project: with a desktop .exe
    `os.startfile` (so the window opens); otherwise the manifest `run` /
    the sensed command. So a WinExe .NET app does not say "started" and
    stay without a UI.
    """
    root = sandbox_root.resolve()
    ref = (base or root).resolve()
    target = (ref / rel_path).resolve()
    if target != root and root not in target.parents:
        return {"ok": False, "error": "Atölye dışı: yalnızca kendi ürettiğin çalıştırılır."}

    folder = target if target.is_dir() else (target.parent if target.is_file() else None)
    gui = _desktop_exe(folder) if folder is not None else None

    # If the same thing is already running: for web/service do not start a
    # second one. For a desktop GUI "already" as silent success is wrong —
    # reopen the window.
    for pid, info in list(_PROCS.items()):
        if info.get("path") == rel_path and info["proc"].poll() is None:
            if gui is not None:
                try:
                    import os
                    os.startfile(str(gui))  # type: ignore[attr-defined]
                except Exception as exc:
                    return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
                return {"ok": True, "pid": pid, "path": rel_path,
                        "already": True, "note": "Pencere yeniden açıldı."}
            return {"ok": True, "pid": pid, "path": rel_path,
                    "already": True, "note": "Zaten çalışıyor."}

    if target.is_dir():
        # Desktop app: open the real .exe — the dotnet/ps1 wrapper may have
        # been started earlier with CREATE_NO_WINDOW.
        if gui is not None:
            try:
                import os
                os.startfile(str(gui))  # type: ignore[attr-defined]
            except Exception as exc:
                return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
            return {"ok": True, "run": gui.name, "path": rel_path, "pid": None,
                    "note": "Masaüstü uygulaması açıldı."}

        manifest = _manifest_data(target)
        run_cmd = str((manifest or {}).get("run") or "").strip()
        kind, entry, detected = _detect(target)
        run_cmd = run_cmd or detected
        entry_path = (target / entry).resolve() if entry else None

        # If the command is a simple "interpreter + file" we start the file
        # OURSELVES: the manifest `run` line is most of the time written for
        # a human ("py app.py  (127.0.0.1:5006)" with an annotation) and
        # blows up when handed to the shell. Toolchain commands like
        # `npm start`, `dotnet run` run from the shell — they have no script file.
        script = _script_of(run_cmd, target)
        if script is None and entry_path is not None and entry_path.is_file() \
                and entry_path.suffix.lower() in RUN:
            script = entry_path
        if script is not None:
            target = script
        elif run_cmd:
            try:
                proc = _spawn_command(run_cmd, target)
            except Exception as exc:
                return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
            _PROCS[proc.pid] = {"proc": proc, "path": rel_path, "name": target.name,
                                "started": time.time(), "run": run_cmd}
            return {"ok": True, "run": run_cmd, "path": rel_path, "pid": proc.pid}
        else:
            return {"ok": False,
                    "error": "Çalıştırma komutu bulunamadı: app.json'a "
                             "bir `run` satırı ekletebilirsin (Dornick'e sor). "
                             + MANIFEST_OGRETICI}

    if not target.is_file():
        return {"ok": False, "error": f"Dosya yok: {rel_path}"}

    try:
        proc = _spawn(target)
    except Exception as exc:  # a launch error must not bring the UI down
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    pid = getattr(proc, "pid", None)
    if proc is not None and pid is not None:
        _PROCS[pid] = {"proc": proc, "path": rel_path, "name": target.name,
                       "started": time.time()}
    return {"ok": True, "run": _run_line(target), "path": rel_path, "pid": pid}


def running(sandbox_root: Path | None = None,
            base: Path | None = None) -> list[dict[str, Any]]:
    """Apps still running and trackable — with their live addresses.

    Dead processes are pruned. The address (if a web server bound one) is
    found by matching PID → listened port via netstat; if the port is not
    bound yet it comes back empty and shows up on the next poll.

    Dornick's OWN processes drop from this list. When the model got
    confused and ran `dornick --web 8873` the panel listed a copy of
    Dornick as "your app"; what the user saw was a clone of their own
    program. Its own copy shows as a separate, NON-STOPPABLE row — hiding
    it would be wrong too, the user should know something is running there.
    """
    out: list[dict[str, Any]] = []
    dead: list[int] = []
    # The process tree, command lines and listened ports are gathered ONCE:
    # querying separately for each process would make the poll heavy.
    info_map = _proc_info()
    parents = {pid: v["ppid"] for pid, v in info_map.items()}
    listen = _listening_ports()
    for pid, info in list(_PROCS.items()):
        proc = info["proc"]
        if proc.poll() is not None:   # finished
            dead.append(pid)
            continue
        # The record's own text is the most reliable sign (the shell tool
        # writes the command as-is); the tree scan is the fallback.
        own = (is_dornick_process(str(info.get("path") or ""))
               or is_dornick_process(str(info.get("run") or ""))
               or _dornick_family(pid, info_map))
        out.append({
            "pid": pid,
            "path": info["path"],
            "name": "Dornick (kendisi)" if own else info["name"],
            "address": _address(pid, parents, listen),
            "started": info.get("started", 0),
            "run": info.get("run", ""),
            "self": own,
            "stoppable": not own,
        })
    for pid in dead:
        _PROCS.pop(pid, None)

    # Running servers NOT in the ledger but belonging to the workshop: when
    # dornick is restarted or the user ran the app by hand the process is
    # not in `_PROCS` — the panel said "nothing is running", yet the app
    # was serving on 8090. If the project port is really listened on, that
    # app counts as LIVE.
    if sandbox_root is not None:
        known = {row["pid"] for row in out}
        for row in _discovered_servers(sandbox_root, info_map, listen, base):
            if row["pid"] not in known:
                out.append(row)
                known.add(row["pid"])
    return out


def _discovered_servers(
    sandbox_root: Path,
    info_map: dict[int, dict[str, Any]],
    listen: dict[int, list[int]],
    base: Path | None = None,
) -> list[dict[str, Any]]:
    """Processes LISTENING on the ports the workshop projects declare.

    The proof is a socket: the project says "I live on 8090", a process is
    listening on 8090 and that process is not Dornick itself → the app is running.

    Paths are given relative to `base` (the panel matches against project
    paths); two paths produced against different roots would show the same
    app twice.
    """
    out: list[dict[str, Any]] = []
    try:
        items = katalog(sandbox_root, base, live=False)["projects"]
    except Exception:
        return out
    owner: dict[int, int] = {}     # port → pid
    for pid, ports in listen.items():
        for port in ports:
            owner.setdefault(port, pid)
    for p in items:
        port = int(p.get("port") or 0)
        pid = owner.get(port, 0)
        if not port or not pid or _dornick_family(pid, info_map):
            continue
        _DISCOVERED.add(pid)
        out.append({
            "pid": pid,
            "path": p.get("path", ""),
            "name": p.get("name", ""),
            "address": f"http://127.0.0.1:{port}",
            "started": 0,
            "run": p.get("run", ""),
            "self": False,
            "stoppable": True,
            "discovered": True,
        })
    return out


def _mark_live(items: list[Project], root: Path, ref: Path) -> None:
    """Stamps live state onto the projects: pid, address, stoppability.

    Two sources together: (1) the process ledger (`_PROCS`) — what Dornick
    itself started; (2) the declared port actually being listened on —
    even if dornick was restarted or the user ran the app by hand, what is
    running shows up.
    """
    tracked: dict[str, int] = {}
    for pid, info in _PROCS.items():
        if info["proc"].poll() is None:
            tracked[str(info.get("path") or "")] = pid
    declared = {p.port for p in items if p.port}
    if not items or (not tracked and not declared):
        return   # nothing to match: do not even open a process query
    try:
        listen = _listening_ports()
    except Exception:
        return
    owner: dict[int, int] = {}
    for pid, ports in listen.items():
        for port in ports:
            owner.setdefault(port, pid)
    if not tracked and not (declared & set(owner)):
        return   # none of the declared ports is being listened on

    info_map = _proc_info()
    parents = {pid: v["ppid"] for pid, v in info_map.items()}

    for p in items:
        pid = tracked.get(p.path) or (tracked.get(p.entry) if p.entry else 0) or 0
        if pid:
            p.pid = pid
            p.address = _address(pid, parents, listen)
            p.stoppable = not _dornick_family(pid, info_map)
        if p.port and not p.address:
            listener = owner.get(p.port, 0)
            if listener and not _dornick_family(listener, info_map):
                p.pid = p.pid or listener
                p.address = f"http://127.0.0.1:{p.port}"
                p.stoppable = True
                _DISCOVERED.add(listener)


# Dornick's own processes: anything with `dornick` on the command line. When
# the model started Dornick instead of its app (`dornick --web 8873`) the
# panel listed it as "your app" — the user was looking at a clone of their
# own program. This pattern recognises that copy.
# Careful (01.09, caught during the rename): `dornick` is now both the
# package AND the FOLDER name. If a bare path segment matched, every
# process under a shell opened from the project folder counted as "itself".
# The trace recognises only REAL launch signatures: `-m dornick`,
# `dornick.exe/.cmd`, or a bare `dornick` at the start of the command line.
_DORNICK_TRACE = re.compile(
    r"(-m\s+dornick(?=[\s\"']|$))"
    r"|((^|[\\/\s\"'])dornick\.(exe|cmd)(?=[\s\"']|$))"
    r"|(^\s*\"?dornick\"?(?=[\s\"']|$))",
    re.IGNORECASE)

# Processes discovered by port evidence (not in the ledger). Kept so that
# `stop()` can only stop a pid seen once: the panel cannot kill a random
# system process.
_DISCOVERED: set[int] = set()


def is_dornick_process(cmdline: str) -> bool:
    """Does this command line start Dornick itself? (also used from outside)"""
    return bool(_DORNICK_TRACE.search(cmdline or ""))


def _dornick_family(pid: int, info_map: dict[int, dict[str, Any]]) -> bool:
    """Is pid or one of its ANCESTORS dornick?

    Looking at the wrapper is not enough: in the chain
    `powershell -Command "dornick --web 8873"` the real dornick is the
    grandchild process. The chain is scanned upwards.
    """
    if pid == os.getpid():
        return True
    seen: set[int] = set()
    cur = pid
    while cur and cur not in seen:
        seen.add(cur)
        record = info_map.get(cur)
        if record is None:
            break
        if is_dornick_process(str(record.get("cmd") or "")):
            return True
        cur = int(record.get("ppid") or 0)
    # Is there a dornick among the descendants (wrapper pid in the ledger, dornick in its child)
    for child, record in info_map.items():
        if record.get("ppid") == pid and is_dornick_process(str(record.get("cmd") or "")):
            return True
    return False


def stop(pid: int) -> dict[str, Any]:
    """Stops a tracked process WITH ITS TREE.

    The recorded pid is most of the time a wrapper (the py launcher,
    PowerShell); `terminate()` killed only that one, the real server kept
    living as a grandchild process — the user lived "I say stop, it won't
    stop" (the twin of the tree issue in address resolution). On Windows
    taskkill /T brings the whole tree down."""
    info = _PROCS.get(pid)
    if info is None:
        # Not in the ledger but if discovered by PORT EVIDENCE it may be
        # stopped: when dornick was restarted the apps became "unstoppable".
        # To avoid killing a random system process only pids seen once by
        # `running()` are accepted.
        if pid not in _DISCOVERED:
            return {"ok": False, "error": "Bu süreç izlenmiyor ya da zaten bitmiş."}
        if _dornick_family(pid, _proc_info()):
            return {"ok": False, "error": "Bu Dornick'in kendi süreci — panelden durdurulmuyor."}
        try:
            if sys.platform == "win32":
                subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                               capture_output=True, timeout=10,
                               **environment.quiet_flags())
            else:
                os.kill(pid, 15)
        except Exception as exc:
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        _DISCOVERED.discard(pid)
        return {"ok": True, "pid": pid}
    # The ledger record's own text suffices (no need to query the process
    # tree): the shell tool writes the command as-is, `dornick --web 8873`
    # shows there.
    if is_dornick_process(str(info.get("path") or "")) or is_dornick_process(str(info.get("run") or "")):
        return {"ok": False, "error": "Bu Dornick'in kendi süreci — panelden durdurulmuyor."}
    try:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                           capture_output=True, timeout=10,
                           **environment.quiet_flags())
        else:
            info["proc"].terminate()
        # Did it really die? Saying "stopped" and leaving it running is the
        # very "I say stop, it won't stop" complaint. Verified with a short
        # wait; if still alive an honest error is returned.
        try:
            info["proc"].wait(timeout=3)
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "Süreç durdurulamadı — hâlâ çalışıyor. "
                                          "Tekrar dene ya da Dornick'e söyle."}
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    _PROCS.pop(pid, None)
    return {"ok": True, "pid": pid}


def open_path(sandbox_root: Path, rel_path: str, base: Path | None = None) -> dict[str, Any]:
    """Opens a file/page in the workshop OUTSIDE the system (default app).

    For a web page this means the user's real browser: a self-contained
    page (needing no server) opens from the file as `file://` and works
    fully. The address of an app needing a server is already opened from
    the Running section/the capsule — this path is for statics.
    """
    allowed = _openable(sandbox_root, rel_path, base)
    if isinstance(allowed, dict):
        return allowed
    target = allowed
    # Only what is the browser's business: throwing a .docx at Word under
    # "open in browser" sets a wrong expectation — if those files are
    # wanted in their own app there is `sistemde_ac`.
    if target.suffix.lower() not in {".html", ".htm", ".svg"}:
        return {"ok": False, "error": "Bu bir web sayfası değil; tarayıcıda açılmaz."}
    try:
        os.startfile(str(target))  # type: ignore[attr-defined]
    except Exception as exc:
        return {"ok": False, "error": f"Açılamadı: {type(exc).__name__}: {exc}"}
    return {"ok": True, "opened": str(target)}


# Openable area: the workshop + the project folder the user CONNECTED.
#
# The old state was the workshop only, and when the agent wrote a report
# into a connected folder the "Show in folder"/"Open" buttons refused with
# "Outside the workshop" — the user could not reach the file they produced
# (live wound, 02.09). The user picks the project folder themselves; that
# is their area too.
def _izinli_kokler(sandbox_root: Path, base: Path | None = None) -> list[Path]:
    roots = [sandbox_root.resolve()]
    if base is not None:
        try:
            roots.append(base.resolve())
        except OSError:
            pass
    return roots


def _openable(sandbox_root: Path, rel_path: str,
              base: Path | None = None) -> Any:
    """Resolves the target and checks whether it is allowed. Returns a Path or an error dict."""
    roots = _izinli_kokler(sandbox_root, base)
    ref = (base or sandbox_root).resolve()
    try:
        target = (ref / rel_path).resolve() if rel_path else ref
    except OSError:
        return {"ok": False, "error": f"Yol çözümlenemedi: {rel_path}"}
    if not any(target == k or k in target.parents for k in roots):
        return {"ok": False,
                "error": "Çalışma alanı dışı: yalnızca atölyedeki ya da "
                         "bağlı klasördeki dosyalar açılır."}
    if not target.exists():
        return {"ok": False, "error": f"Yok: {rel_path}"}
    return target


def sistemde_ac(sandbox_root: Path, rel_path: str,
                base: Path | None = None) -> dict[str, Any]:
    """Opens the file in the operating system's DEFAULT app.

    PDF, docx, xlsx, png… — the endpoint behind the "open" button for every
    file the agent produced. `open_path` opened only web pages; telling a
    user who wants to read a report "this is not a web page" was no answer
    (live wound, 02.09).
    """
    allowed = _openable(sandbox_root, rel_path, base)
    if isinstance(allowed, dict):
        return allowed
    target = allowed
    try:
        if sys.platform == "win32":
            os.startfile(str(target))  # type: ignore[attr-defined]
        else:  # pragma: no cover - non-Windows path
            subprocess.Popen(["xdg-open", str(target)])
    except Exception as exc:
        return {"ok": False, "error": f"Açılamadı: {type(exc).__name__}: {exc}"}
    return {"ok": True, "opened": str(target)}


def reveal(sandbox_root: Path, rel_path: str, base: Path | None = None) -> dict[str, Any]:
    """Opens the app's folder in the file explorer.

    "Where is this thing?" is the panel's most asked question: the card
    prints a path but the user browsed by hand to find it on disk. If a
    file is given its folder opens (file selected).
    """
    root = sandbox_root.resolve()
    allowed = _openable(sandbox_root, rel_path, base)
    if isinstance(allowed, dict):
        return allowed
    target = allowed
    try:
        if sys.platform == "win32":
            if target.is_dir():
                os.startfile(str(target))  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["explorer", "/select,", str(target)])
        else:
            subprocess.Popen(["xdg-open", str(target if target.is_dir() else target.parent)])
    except Exception as exc:
        return {"ok": False, "error": f"Açılamadı: {type(exc).__name__}: {exc}"}
    return {"ok": True, "shown": _rel(target, root)}


def remove(sandbox_root: Path, rel_path: str, base: Path | None = None) -> dict[str, Any]:
    """Removes a project from the workshop — not deleted permanently, moved to the recycle bin.

    The user must be able to delete from the panel; but permanently
    destroying a project with one click is dangerous. The project is moved
    under `atolye/.geri-donusum/<time>-<name>`: it drops from the list
    (dot-prefixed folders are skipped anyway), but something deleted by
    mistake can be restored by hand.
    """
    import shutil
    import time as _time

    root = sandbox_root.resolve()
    ref = (base or root).resolve()
    target = (ref / rel_path).resolve()
    if target == root or root not in target.parents:
        return {"ok": False, "error": "Atölye dışı: yalnızca atölyedekiler silinir."}
    if not target.exists():
        return {"ok": False, "error": f"Yok: {rel_path}"}

    bin_dir = root / ".geri-donusum"
    try:
        bin_dir.mkdir(exist_ok=True)
        stamp = _time.strftime("%Y%m%d-%H%M%S")
        dest = bin_dir / f"{stamp}-{target.name}"
        shutil.move(str(target), str(dest))
    except Exception as exc:
        # A running process may have locked the file — say so explicitly.
        return {"ok": False, "error": f"Taşınamadı ({type(exc).__name__}): önce durdurmayı dene."}
    return {"ok": True, "moved_to": str(dest.relative_to(root))}


def _address(
    pid: int,
    parents: dict[int, int] | None = None,
    listen: dict[int, list[int]] | None = None,
) -> str:
    """The local address the process (or its DESCENDANTS) listens on. Empty if none.

    Why descendants: the process we start is most of the time a wrapper —
    PowerShell (`shell` background), the `py` launcher, `npm`/`cmd`. The
    real listening socket belongs to a child/grandchild process. Looking
    only for the exact pid (the old state) found the address in NONE of
    these cases; that is why the capsule stayed empty too. Now the smallest
    LISTENING port among pid + all its descendants is picked.
    """
    if parents is None:
        parents = _proc_parents()
    if listen is None:
        listen = _listening_ports()
    family = _descendants(pid, parents)
    best: int | None = None
    for owner, ports in listen.items():
        if owner not in family:
            continue
        for port in ports:
            best = port if best is None else min(best, port)
    return f"http://localhost:{best}" if best else ""


def _proc_parents() -> dict[int, int]:
    """pid → ppid map. For finding descendants in the process tree."""
    return {pid: v["ppid"] for pid, v in _proc_info().items()}


def _proc_info() -> dict[int, dict[str, Any]]:
    """pid → {ppid, cmd}. The process tree AND the command lines in a single query.

    The command line is needed because only it tells Dornick's own copy
    (`dornick --web ...`) apart from the user's app. Opening one more
    separate query would double the 4-second poll; adding a field to the
    same query is close to free.

    Separator `|`: CSV was breaking on the commas in command lines.
    """
    out: dict[int, dict[str, Any]] = {}
    try:
        if sys.platform == "win32":
            res = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "Get-CimInstance Win32_Process | ForEach-Object { "
                 "\"$($_.ProcessId)|$($_.ParentProcessId)|"
                 "$($_.CommandLine -replace '[\\r\\n\\|]',' ')\" }"],
                # errors="replace": command lines can contain bytes the
                # console code page cannot decode (not a crash, a broken
                # character is acceptable — the `dornick` trace we look for
                # is ASCII anyway).
                capture_output=True, text=True, errors="replace", timeout=8,
                **environment.quiet_flags(),
            )
            for line in res.stdout.splitlines():
                parts = line.split("|", 2)
                if len(parts) >= 2 and parts[0].strip().isdigit() \
                        and parts[1].strip().isdigit():
                    out[int(parts[0])] = {
                        "ppid": int(parts[1]),
                        "cmd": parts[2].strip() if len(parts) > 2 else "",
                    }
        else:
            for entry in os.listdir("/proc"):
                if not entry.isdigit():
                    continue
                try:
                    with open(f"/proc/{entry}/stat") as fh:
                        fields = fh.read().split()
                    try:
                        with open(f"/proc/{entry}/cmdline", "rb") as ch:
                            cmd = ch.read().replace(b"\0", b" ").decode(
                                "utf-8", "replace").strip()
                    except OSError:
                        cmd = ""
                    out[int(entry)] = {"ppid": int(fields[3]), "cmd": cmd}
                except Exception:
                    continue
    except Exception:
        pass
    return out


def _descendants(pid: int, parents: dict[int, int]) -> set[int]:
    """pid and all its descendants."""
    family = {pid}
    changed = True
    while changed:
        changed = False
        for child, parent in parents.items():
            if parent in family and child not in family:
                family.add(child)
                changed = True
    return family


def _listening_ports() -> dict[int, list[int]]:
    """pid → LISTENING ports (netstat once)."""
    out: dict[int, list[int]] = {}
    try:
        proc = subprocess.run(
            ["netstat", "-ano", "-p", "TCP"] if sys.platform == "win32"
            else ["netstat", "-tlnp"],
            capture_output=True, text=True, errors="replace", timeout=3,
            **environment.quiet_flags(),
        )
    except Exception:
        return out
    for line in proc.stdout.splitlines():
        parts = line.split()
        if sys.platform == "win32":
            # Proto  Local  Foreign  State  PID
            if len(parts) < 5 or parts[3].upper() != "LISTENING":
                continue
            owner, local = parts[-1], parts[1]
        else:
            # Proto Recv Send Local Foreign State PID/Program
            if "LISTEN" not in line or "/" not in parts[-1]:
                continue
            owner, local = parts[-1].split("/", 1)[0], (parts[3] if len(parts) > 3 else "")
        port = local.rsplit(":", 1)[-1]
        if owner.isdigit() and port.isdigit():
            out.setdefault(int(owner), []).append(int(port))
    return out


def _spawn(target: Path):
    suffix = target.suffix.lower()
    cwd = str(target.parent)

    if suffix in (".bat", ".cmd", ".exe") or (suffix == "" and sys.platform == "win32"):
        # A self-running file: start directly. No handle, so it cannot be
        # tracked (state/stop do not apply to these).
        import os
        os.startfile(str(target))  # type: ignore[attr-defined]
        return None

    if suffix == ".ps1":
        cmd = ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(target)]
    elif suffix == ".sh":
        cmd = ["bash", str(target)]
    elif suffix in (".js", ".mjs", ".cjs"):
        cmd = [_runtime("node"), str(target)]
    elif suffix == ".php":
        cmd = [_runtime("php"), str(target)]
    elif suffix == ".rb":
        cmd = [_runtime("ruby"), str(target)]
    elif suffix == ".jar":
        cmd = [_runtime("java"), "-jar", str(target)]
    elif suffix == ".pyw":
        cmd = [_python(windowless=True), str(target)]
    else:  # .py and the rest
        cmd = [_python(), str(target)]

    # New console: the script's output shows in its own window and does not
    # mix with the UI's process. GUI/windowed tools do not open a console anyway.
    flags = 0
    if sys.platform == "win32":
        flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
    return subprocess.Popen(cmd, cwd=cwd, creationflags=flags)


# Interpreters that do exactly the same job as launching the file directly.
# For a command on this list we start the script file ourselves; the shell
# (and the possible annotation residue on the command line) is taken out of the loop.
_SIMPLE_RUNNERS = {"py", "python", "python3", "pythonw", "powershell", "pwsh",
                   "bash", "sh", "node", "php", "ruby"}


def _script_of(run_cmd: str, folder: Path) -> Path | None:
    """If the command is a simple "interpreter + script", gives the script's path.

    "py app.py  (127.0.0.1:5006)" → app.py. "npm start" → None (toolchain,
    must run from the shell). "python -m http.server" → None (no file).
    """
    tokens = run_cmd.split()
    if not tokens or tokens[0].lower() not in _SIMPLE_RUNNERS:
        return None
    for token in tokens[1:]:
        candidate = folder / token
        try:
            if candidate.is_file() and candidate.suffix.lower() in RUN:
                return candidate.resolve()
        except OSError:
            continue
    return None


def _spawn_command(command: str, cwd: Path) -> "subprocess.Popen":
    """Starts a run COMMAND (npm start, dotnet run) in the project folder.

    Goes through the shell because the commands set up a toolchain
    (npm → node); even though the wrapper's pid lands in the process
    ledger, address resolution and stopping already look at the process TREE.
    """
    if sys.platform == "win32":
        import shutil as _shutil
        exe = _shutil.which("pwsh") or _shutil.which("powershell") or "powershell.exe"
        cmd = [exe, "-NoProfile", "-Command", command]
        flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
    else:
        cmd = ["/bin/sh", "-lc", command]
        flags = 0
    return subprocess.Popen(cmd, cwd=str(cwd), creationflags=flags)


def _runtime(name: str) -> str:
    """Finds the runtime; if missing raises an error saying WHAT TO INSTALL."""
    import shutil as _shutil

    found = _shutil.which(name)
    if not found:
        raise FileNotFoundError(
            f"'{name}' bu makinede kurulu değil ya da PATH'te yok. "
            f"Kurulumu Dornick'ten isteyebilirsin."
        )
    return found


def _python(windowless: bool = False) -> str:
    runner = Path(sys.executable)
    if windowless:
        quiet = runner.with_name("pythonw.exe")
        if quiet.exists():
            return str(quiet)
    return str(runner)


# -- helpers ------------------------------------------------------------


def _rel(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root).as_posix()
    except (ValueError, OSError):
        return path.name


def _head(path: Path, limit: int) -> str:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            return fh.read(limit)
    except OSError:
        return ""


def _clean(text: str) -> str:
    flat = " ".join((text or "").split())
    return flat if len(flat) <= 120 else flat[:120] + "…"


def to_dict(app: App) -> dict[str, Any]:
    """The shape going to the API. Empty fields go too; the UI checks presence."""
    return asdict(app)
