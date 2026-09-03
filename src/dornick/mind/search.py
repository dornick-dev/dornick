"""Ranking.

No embedding vectors — word overlap + rarity weight + freshness. For a small
personal memory this works surprisingly well and brings in no dependency.
When the memory grows to thousands of records this gets replaced with an
embedding-based index; the interface stays the same.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Sequence

_WORD = re.compile(r"\w+", re.UNICODE)

# Very frequent Turkish/English words that do not narrow the query.
STOPWORDS = frozenset(
    """
    ve veya ile için gibi kadar daha çok az bir bu şu o ne nasıl neden
    da de ki mi mı mu mü ben sen biz siz onlar var yok olan olarak
    the a an and or of to in on for with is are was were be been it this that
    """.split()
)


# The shortest word for which prefix matching kicks in.
MIN_STEM = 4


def tokenize(text: str) -> list[str]:
    return [
        t for t in (m.group(0).casefold() for m in _WORD.finditer(text or "")) if t not in STOPWORDS
    ]


def matches(term: str, vocabulary: set[str]) -> list[str]:
    """Document terms matching a query term.

    Turkish is agglutinative: the query "rapor" must match "raporları",
    "raporu", "raporlar". Exact word comparison loses half of search in this
    language. We use prefix matching instead of a stemmer — crude, but
    dependency-free and, since suffixing goes in a single direction,
    surprisingly accurate.

    To limit false positives both sides must be at least MIN_STEM long;
    short words only match exactly.
    """
    if term in vocabulary:
        return [term]
    if len(term) < MIN_STEM:
        return []
    return [
        other
        for other in vocabulary
        if len(other) >= MIN_STEM and (other.startswith(term) or term.startswith(other))
    ]


@dataclass(slots=True)
class Scored:
    item: Any
    score: float
    matched: list[str]


def rank(
    query: str,
    items: Sequence[Any],
    *,
    text_of,
    time_of=None,
    limit: int = 10,
    half_life_days: float = 30.0,
    now: datetime | None = None,
) -> list[Scored]:
    """Ranks by the query. If the query is empty the newest come back.

    Score = term overlap × inverse document frequency × freshness.
    Without the rarity weight a word that occurs everywhere, like "dosya",
    would take over the results.
    """
    if not items:
        return []

    # The clock is injected so a virtual-calendar benchmark does not read the
    # real date; the product passes nothing and gets wall time. (The freshness
    # tilt below used datetime.now() directly, which quietly made episode
    # ranking depend on when the process ran — invisible to the store's own
    # datetime.now guard, which only covers store.py.)
    now = now or datetime.now(timezone.utc)

    docs = [tokenize(text_of(item)) for item in items]
    vocabularies = [set(d) for d in docs]

    if not (terms := set(tokenize(query))):
        scored = [Scored(item, _freshness(item, time_of, half_life_days, now), [])
                  for item in items]
        return sorted(scored, key=lambda s: -s.score)[:limit]

    idf = _idf(vocabularies, terms)
    out: list[Scored] = []

    for item, doc, vocabulary in zip(items, docs, vocabularies):
        if not doc:
            continue

        raw = 0.0
        hit_terms = 0
        surface: set[str] = set()

        for term in terms:
            if not (found := matches(term, vocabulary)):
                continue
            hit_terms += 1
            surface.update(found)
            # Saturate term frequency: the same word occurring 50 times is
            # not 10 times more relevant than occurring 5 times.
            occurrences = sum(doc.count(f) for f in found)
            raw += idf[term] * (1 + math.log(occurrences))

        if not hit_terms:
            continue

        coverage = hit_terms / len(terms)
        score = raw * (0.5 + 0.5 * coverage) * _freshness(
            item, time_of, half_life_days, now)
        out.append(Scored(item, score, sorted(surface)))

    return sorted(out, key=lambda s: -s.score)[:limit]


def _idf(vocabularies: list[set[str]], terms: Iterable[str]) -> dict[str, float]:
    total = len(vocabularies) or 1
    return {
        term: math.log(1 + total / (1 + sum(1 for v in vocabularies if matches(term, v))))
        for term in terms
    }


def _freshness(item: Any, time_of, half_life_days: float,
               now: datetime) -> float:
    """A multiplier between 0.5 and 1.0. Freshness must not crush relevance, only tilt it."""
    if time_of is None:
        return 1.0
    stamp = time_of(item)
    if not stamp:
        return 0.75
    try:
        when = datetime.fromisoformat(stamp)
    except (TypeError, ValueError):
        return 0.75
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    age_days = max(0.0, (now - when).total_seconds() / 86_400)
    return 0.5 + 0.5 * math.pow(0.5, age_days / half_life_days)


def excerpt(text: str, matched: Sequence[str], width: int = 220) -> str:
    """Cuts a readable window around the matched term."""
    flat = " ".join((text or "").split())
    if len(flat) <= width:
        return flat
    lowered = flat.casefold()
    position = next(
        (lowered.find(t) for t in matched if lowered.find(t) != -1),
        -1,
    )
    if position == -1:
        return flat[:width] + "…"
    start = max(0, position - width // 3)
    window = flat[start : start + width]
    return ("…" if start else "") + window + ("…" if start + width < len(flat) else "")
