"""Sıralama.

Gömme vektörü yok — sözcük örtüşmesi + nadirlik ağırlığı + tazelik. Küçük
kişisel bir bellek için bu şaşırtıcı derecede iyi çalışır ve hiçbir bağımlılık
getirmez. Bellek binlerce kayda çıktığında burası gömme tabanlı bir indeksle
değiştirilir; arayüz aynı kalır.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Sequence

_WORD = re.compile(r"\w+", re.UNICODE)

# Sorguyu daraltmayan çok sık Türkçe/İngilizce sözcükler.
STOPWORDS = frozenset(
    """
    ve veya ile için gibi kadar daha çok az bir bu şu o ne nasıl neden
    da de ki mi mı mu mü ben sen biz siz onlar var yok olan olarak
    the a an and or of to in on for with is are was were be been it this that
    """.split()
)


# Ön ek eşleşmesinin devreye girmesi için gereken en kısa sözcük.
MIN_STEM = 4


def tokenize(text: str) -> list[str]:
    return [
        t for t in (m.group(0).casefold() for m in _WORD.finditer(text or "")) if t not in STOPWORDS
    ]


def matches(term: str, vocabulary: set[str]) -> list[str]:
    """Bir sorgu terimiyle eşleşen belge terimleri.

    Türkçe sondan eklemeli: "rapor" sorgusu "raporları", "raporu", "raporlar"
    ile eşleşmeli. Tam sözcük karşılaştırması bu dilde aramanın yarısını
    kaybettirir. Gövdeleyici yerine ön ek eşleşmesi kullanıyoruz — kaba ama
    bağımlılıksız ve ekleme yönü tek olduğu için şaşırtıcı derecede isabetli.

    Yanlış pozitifleri sınırlamak için iki taraf da en az MIN_STEM uzunlukta
    olmalı; kısa sözcükler yalnızca birebir eşleşir.
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
) -> list[Scored]:
    """Sorguya göre sıralar. Sorgu boşsa en yeniler döner.

    Skor = terim örtüşmesi × ters belge sıklığı × tazelik.
    Nadirlik ağırlığı olmadan "dosya" gibi her yerde geçen bir sözcük
    sonuçları ele geçirirdi.
    """
    if not items:
        return []

    docs = [tokenize(text_of(item)) for item in items]
    vocabularies = [set(d) for d in docs]

    if not (terms := set(tokenize(query))):
        scored = [Scored(item, _freshness(item, time_of, half_life_days), []) for item in items]
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
            # Terim sıklığını doyur: aynı sözcüğün 50 kez geçmesi 5 kez
            # geçmesinden 10 kat daha alakalı değil.
            occurrences = sum(doc.count(f) for f in found)
            raw += idf[term] * (1 + math.log(occurrences))

        if not hit_terms:
            continue

        coverage = hit_terms / len(terms)
        score = raw * (0.5 + 0.5 * coverage) * _freshness(item, time_of, half_life_days)
        out.append(Scored(item, score, sorted(surface)))

    return sorted(out, key=lambda s: -s.score)[:limit]


def _idf(vocabularies: list[set[str]], terms: Iterable[str]) -> dict[str, float]:
    total = len(vocabularies) or 1
    return {
        term: math.log(1 + total / (1 + sum(1 for v in vocabularies if matches(term, v))))
        for term in terms
    }


def _freshness(item: Any, time_of, half_life_days: float) -> float:
    """0.5 ile 1.0 arası çarpan. Tazelik alakayı ezmemeli, sadece eğmeli."""
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
    age_days = max(0.0, (datetime.now(timezone.utc) - when).total_seconds() / 86_400)
    return 0.5 + 0.5 * math.pow(0.5, age_days / half_life_days)


def excerpt(text: str, matched: Sequence[str], width: int = 220) -> str:
    """Eşleşen terimin etrafından okunabilir bir pencere keser."""
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
