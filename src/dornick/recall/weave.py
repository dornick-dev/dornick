"""Night pass — replaying the day's sequences.

Until now night school did *training*: it fine-tuned the base writer on the
personal corpus. It did no *replay*. Yet the real work the brain does at
night is replaying the day's sequences (sharp-wave ripple), and none of
what falls out of that existed in dornick:

1. Every edge was "similar content" — there was no **experienced together**
   bond. "What was the thing I used while doing that report last week"
   cannot be found by a content search; that question is a temporal one.
2. The `uses` counter makes no distinction: the memory that led to the
   wrong answer and the one that led to the right answer each get one
   point. There is no **credit assignment**.
3. Replay has no priority: the trigger is "have 25 new memories piled up".
   A failed session, an open goal, a correction round get the same
   treatment as a routine session.
4. `_weave` freezes at write time; the graph depends on write order, early
   records stay weakly linked.
5. Nothing that strengthens by day ever shrinks. Edges bloat, `_weave`
   neighbours turn to noise.

There are six steps and **the first five need no model** — pure Python +
SQLite. Even an installation without a model does meaningful work at
night; distillation (step 6) runs only when a local model is present.

The atomic unit is the replay of a single session: when the budget runs
out the remainder is not skipped, it **carries over** to the next night.
The watermark is kept per session, so a night cut short loses no work and
a completed session never pays out credit a second time.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Iterable

from . import activation, switches
from .clock import Clock, parse, wall_clock

# Step 1 — Mattar-Daw: gain × need. Failed and corrected sessions are the
# ones that teach the most; there is little to learn from a routine session.
GAIN = {"basarisiz": 1.0, "duzeltildi": 1.0, "acik": 0.7,
          "basarili": 0.4, "rutin": 0.1}

# The bound for counting as routine: no tool error, no goal, no correction
# and at most this many turns.
ROUTINE_KIND = 3

# Replay window: sessions closed since the watermark are always candidates.
# Sessions from the previous this-many days are candidates too, but their
# priority halves per day and they only get a turn if the budget grows.
# Anything older is not scanned — the old is consolidated by schema refresh,
# not by scanning.
LOOKBACK_DAYS = 7
LOOKBACK_DECAY = 0.5

# Step 2 — temporal adjacency window and weight. Neighbour 0.6, two away 0.42.
WINDOW = 4
ADJACENCY_WEIGHT = 0.6
ADJACENCY_DECAY = 0.7

# Step 2b — the refresh share a schema-linked neighbour receives. One jump;
# the rest is left to Phase 1 decay.
SCHEMA_SHARE = 0.15

# Step 3 — credit shares. Whatever is close to the outcome takes the most.
# Calibration (life bench, 2026-09-03): (0.5, -0.3) / (0.7, -0.5) /
# (0.5, -0.6) / (1.0, -0.8) were scanned. `sorumluluk_dogrulugu` clears the
# target only with the last pair: 0.75 → 1.00. The (0.5, -0.3) pair the
# roadmap suggested is far too weak — a single success/failure share stays
# below the record's own freshness and cannot flip the ranking. The other
# metrics are insensitive in this range (precision 0.2758–0.2773).
SHARE_DECAY = 0.8
SUCCESS_SHARE = 1.0
FAILURE_SHARE = -0.8

# Step 1 — retroactive capture (synaptic tagging and capture): the ordinary
# records within ±60 minutes of a high-surprise event get consolidated too.
# The weak trace survives because it stood next to the strong event.
#
# Calibration was TRIED and stayed INCONCLUSIVE (life bench, 2026-09-03):
# scanning the threshold from 0.35 to 0.70 did not move the `yakalama`
# metric at all (-0.108 constant). The cause was measured: in a memory of
# five hundred nodes the surprise of "morning coffee was drunk" is 0.389,
# that of "main panel burned out, the site lost power" is 0.422. The
# surprise proxy (1 − nearest-neighbour score) cannot tell the ordinary from
# the catastrophic at this scale; the threshold of a signal that cannot
# discriminate cannot be tuned either. The roadmap's initial value was kept
# and the finding was written into the report — Phase 4's encoding strength
# rests on the same proxy and is expected to hit the same wall.
CAPTURE_THRESHOLD = 0.7
CAPTURE_MINUTES = 60
CAPTURE_SHARE = 0.3

# Step 5a — reweaving: how many candidates are pulled and how many linked.
WEAVE_CANDIDATES = 6
WEAVE_LINKS = 3

# Step 5b — synaptic homeostasis (Tononi-Cirelli): everything that
# strengthens by day shrinks proportionally at night. An untouched edge
# melts by this ratio every night; at 2% it halves in ~35 nights and reaches
# the floor in ~150. Edges strengthened tonight grew before the shrink, so
# they come out with a net gain.
# Calibration: docs/hafiza-fazlar.md "Faz 3 kalibrasyonu".
EPSILON = 0.02
EDGE_FLOOR = 0.05

# Phase 3.11 — the hot/cold boundary. A record below this activation (and
# older than seven days) drops out of the signature index: it no longer
# comes up on its own but is still found by an exact word.
#
# The roadmap gives the calibration target not as a number but as a RATIO:
# in the ninety-day scenario the hot share must stay between 10-30%. Scan
# (2026-09-03): -2.0 → 2.9% · -3.0 → 4.5% · -4.0 → 6.5% · **-5.0 → 25.2%** ·
# -6.0 → 69% · -7.0 → 98.5%. The only value that lands in the band is -5.0.
# The side effect was measured and is the expected one: because a cold
# record cannot enter the prime, trap silence rises 0.45 → 0.525 and prime
# recall drops 0.99 → 0.75. The latter is the direct consequence of what the
# mechanism is for, not a flaw in it.
COLD_THRESHOLD = -5.0


@dataclass(slots=True)
class ReplaySession:
    """A session's summary as carried into the night."""

    id: str
    sequence: list[str] = field(default_factory=list)
    stamps: dict[str, datetime] = field(default_factory=dict)
    outcome: str = ""
    tools: list[str] = field(default_factory=list)
    error_text: str = ""
    goal_open: bool = False
    correction: bool = False
    turns: int = 0
    end: datetime | None = None
    priority: float = 0.0
    # If awake replay (recall/awake.py) already assigned this session's
    # credit at the moment of the outcome, the night does not assign it
    # again: one success must not leave two `basari` entries. Forward replay
    # and stitching still run — neither is cumulative, repeating them is
    # harmless.
    reverse_done: bool = False
    forward_index: int = 0

    @property
    def disabled(self) -> bool:
        return bool(self.outcome)

    def gain_class(self) -> str:
        if self.outcome in ("basarisiz", "duzeltildi", "acik"):
            return self.outcome
        if (not self.error_text and not self.goal_open and not self.correction
                and self.turns <= ROUTINE_KIND):
            return "rutin"
        return self.outcome or "rutin"


@dataclass(slots=True)
class NightReport:
    """What the night did. Written to `.dornick/gece.jsonl`; the UI reads it."""

    session_count: int = 0
    replayed: int = 0
    carried_over: int = 0       # read by sleep.py
    new_edges: int = 0
    schema_touches: int = 0
    captured: int = 0
    success_shares: int = 0
    failure_shares: int = 0
    lessons_written: int = 0
    procedures_written: int = 0
    goals_written: int = 0
    distilled_nodes: int = 0    # read by sleep.py
    warmed: int = 0
    cooled: int = 0             # read by test_hot_cold.py
    contradictions: int = 0
    rolled_back: int = 0
    stitched: int = 0
    reweave_edges: int = 0
    edges_shrunk: int = 0
    edges_removed: int = 0
    distillation: str = ""
    seconds: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


# -- entry point -------------------------------------------------------


def night_pass(
    store: Any,
    sessions_dir: Path,
    *,
    clock: Clock | None = None,
    watermark: Path | None = None,
    model: Callable[[str], str] | None = None,
    budget_s: float = 300.0,
    local_model: bool = True,
    cloud_consent: bool = False,
    state_dir: Path | None = None,
    exam: Callable[[], dict[str, Any]] | None = None,
) -> NightReport:
    """The night's six steps. The first five need no model.

    When `budget_s` runs out the running unit is completed and the next one
    is not started; the remaining sessions stay unmarked in the watermark
    and go to the front of the queue the next night.
    """
    started = time.perf_counter()
    clock = clock or wall_clock
    report = NightReport()
    if not switches.ACTIVE.weave:
        report.distillation = "atlandı: örgü kapalı"
        return report

    status = _read_watermark(watermark)
    sessions = prioritised_sessions(store, sessions_dir, clock=clock,
                                    watermark=watermark, status=status)
    report.session_count = len(sessions)

    touched: list[str] = []
    processed: list[ReplaySession] = []
    for session in sessions:
        if processed and time.perf_counter() - started > budget_s:
            break
        _forward_replay(store, session, report)
        _schema_refresh(store, session, report)
        _capture(store, session, report, clock)
        if not session.reverse_done:
            reverse_replay(store, session, report=report)
        touched.extend(session.sequence)
        processed.append(session)
        status.setdefault("islenen", {})[session.id] = _stamp(clock)
        report.replayed += 1
    report.carried_over = len(sessions) - len(processed)

    _stitch(store, processed, report)
    _reweave(store, dict.fromkeys(touched), report)
    _downscale(store, report)

    # Step 6 — distillation. The one step that needs a model, the one step
    # that can be rolled back: the first five are a record of what happened,
    # this one is an inference. The privacy gate lives in distil.gate.
    from . import distil

    exam_before = exam() if exam is not None else None
    distillation = distil.distil(store, touched, model=model, clock=clock,
                            local_model=local_model, cloud_ok=cloud_consent,
                            state_dir=state_dir)
    report.distilled_nodes = distillation.written
    report.contradictions = distillation.contradictions
    if distillation.node_ids and exam is not None:
        # Exam gate: if the pass lowered prime quality, the distilled nodes
        # go to the tombstone. Replay and credit are not rolled back.
        report.rolled_back = distil.exam(store, distillation, exam_before, exam())
    report.distillation = distillation.status

    # Step 7 — hot/cold. At the end of the night, after everything has
    # settled: unless the active set is kept bounded, the signature scan and
    # RAM grow linearly with total memory (measured: p95 33 ms at 200k,
    # budget 20).
    report.warmed, report.cooled = store.update_heat(COLD_THRESHOLD)

    status["son_kosu"] = _stamp(clock)
    _write_watermark(watermark, status)
    report.seconds = round(time.perf_counter() - started, 3)
    _append_journal(sessions_dir, report, clock)
    return report


# -- Step 1: priority --------------------------------------------------


def prioritised_sessions(
    store: Any,
    sessions_dir: Path,
    *,
    clock: Clock,
    watermark: Path | None = None,
    status: dict[str, Any] | None = None,
) -> list[ReplaySession]:
    """The sessions to replay, in gain × need order.

    Gain comes from the outcome (a failed session teaches the most), need
    from the number of nodes touched: a session that touched many memories
    will touch them in the future too.
    """
    status = status if status is not None else _read_watermark(watermark)
    processed = set((status.get("islenen") or {}).keys())
    now = clock()
    out: list[ReplaySession] = []
    for path in sorted(sessions_dir.glob("*.jsonl")):
        if path.stem in processed:
            continue
        session = _read_session(path)
        if session is None or not session.disabled or not session.sequence:
            continue
        age = _days_between(now, session.end)
        if age > LOOKBACK_DAYS:
            continue        # the old is consolidated by schema, not by scanning
        mean_surprise = _mean_surprise(store, session.sequence)
        session.priority = (
            GAIN.get(session.gain_class(), 0.1)
            * (1 + 0.1 * len(set(session.sequence)))
            * (1 + mean_surprise)
            * (LOOKBACK_DECAY ** max(0, age))
        )
        out.append(session)
    out.sort(key=lambda o: (-o.priority, o.id))
    return out


def _days_between(now: datetime, moment: datetime | None) -> int:
    if moment is None:
        return 0
    return max(0, (now - moment).days)


def surprise(store: Any, body: str, *, exclude: str = "") -> float:
    """How new is this body? 0 = known, 1 = never seen.

    `exclude`: the record itself. Once written, its nearest neighbour is
    itself and every record would look "not surprising at all" — a silently
    wrong zero.

    Phase 4 does the same computation AT WRITE TIME and stores it as
    encoding strength (`activation.encoding_strength`). The computation here
    is not that moment's surprise but THIS moment's: the night looks at what
    is ordinary relative to today's memory. The two are deliberately
    separate.
    """
    try:
        neighbours = store._seed(body[:400], 4)          # noqa: SLF001
    except Exception:
        return 0.0
    for node_id, score, _kind in neighbours:
        if node_id != exclude:
            return round(1.0 - score, 4)
    return 1.0


def _mean_surprise(store: Any, sequence: Iterable[str]) -> float:
    values = []
    for node_id in dict.fromkeys(sequence):
        node = store.peek(node_id)
        if node is not None:
            values.append(surprise(store, f"{node.title} {node.body}",
                                   exclude=node_id))
    return sum(values) / len(values) if values else 0.0


# -- Step 2: forward replay --------------------------------------------


def _forward_replay(store: Any, session: ReplaySession, report: NightReport, *,
                    start: int = 0) -> None:
    """Links the neighbours in the session sequence with "used together".

    These edges travel the same road as content edges in `recall()`
    spreading but **do not enter the prime** (the prime is limited to hop
    0). So temporal adjacency enriches explicit search without polluting
    automatic injection.
    """
    sequence = list(dict.fromkeys(session.sequence))
    for i, a in enumerate(sequence):
        for j in range(i + 1, min(i + WINDOW, len(sequence))):
            if j < start:
                continue        # this pair was written before (incremental run)
            weight = round(ADJACENCY_WEIGHT * ADJACENCY_DECAY ** (j - i - 1), 3)
            if store.connect(a, sequence[j], weight=weight,
                            reason=f"birlikte kullanıldı ({session.id})",
                            birikimli=True):
                report.new_edges += 1


# -- Step 2b: schema refresh -------------------------------------------


def _schema_refresh(store: Any, session: ReplaySession, report: NightReport) -> None:
    """An old memory linked to today's memory refreshes on its own.

    The counterpart of the brain not "scanning the old to consolidate it"
    but replaying the overlapping pattern (Tse 2007: information that fits
    a schema consolidates fast). What is not linked is not refreshed — and
    must not be.
    """
    touched = set(session.sequence)
    for node_id in dict.fromkeys(session.sequence):
        for neighbour, weight in store.neighbours(node_id):
            if neighbour.id in touched:
                continue
            store.add_use(neighbour.id, w=SCHEMA_SHARE * weight,
                                label=activation.SCHEMA)
            report.schema_touches += 1


# -- Step 1b: retroactive capture --------------------------------------


def _capture(store: Any, session: ReplaySession, report: NightReport, clock: Clock) -> None:
    """The ordinary record next to a surprising event consolidates too."""
    surprising: list[datetime] = []
    for node_id in dict.fromkeys(session.sequence):
        node = store.peek(node_id)
        moment = session.stamps.get(node_id)
        if node is None or moment is None:
            continue
        if surprise(store, f"{node.title} {node.body}",
                    exclude=node_id) >= CAPTURE_THRESHOLD:
            surprising.append(moment)
    if not surprising:
        return
    window = timedelta(minutes=CAPTURE_MINUTES)
    for node_id in dict.fromkeys(session.sequence):
        moment = session.stamps.get(node_id)
        if moment is None:
            continue
        node = store.peek(node_id)
        if node is None or surprise(store, f"{node.title} {node.body}",
                                    exclude=node_id) >= CAPTURE_THRESHOLD:
            continue
        if any(abs(moment - big) <= window for big in surprising):
            store.add_use(node_id, w=CAPTURE_SHARE,
                                label=activation.CAPTURED)
            report.captured += 1


# -- Step 3: reverse replay --------------------------------------------


def reverse_replay(store: Any, session: ReplaySession, *,
                   report: NightReport | None = None) -> NightReport:
    """Walks backwards from the outcome and assigns credit.

    The distinction the `uses` counter never made: the memory that led to
    the wrong answer and the one that led to the right answer each got one
    point. Here what led to success gets a positively weighted use and what
    led to failure a negatively weighted one — and a `lesson` is written
    next to what led to failure. The record is not forgotten, it **falls
    behind**.

    Awake replay (Phase 3.12) will call the same function at the moment of
    the outcome; the night only collects the sessions that missed that run.
    """
    report = report if report is not None else NightReport()
    sequence = list(dict.fromkeys(session.sequence))
    if not sequence:
        return report

    if session.outcome == "basarili":
        for k, node_id in enumerate(reversed(sequence)):
            store.add_use(node_id, w=SUCCESS_SHARE * SHARE_DECAY ** k,
                                label=activation.SUCCESS)
            report.success_shares += 1
        if len(sequence) >= 3 and len(session.tools) >= 2:
            title = "yordam: " + " → ".join(session.tools[:6])
            if not _reinforce(store, "procedure", title, activation.SUCCESS):
                store.remember("Bu yordam işe yaradı: "
                               + " → ".join(session.tools[:6]),
                               kind="procedure", title=title,
                               tags=["gece", "yordam"],
                               links=sequence[-3:], session=session.id)
                report.procedures_written += 1

    elif session.outcome in ("basarisiz", "duzeltildi"):
        for k, node_id in enumerate(reversed(sequence)):
            store.add_use(node_id, w=FAILURE_SHARE * SHARE_DECAY ** k,
                                label=activation.FAILURE)
            report.failure_shares += 1
        source = sequence[-1]
        if session.error_text:
            # The same lesson is not LEARNED a second time, it is reinforced.
            # If the night wrote a new lesson for every failed session, an
            # error that happened five times would become five separate
            # lessons, all competing for the soul's eight slots. Similarity
            # is measured by the error TEXT, not by the record's IDENTITY:
            # the identity differs per session, the error is the same.
            title = f"hata: {session.error_text}"[:140]
            existing = store.find_by_title("lesson", title)
            if existing is not None:
                store.add_use(existing.id, w=0.5, label=activation.FAILURE)
                store.connect(existing.id, source, weight=0.6,
                             reason="bu hatıra hataya götürdü")
            else:
                # The record's identity is NOT written into the body: it
                # already sits on the edge ("bu hatıra hataya götürdü") and
                # `mind_recall` shows edge reasons. A raw identity gave the
                # model no information; it only raised the soul's cost in
                # every session.
                store.remember(
                    session.error_text, kind="lesson", title=title,
                    tags=["gece", "hata"], links=[source], session=session.id)
                report.lessons_written += 1

    elif session.outcome == "acik":
        # An open goal is left alone — let Phase 1 decay do its work. But
        # "where you left off" should be a node the next session can find.
        store.remember(
            f"Yarım kalan iş ({session.id}): son dokunulan kayıtlar {', '.join(sequence[-2:])}",
            kind="goal", tags=["acik"], links=sequence[-2:], session=session.id)
        report.goals_written += 1
    return report


def _reinforce(store: Any, kind: str, title: str, label: str) -> bool:
    """If the same thing is already written, strengthen it; do not write anew.

    The rule the roadmap set for procedures ("if one with the same title
    exists, add a use instead of superseding") was needed for lessons most
    of all: what fills the memory is a new lesson written on every repeat of
    the same error.
    """
    existing = store.find_by_title(kind, title)
    if existing is None:
        return False
    store.add_use(existing.id, w=0.5, label=label)
    return True


# -- Step 4: stitching -------------------------------------------------


def _stitch(store: Any, sessions: list[ReplaySession], report: NightReport) -> None:
    """Sequences never experienced: Monday A→B, Thursday B→C ⇒ A→C.

    The weight is low (0.3): a bond never experienced is half as
    trustworthy as one that was. If they are later genuinely used together
    Step 2 raises the weight; if not, downscaling lowers it.
    """
    # In time order: stitching is a directed job — "what came before it" in
    # the earlier session is joined with "what came after it" in the later
    # one. Priority order (Step 1) would give the wrong direction here.
    ordered = sorted(sessions, key=lambda o: (o.end is None, o.end, o.id))
    for i, first in enumerate(ordered):
        for second in ordered[i + 1:]:
            s1 = list(dict.fromkeys(first.sequence))
            s2 = list(dict.fromkeys(second.sequence))
            for shared in set(s1) & set(s2):
                a = _before(s1, shared)
                c = _after(s2, shared)
                if not a or not c or a == c:
                    continue
                if store.connect(a, c, weight=0.3,
                                reason=f"{shared} üzerinden dikildi "
                                       f"({first.id}→{second.id})",
                                yalniz_yeni=True):
                    report.stitched += 1


def _before(sequence: list[str], node_id: str) -> str:
    i = sequence.index(node_id)
    return sequence[i - 1] if i > 0 else ""


def _after(sequence: list[str], node_id: str) -> str:
    i = sequence.index(node_id)
    return sequence[i + 1] if i + 1 < len(sequence) else ""


# -- Step 5: reweaving and downscaling ---------------------------------


def _reweave(store: Any, touched: Iterable[str],
             report: NightReport) -> None:
    """`_weave` used to freeze at write time; the graph depended on write order.

    Incremental: only the nodes touched tonight are rewoven. The full graph
    would cost 250 seconds at 50k nodes; the touched set takes a few
    seconds.
    """
    for node_id in touched:
        node = store.peek(node_id)
        if node is None:
            continue
        candidates = store._seed(f"{node.title} {node.body}"[:400], WEAVE_CANDIDATES)  # noqa: SLF001
        rank = 0
        for candidate, _score, _kind in candidates:
            if candidate == node_id:
                continue
            if store.connect(node_id, candidate, weight=round(0.8 - rank * 0.15, 3),
                            reason="benzer icerik (yeniden örgü)"):
                report.reweave_edges += 1
            rank += 1
            if rank >= WEAVE_LINKS:
                break


def _downscale(store: Any, report: NightReport) -> None:
    """Synaptic homeostasis: all edges shrink proportionally, no reason is exempt.

    Those strengthened tonight grew before the shrink, so they come out
    with a net gain; the untouched melt every night. An edge that falls
    below the floor is deleted — an edge may be deleted, a node may not:
    an edge is a road, not knowledge.
    """
    report.edges_shrunk, report.edges_removed = store.shrink_edges(
        EPSILON, EDGE_FLOOR)


# -- session log -------------------------------------------------------


# The log events that say a node was touched. Records injected via `prime`
# enter the sequence too: the model SAW them, that counts as use.
TOUCH = ("mind_open", "mind_write")


def _read_session(path: Path) -> ReplaySession | None:
    session = ReplaySession(id=path.stem)
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in lines:
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get("kind") != "meta":
            continue
        name = event.get("content")
        meta = event.get("meta") or {}
        moment = parse(event.get("ts"))

        if name in TOUCH:
            if node_id := meta.get("memory_id"):
                session.sequence.append(node_id)
                if moment is not None:
                    session.stamps.setdefault(node_id, moment)
            session.turns += 1
            if meta.get("kind") == "lesson" or meta.get("supersedes"):
                session.correction = True
        elif name == "prime":
            for node_id in meta.get("ids") or []:
                session.sequence.append(node_id)
                if moment is not None:
                    session.stamps.setdefault(node_id, moment)
            session.turns += 1
        elif name == "tool_end":
            session.tools.append(str(meta.get("tool") or ""))
            if meta.get("error"):
                session.error_text = str(meta.get("ozet") or meta.get("tool") or "hata")
        elif name == "goal_push":
            session.goal_open = True
        elif name == "goal_status":
            session.goal_open = False
        elif name == "ters_tekrar_kostu":
            session.reverse_done = True
        elif name == "ileri_tekrar_kostu":
            session.forward_index = max(session.forward_index,
                                        int(meta.get("n") or 0))
        elif name == "sonuc":
            session.outcome = str(meta.get("sonuc") or "")
            session.end = moment
    if session.end is None:
        session.end = parse(json.loads(lines[-1]).get("ts")) if lines else None
    return session


# -- watermark and report ----------------------------------------------


def _stamp(clock: Clock) -> str:
    return clock().isoformat(timespec="milliseconds")


def _read_watermark(path: Path | None) -> dict[str, Any]:
    if path is None or not Path(path).exists():
        return {"islenen": {}}
    try:
        status = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"islenen": {}}
    status.setdefault("islenen", {})
    return status


def _write_watermark(path: Path | None, status: dict[str, Any]) -> None:
    if path is None:
        return
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(status, ensure_ascii=False), encoding="utf-8")


def _append_journal(sessions_dir: Path, report: NightReport, clock: Clock) -> None:
    """The night's summary to disk: the "memory health" panel in the UI reads it."""
    try:
        path = Path(sessions_dir).parent / "gece.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"ts": _stamp(clock), **report.as_dict()},
                                ensure_ascii=False) + "\n")
    except OSError:
        pass        # if the report could not be written, the night still happened
