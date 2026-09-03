"""Associative signature layer — the "intuition" side of recall.

FTS5 knows the word, not the meaning. A search for "postgres yedeği" can
never find a record saying "veritabanı dökümü"; a letter's difference is
enough for the record to become invisible. The layer here fills that gap.

The idea comes from LLM token embeddings but there are no weights, no
training, and no model downloaded from outside: every text is projected onto
a fixed **hypervector** (random projection / SimHash). Close texts produce
close vectors; the distance is Hamming distance.

The real gain is speed. The vector is 256 bits — a single Python integer.
Comparing two records is `(a ^ b).bit_count()`, that is, work on the level
of a single machine instruction. Float cosine similarity meant 256
multiplications; this is one XOR. Fifty thousand records are scanned in pure
Python within milliseconds — which was exactly the user's condition: "if it
gets lost for minutes once a long time has passed, there is no point".

Feature extraction has two channels:

    word          "rapor"        — exact match, strong signal
    4-char gram   "rapo" "apor"  — Turkish is agglutinative; "raporları"
                                   and "rapor" overlap in this channel

Together they produce a trace robust to both typos and inflectional
suffixes.
"""

from __future__ import annotations

import hashlib
import re
from typing import Iterable, Iterator

# Signature width. 256 bits fits in a single integer and is more than enough
# to discriminate; making it bigger pushes the comparison into multi-limb
# arithmetic.
BITS = 256

# Words shorter than this are not split — their fragment is already
# themselves.
GRAM = 4

# Two randomly matching signatures agree on half their bits. Below that is
# noise, not information; it is clipped to zero so it does not leak into
# seeding.
CHANCE = 0.5

# Noise floor. Two unrelated signatures agree not on exactly half their bits
# but around half; at 256 bits the spread is ~0.06 on the similarity scale.
# The floor must be above this scatter, otherwise every query "remembers"
# something.
FLOOR = 0.15

_WORD = re.compile(r"\w+", re.UNICODE)

# Function words that do not narrow the query (prepositions, pronouns,
# question particles, conjunctions). Dropped in the FTS literal channel
# (store._match_expression): a question like "bir fıkra anlat" was sticking,
# through FTS, to a general memory containing "bir" ("...bir kod asistanı
# değil; genel bir ajan"), and a query that should have come back empty
# remembered something. Noise, not content.
#
# NOT dropped on the signature side — deleting them there makes short texts
# ("bir şey" → a single "şey" feature) unstable and similar to one another
# (see test_vector short-texts). The frequent-word problem in the signature
# should be handled separately (IDF weighting).
STOPWORDS = frozenset(
    """
    ve veya ile için gibi kadar daha çok az bir bu şu o ne nasıl neden
    da de ki mi mı mu mü ben sen biz siz onlar var yok olan olarak
    the a an and or of to in on for with is are was were be been it this that
    """.split()
)

# Byte -> the sign sequence of that byte's 8 bits. Instead of 256 bit shifts
# per feature we do 32 table lookups; indexing gets several times faster.
_SIGNS: tuple[tuple[int, ...], ...] = tuple(
    tuple(1 if (byte >> (7 - i)) & 1 else -1 for i in range(8)) for byte in range(256)
)


def features(text: str) -> Iterator[str]:
    """Splits the text into the features to be signed.

    The word itself and its character n-grams are given together: the first
    provides precision, the second tolerance.
    """
    for match in _WORD.finditer((text or "").lower()):
        word = match.group(0)
        yield word
        if len(word) > GRAM:
            for i in range(len(word) - GRAM + 1):
                yield word[i : i + GRAM]


def signature(text: str) -> int:
    """The text's 256-bit association signature.

    Every feature expands into a fixed ±1 vector derived from its own hash,
    all are summed, and the result is turned into bits by sign. The same
    text gives the same signature on every run — the hash seed is fixed.
    """
    weights = [0] * BITS
    seen = False

    for feature in features(text):
        seen = True
        digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=BITS // 8).digest()
        offset = 0
        for byte in digest:
            signs = _SIGNS[byte]
            for i in range(8):
                weights[offset + i] += signs[i]
            offset += 8

    if not seen:
        return 0

    # Ties (sum 0) are frequent in short texts: in a record with two or
    # three features most dimensions stay tied. Writing ties to a fixed side
    # made all short texts look alike — "bir sey" and "hic konusulmamis
    # konu" came out as neighbours. Instead a bit is taken from the text's
    # own digest: the same text gives the same bit, a different text gives
    # an independent bit.
    tie = int.from_bytes(
        hashlib.blake2b(text.encode("utf-8"), digest_size=BITS // 8).digest(), "big"
    )

    value = 0
    for position, weight in enumerate(weights):
        if weight:
            bit = 1 if weight > 0 else 0
        else:
            bit = (tie >> (BITS - 1 - position)) & 1
        value = (value << 1) | bit
    return value


def similarity(a: int, b: int) -> float:
    """Closeness of two signatures, 0..1.

    Below chance (two random signatures agreeing on half) is clipped to
    zero; otherwise every unrelated record would enter the list with 0.5
    points.
    """
    if not a or not b:
        return 0.0
    agreement = 1.0 - (a ^ b).bit_count() / BITS
    return max(0.0, (agreement - CHANCE) / (1.0 - CHANCE))


def to_blob(value: int) -> bytes:
    return value.to_bytes(BITS // 8, "big")


def from_blob(blob: bytes | None) -> int:
    return int.from_bytes(blob, "big") if blob else 0


class Index:
    """The signatures as they live in RAM.

    All of it is kept in memory because there is no reason not to: fifty
    thousand records mean ~1.6 MB of signatures. The actual body stays on
    disk; only the "what does it look like" information lives here.

    The search is a plain scan — but since what is scanned is an integer
    XOR, the complexity of approximate-neighbour structures (HNSW, IVF) is
    unnecessary at this scale.
    """

    __slots__ = ("_sigs", "_flat")

    def __init__(self, entries: Iterable[tuple[str, int]] = ()) -> None:
        self._sigs: dict[str, int] = {k: v for k, v in entries if v}
        # The flat list the scan runs over. Iterating over the dict added a
        # hash-table step at every iteration; with the scan already down to a
        # single XOR, that overhead was a noticeable share of the total.
        self._flat: list[tuple[int, str]] | None = None

    def __len__(self) -> int:
        return len(self._sigs)

    def __contains__(self, node_id: str) -> bool:
        return node_id in self._sigs

    def add(self, node_id: str, value: int) -> None:
        if value:
            self._sigs[node_id] = value
            self._flat = None

    def ids(self) -> list[str]:
        """The ids sitting in the index. The hot set itself (Phase 3.11)."""
        return list(self._sigs)

    def drop(self, node_id: str) -> None:
        if self._sigs.pop(node_id, None) is not None:
            self._flat = None

    def search(self, query: int, limit: int, *, floor: float = FLOOR) -> list[tuple[str, float]]:
        """Returns the closest `limit` signatures.

        The scan is exact and LINEAR: unlike approximate-neighbour structures
        (LSH bands, HNSW) it misses no match. Nor is one needed at this
        scale — since the work per record is a single XOR and popcount,
        fifty thousand records take ~3-5 ms (measured, 29.08); a thousandth
        of a model call.

        `floor` is the noise floor: everything below it means "I did not
        remember". Letting a weak match into the list makes spreading
        activation jump into an unrelated region.
        """
        if not query or not self._sigs:
            return []

        if self._flat is None:
            self._flat = [(value, node_id) for node_id, value in self._sigs.items()]

        # The floor is computed once outside the loop, in distance terms:
        # computing the similarity ratio for every candidate would slow the
        # scan down.
        #   sim >= floor  <=>  hamming <= BITS * CHANCE * (1 - floor)
        cutoff = int(BITS * CHANCE * (1.0 - floor))

        near = [
            (distance, node_id)
            for distance, node_id in (
                ((query ^ value).bit_count(), node_id) for value, node_id in self._flat
            )
            if distance <= cutoff
        ]
        near.sort()
        span = BITS * (1.0 - CHANCE)
        return [
            (node_id, round((BITS * CHANCE - distance) / span, 4))
            for distance, node_id in near[:limit]
        ]
