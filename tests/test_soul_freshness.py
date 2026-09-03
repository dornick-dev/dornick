"""The soul's composition: fresh corrections and the night's repeated lessons.

Two regressions measured (against the old version): `taze_ruh` 1.00 → 0.70
and `ruh_token` 325 → 348. Their roots are separate and both are flaws,
not design.

**Fresh correction.** Ranking by activation does the right thing — a
procedure in regular use really is livelier than a week-old correction. But
a correction is not an ordinary memory, it is a **change**: the reason the
soul sits in the system prompt is so the agent does not act on a stale
rule. A record corrected this week must be guaranteed its slot.

**Repeated lesson.** The night wrote one `lesson` per failed session. When
the same error happens five times that makes five separate lessons, all
competing for the soul's eight slots. The rule the roadmap states for
procedures ("if one with the same title exists, add a use instead of
superseding") was needed here most of all: the same lesson is not learned a
second time, it is **reinforced**.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from dornick.events import EventLog
from dornick.mind import open_mind
from dornick.recall import weave

NOW = datetime(2025, 6, 2, 9, 0, tzinfo=timezone.utc)


class Clock:
    def __init__(self, moment: datetime) -> None:
        self.moment = moment

    def __call__(self) -> datetime:
        return self.moment

    def advance(self, **delta) -> None:
        self.moment += timedelta(**delta)

    def text(self) -> str:
        return self.moment.isoformat(timespec="milliseconds")


@pytest.fixture()
def clock() -> Clock:
    return Clock(NOW)


@pytest.fixture()
def mind(tmp_path: Path, clock: Clock):
    m = open_mind(tmp_path / "mind", tmp_path / "sessions", "t", clock=clock)
    yield m
    m.store.close()


def _session(sessions: Path, name: str, node_ids, clock: Clock,
             *, outcome: str, tool: str = "kos", error: str = "") -> None:
    sessions.mkdir(parents=True, exist_ok=True)
    log = EventLog(sessions / f"{name}.jsonl", clock=clock.text)
    log.note("session_start", session_id=name)
    for node_id in node_ids:
        clock.advance(minutes=1)
        log.note("mind_open", memory_id=node_id)
    log.note("tool_end", tool=tool, error=bool(error), ms=10, ozet=error)
    log.note("sonuc", sonuc=outcome)
    log.close()


# -- a fresh correction finds a place in the soul ----------------------


def test_record_corrected_this_week_enters_the_soul(mind, clock) -> None:
    """Even with eight procedures in regular use."""
    # Eight procedures, all in regular use: they deserve every slot.
    filled = [mind.remember(f"Yordam {i}: saha kontrolü {i} adımları.",
                            kind="procedure") for i in range(8)]
    for _ in range(6):
        clock.advance(days=2)
        for m in filled:
            mind.store.open(m.id)

    old = mind.remember("Testler pytest ile kök dizinden koşuluyor.",
                        kind="procedure")
    clock.advance(days=30)
    new = mind.update(old.id, "Testler py -m pytest tests ile koşuluyor.",
                      kind="procedure")
    clock.advance(days=2)

    soul = mind.soul()
    ids = [m.id for m in soul.procedures]
    assert new.id in ids, "this week's correction is missing from the soul"
    assert old.id not in ids          # the old version stays out regardless


def test_fresh_corrections_do_not_take_over_the_soul(mind, clock) -> None:
    """The reserved share stays under half: the soul is not a list of corrections."""
    filled = [mind.remember(f"Yordam {i}: saha kontrolü {i}.", kind="procedure")
              for i in range(8)]
    for _ in range(6):
        clock.advance(days=2)
        for m in filled:
            mind.store.open(m.id)

    for i in range(8):
        old = mind.remember(f"Eski kural {i}: elle yapılıyor.", kind="procedure")
        clock.advance(hours=1)
        mind.update(old.id, f"Yeni kural {i}: otomatik yapılıyor.",
                    kind="procedure")

    soul = mind.soul()
    corrections = [m for m in soul.procedures if m.supersedes]
    assert len(corrections) <= len(soul.procedures) // 2
    assert any(not m.supersedes for m in soul.procedures)


def test_an_old_correction_loses_its_privilege(mind, clock) -> None:
    """The privilege belongs to freshness, not to being a correction."""
    filled = [mind.remember(f"Yordam {i}: saha kontrolü {i}.", kind="procedure")
              for i in range(8)]
    for _ in range(6):
        clock.advance(days=2)
        for m in filled:
            mind.store.open(m.id)

    old = mind.remember("Testler pytest ile koşuluyor.", kind="procedure")
    clock.advance(hours=1)
    new = mind.update(old.id, "Testler py -m pytest ile koşuluyor.",
                      kind="procedure")
    clock.advance(days=40)                    # the correction is no longer fresh

    assert new.id not in [m.id for m in mind.soul().procedures]


# -- the same lesson is not learned twice, it is reinforced ------------


def test_same_error_does_not_write_a_second_lesson(mind, tmp_path, clock) -> None:
    source = mind.remember("Gate servisi doğrudan kill ile durduruluyor.",
                           kind="procedure")
    sessions = tmp_path / "sessions"
    for i in range(4):
        clock.advance(days=1)
        _session(sessions, f"hata{i}", [source.id], clock,
                 outcome="basarisiz", error="sqlite database is locked")
        weave.night_pass(mind.store, sessions, clock=clock,
                         watermark=tmp_path / "w.json")

    lessons = mind.store.by_kind("lesson", limit=20)
    assert len(lessons) == 1, [d.body[:40] for d in lessons]


def test_repeated_lesson_is_reinforced(mind, tmp_path, clock) -> None:
    """Not written a second time, but the fact that it HAPPENED a second time is recorded."""
    source = mind.remember("Şema göçü doğrudan üretimde koşuluyor.",
                           kind="procedure")
    sessions = tmp_path / "sessions"
    _session(sessions, "h1", [source.id], clock, outcome="basarisiz",
             error="göç yarıda kaldı")
    weave.night_pass(mind.store, sessions, clock=clock, watermark=tmp_path / "w.json")
    lesson = mind.store.by_kind("lesson", limit=5)[0]
    first = len(mind.store.use_log(lesson.id))

    clock.advance(days=1)
    _session(sessions, "h2", [source.id], clock, outcome="basarisiz",
             error="göç yarıda kaldı")
    weave.night_pass(mind.store, sessions, clock=clock, watermark=tmp_path / "w.json")

    assert len(mind.store.by_kind("lesson", limit=5)) == 1
    assert len(mind.store.use_log(lesson.id)) > first


def test_a_different_error_writes_a_new_lesson(mind, tmp_path, clock) -> None:
    """Reinforcement is not merging: a different error is a different lesson."""
    source = mind.remember("Bir yordam.", kind="procedure")
    sessions = tmp_path / "sessions"
    for i, error in enumerate(("sqlite database is locked",
                               "sertifika doğrulanamadı")):
        clock.advance(days=1)
        _session(sessions, f"h{i}", [source.id], clock, outcome="basarisiz",
                 error=error)
        weave.night_pass(mind.store, sessions, clock=clock,
                         watermark=tmp_path / "w.json")

    assert len(mind.store.by_kind("lesson", limit=10)) == 2


def test_same_procedure_is_not_written_twice(mind, tmp_path, clock) -> None:
    """The rule the roadmap states for procedures, in the same place."""
    nodes = [mind.remember(f"Adım {i}: saha kontrolü.", kind="fact")
             for i in range(3)]
    sessions = tmp_path / "sessions"
    for i in range(3):
        clock.advance(days=1)
        log = EventLog(sessions / f"ok{i}.jsonl", clock=clock.text)
        sessions.mkdir(parents=True, exist_ok=True)
        for m in nodes:
            clock.advance(minutes=1)
            log.note("mind_open", memory_id=m.id)
        log.note("tool_end", tool="kos", error=False, ms=10)
        log.note("tool_end", tool="dosya_yaz", error=False, ms=10)
        log.note("sonuc", sonuc="basarili")
        log.close()
        weave.night_pass(mind.store, sessions, clock=clock,
                         watermark=tmp_path / "w.json")

    night_procedures = [n for n in mind.store.by_kind("procedure", limit=20)
                        if "gece" in n.tags]
    assert len(night_procedures) <= 1
