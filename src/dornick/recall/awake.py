"""Awake replay, micro-sleep and local sleep.

Sharp-wave ripple replay is not exclusive to sleep. It also happens during
quiet wakefulness — right after a task ends, right after a reward — and
reverse replay was in fact first observed there (Foster-Wilson 2006). Awake
replay serves fast learning and planning; sleep replay serves broad
integration. In an overtired brain, cortical neuron groups go offline one by
one while the animal is still awake ("local sleep", Vyazovskiy 2011).

Two product wounds follow from ignoring that:

* The lesson of a failed tool call was not written until the next night, so
  the same mistake could repeat inside the same session.
* A machine that never idles (a 7/24 gate, continuous automation) never gets
  a night, so consolidation debt grows without bound and nobody notices.

This module owns **when** things run, not what they do: the mechanics live in
`weave`. The one invariant it defends is the reason any of this is tied to
sleep at all — **downscaling only runs where learning is not happening.**
Night sleep downscales the whole graph; local sleep downscales the cold
region only; micro-sleep never downscales.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from . import switches, weave
from .clock import Clock, wall_clock

# 3.12.2 — the user has stopped typing for this long, so the turn gap is a
# safe place for incremental work.
BLANK_SECONDS = 20.0

# 3.12.3 — micro-sleep: idle this long, pressure above zero, and no night
# sleep for this many hours. One deep cycle, hard-capped.
MICRO_IDLE_MINUTES = 5
MICRO_BUDGET_SECONDS = 120.0
NIGHT_GAP_HOURS = 12

# 3.12.4 — local sleep: the machine that never idles. Both conditions must
# hold; the thresholds are deliberately conservative because local sleep is
# the only path that touches the graph while the user is active.
DEBT_HOURS = 48
DEBT_SESSIONS = 50

# The active region is "anything touched in the last week". Local sleep must
# never enter it: downscaling what is being learned right now would shrink
# the very traces that are strengthening (Tononi).
ACTIVE_DAYS = 7
REGION_REFRESH_MINUTES = 10

# A single session's reverse replay must fit between two turns. Beyond this
# it is not cut short — it finishes on a background thread so the turn is
# never blocked.
TURN_BUDGET_MS = 50.0

# Marker written into the session log once awake reverse replay has run, so
# the night skips that session. Without it every payout would be counted
# twice: once awake, once asleep.
REVERSE_DONE = "ters_tekrar_kostu"

# How far forward replay has already walked this session's sequence. Without
# it, running after every turn would keep inflating the same edge with no new
# information — the accumulation rule would turn a habit into a certainty.
FORWARD_MARK = "ileri_tekrar_kostu"


@dataclass(slots=True)
class LocalSleepReport:
    """What local sleep did — and, just as importantly, what it left alone."""

    cold_nodes: int = 0
    shrunk_edges: int = 0
    deleted_edges: int = 0
    skipped_active: int = 0
    seconds: float = 0.0
    reason: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"cold_nodes": self.cold_nodes, "shrunk_edges": self.shrunk_edges,
                "deleted_edges": self.deleted_edges,
                "skipped_active": self.skipped_active,
                "seconds": self.seconds, "reason": self.reason}


# -- 3.12.1 awake reverse replay ---------------------------------------


def on_result(
    store: Any,
    log_path: Path,
    outcome: str,
    *,
    clock: Clock | None = None,
    log: Any = None,
) -> weave.NightReport:
    """Assign credit the moment the outcome is known, not next night.

    Triggers: a test run came back, a tool failed, the user corrected
    something, a goal was closed. The lesson or procedure is written
    immediately, so the user sees it in the same session and the model can
    reach it on the very next turn.

    The session is marked so the night skips it. Running both would count
    every payout twice, and the record would carry two `basari` entries for
    one success.
    """
    clock = clock or wall_clock
    report = weave.NightReport()
    if not switches.ACTIVE.weave:
        return report

    session = weave._read_session(Path(log_path))      # noqa: SLF001 - same module family
    if session is None or not session.sequence or _already_replayed(Path(log_path)):
        return report
    session.outcome = outcome
    weave.reverse_replay(store, session, report=report)
    report.replayed = 1
    if log is not None:
        log.note(REVERSE_DONE, oturum=session.id, sonuc=outcome)
    return report


def _already_replayed(log_path: Path) -> bool:
    try:
        text = log_path.read_text(encoding="utf-8")
    except OSError:
        return False
    return f'"{REVERSE_DONE}"' in text


# -- 3.12.2 awake forward replay ---------------------------------------


def forward_replay(store: Any, log_path: Path, *, clock: Clock | None = None,
                   log: Any = None) -> int:
    """Write this session's temporal edges incrementally, between turns.

    The end-of-session capsule used to be a single shot: if the process
    crashed, the edges were never written. Doing it incrementally is also
    idempotent — `connect` is a max/accumulate over the same pair, and the
    replay is bounded by the same window as the night's step 2.

    Deliberately absent: schema refresh (that is cross-session), stitching,
    downscaling and distillation. None of those may run while the user is
    still working.
    """
    if not switches.ACTIVE.weave:
        return 0
    session = weave._read_session(Path(log_path))      # noqa: SLF001
    if session is None or len(session.sequence) < 2:
        return 0
    length = len(dict.fromkeys(session.sequence))
    if session.forward_index >= length:
        return 0                                    # nothing new since last run
    report = weave.NightReport()
    weave._forward_replay(store, session, report,      # noqa: SLF001
                       start=session.forward_index)
    if log is not None:
        log.note(FORWARD_MARK, oturum=session.id, n=length)
    return report.new_edges


# -- 3.12.3 micro-sleep ------------------------------------------------


def should_micro_sleep(
    *,
    idle_minutes: float,
    pressure: float,
    hours_since_night: float,
) -> bool:
    """Is a two-minute nap warranted right now?

    All three conditions, not any of them: the user is away, there is
    something to consolidate, and the night is overdue. A nap that runs for
    no reason is just latency.
    """
    return (idle_minutes >= MICRO_IDLE_MINUTES
            and pressure > 0.0
            and hours_since_night >= NIGHT_GAP_HOURS)


def micro_sleep(
    store: Any,
    sessions_dir: Path,
    *,
    clock: Clock | None = None,
    watermark: Path | None = None,
    budget_s: float = MICRO_BUDGET_SECONDS,
) -> weave.NightReport:
    """One deep cycle, capped. Catches up on replay; never downscales.

    Reduces debt, does not clear it — the night still comes. Distillation and
    downscaling are excluded by construction, not by configuration: this
    function does not call them.
    """
    clock = clock or wall_clock
    report = weave.NightReport()
    if not switches.ACTIVE.weave:
        return report
    started = time.perf_counter()
    state = weave._read_watermark(watermark)            # noqa: SLF001
    sessions = weave.prioritised_sessions(store, sessions_dir, clock=clock,
                                        status=state)
    report.session_count = len(sessions)
    replayed: list[weave.ReplaySession] = []
    for session in sessions:
        if replayed and time.perf_counter() - started > budget_s:
            break
        weave._forward_replay(store, session, report)          # noqa: SLF001
        weave._schema_refresh(store, session, report)       # noqa: SLF001
        if not _already_replayed(sessions_dir / f"{session.id}.jsonl"):
            weave.reverse_replay(store, session, report=report)
        replayed.append(session)
        state.setdefault("islenen", {})[session.id] = weave._stamp(clock)  # noqa: SLF001
        report.replayed += 1
    weave._stitch(store, replayed, report)                    # noqa: SLF001
    report.devreden = len(sessions) - len(replayed)
    weave._write_watermark(watermark, state)                     # noqa: SLF001
    report.distillation = "atlandı: mikro-uyku damıtmaz"
    report.seconds = round(time.perf_counter() - started, 3)
    return report


# -- 3.12.4 local sleep ------------------------------------------------


def sleep_debt(
    sessions_dir: Path,
    *,
    clock: Clock | None = None,
    watermark: Path | None = None,
) -> tuple[float, int]:
    """(hours since the last night, number of un-replayed sessions)."""
    clock = clock or wall_clock
    state = weave._read_watermark(watermark)             # noqa: SLF001
    done = set((state.get("islenen") or {}).keys())
    pending = sum(1 for p in Path(sessions_dir).glob("*.jsonl")
                  if p.stem not in done)
    last = state.get("son_kosu")
    from .clock import parse

    moment = parse(last) if last else None
    hours = ((clock() - moment).total_seconds() / 3600.0
             if moment is not None else float(DEBT_HOURS))
    return hours, pending


def should_local_sleep(hours_since_night: float, pending_sessions: int) -> bool:
    """Only for the machine that genuinely never gets an idle window."""
    return hours_since_night >= DEBT_HOURS and pending_sessions >= DEBT_SESSIONS


def local_sleep(
    store: Any,
    *,
    clock: Clock | None = None,
    active_days: int = ACTIVE_DAYS,
) -> LocalSleepReport:
    """Downscale the cold region while the machine stays awake.

    This is the one place that shrinks edges outside night sleep, and it is
    allowed exactly because of where it is confined: nodes that nothing has
    touched for a week, and only the edges between two such nodes. What is
    downscaled is, by definition, what is not being learned right now.

    Not done here: replay, schema refresh, stitching, distillation. All of
    those need the active region, and the active region is off limits.
    """
    clock = clock or wall_clock
    report = LocalSleepReport()
    if not switches.ACTIVE.weave:
        report.reason = "weave disabled"
        return report
    started = time.perf_counter()
    cutoff = clock() - timedelta(days=active_days)
    cold, skipped = store.cold_nodes(cutoff)
    report.cold_nodes = len(cold)
    report.skipped_active = skipped
    if cold:
        report.shrunk_edges, report.deleted_edges = store.shrink_edges_between(
            cold, weave.EPSILON, weave.EDGE_FLOOR)
    report.seconds = round(time.perf_counter() - started, 3)
    report.reason = "cold region only; active region untouched"
    return report


# -- reporting ---------------------------------------------------------


def write_report(state_dir: Path, kind: str, payload: dict[str, Any],
                 *, clock: Clock | None = None) -> None:
    """Append one line to `.dornick/gece.jsonl`. The UI reads it."""
    clock = clock or wall_clock
    try:
        path = Path(state_dir) / "gece.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"ts": clock().isoformat(timespec="milliseconds"),
                                 "kind": kind, **payload},
                                ensure_ascii=False) + "\n")
    except OSError:
        pass
