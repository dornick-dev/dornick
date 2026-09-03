"""Injectable clock.

Every memory mechanism from here on (decay, consolidation, recency) looks at
time. If time is read directly via `datetime.now()`, the question "what
happens thirty days from now" can only be answered by waiting thirty days —
that is, never. The tests here enforce that the injected clock reaches EVERY
stamp written to disk and that the direct call does not leak back in.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dornick.mind import open_mind
from dornick.recall import open_store
from dornick.recall.clock import parse, stamp

ROOT = Path(__file__).resolve().parents[1]


class Calendar:
    """Manually advanced clock."""

    def __init__(self, start: datetime) -> None:
        self.moment = start

    def __call__(self) -> datetime:
        return self.moment

    def add_days(self, days: int) -> None:
        self.moment += timedelta(days=days)


START = datetime(2025, 1, 6, 9, 0, tzinfo=timezone.utc)


# -- store -------------------------------------------------------------


def test_injected_clock_reaches_created_field(tmp_path: Path) -> None:
    calendar = Calendar(START)
    store = open_store(tmp_path, clock=calendar)
    try:
        node = store.remember("ilk gün yazılan kayıt", kind="fact")
        assert node.created.startswith("2025-01-06T09:00")
        calendar.add_days(40)
        later = store.remember("kırk gün sonra yazılan kayıt", kind="fact")
        assert later.created.startswith("2025-02-15T09:00")
    finally:
        store.close()


def test_injected_clock_reaches_last_used_field(tmp_path: Path) -> None:
    calendar = Calendar(START)
    store = open_store(tmp_path, clock=calendar)
    try:
        node = store.remember("kullanılacak kayıt", kind="fact")
        calendar.add_days(10)
        store.open(node.id)
        refreshed = store.peek(node.id)
        assert refreshed is not None
        assert refreshed.last_used.startswith("2025-01-16")
        assert refreshed.uses == 1
        # The moment of writing stays behind: a use does not change it.
        assert refreshed.created.startswith("2025-01-06")
    finally:
        store.close()


def test_wall_clock_when_no_clock_given(tmp_path: Path) -> None:
    """Product behaviour must not change: real time when the parameter is absent."""
    store = open_store(tmp_path)
    try:
        node = store.remember("bugün yazıldı", kind="fact")
        written = parse(node.created)
        assert written is not None
        assert abs((datetime.now(timezone.utc) - written).total_seconds()) < 60
    finally:
        store.close()


# -- mind --------------------------------------------------------------


def test_mind_passes_clock_to_store_and_goals(tmp_path: Path) -> None:
    calendar = Calendar(START)
    mind = open_mind(tmp_path / "mind", tmp_path / "sessions", "t", clock=calendar)
    try:
        memory = mind.remember("kullanıcı Ankara'da yaşıyor", kind="user")
        goal = mind.push_goal("kurulum paketini imzala")
        assert memory.ts.startswith("2025-01-06")
        assert goal.ts.startswith("2025-01-06")

        calendar.add_days(30)
        later = mind.remember("kullanıcı taşındı", kind="user")
        closed = mind.set_goal_status(goal.id, "done")
        assert later.ts.startswith("2025-02-05")
        assert closed is not None and closed.ts.startswith("2025-02-05")
    finally:
        mind.store.close()


def test_mind_and_store_see_the_same_clock(tmp_path: Path) -> None:
    """If the two layers read different calendars the recency ranking would break."""
    calendar = Calendar(START)
    mind = open_mind(tmp_path / "mind", tmp_path / "sessions", "t", clock=calendar)
    try:
        assert mind.store._clock is calendar
        assert mind._now() == stamp(calendar)
    finally:
        mind.store.close()


# -- rule --------------------------------------------------------------


def test_no_direct_datetime_now_call_remains() -> None:
    """`_now()` instead of `datetime.now()`.

    Calling `datetime.now()` directly while writing a new mechanism silently
    makes that mechanism unmeasurable — the benchmark's virtual clock cannot
    reach that call. The rule is enforced by grep; the single exception is
    `recall/clock.py`, the one place where time is read.
    """
    # The whole recall + mind surface, not just store.py: mind/search.py
    # read the wall clock in `_freshness` for a year, invisible to this guard
    # because the guard only listed store.py — and it made the life benchmark
    # depend on the real date it ran. Every module that ranks or ages a record
    # must read time through an injected clock.
    guarded = [
        "src/dornick/recall/store.py",
        "src/dornick/recall/weave.py",
        "src/dornick/recall/awake.py",
        "src/dornick/recall/activation.py",
        "src/dornick/mind/store.py",
        "src/dornick/mind/search.py",
    ]
    for relative in guarded:
        # Comment lines are filtered out: a comment DESCRIBING the rule must
        # not count as breaking it.
        lines = [
            line
            for line in (ROOT / relative).read_text(encoding="utf-8").splitlines()
            if not line.lstrip().startswith("#")
        ]
        # `datetime.now()` is allowed in exactly one shape: an injectable
        # fallback, `now = now or datetime.now(...)`, where a caller can pass
        # a virtual clock and only the default reads real time. A bare direct
        # call in a computation is what the benchmark cannot reach.
        offenders = [
            line for line in lines
            if "datetime.now(" in line and " or datetime.now(" not in line
        ]
        assert not offenders, (
            f"{relative}: direct datetime.now() call present. Read time "
            "through an injected clock (self._now(), or a `now` parameter "
            "defaulting to `now or datetime.now(...)`)."
        )


# -- stamp parsing -----------------------------------------------------


def test_corrupt_stamp_returns_none_instead_of_error() -> None:
    """A hand-edited or corrupted db must stay openable."""
    assert parse(None) is None
    assert parse("") is None
    assert parse("dün akşam") is None


def test_stamp_without_timezone_is_taken_as_utc() -> None:
    """Comparing a naive and an aware stamp used to blow up with TypeError."""
    moment = parse("2025-01-06T09:00:00.000")
    assert moment is not None and moment.tzinfo is timezone.utc
    assert moment == datetime(2025, 1, 6, 9, 0, tzinfo=timezone.utc)
