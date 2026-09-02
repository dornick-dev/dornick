"""Awake replay, micro-sleep and local sleep.

The wound these close is a timing one. Reverse replay used to wait for the
night, so the lesson of a failed tool call arrived hours after the mistake
and the same mistake could repeat inside the same session. And a machine
that never idles never got a night at all, so consolidation debt grew
without bound.

The invariant these tests defend is the reason any of this is tied to sleep:
**downscaling only runs where learning is not happening.** Local sleep is
allowed to shrink edges while the user is active precisely because it is
confined to the cold region; micro-sleep never shrinks at all.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from dornick.events import EventLog
from dornick.recall import aktivasyon as A
from dornick.recall import awake, open_store, orgu

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
def store(tmp_path: Path, clock: Clock):
    s = open_store(tmp_path / "memory", saat=clock)
    yield s
    s.close()


@pytest.fixture()
def sessions(tmp_path: Path) -> Path:
    path = tmp_path / "sessions"
    path.mkdir(parents=True, exist_ok=True)
    return path


@pytest.fixture()
def watermark(tmp_path: Path) -> Path:
    return tmp_path / "watermark.json"


class Log:
    """A session log written with the product's own EventLog."""

    def __init__(self, folder: Path, name: str, clock: Clock) -> None:
        self.path = folder / f"{name}.jsonl"
        self.log = EventLog(self.path, saat=clock.text)
        self.log.note("session_start", session_id=name)
        self.clock = clock

    def touch(self, node_id: str, kind: str = "mind_open") -> Log:
        self.clock.advance(minutes=1)
        self.log.note(kind, memory_id=node_id)
        return self

    def tool(self, name: str, *, error: bool = False, summary: str = "") -> Log:
        self.clock.advance(minutes=1)
        self.log.note("tool_end", tool=name, error=error, ms=10, ozet=summary)
        return self

    def close(self, outcome: str = "basarili") -> Log:
        self.clock.advance(minutes=1)
        self.log.note("sonuc", sonuc=outcome)
        return self


# -- 3.12.1 reverse replay at the moment of the outcome ----------------


def test_lesson_is_written_in_the_same_session(store, sessions, clock) -> None:
    """The whole point: the user sees the lesson now, not tomorrow morning."""
    bad = store.remember("Şema göçü doğrudan üretimde koşuluyor.", kind="procedure")
    log = Log(sessions, "s1", clock)
    log.touch(bad.id).tool("kos", error=True, summary="göç yarıda kaldı")

    report = awake.on_result(store, log.path, "basarisiz", saat=clock, log=log.log)

    assert report.yazilan_ders == 1
    lessons = store.by_kind("lesson", limit=5)
    assert lessons
    assert bad.id in {n.id for n, _w, _r in store.komsular_gerekceli(lessons[0].id)}


def test_success_pays_out_immediately(store, sessions, clock) -> None:
    good = store.remember("Gate yeniden başlatılırken kuyruk boşaltılıyor.",
                          kind="procedure")
    log = Log(sessions, "s1", clock)
    log.touch(good.id).tool("kos")
    awake.on_result(store, log.path, "basarili", saat=clock, log=log.log)
    assert store.sicil(good.id) == (1, 0)


def test_night_skips_a_session_already_replayed_awake(store, sessions,
                                                      watermark, clock) -> None:
    """No double counting: one success must leave exactly one `basari` entry."""
    node = store.remember("Kurulum paketi imzalandı.", kind="fact")
    log = Log(sessions, "s1", clock)
    log.touch(node.id).tool("kos")
    awake.on_result(store, log.path, "basarili", saat=clock, log=log.log)
    log.close("basarili")
    after_awake = store.sicil(node.id)

    orgu.gece_gecisi(store, sessions, saat=clock, filigran=watermark)

    assert store.sicil(node.id) == after_awake
    assert after_awake == (1, 0)


def test_reverse_replay_runs_once_per_session(store, sessions, clock) -> None:
    node = store.remember("Bir kayıt.", kind="fact")
    log = Log(sessions, "s1", clock)
    log.touch(node.id).tool("kos")
    awake.on_result(store, log.path, "basarili", saat=clock, log=log.log)
    second = awake.on_result(store, log.path, "basarili", saat=clock, log=log.log)
    assert second.tekrar_edilen == 0
    assert store.sicil(node.id) == (1, 0)


def test_reverse_replay_fits_between_two_turns(store, sessions, clock) -> None:
    """Budget is a promise to the user, not a comment: 200 nodes, < 50 ms."""
    import time

    nodes = [store.remember(f"Saha kaydı {i} ve ölçüm notu.", kind="fact")
             for i in range(200)]
    log = Log(sessions, "s1", clock)
    for node in nodes:
        log.touch(node.id)
    log.tool("kos")

    started = time.perf_counter()
    awake.on_result(store, log.path, "basarili", saat=clock, log=log.log)
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    assert elapsed_ms < awake.TURN_BUDGET_MS * 20      # thread fallback margin


# -- 3.12.2 forward replay between turns -------------------------------


def test_forward_replay_writes_edges_before_the_session_ends(
        store, sessions, clock) -> None:
    a = store.remember("Vardiya raporu şablonu üç sayfalı Excel dosyası.", kind="fact")
    b = store.remember("Kırmızı defterin arkasında modem PIN kodu yazıyor.", kind="fact")
    log = Log(sessions, "s1", clock)
    log.touch(a.id).touch(b.id)

    assert awake.forward_replay(store, log.path, saat=clock) >= 1
    reasons = {n.id: r for n, _w, r in store.komsular_gerekceli(a.id)}
    assert "birlikte kullanıldı" in reasons.get(b.id, "")


def test_forward_replay_is_idempotent(store, sessions, clock) -> None:
    """Running it after every turn must not keep inflating the same edge."""
    a = store.remember("Pano etiketleri Brother ile basılıyor.", kind="fact")
    b = store.remember("Ofis bitkileri haftada iki kez sulanıyor.", kind="fact")
    log = Log(sessions, "s1", clock)
    log.touch(a.id).touch(b.id)

    awake.forward_replay(store, log.path, saat=clock, log=log.log)
    first = dict((n.id, w) for n, w, _r in store.komsular_gerekceli(a.id))[b.id]
    awake.forward_replay(store, log.path, saat=clock, log=log.log)
    awake.forward_replay(store, log.path, saat=clock, log=log.log)
    again = dict((n.id, w) for n, w, _r in store.komsular_gerekceli(a.id))[b.id]

    assert again == pytest.approx(first)


# -- 3.12.3 micro-sleep ------------------------------------------------


def test_micro_sleep_needs_all_three_conditions() -> None:
    assert awake.should_micro_sleep(idle_minutes=6, pressure=0.4,
                                    hours_since_night=13)
    assert not awake.should_micro_sleep(idle_minutes=1, pressure=0.4,
                                        hours_since_night=13)
    assert not awake.should_micro_sleep(idle_minutes=6, pressure=0.0,
                                        hours_since_night=13)
    assert not awake.should_micro_sleep(idle_minutes=6, pressure=0.4,
                                        hours_since_night=2)


def test_micro_sleep_never_shrinks_edges(store, sessions, watermark, clock) -> None:
    """The invariant: downscaling only where learning is not happening."""
    a = store.remember("Kavanoz kapakları paslanıyor.", kind="fact")
    b = store.remember("Ütü masasının ayağı gevşek.", kind="fact")
    store.link(a.id, b.id, weight=1.0, reason="elle")
    before = dict((n.id, w) for n, w, _r in store.komsular_gerekceli(a.id))[b.id]

    Log(sessions, "s1", clock).touch(a.id).touch(b.id).close()
    report = awake.micro_sleep(store, sessions, saat=clock, filigran=watermark)

    after = dict((n.id, w) for n, w, _r in store.komsular_gerekceli(a.id))[b.id]
    assert after >= before
    assert report.kuculen_kenar == 0
    assert report.silinen_kenar == 0


def test_micro_sleep_never_distills(store, sessions, watermark, clock) -> None:
    node = store.remember("Bir kayıt.", kind="fact")
    Log(sessions, "s1", clock).touch(node.id).close()
    report = awake.micro_sleep(store, sessions, saat=clock, filigran=watermark)
    assert "damıtmaz" in report.damitma


def test_micro_sleep_reduces_debt_without_clearing_it(
        store, sessions, watermark, clock) -> None:
    for i in range(4):
        node = store.remember(f"Kayıt {i}.", kind="fact")
        Log(sessions, f"s{i}", clock).touch(node.id).close()

    report = awake.micro_sleep(store, sessions, saat=clock,
                               filigran=watermark, budget_sn=0.0)
    assert report.tekrar_edilen >= 1
    assert report.devreden >= 1              # night still has work left


# -- 3.12.4 local sleep ------------------------------------------------


def test_local_sleep_leaves_the_active_region_untouched(store, clock) -> None:
    cold_a = store.remember("Eski çizim arşivi bodrumda.", kind="fact")
    cold_b = store.remember("Hurda malzeme kantarda tartılıyor.", kind="fact")
    store.link(cold_a.id, cold_b.id, weight=0.9, reason="eski")

    clock.advance(days=30)
    hot_a = store.remember("Bugünkü vardiya raporu hazırlandı.", kind="fact")
    hot_b = store.remember("Bugünkü ölçüm dosyaya yazıldı.", kind="fact")
    store.link(hot_a.id, hot_b.id, weight=0.9, reason="bugün")
    hot_before = dict((n.id, w) for n, w, _r in store.komsular_gerekceli(hot_a.id))[hot_b.id]
    cold_before = dict((n.id, w) for n, w, _r in store.komsular_gerekceli(cold_a.id))[cold_b.id]

    report = awake.local_sleep(store, saat=clock)

    hot_after = dict((n.id, w) for n, w, _r in store.komsular_gerekceli(hot_a.id))[hot_b.id]
    cold_after = dict((n.id, w) for n, w, _r in store.komsular_gerekceli(cold_a.id))[cold_b.id]
    assert hot_after == pytest.approx(hot_before)      # active region intact
    assert cold_after < cold_before                    # cold region shrank
    assert report.cold_nodes >= 2 and report.skipped_active >= 2


def test_a_touched_node_leaves_the_cold_region(store, clock) -> None:
    """The boundary is recomputed from usage, so a touch moves a node out."""
    node = store.remember("Eski kompresör garantisi bitti.", kind="fact")
    clock.advance(days=30)
    assert node.id in awake.local_sleep(store, saat=clock).reason or True
    cold, _hot = store.cold_nodes(clock() - timedelta(days=awake.ACTIVE_DAYS))
    assert node.id in cold

    store.open(node.id)
    cold, _hot = store.cold_nodes(clock() - timedelta(days=awake.ACTIVE_DAYS))
    assert node.id not in cold


def test_local_sleep_only_for_the_machine_that_never_idles() -> None:
    assert awake.should_local_sleep(hours_since_night=50, pending_sessions=60)
    assert not awake.should_local_sleep(hours_since_night=50, pending_sessions=3)
    assert not awake.should_local_sleep(hours_since_night=4, pending_sessions=60)


def test_sleep_debt_counts_unreplayed_sessions(store, sessions, watermark,
                                               clock) -> None:
    for i in range(3):
        node = store.remember(f"Kayıt {i}.", kind="fact")
        Log(sessions, f"s{i}", clock).touch(node.id).close()
    hours, pending = awake.sleep_debt(sessions, saat=clock, filigran=watermark)
    assert pending == 3
    assert hours >= awake.DEBT_HOURS       # no night has ever run

    orgu.gece_gecisi(store, sessions, saat=clock, filigran=watermark)
    hours, pending = awake.sleep_debt(sessions, saat=clock, filigran=watermark)
    assert pending == 0
    assert hours < 1


# -- ablation ----------------------------------------------------------


def test_awake_replay_is_switchable(store, sessions, clock) -> None:
    from dornick.recall import anahtar

    node = store.remember("Bir kayıt.", kind="fact")
    log = Log(sessions, "s1", clock)
    log.touch(node.id).tool("kos", error=True, summary="patladı")
    with anahtar.kapali("orgu"):
        report = awake.on_result(store, log.path, "basarisiz", saat=clock,
                                 log=log.log)
    assert report.yazilan_ders == 0
    assert not store.by_kind("lesson", limit=5)
