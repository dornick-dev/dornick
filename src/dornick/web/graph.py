"""Zihni gezinilebilir bir grafa çevirir.

Merkezde ajan, etrafında kategoriler, onların ucunda tek tek kayıtlar.
İki seviyeli olmasının sebebi okunabilirlik: yüzlerce hatırayı doğrudan
merkeze bağlamak yıldız değil, yumak üretir.

Bu modül saf: Mind okur, sözlük döndürür. Sunucu ve arayüzden bağımsız
test edilebilir.
"""

from __future__ import annotations

from typing import Any

from ..mind.store import MEMORY_KINDS, Mind

# Kategori başlıkları ve çizim sırası. Sıra sabit olmalı, yoksa graf her
# yenilemede yeniden diziliyormuş gibi görünür.
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

    # "Konuşmaya git" ancak kaynak oturum DOSYASI hâlâ duruyorsa vaat
    # edilebilir: taşınmış/birleştirilmiş anıların oturumları çoğu zaman
    # bu makinede yok ve düğme sessizce ölüyordu (canlıda görüldü).
    def _kaynak_var(session_id: str) -> bool:
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

    # Hatiralar arasi gercek cagrisim baglari. Merkez-yaprak kenarlarindan
    # ayri isaretleniyor: arayuz agi bunlarla oruyor, hiyerarsiyle degil.
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


# "Konuşmaya git" ancak kaynak oturum DOSYASI hâlâ duruyorsa vaat
# edilebilir: taşınmış/birleştirilmiş anıların oturumları çoğu zaman bu
# makinede yok ve düğme sessizce ölüyordu (canlıda görüldü).
def _kaynak_var(mind: Mind, session_id: str) -> bool:
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
                # "Nasıl öğrendim": hangi konuşmada, ne zaman. Arayüz çift
                # tıkla kaynağa gidiyor — kimlik olmadan gidilemezdi.
                "kaynak": memory.session_id,
                "kaynak_var": _kaynak_var(mind, memory.session_id),
                "ts": memory.ts,
            }
            for memory in mind.memories(kind)
        ]

    buckets["goal"] = [
        {"id": goal.id, "label": _clip(goal.text), "detail": goal.text,
         "meta": goal.status, "kaynak": goal.session_id,
         "kaynak_var": _kaynak_var(mind, goal.session_id), "ts": goal.ts}
        # Beyin grafiği zihnin tamamına bakar: hedefler artık oturuma
        # süzülü geldiğinden burada bilerek hepsi isteniyor.
        for goal in mind.goals(all_sessions=True)
    ]

    buckets["session"] = [
        {
            "id": hit.item.session_id,
            # Ham damga ("20260823T173004Z") ekranda hiçbir şey söylemiyor
            # ve grafta yan yana duran beş tanesi okunmuyor.
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
    """Oturum kimliğini okunur bir tarihe çevirir.

    Kimlik `20260823T173004Z` biçiminde; çözülemezse olduğu gibi kalıyor —
    elle kopyalanmış bir oturum dosyası başka bir ad taşıyor olabilir.
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
