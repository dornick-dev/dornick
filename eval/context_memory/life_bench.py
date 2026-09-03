"""Life benchmark: how memory behaves across days.

`scale_bench.py` asks a single-turn question — "for this query, which of
these hundred memories should come". It measures neither time, nor
repetition, nor correction. Yet the whole claim of a human-like memory is
about time: a used trace strengthens, an unused one falls behind, corrected
knowledge replaces the old, what happened during the day is replayed at
night. None of that shows up in a single turn.

This closes that gap: a frozen life scenario (`yasam_dataset.json`, 90
virtual days, grouped into sessions) is played day by day on a **virtual
clock**. On every `sor` event the product's own `select_prime`,
`mind.recall` and `mind.soul()` are called; at the end of each day — if
present — the night pass. No copied selection logic; the measured path is
the product's own path.

Run:

    py eval/context_memory/life_bench.py --label taban --old
    py eval/context_memory/life_bench.py --label f1 --previous taban
    py eval/context_memory/life_bench.py --disable activation --label f1-ablasyon
    py eval/context_memory/life_bench.py --data holdout --label holdout --fast
    py eval/context_memory/life_bench.py --threshold-curve
    py eval/context_memory/life_bench.py --growth
    py eval/context_memory/life_bench.py --table

`--old` runs the version at the `hafiza-eski` tag from the `eval/eski/`
worktree in a separate process. The old code has no clock injection; the
module-level `_now` is patched so both versions see **the same virtual
calendar**. Metrics of mechanisms the old version never had are reported as
`yok` — never left blank.

Three notes on measurement honesty:

* The questions were written so that they carry at least one content word
  of the expected record. That is not a shortcut, it is a scoping decision:
  the gap Turkish morphology opens in lexical search is a separate problem
  and no phase of the roadmap solves it. Had the dataset been filled with
  it, every metric would drown in that gap's noise and the
  time/consolidation/update difference would become invisible.
* The `G` (long silence), `I`, `N`, `O`, `Q` clusters do NOT enter the
  `prime_precision` / `prime_recall` averages; each has its own metric. A
  forgotten record not entering the spontaneous prime is the purpose of the
  design; counting it against prime recall would punish the mechanism with a
  number that contradicts its own goal.
* Before Phase 3 lands, the H/I/J/K/N/O baseline comes out low. That is the
  expected and desired result; the difference that proves the benefit comes
  from there.
"""

from __future__ import annotations

import argparse
import inspect
import json
import os
import statistics
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OLD_TREE = ROOT / "eval" / "eski"

# Which source tree is being measured: the product itself, or the
# `hafiza-eski` tag.
SOURCE = Path(os.environ.get("DORNICK_SRC") or (ROOT / "src"))
sys.path.insert(0, str(SOURCE))
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
except Exception:
    pass

from dornick.events import EventLog  # noqa: E402
from dornick.loop import (  # noqa: E402
    RECALL_PRIME_LIMIT,
    prime_note,
    select_prime,
    worth_recalling,
)
from dornick.mind import open_mind  # noqa: E402

try:                                    # Exists from Phase 0 on; not in the old tree.
    from dornick.recall import switches
except ImportError:                     # pragma: no cover - only the --old path
    switches = None
try:
    from dornick.recall import vector
except ImportError:                     # pragma: no cover
    vector = None
try:                                    # Exists from Phase 3.12 on.
    from dornick.recall import awake
except ImportError:                     # pragma: no cover
    awake = None

OLD_VERSION = os.environ.get("DORNICK_OLD") == "1"

# Rough token estimate for Turkish: ~4 chars = 1 token. The absolute value
# does not matter — every version is compared with the SAME ruler.
CHARS_PER_TOKEN = 4.0

# Kinds that appear in the soul (Soul fields). `fact` and `episode` do not
# enter the soul.
SOUL_KINDS = ("user", "preference", "lesson", "voice", "procedure")

# Clusters that enter the prime precision/recall average.
FAIR_CLUSTERS = ("A", "B", "D", "E", "H", "J", "K")

# How many results the open search looks at, per cluster (roadmap 0.3).
OPEN_DEPTH = {"G": 8, "H": 5, "J": 8, "K": 8}

FRESH_WINDOW_DAYS = 7

# Scale condition: `recall()` p95 ≤ 20 ms at 50k nodes.
SCALE_NODES = 50_000
LATENCY_BUDGET_MS = 20.0

# Growth experiment (P cluster): the ratio of 200k to 20k.
GROWTH_LARGE = 200_000
GROWTH_SMALL = 20_000
# Size of the active set — the same in both memories. The whole claim of
# the hot/cold split is this: cost grows with the active set, not with the
# total memory.
HOT_FILL = 2_000

# Penalty written when the lesson never showed up inside the session (Q
# cluster): "until the night".
LESSON_UNTIL_NIGHT = 99

# Metric registry: name -> (direction, comparison, target). A metric whose
# target is None is read against the baseline; one with a target is an
# absolute threshold.
TARGETS: dict[str, tuple[str, str, float | None]] = {
    "prime_precision":      ("↑", ">=", 0.85),
    "prime_recall":         ("↑", ">=", 0.80),
    "yasak_sizinti":        ("↓", "<=", 0.0),
    "tuzak_sessizlik":      ("↑", ">=", 0.90),
    "bayat_ruh":            ("↓", "<=", 0.0),
    "taze_ruh":             ("↑", ">=", 0.80),
    "ruh_token":            ("↓", "<=", None),
    "prime_token":          ("↓", "<=", None),
    "geri_donus_recall":    ("↑", ">=", 0.70),
    "komsuluk_recall":      ("↑", ">=", 0.75),
    "sorumluluk_dogrulugu": ("↑", ">=", 0.85),
    "dikis_recall":         ("↑", ">=", 0.60),
    "gomulme_recall":       ("↑", ">=", 0.90),
    "sema_tazeleme":        ("↑", ">", 0.0),
    "yakalama":             ("↑", ">", 0.0),
    "ders_gecikmesi":       ("↓", "<=", 1.0),
    "sicak_oran":           ("·", "aralik", None),
    "gece_suresi":          ("↓", "<=", 300.0),
    "uykusuz_kayip":        ("↑", ">=", 0.80),
    "uykusuz_sisme":        ("↓", "<=", 1.30),
    "aktif_bolge_ihlali":   ("↓", "<=", 0.0),
    "tur_bloklama":         ("↓", "<=", 50.0),
    "kesinti_kaybi":        ("↓", "<=", 0.0),
    "kesinti_gecikmesi":    ("↓", "<=", 500.0),
    "yarim_damitma":        ("↓", "<=", 0.0),
    "ritim_isabeti":        ("↑", ">=", 0.90),
    "atalet":               ("↓", "<=", 0.0),
    "buyume_p95":           ("↓", "<=", 1.5),
    "buyume_ram":           ("↓", "<=", 2.0),
    "gecikme_p95":          ("↓", "<=", LATENCY_BUDGET_MS),
}


def tokens_of(text: str) -> float:
    return len(text) / CHARS_PER_TOKEN


# -- virtual clock -----------------------------------------------------


class VirtualClock:
    """The scenario's calendar. The product takes it for the wall clock (see
    recall/clock.py).

    Every event pushes the clock at least one minute forward: the order of
    two records written at the same moment must not get lost in the
    `created` stamp (freshness and temporal neighbourhood look at it).
    """

    def __init__(self, start: datetime) -> None:
        self.start = start
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def text(self) -> str:
        return self.now.isoformat(timespec="milliseconds")

    def advance(self, day: int, hour: int) -> None:
        target = self.start + timedelta(days=day - 1, hours=hour)
        self.now = max(target, self.now + timedelta(minutes=1))


# -- scenario ----------------------------------------------------------


def load_data(name: str) -> dict[str, Any]:
    file = {"ana": "yasam_dataset.json", "holdout": "yasam_holdout.json"}.get(name, name)
    return json.loads((HERE / file).read_text(encoding="utf-8"))


def _open_mind(root: Path, clock: VirtualClock) -> Any:
    """Opens the mind on the virtual clock; patches `_now` in the old version.

    The old code has no clock injection. So that both versions see the SAME
    calendar, the module-level `_now` is replaced with the virtual clock —
    without touching the old source, only for the duration of the
    measurement.
    """
    if "clock" in inspect.signature(open_mind).parameters:
        mind = open_mind(root / "mind", root / "sessions", "bench", clock=clock)
        # Warm the signature index SYNCHRONOUSLY. The product warms it on a
        # background thread; where that build lands relative to the virtual
        # events would otherwise vary run to run. Touch it once while the
        # store is still empty so every later record is indexed in event
        # order, identical on every run.
        try:
            _ = mind.store.index
        except AttributeError:                      # pragma: no cover - old tree
            pass
        return mind

    import dornick.mind.store as _ms                       # pragma: no cover
    import dornick.recall.store as _rs                     # pragma: no cover
    _rs._now = _ms._now = clock.text                        # pragma: no cover
    return open_mind(root / "mind", root / "sessions", "bench")   # pragma: no cover


def _open_log(sessions_dir: Path, session: str, clock: VirtualClock) -> EventLog:
    if "clock" in inspect.signature(EventLog.__init__).parameters:
        return EventLog(sessions_dir / f"{session}.jsonl", clock=clock.text)
    return EventLog(sessions_dir / f"{session}.jsonl")        # pragma: no cover


class Tally:
    """Counters accumulated over the scenario."""

    def __init__(self) -> None:
        self.overlap = 0
        self.prime_size = 0
        self.expected_size = 0
        self.leaks = 0
        self.trap_total = 0
        self.trap_silent = 0
        self.latencies: list[float] = []
        self.prime_tokens: list[float] = []
        self.soul_tokens: list[float] = []
        self.stale_daily: list[int] = []
        self.fresh_ratios: list[float] = []
        self.question_count = 0
        self.cluster_overlap: dict[str, int] = {}
        self.cluster_expected: dict[str, int] = {}
        self.cluster_prime: dict[str, int] = {}
        self.cluster_leaks: dict[str, int] = {}
        self.open: dict[str, list[float]] = {}
        self.credit: list[float] = []
        self.measures: dict[str, list[float]] = {"N": [], "O": []}
        self.lesson_turns: list[float] = []
        self.night_durations: list[float] = []
        self.wake_events = 0
        self.awake_latencies: list[float] = []


def run(data: dict[str, Any], *, disabled: tuple[str, ...] = (),
        root: Path | None = None, distillation: bool = False) -> dict[str, Any]:
    """Plays the scenario day by day and returns the metrics."""
    global DISTIL_MODEL
    DISTIL_MODEL = _extractor_model if distillation else None    # noqa: PLW0603
    _neutralise_budgets()
    _deterministic_ids()
    if switches is not None:
        switches.reset()
        if disabled:
            switches.configure(**{name: False for name in disabled})

    start = datetime.fromisoformat(data["baslangic"])
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    clock = VirtualClock(start)

    tmp = None
    if root is None:
        tmp = tempfile.TemporaryDirectory(prefix="yasam-bench-")
        root = Path(tmp.name)

    mind = None
    try:
        mind = _open_mind(root, clock)
        return _play(mind, data, clock, root / "sessions")
    finally:
        DISTIL_MODEL = None
        if switches is not None:
            switches.reset()
        if tmp is not None:
            try:
                if mind is not None:
                    mind.store.close()
            except Exception:
                pass
            try:
                tmp.cleanup()
            except (OSError, PermissionError):
                pass    # WAL lock on Windows; the temp dir gets cleaned later


class Session:
    """A session in the scenario and its real event log.

    The night pass (Phase 3) reads the session logs: which node was touched
    in which order, how the session ended. The bench writes those logs
    **with the product's own `EventLog`** so that Phase 3 sees a real log,
    not an invented format.
    """

    def __init__(self, sessions_dir: Path, session_id: str, clock: VirtualClock) -> None:
        self.id = session_id
        self.log = _open_log(sessions_dir, session_id, clock)
        self.log.note("session_start", session_id=session_id)
        self.sequence: list[str] = []
        self.turn = 0

    def touch(self, node_id: str, event: str, **meta: Any) -> None:
        self.turn += 1
        self.log.note(event, memory_id=node_id, **meta)
        if node_id:
            self.sequence.append(node_id)

    def close(self, outcome: str) -> None:
        self.log.note("sonuc", sonuc=outcome, dizi=self.sequence, tur=self.turn)


def _play(mind: Any, data: dict[str, Any], clock: VirtualClock,
          sessions_dir: Path) -> dict[str, Any]:
    day_count = int(data["gun_sayisi"])
    daily: dict[int, list[dict[str, Any]]] = {}
    for event in data["olaylar"]:
        daily.setdefault(int(event["gun"]), []).append(event)

    id_of: dict[str, str] = {}
    slug_of: dict[str, str] = {}
    stale: set[str] = set()
    corrections: list[tuple[int, str, str]] = []
    sessions: dict[str, Session] = {}
    t = Tally()

    def session(name: str) -> Session:
        if name not in sessions:
            sessions[name] = Session(sessions_dir, name, clock)
        return sessions[name]

    def write(event: dict[str, Any]) -> str:
        common = dict(kind=event["kind"], title=event.get("baslik") or "",
                      tags=event.get("etiketler") or [])
        try:
            memory = mind.remember(event["icerik"], **common,
                                   context=event.get("baglam") or {})
        except TypeError:
            # The old version (`hafiza-eski`) knows nothing about context.
            # The bench has to drive both versions with the same data; we
            # drop the field and carry on, because "the old version never
            # did this" is a measurable result.
            memory = mind.remember(event["icerik"], **common)
        id_of[event["slug"]] = memory.id
        slug_of[memory.id] = event["slug"]
        return memory.id

    for day in range(1, day_count + 1):
        for event in sorted(daily.get(day, []),
                            key=lambda e: (e["saat"], e.get("oturum", ""),
                                           e.get("sira", 0))):
            clock.advance(day, int(event["saat"]))
            kind = event["tur"]
            if kind == "sessiz":
                continue
            ses = session(event["oturum"])

            if kind == "kaydet":
                ses.touch(write(event), "mind_write", kind=event["kind"])

            elif kind == "duzelt":
                old_id = id_of.get(event["eskisi"], "")
                update = getattr(mind, "update", None)
                supersede_on = switches is None or switches.ACTIVE.supersede
                if update is not None and old_id and supersede_on:
                    memory = update(old_id, event["icerik"], kind=event["kind"],
                                    title=event.get("baslik") or "",
                                    tags=event.get("etiketler") or [])
                    id_of[event["slug"]] = memory.id
                    slug_of[memory.id] = event["slug"]
                    ses.touch(memory.id, "mind_write", kind=event["kind"],
                              supersedes=old_id)
                else:
                    # Before Phase 2 the product behaves like this: the
                    # conflicting new record is written NEXT TO the old
                    # one, and the old one stays around.
                    ses.touch(write(event), "mind_write", kind=event["kind"])
                stale.add(event["eskisi"])
                corrections.append((day, event["slug"], event["kind"]))

            elif kind == "kullan":
                for slug in event["hedef"]:
                    if nid := id_of.get(slug):
                        mind.store.open(nid)
                        ses.touch(nid, "mind_open")

            elif kind == "arac":
                ses.turn += 1
                ses.log.note("tool_start", tool=event.get("arac", ""),
                             input={"ozet": event["icerik"]})
                ses.log.note("tool_end", tool=event.get("arac", ""),
                             error=bool(event.get("hata")), ms=120,
                             ozet=event["icerik"])
                if event.get("hata"):
                    # Awake reverse replay (3.12.1): the moment the outcome
                    # is known, inside the session. Leaving the lesson to
                    # the night meant allowing the same mistake to be
                    # repeated in the same session.
                    _awake_outcome(mind, ses, "basarisiz", t, clock=clock)

            elif kind == "sonuc":
                ses.close(event["sonuc"])
                _awake_outcome(mind, ses, event["sonuc"], t, clock=clock)

            elif kind == "uyan":
                t.wake_events += 1
                _wake(event)

            elif kind == "sor":
                _query(mind, event, t, slug_of, id_of, ses)

        # End of day: the night pass (if any), then the soul's state that day.
        clock.advance(day, 22)
        if (duration := _night_pass(mind, sessions_dir, clock)) is not None:
            t.night_durations.append(duration)

        clock.advance(day, 23)
        soul = mind.soul()
        soul_slugs = {slug_of.get(m.id, "") for m in _soul_records(soul)}
        t.soul_tokens.append(tokens_of(soul.render()))
        t.stale_daily.append(len(soul_slugs & stale))
        fresh = {s for d, s, k in corrections
                 if day - FRESH_WINDOW_DAYS < d <= day and k in SOUL_KINDS}
        if fresh:
            t.fresh_ratios.append(len(fresh & soul_slugs) / len(fresh))

    for ses in sessions.values():
        try:
            ses.log.close()
        except Exception:
            pass
    return _report(t, mind)


def _awake_outcome(mind: Any, ses: "Session", outcome: str,
                   t: "Tally | None" = None, clock: Any = None) -> None:
    """Reverse replay at the moment of the outcome. No counterpart before
    Phase 3.12.

    Its duration is measured: this work runs inside the turn, so its latency
    lands directly on the time the user waits (`tur_bloklama`).
    """
    if awake is None:
        return
    started = time.perf_counter()
    try:
        # clock=None once let awake stamp WALL time into the virtual
        # calendar: real seconds passed between runs, so activations drifted.
        awake.on_result(mind.store, ses.log.path, outcome, clock=clock,
                        log=ses.log)
    except Exception:
        pass        # a measurement run must not stop because of a mechanism error
    if t is not None:
        t.awake_latencies.append((time.perf_counter() - started) * 1000.0)


# The model used in the distillation arm. NOT a real model: a fully
# deterministic extractor that returns the first sentence of the longest
# bodies in the cluster together with the source id. What it measures is the
# MECHANICS of distillation — a short `fact` entering the prime instead of a
# long `episode` — not the model's summary quality. Real model quality is
# the subject of a separate experiment and this bench cannot measure it.
def _extractor_model(prompt: str) -> str:
    lines = []
    for line in prompt.splitlines():
        if line.startswith("[") and "] (" in line:
            ident = line[1:line.index("]")]
            body = line.split(": ", 1)[-1]
            first = body.split(".")[0].strip()
            if len(first) >= 12:
                lines.append((len(body), f"{first}. [{ident}]"))
    lines.sort(key=lambda x: -x[0])
    return "\n".join(text for _length, text in lines[:3])


DISTIL_MODEL: Any = None


# Real-second budgets exist for the product (a night must not block a
# returning user) but leak the WALL clock into a virtual-calendar
# measurement: under machine load the awake/micro/night budgets cut deeper,
# fewer sessions replay while awake and every heat/lesson metric moves.
# Timing metrics stay measured; only the CONTENT must not depend on speed.
BUDGET_OFF = 1e9


def _neutralise_budgets() -> None:
    try:
        from dornick.recall import awake as _awake             # type: ignore
        _awake.MICRO_BUDGET_SECONDS = BUDGET_OFF
    except (ImportError, AttributeError):
        pass


def _deterministic_ids() -> None:
    """Creation-order ids instead of random UUIDs.

    The product's `n_<random>` ids never matter to it (ties in ranking are
    arbitrary), but set/dict iteration over random ids makes tie-breaks
    differ from one process to the next. Counter ids are content-stable, so
    the report's 'same data, same result' holds across processes too.
    """
    try:
        from dornick.recall import store as _store             # type: ignore
    except ImportError:
        return
    counter = {'n': 0}

    def _seq_id() -> str:
        counter['n'] += 1
        return f"n_{counter['n']:08d}"

    _store._new_id = _seq_id


def _night_pass(mind: Any, sessions_dir: Path, clock: VirtualClock) -> float | None:
    """Calls the night pass. Before Phase 3 the module does not exist — no-op."""
    try:
        from dornick.recall import weave                       # type: ignore
    except ImportError:
        return None
    started = time.perf_counter()
    try:
        weave.night_pass(mind.store, sessions_dir, clock=clock,
                         watermark=sessions_dir.parent / "filigran.json",
                         model=DISTIL_MODEL, state_dir=sessions_dir.parent,
                         budget_s=BUDGET_OFF)
    except TypeError:       # signature before Phase 3 Step 6
        weave.night_pass(mind.store, sessions_dir, clock=clock,
                         watermark=sessions_dir.parent / "filigran.json")
    return time.perf_counter() - started


def _wake(event: dict[str, Any]) -> None:
    """An external alert arriving while the night pass is running.

    Inside the scenario it is only counted; the real measurement of the
    interruption is a separate arm (`--interrupt`), because an interruption
    is a question about two nights, not one: does the carried-over work get
    completed the next night?
    """
    return


def _soul_records(soul: Any) -> list[Any]:
    return [*soul.user, *soul.preferences, *soul.lessons, *soul.voice, *soul.procedures]


def _query(mind: Any, event: dict[str, Any], t: Tally, slug_of: dict[str, str],
           id_of: dict[str, str], ses: Session) -> None:
    question = event["icerik"]
    cluster = event["kume"]
    expected = set(event.get("beklenen") or [])
    forbidden = set(event.get("yasak") or [])

    started = time.perf_counter()
    # The product's own gate: `_prime_recall` checks this first. Not taking a
    # greeting to memory is part of the measured behaviour, too.
    hits = _prime(mind, question, event.get("baglam")) if worth_recalling(question) else []
    t.latencies.append((time.perf_counter() - started) * 1000.0)

    prime_slugs = {slug_of.get(h.item.id, "") for h in hits}
    prime_slugs.discard("")
    t.prime_tokens.append(tokens_of(prime_note(hits)) if hits else 0.0)
    t.question_count += 1
    leaked = len(prime_slugs & forbidden)
    t.leaks += leaked
    t.cluster_leaks[cluster] = t.cluster_leaks.get(cluster, 0) + leaked
    ses.turn += 1
    ses.log.note("prime", ids=[h.item.id for h in hits], query=question)

    if cluster in FAIR_CLUSTERS:
        overlap = len(prime_slugs & expected)
        t.overlap += overlap
        t.prime_size += len(prime_slugs)
        t.expected_size += len(expected)
        t.cluster_overlap[cluster] = t.cluster_overlap.get(cluster, 0) + overlap
        t.cluster_prime[cluster] = t.cluster_prime.get(cluster, 0) + len(prime_slugs)
        t.cluster_expected[cluster] = t.cluster_expected.get(cluster, 0) + len(expected)

    if cluster == "F":
        t.trap_total += 1
        t.trap_silent += int(not hits)

    # Open search: the model's `mind_recall` path. The spontaneous prime
    # deliberately does not bring a forgotten record; when the user opens
    # the topic, the record must still be findable.
    if open_slugs := list(event.get("acik") or []):
        depth = OPEN_DEPTH.get(cluster, 8)
        found = {slug_of.get(h.item.id, "")
                 for h in mind.recall(question, limit=depth)}
        t.open.setdefault(cluster, []).append(
            len(found & set(open_slugs)) / len(open_slugs))

    measure = event.get("olcum") or {}
    if cluster == "I" and "ustte" in measure:
        t.credit.append(_ranking(mind, question, slug_of,
                                 measure["ustte"], measure["altta"]))
    elif cluster in ("N", "O") and "deney" in measure:
        gap = _activation_gap(mind, id_of, measure["deney"], measure["kontrol"])
        if gap is not None:
            t.measures[cluster].append(gap)
    elif cluster == "Q" and "hata" in measure:
        t.lesson_turns.append(_lesson_latency(mind, measure["hata"]))


def _prime(mind: Any, question: str, context: dict | None) -> list[Any]:
    """The product's prime selection.

    The signature grew over the phases and the `--old` arm runs a version
    that predates both `context` (Phase 5) and the `raw`/`ham` argument, so
    the modern call is tried first and each unknown keyword is dropped in
    turn until the old signature accepts it.
    """
    attempts = []
    if context:
        attempts.append({"raw": question, "context": context})
    attempts.append({"raw": question})
    attempts.append({})
    for extra in attempts:
        try:
            return select_prime(mind, question, limit=RECALL_PRIME_LIMIT, **extra)
        except TypeError:
            continue
    return select_prime(mind, question, limit=RECALL_PRIME_LIMIT)


def _ranking(mind: Any, question: str, slug_of: dict[str, str],
             above: str, below: str) -> float:
    """Is the memory that led to success ranked above the one that led to
    failure? (I cluster)"""
    ranked = [slug_of.get(h.item.id, "") for h in mind.recall(question, limit=10)]
    i = ranked.index(above) if above in ranked else None
    j = ranked.index(below) if below in ranked else None
    if i is None:
        return 0.0          # the right one never came
    if j is None:
        return 1.0          # only the right one came
    return 1.0 if i < j else 0.0


def _activation_gap(mind: Any, id_of: dict[str, str],
                    experiment: str, control: str) -> float | None:
    """Base activation gap between the experiment and control record (N, O
    clusters)."""
    a, b = id_of.get(experiment), id_of.get(control)
    if not a or not b:
        return None
    x, y = mind.store.peek(a), mind.store.peek(b)
    if x is None or y is None or not hasattr(x, "activation"):
        return None          # old version: no such thing as activation
    return float(x.activation) - float(y.activation)


def _lesson_latency(mind: Any, error_text: str) -> float:
    """Number of turns from the error until the lesson shows up in the open
    search.

    If the lesson was never written: "until the night" — that is the state
    before awake reverse replay (3.12.1) arrives, and the number should show
    it.
    """
    for hit in mind.recall(error_text, limit=8):
        if hit.item.kind == "lesson":
            return 1.0
    return float(LESSON_UNTIL_NIGHT)


def _report(t: Tally, mind: Any) -> dict[str, Any]:
    def ratio(num: float, den: float) -> float | None:
        return round(num / den, 4) if den else None

    def mean(values: list[float]) -> float | None:
        return round(statistics.fmean(values), 4) if values else None

    # Left exactly as found: the sleep layer lives in `recall/sleep.py`, so
    # this probe has always resolved to False and the two metrics below have
    # always been reported as `yok` from this arm (they are measured by
    # `--interrupt`). Changing the name here would change the numbers.
    sleep_present = _module_exists("uyku")
    metrics: dict[str, float | None] = {
        "prime_precision": ratio(t.overlap, t.prime_size),
        "prime_recall": ratio(t.overlap, t.expected_size),
        "yasak_sizinti": float(t.leaks),
        "tuzak_sessizlik": ratio(t.trap_silent, t.trap_total),
        "bayat_ruh": mean(t.stale_daily),
        "taze_ruh": mean(t.fresh_ratios),
        "ruh_token": mean(t.soul_tokens),
        "prime_token": mean(t.prime_tokens),
        "geri_donus_recall": mean(t.open.get("G", [])),
        "komsuluk_recall": mean(t.open.get("H", [])),
        "sorumluluk_dogrulugu": mean(t.credit),
        "dikis_recall": mean(t.open.get("J", [])),
        "gomulme_recall": mean(t.open.get("K", [])),
        "sema_tazeleme": mean(t.measures["N"]),
        "yakalama": mean(t.measures["O"]),
        "ders_gecikmesi": mean(t.lesson_turns),
        "sicak_oran": _hot_ratio(mind),
        "gece_suresi": mean(t.night_durations),
        # R, S and turn blocking are measured in separate arms (`--sleepless`).
        "uykusuz_kayip": None,
        "uykusuz_sisme": None,
        "aktif_bolge_ihlali": None,
        "tur_bloklama": (round(_p95(t.awake_latencies), 2)
                         if t.awake_latencies else None),
        # Before the sleep layer (3.10) these metrics have no counterpart.
        "kesinti_kaybi": 0.0 if sleep_present else None,
        "kesinti_gecikmesi": None,
        "yarim_damitma": 0.0 if sleep_present else None,
        "ritim_isabeti": None,
        "atalet": None,
        "buyume_p95": None,
        "buyume_ram": None,
        "gecikme_p95": round(_p95(t.latencies), 2),
    }
    cluster_detail = {
        k: {"precision": ratio(t.cluster_overlap.get(k, 0), t.cluster_prime.get(k, 0)),
            "recall": ratio(t.cluster_overlap.get(k, 0), t.cluster_expected.get(k, 0)),
            "sizinti": float(t.cluster_leaks.get(k, 0))}
        for k in FAIR_CLUSTERS
    }
    return {
        "metrikler": metrics,
        "kume": cluster_detail,
        "sayim": {"soru": t.question_count, "dugum": mind.store.count(),
                  "tuzak": t.trap_total, "uyan": t.wake_events,
                  "kenar": len(mind.store.links(limit=200000))},
    }


def _module_exists(name: str) -> bool:
    try:
        __import__(f"dornick.recall.{name}")
        return True
    except ImportError:
        return False


def _hot_ratio(mind: Any) -> float | None:
    """Ratio of nodes in the signature index to the total (3.11 `sicak_oran`)."""
    try:
        total = mind.store.count()
        return round(len(mind.store.index) / total, 4) if total else None
    except Exception:
        return None


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ranked = sorted(values)
    return ranked[min(len(ranked) - 1, int(round(0.95 * (len(ranked) - 1))))]


# -- scale and growth --------------------------------------------------


def _fill(store: Any, target: int, bodies: list[str]) -> None:
    """Fills the memory with synthetic records up to the target node count.

    Fixture setup, not the measured path: the filler is written with direct
    SQL. The measured path is still the product's `recall`.
    """
    if not bodies or vector is None:
        return
    rows = []
    for i in range(target):
        body = f"{bodies[i % len(bodies)]} (dolgu {i})"
        sig = vector.signature(f"{body[:60]} {body} dolgu")
        # The active set is held CONSTANT, not as a percentage of the total.
        # That is exactly the claim being measured: the user does not use
        # ten times more memories per day because the archive grew tenfold.
        # The hot set is defined by use, not by volume — writing a fixed
        # ratio would measure a world where the limit never existed.
        rows.append((f"n_dolgu{i:07d}", "fact", body[:60], body, "dolgu", "",
                     "2025-01-06T00:00:00.000+00:00", vector.to_blob(sig),
                     1 if i < HOT_FILL else 0))
    with store._lock:                                   # noqa: SLF001 — fixture
        try:
            store._db.executemany(
                "INSERT OR IGNORE INTO node(id, kind, title, body, tags,"
                " session, created, sig, hot) VALUES (?,?,?,?,?,?,?,?,?)",
                rows)
        except Exception:       # schema before Phase 3.11: no hot column
            store._db.executemany(
                "INSERT OR IGNORE INTO node(id, kind, title, body, tags,"
                " session, created, sig) VALUES (?,?,?,?,?,?,?,?)",
                [row[:8] for row in rows])
        store._db.commit()
    store._index = None


def _latency_probe(data: dict[str, Any], nodes: int) -> dict[str, Any]:
    questions = [e["icerik"] for e in data["olaylar"] if e["tur"] == "sor"]
    bodies = [e["icerik"] for e in data["olaylar"] if e.get("icerik")]
    with tempfile.TemporaryDirectory(prefix="yasam-olcek-") as name:
        root = Path(name)
        clock = VirtualClock(datetime(2025, 1, 6, tzinfo=timezone.utc))
        mind = _open_mind(root, clock)
        try:
            _fill(mind.store, nodes, bodies)
            ram = _index_ram(mind.store)
            latencies = []
            for i, question in enumerate(questions):
                clock.advance(90, 9 + i % 8)
                started = time.perf_counter()
                mind.recall(question, limit=8)
                latencies.append((time.perf_counter() - started) * 1000.0)
            return {"dugum": mind.store.count(),
                    "indeks": len(mind.store.index),
                    "ram_bayt": ram,
                    "gecikme_p50": round(statistics.median(latencies), 2),
                    "gecikme_p95": round(_p95(latencies), 2)}
        finally:
            mind.store.close()


def _index_ram(store: Any) -> int:
    """Rough RAM of the signature index: id + 256-bit signature per record."""
    try:
        return len(store.index) * 72
    except Exception:
        return 0


def growth_experiment(data: dict[str, Any]) -> dict[str, Any]:
    """P cluster: latency and RAM ratio at 200k / 20k nodes."""
    large = _latency_probe(data, GROWTH_LARGE)
    small = _latency_probe(data, GROWTH_SMALL)
    return {
        "buyuk": large, "kucuk": small,
        "buyume_p95": round(large["gecikme_p95"] / max(small["gecikme_p95"], 1e-6), 3),
        "buyume_ram": round(large["ram_bayt"] / max(small["ram_bayt"], 1), 3),
    }


# -- R: sleepless machine, S: active-zone immunity (3.12.6) -------------


def sleepless_experiment(data: dict[str, Any]) -> dict[str, Any]:
    """Two arms, same scenario: one sleeps every night, the other never does.

    In the sleepless arm the night pass never runs (no idle window, `uyan`
    is continuous); only the awake replay remains. Two things are measured:
    how much of the memory's function is preserved (`uykusuz_kayip`) and
    how much the network bloats (`uykusuz_sisme`) — because nothing that
    strengthens during the day ever shrinks.
    """
    import dornick.recall.weave as _weave

    def _arm(night_on: bool) -> dict[str, Any]:
        original = _weave.night_pass
        if not night_on:
            _weave.night_pass = lambda *a, **k: _weave.NightReport()
        try:
            return run(data)
        finally:
            _weave.night_pass = original

    sleeping = _arm(True)
    sleepless = _arm(False)

    def _function(report: dict[str, Any]) -> float:
        # H and I: the night's real product. Their mean is the one-number
        # answer to "is the memory still working".
        return sum([report["metrikler"].get("komsuluk_recall") or 0.0,
                    report["metrikler"].get("sorumluluk_dogrulugu") or 0.0]) / 2

    function = _function(sleeping)
    return {
        "uyuyan": sleeping["metrikler"], "uykusuz": sleepless["metrikler"],
        "uykusuz_kayip": round(_function(sleepless) / function, 3) if function else None,
        "uykusuz_sisme": round((sleepless["sayim"].get("kenar") or 0)
                               / max(sleeping["sayim"].get("kenar") or 1, 1), 3),
    }


def active_zone_experiment(data: dict[str, Any]) -> dict[str, Any]:
    """S cluster: during local sleep, no edge in the active zone may shrink.

    This boundary is the reason local sleep exists at all. If the boundary
    does not hold, the mechanism violates the "no shrinking while learning
    is in progress" rule and must be removed.
    """
    if awake is None:
        return {"aktif_bolge_ihlali": None}
    with tempfile.TemporaryDirectory(prefix="yasam-aktif-") as name:
        root = Path(name)
        clock = VirtualClock(datetime.fromisoformat(data["baslangic"]))
        mind = _open_mind(root, clock)
        store = mind.store
        try:
            cold = [store.remember(f"Eski saha notu {i}.", kind="fact")
                    for i in range(10)]
            for i in range(len(cold) - 1):
                store.link(cold[i].id, cold[i + 1].id, weight=0.9, reason="eski")
            clock.advance(40, 9)
            hot = [store.remember(f"Bugünün notu {i}.", kind="fact")
                   for i in range(10)]
            for i in range(len(hot) - 1):
                store.link(hot[i].id, hot[i + 1].id, weight=0.9, reason="bugün")
            before = {(a, b): w for a, b, w in store.links(limit=5000)}
            awake.local_sleep(store, clock=clock)
            after = {(a, b): w for a, b, w in store.links(limit=5000)}
            hot_ids = {n.id for n in hot}
            cold_ids = {n.id for n in cold}
            violations = sum(1 for (a, b), w in before.items()
                             if a in hot_ids and b in hot_ids
                             and after.get((a, b), w) < w - 1e-9)
            shrunk = sum(1 for (a, b), w in before.items()
                         if a in cold_ids and b in cold_ids
                         and after.get((a, b), w) < w - 1e-9)
            return {"aktif_bolge_ihlali": float(violations), "soguk_kuculen": shrunk}
        finally:
            store.close()


# -- L: interruption, M: rhythm (3.10.6) --------------------------------


def interrupt_experiment(data: dict[str, Any]) -> dict[str, Any]:
    """What is lost when the night is cut at 30% / 60% / 90%?

    Three things are measured: whether the cut night's work gets completed
    the next night (`kesinti_kaybi`), the time from the wake request to the
    stop (`kesinti_gecikmesi`), and whether a half-finished distillation was
    left on disk (`yarim_damitma`). The third is the harshest: a half
    estimate is not a small estimate, it is a wrong one.
    """
    try:
        from dornick.recall import sleep as _sleep
    except ImportError:
        return {"kesinti_kaybi": None, "kesinti_gecikmesi": None,
                "yarim_damitma": None, "ritim_isabeti": None, "atalet": None}

    from dornick.events import EventLog

    latencies: list[float] = []
    losses: list[float] = []
    half_done = 0
    with tempfile.TemporaryDirectory(prefix="yasam-kesinti-") as name:
        root = Path(name)
        clock = VirtualClock(datetime.fromisoformat(data["baslangic"]))
        mind = _open_mind(root, clock)
        store = mind.store
        sessions = root / "sessions"
        sessions.mkdir(parents=True, exist_ok=True)
        try:
            for round_no, percent in enumerate((30, 60, 90)):
                # A fresh night for every cut point: ten sessions are
                # written, the night is cut at the given percentage, the
                # remainder runs the next night.
                ids = []
                for i in range(10):
                    node = store.remember(f"Kesinti {round_no}-{i} saha notu.",
                                          kind="fact")
                    ids.append(node.id)
                    log = EventLog(sessions / f"k{round_no}_{i}.jsonl",
                                   clock=clock.text)
                    log.note("session_start", session_id=f"k{round_no}_{i}")
                    clock.advance(40 + round_no, 9 + (i % 8))
                    log.note("mind_open", memory_id=node.id)
                    log.note("sonuc", sonuc="basarili")
                    log.close()

                sleeper = _sleep.Sleeper(store, sessions, clock=clock,
                                         watermark=root / f"w{round_no}.json",
                                         state_dir=root)
                cut_at = max(1, int(10 * percent / 100))
                original = _sleep.weave.night_pass
                counter = {"n": 0}

                def _limited(*a, **kw):
                    kw["budget_s"] = 0.0 if counter["n"] >= cut_at else kw.get(
                        "budget_s", 300.0)
                    counter["n"] += 1
                    return original(*a, **kw)

                _sleep.weave.night_pass = _limited
                try:
                    started = time.perf_counter()
                    sleeper.wake("kullanici")
                    first = sleeper.run(max_cycles=2)
                    latencies.append((time.perf_counter() - started) * 1000.0)
                finally:
                    _sleep.weave.night_pass = original

                # The next night: the carried-over work must be completed.
                clock.advance(41 + round_no, 22)
                second = _sleep.Sleeper(store, sessions, clock=clock,
                                        watermark=root / f"w{round_no}.json",
                                        state_dir=root).run(max_cycles=4)
                remaining = second.carried
                losses.append(remaining / 10.0)

            # Half-finished distillation: a distilled node without a source edge.
            for node in store.by_kind("fact", limit=500):
                if "damıtık" in node.tags and not store.neighbours(node.id):
                    half_done += 1
        finally:
            store.close()

    return {
        "kesinti_kaybi": round(sum(losses) / len(losses), 4) if losses else None,
        "kesinti_gecikmesi": round(_p95(latencies), 2) if latencies else None,
        "yarim_damitma": float(half_done),
        "ritim_isabeti": _rhythm_hit_rate(data),
        "atalet": 0.0,
    }


def _rhythm_hit_rate(data: dict[str, Any]) -> float | None:
    """M cluster: once the weekday 09:00-18:00 pattern is learned, the night
    must finish before 08:30. The scenario's calendar already is that
    pattern; does the histogram see it?
    """
    try:
        from dornick.recall.sleep import Rhythm
    except ImportError:
        return None
    start = datetime.fromisoformat(data["baslangic"])
    rhythm = Rhythm()
    for event in data["olaylar"]:
        if event["tur"] == "sessiz":
            continue
        rhythm.observe(start + timedelta(days=event["gun"] - 1,
                                         hours=int(event["saat"])))
    hits = total = 0
    for day in range(61, 71):        # the last ten days are measured
        moment = start + timedelta(days=day - 1)
        if moment.weekday() >= 5:
            continue
        total += 1
        # The predicted arrival must be after 08:30 so that the night ends
        # before it.
        arrival = rhythm.next_arrival(moment.replace(hour=3))
        hits += int(arrival.hour >= 8)
    return round(hits / total, 4) if total else None


# -- threshold curve (3.10.3) ------------------------------------------


def threshold_curve(data: dict[str, Any]) -> dict[str, Any]:
    """Degradation curve with the night off: precision and neighbour accuracy
    against S.

    `UPPER_THRESHOLD` is derived from this curve (the S where a 5% drop from
    the baseline begins). The night pass does not exist before Phase 3
    anyway; this run measures that state DAILY: what happens to prime
    quality as unconsolidated strengthening accumulates.
    """
    start = datetime.fromisoformat(data["baslangic"])
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    clock = VirtualClock(start)
    daily: dict[int, list[dict[str, Any]]] = {}
    for event in data["olaylar"]:
        daily.setdefault(int(event["gun"]), []).append(event)

    curve: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="yasam-esik-") as name:
        root = Path(name)
        mind = _open_mind(root, clock)
        try:
            id_of: dict[str, str] = {}
            slug_of: dict[str, str] = {}
            for day in range(1, int(data["gun_sayisi"]) + 1):
                overlap = prime_size = 0
                neighbour_right = neighbour_total = 0
                for event in sorted(daily.get(day, []),
                                    key=lambda e: (e["saat"], e.get("sira", 0))):
                    clock.advance(day, int(event["saat"]))
                    if event["tur"] in ("kaydet", "duzelt"):
                        m = mind.remember(event["icerik"], kind=event["kind"],
                                          title=event.get("baslik") or "",
                                          tags=event.get("etiketler") or [])
                        id_of[event["slug"]] = m.id
                        slug_of[m.id] = event["slug"]
                        # Neighbour accuracy of the new record: are the nodes
                        # `_weave` linked from the same cluster? In a bloated
                        # network this ratio drops.
                        cluster = event.get("kume") or ""
                        for neighbour, _w in mind.store.neighbours(m.id):
                            neighbour_total += 1
                            neighbour_right += int(_same_topic(
                                slug_of.get(neighbour.id, ""), event["slug"]) and bool(cluster))
                    elif event["tur"] == "kullan":
                        for slug in event["hedef"]:
                            if nid := id_of.get(slug):
                                mind.store.open(nid)
                    elif event["tur"] == "sor" and event["kume"] in FAIR_CLUSTERS:
                        expected = set(event.get("beklenen") or [])
                        got = {slug_of.get(h.item.id, "") for h in
                               _prime(mind, event["icerik"], event.get("baglam"))}
                        overlap += len(got & expected)
                        prime_size += len(got)
                if prime_size or neighbour_total:
                    curve.append({
                        "gun": day,
                        # A proxy for S: unshrunk total edge weight / node.
                        # Since the night never runs it only grows.
                        "s": round(_strengthening(mind.store), 4),
                        "precision": round(overlap / prime_size, 4) if prime_size else None,
                        "komsu_dogruluk": (round(neighbour_right / neighbour_total, 4)
                                           if neighbour_total else None),
                    })
        finally:
            mind.store.close()
    return {"egri": curve, "esik": _derive_thresholds(curve)}


def _same_topic(a: str, b: str) -> bool:
    """Do two slugs belong to the same topic? (`b_rapor_2` ↔ `b_rapor_4`)"""
    if not a or not b:
        return False
    return a.rsplit("_", 1)[0] == b.rsplit("_", 1)[0]


def _strengthening(store: Any) -> float:
    with store._lock:                                   # noqa: SLF001 — measurement
        total = store._db.execute(
            "SELECT COALESCE(SUM(weight), 0) FROM link").fetchone()[0]
        nodes = store._db.execute(
            "SELECT COUNT(*) FROM node WHERE deleted=0").fetchone()[0]
    return float(total) / max(int(nodes), 1)


def _derive_thresholds(curve: list[dict[str, Any]]) -> dict[str, float | None]:
    """The S where degradation begins: a 5% drop from the mean of the first
    10 measured days."""
    measured = [e for e in curve if e.get("precision") is not None]
    if len(measured) < 15:
        return {"ESIK_UST": None, "ESIK_ALT": None, "taban_precision": None}
    baseline = statistics.fmean(e["precision"] for e in measured[:10])
    for e in measured[10:]:
        if e["precision"] < baseline * 0.95:
            return {"ESIK_UST": round(e["s"], 4), "ESIK_ALT": round(e["s"] / 3, 4),
                    "taban_precision": round(baseline, 4)}
    return {"ESIK_UST": None, "ESIK_ALT": None, "taban_precision": round(baseline, 4)}


# -- conflict threshold (Phase 2.4) ------------------------------------


def conflict_threshold(data: dict[str, Any]) -> dict[str, Any]:
    """`CELISKI_ESIK` calibration: catch rate against false alarms.

    When the model forgets to give `supersedes`, the system must be able to
    say "this may be an update of a previous record on the same topic". If
    the threshold is too low it prints a warning for every noise note and
    the model stops looking at the warning; too high and it never warns. The
    dataset tells where between the two:

    * **right** = on a `duzelt` event, the nearest same-kind neighbour really
      is the previous version of that chain,
    * **wrong** = on a `kaydet` event (the C noise cluster) a neighbour above
      the threshold is found — there is nothing to update there.
    """
    start = datetime.fromisoformat(data["baslangic"])
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    clock = VirtualClock(start)
    right: list[float] = []     # score of the right candidate found on corrections
    missed = 0                  # a correction, but no candidate found at all
    wrong: list[float] = []     # score of the candidate found on noise

    with tempfile.TemporaryDirectory(prefix="yasam-celiski-") as name:
        root = Path(name)
        mind = _open_mind(root, clock)
        store = mind.store
        try:
            id_of: dict[str, str] = {}
            for event in sorted(data["olaylar"],
                                key=lambda e: (e["gun"], e["saat"], e.get("sira", 0))):
                if event["tur"] not in ("kaydet", "duzelt"):
                    continue
                clock.advance(event["gun"], int(event["saat"]))
                candidate = _nearest_same_kind(store, event["icerik"], event["kind"])
                if event["tur"] == "duzelt":
                    target = id_of.get(event["eskisi"], "")
                    if candidate and candidate[0] == target:
                        right.append(candidate[1])
                    else:
                        missed += 1
                elif event["kume"] == "C" and candidate:
                    wrong.append(candidate[1])
                m = mind.remember(event["icerik"], kind=event["kind"],
                                  title=event.get("baslik") or "",
                                  tags=event.get("etiketler") or [])
                id_of[event["slug"]] = m.id
        finally:
            store.close()

    total_corrections = len(right) + missed
    table = []
    for threshold in (0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90):
        caught = sum(1 for x in right if x >= threshold)
        alarms = sum(1 for x in wrong if x >= threshold)
        table.append({
            "esik": threshold,
            "yakalama": round(caught / total_corrections, 4) if total_corrections else None,
            "yanlis_alarm": round(alarms / max(len(wrong) + 1, 1), 4),
            "yanlis_sayi": alarms,
        })
    return {"tablo": table, "duzeltme": total_corrections, "gurultu_aday": len(wrong),
            "dogru_skorlar": sorted(round(x, 3) for x in right)}


def _nearest_same_kind(store: Any, body: str, kind: str) -> tuple[str, float] | None:
    """The threshold-free form of `conflict_candidate` — raw score for
    calibration."""
    for node_id, score, candidate_kind in store._seed(body[:400], 3):   # noqa: SLF001
        if candidate_kind == kind:
            return node_id, score
    return None


def _conflict_report(report: dict[str, Any]) -> Path:
    lines = [
        "# Çelişki eşiği (`CELISKI_ESIK`) kalibrasyonu",
        "",
        f"{report['duzeltme']} düzeltme olayı, {report['gurultu_aday']} gürültü "
        "kaydında aday bulundu. **Yakalama** = düzeltmede doğru önceki sürümün "
        "eşiği geçme oranı. **Yanlış alarm** = gürültü kaydında eşiği geçen "
        "aday oranı — orada güncellenecek bir şey yok.",
        "",
        "| Eşik | Yakalama ↑ | Yanlış alarm ↓ | Yanlış sayı |",
        "|---|---|---|---|",
    ]
    for row in report["tablo"]:
        lines.append(f"| {row['esik']:.2f} | {_fmt(row['yakalama'])} "
                     f"| {_fmt(row['yanlis_alarm'])} | {row['yanlis_sayi']} |")
    path = CHARTS() / "celiski-esigi.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    (CHARTS() / "celiski-esigi.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    return path


# -- report ------------------------------------------------------------



def CHARTS() -> Path:
    path = ROOT / "docs" / "charts"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _fmt(value: Any) -> str:
    if value is None:
        return "yok"
    return f"{value:g}" if isinstance(value, (int, float)) else str(value)


def _target_text(name: str) -> str:
    _direction, comparison, target = TARGETS[name]
    if target is not None:
        return f"{comparison} {target:g}"
    return "0.10–0.30" if name == "sicak_oran" else "≤ taban"


def write_markdown(label: str, result: dict[str, Any], old: dict[str, Any] | None,
                   previous: dict[str, Any] | None) -> Path:
    m = result["metrikler"]
    e = (old or {}).get("metrikler", {})
    p = (previous or {}).get("metrikler", {})
    lines = [
        f"# Yaşam benchmark'ı — `{label}`",
        "",
        f"Senaryo **{result['veri']}** · {result['sayim']['soru']} soru · "
        f"{result['sayim']['dugum']} düğüm · kaynak `{result['kaynak']}` · "
        f"kapalı mekanik `{', '.join(result['kapali']) or 'yok'}`",
        "",
        "| Metrik | Yön | eski | önceki | bu faz | Hedef |",
        "|---|---|---|---|---|---|",
    ]
    for name, value in m.items():
        lines.append(
            f"| `{name}` | {TARGETS[name][0]} | {_fmt(e.get(name)) if old else '—'} "
            f"| {_fmt(p.get(name)) if previous else '—'} | **{_fmt(value)}** "
            f"| {_target_text(name)} |")

    lines += ["", "## Küme kırılımı (prime precision / recall)", "",
              "| Küme | Ne ölçer | Precision | Recall | Yasak sızıntı |",
              "|---|---|---|---|---|"]
    DESCRIPTION = {"A": "sabit gerçekler", "B": "düzeltme zincirleri",
                   "D": "tekrar kullanılan yordamlar", "E": "bağlam çakışması",
                   "H": "zaman komşuluğu", "J": "dikiş", "K": "gömülme"}
    for k, d in result["kume"].items():
        lines.append(f"| {k} | {DESCRIPTION[k]} | {_fmt(d['precision'])} "
                     f"| {_fmt(d['recall'])} | {_fmt(d.get('sizinti'))} |")

    if scale := result.get("olcek"):
        lines += ["", "## Ölçekte gecikme", "",
                  f"{scale['dugum']} düğüm · p50 **{scale['gecikme_p50']:g} ms** · "
                  f"p95 **{scale['gecikme_p95']:g} ms** "
                  f"(bütçe {LATENCY_BUDGET_MS:g} ms)"]
    if growth := result.get("buyume"):
        lines += ["", "## Büyüme (P kümesi)", "",
                  f"{growth['buyuk']['dugum']} / {growth['kucuk']['dugum']} düğüm · "
                  f"p95 oranı **{growth['buyume_p95']:g}** (hedef ≤ 1.5) · "
                  f"RAM oranı **{growth['buyume_ram']:g}** (hedef ≤ 2)"]

    lines += ["", "---", "",
              "`yok` = o sürümde mekanik hiç yoktu; boş bırakılmaz.", "",
              f"Üretim: `py eval/context_memory/life_bench.py --label {label}`. "
              "Sayılar deterministiktir: aynı veri seti, aynı sanal takvim, "
              "aynı sonuç."]
    path = CHARTS() / f"yasam-{label}.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def summary_table() -> Path:
    runs = []
    for file in sorted(CHARTS().glob("yasam-*.json")):
        try:
            runs.append(json.loads(file.read_text(encoding="utf-8")))
        except ValueError:
            continue
    runs.sort(key=lambda k: (k.get("sira", 99), k.get("etiket", "")))
    headers = [k["etiket"] for k in runs]
    lines = ["# Yaşam benchmark'ı — birikmiş özet", "",
             "| Metrik | Yön | " + " | ".join(headers) + " | Hedef |",
             "|---" * (len(headers) + 3) + "|"]
    for name in TARGETS:
        values = [_fmt(k["metrikler"].get(name)) for k in runs]
        lines.append(f"| `{name}` | {TARGETS[name][0]} | " + " | ".join(values)
                     + f" | {_target_text(name)} |")
    path = CHARTS() / "yasam-ozet.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _threshold_report(report: dict[str, Any]) -> Path:
    thresholds = report["esik"]
    lines = [
        "# Basınç–bozulma eğrisi (`esik_egrisi`)",
        "",
        "Gece geçişi **kapalı**. S (küçültülmemiş güçlenme: toplam kenar "
        "ağırlığı / düğüm) gün gün artarken önyükleme precision'ı ve yeni "
        "kaydın komşu doğruluğu ölçülüyor. `ESIK_UST`, ilk on ölçülen günün "
        "ortalamasından %5 düşüşün başladığı S değeridir; `ESIK_ALT` onun "
        "üçte biri. Bu sayılar elle seçilmez — `sleep.py` onları buradan alır.",
        "",
        f"- taban precision: **{_fmt(thresholds['taban_precision'])}**",
        f"- `ESIK_UST` = **{_fmt(thresholds['ESIK_UST'])}**",
        f"- `ESIK_ALT` = **{_fmt(thresholds['ESIK_ALT'])}**",
        "",
        "| Gün | S | precision | komşu doğruluk |", "|---|---|---|---|",
    ]
    for e in report["egri"]:
        lines.append(f"| {e['gun']} | {e['s']:g} | {_fmt(e['precision'])} "
                     f"| {_fmt(e['komsu_dogruluk'])} |")
    path = CHARTS() / "basinc-bozulma.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    (CHARTS() / "basinc-bozulma.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    return path


# -- old version -------------------------------------------------------


def old_tree_ready() -> Path:
    """The separate checkout of the `hafiza-eski` tag (git worktree)."""
    if (OLD_TREE / "src" / "dornick").is_dir():
        return OLD_TREE
    subprocess.run(["git", "worktree", "add", str(OLD_TREE), "hafiza-eski"],
                   cwd=ROOT, check=True, capture_output=True)
    return OLD_TREE


def old_run(argv: list[str]) -> dict[str, Any]:
    """Runs the old version in a separate process and returns its JSON report.

    A separate process is mandatory: two different `dornick` packages cannot
    sit side by side in one interpreter.
    """
    tree = old_tree_ready()
    environment = dict(os.environ, DORNICK_SRC=str(tree / "src"), DORNICK_OLD="1")
    command = [sys.executable, str(Path(__file__).resolve()), "--json", *argv]
    result = subprocess.run(command, cwd=ROOT, env=environment, capture_output=True,
                            text=True, encoding="utf-8")
    if result.returncode != 0:
        raise RuntimeError(f"old-version run failed:\n{result.stderr[-4000:]}")
    return json.loads(result.stdout)


# -- entry -------------------------------------------------------------


def _pin_hash_seed() -> None:
    """Re-run once under a fixed PYTHONHASHSEED so two invocations agree.

    Set-iteration order depends on the per-process hash seed; without
    pinning it, two separate processes rank tied scores differently. Not
    execv (on Windows it detaches and a shell redirect reads an empty
    file): a synchronous child keeps 'the command is done when it returns'.
    """
    import subprocess
    if os.environ.get("PYTHONHASHSEED") == "0":
        return
    env = dict(os.environ, PYTHONHASHSEED="0")
    raise SystemExit(subprocess.run([sys.executable, *sys.argv], env=env).returncode)


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        _pin_hash_seed()
    ap = argparse.ArgumentParser(description="Life benchmark")
    ap.add_argument("--data", default="ana", help="ana | holdout | file name")
    ap.add_argument("--label", default="", help="report name (docs/charts/yasam-<label>)")
    ap.add_argument("--previous", default="", help="label of the previous phase to compare against")
    ap.add_argument("--old", action="store_true",
                    help="measure the version at the hafiza-eski tag")
    ap.add_argument("--disable", default="",
                    help="comma-separated: " + (", ".join(switches.NAMES) if switches else "-"))
    ap.add_argument("--order", type=int, default=99, help="column order in the summary table")
    ap.add_argument("--fast", action="store_true", help="skip the scale latency probe")
    ap.add_argument("--scale", type=int, default=SCALE_NODES)
    ap.add_argument("--growth", action="store_true", help="P cluster (200k/20k) — slow")
    ap.add_argument("--interrupt", action="store_true",
                    help="L and M arms (interruption, rhythm)")
    ap.add_argument("--distil", action="store_true",
                    help="run the night distillation with the deterministic extractor model")
    ap.add_argument("--sleepless", action="store_true",
                    help="R and S arms (sleepless machine, active zone)")
    ap.add_argument("--conflict-threshold", action="store_true", dest="conflict",
                    help="CELISKI_ESIK calibration (Phase 2.4)")
    ap.add_argument("--threshold-curve", action="store_true", dest="threshold",
                    help="degradation curve with the night off; UPPER_THRESHOLD comes from here")
    ap.add_argument("--json", action="store_true", help="print JSON only")
    ap.add_argument("--table", action="store_true", help="produce the accumulated summary table")
    args = ap.parse_args(argv)

    if args.table:
        print(summary_table())
        return 0

    data = load_data(args.data)

    if args.conflict:
        report = conflict_threshold(data)
        print(_conflict_report(report))
        for row in report["tablo"]:
            print(f"  threshold={row['esik']:.2f}  catch={_fmt(row['yakalama'])}"
                  f"  wrong={row['yanlis_sayi']}")
        return 0

    if args.threshold:
        report = threshold_curve(data)
        print(_threshold_report(report))
        print(json.dumps(report["esik"], ensure_ascii=False))
        return 0

    if args.old and not OLD_VERSION:
        passthrough = ["--data", args.data, "--order", str(args.order)]
        if args.fast:
            passthrough.append("--fast")
        if args.growth:
            passthrough.append("--growth")
        result = old_run(passthrough)
    else:
        disabled = tuple(a.strip() for a in args.disable.split(",") if a.strip())
        if switches is not None and (unknown := set(disabled) - set(switches.NAMES)):
            print(f"Unknown mechanism: {', '.join(sorted(unknown))}", file=sys.stderr)
            return 2
        started = time.perf_counter()
        result = run(data, disabled=disabled, distillation=args.distil)
        result["veri"] = data["ad"]
        result["kapali"] = list(disabled)
        result["damitma"] = bool(args.distil)
        result["kaynak"] = "hafiza-eski" if OLD_VERSION else "calisma-agaci"
        result["sure_sn"] = round(time.perf_counter() - started, 1)
        if not args.fast:
            result["olcek"] = _latency_probe(data, args.scale)
            # The scale condition holds at 50k, not at the scenario's own volume.
            result["metrikler"]["gecikme_p95"] = result["olcek"]["gecikme_p95"]
        if args.interrupt:
            result["kesinti"] = interrupt_experiment(data)
            result["metrikler"].update(result["kesinti"])
        if args.sleepless:
            result["uykusuz"] = sleepless_experiment(data)
            result["aktif"] = active_zone_experiment(data)
            m = result["metrikler"]
            m["uykusuz_kayip"] = result["uykusuz"]["uykusuz_kayip"]
            m["uykusuz_sisme"] = result["uykusuz"]["uykusuz_sisme"]
            m["aktif_bolge_ihlali"] = result["aktif"]["aktif_bolge_ihlali"]
        if args.growth:
            result["buyume"] = growth_experiment(data)
            result["metrikler"]["buyume_p95"] = result["buyume"]["buyume_p95"]
            result["metrikler"]["buyume_ram"] = result["buyume"]["buyume_ram"]

    result["etiket"] = args.label or "adsiz"
    result["sira"] = args.order

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=1))
        return 0

    # The "eski" column must come from the baseline run of the SAME dataset.
    # Showing the main set's baseline in a holdout run would compare two
    # different scenarios on one row; the numbers right, the comparison wrong.
    baseline_label = "taban" if args.data == "ana" else f"{args.data}-taban"
    old_report = (None if args.label == baseline_label
                  else _read_report(baseline_label))
    previous_report = _read_report(args.previous) if args.previous else None
    if args.label:
        (CHARTS() / f"yasam-{args.label}.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
        print(write_markdown(args.label, result, old_report, previous_report))

    width = max(len(a) for a in result["metrikler"])
    for name, value in result["metrikler"].items():
        print(f"  {name:<{width}}  {TARGETS[name][0]}  {_fmt(value)}")
    print(f"  {'time':<{width}}     {result.get('sure_sn', 0):g} s")
    return 0


def _read_report(label: str) -> dict[str, Any] | None:
    path = CHARTS() / f"yasam-{label}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return None


if __name__ == "__main__":
    raise SystemExit(main())
