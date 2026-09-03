"""Workflow store.

An automation is not just a prompt text: it is a graph of nodes and
edges. The store lives under `.dornick/workflows/<id>.json`; the
settings page and the agent read and write the same files.

Node types are not a closed enum (`mail_read`, `http`, `skill`,
`shell`, `agent`, `custom`, …): adding a new node type does not
require breaking the store schema — the runner rejects types it
does not know.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .events import utcnow

FOLDER = "workflows"

# The id becomes the file name; no path separators or spaces allowed.
_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,48}$")


class WorkflowError(Exception):
    """Format error. The message is shown to the model and the user."""


@dataclass(slots=True)
class WorkflowNode:
    """A single step in the graph.

    type: open string — the runner itself knows which types it understands.
    config: free-form object specific to the type.
    secrets_needed: names of the secret keys this step requires.
    skill: skill name for the `skill` type; may stay empty for the rest.
    position: editor position ({"x": …, "y": …}); the runner does not care.
    """

    id: str
    title: str = ""
    type: str = "custom"
    config: dict[str, Any] = field(default_factory=dict)
    secrets_needed: list[str] = field(default_factory=list)
    skill: str = ""
    position: dict[str, Any] = field(default_factory=dict)
    # Did the user edit this step BY HAND? Self-repair checks this:
    # the model rewriting a step the user deliberately wrote would not be
    # a "fix" but a silent revert. (`elle` is a persisted JSON key.)
    elle: bool = False


@dataclass(slots=True)
class WorkflowEdge:
    """A transition between two nodes.

    `from_` is written as `from` in JSON — `from` is a Python keyword.
    on: under which condition (e.g. "ok", "hata", ""); empty = always.
    """

    from_: str
    to: str
    on: str = ""


@dataclass(slots=True)
class Workflow:
    id: str
    title: str
    nodes: list[WorkflowNode] = field(default_factory=list)
    edges: list[WorkflowEdge] = field(default_factory=list)
    updated: str = ""


def folder(state_dir: Path) -> Path:
    return Path(state_dir) / FOLDER


def new_id(state_dir: Path, title: str = "") -> str:
    """Short, collision-free id: optional slug + 8 hex chars."""
    from . import canvas

    slug = canvas.slug(title, fallback="wf")[:24].strip("-") or "wf"
    root = folder(state_dir)
    for _ in range(8):
        candidate = f"{slug}-{uuid.uuid4().hex[:8]}"
        if not _ID.match(candidate):
            candidate = f"wf-{uuid.uuid4().hex[:8]}"
        if not (root / f"{candidate}.json").exists():
            return candidate
    raise WorkflowError("Kimlik üretilemedi — workflows klasörünü denetle.")


def _path(state_dir: Path, workflow_id: str) -> Path:
    ident = str(workflow_id or "").strip().lower()
    if not _ID.match(ident):
        raise WorkflowError(f"Geçersiz workflow kimliği: {workflow_id!r}")
    root = folder(state_dir).resolve()
    target = (root / f"{ident}.json").resolve()
    if target.parent != root:
        raise WorkflowError(f"Geçersiz workflow kimliği: {workflow_id!r}")
    return target


# -- format ------------------------------------------------------------


def _parse_node(raw: Any, index: int) -> WorkflowNode:
    if not isinstance(raw, dict):
        raise WorkflowError(f"nodes[{index}] bir nesne olmalı.")
    nid = str(raw.get("id") or "").strip()
    if not nid:
        raise WorkflowError(f"nodes[{index}].id boş olamaz.")
    config = raw.get("config") if isinstance(raw.get("config"), dict) else {}
    position = raw.get("position") if isinstance(raw.get("position"), dict) else {}
    secrets = raw.get("secrets_needed") or []
    if not isinstance(secrets, list):
        raise WorkflowError(f"nodes[{index}].secrets_needed bir liste olmalı.")
    return WorkflowNode(
        id=nid,
        title=str(raw.get("title") or "").strip(),
        type=str(raw.get("type") or "custom").strip() or "custom",
        config=dict(config),
        secrets_needed=[str(s).strip() for s in secrets if str(s).strip()],
        skill=str(raw.get("skill") or "").strip(),
        position=dict(position),
        elle=bool(raw.get("elle")),
    )


def _parse_edge(raw: Any, index: int) -> WorkflowEdge:
    if not isinstance(raw, dict):
        raise WorkflowError(f"edges[{index}] bir nesne olmalı.")
    # JSON uses `from`; `from_` from the old / Python side is accepted too.
    src = str(raw.get("from") if "from" in raw else raw.get("from_") or "").strip()
    dst = str(raw.get("to") or "").strip()
    if not src or not dst:
        raise WorkflowError(f"edges[{index}] from ve to zorunlu.")
    return WorkflowEdge(from_=src, to=dst, on=str(raw.get("on") or "").strip())


def parse(raw: Any) -> Workflow:
    """Workflow from a dict. Basic structure: nodes and edges lists."""
    if not isinstance(raw, dict):
        raise WorkflowError("Workflow bir nesne olmalı.")

    ident = str(raw.get("id") or "").strip().lower()
    if not _ID.match(ident):
        raise WorkflowError(
            "id küçük harf, rakam, tire ve alt çizgiden oluşmalı "
            f"(verilen: {raw.get('id')!r})."
        )

    title = str(raw.get("title") or "").strip()
    if not title:
        raise WorkflowError("title boş olamaz.")

    nodes_raw = raw.get("nodes")
    edges_raw = raw.get("edges")
    if not isinstance(nodes_raw, list):
        raise WorkflowError("nodes bir liste olmalı.")
    if not isinstance(edges_raw, list):
        raise WorkflowError("edges bir liste olmalı.")

    nodes = [_parse_node(item, i) for i, item in enumerate(nodes_raw, start=1)]
    edges = [_parse_edge(item, i) for i, item in enumerate(edges_raw, start=1)]

    return Workflow(
        id=ident,
        title=title,
        nodes=nodes,
        edges=edges,
        updated=str(raw.get("updated") or ""),
    )


def to_dict(wf: Workflow) -> dict[str, Any]:
    """Disk / API format: the edge carries a `from` key."""
    return {
        "id": wf.id,
        "title": wf.title,
        "nodes": [asdict(n) for n in wf.nodes],
        "edges": [{"from": e.from_, "to": e.to, "on": e.on} for e in wf.edges],
        "updated": wf.updated,
    }


def validate(raw: Any) -> Workflow:
    """Basic structural validation — the same gate as parse."""
    return parse(raw)


# -- store -------------------------------------------------------------


def list_all(state_dir: Path) -> list[Workflow]:
    """All workflows in the folder. A broken file does not sink the list."""
    root = folder(state_dir)
    if not root.is_dir():
        return []

    found: list[Workflow] = []
    for path in sorted(root.glob("*.json")):
        try:
            found.append(parse(json.loads(path.read_text(encoding="utf-8"))))
        except (WorkflowError, json.JSONDecodeError, OSError, TypeError):
            continue
    return found


def get(state_dir: Path, workflow_id: str) -> Workflow | None:
    try:
        path = _path(state_dir, workflow_id)
    except WorkflowError:
        return None
    if not path.is_file():
        return None
    try:
        return parse(json.loads(path.read_text(encoding="utf-8")))
    except (WorkflowError, json.JSONDecodeError, OSError, TypeError):
        return None


def save(state_dir: Path, raw: Any) -> Workflow:
    """Writes the workflow. Updates an existing one, creates it otherwise."""
    data = dict(raw) if isinstance(raw, dict) else raw
    if isinstance(data, dict) and not str(data.get("id") or "").strip():
        data = {**data, "id": new_id(state_dir, str(data.get("title") or ""))}
    wf = parse(data)
    wf.updated = utcnow()
    path = _path(state_dir, wf.id)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(to_dict(wf), ensure_ascii=False, indent=2) + "\n"
    temp = path.with_suffix(".tmp")
    temp.write_text(payload, encoding="utf-8")
    temp.replace(path)
    return wf


def remove(state_dir: Path, workflow_id: str) -> bool:
    try:
        path = _path(state_dir, workflow_id)
    except WorkflowError:
        return False
    if not path.is_file():
        return False
    path.unlink()
    return True
