"""The sleep daemon: the watchman that finally puts the product to sleep.

The night, the switch, the rhythm, micro-sleep and local sleep were all
built and measured — and nothing in the product constructed them. These
tests drive the daemon with an injected clock and a synchronous `tick()`;
only the shutdown test starts the real thread, because a night that must
be interrupted from another thread is the thing being proven there.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from dornick import desktop
from dornick.config import Config, SleepConfig
from dornick.desktop import Bridge
from dornick.events import EventLog
from dornick.recall import awake, night_events, open_store, sleep, switches, weave
from dornick.recall import daemon as daemon_module
from dornick.recall.daemon import SleepDaemon
from dornick.recall.sleep import State

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


class Hub:
    """The live sink: what the browser would see over SSE."""

    def __init__(self) -> None:
        self.events: list[dict] = []
        self.on = None

    def emit(self, event: dict) -> None:
        self.events.append(event)
        if self.on is not None:
            self.on(event)

    def kinds(self) -> list[str]:
        return [e["olay"]["tur"] for e in self.events if e.get("type") == "gece"]

    def find(self, kind: str) -> dict:
        return next(e["olay"] for e in self.events
                    if e.get("type") == "gece" and e["olay"]["tur"] == kind)


@pytest.fixture()
def clock() -> Clock:
    return Clock(MONDAY)


@pytest.fixture()
def state(tmp_path: Path) -> Path:
    folder = tmp_path / ".dornick"
    (folder / "sessions").mkdir(parents=True)
    return folder


@pytest.fixture()
def store(state: Path, clock: Clock):
    s = open_store(state / "mind", clock=clock)
    yield s
    s.close()


def _session(state: Path, name: str, node_ids, clock: Clock,
             outcome: str = "basarili") -> None:
    log = EventLog(state / "sessions" / f"{name}.jsonl", clock=clock.text)
    log.note("session_start", session_id=name)
    for node_id in node_ids:
        clock.advance(seconds=1)
        log.note("mind_open", memory_id=node_id)
    log.note("sonuc", sonuc=outcome)
    log.close()


def _pressurise(store, n: int = 10) -> list:
    """A dense mesh: strengthening per node well above the upper threshold."""
    nodes = [store.remember(f"Saha notu {i}.", kind="fact") for i in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            store.link(nodes[i].id, nodes[j].id, weight=1.0, reason="elle")
    assert sleep.pressure(store).total > sleep.UPPER_THRESHOLD
    return nodes


def _last_night(state: Path, clock: Clock, hours_ago: float) -> None:
    weave._write_watermark(state / daemon_module.WATERMARK_FILE, {          # noqa: SLF001
        "islenen": {},
        "son_kosu": (clock() - timedelta(hours=hours_ago)).isoformat(timespec="milliseconds")})


def _daemon(store, state: Path, clock: Clock, hub: Hub | None = None, **kw) -> SleepDaemon:
    return SleepDaemon(store, state / "sessions", state, clock=clock,
                       hub=hub if hub is not None else Hub(), **kw)


def _fall_asleep(daemon: SleepDaemon, clock: Clock) -> State:
    """The user leaves; orexin drops after five minutes; two minutes of SLEEPY."""
    clock.advance(minutes=daemon_module.IDLE_MINUTES + 1)
    assert daemon.tick() is State.SLEEPY
    clock.advance(minutes=sleep.SLEEPY_MINUTES)
    return daemon.tick()          # ASLEEP → the night runs inside this tick


# -- the night ---------------------------------------------------------


def test_pressure_puts_it_to_sleep_and_the_night_reaches_both_sinks(
        store, state, clock) -> None:
    nodes = _pressurise(store)
    for i in range(4):
        _session(state, f"s{i}", [nodes[i].id], clock)
    _last_night(state, clock, hours_ago=1)
    hub = Hub()
    daemon = _daemon(store, state, clock, hub)

    assert daemon.tick() is State.AWAKE          # the user just launched it
    after = _fall_asleep(daemon, clock)

    # The night ran and ended on its own; the switch is coming out of it.
    assert after is State.WAKING
    kinds = hub.kinds()
    assert kinds[0] == "uyku.basladi"
    assert "uyku.dongu" in kinds
    assert kinds[-1] == "uyku.bitti"
    assert daemon.tick() is State.AWAKE          # inertia over

    # The file sink carries the same events, in the same order, and they
    # all validate against the frozen schema.
    path = night_events.night_path(state, clock().date().isoformat())
    replayed = [e["tur"] for e in night_events.replay(path)]
    assert replayed == kinds
    report = daemon.status()["son_gece"]["rapor"]
    assert report["replayed"] == 4 and report["carried"] == 0

    # A finished night rests: the pressure the downscale leaves behind does
    # not put the graph through another night three minutes later.
    clock.advance(hours=1)
    assert daemon.tick() is State.AWAKE
    assert kinds.count("uyku.basladi") == 1
    assert daemon.status()["dinlenmis"]


def _one_unit(store, sessions_dir, *, clock=None, watermark=None, **_):
    """A night pass that processes exactly one session: the atomic unit."""
    status = weave._read_watermark(watermark)                          # noqa: SLF001
    pending = sorted(p.stem for p in Path(sessions_dir).glob("*.jsonl")
                     if p.stem not in status["islenen"])
    report = weave.NightReport()
    if pending:
        status["islenen"][pending[0]] = weave._stamp(clock)            # noqa: SLF001
        report.replayed = 1
    report.carried_over = max(0, len(pending) - 1)
    status["son_kosu"] = weave._stamp(clock)                           # noqa: SLF001
    weave._write_watermark(watermark, status)                          # noqa: SLF001
    return report


def test_user_activity_wakes_the_night_and_the_rest_is_carried(
        store, state, clock, monkeypatch) -> None:
    monkeypatch.setattr(weave, "night_pass", _one_unit)
    nodes = _pressurise(store)
    for i in range(6):
        _session(state, f"s{i}", [nodes[i].id], clock)
    _last_night(state, clock, hours_ago=1)
    hub = Hub()
    daemon = _daemon(store, state, clock, hub)

    # The user comes back during the first cycle — from the UI thread, as
    # it were: the hub listener is where the event surfaces.
    def come_back(event: dict) -> None:
        if event.get("type") == "gece" and event["olay"]["tur"] == "uyku.dongu":
            hub.on = None
            daemon.user_active()
    hub.on = come_back

    assert _fall_asleep(daemon, clock) is State.AWAKE     # orexin pinned it
    woke = hub.find("uyku.uyandi")
    assert woke["sebep"] == "kullanici"
    assert woke["dongu"] == 1 and woke["tamamlanan"] == 1
    assert woke["devreden"] == 5
    assert "uyku.bitti" not in hub.kinds()
    assert json.loads((state / "uyku_borcu.json").read_text("utf-8"))["devreden"] == 5
    assert daemon.status()["dinlenmis"] == ""             # interrupted, not rested

    # The next idle window resumes the debt and this time finishes it.
    assert _fall_asleep(daemon, clock) is State.WAKING
    assert hub.kinds().count("uyku.basladi") == 2
    assert hub.kinds()[-1] == "uyku.bitti"
    assert json.loads((state / "uyku_borcu.json").read_text("utf-8"))["devreden"] == 0


def test_the_switch_off_means_no_night(store, state, clock) -> None:
    nodes = _pressurise(store)
    _session(state, "s0", [nodes[0].id], clock)
    hub = Hub()
    daemon = _daemon(store, state, clock, hub, enabled=False)
    clock.advance(minutes=30)
    for _ in range(5):
        assert daemon.tick() is State.AWAKE
        clock.advance(minutes=3)
    assert hub.events == []
    assert daemon.status()["acik"] is False

    # The bench's ablation flag is the same door.
    live = _daemon(store, state, clock, hub, enabled=True)
    with switches.disabled("weave"):
        clock.advance(minutes=30)
        for _ in range(5):
            assert live.tick() is State.AWAKE
            clock.advance(minutes=3)
    assert hub.events == []


def test_a_night_a_day_even_at_zero_pressure(store, state, clock) -> None:
    """The daily insurance: no watermark, no pressure, the user away — one night."""
    hub = Hub()
    daemon = _daemon(store, state, clock, hub)
    assert sleep.pressure(store).total == 0.0
    assert _fall_asleep(daemon, clock) is State.WAKING
    assert hub.kinds()[0] == "uyku.basladi" and hub.kinds()[-1] == "uyku.bitti"


# -- micro-sleep and local sleep ---------------------------------------


def test_micro_sleep_runs_only_when_awake_says_so(store, state, clock,
                                                  monkeypatch) -> None:
    node = store.remember("Bir kayıt.", kind="fact")
    _session(state, "s0", [node.id], clock)
    # Overdue for a nap (≥ 12 h), not yet for the daily insurance night (20 h).
    _last_night(state, clock, hours_ago=awake.NIGHT_GAP_HOURS + 1)
    hub = Hub()
    daemon = _daemon(store, state, clock, hub)

    clock.advance(minutes=2)
    daemon.tick()                                   # orexin still up
    assert "mikro.basladi" not in hub.kinds()

    clock.advance(minutes=daemon_module.IDLE_MINUTES)
    assert daemon.tick() is State.AWAKE             # S too small for a night
    assert hub.kinds() == ["mikro.basladi", "mikro.bitti"]
    assert hub.find("mikro.bitti")["tamamlanan"] == 1
    assert hub.find("mikro.basladi")["basinc"] > 0

    clock.advance(minutes=1)
    daemon.tick()                                   # one nap per idle stretch
    assert hub.kinds().count("mikro.basladi") == 1

    # New work, the user back and gone again — but the contract says no.
    _session(state, "s1", [node.id], clock)
    daemon.user_active()
    clock.advance(minutes=daemon_module.IDLE_MINUTES + 1)
    monkeypatch.setattr(awake, "should_micro_sleep", lambda **_: False)
    daemon.tick()
    assert hub.kinds().count("mikro.basladi") == 1
    monkeypatch.undo()
    daemon.tick()
    assert hub.kinds().count("mikro.basladi") == 2


def test_local_sleep_for_the_machine_that_never_idles(store, state, clock) -> None:
    node = store.remember("Bir kayıt.", kind="fact")
    for i in range(awake.DEBT_SESSIONS):
        _session(state, f"s{i}", [node.id], clock)
    hub = Hub()
    daemon = _daemon(store, state, clock, hub)     # no watermark: 48 h of debt
    daemon.user_active()                           # and the user never leaves
    daemon.tick()
    assert hub.kinds() == ["yerel.basladi", "yerel.bitti"]
    assert "uyku.basladi" not in hub.kinds()        # orexin: no night, no nap
    clock.advance(minutes=1)
    daemon.user_active()
    daemon.tick()
    assert hub.kinds().count("yerel.basladi") == 1  # region refresh is ten minutes


# -- zeitgebers ----------------------------------------------------------


def test_suspend_and_resume_do_not_charge_debt(store, state, clock) -> None:
    _last_night(state, clock, hours_ago=0)
    _pressurise(store)
    hub = Hub()
    daemon = _daemon(store, state, clock, hub)
    hours, _pending = daemon.debt()
    assert hours < 0.1

    daemon.os_suspended()
    clock.advance(hours=60)
    assert daemon.tick() is State.AWAKE            # nothing moves, nothing runs
    assert hub.events == []
    assert daemon.status()["askida"] is True

    gap = daemon.os_resumed()
    assert gap == timedelta(hours=60)
    hours, pending = daemon.debt()
    assert hours < 1.0                             # the lid was closed, not the night skipped
    assert not awake.should_local_sleep(hours, pending)
    daemon.tick()
    assert "yerel.basladi" not in hub.kinds()
    assert daemon.status()["askida"] is False


def test_the_rhythm_is_learned_by_the_hour_and_kept_on_disk(store, state, clock) -> None:
    daemon = _daemon(store, state, clock)
    assert daemon.rhythm.days == 0.0
    clock.advance(hours=1)
    daemon.tick()                                   # the 09:00 hour closes: the user was here
    assert daemon.rhythm.days > 0.0
    assert daemon.rhythm.counts[MONDAY.weekday()][MONDAY.hour] == 1.0
    saved = json.loads((state / daemon_module.RHYTHM_FILE).read_text("utf-8"))
    assert saved["counts"][MONDAY.weekday()][MONDAY.hour] == 1.0

    # The next daemon starts from what this one learned.
    again = _daemon(store, state, clock)
    assert again.rhythm.counts == daemon.rhythm.counts


# -- the thread -----------------------------------------------------------


def _slow_unit(store, sessions_dir, *, clock=None, watermark=None, **_):
    time.sleep(0.15)
    report = weave.NightReport()
    report.replayed = 1
    report.carried_over = 1        # never runs out: only stop() ends it
    return report


def _wait(condition, seconds: float = 3.0) -> bool:
    deadline = time.perf_counter() + seconds
    while time.perf_counter() < deadline:
        if condition():
            return True
        time.sleep(0.01)
    return False


def test_shutdown_stops_a_running_night_within_the_timeout(
        store, state, clock, monkeypatch) -> None:
    monkeypatch.setattr(weave, "night_pass", _slow_unit)
    _pressurise(store)
    _last_night(state, clock, hours_ago=1)
    hub = Hub()
    daemon = _daemon(store, state, clock, hub, interval_s=0.01)
    clock.advance(minutes=daemon_module.IDLE_MINUTES + 1)
    daemon.start()
    assert daemon_module.active() is daemon
    assert _wait(lambda: daemon.switch.state is State.SLEEPY)
    clock.advance(minutes=sleep.SLEEPY_MINUTES)
    assert _wait(lambda: daemon.night_running)

    started = time.perf_counter()
    assert daemon.stop(timeout=5.0) is True
    assert time.perf_counter() - started < 5.0
    assert not daemon.running
    assert daemon_module.active() is None
    woke = hub.find("uyku.uyandi")
    assert woke["sebep"] == daemon_module.SHUTDOWN
    assert daemon.switch.state is not State.ASLEEP


def test_the_turn_loop_reaches_the_daemon_through_the_module(store, state, clock) -> None:
    daemon = _daemon(store, state, clock, interval_s=60.0)
    daemon.switch.user_active(False)
    daemon.start()
    try:
        clock.advance(minutes=30)
        daemon_module.user_active()              # the one line loop.py calls
        assert daemon.switch.orexin == 1.0
        assert daemon.idle_minutes() == 0.0
        assert daemon_module.wake("otomasyon") is False
    finally:
        daemon.stop()
    assert daemon_module.active() is None
    daemon_module.user_active()                  # no daemon: nothing, no error


# -- status ---------------------------------------------------------------


def test_status_has_the_shape_the_ui_reads(store, state, clock) -> None:
    daemon = _daemon(store, state, clock)
    status = daemon.status()
    # What /api/uyku returned before the daemon existed…
    assert set(status["basinc"]) == {"strengthening", "debt", "heat", "total"}
    assert status["esik"] == {"ust": sleep.UPPER_THRESHOLD, "alt": sleep.LOWER_THRESHOLD}
    assert set(status["borc"]) == {"saat", "oturum"}
    assert "sicak_oran" in status
    # …plus what only the watchman knows.
    assert status["durum"] == "uyanik"
    assert status["acik"] is True and status["kosuyor"] is False
    assert status["oreksin"] == 1.0
    assert status["sonraki_gece"] == ""          # a new install does not know yet
    assert set(status["son_gece"]) == {"bitti", "rapor", "damitma"}
    assert set(status["ritim"]) == {"gun", "guven", "simdi", "saatler"}
    assert status["ritim"]["saatler"] == []       # nor the usual hours
    for key in ("bosta_dk", "askida", "kafein", "dinlenmis", "mikro", "yerel"):
        assert key in status
    json.dumps(status)                           # it goes over the wire as JSON


def test_the_distil_model_passes_the_privacy_gate_only(store, state, clock) -> None:
    calls: list[str] = []
    model = lambda prompt: calls.append(prompt) or ""       # noqa: E731
    hosted = _daemon(store, state, clock, model=model, local_model=False, cloud_ok=False)
    assert hosted._night_model() is None                     # noqa: SLF001
    assert "bulut onayı" in hosted._distil_note              # noqa: SLF001
    consented = _daemon(store, state, clock, model=model, local_model=False, cloud_ok=True)
    assert consented._night_model() is model                 # noqa: SLF001
    local = _daemon(store, state, clock, model=model, local_model=lambda: True)
    assert local._night_model() is model                     # noqa: SLF001


# -- the bridge -------------------------------------------------------------


class _Hub:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def emit(self, ev: dict) -> None:
        self.events.append(ev)


class FakeDaemon:
    """The daemon's surface as the bridge sees it."""

    def __init__(self, store, sessions_dir, state_dir, **kw) -> None:
        self.args = (store, sessions_dir, state_dir)
        self.kw = kw
        self.started = False
        self.stopped: float | None = None
        self.suspended = 0

    def start(self) -> None:
        self.started = True

    def stop(self, timeout: float = 5.0) -> bool:
        self.stopped = timeout
        return True

    def status(self) -> dict:
        return {"durum": "uyanik"}

    def os_suspended(self) -> None:
        self.suspended += 1

    def os_resumed(self) -> None:
        self.suspended -= 1


def test_the_bridge_starts_the_daemon_after_the_mind_and_stops_it_on_teardown(
        tmp_path: Path) -> None:
    config = Config(workspace=tmp_path, state_dir=tmp_path / ".dornick")
    config.model = replace(config.model, base_url="http://localhost:1234/v1")
    mind = SimpleNamespace(store=object(), clear_caches=lambda: 3)
    bridge = Bridge(_Hub(), asyncio.new_event_loop())

    daemon = bridge.start_sleep(config, mind, factory=FakeDaemon)
    assert daemon.started
    assert daemon.args == (mind.store, config.sessions_dir, config.state_dir)
    assert daemon.kw["hub"] is bridge.hub
    assert daemon.kw["caches"] is mind.clear_caches
    assert daemon.kw["model"] == bridge._night_model              # noqa: SLF001
    assert daemon.kw["local_model"]() is True
    assert daemon.kw["cloud_ok"]() is False                      # no consent on disk
    assert daemon.kw["enabled"]() is True
    assert bridge.sleep_status() == {"durum": "uyanik"}

    # The settings page saves: the daemon reads the new switch at once.
    bridge.reload(replace(config, sleep=SleepConfig(uyku_acik=False)))
    assert daemon.kw["enabled"]() is False

    # The OS power broadcast reaches the daemon through the frame shell hook.
    desktop._power_broadcast(desktop._PBT_APMSUSPEND)             # noqa: SLF001
    assert daemon.suspended == 1
    desktop._power_broadcast(desktop._PBT_APMRESUMEAUTOMATIC)     # noqa: SLF001
    assert daemon.suspended == 0

    assert bridge.stop_sleep() is True
    assert daemon.stopped == 5.0
    assert bridge.sleeper is None
    assert bridge.sleep_status() is None
    assert desktop._POWER_LISTENER is None                        # noqa: SLF001


# -- the composer's sleep commands ------------------------------------------
#
# `/uyu`, `/uyuma` and `/yorgun` reach the daemon through the bridge and
# two POST routes. The daemon side is proven here with the synchronous
# tick; the wire is in tests/test_web.py.


def test_sleep_now_runs_a_night_on_the_next_tick(store, state, clock, monkeypatch) -> None:
    monkeypatch.setattr(weave, "night_pass", _one_unit)
    nodes = _pressurise(store)
    for i in range(2):
        _session(state, f"s{i}", [nodes[i].id], clock)
    hub = Hub()
    daemon = _daemon(store, state, clock, hub)
    assert daemon.tick() is State.AWAKE          # the user is here, no idle time

    # The user asks for the night: the switch moves at once, without the
    # thresholds or the five idle minutes.
    answer = daemon.sleep_now()
    assert answer == {"ok": True, "durum": "uyuyor"}
    assert daemon.status()["durum"] == "uyuyor"
    assert daemon.sleep_now() == {"ok": False, "durum": "uyuyor", "error": "Zaten uyuyor."}

    # The next tick runs the night instead of stepping the switch back.
    clock.advance(seconds=daemon_module.TICK_SECONDS)
    after = daemon.tick()
    assert after in (State.WAKING, State.AWAKE)
    assert hub.kinds()[0] == "uyku.basladi"
    assert not daemon.night_running
    assert daemon.status()["son_gece"]["rapor"]["replayed"] >= 1
    # Journalled like any transition, with the user's reason.
    journal = (state / daemon_module.JOURNAL_FILE).read_text("utf-8").splitlines()
    assert any(json.loads(row)["sebep"] == "kullanici istedi" for row in journal)


def test_sleep_now_yields_to_the_user_and_to_the_switch(store, state, clock) -> None:
    hub = Hub()
    daemon = _daemon(store, state, clock, hub)
    daemon.tick()
    assert daemon.sleep_now()["ok"] is True
    # A message lands before the tick: orexin wins and no night starts.
    daemon.user_active()
    assert daemon.tick() is State.AWAKE
    assert hub.events == []
    assert daemon.status()["durum"] == "uyanik"

    # Caffeine is spent by an explicit "sleep now" — the later word wins.
    daemon.caffeine()
    assert daemon.status()["kafein"]
    assert daemon.sleep_now()["ok"] is True
    assert daemon.status()["kafein"] == ""

    # The user's switch off: refused with the reason, nothing moves.
    off = _daemon(store, state, clock, Hub(), enabled=False)
    assert off.sleep_now() == {"ok": False, "durum": "uyanik", "error": "Gece uykusu kapalı."}
    assert off.tick() is State.AWAKE


def test_caffeine_holds_the_night_off_and_wakes_a_running_one(
        store, state, clock, monkeypatch) -> None:
    monkeypatch.setattr(weave, "night_pass", _one_unit)
    # Above the threshold, below the doubled one caffeine sets (n=6 → S≈3.2).
    nodes = _pressurise(store, n=6)
    for i in range(2):
        _session(state, f"s{i}", [nodes[i].id], clock)
    _last_night(state, clock, hours_ago=1)
    hub = Hub()
    daemon = _daemon(store, state, clock, hub)

    answer = daemon.caffeine()
    assert answer["ok"] is True and answer["saat"] == float(sleep.CAFFEINE_HOURS)
    assert answer["kafein"] == daemon.status()["kafein"]
    # Away and under pressure — but the threshold is out of reach.
    clock.advance(minutes=daemon_module.IDLE_MINUTES + 1)
    assert daemon.tick() is State.AWAKE
    clock.advance(minutes=sleep.SLEEPY_MINUTES)
    assert daemon.tick() is State.AWAKE
    assert hub.events == []

    # Four hours later the night comes; caffeine said during it stops it.
    clock.advance(hours=sleep.CAFFEINE_HOURS)

    def not_tonight(event: dict) -> None:
        if event.get("type") == "gece" and event["olay"]["tur"] == "uyku.dongu":
            hub.on = None
            daemon.caffeine()
    hub.on = not_tonight
    assert daemon.tick() is State.SLEEPY
    clock.advance(minutes=sleep.SLEEPY_MINUTES)
    assert daemon.tick() is State.WAKING
    assert hub.find("uyku.uyandi")["sebep"] == "kafein"


class FakeSleepingDaemon(FakeDaemon):
    def __init__(self, *a, **kw) -> None:
        super().__init__(*a, **kw)
        self.calls: list[str] = []

    def sleep_now(self) -> dict:
        self.calls.append("uyu")
        return {"ok": True, "durum": "uyuyor"}

    def caffeine(self) -> dict:
        self.calls.append("kafein")
        return {"ok": True, "durum": "uyanik", "saat": 4.0, "kafein": "2025-06-02T13:00"}


def test_the_bridge_relays_the_sleep_commands_or_refuses_without_a_daemon(
        tmp_path: Path) -> None:
    config = Config(workspace=tmp_path, state_dir=tmp_path / ".dornick")
    mind = SimpleNamespace(store=object(), clear_caches=lambda: 3)
    bridge = Bridge(_Hub(), asyncio.new_event_loop())
    # No daemon yet: an honest refusal in Turkish, not an exception.
    assert bridge.sleep_now()["ok"] is False and bridge.sleep_now()["error"]
    assert bridge.caffeine()["ok"] is False and bridge.caffeine()["error"]

    daemon = bridge.start_sleep(config, mind, factory=FakeSleepingDaemon)
    assert bridge.sleep_now() == {"ok": True, "durum": "uyuyor"}
    assert bridge.caffeine()["kafein"] == "2025-06-02T13:00"
    assert daemon.calls == ["uyu", "kafein"]
    assert bridge.stop_sleep() is True
    assert bridge.sleep_now()["ok"] is False
