"""Context: which project you were in when you wrote it.

The `session` field existed and search never read it. The leak it was meant
to stop — a crypto note surfacing in the middle of SCADA work — was being
held down instead by two later patches: stripping digits from the query, and
refusing a record that matches a rich query on only one stem. Both are real
filters; neither is about the thing that actually separates those memories.

The fix reads what was already written. A record carries the context it was
born in, and automatic priming prefers records from the same context. Two
rules keep it honest:

* an empty context is neutral — never penalised, because migrating a user's
  years of memories must not push them all to the back;
* a *conflicting* context is discounted but never erased, and open search is
  not filtered at all. "What did we do in kobyte" must be answerable while
  sitting in koru1000.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from dornick.recall import switches, open_store
from dornick.recall import store as S

NOW = datetime(2025, 6, 2, 9, 0, tzinfo=timezone.utc)
KORU = {"proje": "koru1000", "dizin_kok": "D:/Projects/koru1000"}
KOBYTE = {"proje": "kobyte", "dizin_kok": "D:/Projects/kobyte"}


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


@pytest.fixture()
def pair(store):
    """The same words, two projects. This is the whole test set in miniature."""
    # Dolgu: iki belgelik bir korpusta bm25 çöker (kusursuz eşleşme 0.0) ve
    # ölçülen şey bağlam değil o çöküş olurdu.
    for metin in ("Kapı zilinin pili bitmek üzere.",
                  "Semt pazarı perşembe kuruluyor.",
                  "Jeneratör motorini altı ayda bir tazeleniyor.",
                  "Rapor şablonu üç sayfalı bir dosya.",
                  "Rapor teslimi vardiya defterine işleniyor.",
                  "Raporlama aracı yeniden yazıldı."):
        store.remember(metin, kind="fact")
    koru = store.remember("Raporlar vardiya sonunda otomatik üretiliyor.",
                          kind="fact", context=KORU)
    kobyte = store.remember("Raporlar ayın ilk günü müşteriye gönderiliyor.",
                            kind="fact", context=KOBYTE)
    return koru.id, kobyte.id


def _scores(store, query: str, context=None) -> dict[str, float]:
    return {i: s for i, s, _k in store._seed(query, 10, context=context)}


# -- the field ---------------------------------------------------------


def test_context_is_written_and_read_back(store) -> None:
    node = store.remember("Vardiya defteri kasada.", kind="fact", context=KORU)
    assert store.peek(node.id).context == KORU


def test_a_record_without_context_is_plain_empty(store) -> None:
    node = store.remember("Bağlamsız bir kayıt.", kind="fact")
    assert store.peek(node.id).context == {}


def test_a_correction_inherits_the_context(store, clock) -> None:
    first = store.remember("Raporlar PDF üretiliyor.", kind="preference",
                           context=KORU)
    clock.advance(days=2)
    second = store.update(first.id, "Raporlar xlsx üretiliyor.")
    assert store.peek(second.id).context == KORU


# -- what the bonus does -----------------------------------------------


def test_the_same_context_is_preferred(store, pair) -> None:
    koru, kobyte = pair
    plain = _scores(store, "Raporlar konusunda ne kararlaştırmıştık?")
    in_koru = _scores(store, "Raporlar konusunda ne kararlaştırmıştık?",
                      context=KORU)
    assert in_koru[koru] > plain[koru]
    assert in_koru[koru] > in_koru[kobyte]


def test_a_conflicting_context_is_discounted_not_erased(store, pair) -> None:
    """Suppressed, still reachable. The tombstone philosophy, in search."""
    koru, kobyte = pair
    plain = _scores(store, "Raporlar konusunda ne kararlaştırmıştık?")
    in_koru = _scores(store, "Raporlar konusunda ne kararlaştırmıştık?",
                      context=KORU)
    assert in_koru[kobyte] < plain[kobyte]
    assert in_koru[kobyte] > 0.0


def test_an_empty_context_is_never_penalised(store, pair) -> None:
    """Migration must not push a user's whole history to the back."""
    old = store.remember("Raporlar eskiden elle yazılıyordu.", kind="fact")
    plain = _scores(store, "Raporlar nasıl yazılıyor?")
    in_koru = _scores(store, "Raporlar nasıl yazılıyor?", context=KORU)
    assert in_koru[old.id] == pytest.approx(plain[old.id])


def test_the_switch_turns_it_off(store, pair) -> None:
    koru, kobyte = pair
    with switches.disabled("context"):
        scored = _scores(store, "Raporlar konusunda ne kararlaştırmıştık?",
                         context=KORU)
        plain = _scores(store, "Raporlar konusunda ne kararlaştırmıştık?")
    assert scored == plain


# -- where it applies, and where it must not ---------------------------


def test_automatic_priming_uses_the_session_context(store, tmp_path,
                                                    clock, pair) -> None:
    from dornick.loop import select_prime
    from dornick.mind import open_mind

    koru, kobyte = pair
    mind = open_mind(store.path.parent, tmp_path / "sessions", "t", clock=clock)
    try:
        hits = select_prime(mind, "Raporlar konusunda ne kararlaştırmıştık?",
                            limit=5, context=KORU)
        ids = [h.item.id for h in hits]
        assert koru in ids
        assert ids.index(koru) < (ids.index(kobyte) if kobyte in ids else 99)
    finally:
        mind.store.close()


def test_open_search_is_not_filtered_by_context(store, tmp_path, clock,
                                                pair) -> None:
    """"What did we do in kobyte" must be answerable from inside koru1000."""
    from dornick.mind import open_mind

    _koru, kobyte = pair
    mind = open_mind(store.path.parent, tmp_path / "sessions", "t", clock=clock)
    try:
        mind.set_context(KORU)
        found = {h.item.id for h in mind.recall("Raporlar müşteriye ne zaman")}
        assert kobyte in found
    finally:
        mind.store.close()


def test_the_mind_stamps_the_session_context_on_writes(store, tmp_path,
                                                       clock) -> None:
    """The harness writes it, not the model: the model would be guessing."""
    from dornick.mind import open_mind

    mind = open_mind(store.path.parent, tmp_path / "sessions", "t", clock=clock)
    try:
        mind.set_context(KOBYTE)
        memory = mind.remember("Dağıtım her birleştirmede yapılıyor.",
                               kind="fact")
        assert mind.store.peek(memory.id).context == KOBYTE
    finally:
        mind.store.close()


# -- migration ---------------------------------------------------------


def test_an_old_memory_opens_with_empty_contexts(tmp_path: Path) -> None:
    import shutil

    from dornick.recall import RecallStore

    fixture = Path(__file__).resolve().parent / "fixtures" / "recall-v1.db"
    target = tmp_path / "recall.db"
    shutil.copy2(fixture, target)
    store = RecallStore(target)
    try:
        assert store.peek("n_v1scada").context == {}
        scored = {i: s for i, s, _k in store._seed("SCADA WinCC", 5, context=KORU)}
        plain = {i: s for i, s, _k in store._seed("SCADA WinCC", 5)}
        assert scored == plain          # no bonus, and no penalty either
    finally:
        store.close()


def test_a_broken_context_field_does_not_break_search(store) -> None:
    node = store.remember("Bir kayıt.", kind="fact", context=KORU)
    with store._lock:                    # noqa: SLF001 — bilerek bozuk veri
        store._db.execute("UPDATE node SET context='bu json değil' WHERE id=?",
                          (node.id,))
        store._db.commit()
    assert store.peek(node.id).context == {}
    assert store._seed("bir kayıt", 5, context=KORU) is not None
