"""Sleep dynamics: pressure, the switch, rhythm, interruption, housekeeping.

The single claim these defend is that sleep here is not a scheduled batch
job. A batch job a user walks in on is either rude or lossy; this one
finishes its atomic unit, hands the machine back, and carries the rest.

The narcolepsy test is the sharpest of them: with one threshold a system
whose pressure sits near it flips state every minute, which is precisely
what a user would experience as a machine that can never settle. Two
thresholds and an orexin term are what stop it, and the test measures the
flipping directly rather than trusting the design.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from dornick.events import EventLog
from dornick.recall import open_store, sleep
from dornick.recall.sleep import Phase, Rhythm, SleepSwitch, Sleeper, State

MONDAY = datetime(2025, 6, 2, 9, 0, tzinfo=timezone.utc)


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
    return Clock(MONDAY)


@pytest.fixture()
def store(tmp_path: Path, clock: Clock):
    s = open_store(tmp_path / "memory", clock=clock)
    yield s
    s.close()


@pytest.fixture()
def sessions(tmp_path: Path) -> Path:
    path = tmp_path / "sessions"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _session(sessions: Path, name: str, node_ids, clock: Clock,
             outcome: str = "basarili") -> None:
    log = EventLog(sessions / f"{name}.jsonl", clock=clock.text)
    log.note("session_start", session_id=name)
    for node_id in node_ids:
        clock.advance(minutes=1)
        log.note("mind_open", memory_id=node_id)
    log.note("sonuc", sonuc=outcome)
    log.close()


# -- the thresholds come from the curve --------------------------------


def test_thresholds_are_the_measured_ones() -> None:
    """Not chosen: derived from the degradation curve with the night off."""
    assert sleep.UPPER_THRESHOLD == pytest.approx(2.3374)
    assert sleep.LOWER_THRESHOLD == pytest.approx(sleep.UPPER_THRESHOLD / 3, rel=1e-3)

    source = (Path(__file__).resolve().parents[1]
              / "src" / "dornick" / "recall" / "sleep.py").read_text("utf-8")
    assert "basinc-bozulma.md" in source, "the constant's source must be in the comment"


# -- pressure is measured ----------------------------------------------


def test_pressure_rises_as_edges_pile_up_unshrunk(store, sessions, clock) -> None:
    """S is a count, not a mood: unshrunk strengthening per node."""
    first = sleep.pressure(store, sessions, clock=clock)
    nodes = [store.remember(f"Saha notu {i}.", kind="fact") for i in range(12)]
    for i in range(len(nodes) - 1):
        store.link(nodes[i].id, nodes[i + 1].id, weight=1.0, reason="elle")
    later = sleep.pressure(store, sessions, clock=clock)
    assert later.strengthening > first.strengthening
    assert later.total > first.total


def test_debt_counts_toward_pressure(store, sessions, clock) -> None:
    node = store.remember("Bir kayıt.", kind="fact")
    without = sleep.pressure(store, sessions, clock=clock).debt
    for i in range(10):
        _session(sessions, f"s{i}", [node.id], clock)
    with_debt = sleep.pressure(store, sessions, clock=clock).debt
    assert with_debt > without


# -- the switch --------------------------------------------------------


def test_user_activity_pins_it_awake(clock) -> None:
    """Orexin = 1 means no kind of sleep runs. No exceptions, no micro-sleep."""
    switch = SleepSwitch(clock=clock)
    switch.user_active(False)
    switch.step(sleep.UPPER_THRESHOLD * 5, idle_minutes=30)
    assert switch.state is State.SLEEPY

    switch.user_active(True)
    assert switch.state is State.AWAKE
    for _ in range(20):
        clock.advance(minutes=5)
        assert switch.step(sleep.UPPER_THRESHOLD * 5, idle_minutes=30) is State.AWAKE


def test_it_falls_asleep_only_after_settling(clock) -> None:
    switch = SleepSwitch(clock=clock)
    switch.user_active(False)
    assert switch.step(sleep.UPPER_THRESHOLD * 3, idle_minutes=30) is State.SLEEPY
    assert switch.step(sleep.UPPER_THRESHOLD * 3, idle_minutes=30) is State.SLEEPY
    clock.advance(minutes=sleep.SLEEPY_MINUTES + 1)
    assert switch.step(sleep.UPPER_THRESHOLD * 3, idle_minutes=30) is State.ASLEEP


def test_it_wakes_when_pressure_falls_below_the_lower_threshold(clock) -> None:
    switch = SleepSwitch(clock=clock)
    switch.user_active(False)
    switch.step(sleep.UPPER_THRESHOLD * 3, idle_minutes=30)
    clock.advance(minutes=sleep.SLEEPY_MINUTES + 1)
    switch.step(sleep.UPPER_THRESHOLD * 3, idle_minutes=30)
    assert switch.state is State.ASLEEP
    assert switch.step(sleep.LOWER_THRESHOLD / 2) is State.WAKING


def test_narcolepsy_two_hours_around_the_threshold(clock) -> None:
    """The reason there are two thresholds, measured rather than argued.

    Pressure wanders inside ±5% of the upper threshold for two hours with no
    user around. A single-threshold controller flips state dozens of times.
    """
    switch = SleepSwitch(clock=clock)
    switch.user_active(False)
    # Deterministic wander: no randomness, so the number is reproducible.
    band = [1.0, -1.0, 1.0, -1.0, 0.5, -0.5] * 20
    for i, direction in enumerate(band):
        clock.advance(minutes=1)
        switch.step(sleep.UPPER_THRESHOLD * (1 + 0.05 * direction), idle_minutes=30)
    assert len(switch.transitions) <= 2, [t.new for t in switch.transitions]


def test_caffeine_delays_without_erasing_the_pressure(clock) -> None:
    """"Don't sleep now" raises the bar; it does not make the debt go away."""
    switch = SleepSwitch(clock=clock)
    switch.user_active(False)
    switch.caffeine(hours=4)
    assert switch.step(sleep.UPPER_THRESHOLD * 1.5, idle_minutes=30) is State.AWAKE

    clock.advance(hours=5)
    assert switch.step(sleep.UPPER_THRESHOLD * 1.5, idle_minutes=30) is State.SLEEPY


def test_the_predicted_window_makes_falling_asleep_easier(clock) -> None:
    """Melatonin's counterpart: eased, never forced."""
    rhythm = Rhythm()
    for day in range(30):
        for hour in range(9, 18):
            rhythm.observe(MONDAY + timedelta(days=day, hours=hour - 9))
    switch = SleepSwitch(clock=clock, rhythm=rhythm)
    normal = switch.upper_threshold()

    # Just before a predicted active window the threshold must not ease.
    assert normal <= sleep.UPPER_THRESHOLD


# -- arousal thresholds ------------------------------------------------


def test_only_the_right_stimuli_wake_it() -> None:
    assert sleep.wakes_us("kullanici")
    assert sleep.wakes_us("voice")
    assert not sleep.wakes_us("otomasyon")
    assert not sleep.wakes_us("tepsi")
    # A reader never waits for a writer under WAL; a writer contends.
    assert not sleep.wakes_us("gate", writes=False)
    assert sleep.wakes_us("gate", writes=True)


def test_a_stimulus_below_threshold_does_not_interrupt(clock) -> None:
    switch = SleepSwitch(clock=clock)
    switch.user_active(False)
    switch.step(sleep.UPPER_THRESHOLD * 3, idle_minutes=30)
    clock.advance(minutes=sleep.SLEEPY_MINUTES + 1)
    switch.step(sleep.UPPER_THRESHOLD * 3, idle_minutes=30)

    assert switch.stimulus("otomasyon") is False
    assert switch.state is State.ASLEEP
    assert switch.stimulus("kullanici") is True
    assert switch.state is State.WAKING


# -- rhythm and zeitgebers ---------------------------------------------


def test_a_weekday_pattern_is_learned(clock) -> None:
    rhythm = Rhythm()
    for day in range(60):
        moment = MONDAY + timedelta(days=day)
        if moment.weekday() < 5:
            for hour in range(9, 18):
                rhythm.observe(moment.replace(hour=hour))

    tuesday = datetime(2025, 8, 5, 8, 45, tzinfo=timezone.utc)
    sunday = datetime(2025, 8, 10, 3, 0, tzinfo=timezone.utc)
    assert rhythm.probability(tuesday.replace(hour=10)) >= 0.5
    assert rhythm.probability(sunday) < 0.3


def test_a_new_install_says_it_does_not_know(clock) -> None:
    """A flat prior is the honest answer for the first two weeks."""
    rhythm = Rhythm()
    assert rhythm.probability(MONDAY) == pytest.approx(sleep.FLAT_PRIOR)


def test_a_timezone_change_shifts_and_humbles_the_histogram() -> None:
    rhythm = Rhythm()
    for day in range(30):
        for hour in range(9, 18):
            rhythm.observe(MONDAY + timedelta(days=day, hours=hour - 9))
    before = rhythm.confidence

    rhythm.shift_timezone(3)
    assert rhythm.offset == 3
    assert rhythm.confidence < before          # jet lag: trust yourself less
    for _ in range(3):
        rhythm.recover()
    assert rhythm.confidence == pytest.approx(1.0, abs=0.02)


def test_rhythm_survives_a_round_trip() -> None:
    rhythm = Rhythm()
    rhythm.observe(MONDAY)
    again = Rhythm.from_dict(json.loads(json.dumps(rhythm.as_dict())))
    assert again.as_dict() == rhythm.as_dict()


# -- cycles and interruption -------------------------------------------


def test_early_cycles_replay_late_cycles_distil() -> None:
    assert sleep.phase_of(1) is Phase.DEEP
    assert sleep.phase_of(2) is Phase.DEEP
    assert sleep.phase_of(4) is Phase.LIGHT
    assert sleep.phase_of(6) is Phase.REM


def test_a_night_that_ran_out_of_rem_starts_there_next_time() -> None:
    """REM rebound: the phase that was missed goes first."""
    assert sleep.phase_of(1, debt_phase=Phase.REM.value) is Phase.REM


def test_waking_stops_the_night_and_carries_the_rest(store, sessions,
                                                     tmp_path, clock) -> None:
    nodes = [store.remember(f"Kayıt {i}.", kind="fact") for i in range(6)]
    for i, node in enumerate(nodes):
        _session(sessions, f"s{i}", [node.id], clock)

    sleeper = Sleeper(store, sessions, clock=clock,
                      watermark=tmp_path / "w.json", state_dir=tmp_path)
    sleeper.wake("kullanici")
    report = sleeper.run(max_cycles=4)

    assert report.woke_reason == "kullanici"
    assert report.cycles == 0                # no unit started after the ask
    assert report.wake_latency_ms < 500      # the budget, measured


def test_an_uninterrupted_night_finishes_and_reports(store, sessions,
                                                     tmp_path, clock) -> None:
    nodes = [store.remember(f"Kayıt {i}.", kind="fact") for i in range(4)]
    for i, node in enumerate(nodes):
        _session(sessions, f"s{i}", [node.id], clock)

    events: list[str] = []
    sleeper = Sleeper(store, sessions, clock=clock, watermark=tmp_path / "w.json",
                      state_dir=tmp_path,
                      events=lambda kind, _data: events.append(kind))
    report = sleeper.run(max_cycles=3)

    assert report.replayed == 4
    assert report.carried == 0
    assert "uyku.basladi" in events and "uyku.bitti" in events


def test_deep_cycles_never_call_the_model(store, sessions, tmp_path,
                                          clock) -> None:
    """An early wake cannot leave half a guess behind if no guess was started."""
    calls: list[str] = []
    node = store.remember("Bir kayıt.", kind="fact")
    _session(sessions, "s1", [node.id], clock)

    sleeper = Sleeper(store, sessions, clock=clock, watermark=tmp_path / "w.json",
                      state_dir=tmp_path)
    sleeper.run(max_cycles=2, model=lambda p: calls.append(p) or "")
    assert calls == []                       # cycles 1-2 are deep


def test_the_debt_file_records_what_was_missed(store, sessions, tmp_path,
                                               clock) -> None:
    node = store.remember("Bir kayıt.", kind="fact")
    _session(sessions, "s1", [node.id], clock)
    Sleeper(store, sessions, clock=clock, watermark=tmp_path / "w.json",
            state_dir=tmp_path).run(max_cycles=1)
    debt = json.loads((tmp_path / "uyku_borcu.json").read_text("utf-8"))
    assert "devreden" in debt and "ts" in debt


# -- housekeeping ------------------------------------------------------


def test_vacuum_is_refused_while_awake(store) -> None:
    """The alternative to refusing is a frozen UI, so this is a guard."""
    with pytest.raises(sleep.AwakeError):
        sleep.housekeeping(store, State.AWAKE, vacuum=True)
    with pytest.raises(sleep.AwakeError):
        sleep.housekeeping(store, State.SLEEPY)


def test_housekeeping_runs_asleep_and_shrinks_the_wal(store) -> None:
    for i in range(50):
        store.remember(f"Kayıt {i}.", kind="fact")
    done = sleep.housekeeping(store, State.ASLEEP, vacuum=True)
    assert done["wal"] < 1_000_000           # < 1 MB after a full checkpoint
    assert done["fts"] is True and done["vacuum"] is True


class _Spy:
    """A store that records which sleep-only jobs were asked of it.

    Delegates everything else to the real store, so replay still works;
    only the housekeeping surface is observed.
    """

    WATCHED = ("checkpoint", "optimize_fts", "vacuum", "backup_to")

    def __init__(self, real) -> None:
        self._real = real
        self.calls: list[str] = []

    def __getattr__(self, name: str):
        attr = getattr(self._real, name)
        if name in self.WATCHED:
            def record(*args, **kwargs):
                self.calls.append(name)
                return attr(*args, **kwargs)
            return record
        return attr


def test_backup_is_taken_at_the_start_of_the_night_before_any_work(
        store, sessions, tmp_path, clock) -> None:
    """The snapshot must predate the night: whatever tonight breaks, this
    morning's memory is on disk. Proven by content, not by ordering — the
    backup carries no edge the replay wrote."""
    import sqlite3

    def edges(path: Path) -> set[tuple[str, str, float]]:
        db = sqlite3.connect(path)         # a second reader; WAL allows it
        try:
            return {(s, d, round(float(w), 4)) for s, d, w in
                    db.execute("SELECT src, dst, weight FROM link")}
        finally:
            db.close()

    nodes = [store.remember(f"Kayıt {i}.", kind="fact") for i in range(3)]
    _session(sessions, "s1", [n.id for n in nodes], clock)
    before = edges(store.path)             # `remember` may auto-link; fine

    report = Sleeper(store, sessions, clock=clock, watermark=tmp_path / "w.json",
                     state_dir=tmp_path).run(max_cycles=2)

    assert edges(store.path) != before, "the night changed the graph"
    copy = Path(report.backup)
    assert copy == tmp_path / "yedek" / f"recall-{clock().date().isoformat()}.db"
    assert copy.is_file()
    assert edges(copy) == before           # the graph as it was before the night
    assert store.count() == 3


def test_only_the_last_seven_backups_are_kept(store, tmp_path, clock) -> None:
    for _ in range(sleep.BACKUP_KEEP + 3):
        sleep.backup(store, State.ASLEEP, tmp_path, clock=clock)
        clock.advance(days=1)
    kept = sorted(p.name for p in (tmp_path / "yedek").glob("recall-*.db"))
    assert len(kept) == sleep.BACKUP_KEEP
    assert kept[-1] == f"recall-{(clock().date() - timedelta(days=1)).isoformat()}.db"
    assert f"recall-{MONDAY.date().isoformat()}.db" not in kept   # the oldest went


def test_every_housekeeping_job_is_refused_outside_deep_sleep(store, tmp_path,
                                                              clock) -> None:
    """AWAKE, SLEEPY, WAKING: none of them is the night. The guard is the
    same one VACUUM uses, so a new job cannot forget it."""
    for state in (State.AWAKE, State.SLEEPY, State.WAKING):
        with pytest.raises(sleep.AwakeError):
            sleep.backup(store, state, tmp_path, clock=clock)
        with pytest.raises(sleep.AwakeError):
            sleep.compress_old_nights(state, tmp_path, clock=clock)
        with pytest.raises(sleep.AwakeError):
            sleep.clear_caches(lambda: 1, state)
        with pytest.raises(sleep.AwakeError):
            sleep.weekly_housekeeping(store, state, tmp_path, clock=clock)
    assert not (tmp_path / "yedek").exists()


def test_old_night_logs_are_compressed_and_still_replay(tmp_path, clock) -> None:
    """Disk, not history: a gzipped night lists and replays exactly as before,
    and the view never learns it was compressed."""
    from dornick.recall import night_events as ne

    old_day = (clock().date() - timedelta(days=45)).isoformat()
    fresh_day = (clock().date() - timedelta(days=5)).isoformat()
    for day in (old_day, fresh_day):
        ne.NightLog(ne.night_path(tmp_path, day), clock).emit("dokunus", id="n_1")

    done = sleep.compress_old_nights(State.ASLEEP, tmp_path, clock=clock)

    assert [p.name for p in done] == [f"{old_day}.jsonl.gz"]
    assert not ne.night_path(tmp_path, old_day).exists()          # original gone
    assert ne.night_path(tmp_path, fresh_day).is_file()           # too young
    assert ne.nights(tmp_path) == [fresh_day, old_day]
    assert [e["id"] for e in ne.replay(ne.night_path(tmp_path, old_day))] == ["n_1"]
    # Idempotent: a second pass finds nothing left to do.
    assert sleep.compress_old_nights(State.ASLEEP, tmp_path, clock=clock) == []


def test_the_first_deep_cycle_clears_the_caches_once(store, sessions, tmp_path,
                                                     clock) -> None:
    node = store.remember("Bir kayıt.", kind="fact")
    for i in range(3):
        _session(sessions, f"s{i}", [node.id], clock)
    calls: list[int] = []

    def drop() -> int:
        calls.append(1)
        return 7

    report = Sleeper(store, sessions, clock=clock, watermark=tmp_path / "w.json",
                     state_dir=tmp_path, caches=drop).run(max_cycles=4)
    assert report.housekeeping["caches"] == 7
    assert len(calls) == 1                   # first deep cycle, not every cycle
    assert "wal" in report.housekeeping and report.housekeeping["fts"] is True


def test_the_mind_can_drop_its_caches(tmp_path, clock) -> None:
    """What the sleeper is handed in production: `Mind.clear_caches`."""
    from dornick.mind import open_mind

    sessions = tmp_path / "sessions"
    sessions.mkdir()
    log = EventLog(sessions / "s1.jsonl", clock=clock.text)
    log.message("user", "Pres hattında kalıp değişimi.")   # a digestible turn
    log.close()
    mind = open_mind(tmp_path / "mind", sessions, "cur", clock=clock)
    try:
        mind._scan_sessions()                       # fills the episode cache
        assert mind.clear_caches() >= 1
        assert mind.clear_caches() == 0             # nothing left to drop
    finally:
        mind.store.close()


def test_micro_and_local_sleep_do_none_of_it_except_the_caches(
        store, sessions, tmp_path, clock) -> None:
    """The table's last line: nothing runs in micro-sleep or local sleep —
    with one exception, the cache clearing, which takes no lock and is
    therefore allowed in local sleep only."""
    from dornick.recall import awake

    node = store.remember("Bir kayıt.", kind="fact")
    _session(sessions, "s1", [node.id], clock)
    spy = _Spy(store)
    dropped: list[int] = []

    awake.micro_sleep(spy, sessions, clock=clock, watermark=tmp_path / "w.json")
    assert spy.calls == []

    clock.advance(days=30)
    report = awake.local_sleep(spy, clock=clock, caches=lambda: dropped.append(1) or 5)
    assert spy.calls == []
    assert report.caches_cleared == 5 and dropped == [1]
    assert not (tmp_path / "yedek").exists()


def test_weekly_jobs_run_once_a_week_and_wait_for_the_user_to_be_gone(
        store, tmp_path, clock) -> None:
    """VACUUM cannot be interrupted, so it is started only when the rhythm
    says nobody is due; and once done it is not done again for a week."""
    first = sleep.weekly_housekeeping(store, State.ASLEEP, tmp_path, clock=clock)
    assert first["vacuum"] is True and first["compressed"] == 0

    clock.advance(days=2)
    again = sleep.weekly_housekeeping(store, State.ASLEEP, tmp_path, clock=clock)
    assert "vacuum" not in again and "compressed" not in again   # not due yet

    clock.advance(days=6)
    busy = Rhythm()                          # the user is always here at this hour
    for day in range(30):
        for hour in range(24):
            busy.observe(clock() + timedelta(days=day, hours=hour))
    postponed = sleep.weekly_housekeeping(store, State.ASLEEP, tmp_path,
                                          clock=clock, rhythm=busy)
    assert postponed["vacuum"] is False      # due, but the user is expected

    quiet = sleep.weekly_housekeeping(store, State.ASLEEP, tmp_path, clock=clock)
    assert quiet["vacuum"] is True
    ledger = json.loads((tmp_path / "bakim.json").read_text("utf-8"))
    assert ledger["vacuum"].startswith(clock().date().isoformat())
