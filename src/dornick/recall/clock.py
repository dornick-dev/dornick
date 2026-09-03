"""Injectable clock.

Memory runs on time: how well a record is remembered depends on when it was
written and when it was last used. That carries an unmeasurable design trap —
if `datetime.now()` is called directly, the question "what happens thirty
days from now" can only be answered by waiting thirty days.

So there is a single place that reads the time, and it can be supplied from
outside. The product default is the wall clock; the life benchmark
(eval/context_memory/life_bench.py) puts a virtual calendar in its place and
plays ninety days in seconds. Product behaviour does not change,
measurability opens up.

Rule: `datetime.now()` is not called directly inside `recall/store.py` and
`mind/store.py` — `tests/test_clock.py` enforces it.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

# Clock: something called with no arguments that gives "now". It must carry
# timezone information — subtracting a UTC stamp from a naive one silently
# produces a wrong interval.
Clock = Callable[[], datetime]


def wall_clock() -> datetime:
    """The product's default clock: real time, UTC."""
    return datetime.now(timezone.utc)


def stamp(clock: Clock) -> str:
    """The format written to disk.

    Millisecond resolution: the order of two records written within the same
    second must not be lost (the recency ranking depends on it).
    """
    return clock().isoformat(timespec="milliseconds")


def parse(text: str | None) -> datetime | None:
    """Reads back an on-disk stamp; None for an unrecognised format.

    Old stamps written without a timezone (the residue of a bug before this
    version, or a hand-edited db) are taken as UTC — otherwise comparing naive
    and aware stamps blows up.
    """
    if not text:
        return None
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)
