"""The trace automations leave in memory.

Two things are written, both in the same shape:

    procedure  What a workflow does, when it is created/updated
               (`kind="procedure"`). The aim is to remember months later
               "I did this in an automation before" and look there — use it
               if it works, write a new one if it does not.
    lesson     What happened when a step failed (`kind="lesson"`).

Why the shape MATTERS: these records are not only for association, they are
also the input of the personal fine-tuning that runs at night. Writing the
same event with the same pattern every time lets the model see the pattern;
if free text is written differently every time there is no pattern left to
learn.

If there is no memory or the write blows up it is silently skipped: the
automation itself matters more than being remembered.
"""

from __future__ import annotations

from typing import Any

from .workflows import Workflow

# Tags in one place: these are the key to finding things again.
TAG = "otomasyon"
LESSON_TAG = "otomasyon-ders"

# Maximum number of steps carried in the record — dumping a fifty-node graph
# into memory as is drowns association in its own noise.
MAX_STEPS = 12


def _summary(wf: Workflow) -> str:
    steps = []
    for node in wf.nodes[:MAX_STEPS]:
        name = (node.title or node.id).strip()
        steps.append(f"{node.type}: {name}")
    if len(wf.nodes) > MAX_STEPS:
        steps.append(f"… ve {len(wf.nodes) - MAX_STEPS} adım daha")
    return " → ".join(steps) if steps else "(adım yok)"


def workflow_text(wf: Workflow) -> str:
    """A workflow's shape as written to memory. The pattern is fixed."""
    lines = [
        f"Otomasyon [{wf.id}] «{wf.title or wf.id}» — {len(wf.nodes)} adım.",
        f"Adımlar: {_summary(wf)}",
    ]
    secrets = sorted({s for n in wf.nodes for s in n.secrets_needed if s})
    if secrets:
        lines.append(f"Gerektirdiği gizli alanlar: {', '.join(secrets)}")
    skills = sorted({n.skill for n in wf.nodes if n.skill})
    if skills:
        lines.append(f"Kullandığı yetenekler: {', '.join(skills)}")
    return "\n".join(lines)


def lesson_text(wf_id: str, node: Any, exc: BaseException) -> str:
    """A step failure's shape as written to memory. The pattern is fixed."""
    name = (getattr(node, "title", "") or getattr(node, "id", "")).strip()
    return (
        f"Otomasyon [{wf_id}] adımı hata verdi — {getattr(node, 'type', '?')}: «{name}». "
        f"Hata: {type(exc).__name__}: {exc}"
    )


def akisi_hatirla(mind: Any, wf: Workflow) -> bool:
    """Write the workflow as a procedure. True if written."""
    if mind is None or not hasattr(mind, "remember"):
        return False
    try:
        mind.remember(
            workflow_text(wf),
            kind="procedure",
            title=f"otomasyon:{wf.id}",
            tags=(TAG, f"{TAG}:{wf.id}"),
        )
        return True
    except Exception:
        return False


def recall_lesson(mind: Any, wf_id: str, node: Any, exc: BaseException) -> bool:
    """Write the step failure as a lesson. True if written."""
    if mind is None or not hasattr(mind, "remember"):
        return False
    try:
        mind.remember(
            lesson_text(wf_id, node, exc),
            kind="lesson",
            title=f"otomasyon-hata:{wf_id}:{getattr(node, 'id', '?')}",
            tags=(LESSON_TAG, f"{TAG}:{wf_id}"),
        )
        return True
    except Exception:
        return False


def search_workflows(mind: Any, query: str, *, limit: int = 5) -> list[Any]:
    """Have we done this job in an automation before?

    Finding nothing is normal and silent: a "none" answer is better than a
    made-up match. The caller is NOT OBLIGED to USE what it finds — if it
    does not work, writing a new one is the right thing.
    """
    if mind is None or not hasattr(mind, "recall"):
        return []
    try:
        found = mind.recall(query, limit=limit * 3) or []
    except Exception:
        return []
    result = []
    for m in found:
        # `recall` returns a scored wrapper (`Scored.item`); both are accepted
        # so a caller that returns the memory directly stays supported too.
        record = getattr(m, "item", m)
        tags = set(getattr(record, "tags", ()) or ())
        title = str(getattr(record, "title", ""))
        if TAG in tags or title.startswith("otomasyon:"):
            result.append(record)
        if len(result) >= limit:
            break
    return result
