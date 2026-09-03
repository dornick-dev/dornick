"""Time-based activation (ACT-R base level).

The `uses` counter knew nothing about time: a record written three hundred
days ago was as strong as yesterday's, and a heavily used old record could
keep a fresh correction out of the soul. The tests here exercise the formula
that closes that gap and the places where it is wired into the store.

Invariant: nothing is lost. "Forgetting" = the activation dropping below a
threshold; the record can always be found by explicit search.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from dornick.recall import RecallStore, switches, open_store
from dornick.recall import activation as A
from dornick.recall.activation import (
    MAX_USES,
    NO_BASE,
    Use,
    activation_factor,
    base_activation,
    seed_factor,
)

NOW = datetime(2025, 6, 1, 12, 0, tzinfo=timezone.utc)


def ago(**delta) -> datetime:
    return NOW - timedelta(**delta)


def _uses(*moments: datetime, w: float = 1.0, label: str = A.OPENED) -> list[Use]:
    return [Use(moment, w, label) for moment in moments]


class Calendar:
    def __init__(self, moment: datetime) -> None:
        self.moment = moment

    def __call__(self) -> datetime:
        return self.moment

    def advance(self, **delta) -> None:
        self.moment += timedelta(**delta)


# -- formula -----------------------------------------------------------


def test_fresh_trace_stronger_than_old_trace() -> None:
    """Single use: an hour ago > a day ago > thirty days ago."""
    one_hour = base_activation(_uses(ago(hours=1)), NOW)
    one_day = base_activation(_uses(ago(days=1)), NOW)
    thirty_days = base_activation(_uses(ago(days=30)), NOW)
    assert one_hour > one_day > thirty_days


def test_spaced_repetition_stronger_than_massed_repetition() -> None:
    """Spaced-repetition effect: same number of uses, different distribution.

    If all five uses are crammed into one hour thirty days ago, the trace must
    stay weaker than when the same five uses are spread over thirty days. One
    of the best-measured properties of human memory; the formula gives it for
    free.
    """
    massed = _uses(*[ago(days=30, minutes=i * 10) for i in range(5)])
    spaced = _uses(ago(days=30), ago(days=22), ago(days=15),
                   ago(days=8), ago(days=1))
    assert base_activation(spaced, NOW) > base_activation(massed, NOW)


def test_many_uses_stronger_than_single_use() -> None:
    single = base_activation(_uses(ago(days=5)), NOW)
    many = base_activation(_uses(ago(days=5), ago(days=4), ago(days=3)), NOW)
    assert many > single


def test_never_used_record_is_floor_not_zero() -> None:
    """The record is not lost: even the most forgotten trace keeps the floor value."""
    assert base_activation([], NOW) == NO_BASE
    assert 0.0 < activation_factor(NO_BASE) < 0.1
    # The seed factor leaves half of the score in every case.
    assert seed_factor(NO_BASE) >= 0.5


def test_future_dated_use_does_not_blow_up() -> None:
    """On a machine whose clock was set back, a stamp may be future-dated."""
    ahead = base_activation(_uses(NOW + timedelta(days=2)), NOW)
    assert ahead == pytest.approx(base_activation(_uses(NOW), NOW))


def test_factor_bounded_and_monotonic() -> None:
    values = [activation_factor(b) for b in (-10, -5, -2, 0, 2, 5)]
    assert values == sorted(values)
    assert all(0.0 < v < 1.0 for v in values)
    assert all(0.5 <= seed_factor(b) <= 1.0 for b in (-10, -5, 0, 5))


# -- wiring into the store ---------------------------------------------


def test_use_stamps_written_to_disk(tmp_path: Path) -> None:
    calendar = Calendar(NOW)
    store = open_store(tmp_path, clock=calendar)
    try:
        node = store.remember("yordam: yedek al", kind="procedure")
        calendar.advance(days=3)
        store.open(node.id)
        calendar.advance(days=3)
        store.open(node.id)
        use_log = store.use_log(node.id)
        assert len(use_log) == 3          # the moment of writing is the first use
        assert [k.t for k in use_log] == sorted(k.t for k in use_log)
        assert use_log[0].label == A.WRITTEN
        assert [k.label for k in use_log[1:]] == [A.OPENED, A.OPENED]
        assert all(k.w == 1.0 for k in use_log)
    finally:
        store.close()


def test_use_list_is_bounded(tmp_path: Path) -> None:
    """The last 30 uses are kept: the column must not grow without bound."""
    calendar = Calendar(NOW)
    store = open_store(tmp_path, clock=calendar)
    try:
        node = store.remember("çok kullanılan kayıt", kind="fact")
        for _ in range(MAX_USES + 20):
            calendar.advance(hours=6)
            store.open(node.id)
        assert len(store.use_log(node.id)) == MAX_USES
    finally:
        store.close()


def test_used_record_moves_ahead_in_soul_ranking(tmp_path: Path) -> None:
    """`by_kind` no longer orders by `uses DESC` but by activation."""
    calendar = Calendar(NOW)
    store = open_store(tmp_path, clock=calendar)
    try:
        old = store.remember("eskiden beri duran yordam", kind="procedure")
        calendar.advance(days=120)
        new = store.remember("yeni yazılmış yordam", kind="procedure")
        calendar.advance(days=2)
        # The old record is used regularly; the new one was never opened.
        for _ in range(5):
            calendar.advance(hours=8)
            store.open(old.id)
        ranked = [n.id for n in store.by_kind("procedure", limit=5)]
        assert ranked[0] == old.id

        # And the reverse: an old record untouched for months drops below the new one.
        calendar.advance(days=200)
        fresh = store.remember("bugün yazılan yordam", kind="procedure")
        ranked = [n.id for n in store.by_kind("procedure", limit=5)]
        assert ranked[0] == fresh.id
        assert ranked.index(old.id) > ranked.index(fresh.id)
        assert new.id in ranked          # nobody drops off the list
    finally:
        store.close()


def test_forgotten_record_still_found_by_explicit_search(tmp_path: Path) -> None:
    """Invariant: activation drops, the record stays."""
    calendar = Calendar(NOW)
    store = open_store(tmp_path, clock=calendar)
    try:
        node = store.remember(
            "Debimetre kalibrasyonu iki yılda bir yetkili serviste yapılıyor.",
            kind="fact")
        calendar.advance(days=400)
        result = store.recall("debimetre kalibrasyonu", limit=5)
        assert node.id in {n.id for n in result.hits}
    finally:
        store.close()


def test_forgotten_node_conducts_association_path_weakly(tmp_path: Path) -> None:
    """A node untouched for months should not wake its neighbour as much as before."""
    calendar = Calendar(NOW)
    store = open_store(tmp_path, clock=calendar)
    try:
        source = store.remember("Karatay deposu seviye ölçümü", kind="fact")
        far = store.remember("Sıcaklık sensörü kalibrasyon notu", kind="fact")
        store.link(source.id, far.id, weight=1.0, reason="aynı saha")

        fresh = store.recall("Karatay deposu seviye", limit=6)
        fresh_activation = {s.node: s.activation for s in fresh.trace}[far.id]

        calendar.advance(days=300)
        aged = store.recall("Karatay deposu seviye", limit=6)
        old_activation = {s.node: s.activation for s in aged.trace}.get(far.id, 0.0)
        assert old_activation < fresh_activation
    finally:
        store.close()


# -- migration ---------------------------------------------------------


def test_old_records_activation_is_backfilled(tmp_path: Path) -> None:
    """A memory without the `use_log` column must be roughly filled from
    created/last_used/uses — otherwise every old memory would count as
    "never used" all at once."""
    import shutil

    fixture = Path(__file__).resolve().parent / "fixtures" / "recall-v1.db"
    target = tmp_path / "recall.db"
    shutil.copy2(fixture, target)

    store = RecallStore(target)
    try:
        many = store.use_log("n_v1scada")      # uses=5
        few = store.use_log("n_v1kedi")        # uses=1
        assert len(many) > len(few) >= 1
        node = store.peek("n_v1scada")
        assert node is not None and node.activation > NO_BASE
    finally:
        store.close()


# -- ablation ----------------------------------------------------------


def test_factor_is_neutral_while_mechanism_disabled(tmp_path: Path) -> None:
    """`--kapat aktivasyon`: measurement must be able to switch mechanisms off one by one."""
    with switches.disabled("activation"):
        assert seed_factor(NO_BASE) == 1.0
        assert seed_factor(5.0) == 1.0
        # Spreading must also be neutralised by going through the product's own code.
        assert A.spread_factor(NO_BASE) == 1.0
    assert seed_factor(NO_BASE) < 1.0
    assert A.spread_factor(NO_BASE) < 1.0


# -- weighted use (Phase 3's reverse replay will go through here) ------


def test_negative_weight_weakens_trace() -> None:
    """A use that led to a failure does not reinforce, it pulls back."""
    positive = base_activation(_uses(ago(days=2), ago(days=1)), NOW)
    mixed = base_activation(
        [Use(ago(days=2), 1.0, A.SUCCESS),
         Use(ago(days=1), -0.3, A.FAILURE)], NOW)
    assert mixed < positive


def test_failure_only_drops_to_floor_value() -> None:
    """Even when the sum goes below zero the record is not erased — it stays behind."""
    failure_only = base_activation(
        [Use(ago(days=1), -0.5, A.FAILURE)], NOW)
    assert failure_only == NO_BASE
    assert seed_factor(failure_only) >= 0.5


def test_mixed_track_record_stronger_than_never_used() -> None:
    """3 successes 1 failure → still more alive than a record never touched."""
    mixed = base_activation(
        [Use(ago(days=4), 0.5, A.SUCCESS),
         Use(ago(days=3), 0.5, A.SUCCESS),
         Use(ago(days=2), 0.5, A.SUCCESS),
         Use(ago(days=1), -0.3, A.FAILURE)], NOW)
    assert mixed > NO_BASE


def test_add_use_does_not_increment_counter(tmp_path: Path) -> None:
    """An accountability share is not a "use"; `uses` must stay untouched."""
    calendar = Calendar(NOW)
    store = open_store(tmp_path, clock=calendar)
    try:
        node = store.remember("yordam kaydı", kind="procedure")
        calendar.advance(days=1)
        assert store.add_use(node.id, w=0.5, label=A.SUCCESS) is True
        calendar.advance(days=1)
        assert store.add_use(node.id, w=-0.3, label=A.FAILURE) is True
        assert store.peek(node.id).uses == 0
        assert store.track_record(node.id) == (1, 1)
        labels = [k.label for k in store.use_log(node.id)]
        assert labels == [A.WRITTEN, A.SUCCESS, A.FAILURE]
    finally:
        store.close()


def test_add_use_on_missing_record_is_silently_false(tmp_path: Path) -> None:
    store = open_store(tmp_path, clock=Calendar(NOW))
    try:
        assert store.add_use("n_yok", w=1.0) is False
    finally:
        store.close()


def test_old_plain_stamp_format_is_still_read() -> None:
    """A memory written before the format changed must keep opening."""
    import json

    raw = json.dumps([ago(days=2).isoformat(timespec="milliseconds"),
                      ago(days=1).isoformat(timespec="milliseconds")])
    parsed = A.parse_use_log(raw)
    assert len(parsed) == 2
    assert all(k.w == 1.0 and k.label == A.OPENED for k in parsed)


# -- corrupt record ----------------------------------------------------


def test_corrupt_use_history_does_not_drop_record() -> None:
    """Even if the on-disk JSON is corrupt, recall must keep working."""
    assert A.parse_use_log("bu json değil") == []
    assert A.parse_use_log("{}") == []
    assert A.parse_use_log(42) == []
    assert A.parse_use_log("[]") == []
    # If an entry is partially corrupt only that entry drops, not the record.
    parsed = A.parse_use_log(
        '[{"t": 5}, {"t": "2025-06-01T10:00:00+00:00", "w": "abc"},'
        ' {"t": "2025-06-01T11:00:00+00:00"}]')
    assert len(parsed) == 2
    assert parsed[0].w == 1.0        # an unparseable weight falls back to neutral
    assert parsed[1].label == A.OPENED


def test_corrupt_history_falls_back_to_backfill(tmp_path: Path) -> None:
    """If the column cannot be read, created/last_used/uses take over."""
    parsed = A.parse_use_log(
        "bozuk", created="2025-06-01T09:00:00.000+00:00",
        last_used="2025-06-02T09:00:00.000+00:00", uses=3)
    assert len(parsed) == 4          # moment of writing + three uses
    assert parsed[0].label == A.WRITTEN
