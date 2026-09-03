"""Synonym bridge — meaning expansion on the query side.

The measured wall of lexical recall: if the query and the record share no
word/n-gram at all (bitcoin↔BTC, etiket↔tag), neither FTS nor the signature
can bridge the gap. Embeddings are deliberately absent (the no-install,
no-GPU principle); instead, a small, hand-maintainable mapping: the synonyms
of a word in the query are added to the query as extra terms. The record
side is untouched — what was written stays as written, the bridge opens only
while searching.

The table was compiled from GENERAL categories (crypto abbreviations,
industry terms, IT's everyday English↔Turkish vocabulary, common Turkish
synonyms) — not by looking at the eval queries; writing the table against
the eval makes the measurement meaningless (the ARASTIRMA.md cheating rule).
Honesty note: the author knew the failure CLASSES (abbreviation/translation
pairs); the pairs were still chosen category-wide, and the misses the class
does not cover (non-synonyms such as iş↔mühendis) were deliberately left
out.

The expansion is measured: at most a few extra terms per word, content words
only, suffixed forms are caught by prefix ("etiketleri" → etiket).
"""

from __future__ import annotations

import re

# Synonym groups. Every word in a group calls the others in the group. Kept
# short on purpose: an aggressive table (loose chains like
# "fiyat/bedel/ücret/para") wakes unrelated records and increases trap
# leakage.
GROUPS: tuple[tuple[str, ...], ...] = (
    # crypto / finance abbreviations
    ("btc", "bitcoin"),
    ("eth", "ethereum"),
    ("usdt", "tether"),
    ("borsa", "exchange"),
    ("cüzdan", "wallet"),
    ("portföy", "portfolio"),
    ("alım", "alış"),
    ("satım", "satış"),
    # industry / SCADA
    ("vana", "valf"),
    ("debi", "akış"),
    ("arıza", "fault"),
    ("uyarı", "alarm"),
    ("sensör", "algılayıcı"),
    ("yazmaç", "register"),
    ("pano", "panel"),
    ("motor", "pompa"),  # frequently interchanged in the field; remove if it hurts the measurement
    ("sondaj", "kuyu"),
    ("basınç", "bar"),
    # IT — everyday English↔Turkish vocabulary
    ("etiket", "tag"),
    ("yedek", "backup"),
    ("şifre", "parola", "password"),
    ("sunucu", "server"),
    ("veritabanı", "database"),
    ("eposta", "mail", "posta"),
    ("güncelleme", "update"),
    ("dizin", "klasör", "folder"),
    ("ağ", "network"),
    ("bağlantı", "link"),
    ("hata", "bug"),
    ("sürüm", "versiyon"),
    ("depolama", "disk"),
    ("bellek", "hafıza"),
    ("araç", "tool"),
    # everyday Turkish
    ("araba", "otomobil"),
    ("ev", "konut"),
    ("doktor", "hekim"),
    ("ilaç", "hap"),
    ("yanıt", "cevap"),
    ("soru", "sual"),
    ("sorun", "problem"),
    ("kent", "şehir"),
    ("görsel", "resim", "fotoğraf"),
    ("hedef", "amaç"),
    ("ders", "öğreti"),
    ("koşu", "koşmak"),
    ("yürüyüş", "yürümek"),
    ("takvim", "ajanda"),
    ("toplantı", "görüşme"),
    ("tatil", "izin"),
    ("maaş", "ücret"),
    ("kira", "kiralık"),
)

_CLEAN = re.compile(r"[^\wçğıöşü]+", re.UNICODE)

# word → the extra terms it calls. For prefix matching the keys are also
# kept by length ("etiketleri" → "etiket").
_CALLS: dict[str, tuple[str, ...]] = {}
for _group in GROUPS:
    for _word in _group:
        _CALLS.setdefault(_word, tuple(w for w in _group if w != _word))

# Prefix search only on keys of ≥5 letters: accidents like "işlem" calling
# "iş" are cut off by requiring an exact match on short keys.
_LONG_KEYS = tuple(sorted((k for k in _CALLS if len(k) >= 5),
                          key=len, reverse=True))


def calls_of(word: str) -> tuple[str, ...]:
    """The synonyms a word calls (suffixed forms included)."""
    plain = _CLEAN.sub("", (word or "").casefold())
    if not plain:
        return ()
    if plain in _CALLS:
        return _CALLS[plain]
    for key in _LONG_KEYS:
        if plain.startswith(key):
            return _CALLS[key]
    return ()


def expand(query: str) -> str:
    """Adds synonymous extra terms to the query; returns it unchanged if none.

    The additions go at the END: an extra OR term on the FTS side, a few
    extra features on the signature side. Since the record side does not
    change, the expansion can be reverted at any time — the index is not
    rebuilt.
    """
    text = query or ""
    extra: list[str] = []
    seen = set(_CLEAN.sub(" ", text.casefold()).split())
    for word in text.split():
        for called in calls_of(word):
            if called not in seen:
                seen.add(called)
                extra.append(called)
    return f"{text} {' '.join(extra)}" if extra else text
