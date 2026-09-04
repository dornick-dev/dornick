"""The watchman that puts the memory to sleep — and wakes it.

Everything the night needs was built and measured before this module
existed: pressure, the two-threshold switch, the rhythm and the
interruptible night in `sleep.py`; micro-sleep and local sleep in
`awake.py`; the six steps in `weave.py`. None of it ran in the product,
because nothing constructed a `Sleeper`. This is the missing constructor —
the roadmap's watchman (3.10.8): a background thread that samples pressure
once a minute, drives the switch, learns the rhythm from when the user is
around, and starts the night when the switch says ASLEEP.

Three rules shape it:

* **The night runs on this thread, never on the agent's.** The UI is
  served by an HTTP server and the agent by an asyncio loop; anything that
  blocks either freezes the product. The night blocks — for minutes — so
  it lives here, and every unit of it is interruptible through
  `Sleeper.wake()`.
* **Orexin is the user.** A message, or a tool call inside the user's own
  turn, pins the switch AWAKE and wakes a running night the moment it
  arrives — not on the next tick. A scheduled automation does not
  (`sleep.wakes_us`). The tick never decides on its own that the user is
  here; it only notices that they have been away.
* **Nothing here reads the wall clock directly.** The clock is injected so
  a test can play a day in a millisecond and the bench can play ninety.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from . import awake, distil, night_events, sleep, switches
from .clock import Clock, parse, wall_clock

# How often the watchman samples pressure and drives the switch. The
# roadmap sketches 30 s; a minute loses nothing — a keystroke reaches the
# switch immediately, not on the tick — and halves the pressure reads on a
# large store.
TICK_SECONDS = 60.0

# Orexin drops when the user has been away this long. The same notion of
# absence the micro-sleep uses (awake.MICRO_IDLE_MINUTES): one "away", not
# two that drift apart.
IDLE_MINUTES = float(awake.MICRO_IDLE_MINUTES)

# A night that ended on its own is a night. The pressure it leaves behind
# is the floor the two-percent-per-night downscale leaves, and feeding that
# straight back to the switch would put the graph through a night every
# few minutes — the downscale is per night, not per tick. For this long
# after a finished night the switch is fed no pressure. An interrupted
# night is not finished and does not rest: its debt is carried, and the
# next idle window resumes it.
REST_HOURS = float(awake.NIGHT_GAP_HOURS)

# Daily insurance (roadmap 3.10.8: the twenty-hour freshness rule stays).
# With the user away, one night a day even when S sits at zero — backup,
# housekeeping, and a watermark that says a night happened.
INSURANCE_HOURS = 20.0

# Cycles per night: 6 × CYCLE_MINUTES is the biological night, scaled
# (roadmap 3.10.4). The budget follows from it rather than from
# `Sleeper.run`'s five-minute default, which is sized for the bench.
MAX_CYCLES = 6
NIGHT_BUDGET_SECONDS = MAX_CYCLES * sleep.CYCLE_MINUTES * 60.0

# Files under the state directory. The watermark name is the one the web
# server already reads; the others are this module's.
WATERMARK_FILE = "filigran.json"
RHYTHM_FILE = "ritim.json"
JOURNAL_FILE = "uyku_gunlugu.jsonl"

# The reason a night stopped because the application is closing. Not a
# stimulus (nothing is disturbed), so it does not pass through the switch's
# arousal threshold — the daemon asks the sleeper directly.
SHUTDOWN = "kapanis"

Flag = bool | Callable[[], bool]


def _flag(value: Flag) -> bool:
    try:
        return bool(value() if callable(value) else value)
    except Exception:
        return False


class SleepDaemon:
    """Owns the switch and the rhythm; runs every kind of sleep on its own thread."""

    def __init__(
        self,
        store: Any,
        sessions_dir: Path,
        state_dir: Path,
        *,
        clock: Clock | None = None,
        hub: Any = None,
        caches: Callable[[], int] | None = None,
        model: Callable[[str], str] | None = None,
        local_model: Flag = True,
        cloud_ok: Flag = False,
        enabled: Flag = True,
        interval_s: float = TICK_SECONDS,
        rhythm: sleep.Rhythm | None = None,
    ) -> None:
        self.store = store
        self.sessions_dir = Path(sessions_dir)
        self.state_dir = Path(state_dir)
        self.clock = clock or wall_clock
        # Live event sink (web.server.Hub or anything with `emit`): every
        # night event goes to the browser as `{"type": "gece", "olay": ...}`,
        # the shape night.js already consumes.
        self.hub = hub
        self.caches = caches
        # The distillation model and the two facts the privacy gate needs.
        # Callables, because the configured model and the consent can change
        # while the daemon runs; they are read when a night starts.
        self.model = model
        self._local_model = local_model
        self._cloud_ok = cloud_ok
        self._enabled = enabled
        self.interval_s = float(interval_s)
        self.watermark = self.state_dir / WATERMARK_FILE

        self.rhythm = rhythm or rhythm_read(self.state_dir)
        self.switch = sleep.SleepSwitch(clock=self.clock, rhythm=self.rhythm)
        self._lock = threading.RLock()

        now = self.clock()
        # Booting is the user's doing: the daemon comes up awake, with the
        # idle counter at zero.
        self._last_active = now
        self._hour_start = now
        self._active_hour = True

        self._sleeper: sleep.Sleeper | None = None
        self._last_report: sleep.NightReport | None = None
        self._distil_note = ""
        debt = sleep._debt_read(self.state_dir)      # noqa: SLF001 - same module family
        self._last_night_end = parse(debt.get("ts"))
        # A finished night survives a restart as rest: otherwise a relaunch
        # would sleep again seven minutes after the user left.
        self._rested_until: datetime | None = (
            self._last_night_end + timedelta(hours=REST_HOURS)
            if self._last_night_end is not None and not int(debt.get("devreden") or 0)
            else None)
        self._last_micro: datetime | None = None
        self._micro_report: Any = None
        self._last_local: datetime | None = None
        self._local_report: Any = None
        self._pressure = sleep.Pressure()

        self._logs: dict[str, night_events.NightLog] = {}
        self._journaled = 0
        self._thread: threading.Thread | None = None
        self._stopping = False
        self._kick = threading.Event()

    # -- lifecycle -----------------------------------------------------

    def start(self) -> None:
        """Start the watchman thread. A second call is a no-op."""
        global _ACTIVE
        if self._thread is not None and self._thread.is_alive():
            return
        self._stopping = False
        self._kick.clear()
        self._thread = threading.Thread(target=self._run, daemon=True,
                                        name="dornick-uyku")
        self._thread.start()
        _ACTIVE = self

    def stop(self, timeout: float = 5.0) -> bool:
        """Ask a running night to stop and join the thread.

        Returns whether the thread is gone. The night finishes its running
        unit (well under the timeout, measured in tests/test_sleep.py) and
        starts no other; what is left becomes debt, as with any waking.
        """
        global _ACTIVE
        self._stopping = True
        with self._lock:
            sleeper = self._sleeper
        if sleeper is not None:
            sleeper.wake(SHUTDOWN)
        self._kick.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout)
        if _ACTIVE is self:
            _ACTIVE = None
        return thread is None or not thread.is_alive()

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def night_running(self) -> bool:
        return self._sleeper is not None

    def _run(self) -> None:
        while not self._stopping:
            try:
                self.tick()
            except Exception:
                pass            # one bad sample must not kill the watchman
            if self._stopping:
                break
            self._kick.wait(self.interval_s)
            self._kick.clear()

    def poke(self) -> None:
        """Re-evaluate now rather than on the next tick (an OS event arrived)."""
        self._kick.set()

    # -- stimuli (any thread) ------------------------------------------

    def user_active(self) -> None:
        """Orexin: the user is here. Pins AWAKE and wakes a running night now."""
        with self._lock:
            self._last_active = self.clock()
            self._active_hour = True
            self.switch.user_active(True)
            sleeper = self._sleeper
            self._journal()
        if sleeper is not None:
            sleeper.wake("kullanici")

    def wake(self, reason: str, *, writes: bool = False) -> bool:
        """An external stimulus. Whether it wakes us is `sleep.wakes_us`'s call."""
        with self._lock:
            woke = self.switch.stimulus(reason, writes=writes)
            sleeper = self._sleeper
            self._journal()
        if woke and sleeper is not None:
            sleeper.wake(reason)
        return woke

    def caffeine(self, hours: float = sleep.CAFFEINE_HOURS) -> None:
        """"Don't sleep now." The threshold rises; the pressure stays honest."""
        with self._lock:
            self.switch.caffeine(hours)

    def os_suspended(self) -> None:
        """The machine is going to sleep (WM_POWERBROADCAST suspend)."""
        with self._lock:
            self.switch.os_suspended()

    def os_resumed(self) -> timedelta:
        """Back from suspend: the gap is booked as slept, and the rhythm is re-read now."""
        with self._lock:
            gap = self.switch.os_resumed()
        self.poke()
        return gap

    def timezone_shifted(self, hours: int) -> None:
        """Jet lag: the histogram moves and distrusts itself for three days."""
        with self._lock:
            self.rhythm.shift_timezone(hours)
            rhythm_write(self.state_dir, self.rhythm)

    # -- measurement ---------------------------------------------------

    def enabled(self) -> bool:
        """The user's switch and the bench's ablation flag, together."""
        return switches.ACTIVE.weave and _flag(self._enabled)

    def idle_minutes(self, now: datetime | None = None) -> float:
        now = now or self.clock()
        return max(0.0, (now - self._last_active).total_seconds() / 60.0)

    def measure(self) -> sleep.Pressure:
        """S, counted from the store — never a feeling."""
        self._pressure = sleep.pressure(self.store, self.sessions_dir,
                                        watermark=self.watermark, clock=self.clock)
        return self._pressure

    def debt(self) -> tuple[float, int]:
        """(hours since the last night, un-replayed sessions).

        Wall time the machine spent suspended is subtracted: a laptop closed
        on Friday and opened on Monday has not gone three days without a
        night, and the micro/local decisions must not think so.
        """
        hours, pending = awake.sleep_debt(self.sessions_dir, clock=self.clock,
                                          watermark=self.watermark)
        since = self.clock() - timedelta(hours=hours)
        offline = self.switch.offline_since(since).total_seconds() / 3600.0
        return max(0.0, hours - offline), pending

    def next_night(self, now: datetime | None = None) -> str:
        """The next hour the rhythm expects the user gone; "" while it does not know."""
        now = now or self.clock()
        if self.rhythm.days < 7:
            return ""
        for ahead in range(0, 24):
            candidate = now + timedelta(hours=ahead)
            if self.rhythm.probability(candidate) < 0.5:
                return candidate.replace(minute=0, second=0, microsecond=0).isoformat(
                    timespec="minutes")
        return ""

    # -- the tick ------------------------------------------------------

    def tick(self) -> sleep.State:
        """One sample: learn the hour, drop orexin if away, step the switch, act.

        Synchronous on purpose — the thread calls it, and so can a test with
        an injected clock, without a thread at all.
        """
        now = self.clock()
        self._learn_rhythm(now)
        if not self.enabled() or self.switch.suspended_at is not None:
            return self.switch.state

        idle = self.idle_minutes(now)
        with self._lock:
            if idle >= IDLE_MINUTES and self.switch.orexin >= 1.0:
                self.switch.user_active(False)

        pressure = self.measure()
        hours, pending = self.debt()
        with self._lock:
            state = self.switch.step(self._fed(pressure.total, hours, now),
                                     idle_minutes=idle)
            self._journal()

        if state is sleep.State.ASLEEP:
            self._night()
        elif state is sleep.State.AWAKE and self.switch.orexin < 1.0:
            if (awake.should_micro_sleep(idle_minutes=idle, pressure=pressure.total,
                                         hours_since_night=hours)
                    and self._micro_due()):
                self._micro(pressure)

        if (self.switch.state is not sleep.State.ASLEEP
                and awake.should_local_sleep(hours, pending) and self._local_due(now)):
            self._local()
        return self.switch.state

    def _fed(self, total: float, hours: float, now: datetime) -> float:
        """What the switch is told. The measured S is reported as it is."""
        if self._rested_until is not None and now < self._rested_until:
            return 0.0
        if hours >= INSURANCE_HOURS:
            return max(total, sleep.UPPER_THRESHOLD)
        return total

    def _learn_rhythm(self, now: datetime) -> None:
        """One observation per hour lived: was the user around in it?"""
        if (now.date(), now.hour) == (self._hour_start.date(), self._hour_start.hour):
            return
        with self._lock:
            self.rhythm.observe(self._hour_start, active=self._active_hour)
            self._hour_start = now
            self._active_hour = self.idle_minutes(now) < IDLE_MINUTES
            rhythm_write(self.state_dir, self.rhythm)

    # -- the night -----------------------------------------------------

    def _night(self) -> sleep.NightReport | None:
        sleeper = sleep.Sleeper(
            self.store, self.sessions_dir, clock=self.clock,
            watermark=self.watermark, state_dir=self.state_dir,
            rhythm=self.rhythm, events=self._night_event, caches=self.caches)
        with self._lock:
            self._sleeper = sleeper
            # A stimulus that landed between the step and this line: the
            # switch already left ASLEEP, the sleeper must not start a unit.
            if self.switch.state is not sleep.State.ASLEEP or self._stopping:
                sleeper.wake(self._last_reason() or SHUTDOWN)
        model = self._night_model()
        try:
            report = sleeper.run(model=model, max_cycles=MAX_CYCLES,
                                 budget_s=NIGHT_BUDGET_SECONDS)
        except Exception as exc:
            report = sleep.NightReport(woke_reason=f"hata: {exc}")
        finally:
            with self._lock:
                self._sleeper = None
        now = self.clock()
        with self._lock:
            self._last_report = report
            self._last_night_end = now
            if not report.woke_reason:
                self._rested_until = now + timedelta(hours=REST_HOURS)
                self.switch.night_over("gece bitti")
            elif self.switch.state is sleep.State.ASLEEP:
                # Stopped by something that is not a stimulus (shutdown, an
                # error): the switch did not see it, so it is told here.
                self.switch.night_over(report.woke_reason)
            self._journal()
        return report

    def _night_event(self, kind: str, data: dict[str, Any]) -> None:
        """Every night event goes to the file and to the live hub; a cycle
        boundary is also where the switch is re-sampled (roadmap 3.10.4)."""
        self._emit(kind, data)
        if kind != "uyku.dongu" or int(data.get("no") or 0) <= 1:
            return
        sleeper = self._sleeper
        if sleeper is None:
            return
        pressure = self.measure()
        hours, _pending = self.debt()
        with self._lock:
            state = self.switch.step(self._fed(pressure.total, hours, self.clock()))
            self._journal()
        if state is not sleep.State.ASLEEP:
            sleeper.wake(self._last_reason() or "ritim")

    def _night_model(self) -> Callable[[str], str] | None:
        """The distillation model, or None with the reason the gate gave."""
        self._distil_note = distil.gate(
            self.model, local_model=_flag(self._local_model),
            cloud_ok=_flag(self._cloud_ok))
        return None if self._distil_note else self.model

    def _last_reason(self) -> str:
        return self.switch.transitions[-1].reason if self.switch.transitions else ""

    # -- micro-sleep and local sleep -----------------------------------

    def _micro_due(self) -> bool:
        """One nap per idle stretch: a second one would find nothing new."""
        return self._last_micro is None or self._last_micro < self._last_active

    def _micro(self, pressure: sleep.Pressure) -> None:
        self._emit("mikro.basladi", {"basinc": pressure.total})
        try:
            report = awake.micro_sleep(self.store, self.sessions_dir, clock=self.clock,
                                       watermark=self.watermark,
                                       budget_s=awake.MICRO_BUDGET_SECONDS)
        except Exception:
            report = None
        self._last_micro = self.clock()
        self._micro_report = report
        self._emit("mikro.bitti", {"tamamlanan": report.replayed if report else 0})

    def _local_due(self, now: datetime) -> bool:
        return (self._last_local is None
                or now - self._last_local >= timedelta(minutes=awake.REGION_REFRESH_MINUTES))

    def _local(self) -> None:
        self._emit("yerel.basladi", {"bolge": "soguk"})
        try:
            report = awake.local_sleep(self.store, clock=self.clock, caches=self.caches)
        except Exception:
            report = None
        self._last_local = self.clock()
        self._local_report = report
        self._emit("yerel.bitti", {
            "kuculen": report.shrunk_edges if report else 0,
            "atlanan": report.skipped_active if report else 0})

    # -- sinks ---------------------------------------------------------

    def _emit(self, kind: str, data: dict[str, Any]) -> None:
        """One event, two sinks: the night file and the live hub."""
        day = self.clock().date().isoformat()
        log = self._logs.get(day)
        if log is None:
            self._logs.clear()          # one open night at a time
            log = night_events.NightLog(night_events.night_path(self.state_dir, day),
                                        self.clock)
            if self.hub is not None:
                hub = self.hub
                log.listeners.append(
                    lambda event: hub.emit({"type": "gece", "olay": event}))
            self._logs[day] = log
        try:
            log.emit(kind, **data)
        except night_events.SchemaError:
            raise
        except Exception:
            pass                        # a lost event is not a lost night

    def _journal(self) -> None:
        """Every switch transition to `uyku_gunlugu.jsonl` (roadmap 3.10.8)."""
        fresh = self.switch.transitions[self._journaled:]
        if not fresh:
            return
        self._journaled = len(self.switch.transitions)
        try:
            path = self.state_dir / JOURNAL_FILE
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as fh:
                for t in fresh:
                    fh.write(json.dumps({
                        "ts": t.at.isoformat(timespec="milliseconds"),
                        "eski": t.old.value, "yeni": t.new.value,
                        "sebep": t.reason, "S": self._pressure.as_dict()},
                        ensure_ascii=False) + "\n")
        except OSError:
            pass

    # -- status --------------------------------------------------------

    def status(self) -> dict[str, Any]:
        """What GET /api/uyku returns, plus the state the watchman holds."""
        now = self.clock()
        pressure = self.measure()
        hours, pending = self.debt()
        try:
            hot = self.store.hot_share()
        except Exception:
            hot = 0.0
        report = self._last_report
        return {
            "basinc": pressure.as_dict(),
            "esik": {"ust": sleep.UPPER_THRESHOLD, "alt": sleep.LOWER_THRESHOLD},
            "borc": {"saat": round(hours, 2), "oturum": pending},
            "sicak_oran": hot,
            "durum": self.switch.state.value,
            "acik": self.enabled(),
            "kosuyor": self.running,
            "oreksin": self.switch.orexin,
            "bosta_dk": round(self.idle_minutes(now), 1),
            "askida": self.switch.suspended_at is not None,
            "kafein": (self.switch.caffeine_until.isoformat(timespec="minutes")
                       if self.switch.caffeine_until and now < self.switch.caffeine_until
                       else ""),
            "dinlenmis": (self._rested_until.isoformat(timespec="minutes")
                          if self._rested_until and now < self._rested_until else ""),
            "ritim": {"gun": round(self.rhythm.days, 2),
                      "guven": self.rhythm.confidence,
                      "simdi": self.rhythm.probability(now)},
            "sonraki_gece": self.next_night(now),
            "son_gece": {
                "bitti": (self._last_night_end.isoformat(timespec="minutes")
                          if self._last_night_end else ""),
                "rapor": report.as_dict() if report else {},
                "damitma": self._distil_note,
            },
            "mikro": self._micro_report.as_dict() if self._micro_report else {},
            "yerel": self._local_report.as_dict() if self._local_report else {},
        }


# -- the rhythm on disk ------------------------------------------------


def rhythm_read(state_dir: Path | None) -> sleep.Rhythm:
    if state_dir is None:
        return sleep.Rhythm()
    try:
        data = json.loads((Path(state_dir) / RHYTHM_FILE).read_text("utf-8"))
        return sleep.Rhythm.from_dict(data) if isinstance(data, dict) else sleep.Rhythm()
    except (OSError, ValueError, TypeError):
        return sleep.Rhythm()


def rhythm_write(state_dir: Path | None, rhythm: sleep.Rhythm) -> None:
    if state_dir is None:
        return
    try:
        path = Path(state_dir) / RHYTHM_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(rhythm.as_dict(), ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


# -- the process-wide hook the turn loop calls -------------------------
#
# The agent loop does not hold a reference to the daemon (lanes build
# agents of their own); it calls the module. One daemon per process: the
# bridge starts it after the mind opens and stops it on shutdown.

_ACTIVE: SleepDaemon | None = None


def active() -> SleepDaemon | None:
    return _ACTIVE


def user_active() -> None:
    """The user did something. One line at the turn start; nothing if no daemon."""
    daemon = _ACTIVE
    if daemon is not None:
        daemon.user_active()


def wake(reason: str, *, writes: bool = False) -> bool:
    daemon = _ACTIVE
    return daemon.wake(reason, writes=writes) if daemon is not None else False
