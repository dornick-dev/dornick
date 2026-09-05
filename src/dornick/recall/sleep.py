"""Sleep dynamics — pressure, rhythm, the switch, and being interrupted.

The night pass is not a batch job. A batch job that a user walks in on is
either rude (it keeps the lock) or lossy (it rolls back). Biology solved this
a long time ago and the solution has four parts, all of which are here:

* **Pressure is measured, not simulated.** The system never says "I feel
  tired". It says "unshrunk strengthening is 34%, precision started to
  drop". The threshold is not chosen either — it comes from the degradation
  curve measured with the night switched off (`esik_egrisi`).
* **Two thresholds, not one** (Saper's flip-flop). With a single threshold a
  system whose pressure hovers near it flips state every minute. Hysteresis
  plus an orexin term — user activity — keeps it pinned.
* **Arousal is stimulus-dependent.** A user keystroke always wakes it. A
  scheduled automation does not. A read through the gate does not; a write
  does. Nothing about this is a preference: it follows from what would
  actually be disturbed.
* **Interruption is safe by construction.** The atomic unit is one session's
  replay in one transaction. Waking finishes the running unit and starts no
  other; unfinished work becomes debt and the next night runs it first.
  Distillation is the exception — a half-finished guess is discarded, since
  a guess interrupted is not a smaller guess, it is a wrong one.
"""

from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Iterable

from . import switches, weave
from .clock import Clock, parse, wall_clock

# Derived, not chosen. `life_bench.py --threshold-curve` runs the 90-day
# scenario with the night switched off and records prime precision against S
# (unshrunk strengthening: total edge weight / node). Baseline precision was
# 0.6033; the 5% drop starts at S = 2.3374. Run of 2026-09-02, curve in
# docs/charts/basinc-bozulma.md. LOWER_THRESHOLD is a third of it (roadmap 3.10.3).
UPPER_THRESHOLD = 2.3374
LOWER_THRESHOLD = 0.7791

# Pressure weights. Strengthening is the SHY term and dominates; debt and
# heat are corrections. Calibration note in docs/hafiza-fazlar.md.
W_STRENGTHENING = 0.6
W_DEBT = 0.25
W_HEAT = 0.15

# Normalisers so the three components share a scale.
DEBT_FULL = 50.0          # this many un-replayed sessions counts as "full"
HEAT_TARGET = 0.30        # hot-node share above which heat starts to count

# A cycle is 15 minutes — the scaled version of the biological 90. Early
# cycles are deep (replay), late cycles are REM (distillation).
CYCLE_MINUTES = 15
DEEP_CYCLES = 4

# Melatonin's counterpart: as the predicted idle window approaches, the upper
# threshold eases down so falling asleep is easy rather than forced.
EARLY_MINUTES = 30
EARLY_FACTOR = 0.7

# "Don't sleep now" holds for this long. It raises the threshold; it does not
# lower the pressure, so the rebound is real and the UI can say so honestly.
CAFFEINE_HOURS = 4

# How long the state must sit in SLEEPY before committing (Saper's switch is
# fast, but not instantaneous — and the user often comes back in that minute).
SLEEPY_MINUTES = 2

# Waking must hand the session back this fast, ruled by the UI not by us.
INERTIA_BUDGET_SECONDS = 2.0

# A new install has no histogram. A flat prior means "no idea", which is the
# honest state for two weeks.
FLAT_PRIOR = 0.3
RHYTHM_DAYS = 60

# Housekeeping (roadmap 3.10.10). A backup is taken at the start of EVERY
# night and the last BACKUP_KEEP are kept; VACUUM and night-log compression
# are weekly; a night log older than LOG_AGE_DAYS is gzipped.
BACKUP_KEEP = 7
WEEKLY_DAYS = 7
LOG_AGE_DAYS = 30


class State(str, Enum):
    AWAKE = "uyanik"
    SLEEPY = "uykulu"
    ASLEEP = "uyuyor"
    WAKING = "uyaniyor"


class Phase(str, Enum):
    DEEP = "derin"
    LIGHT = "hafif"
    REM = "rem"


# Arousal thresholds (roadmap 3.10.2). The rule is not "how important is
# this" but "would ignoring it disturb anything".
def wakes_us(reason: str, *, writes: bool = False) -> bool:
    """Does this stimulus cross the arousal threshold?"""
    if reason in ("kullanici", "user", "keyboard", "voice", "focus"):
        return True
    if reason in ("gate", "mcp"):
        # A reader never waits for a writer under WAL, so reads pass below
        # the threshold. A write would contend for the same lock.
        return writes
    return False        # automation, tray, settings: below threshold


@dataclass(slots=True)
class Pressure:
    """Homeostatic pressure S, per region, from three measured components."""

    strengthening: float = 0.0
    debt: float = 0.0
    heat: float = 0.0

    @property
    def total(self) -> float:
        return round(W_STRENGTHENING * self.strengthening
                     + W_DEBT * self.debt
                     + W_HEAT * self.heat, 4)

    def as_dict(self) -> dict[str, float]:
        return {"strengthening": round(self.strengthening, 4),
                "debt": round(self.debt, 4), "heat": round(self.heat, 4),
                "total": self.total}


def pressure(
    store: Any,
    sessions_dir: Path | None = None,
    *,
    watermark: Path | None = None,
    clock: Clock | None = None,
) -> Pressure:
    """Measure S. Nothing here is a feeling; every term is counted.

    `strengthening` is the SHY term: total edge weight per node, the same
    quantity the threshold curve was derived against. `debt` is un-replayed
    sessions. `heat` is how far the hot set has drifted past its target.
    """
    clock = clock or wall_clock
    out = Pressure()
    try:
        out.strengthening = store.strengthening()
    except Exception:
        return out
    if sessions_dir is not None:
        from .awake import sleep_debt

        _hours, pending = sleep_debt(sessions_dir, clock=clock, watermark=watermark)
        out.debt = min(1.0, pending / DEBT_FULL)
    try:
        total = store.count()
        if total:
            share = len(store.index) / total
            out.heat = max(0.0, (share - HEAT_TARGET) / (1.0 - HEAT_TARGET))
    except Exception:
        pass
    return out


# -- circadian ---------------------------------------------------------


class Rhythm:
    """A 7×24 histogram of when the user is around, kept honest by zeitgebers.

    A histogram on its own is a free-running oscillator: it drifts, exactly
    as a human clock drifts without light. The zeitgebers (lock, keyboard,
    power, focus assist, timezone) are what re-set it every day. The
    histogram says "usually"; the zeitgeber says "right now"; neither is
    enough alone.
    """

    def __init__(self, counts: list[list[float]] | None = None,
                 days: float = 0.0) -> None:
        self.counts = counts or [[0.0] * 24 for _ in range(7)]
        self.days = days
        self.offset = 0
        self.confidence = 1.0

    # -- learning ------------------------------------------------------

    def observe(self, moment: datetime, active: bool = True) -> None:
        self.counts[moment.weekday()][moment.hour] += 1.0 if active else 0.0
        self.days = min(RHYTHM_DAYS, self.days + 1.0 / 24.0)

    def learn_from(self, moments: Iterable[datetime]) -> None:
        for moment in moments:
            self.observe(moment)

    # -- reading -------------------------------------------------------

    def probability(self, moment: datetime) -> float:
        """Laplace-smoothed chance the user is active at this hour."""
        if self.days < 7:
            return FLAT_PRIOR       # two weeks of "no idea" is the honest answer
        hour = (moment.hour + self.offset) % 24
        seen = self.counts[moment.weekday()][hour]
        weeks = max(1.0, self.days / 7.0)
        return round(min(1.0, (seen + 1.0) / (weeks + 2.0)) * self.confidence, 4)

    def next_arrival(self, moment: datetime, *, horizon_hours: int = 16) -> datetime:
        """When the user is next likely to show up. Waking aims to be done."""
        for ahead in range(1, horizon_hours + 1):
            candidate = moment + timedelta(hours=ahead)
            if self.probability(candidate) >= 0.5:
                return candidate
        return moment + timedelta(hours=horizon_hours)

    # -- zeitgebers ----------------------------------------------------

    def shift_timezone(self, hours: int) -> None:
        """Jet lag: the histogram moves, and it distrusts itself for a while."""
        self.offset = (self.offset + hours) % 24
        self.confidence = 0.5

    def recover(self, days: float = 1.0) -> None:
        self.confidence = min(1.0, self.confidence + 0.17 * days)

    def as_dict(self) -> dict[str, Any]:
        return {"counts": self.counts, "days": self.days,
                "offset": self.offset, "confidence": self.confidence}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Rhythm:
        rhythm = cls(data.get("counts"), float(data.get("days") or 0.0))
        rhythm.offset = int(data.get("offset") or 0)
        rhythm.confidence = float(data.get("confidence") or 1.0)
        return rhythm


# -- the switch --------------------------------------------------------


@dataclass(slots=True)
class Transition:
    at: datetime
    old: State
    new: State
    reason: str
    s: float


class SleepSwitch:
    """Four states, two thresholds, one orexin term.

    With a single threshold a system whose pressure hovers near it flips
    state every minute — the narcolepsy test measures exactly that and
    demands at most two transitions in two hours. Hysteresis (two
    thresholds) plus orexin (user activity pins AWAKE) is what prevents it.
    """

    def __init__(self, *, clock: Clock | None = None,
                 rhythm: Rhythm | None = None) -> None:
        self.clock = clock or wall_clock
        self.rhythm = rhythm or Rhythm()
        self.state = State.AWAKE
        self.orexin = 1.0
        self.caffeine_until: datetime | None = None
        self.sleepy_since: datetime | None = None
        self.transitions: list[Transition] = []
        # OS suspend (lid closed, hibernate). Wall time passes while the
        # machine does not exist; the ledger of those gaps is what lets debt
        # be charged only for time that was actually lived.
        self.suspended_at: datetime | None = None
        self.suspensions: list[tuple[datetime, datetime]] = []

    # -- inputs --------------------------------------------------------

    def user_active(self, active: bool = True) -> None:
        """Orexin. While it is 1, no kind of sleep runs. No exceptions."""
        if active and self.suspended_at is not None:
            self.os_resumed()           # the lid was opened by a person
        self.orexin = 1.0 if active else 0.0
        if active and self.state is not State.AWAKE:
            self._go(State.AWAKE, "oreksin")

    def os_suspended(self) -> None:
        """The OS is going to sleep (`WM_POWERBROADCAST` suspend, 3.10.9).

        Nothing accumulates while suspended: `step()` becomes a no-op, the
        SLEEPY settle timer and the caffeine hold stop counting. Pressure S
        itself needs no freezing — it is measured from the store, not from
        the clock — so what freezes is every counter that reads wall time.
        A night in progress is left in ASLEEP; the OS took the machine, not
        the user, so there is nothing to wake for.
        """
        if self.suspended_at is None:
            self.suspended_at = self.clock()

    def os_resumed(self) -> timedelta:
        """Back from suspend. The gap is booked as a slept period.

        Wall time that the machine did not live through is not debt: the
        gap is recorded in `suspensions` so `offline_since()` can subtract
        it from "hours since the last night", and the SLEEPY settle timer
        and the caffeine hold are shifted forward by it — four hours of "do
        not sleep now" are four hours of use, not four hours of lid-closed.
        The clock jump is what makes the rhythm re-evaluate: the next
        `step()` samples the real hour, not the one before the lid closed.
        Returns the gap (zero when not suspended).
        """
        if self.suspended_at is None:
            return timedelta(0)
        now = self.clock()
        gap = max(timedelta(0), now - self.suspended_at)
        self.suspensions.append((self.suspended_at, now))
        del self.suspensions[:-64]
        self.suspended_at = None
        if self.caffeine_until is not None:
            self.caffeine_until += gap
        if self.sleepy_since is not None:
            self.sleepy_since = now      # the two minutes restart, honestly
        return gap

    def offline_since(self, moment: datetime) -> timedelta:
        """How much of the wall time since `moment` was spent suspended.

        Debt callers subtract this from `hours since the last night`: a
        laptop closed on Friday and opened on Monday has not been awake for
        three days, and its micro/local sleep decisions must not think so.
        """
        total = timedelta(0)
        for start, end in self.suspensions:
            if end <= moment:
                continue
            total += end - max(start, moment)
        if self.suspended_at is not None and self.suspended_at < self.clock():
            total += self.clock() - max(self.suspended_at, moment)
        return total

    def caffeine(self, hours: float = CAFFEINE_HOURS) -> None:
        """"Don't sleep now." Raises the threshold; does not touch S."""
        self.caffeine_until = self.clock() + timedelta(hours=hours)

    def stimulus(self, reason: str, *, writes: bool = False) -> bool:
        """An external signal. Returns whether it woke us."""
        if self.state in (State.ASLEEP, State.SLEEPY) and wakes_us(reason, writes=writes):
            self._go(State.WAKING, reason)
            return True
        return False

    def sleep_now(self, reason: str = "istek") -> bool:
        """The user asked for the night now: straight to ASLEEP.

        Orexin drops and a caffeine hold is spent — the user's later word
        wins over the earlier one. The thresholds are not consulted here;
        they get their say again at the first cycle boundary, so a forced
        night with nothing to do ends after one cycle. Returns whether the
        switch moved (not while the machine is suspended).
        """
        if self.suspended_at is not None:
            return False
        self.orexin = 0.0
        self.caffeine_until = None
        self._go(State.ASLEEP, reason)
        return self.state is State.ASLEEP

    def night_over(self, reason: str = "gece bitti") -> None:
        """The night ended without a stimulus: it ran out of work, or the
        application is closing. ASLEEP → WAKING; the next step() finishes
        the inertia. Not a stimulus, so it does not pass the threshold."""
        if self.state is State.ASLEEP:
            self._go(State.WAKING, reason)

    # -- the step ------------------------------------------------------

    def upper_threshold(self) -> float:
        limit = UPPER_THRESHOLD
        now = self.clock()
        if self.caffeine_until and now < self.caffeine_until:
            return limit * 2.0          # deliberately out of reach
        window = self.rhythm.next_arrival(now)
        if window - now <= timedelta(minutes=EARLY_MINUTES):
            return limit * EARLY_FACTOR  # melatonin: easier, never forced
        return limit

    def step(self, s: float, *, idle_minutes: float = 0.0) -> State:
        """Advance the state machine one sample (the watchman calls this)."""
        if self.suspended_at is not None:
            return self.state           # the machine is not here; nothing moves
        now = self.clock()
        if self.orexin >= 1.0:
            if self.state is not State.AWAKE:
                self._go(State.AWAKE, "oreksin")
            return self.state

        if self.state is State.AWAKE:
            circadian = 1.0 - self.rhythm.probability(now + timedelta(hours=1))
            if s + circadian * 0.5 >= self.upper_threshold() and idle_minutes >= 1:
                self._go(State.SLEEPY, "basinc")
        elif self.state is State.SLEEPY:
            waited = ((now - self.sleepy_since).total_seconds() / 60.0
                      if self.sleepy_since else 0.0)
            if waited >= SLEEPY_MINUTES:
                self._go(State.ASLEEP, "hazir")
        elif self.state is State.ASLEEP:
            if s <= LOWER_THRESHOLD:
                self._go(State.WAKING, "basinc dustu")
            elif self.rhythm.probability(now + timedelta(minutes=EARLY_MINUTES)) >= 0.5:
                self._go(State.WAKING, "ritim")
        elif self.state is State.WAKING:
            self._go(State.AWAKE, "atalet bitti")
        return self.state

    def _go(self, new: State, reason: str) -> None:
        if new is self.state:
            return
        self.transitions.append(
            Transition(self.clock(), self.state, new, reason, 0.0))
        self.state = new
        self.sleepy_since = self.clock() if new is State.SLEEPY else None


# -- the night, in cycles ----------------------------------------------


@dataclass(slots=True)
class NightReport:
    cycles: int = 0
    replayed: int = 0
    carried: int = 0
    distilled: int = 0
    discarded_clusters: int = 0
    woke_reason: str = ""
    wake_latency_ms: float = 0.0
    seconds: float = 0.0
    phases: list[str] = field(default_factory=list)
    backup: str = ""
    housekeeping: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"cycles": self.cycles, "replayed": self.replayed,
                "carried": self.carried, "distilled": self.distilled,
                "discarded_clusters": self.discarded_clusters,
                "woke_reason": self.woke_reason,
                "wake_latency_ms": round(self.wake_latency_ms, 2),
                "seconds": round(self.seconds, 3), "phases": self.phases,
                "backup": self.backup, "housekeeping": self.housekeeping}


def phase_of(cycle: int, *, debt_phase: str = "") -> Phase:
    """Early cycles are deep, late cycles are REM.

    A night cut short loses distillation, not replay — which is the right
    priority: replay is the record of the day, distillation is a guess about
    it. If last night ran out of REM, this night starts there (rebound).
    """
    if debt_phase == Phase.REM.value and cycle == 1:
        return Phase.REM
    if cycle <= 2:
        return Phase.DEEP
    if cycle <= DEEP_CYCLES:
        return Phase.LIGHT
    return Phase.REM


class Sleeper:
    """Runs the night in cycles and can be woken between atomic units."""

    rhythm: Rhythm

    def __init__(self, store: Any, sessions_dir: Path, *,
                 clock: Clock | None = None, watermark: Path | None = None,
                 state_dir: Path | None = None,
                 rhythm: Rhythm | None = None,
                 events: Callable[[str, dict[str, Any]], None] | None = None,
                 caches: Callable[[], int] | None = None) -> None:
        self.store = store
        self.rhythm = rhythm or Rhythm()
        self.sessions_dir = Path(sessions_dir)
        self.clock = clock or wall_clock
        self.watermark = watermark
        self.state_dir = state_dir
        # Something that drops the transcript/episode caches and returns how
        # many entries went (`Mind.clear_caches`). None: nothing to drop.
        self.caches = caches
        # Events go through the frozen schema (night_events.SCHEMA): the view
        # trusts only that dict and never looks at `recall.db`.
        self.events = events or self._default_event
        self._wake: str = ""
        self._wake_at: float = 0.0

    def _default_event(self, kind: str, data: dict[str, Any]) -> None:
        if self.state_dir is None:
            return
        from . import night_events

        day = self.clock().date().isoformat()
        try:
            night_events.NightLog(
                night_events.night_path(self.state_dir, day),
                lambda: self.clock()).emit(kind, **data)
        except Exception:
            pass        # the night still happened if its log could not be written

    def wake(self, reason: str = "kullanici") -> None:
        """Ask the night to stop. The running unit finishes; none starts."""
        self._wake = reason
        self._wake_at = time.perf_counter()

    def rhythm_arrival(self) -> str:
        """The predicted time the user shows up — the night ends against it."""
        return self.rhythm.next_arrival(self.clock()).isoformat(timespec="minutes")

    def run(self, *, model: Callable[[str], str] | None = None,
            max_cycles: int = 6, budget_s: float = 300.0,
            cycle_budget_s: float = CYCLE_MINUTES * 60.0) -> NightReport:
        report = NightReport()
        if not switches.ACTIVE.weave:
            report.woke_reason = "orgu kapali"
            return report
        started = time.perf_counter()
        debt = _debt_read(self.state_dir)
        self.events("uyku.basladi", {
            "basinc": round(debt.get("devreden", 0) / max(DEBT_FULL, 1), 4),
            "tahmini_uyanma": self.rhythm_arrival(),
            "dongu_sayisi": max_cycles})

        # `run()` IS the night: the switch is ASLEEP by the time it is
        # called, so the housekeeping guards are passed that state here.
        # Anyone calling the jobs from elsewhere must pass the real one.
        if not self._wake:
            # Night start, every night, before any replay touches the graph:
            # whatever tonight breaks, this morning's memory is on disk.
            report.backup = str(self._safely(
                backup, self.store, State.ASLEEP, self.state_dir,
                clock=self.clock) or "")

        for cycle in range(1, max_cycles + 1):
            if self._wake:
                break
            phase = phase_of(cycle, debt_phase=debt.get("faz", ""))
            report.phases.append(phase.value)
            self.events("uyku.dongu", {"no": cycle, "faz": phase.value})
            remaining = min(cycle_budget_s, budget_s - (time.perf_counter() - started))
            if remaining <= 0:
                break
            if phase is Phase.DEEP and not report.housekeeping:
                # First deep cycle: checkpoint, FTS merge, caches — the jobs
                # that want no writer around. VACUUM waits for the end.
                report.housekeeping = self._safely(
                    housekeeping, self.store, State.ASLEEP,
                    caches=self.caches) or {}
            night = weave.night_pass(
                self.store, self.sessions_dir, clock=self.clock,
                watermark=self.watermark,
                # REM is where distillation lives; deep cycles never call the
                # model, so an early wake cannot leave half a guess behind.
                model=model if phase is Phase.REM else None,
                budget_s=remaining, state_dir=self.state_dir)
            report.cycles = cycle
            report.replayed += night.replayed
            report.carried = night.carried_over
            report.distilled += night.distilled_nodes
            if night.replayed == 0 and phase is not Phase.REM:
                break               # nothing left to replay

        if not self._wake:
            # Weekly, at the end of the night: S is lowest here (replay is
            # done) and VACUUM cannot be interrupted once started, so it is
            # only begun when the rhythm says nobody is due (3.10.10).
            report.housekeeping.update(self._safely(
                weekly_housekeeping, self.store, State.ASLEEP, self.state_dir,
                clock=self.clock, rhythm=self.rhythm) or {})
        report.seconds = time.perf_counter() - started

        if self._wake:
            report.woke_reason = self._wake
            report.wake_latency_ms = (time.perf_counter() - self._wake_at) * 1000.0
            # A cluster whose model call was in flight is dropped, not half
            # written: an interrupted guess is a wrong guess, not a small one.
            report.discarded_clusters = 0
            self.events("uyku.uyandi", {
                "sebep": self._wake, "dongu": report.cycles,
                "tamamlanan": report.replayed, "devreden": report.carried,
                "borc": debt})
        else:
            self.events("uyku.bitti", {"sebep": "basinc", "rapor": report.as_dict()})

        _debt_write(self.state_dir, {
            "faz": Phase.REM.value if report.distilled == 0 else "",
            "devreden": report.carried,
            "ts": self.clock().isoformat(timespec="milliseconds")})
        return report

    @staticmethod
    def _safely(job: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """A failed housekeeping job must not cost the night's replay."""
        try:
            return job(*args, **kwargs)
        except Exception:
            return None


def _debt_read(state_dir: Path | None) -> dict[str, Any]:
    if state_dir is None:
        return {}
    try:
        return json.loads((Path(state_dir) / "uyku_borcu.json").read_text("utf-8"))
    except (OSError, ValueError):
        return {}


def _debt_write(state_dir: Path | None, data: dict[str, Any]) -> None:
    if state_dir is None:
        return
    try:
        path = Path(state_dir) / "uyku_borcu.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


# -- housekeeping that only deep sleep may do --------------------------


class AwakeError(RuntimeError):
    """Raised when a sleep-only maintenance task is attempted while awake."""


def _require_asleep(state: State, job: str) -> None:
    """Every job below runs in deep sleep and nowhere else.

    Not AWAKE, not SLEEPY, not micro-sleep (which never calls these: it is a
    capped replay, not a night). The single exception, cache clearing under
    local sleep, does not come through here — `awake.local_sleep` calls the
    cache callable directly, because that job needs no lock.
    """
    if state is not State.ASLEEP:
        raise AwakeError(
            f"{job} yalnız uykuda koşar (durum: {state.value})")


def housekeeping(store: Any, state: State, *, vacuum: bool = False,
                 caches: Callable[[], int] | None = None) -> dict[str, Any]:
    """Glymphatic counterpart: the jobs that need the space sleep opens.

    SQLite's space-needing work is the same shape. A full WAL checkpoint
    needs no writer; FTS merging is I/O heavy; VACUUM takes an exclusive lock
    and simply cannot run under a live session. Refusing it while awake is a
    guard, not a preference — the alternative is a frozen UI.

    `caches` drops the transcript/episode caches (RAM) — the one job that is
    also allowed in local sleep, see `awake.local_sleep`.
    """
    _require_asleep(state, "bakım işleri")
    done: dict[str, Any] = {}
    done["wal"] = store.checkpoint()
    done["fts"] = store.optimize_fts()
    if caches is not None:
        done["caches"] = clear_caches(caches, state)
    if vacuum:
        done["vacuum"] = store.vacuum()
    return done


def clear_caches(caches: Callable[[], int], state: State) -> int:
    """Drop the transcript/episode caches; returns how many entries went."""
    _require_asleep(state, "önbellek boşaltma")
    return int(caches() or 0)


def backup(store: Any, state: State, state_dir: Path | None, *,
           clock: Clock | None = None, keep: int = BACKUP_KEEP) -> Path | None:
    """A consistent snapshot of the memory, taken before the night touches it.

    `<state_dir>/yedek/recall-<date>.db` through SQLite's backup API (the
    WAL is included; a raw file copy would miss it). The last `keep` nights
    are kept, oldest pruned. Same date twice — a night run twice — simply
    overwrites. Deep sleep only: the copy reads every page and would sit on
    the same lock a live session writes through.
    """
    _require_asleep(state, "yedek")
    if state_dir is None:
        return None
    clock = clock or wall_clock
    folder = Path(state_dir) / "yedek"
    target = folder / f"recall-{clock().date().isoformat()}.db"
    store.backup_to(target)
    for old in sorted(folder.glob("recall-*.db"))[:-keep] if keep > 0 else []:
        for stale in (old, old.with_name(old.name + "-wal"),
                      old.with_name(old.name + "-shm")):
            try:
                stale.unlink()
            except OSError:
                pass
    return target


def compress_old_nights(state: State, state_dir: Path | None, *,
                        clock: Clock | None = None,
                        older_than_days: int = LOG_AGE_DAYS) -> list[Path]:
    """Gzip night logs under `<state_dir>/gece/` older than `older_than_days`.

    Disk, not RAM: a night's event stream is a few hundred KB of JSON that
    is read once, if ever, from the replay panel — which reads the `.gz`
    transparently (`night_events.replay`). The date comes from the file
    name, so an undated file is left alone rather than guessed at.
    """
    _require_asleep(state, "günlük sıkıştırma")
    if state_dir is None:
        return []
    from . import night_events

    clock = clock or wall_clock
    cutoff = clock().date() - timedelta(days=older_than_days)
    done: list[Path] = []
    folder = Path(state_dir) / "gece"
    for path in sorted(folder.glob("*.jsonl")) if folder.is_dir() else []:
        try:
            day = datetime.fromisoformat(path.stem[:10]).date()
        except ValueError:
            continue
        if day > cutoff:
            continue
        try:
            done.append(night_events.compress(path))
        except OSError:
            continue        # one unreadable night is not the night's problem
    return done


def weekly_housekeeping(store: Any, state: State, state_dir: Path | None, *,
                        clock: Clock | None = None,
                        rhythm: Rhythm | None = None) -> dict[str, Any]:
    """The weekly jobs: VACUUM and night-log compression, when they are due.

    Both are scheduled through `<state_dir>/bakim.json` (last run per job)
    so a machine that sleeps every night does them once a week and a machine
    that sleeps rarely does them the first night it can. VACUUM cannot be
    interrupted once begun (SQLite), so it is only started when the rhythm
    says nobody is expected within EARLY_MINUTES — the one job whose wake
    latency is measured separately, and the reason it runs last, at the
    lowest S.
    """
    _require_asleep(state, "haftalık bakım")
    clock = clock or wall_clock
    now = clock()
    ledger = _maintenance_read(state_dir)
    done: dict[str, Any] = {}

    if _due(ledger.get("sikistirma"), now):
        done["compressed"] = len(compress_old_nights(state, state_dir, clock=clock))
        ledger["sikistirma"] = now.isoformat(timespec="milliseconds")

    if _due(ledger.get("vacuum"), now):
        arrival = rhythm.probability(now + timedelta(minutes=EARLY_MINUTES)) if rhythm else 0.0
        if arrival < 0.5:
            done["vacuum"] = store.vacuum()
            ledger["vacuum"] = now.isoformat(timespec="milliseconds")
        else:
            done["vacuum"] = False      # postponed: the user is due

    _maintenance_write(state_dir, ledger)
    return done


def _due(last: str | None, now: datetime, days: int = WEEKLY_DAYS) -> bool:
    moment = parse(last) if last else None
    return moment is None or (now - moment) >= timedelta(days=days)


def _maintenance_read(state_dir: Path | None) -> dict[str, Any]:
    if state_dir is None:
        return {}
    try:
        data = json.loads((Path(state_dir) / "bakim.json").read_text("utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _maintenance_write(state_dir: Path | None, data: dict[str, Any]) -> None:
    if state_dir is None:
        return
    try:
        path = Path(state_dir) / "bakim.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass
