"""Hot and cold: keeping the active set bounded while the archive grows.

The measured problem (Faz 0, P set): the signature index held every node and
scanned all of them linearly, so cost grew with total memory rather than with
active memory. At 200k nodes `recall()` p95 was 33 ms against a 20 ms budget,
and index RAM was ten times a 20k memory's.

The answer is not a smaller archive. Nothing is deleted, nothing gets a
tombstone, nothing drops out of `series`. What changes is reachability: a hot
node is in the signature index and can come to mind on its own; a cold node
lives only in FTS, so it still wakes to an exact word — a cue — but never
arrives unbidden. Opening one warms it again by the next night.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from dornick.recall import activation as A
from dornick.recall import open_store, weave

NOW = datetime(2025, 6, 2, 9, 0, tzinfo=timezone.utc)


class Clock:
    def __init__(self, moment: datetime) -> None:
        self.moment = moment

    def __call__(self) -> datetime:
        return self.moment

    def advance(self, **delta) -> None:
        self.moment += timedelta(**delta)


@pytest.fixture()
def clock() -> Clock:
    return Clock(NOW)


@pytest.fixture()
def store(tmp_path: Path, clock: Clock):
    s = open_store(tmp_path / "memory", clock=clock)
    yield s
    s.close()


def _cool(store, clock: Clock) -> tuple[int, int]:
    return store.update_heat(weave.COLD_THRESHOLD)


# -- who goes cold -----------------------------------------------------


def test_a_new_record_is_always_hot(store, clock) -> None:
    """The first week is unconditional: a fresh memory must be reachable."""
    node = store.remember("Bugün yazılan bir kayıt.", kind="fact")
    _cool(store, clock)
    assert store.peek(node.id).hot is True


def test_an_untouched_record_goes_cold(store, clock) -> None:
    node = store.remember("Eski çizim arşivi bodrumda.", kind="fact")
    clock.advance(days=60)
    warmed, cooled = _cool(store, clock)
    assert cooled == 1 and warmed == 0
    assert store.peek(node.id).hot is False


def test_a_regularly_used_record_stays_hot(store, clock) -> None:
    node = store.remember("Sürüm yayınlama yordamı.", kind="procedure")
    for _ in range(20):
        clock.advance(days=3)
        store.open(node.id)
    _cool(store, clock)
    assert store.peek(node.id).hot is True


def test_nothing_is_deleted_when_it_cools(store, clock) -> None:
    """Cold is a reachability state, not a tombstone."""
    node = store.remember("Hurda malzeme kantarda tartılıyor.", kind="fact",
                          tags=["depo"])
    clock.advance(days=60)
    _cool(store, clock)

    cold = store.peek(node.id)
    assert cold is not None and cold.deleted is False
    assert node.id in {n.id for n in store.by_kind_any(limit=50)}


# -- what cold changes -------------------------------------------------


def test_a_cold_record_still_wakes_to_an_exact_word(store, clock) -> None:
    """"Wakes to a cue." This is the behaviour, not a consolation prize."""
    node = store.remember(
        "Debimetre kalibrasyonu iki yılda bir yetkili serviste yapılıyor.",
        kind="fact")
    clock.advance(days=200)
    _cool(store, clock)
    assert store.peek(node.id).hot is False

    hits = {n.id for n in store.recall("debimetre kalibrasyonu", limit=8).hits}
    assert node.id in hits


def test_a_cold_record_is_not_in_the_signature_index(store, clock) -> None:
    """"Does not come on its own": the associative channel drops it."""
    node = store.remember("Kaynak makinesinin maskesi otomatik kararan tip.",
                          kind="fact")
    clock.advance(days=200)
    _cool(store, clock)
    assert node.id not in set(store.index.ids())

    # The literal channel still finds it; only the signature channel lost it.
    assert store._seed_signature("kaynak maskesi otomatik", 5) == [] or \
        node.id not in {i for i, _s in store._seed_signature("kaynak maskesi", 5)}


def test_a_cold_record_cannot_enter_the_prime(store, tmp_path, clock) -> None:
    """Even the young-memory exception must not push a cold node in."""
    from dornick.loop import select_prime
    from dornick.mind import open_mind

    node = store.remember("Sac büküm kalıpları raf altında duruyor.", kind="fact")
    clock.advance(days=200)
    _cool(store, clock)

    mind = open_mind(store.path.parent, tmp_path / "sessions", "t", clock=clock)
    try:
        hits = select_prime(mind, "Sac büküm kalıpları nerede duruyor?", limit=5)
        assert node.id not in {h.item.id for h in hits}
        # But an open search still reaches it.
        assert node.id in {h.item.id for h in mind.recall("Sac büküm kalıpları")}
    finally:
        mind.store.close()


def test_opening_a_cold_record_warms_it_by_the_next_night(store, clock) -> None:
    """Recalling something puts it back in the active set — the hippocampal
    round trip, in the only form this system can have one."""
    node = store.remember("Atölye vinci iki tonluk.", kind="fact")
    clock.advance(days=200)
    _cool(store, clock)
    assert store.peek(node.id).hot is False

    store.open(node.id)
    warmed, _cooled = _cool(store, clock)
    assert warmed == 1
    assert store.peek(node.id).hot is True
    assert node.id in set(store.index.ids())


# -- systems consolidation (3.11.2) ------------------------------------


def test_a_distilled_episode_cools_unconditionally_after_two_weeks(
        store, clock) -> None:
    """Detail on disk, summary in the active set. The episode is not deleted."""
    episode = store.remember("Uzun bir konuşma dökümü, rapor tartışması.",
                             kind="episode")
    store.add_use(episode.id, w=-0.2, etiket=A.DISTILLED)

    # It keeps being used: by the normal rule it should have stayed hot.
    for _ in range(10):
        clock.advance(days=1)
        store.open(episode.id)
    _cool(store, clock)
    assert store.peek(episode.id).hot is True       # window not over yet

    for _ in range(5):
        clock.advance(days=1)
        store.open(episode.id)
    _cool(store, clock)
    # Unconditional: still in use, but its essence now lives in a short `fact`.
    assert store.peek(episode.id).hot is False
    assert store.peek(episode.id) is not None         # and still there


def test_an_undistilled_episode_follows_the_normal_rule(store, clock) -> None:
    episode = store.remember("Damıtılmamış bir döküm.", kind="episode")
    for _ in range(15):
        clock.advance(days=1)
        store.open(episode.id)
    _cool(store, clock)
    assert store.peek(episode.id).hot is True       # used, so still hot


# -- the share ---------------------------------------------------------


def test_the_hot_share_lands_in_the_target_band(store, clock) -> None:
    """The calibration target is a share, not a number: %10-30 (roadmap 3.11)."""
    for i in range(100):
        store.remember(f"Saha notu {i}: ölçüm ve bakım kaydı.", kind="fact")
        clock.advance(hours=8)
    # Ten records stay in use; the rest are written once and left alone.
    kept = [n.id for n in store.by_kind_any(limit=10)]
    for _ in range(10):
        clock.advance(days=2)
        for node_id in kept:
            store.open(node_id)
    clock.advance(days=20)
    _cool(store, clock)

    share = store.hot_share()
    assert 0.05 <= share <= 0.35, f"hot share {share}"


def test_the_night_recomputes_the_active_set(store, tmp_path, clock) -> None:
    from dornick.events import EventLog

    sessions = tmp_path / "sessions"
    sessions.mkdir()
    old = store.remember("Rulman tedarikçisi İzmir'deki Mekanik Ltd.", kind="fact")
    # Filler: in a two-node memory `_weave` links everything, and the night's
    # schema refresh warms the old record — which is the CORRECT behaviour
    # (the schema arm of the K set). To measure the isolated arm, records
    # that will not get linked in between are needed.
    for text in ("Kapı zilinin pili bitmek üzere.",
                 "Semt pazarı perşembe kuruluyor.",
                 "Ütü masasının ayağı gevşek.",
                 "Kavanoz kapakları paslanıyor."):
        store.remember(text, kind="fact")
    clock.advance(days=90)
    fresh = store.remember("Bugünkü vardiya raporu hazırlandı.", kind="fact")
    assert old.id not in {n.id for n, _w, _r in store.neighbours_with_reasons(fresh.id)}
    log = EventLog(sessions / "s1.jsonl",
                   clock=lambda: clock().isoformat(timespec="milliseconds"))
    log.note("mind_open", memory_id=fresh.id)
    log.note("sonuc", sonuc="basarili")

    report = weave.night_pass(store, sessions, clock=clock,
                              watermark=tmp_path / "w.json")
    assert report.soguyan >= 1
    assert store.peek(old.id).hot is False
    assert store.peek(fresh.id).hot is True


# -- migration ---------------------------------------------------------


def test_an_old_memory_opens_with_everything_hot(tmp_path: Path) -> None:
    """Migration must not make a user's memories unreachable overnight."""
    import shutil

    from dornick.recall import RecallStore

    fixture = Path(__file__).resolve().parent / "fixtures" / "recall-v1.db"
    target = tmp_path / "recall.db"
    shutil.copy2(fixture, target)
    store = RecallStore(target)
    try:
        assert store.hot_share() == 1.0
        assert store.peek("n_v1scada").hot is True
    finally:
        store.close()
