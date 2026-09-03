"""Portability: moving what Dornick accumulated on one machine somewhere else.

As dornick lives on a computer it accumulates memories, weaves links, holds
goals, writes itself skills. All of that is on disk — but it must not be
chained to one machine. This module puts all of it into a single portable
package (`.neobundle`, a plain zip) and **merges** it into another Dornick.

The principle is merge, not overwrite: a memory with the same id does not
enter twice (idempotent), only new ones are added. So what two machines
learned can be gathered into one Dornick — without one wiping the other.
The soul (persona) is preserved: if the target Dornick has an identity the
incoming package does not crush it; it fills it only when empty.

Package contents (by part — see PARTS):
    manifest.json     version, date, counts, selected parts
    recall.db         memories + links (with their signatures) — consistent copy
    goals.jsonl       goals (if any)
    persona.md        soul text (if any)
    projects.json     session→project mapping (if any)
    skills/<...>      the skills folder
    tanima/<...>      personal model (taban.npz) + the training rig's personal
                      files (corpus + watermark, if any)
    projeler/<...>    the workshop itself (produced projects/files)
    ayarlar/<...>     config.json — WITHOUT KEYS (see below)

KEYS NEVER ENTER THE PACKAGE: keys.json is in no part, and the field
pointing at a key (api_key_env) is dropped from config.json in the settings
part too — the importing side re-derives it from the provider. The package
is a file that may pass from hand to hand; it must carry no secret.

Session logs (raw conversations) are OUTSIDE: they are not "what was
learned", they are the raw record; large and private. If wanted it would
be a separate export job.
"""

from __future__ import annotations

import io
import json
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from . import skills as skills_mod
from . import recognition as recognition_mod

BUNDLE_VERSION = 1

# Selectable parts. "anilar" is the whole of the old package (memories,
# links, goals, soul, session→project mapping, skills) — backwards
# compatibility: a request without parts produces exactly the old package.
PARTS = ("anilar", "tanima", "projeler", "ayarlar")

# Fixed names inside the zip.
_MANIFEST = "manifest.json"
_DB = "recall.db"
_GOALS = "goals.jsonl"
_PERSONA = "persona.md"
_PROJECTS = "projects.json"
_SKILLS = "skills/"
_RECOGNITION = "tanima/"
_PROJECTS_DIR = "projeler/"
_SETTINGS = "ayarlar/"

# Directories skipped in the workshop scan: tool residue, version control,
# the recycle bin (same reasoning as SKIPPED in server.py / gate._ATLA).
# .dornick is on the list too: change snapshots (.dornick/degisiklikler) and
# other session residue must not enter the package — even if the workshop
# root one day collides with state.
_ATLA = frozenset({".git", "__pycache__", "node_modules", ".venv",
                   ".mypy_cache", ".geri-donusum", ".dornick"})


def export_bundle(config: Any, mind: Any,
                  parts: Sequence[str] | None = None) -> bytes:
    """Puts the selected parts into a single zip and returns its bytes.

    If `parts` is not given, the old behaviour: only "anilar" (the whole of
    the old package). Unknown names are dropped silently — a broken request
    should produce a package with what it knows, not an empty one.
    """
    chosen = [p for p in (parts or ("anilar",)) if p in PARTS] or ["anilar"]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        counts = {"memories": 0, "links": 0, "goals": 0, "skills": 0}

        if "anilar" in chosen:
            # Memory: a consistent copy (WAL included), via a temp file.
            with tempfile.TemporaryDirectory() as tmp:
                db_copy = Path(tmp) / _DB
                mind.store.backup_to(db_copy)
                zf.write(db_copy, _DB)
            counts["memories"] = _safe_count(lambda: mind.store.count())
            counts["links"] = _safe_count(lambda: len(mind.store.links()))

            # Goals.
            goals = config.mind_dir / "goals.jsonl"
            if goals.is_file():
                data = goals.read_text(encoding="utf-8")
                zf.writestr(_GOALS, data)
                counts["goals"] = sum(1 for ln in data.splitlines() if ln.strip())

            # Soul (persona).
            persona = _persona_path(config)
            if persona and persona.is_file():
                zf.writestr(_PERSONA, persona.read_text(encoding="utf-8"))

            # Projects (session→project).
            projects = config.sessions_dir / "_projects.json"
            if projects.is_file():
                zf.writestr(_PROJECTS, projects.read_text(encoding="utf-8"))

            # Skills.
            skills_dir = _skills_dir(config)
            if skills_dir and skills_dir.is_dir():
                for path in sorted(skills_dir.rglob("*")):
                    if path.is_file() and not _is_noise(path):
                        rel = path.relative_to(skills_dir).as_posix()
                        zf.writestr(_SKILLS + rel, path.read_bytes())
                        counts["skills"] += 1

        if "tanima" in chosen:
            counts["tanima"] = _export_recognition(config, zf)

        if "projeler" in chosen:
            counts["projeler"] = _export_projects(config, zf)

        if "ayarlar" in chosen:
            counts["ayarlar"] = _export_settings(config, zf)

        manifest = {
            "kind": "neobundle",
            "version": BUNDLE_VERSION,
            "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "counts": counts,
            "parcalar": chosen,
        }
        zf.writestr(_MANIFEST, json.dumps(manifest, ensure_ascii=False, indent=2))

    return buf.getvalue()


def _export_recognition(config: Any, zf: zipfile.ZipFile) -> int:
    """Personal model + the training rig's personal files (if any).

    All "if any": on a machine that has never trained the part stays
    quietly empty — not an error, just nothing to carry.
    """
    written = 0
    sources = [
        (Path(config.state_dir) / "taban.npz", "taban.npz"),
        (recognition_mod.CORPUS, "kisisel_korpus.jsonl"),
        (recognition_mod.WATERMARK, "kisisel_durum.json"),
    ]
    for source, name in sources:
        if source.is_file():
            zf.write(source, _RECOGNITION + name)
            written += 1
    return written


def _export_projects(config: Any, zf: zipfile.ZipFile) -> int:
    """The workshop itself: the projects and files Dornick produced."""
    try:
        root = Path(config.open_sandbox().root)
    except Exception:
        return 0
    written = 0
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if any(part in _ATLA for part in rel.parts):
            continue
        try:
            zf.write(path, _PROJECTS_DIR + rel.as_posix())
        except OSError:
            continue  # a file locked/deleted at that moment must not bring the package down
        written += 1
    return written


def _export_settings(config: Any, zf: zipfile.ZipFile) -> int:
    """config.json — without keys.

    keys.json is in NO part; the field pointing at a key
    (model.api_key_env) is dropped from config too. The importing side
    re-derives it from base_url — the environment variable name is not a
    secret, but even the word "key" has no business inside the package.
    """
    path = Path(config.state_dir) / "config.json"
    if not path.is_file():
        return 0
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 0
    if isinstance(data.get("model"), dict):
        data["model"].pop("api_key_env", None)
    zf.writestr(_SETTINGS + "config.json",
                json.dumps(data, ensure_ascii=False, indent=2))
    return 1


def import_bundle(config: Any, mind: Any, data: bytes,
                  parts: Sequence[str] | None = None) -> dict[str, Any]:
    """Merges a package into this Dornick. Memories join, they are not
    overwritten; file parts (tanima/projeler/ayarlar) move the existing
    state under .dornick/yedek-<date>/ before overwriting.

    If `parts` is given, only the requested ones are processed even when
    the package has more — selective restore from a single archive. The
    returned summary is shown in the UI.
    """
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        return {"ok": False, "error": "Geçersiz paket: zip açılamadı."}

    names = set(zf.namelist())
    if _MANIFEST not in names:
        return {"ok": False, "error": "Bu bir dornick paketi değil (manifest yok)."}

    try:
        manifest = json.loads(zf.read(_MANIFEST))
    except (json.JSONDecodeError, KeyError):
        manifest = {}
    if manifest.get("kind") != "neobundle":
        return {"ok": False, "error": "Tanınmayan paket türü."}
    # Old packages have no notion of parts: the memory file is mandatory. A
    # selective package (the manifest carries "parcalar") may be valid
    # without memory.
    if "parcalar" not in manifest and _DB not in names:
        return {"ok": False, "error": "Bu bir dornick paketi değil (bellek yok)."}

    wanted = set(p for p in (parts or PARTS) if p in PARTS)
    summary: dict[str, Any] = {"ok": True, "memories": 0, "links": 0,
                               "goals": 0, "skills": 0, "persona": False}
    # The backup folder is lazy: if nothing is going to be overwritten not
    # even an empty yedek-<date> folder should be opened.
    backup: list[Path] = []

    if "anilar" in wanted:
        if _DB in names:
            # Memory merge: write to a temp file and fold it into the store.
            with tempfile.TemporaryDirectory() as tmp:
                db_in = Path(tmp) / _DB
                db_in.write_bytes(zf.read(_DB))
                merged = mind.store.merge_from(db_in)
                summary["memories"] = merged.get("nodes", 0)
                summary["links"] = merged.get("links", 0)

        # Goals: add the new ones by id.
        if _GOALS in names:
            summary["goals"] = _merge_goals(config, mind, zf.read(_GOALS).decode("utf-8"))

        # Soul: fill only if the target is empty — the incoming package must not crush the identity.
        if _PERSONA in names:
            summary["persona"] = _maybe_persona(config, zf.read(_PERSONA).decode("utf-8"))

        # Projects (session→project mapping): joins, existing assignments are kept.
        if _PROJECTS in names:
            _merge_projects(config, zf.read(_PROJECTS).decode("utf-8"))

        # Skills: copy the files, do not crush existing ones.
        summary["skills"] = _merge_skills(config, zf, names)

    if "tanima" in wanted:
        summary["tanima"] = _import_recognition(config, zf, names, backup)

    if "projeler" in wanted:
        summary["projeler"] = _import_projects(config, zf, names, backup)

    if "ayarlar" in wanted:
        summary["ayarlar"] = _import_settings(config, zf, names, backup)

    if backup:
        summary["yedek"] = str(backup[0])
    return summary


# -- file parts: restore with backup ----------------------------------------


def backup_folder(state_dir: Path) -> Path:
    """Timestamped backup folder — reset and import use the same name."""
    return Path(state_dir) / f"yedek-{datetime.now().strftime('%Y%m%d-%H%M%S')}"


def _back_up(target: Path, state_dir: Path, backup: list[Path], label: str) -> None:
    """Copies the current state of a file about to be overwritten into the backup folder."""
    if not target.is_file():
        return
    if not backup:
        backup.append(backup_folder(state_dir))
    copy = backup[0] / label / target.name
    copy.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(target, copy)


def _import_recognition(config: Any, zf: zipfile.ZipFile, names: set[str],
                   backup: list[Path]) -> int:
    """Puts back the personal model + personal training files.

    taban.npz always lands in .Dornick (that is where the product reads it)
    and the base cache is dropped so it kicks in without waiting for the
    5-minute refresh. Corpus/watermark go into place if the training rig is
    installed, otherwise under .dornick/tanima_yedek/ — so they are not
    lost on a machine without the rig.
    """
    state_dir = Path(config.state_dir)
    rig_present = recognition_mod.CORPUS.parent.is_dir()
    written = 0
    targets = {
        "taban.npz": state_dir / "taban.npz",
        "kisisel_korpus.jsonl": (recognition_mod.CORPUS if rig_present
                                 else state_dir / "tanima_yedek" / "kisisel_korpus.jsonl"),
        "kisisel_durum.json": (recognition_mod.WATERMARK if rig_present
                               else state_dir / "tanima_yedek" / "kisisel_durum.json"),
    }
    for name, target in targets.items():
        if _RECOGNITION + name not in names:
            continue
        _back_up(target, state_dir, backup, "tanima")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(zf.read(_RECOGNITION + name))
        written += 1
    if written:
        # The incoming personal model should speak right away; the old one's cache drops.
        from .recall import writer
        writer.reset()
    return written


def _import_projects(config: Any, zf: zipfile.ZipFile, names: set[str],
                     backup: list[Path]) -> int:
    """Puts back the workshop files; the overwritten one's current state goes to the backup first."""
    try:
        root = Path(config.open_sandbox().root).resolve()
    except Exception:
        return 0
    written = 0
    for name in sorted(names):
        if not name.startswith(_PROJECTS_DIR) or name.endswith("/"):
            continue
        rel = name[len(_PROJECTS_DIR):]
        if not rel:
            continue
        target = (root / rel).resolve()
        # Escape-outside-the-folder (zip-slip) protection.
        if root not in target.parents and target != root:
            continue
        _back_up(target, Path(config.state_dir), backup, "projeler")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(zf.read(name))
        written += 1
    return written


def _import_settings(config: Any, zf: zipfile.ZipFile, names: set[str],
                    backup: list[Path]) -> int:
    """Puts back config.json (takes effect on restart).

    Keys are not touched: keys.json is outside the package and is not
    handled here at all either. The api_key_env dropped on export is
    re-derived from base_url — otherwise the provider would be left keyless.
    """
    name = _SETTINGS + "config.json"
    if name not in names:
        return 0
    try:
        data = json.loads(zf.read(name).decode("utf-8"))
    except (ValueError, KeyError):
        return 0
    model = data.get("model")
    if isinstance(model, dict) and not model.get("api_key_env"):
        env = _key_variable(str(model.get("base_url") or ""))
        if env:
            model["api_key_env"] = env
    target = Path(config.state_dir) / "config.json"
    _back_up(target, Path(config.state_dir), backup, "ayarlar")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                      encoding="utf-8")
    return 1


def _key_variable(base_url: str) -> str:
    """Derives the key's environment variable name from base_url (the settings list)."""
    from . import settings
    for entry in settings.PROVIDERS:
        if entry.get("env") and entry.get("base_url") and entry["base_url"] in base_url:
            return str(entry["env"])
    return ""


# -- reset -----------------------------------------------------------------


def reset_memories(config: Any, mind: Any) -> dict[str, Any]:
    """Resets memories and links; takes a consistent backup first.

    Memories only: goals, soul, session logs and skills stay in place —
    "forget me" is one thing, "forget who you are" another. The backup is
    .dornick/yedek-<date>/anilar/recall.db — the way back stays open.
    """
    backup = backup_folder(config.state_dir)
    try:
        mind.store.backup_to(backup / "anilar" / "recall.db")
    except Exception as exc:
        # No deletion without a backup: if the backup cannot be taken there is no reset either.
        return {"ok": False, "error": f"Yedek alınamadı: {exc}"}
    deleted = mind.store.reset()
    return {"ok": True, "silinen": deleted, "yedek": str(backup)}


# -- merge helpers -----------------------------------------------------------


def _merge_goals(config: Any, mind: Any, text: str) -> int:
    """Joins incoming goals by id; existing ones are kept."""
    path = config.mind_dir / "goals.jsonl"
    existing_ids = set()
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    existing_ids.add(json.loads(line).get("id"))
                except json.JSONDecodeError:
                    continue
    added = 0
    lines = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if record.get("id") in existing_ids:
            continue
        lines.append(json.dumps(record, ensure_ascii=False))
        existing_ids.add(record.get("id"))
        added += 1
    if lines:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            for line in lines:
                fh.write(line + "\n")
        # The live mind should see it too (without a restart).
        _reload_goals(mind, path)
    return added


def _reload_goals(mind: Any, path: Path) -> None:
    try:
        from .mind.store import Goal, _load
        _load(path, Goal, mind._goals)
    except Exception:
        pass  # the file is written; at worst it shows up on the next start


def _maybe_persona(config: Any, text: str) -> bool:
    """Fills the target's soul if it has none. If it has one, leaves it alone — the identity is not crushed."""
    path = _persona_path(config)
    if path is None:
        path = Path(config.workspace) / "persona.md"
    if path.is_file() and path.read_text(encoding="utf-8").strip():
        return False
    if not text.strip():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return True


def _merge_projects(config: Any, text: str) -> None:
    path = config.sessions_dir / "_projects.json"
    current: dict[str, str] = {}
    if path.is_file():
        try:
            current = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            current = {}
    try:
        incoming = json.loads(text)
    except json.JSONDecodeError:
        return
    if not isinstance(incoming, dict):
        return
    # Existing assignments are kept; only the missing ones come in.
    for sid, name in incoming.items():
        current.setdefault(str(sid), str(name))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")


def _merge_skills(config: Any, zf: zipfile.ZipFile, names: set[str]) -> int:
    skills_dir = _skills_dir(config)
    if skills_dir is None:
        return 0
    added = 0
    for name in names:
        if not name.startswith(_SKILLS) or name.endswith("/"):
            continue
        rel = name[len(_SKILLS):]
        if not rel:
            continue
        dest = (skills_dir / rel).resolve()
        # Escape-outside-the-folder (zip-slip) protection.
        if skills_dir.resolve() not in dest.parents and dest != skills_dir.resolve():
            continue
        if dest.exists():
            continue  # do not crush an existing skill
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(zf.read(name))
        added += 1
    return added


# -- path helpers ------------------------------------------------------------


def _persona_path(config: Any) -> Path | None:
    path = getattr(config, "persona_path", None)
    return Path(path) if path else None


def _skills_dir(config: Any) -> Path | None:
    try:
        root = config.open_sandbox().root
    except Exception:
        return None
    return Path(root) / skills_mod.FOLDER


def _is_noise(path: Path) -> bool:
    return "__pycache__" in path.parts or path.suffix in (".pyc", ".pyo")


def _safe_count(fn) -> int:
    try:
        return int(fn())
    except Exception:
        return 0
