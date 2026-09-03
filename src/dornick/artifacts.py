"""Artifact store: persistent, addressable, updatable pages.

A chat message flows away; the real deliverable the agent produces
(report, dashboard, visualization) must not be lost in the stream.
Artifacts exist for this: the HTML is published once, gets a short
readable id and lives at the same address forever — `/artifact/<id>/`.
Later turns write a new version to the same id; the address does not
change, old versions are kept for a while.

The store is not in the workshop but under `.dornick/artifacts/`: this
is not the agent's working file, it is a surface the program serves
(the same neighbourhood as session and mind records). The workshop
boundary binds the file tools; writing here goes through this module's
own paths and no path is built without the id passing a strict pattern —
a `../` coming from a request never touches the disk.
"""

from __future__ import annotations

import json
import re
import shutil
import uuid
from pathlib import Path
from typing import Any

from . import canvas
from .events import utcnow

# The store folder under state_dir.
FOLDER = "artifacts"

# The subfolder holding old versions and how many are kept. Hoarding
# without limit turns the disk into a dump; five versions are enough for
# "take me back to a moment ago". (`surumler` is a persisted dir name.)
VERSIONS = "surumler"
KEEP_VERSIONS = 5

# Where a deleted artifact is moved: no permanent delete, recoverable by hand.
TRASH = ".geri-donusum"

# Id pattern: title slug + 4 hex. No path is built without passing this
# pattern; dots, separators and spaces never get in — directory traversal
# starts right here.
ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,79}$")


class ArtifactError(Exception):
    """Store error. The tool layer turns this into an instructive error."""


def folder(state_dir: Path) -> Path:
    return Path(state_dir) / FOLDER


def new_id(state_dir: Path, title: str) -> str:
    """Short, readable, collision-free id: title-slug-4hex.

    A slug alone is not enough: "Günlük rapor" gets published every day
    and the second one would silently crush the first. The 4-hex suffix
    ends collisions in practice; if one still happens, it is redrawn.
    """
    slug = canvas.slug(title, fallback="artifact")[:40].strip("-") or "artifact"
    for _ in range(8):
        candidate = f"{slug}-{uuid.uuid4().hex[:4]}"
        if not (folder(state_dir) / candidate).exists():
            return candidate
    raise ArtifactError("Kimlik üretilemedi — depo klasörünü denetle.")


def _dir(state_dir: Path, artifact_id: str) -> Path:
    """Validates the id and returns its folder. Pattern + resolution
    together: the pattern already cuts `..` and separators, resolution is
    the second lock against symlinks."""
    if not ID_PATTERN.match(artifact_id or ""):
        raise ArtifactError(f"Geçersiz artifact kimliği: {artifact_id!r}")
    root = folder(state_dir).resolve()
    target = (root / artifact_id).resolve()
    if target.parent != root:
        raise ArtifactError(f"Geçersiz artifact kimliği: {artifact_id!r}")
    return target


def page_path(state_dir: Path, artifact_id: str) -> Path | None:
    """The page to serve; None if the id is broken or the page is missing.

    The server serves through this: the path is built here, not from the
    request, so an escape attempt is weeded out without touching the disk.
    """
    try:
        page = _dir(state_dir, artifact_id) / "index.html"
    except ArtifactError:
        return None
    return page if page.is_file() else None


def read_meta(state_dir: Path, artifact_id: str) -> dict[str, Any]:
    path = _dir(state_dir, artifact_id) / "meta.json"
    try:
        meta = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ArtifactError(f"Artifact bulunamadı: {artifact_id}") from exc
    if not isinstance(meta, dict):
        raise ArtifactError(f"Artifact kaydı bozuk: {artifact_id}")
    return meta


def _write_meta(target: Path, meta: dict[str, Any]) -> None:
    (target / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def publish(state_dir: Path, title: str, html: str) -> dict[str, Any]:
    """Publishes a new artifact; returns the meta record."""
    title = (title or "").strip()
    if not title:
        raise ArtifactError("`title` boş — artifact'ın bir adı olmalı.")
    if not (html or "").strip():
        raise ArtifactError("`html` boş — yayınlanacak bir sayfa yok.")

    artifact_id = new_id(state_dir, title)
    target = _dir(state_dir, artifact_id)
    target.mkdir(parents=True, exist_ok=True)
    (target / "index.html").write_text(html, encoding="utf-8")

    now = utcnow()
    meta = {"id": artifact_id, "title": title, "created": now,
            "updated": now, "surum": 1}
    _write_meta(target, meta)
    return meta


def update(state_dir: Path, artifact_id: str, html: str,
           title: str | None = None) -> dict[str, Any]:
    """Writes a new version to the same id; the address does not change.

    The old page is kept as `surumler/<n>.html` (last KEEP_VERSIONS);
    a wrong update must not lose the previous state.
    """
    if not (html or "").strip():
        raise ArtifactError("`html` boş — güncellenecek bir sayfa yok.")
    target = _dir(state_dir, artifact_id)
    meta = read_meta(state_dir, artifact_id)

    page = target / "index.html"
    if page.is_file():
        versions = target / VERSIONS
        versions.mkdir(exist_ok=True)
        shutil.copy2(page, versions / f"{meta.get('surum', 1)}.html")
        _prune_versions(versions)

    page.write_text(html, encoding="utf-8")
    meta["surum"] = int(meta.get("surum", 1)) + 1
    meta["updated"] = utcnow()
    if title and title.strip():
        meta["title"] = title.strip()
    _write_meta(target, meta)
    return meta


def _prune_versions(versions: Path) -> None:
    kept = sorted(
        (p for p in versions.glob("*.html") if p.stem.isdigit()),
        key=lambda p: int(p.stem),
    )
    for stale in kept[:-KEEP_VERSIONS]:
        stale.unlink(missing_ok=True)


def listing(state_dir: Path) -> list[dict[str, Any]]:
    """The artifacts in the store, most recently updated first.

    A broken record (a folder whose meta was deleted) does not sink the
    list — it is skipped silently; the trash folder is invisible too.
    """
    root = folder(state_dir)
    rows: list[dict[str, Any]] = []
    try:
        children = list(root.iterdir())
    except OSError:
        return rows
    for child in children:
        if not child.is_dir() or child.name.startswith("."):
            continue
        try:
            meta = read_meta(state_dir, child.name)
        except ArtifactError:
            continue
        rows.append(meta)
    rows.sort(key=lambda m: str(m.get("updated", "")), reverse=True)
    return rows


def remove(state_dir: Path, artifact_id: str) -> dict[str, Any]:
    """Moves the artifact to the trash — no permanent delete, recoverable by hand."""
    target = _dir(state_dir, artifact_id)
    if not target.is_dir():
        raise ArtifactError(f"Artifact bulunamadı: {artifact_id}")
    trash = folder(state_dir) / TRASH
    trash.mkdir(parents=True, exist_ok=True)
    stamp = utcnow().replace(":", "").replace(".", "")
    moved = trash / f"{artifact_id}-{stamp}"
    shutil.move(str(target), str(moved))
    return {"ok": True, "id": artifact_id, "moved": str(moved)}


def address(artifact_id: str) -> str:
    """The page's address in the UI. Keep it in one place: the tool, the
    server and the UI must all state the same path."""
    return f"/artifact/{artifact_id}/"
