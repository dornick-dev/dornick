"""Scale benchmark: priming quality and token cost at 100 memories + 60 episodes.

The question has three layers:
  1. Are we recalling the wrong things? (a weather question must not fetch
     crypto)
  2. Are we saving context? (how many tokens get injected per turn)
  3. Is there a better method? (toggle the gates one by one and look at
     the Pareto front)

The measured path is THE PRODUCT ITSELF: the `current` method calls
`dornick.loop.select_prime`; the variants are a parametric copy of the same
logic, and the copy with default parameters is asserted equal to the
product on every query (a silently drifted copy would mean the benchmark
no longer measures the product — it blows up right there instead).

Run:  py eval/context_memory/scale_bench.py

Note: the memory corpus and the queries are Turkish by design — this bench
measures recall for a Turkish-speaking user's memory. The measurement
machinery around it is what this file is.
"""

from __future__ import annotations

import json
import statistics
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
except Exception:
    pass

from dornick.loop import (  # noqa: E402
    RECALL_PRIME_FLOOR,
    RECALL_PRIME_HEADER,
    RECALL_PRIME_LIMIT,
    _one_line,
    _query_stems,
    _without_numbers,
    select_prime,
    worth_recalling,
)
from dornick.mind import open_mind  # noqa: E402

HERE = Path(__file__).resolve().parent

# Rough token estimate for Turkish: ~4 chars / token. The absolute value
# does not matter — all methods are compared with the SAME ruler.
CHARS_PER_TOKEN = 4.0


def tokens_of(text: str) -> float:
    return len(text) / CHARS_PER_TOKEN


# -- corpus -------------------------------------------------------------


def load_dataset() -> dict[str, Any]:
    return json.loads((HERE / "scale_dataset.json").read_text(encoding="utf-8"))


def build_mind(data: dict[str, Any], root: Path) -> tuple[Any, dict[str, str]]:
    """Write the memories and episodes into a fresh mind. Returns slug → node id."""
    mind = open_mind(root / "mind", root / "sessions", "bench")
    allowed = {"fact", "preference", "lesson", "procedure", "user", "voice"}
    ids: dict[str, str] = {}
    for memory in data["memories"]:
        node = mind.remember(
            memory["content"],
            kind=memory["kind"] if memory["kind"] in allowed else "fact",
            title=memory["title"],
            tags=list(memory.get("tags") or []),
        )
        ids[memory["slug"]] = node.id
    for episode in data["episodes"]:
        mind.remember(episode["content"], kind="episode", title=episode["title"])
    return mind, ids


# -- methods ------------------------------------------------------------
#
# Every method is (mind, query) → (hits, note text). The note text is
# exactly what enters the token ruler; some methods only shorten the text.


def note_text(hits: list[Any], line_cap: int) -> str:
    """The product's prime_note format, with an adjustable line cap."""
    if not hits:
        return ""
    lines = [RECALL_PRIME_HEADER]
    for hit in hits:
        item = hit.item
        body = " ".join((item.content or "").split())
        title = " ".join((item.title or "").split())
        if title and not body.casefold().startswith(title.casefold()[:40]):
            body = f"{title} — {body}"
        lines.append(f"- [{item.kind}] {_one_line(body, line_cap)}")
    return "\n".join(lines)


def matched_stems(item: Any, stems: set[str]) -> int:
    text = f"{item.title} {item.content} {' '.join(item.tags)}".casefold()
    return sum(1 for stem in stems if stem in text)


def parametric(
    mind: Any,
    user_input: str,
    *,
    limit: int = RECALL_PRIME_LIMIT,
    floor: float = RECALL_PRIME_FLOOR,
    direct_only: bool = True,
    drop_episodes: bool = True,
    ground_min: int = 1,
    ground_ratio: float = 0.0,
    tiered: bool = False,
    lone_score: float = 0.0,
    weigh: float = 0.0,
    gap: float = 0.0,
) -> list[Any]:
    """The adjustable copy of select_prime. Defaults mirror the product.

    tiered: if candidates with ≥2 pieces of evidence exist, only they
    survive; otherwise fall back to single-evidence mode, but show at most
    TOP-1 there (a single weak overlap must not fill five lines), and if
    `lone_score` is given the top's score must beat it.
    """
    query = _without_numbers(user_input)
    hits = mind.recall(query, limit=limit)

    trace = getattr(mind, "last_trace", None) or []
    direct = {step.node for step in trace if step.hop == 0}
    if direct_only and not direct:
        return []
    stems = _query_stems(query)

    # Product rule (2026-08-28): when the RAW query has ≥5 stems, a record
    # grounded by a single (prefix-deduplicated) stem cannot prime. The
    # copy carries it verbatim.
    rich = len(_query_stems(query, expand=False)) >= 5

    def _distinct_matches(item: Any) -> int:
        text = f"{item.title} {item.content} {' '.join(item.tags)}".casefold()
        matched = [g for g in stems if g in text]
        distinct = [g for g in matched
                    if not any(g != d and d.startswith(g) for d in matched)]
        return len(distinct)

    def need_for(item: Any) -> bool:
        if not stems:
            return True
        got = matched_stems(item, stems)
        if ground_ratio > 0:
            import math

            return got >= max(1, math.ceil(ground_ratio * len(stems)))
        if ground_min > 1:
            return got >= min(ground_min, max(1, len(stems) - 1))
        if not got:
            return False
        return _distinct_matches(item) >= 2 if rich else True

    passed = [
        hit
        for hit in hits
        if (not drop_episodes or hit.item.kind != "episode")
        and (not direct_only or hit.item.id in direct)
        and need_for(hit.item)
    ]
    if weigh > 0 and stems:
        # Scores saturate (measured: gold median 0.963, leak 0.874 — no
        # separation) but score × evidence-ratio separates (0.477 vs
        # 0.167). The threshold sits on the product; the top exemption
        # only for a top with strong evidence (ratio ≥ 0.5) — in a young
        # memory the score collapses but the ratio stays high.
        def heft(h: Any) -> float:
            return h.score * (matched_stems(h.item, stems) / len(stems))

        best = max(passed, key=heft, default=None)
        passed = [
            h for h in passed
            if heft(h) >= weigh
            or (h is best and matched_stems(h.item, stems) / len(stems) >= 0.5)
        ]
    if tiered and stems:
        strong = [h for h in passed if matched_stems(h.item, stems) >= 2]
        if strong:
            passed = strong
        elif passed:
            lone = max(passed, key=lambda h: h.score)
            passed = [lone] if (lone_score == 0 or lone.score >= lone_score) else []
    if not passed:
        return []
    top = max(passed, key=lambda h: h.score)
    if top.score < floor:
        # Product rule (2026-08-29): the unconditional-top exemption only
        # applies to a YOUNG mind; in a mature one, no record above the
        # floor means no injection (the +9% unrelated-work leak).
        try:
            young = mind.store.count() < 30
        except Exception:
            young = True
        if not young:
            return []
    kept = [h for h in passed if h is top or h.score >= floor]
    if gap > 0:
        kept = [h for h in kept if h is top or h.score >= gap * top.score]
    return kept[:limit]


METHODS: dict[str, tuple[Callable[..., list[Any]], int]] = {
    # name → (selector, line cap)
    "current": (lambda m, q: select_prime(m, q), 220),
    # Gateless: the ablation showing what the filters rescue.
    "bare": (lambda m, q: parametric(m, q, direct_only=False,
                                     drop_episodes=False, ground_min=0,
                                     floor=0.0), 220),
    # Tail cut: everything below 45% of the strongest drops.
    "gap45": (lambda m, q: parametric(m, q, gap=0.45), 220),
    # Double grounding: one accidental word is not enough on multi-word queries.
    "ground2": (lambda m, q: parametric(m, q, ground_min=2), 220),
    # Short lines: same selection, half the tokens.
    "short120": (lambda m, q: select_prime(m, q), 120),
    # Ratio grounding: 40% of the query stems must appear in the record.
    "ratio40": (lambda m, q: parametric(m, q, ground_ratio=0.4), 220),
    # Tiered evidence: doubles if any; else single-evidence top-1.
    "tiered": (lambda m, q: parametric(m, q, tiered=True), 220),
    # Tiered + a score requirement in single-evidence mode.
    "tiered05": (lambda m, q: parametric(m, q, tiered=True, lone_score=0.5), 220),
    # Score × evidence-ratio threshold (born from a diagnostic run).
    "product16": (lambda m, q: parametric(m, q, weigh=0.16), 220),
    "product20": (lambda m, q: parametric(m, q, weigh=0.20), 220),
    "product24": (lambda m, q: parametric(m, q, weigh=0.24), 220),
    # A record whose full body already sits in the soul is not re-injected:
    # the model has carried it in context since the session began. Zero
    # information loss.
    "nonsoul": (lambda m, q: [h for h in select_prime(m, q)
                              if h.item.id not in SOUL_IDS], 220),
    # IDF-weighted evidence threshold: a common word must not open a trap.
    "idf16": (lambda m, q: idf_pick(m, q, 0.16), 220),
    "idf24": (lambda m, q: idf_pick(m, q, 0.24), 220),
    "idf32": (lambda m, q: idf_pick(m, q, 0.32), 220),
    # Numbers are kept on number-heavy queries. (The lambda is required:
    # the function is defined below, its name does not exist while this
    # dict is being built.)
    "numeric": (lambda m, q: keep_numbers_pick(m, q), 220),
    # Plain 160 truncation, not sentence-aware (for the token ruler).
    "short160": (lambda m, q: select_prime(m, q), 160),
}

# Records the soul puts into context with their full body (filled in main).
# `procedure` is excluded: the soul carries only its title, the body is
# still valuable in the prime.
SOUL_IDS: set[str] = set()

# Stem → how many corpus records contain it (for the IDF experiment; main fills).
STEM_DF: dict[str, int] = {}
CORPUS_N: int = 1


def idf_ratio(item: Any, stems: set[str]) -> float:
    """IDF-weighted evidence ratio: rare stems count a lot, common ones little.

    The plain ratio opened traps through a word like "Konya" that appears
    all over the corpus; IDF lowers that word's weight. Weight is
    log(1 + N/df).
    """
    import math

    if not stems:
        return 1.0
    text = f"{item.title} {item.content} {' '.join(item.tags)}".casefold()
    total = got = 0.0
    for stem in stems:
        weight = math.log(1 + CORPUS_N / (STEM_DF.get(stem, 0) + 1))
        total += weight
        if stem in text:
            got += weight
    return got / total if total else 0.0


def idf_pick(mind: Any, user_input: str, threshold: float) -> list[Any]:
    """The product16 family with IDF: the threshold sits on score × IDF ratio."""
    query = _without_numbers(user_input)
    hits = select_prime(mind, user_input)
    stems = _query_stems(query)
    if not stems or not hits:
        return hits

    def heft(h: Any) -> float:
        return h.score * idf_ratio(h.item, stems)

    best = max(hits, key=heft)
    return [h for h in hits
            if heft(h) >= threshold
            or (h is best and idf_ratio(h.item, stems) >= 0.5)]


def keep_numbers_pick(mind: Any, user_input: str) -> list[Any]:
    """Number preservation: keep the digits when the query is number-heavy.

    Dropping numbers was added against a crypto-price leak; but in a query
    like "which register is 404195" the number IS the thing being looked
    up — dropping it pins the numeric class at 0.75. Rule: if fewer than
    two content stems survive without the numbers, the numbers stay.
    """
    stripped = _without_numbers(user_input)
    if len(_query_stems(stripped)) >= 2:
        return select_prime(mind, user_input)
    # loop.select_prime always drops numbers; for the numeric path we use
    # the query as-is through the parametric copy.
    hits = mind.recall(user_input, limit=RECALL_PRIME_LIMIT)
    trace = getattr(mind, "last_trace", None) or []
    direct = {step.node for step in trace if step.hop == 0}
    if not direct:
        return []
    passed = [h for h in hits
              if h.item.kind != "episode" and h.item.id in direct]
    if not passed:
        return []
    top = max(passed, key=lambda h: h.score)
    return [h for h in passed
            if h is top or h.score >= RECALL_PRIME_FLOOR][:RECALL_PRIME_LIMIT]


# -- measurement --------------------------------------------------------


def run_method(
    name: str,
    data: dict[str, Any],
    mind: Any,
    ids: dict[str, str],
) -> dict[str, Any]:
    select, line_cap = METHODS[name]
    slug_of = {node_id: slug for slug, node_id in ids.items()}

    hit_recall = []        # queries with gold: did at least one gold come
    coverage = []          # how much of the gold came
    precision = []         # how much of what came is gold
    silence_ok = []        # goldless queries: did it stay quiet
    leaks: list[str] = []  # leak samples (for the report)
    wrongs: list[str] = []
    token_costs = []
    times = []
    by_type: dict[str, list[float]] = {}

    for query in data["queries"]:
        gold = {ids[s] for s in query["gold"]}
        started = time.perf_counter()
        # The product flow's first gate: the mind never opens on a message
        # not worth recalling for.
        hits = select(mind, query["q"]) if worth_recalling(query["q"]) else []
        times.append((time.perf_counter() - started) * 1000)
        note = note_text(hits, line_cap)
        token_costs.append(tokens_of(note))

        got = {hit.item.id for hit in hits}
        kind = query["type"]

        if gold:
            # Gold already sitting in the soul is already in context: no
            # method is obliged to inject it — counted fair for all.
            satisfied = got | (gold & SOUL_IDS)
            ok = 1.0 if satisfied & gold else 0.0
            hit_recall.append(ok)
            coverage.append(len(satisfied & gold) / len(gold))
            if got:
                precision.append(len(got & gold) / len(got))
                for wrong in got - gold:
                    wrongs.append(f"{kind} «{query['q'][:40]}» → "
                                  f"{slug_of.get(wrong, 'EPISODE')}")
            by_type.setdefault(kind, []).append(ok)
        else:
            quiet = 1.0 if not got else 0.0
            silence_ok.append(quiet)
            if got:
                sample = ", ".join(slug_of.get(g, "EPISODE")
                                   for g in list(got)[:3])
                leaks.append(f"{kind} «{query['q'][:40]}» → {sample}")
            by_type.setdefault(kind, []).append(quiet)

    mean = lambda xs: statistics.fmean(xs) if xs else 0.0
    tokens_avg = mean(token_costs)
    recall = mean(hit_recall)
    return {
        "name": name,
        "recall": recall,
        "coverage": mean(coverage),
        "precision": mean(precision),
        "silence": mean(silence_ok),
        "tokens": tokens_avg,
        # Yield: "hit queries" per 1000 tokens. The goal is minimum context
        # for maximum recall; this squeezes it into one number.
        "yield": (recall * 1000 / tokens_avg) if tokens_avg else float("inf"),
        "p95_ms": sorted(times)[int(len(times) * 0.95) - 1],
        "by_type": {k: mean(v) for k, v in sorted(by_type.items())},
        "leaks": leaks[:10],
        "wrongs": wrongs[:10],
    }


def repeat_bench(data: dict[str, Any], mind: Any, ids: dict[str, str]) -> dict[str, float]:
    """A 12-turn conversation on one topic: how often is the same memory
    re-injected?

    In-turn repetition is its own waste channel: the model reads the same
    memory twelve times.
    """
    talk = [q["q"] for q in data["queries"]
            if q["type"] in ("exact", "continuation")][:12]
    plain, seen_costs = 0.0, 0.0
    seen: set[str] = set()
    for q in talk:
        hits = select_prime(mind, q)
        plain += tokens_of(note_text(hits, 220))
        fresh = [h for h in hits if h.item.id not in seen]
        seen.update(h.item.id for h in hits)
        seen_costs += tokens_of(note_text(fresh, 220))
    return {"repeated": plain, "deduplicated": seen_costs,
            "saving": 1 - (seen_costs / plain) if plain else 0.0}


def main() -> None:
    data = load_dataset()
    print(f"corpus: {len(data['memories'])} memories + "
          f"{len(data['episodes'])} episodes, "
          f"{len(data['queries'])} queries\n")

    with tempfile.TemporaryDirectory() as tmp:
        mind, ids = build_mind(data, Path(tmp))

        # Corpus stem frequencies for the IDF experiment (memories + episodes).
        global CORPUS_N
        texts = [f"{m['title']} {m['content']} {' '.join(m.get('tags') or [])}"
                 for m in data["memories"]]
        texts += [f"{e['title']} {e['content']}" for e in data["episodes"]]
        CORPUS_N = len(texts)
        STEM_DF.clear()
        seen_stems = {s for q in data["queries"]
                      for s in _query_stems(_without_numbers(q["q"]))}
        for stem in seen_stems:
            STEM_DF[stem] = sum(1 for t in texts if stem in t.casefold())

        # Mirrors the product's soul selection: kinds whose full body
        # enters context.
        soul = mind.soul()
        SOUL_IDS.clear()
        SOUL_IDS.update(m.id for group in
                        (soul.user, soul.preferences, soul.lessons, soul.voice)
                        for m in group)
        print(f"in the soul with full body: {len(SOUL_IDS)} records\n")

        # Guard: does the parametric copy with defaults equal the product?
        for query in data["queries"]:
            a = {h.item.id for h in select_prime(mind, query["q"])}
            b = {h.item.id for h in parametric(mind, query["q"])}
            assert a == b, f"copy drifted from the product: {query['q']!r} {a} != {b}"
        print("guard: parametric copy == product (all queries)\n")

        rows = [run_method(name, data, mind, ids) for name in METHODS]

        head = (f"{'method':<10} {'recall':>7} {'coverage':>9} "
                f"{'precision':>10} {'silence':>8} {'tok/query':>10} "
                f"{'yield':>7} {'p95ms':>6}")
        print(head)
        print("-" * len(head))
        for r in rows:
            print(f"{r['name']:<10} {r['recall']:>7.2f} {r['coverage']:>9.2f} "
                  f"{r['precision']:>10.2f} {r['silence']:>8.2f} "
                  f"{r['tokens']:>10.1f} {r['yield']:>7.1f} {r['p95_ms']:>6.2f}")

        print("\nby query type (recall or silence):")
        kinds = sorted({k for r in rows for k in r["by_type"]})
        print(f"{'method':<10} " + " ".join(f"{k:>12}" for k in kinds))
        for r in rows:
            print(f"{r['name']:<10} " + " ".join(
                f"{r['by_type'].get(k, float('nan')):>12.2f}" for k in kinds))

        for r in rows:
            if r["leaks"] or r["wrongs"]:
                print(f"\n{r['name']} leaks:")
                for line in r["leaks"] + r["wrongs"]:
                    print("  !", line)

        echo = repeat_bench(data, mind, ids)
        print(f"\nrepetition in a 12-turn conversation: "
              f"{echo['repeated']:.0f} tok → deduplicated "
              f"{echo['deduplicated']:.0f} tok "
              f"(saving {echo['saving'] * 100:.0f}%)")

        # The anchor for comparison: what would sending everything cost?
        everything = sum(tokens_of(m["content"]) + tokens_of(m["title"])
                         for m in data["memories"])
        print(f"\nanchor: sending ALL memories every turn ≈ "
              f"{everything:.0f} tok/query")

        # Windows: an open SQLite connection blocks deleting the tmp folder.
        mind.store.close()


if __name__ == "__main__":
    main()
