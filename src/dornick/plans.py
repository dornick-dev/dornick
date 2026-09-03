"""Large work plans — a Cursor/Claude style approval gate.

The agent does not paste a wall of text into the chat; it produces a
structured Plan. The user Approves / Edits / Cancels. Store:
`{state_dir}/plans/<id>.json`
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .events import utcnow

FOLDER = "plans"
_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,48}$")
STATUSES = ("bekliyor", "onaylandi", "yapiliyor", "bitti", "iptal")


class PlanError(Exception):
    pass


@dataclass(slots=True)
class Plan:
    id: str
    title: str
    status: str = "bekliyor"
    steps: list[dict[str, Any]] = field(default_factory=list)
    created: str = ""
    updated: str = ""


def folder(state_dir: Path) -> Path:
    return Path(state_dir) / FOLDER


def to_dict(plan: Plan) -> dict[str, Any]:
    return asdict(plan)


def create(
    state_dir: Path,
    *,
    title: str,
    steps: list[Any] | None = None,
) -> Plan:
    rid = f"plan-{uuid.uuid4().hex[:8]}"
    now = utcnow()
    normalized = []
    for i, s in enumerate(steps or []):
        if isinstance(s, dict):
            normalized.append({
                "id": str(s.get("id") or f"s{i+1}"),
                "text": str(s.get("text") or s.get("title") or ""),
                "status": str(s.get("status") or "bekliyor"),
            })
        else:
            normalized.append({"id": f"s{i+1}", "text": str(s), "status": "bekliyor"})
    plan = Plan(id=rid, title=title.strip() or "Plan", status="bekliyor",
                steps=normalized, created=now, updated=now)
    _write(state_dir, plan)
    return plan


def update(
    state_dir: Path,
    plan_id: str,
    *,
    status: str | None = None,
    steps: list[Any] | None = None,
    title: str | None = None,
) -> Plan | None:
    plan = get(state_dir, plan_id)
    if plan is None:
        return None
    if status is not None:
        st = str(status).strip()
        if st not in STATUSES:
            raise PlanError(f"status: {', '.join(STATUSES)}")
        plan.status = st
    if title is not None:
        plan.title = str(title).strip() or plan.title
    if steps is not None:
        plan.steps = []
        for i, s in enumerate(steps):
            if isinstance(s, dict):
                plan.steps.append({
                    "id": str(s.get("id") or f"s{i+1}"),
                    "text": str(s.get("text") or ""),
                    "status": str(s.get("status") or "bekliyor"),
                })
            else:
                plan.steps.append({"id": f"s{i+1}", "text": str(s), "status": "bekliyor"})
    plan.updated = utcnow()
    _write(state_dir, plan)
    return plan


def get(state_dir: Path, plan_id: str) -> Plan | None:
    path = folder(state_dir) / f"{plan_id}.json"
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return Plan(
        id=str(raw.get("id") or plan_id),
        title=str(raw.get("title") or "Plan"),
        status=str(raw.get("status") or "bekliyor"),
        steps=list(raw.get("steps") or []),
        created=str(raw.get("created") or ""),
        updated=str(raw.get("updated") or ""),
    )


def listing(state_dir: Path, limit: int = 30) -> list[dict[str, Any]]:
    root = folder(state_dir)
    if not root.is_dir():
        return []
    rows = []
    for path in sorted(root.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        plan = get(state_dir, path.stem)
        if plan:
            rows.append(to_dict(plan))
        if len(rows) >= limit:
            break
    return rows


def _write(state_dir: Path, plan: Plan) -> None:
    root = folder(state_dir)
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{plan.id}.json"
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(to_dict(plan), ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
    temp.replace(path)
