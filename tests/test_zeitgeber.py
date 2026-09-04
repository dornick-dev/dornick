"""Zeitgebers: the OS events that re-set the switch (roadmap 3.10.9).

A histogram alone is a free-running oscillator; it drifts. The zeitgebers
are what pin it to the day — and the one that is easiest to get wrong is
the machine's own sleep. A laptop closed on Friday and opened on Monday
did not go three days without a night: that wall time did not exist for
it, and neither the settle timer, the caffeine hold, nor the consolidation
debt may count it. These tests feed the switch a suspend/resume pair on
the injected clock and check that nothing accumulated in between.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from dornick.recall import awake, sleep
from dornick.recall.sleep import Rhythm, SleepSwitch, State

FRIDAY = datetime(2025, 6, 6, 18, 0, tzinfo=timezone.utc)


class Clock:
    def __init__(self, moment: datetime) -> None:
        self.moment = moment

    def __call__(self) -> datetime:
        return self.moment

    def advance(self, **delta) -> None:
        self.moment += timedelta(**delta)


@pytest.fixture()
def clock() -> Clock:
    return Clock(FRIDAY)


def _sleepy(clock: Clock) -> SleepSwitch:
    switch = SleepSwitch(clock=clock)
    switch.user_active(False)
    assert switch.step(sleep.UPPER_THRESHOLD * 3, idle_minutes=30) is State.SLEEPY
    return switch


# -- suspend freezes, resume re-evaluates -------------------------------


def test_nothing_moves_while_the_machine_is_suspended(clock) -> None:
    """Three hours with the lid closed are not three hours of settling: the
    switch must not wake up already asleep."""
    switch = _sleepy(clock)
    switch.os_suspended()
    clock.advance(hours=3)
    assert switch.step(sleep.UPPER_THRESHOLD * 3, idle_minutes=30) is State.SLEEPY
    assert len(switch.transitions) == 1        # only AWAKE -> SLEEPY

    gap = switch.os_resumed()
    assert gap == timedelta(hours=3)
    # The settle timer restarts at resume rather than counting the gap.
    assert switch.step(sleep.UPPER_THRESHOLD * 3, idle_minutes=30) is State.SLEEPY
    clock.advance(minutes=sleep.SLEEPY_MINUTES + 1)
    assert switch.step(sleep.UPPER_THRESHOLD * 3, idle_minutes=30) is State.ASLEEP


def test_resume_is_booked_as_a_slept_period_not_as_debt(clock, tmp_path) -> None:
    """Friday evening to Monday morning: the debt is one hour, not sixty."""
    last_night = clock() - timedelta(hours=1)
    watermark = tmp_path / "w.json"
    watermark.write_text(json.dumps(
        {"son_kosu": last_night.isoformat(timespec="milliseconds"), "islenen": {}}),
        encoding="utf-8")
    sessions = tmp_path / "sessions"
    sessions.mkdir()

    switch = SleepSwitch(clock=clock)
    switch.os_suspended()
    clock.advance(hours=60)
    switch.os_resumed()

    wall_hours, _pending = awake.sleep_debt(sessions, clock=clock, watermark=watermark)
    lived = wall_hours - switch.offline_since(last_night).total_seconds() / 3600.0
    assert wall_hours == pytest.approx(61.0)
    assert lived == pytest.approx(1.0)
    assert awake.should_local_sleep(wall_hours, awake.DEBT_SESSIONS)       # wall clock says yes
    assert not awake.should_local_sleep(lived, awake.DEBT_SESSIONS)        # lived time says no


def test_offline_time_only_counts_after_the_moment_asked_about(clock) -> None:
    switch = SleepSwitch(clock=clock)
    switch.os_suspended()
    clock.advance(hours=10)
    switch.os_resumed()
    midway = FRIDAY + timedelta(hours=4)
    assert switch.offline_since(midway) == timedelta(hours=6)
    assert switch.offline_since(clock()) == timedelta(0)
    assert switch.offline_since(FRIDAY - timedelta(days=1)) == timedelta(hours=10)


def test_caffeine_is_hours_of_use_not_hours_of_lid_closed(clock) -> None:
    """"Don't sleep now" for four hours; the lid closes for five. On resume
    the hold is still standing — the user never got their four hours."""
    switch = SleepSwitch(clock=clock)
    switch.user_active(False)
    switch.caffeine(hours=4)
    switch.os_suspended()
    clock.advance(hours=5)
    switch.os_resumed()
    assert switch.step(sleep.UPPER_THRESHOLD * 1.5, idle_minutes=30) is State.AWAKE

    clock.advance(hours=4, minutes=1)
    assert switch.step(sleep.UPPER_THRESHOLD * 1.5, idle_minutes=30) is State.SLEEPY


def test_opening_the_lid_is_a_resume_and_orexin_at_once(clock) -> None:
    switch = _sleepy(clock)
    switch.os_suspended()
    clock.advance(hours=1)
    switch.user_active(True)
    assert switch.suspended_at is None
    assert switch.suspensions == [(FRIDAY, FRIDAY + timedelta(hours=1))]
    assert switch.state is State.AWAKE


def test_a_night_taken_by_the_os_stays_a_night_and_is_re_evaluated_on_resume(
        clock) -> None:
    """The OS took the machine, not the user: no wake-up. On resume the
    switch samples the real clock, and a night whose pressure is gone ends."""
    switch = _sleepy(clock)
    clock.advance(minutes=sleep.SLEEPY_MINUTES + 1)
    assert switch.step(sleep.UPPER_THRESHOLD * 3, idle_minutes=30) is State.ASLEEP

    switch.os_suspended()
    assert switch.state is State.ASLEEP
    clock.advance(hours=8)
    assert switch.step(sleep.LOWER_THRESHOLD / 2) is State.ASLEEP   # frozen
    switch.os_resumed()
    assert switch.step(sleep.LOWER_THRESHOLD / 2) is State.WAKING   # re-evaluated


def test_suspend_twice_is_one_suspend(clock) -> None:
    """A duplicate OS notification must not move the start of the gap."""
    switch = SleepSwitch(clock=clock)
    switch.os_suspended()
    clock.advance(hours=1)
    switch.os_suspended()
    clock.advance(hours=1)
    assert switch.os_resumed() == timedelta(hours=2)
    assert switch.os_resumed() == timedelta(0)        # not suspended any more


# -- timezone: three days of distrust ----------------------------------


def test_a_timezone_shift_takes_three_days_to_trust_again() -> None:
    """Jet lag: the histogram moves at once, but its confidence recovers
    over three days, not instantly."""
    rhythm = Rhythm()
    for day in range(30):
        for hour in range(9, 18):
            rhythm.observe(FRIDAY + timedelta(days=day, hours=hour - 9))
    rhythm.shift_timezone(3)
    assert rhythm.confidence == pytest.approx(0.5)
    rhythm.recover(days=1)
    assert rhythm.confidence < 1.0
    rhythm.recover(days=2)
    assert rhythm.confidence == pytest.approx(1.0, abs=0.02)
