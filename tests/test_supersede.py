"""Supersede — an updated record taking the place of its old version.

The tool description said "if a record on the same topic exists, delete the
old one and write the current one"; the system did not do that. `save` was
unconfirmed, `forget` required confirmation: the model was free to produce
contradictions but not to clean them up. The result, as measured, was four
versions of the same topic all entering the preload at once.

The fix here is not deletion — the tombstone philosophy stands. The new
record **takes the place** of the old one: the old row stays on disk, in
`series` and in explicit search; it only drops out of seeding and the soul,
and association arriving at it is redirected to the new version.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from dornick.recall import RecallStore, switches, open_store
from dornick.recall.activation import NO_BASE

NOW = datetime(2025, 6, 1, 9, 0, tzinfo=timezone.utc)


class Calendar:
    def __init__(self, moment: datetime) -> None:
        self.moment = moment

    def __call__(self) -> datetime:
        return self.moment

    def advance(self, **delta) -> None:
        self.moment += timedelta(**delta)


@pytest.fixture()
def calendar() -> Calendar:
    return Calendar(NOW)


@pytest.fixture()
def store(tmp_path: Path, calendar: Calendar):
    s = open_store(tmp_path, clock=calendar)
    yield s
    s.close()


def _chain(store: RecallStore, calendar: Calendar) -> tuple[str, str, str]:
    """A → B → C: three versions of the same topic."""
    a = store.remember("Raporları PDF olarak istiyorum.", kind="preference",
                       tags=["rapor-format"])
    calendar.advance(days=10)
    b = store.update(a.id, "Raporları artık xlsx istiyorum.",
                     kind="preference", tags=["rapor-format"])
    calendar.advance(days=10)
    c = store.update(b.id, "Rapor formatı csv olsun.",
                     kind="preference", tags=["rapor-format"])
    return a.id, b.id, c.id


# -- chain -------------------------------------------------------------


def test_old_version_not_seeded_new_one_comes(store, calendar) -> None:
    a, b, c = _chain(store, calendar)
    hits = {n.id for n in store.recall("rapor formatı", limit=8).hits}
    assert c in hits
    assert a not in hits and b not in hits


def test_old_version_not_deleted(store, calendar) -> None:
    """Tombstone philosophy: it was replaced, it did not vanish."""
    a, b, c = _chain(store, calendar)
    for node_id in (a, b):
        node = store.peek(node_id)
        assert node is not None
        assert node.deleted is False


def test_supersede_chain_written_both_ways(store, calendar) -> None:
    a, b, c = _chain(store, calendar)
    assert store.peek(a).superseded_by == b
    assert store.peek(b).superseded_by == c
    assert store.peek(c).superseded_by == ""
    assert store.peek(b).supersedes == a
    assert store.peek(c).supersedes == b
    assert store.peek(a).supersedes == ""


def test_updating_record_linked_to_old_one(store, calendar) -> None:
    """The chain also stands as an edge: the UI must be able to draw it."""
    a, b, _c = _chain(store, calendar)
    reasons = {n.id: r for n, _w, r in store.neighbours_with_reasons(b)}
    assert reasons.get(a) == "günceller"


def test_soul_and_list_see_only_current_version(store, calendar) -> None:
    a, b, c = _chain(store, calendar)
    ids = [n.id for n in store.by_kind("preference", limit=10)]
    assert ids == [c]
    assert [n.id for n in store.recent(10)] == [c]


def test_series_returns_all_versions(store, calendar) -> None:
    """The timeline wants the history anyway: `series` does not filter."""
    a, b, c = _chain(store, calendar)
    ids = [n.id for n in store.by_kind_any(limit=50, all_versions=True)]
    assert {a, b, c} <= set(ids)


# -- spreading ---------------------------------------------------------


def test_association_arriving_at_old_node_redirected_to_new(store, calendar) -> None:
    """The old version's neighbourhood is not lost, it moves to the current version."""
    source = store.remember("Vardiya defteri kasada duruyor.", kind="fact")
    old = store.remember("Raporları PDF olarak istiyorum.", kind="preference")
    store.link(source.id, old.id, weight=1.0, reason="aynı iş")
    calendar.advance(days=5)
    new = store.update(old.id, "Raporları xlsx istiyorum.", kind="preference")

    result = store.recall("Vardiya defteri kasada", limit=8)
    touched = {s.node for s in result.trace}
    assert new.id in touched
    assert old.id not in {n.id for n in result.hits}


def test_supersede_cycle_does_not_loop_forever(store, calendar) -> None:
    """If A → B, B → A is written by hand, recall must still terminate."""
    a = store.remember("birinci sürüm", kind="fact")
    b = store.update(a.id, "ikinci sürüm", kind="fact")
    with store._lock:                      # noqa: SLF001 — deliberately corrupt data
        store._db.execute("UPDATE node SET superseded_by=? WHERE id=?", (a.id, b.id))
        store._db.commit()
    result = store.recall("sürüm", limit=5)
    assert isinstance(result.hits, list)    # returning is enough: it did not hang


def test_current_version_points_to_itself(store, calendar) -> None:
    a, b, c = _chain(store, calendar)
    assert store.current_version(a) == c
    assert store.current_version(c) == c
    assert store.current_version("n_yok") == "n_yok"


# -- consolidation inheritance -----------------------------------------


def test_correction_inherits_activation_of_old_one(store, calendar) -> None:
    """Had the correction started from zero it would sit below what it corrects in the soul."""
    old = store.remember("Testler pytest ile koşuluyor.", kind="procedure")
    for _ in range(10):
        calendar.advance(days=3)
        store.open(old.id)
    previous_b = store.peek(old.id).activation

    calendar.advance(hours=1)
    new = store.update(old.id, "Testler py -m pytest ile koşuluyor.",
                       kind="procedure")
    assert store.peek(new.id).activation >= previous_b
    # The inheritance was really copied, not invented:
    assert len(store.use_log(new.id)) > 1


def test_inheriting_record_above_a_fresh_record(store, calendar) -> None:
    old = store.remember("Yedekler harici diske alınıyor.", kind="procedure")
    for _ in range(8):
        calendar.advance(days=2)
        store.open(old.id)
    calendar.advance(days=1)
    rival = store.remember("Sahaya seri kablo götürülüyor.", kind="procedure")
    calendar.advance(hours=2)
    new = store.update(old.id, "Yedekler NAS'a alınıyor.", kind="procedure")

    ranked = [n.id for n in store.by_kind("procedure", limit=5)]
    assert ranked.index(new.id) < ranked.index(rival.id)


def test_superseded_record_does_not_break_activation_computation(store, calendar) -> None:
    a, b, c = _chain(store, calendar)
    assert store.peek(a).activation > NO_BASE      # still computed


# -- explicit search ---------------------------------------------------


def test_opening_old_record_says_it_was_updated(store, calendar) -> None:
    """If the model holds an old id it must see the direction."""
    a, _b, c = _chain(store, calendar)
    node = store.open(a)
    assert node is not None
    assert f"[güncellendi → {c}]" in node.body


def test_opening_current_record_adds_no_note(store, calendar) -> None:
    _a, _b, c = _chain(store, calendar)
    assert "güncellendi" not in store.open(c).body


# -- ablation ----------------------------------------------------------


def test_old_version_seeded_again_while_mechanism_disabled(store, calendar) -> None:
    """`--kapat supersede`: measurement must be able to switch mechanisms off one by one."""
    a, b, c = _chain(store, calendar)
    with switches.disabled("supersede"):
        hits = {n.id for n in store.recall("rapor formatı", limit=8).hits}
        assert a in hits or b in hits
        assert [n.id for n in store.by_kind("preference", limit=10)] != [c]


# -- migration ---------------------------------------------------------


def test_old_memory_opens_with_supersede_columns(tmp_path: Path) -> None:
    import shutil

    fixture = Path(__file__).resolve().parent / "fixtures" / "recall-v1.db"
    target = tmp_path / "recall.db"
    shutil.copy2(fixture, target)
    store = RecallStore(target)
    try:
        node = store.peek("n_v1rapor")
        assert node is not None
        assert node.superseded_by == "" and node.supersedes == ""
        new = store.update("n_v1rapor", "Raporları xlsx istiyorum.",
                           kind="preference")
        assert store.peek("n_v1rapor").superseded_by == new.id
    finally:
        store.close()


# -- tool surface ------------------------------------------------------


async def test_tool_updates_with_supersedes(tmp_path: Path) -> None:
    from tests.test_mind import _arac_ortami

    registry, ctx, mind = _arac_ortami(tmp_path)
    first = mind.remember("Raporları PDF istiyorum.", kind="preference")
    out = await _invoke(registry, ctx, "mind_memory", {
        "action": "save", "kind": "preference",
        "content": "Raporları xlsx istiyorum.", "supersedes": first.id})
    assert "Güncellendi" in out and first.id in out
    assert mind.store.peek(first.id).superseded_by != ""


async def test_tool_flags_conflict_on_its_own(tmp_path: Path) -> None:
    """If the model forgets to give `supersedes` the system must not stay silent."""
    from tests.test_mind import _arac_ortami

    registry, ctx, mind = _arac_ortami(tmp_path)
    first = mind.remember("Testler pytest ile kök dizinden koşuluyor.",
                          kind="procedure")
    out = await _invoke(registry, ctx, "mind_memory", {
        "action": "save", "kind": "procedure",
        "content": "Testler pytest ile kök dizinden koşuluyor artık."})
    assert "Kaydedildi" in out          # the record was written in any case
    assert f"supersedes={first.id}" in out


async def test_tool_does_not_invent_conflict_on_unrelated_record(tmp_path: Path) -> None:
    from tests.test_mind import _arac_ortami

    registry, ctx, mind = _arac_ortami(tmp_path)
    mind.remember("Testler pytest ile koşuluyor.", kind="procedure")
    out = await _invoke(registry, ctx, "mind_memory", {
        "action": "save", "kind": "preference",
        "content": "Kahvesini sütsüz içiyor."})
    assert "Benzer kayıt var" not in out


async def test_tool_refuses_to_update_missing_record(tmp_path: Path) -> None:
    from tests.test_mind import _arac_ortami

    registry, ctx, mind = _arac_ortami(tmp_path)
    out = await _invoke(registry, ctx, "mind_memory", {
        "action": "save", "content": "bir şey", "supersedes": "n_yok"},
        expect_error=True)
    assert "n_yok" in out


async def _invoke(registry, ctx, name: str, args: dict, *, expect_error: bool = False) -> str:
    from tests.test_mind import _call

    return await _call(registry, ctx, name, args, expect_error=expect_error)
