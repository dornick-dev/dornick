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

from . import anahtar, orgu
from .saat import Saat, coz, duvar_saati

# Derived, not chosen. `yasam_bench.py --esik-egrisi` runs the 90-day
# scenario with the night switched off and records prime precision against S
# (unshrunk strengthening: total edge weight / node). Baseline precision was
# 0.6033; the 5% drop starts at S = 2.3374. Run of 2026-09-02, curve in
# docs/charts/basinc-bozulma.md. ESIK_ALT is a third of it (roadmap 3.10.3).
ESIK_UST = 2.3374
ESIK_ALT = 0.7791

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
    filigran: Path | None = None,
    saat: Saat | None = None,
) -> Pressure:
    """Measure S. Nothing here is a feeling; every term is counted.

    `strengthening` is the SHY term: total edge weight per node, the same
    quantity the threshold curve was derived against. `debt` is un-replayed
    sessions. `heat` is how far the hot set has drifted past its target.
    """
    saat = saat or duvar_saati
    out = Pressure()
    try:
        out.strengthening = store.strengthening()
    except Exception:
        return out
    if sessions_dir is not None:
        from .awake import sleep_debt

        _hours, pending = sleep_debt(sessions_dir, saat=saat, filigran=filigran)
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

    def __init__(self, *, saat: Saat | None = None,
                 rhythm: Rhythm | None = None) -> None:
        self.saat = saat or duvar_saati
        self.rhythm = rhythm or Rhythm()
        self.state = State.AWAKE
        self.orexin = 1.0
        self.caffeine_until: datetime | None = None
        self.sleepy_since: datetime | None = None
        self.transitions: list[Transition] = []

    # -- inputs --------------------------------------------------------

    def user_active(self, active: bool = True) -> None:
        """Orexin. While it is 1, no kind of sleep runs. No exceptions."""
        self.orexin = 1.0 if active else 0.0
        if active and self.state is not State.AWAKE:
            self._go(State.AWAKE, "oreksin")

    def caffeine(self, hours: float = CAFFEINE_HOURS) -> None:
        """"Don't sleep now." Raises the threshold; does not touch S."""
        self.caffeine_until = self.saat() + timedelta(hours=hours)

    def stimulus(self, reason: str, *, writes: bool = False) -> bool:
        """An external signal. Returns whether it woke us."""
        if self.state in (State.ASLEEP, State.SLEEPY) and wakes_us(reason, writes=writes):
            self._go(State.WAKING, reason)
            return True
        return False

    # -- the step ------------------------------------------------------

    def upper_threshold(self) -> float:
        limit = ESIK_UST
        now = self.saat()
        if self.caffeine_until and now < self.caffeine_until:
            return limit * 2.0          # deliberately out of reach
        window = self.rhythm.next_arrival(now)
        if window - now <= timedelta(minutes=EARLY_MINUTES):
            return limit * EARLY_FACTOR  # melatonin: easier, never forced
        return limit

    def step(self, s: float, *, idle_minutes: float = 0.0) -> State:
        """Advance the state machine one sample (the watchman calls this)."""
        now = self.saat()
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
            if s <= ESIK_ALT:
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
            Transition(self.saat(), self.state, new, reason, 0.0))
        self.state = new
        self.sleepy_since = self.saat() if new is State.SLEEPY else None


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

    def as_dict(self) -> dict[str, Any]:
        return {"cycles": self.cycles, "replayed": self.replayed,
                "carried": self.carried, "distilled": self.distilled,
                "discarded_clusters": self.discarded_clusters,
                "woke_reason": self.woke_reason,
                "wake_latency_ms": round(self.wake_latency_ms, 2),
                "seconds": round(self.seconds, 3), "phases": self.phases}


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
                 saat: Saat | None = None, filigran: Path | None = None,
                 state_dir: Path | None = None,
                 rhythm: Rhythm | None = None,
                 events: Callable[[str, dict[str, Any]], None] | None = None) -> None:
        self.store = store
        self.rhythm = rhythm or Rhythm()
        self.sessions_dir = Path(sessions_dir)
        self.saat = saat or duvar_saati
        self.filigran = filigran
        self.state_dir = state_dir
        # Olaylar dondurulmuş şemadan geçiyor (night_events.SCHEMA): arayüz
        # yalnız o sözlüğe güveniyor ve `recall.db`'ye hiç bakmıyor.
        self.events = events or self._varsayilan_olay
        self._wake: str = ""
        self._wake_at: float = 0.0

    def _varsayilan_olay(self, tur: str, veri: dict[str, Any]) -> None:
        if self.state_dir is None:
            return
        from . import night_events

        gun = self.saat().date().isoformat()
        try:
            night_events.NightLog(
                night_events.night_path(self.state_dir, gun),
                lambda: self.saat()).emit(tur, **veri)
        except Exception:
            pass        # gece, günlüğü yazılamadıysa da yaşandı

    def wake(self, reason: str = "kullanici") -> None:
        """Ask the night to stop. The running unit finishes; none starts."""
        self._wake = reason
        self._wake_at = time.perf_counter()

    def rhythm_arrival(self) -> str:
        """Kullanıcının ne zaman geleceği tahmini — gece ona göre bitiyor."""
        return self.rhythm.next_arrival(self.saat()).isoformat(timespec="minutes")

    def run(self, *, model: Callable[[str], str] | None = None,
            max_cycles: int = 6, budget_sn: float = 300.0,
            cycle_budget_sn: float = CYCLE_MINUTES * 60.0) -> NightReport:
        report = NightReport()
        if not anahtar.AKTIF.orgu:
            report.woke_reason = "orgu kapali"
            return report
        started = time.perf_counter()
        debt = _debt_read(self.state_dir)
        self.events("uyku.basladi", {
            "basinc": round(debt.get("devreden", 0) / max(DEBT_FULL, 1), 4),
            "tahmini_uyanma": self.rhythm_arrival(),
            "dongu_sayisi": max_cycles})

        for cycle in range(1, max_cycles + 1):
            if self._wake:
                break
            phase = phase_of(cycle, debt_phase=debt.get("faz", ""))
            report.phases.append(phase.value)
            self.events("uyku.dongu", {"no": cycle, "faz": phase.value})
            kalan = min(cycle_budget_sn, budget_sn - (time.perf_counter() - started))
            if kalan <= 0:
                break
            night = orgu.gece_gecisi(
                self.store, self.sessions_dir, saat=self.saat,
                filigran=self.filigran,
                # REM is where distillation lives; deep cycles never call the
                # model, so an early wake cannot leave half a guess behind.
                model=model if phase is Phase.REM else None,
                butce_sn=kalan, state_dir=self.state_dir)
            report.cycles = cycle
            report.replayed += night.tekrar_edilen
            report.carried = night.devreden
            report.distilled += night.damitik
            if night.tekrar_edilen == 0 and phase is not Phase.REM:
                break               # nothing left to replay
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
            "ts": self.saat().isoformat(timespec="milliseconds")})
        return report


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


def housekeeping(store: Any, state: State, *, vacuum: bool = False) -> dict[str, Any]:
    """Glymphatic counterpart: the jobs that need the space sleep opens.

    SQLite's space-needing work is the same shape. A full WAL checkpoint
    needs no writer; FTS merging is I/O heavy; VACUUM takes an exclusive lock
    and simply cannot run under a live session. Refusing it while awake is a
    guard, not a preference — the alternative is a frozen UI.
    """
    if state is not State.ASLEEP:
        raise AwakeError(
            f"bakım işleri yalnız uykuda koşar (durum: {state.value})")
    done: dict[str, Any] = {}
    done["wal"] = store.checkpoint()
    done["fts"] = store.optimize_fts()
    if vacuum:
        done["vacuum"] = store.vacuum()
    return done
