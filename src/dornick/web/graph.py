"""Turns the mind into a navigable graph.

The agent sits at the centre, categories around it, individual records at
their tips. It is two levels deep for readability: wiring hundreds of
memories straight to the centre produces a tangle, not a star.

This module is pure: it reads a Mind and returns a dict. It can be tested
independently of the server and the UI.
"""

from __future__ import annotations

from typing import Any

from ..mind.store import MEMORY_KINDS, Mind

# Category titles and drawing order. The order must be fixed, otherwise the
# graph looks as if it re-arranges itself on every refresh.
HUBS: tuple[tuple[str, str], ...] = (
    ("user", "kullanıcı"),
    ("preference", "tercihler"),
    ("lesson", "dersler"),
    ("procedure", "yordamlar"),
    ("fact", "bilgiler"),
    ("goal", "hedefler"),
    ("session", "geçmiş oturumlar"),
)

LABEL_CHARS = 34
MAX_PER_HUB = 24


def build_graph(mind: Mind, *, episode_limit: int = 8) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = [
        {"id": "self", "label": "dornick", "group": "self", "size": 26, "detail": ""}
    ]

    # "Go to the conversation" can only be promised if the source session
    # FILE is still around: the sessions of migrated/merged memories are
    # usually not on this machine and the button died silently (seen live).
    def _source_exists(session_id: str) -> bool:
        if not session_id:
            return False
        try:
            return (mind.sessions_dir / f"{session_id}.jsonl").is_file()
        except OSError:
            return False
    edges: list[dict[str, str]] = []

    buckets = _buckets(mind, episode_limit)

    for group, title in HUBS:
        items = buckets.get(group, [])
        if not items:
            continue

        hub_id = f"hub:{group}"
        nodes.append(
            {
                "id": hub_id,
                "label": f"{title} ({len(items)})",
                "group": group,
                "size": 15,
                "detail": "",
                "hub": True,
            }
        )
        edges.append({"source": "self", "target": hub_id})

        for item in items[:MAX_PER_HUB]:
            nodes.append({**item, "group": group, "size": 8})
            edges.append({"source": hub_id, "target": item["id"]})

    # Real association links between memories. Marked separately from the
    # hub-leaf edges: the UI weaves its net with these, not with the hierarchy.
    known = {n["id"] for n in nodes}
    synapses = [
        {"source": src, "target": dst, "weight": weight, "synapse": True}
        for src, dst, weight in _links(mind)
        if src in known and dst in known
    ]

    return {
        "nodes": nodes,
        "edges": edges + synapses,
        "stats": _stats(mind, buckets),
    }


# "Go to the conversation" can only be promised if the source session FILE
# is still around: the sessions of migrated/merged memories are usually not
# on this machine and the button died silently (seen live).
def _source_exists(mind: Mind, session_id: str) -> bool:
    if not session_id:
        return False
    try:
        return (mind.sessions_dir / f"{session_id}.jsonl").is_file()
    except (OSError, AttributeError, TypeError):
        return False


def _links(mind: Mind) -> list[tuple[str, str, float]]:
    getter = getattr(mind, "links", None)
    return getter() if callable(getter) else []


def _buckets(mind: Mind, episode_limit: int) -> dict[str, list[dict[str, Any]]]:
    buckets: dict[str, list[dict[str, Any]]] = {}

    for kind in MEMORY_KINDS:
        buckets[kind] = [
            {
                "id": memory.id,
                "label": _clip(memory.title or memory.content),
                "detail": memory.content,
                "meta": ", ".join(memory.tags),
                # "How I learned it": in which conversation, when. The UI
                # double-click goes to the source — impossible without the id.
                "kaynak": memory.session_id,
                "kaynak_var": _source_exists(mind, memory.session_id),
                "ts": memory.ts,
            }
            for memory in mind.memories(kind)
        ]

    buckets["goal"] = [
        {"id": goal.id, "label": _clip(goal.text), "detail": goal.text,
         "meta": goal.status, "kaynak": goal.session_id,
         "kaynak_var": _source_exists(mind, goal.session_id), "ts": goal.ts}
        # The brain graph looks at the whole mind: since goals now arrive
        # filtered by session, all of them are deliberately requested here.
        for goal in mind.goals(all_sessions=True)
    ]

    buckets["session"] = [
        {
            "id": hit.item.session_id,
            # The raw stamp ("20260823T173004Z") says nothing on screen and
            # five of them side by side in the graph are unreadable.
            "label": _when(hit.item.session_id),
            "detail": _clip(hit.item.digest, 400),
            "meta": f"{hit.item.turns} tur"
            + (f" · {', '.join(hit.item.tools)}" if hit.item.tools else ""),
        }
        for hit in mind.episodes("", limit=episode_limit, include_current=True)
    ]

    return buckets


def _stats(mind: Mind, buckets: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    soul = mind.soul()
    return {
        "sessions": soul.sessions,
        "first_seen": soul.first_seen,
        "memories": sum(len(buckets.get(kind, [])) for kind in MEMORY_KINDS),
        "goals": len(buckets.get("goal", [])),
    }


def _when(session_id: str) -> str:
    """Turns a session id into a readable date.

    The id is shaped like `20260823T173004Z`; if it cannot be parsed it is
    left as is — a hand-copied session file may carry another name.
    """
    from datetime import datetime

    try:
        when = datetime.strptime(session_id[:15], "%Y%m%dT%H%M%S")
    except (ValueError, IndexError):
        return _clip(session_id)
    return when.strftime("%d.%m %H:%M")


def _clip(text: str, limit: int = LABEL_CHARS) -> str:
    flat = " ".join((text or "").split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"
