"""Schema migration: the memory on the user's disk must open across a version upgrade.

This file does the same job in every phase: `tests/fixtures/recall-v1.db` —
a real schema written before the `sig` column was even added — is opened and
`recall()` is called. The migration must go through silently and without
irreversible data loss. If a column added by a phase makes the old file
unopenable the user loses their memories; this test exists to prevent that
day.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from dornick.recall import RecallStore

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "recall-v1.db"

# What the fixture contains (hand-written, frozen).
EXPECTED_LIVE = 7           # one record is a tombstone
EXPECTED_TOTAL = 8


@pytest.fixture()
def old_db(tmp_path: Path) -> Path:
    """A copy of the fixture — the test must not modify the file itself."""
    target = tmp_path / "recall.db"
    shutil.copy2(FIXTURE, target)
    return target


def test_old_memory_opens_and_recalls(old_db: Path) -> None:
    store = RecallStore(old_db)
    try:
        assert store.count() == EXPECTED_LIVE
        result = store.recall("SCADA WinCC", limit=5)
        ids = {n.id for n in result.hits}
        assert "n_v1scada" in ids
    finally:
        store.close()


def test_migration_drops_no_record(old_db: Path) -> None:
    """Adding a new column must not delete rows — even the tombstone must stay in place."""
    store = RecallStore(old_db)
    try:
        store.recall("rapor")           # triggers the migration and signature fill
        with store._lock:               # noqa: SLF001 — migration verification
            total = store._db.execute("SELECT COUNT(*) FROM node").fetchone()[0]
            deleted = store._db.execute(
                "SELECT COUNT(*) FROM node WHERE deleted=1").fetchone()[0]
        assert total == EXPECTED_TOTAL
        assert deleted == 1
    finally:
        store.close()


def test_old_records_fields_preserved(old_db: Path) -> None:
    store = RecallStore(old_db)
    try:
        node = store.peek("n_v1rapor")
        assert node is not None
        assert node.body == "Raporları PDF olarak istiyorum."
        assert node.kind == "preference"
        assert node.uses == 2
        assert node.created.startswith("2024-11")
        assert node.last_used is not None
    finally:
        store.close()


def test_signatures_are_backfilled(old_db: Path) -> None:
    """v1 had no `sig` column; it must be produced on the first search and written to disk."""
    store = RecallStore(old_db)
    try:
        store.recall("kedi")
        with store._lock:               # noqa: SLF001 — migration verification
            unsigned = store._db.execute(
                "SELECT COUNT(*) FROM node WHERE deleted=0 AND sig IS NULL"
            ).fetchone()[0]
        assert unsigned == 0
    finally:
        store.close()


def test_database_consistent_after_migration(old_db: Path) -> None:
    """`PRAGMA integrity_check`: the migration must not leave a half-done file behind."""
    store = RecallStore(old_db)
    try:
        store.recall("scada")
        store.remember("göçten sonra yazılan kayıt", kind="fact")
        with store._lock:               # noqa: SLF001 — migration verification
            status = store._db.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        store.close()
    assert status == "ok"


def test_old_memory_is_writable(old_db: Path) -> None:
    """After migration the memory is not a read-only relic but a working memory."""
    store = RecallStore(old_db)
    try:
        new = store.remember("göçten sonra yazılan kayıt", kind="fact")
        assert store.peek(new.id) is not None
        assert store.count() == EXPECTED_LIVE + 1
    finally:
        store.close()


def test_a_memory_with_turkish_column_names_keeps_its_data(tmp_path: Path) -> None:
    """A pre-release build of this branch wrote `baglam`, `sicak` and
    `kullanimlar`. Opening it must rename, not shadow, those columns."""
    import sqlite3

    from dornick.recall import RecallStore

    target = tmp_path / "recall.db"
    db = sqlite3.connect(target)
    db.executescript(
        "CREATE TABLE node (id TEXT PRIMARY KEY, kind TEXT NOT NULL, title TEXT NOT NULL,"
        " body TEXT NOT NULL, tags TEXT NOT NULL DEFAULT '', session TEXT NOT NULL DEFAULT '',"
        " created TEXT NOT NULL, last_used TEXT NOT NULL, uses INTEGER NOT NULL DEFAULT 0,"
        " deleted INTEGER NOT NULL DEFAULT 0, sig BLOB, kullanimlar TEXT NOT NULL DEFAULT '[]',"
        " supersedes TEXT NOT NULL DEFAULT '', superseded_by TEXT NOT NULL DEFAULT '',"
        " sicak INTEGER NOT NULL DEFAULT 1, baglam TEXT NOT NULL DEFAULT '{}');"
        "INSERT INTO node (id, kind, title, body, created, last_used, sicak, baglam)"
        " VALUES ('n1', 'fact', 't', 'b', '2025-06-01T00:00:00.000+00:00',"
        " '2025-06-01T00:00:00.000+00:00', 0, '{\"proje\": \"koru\"}');")
    db.commit()
    db.close()

    store = RecallStore(target)
    try:
        node = store.peek("n1")
        assert node is not None
        assert node.context == {"proje": "koru"}
        assert node.hot is False
        columns = {row[1] for row in store._db.execute("PRAGMA table_info(node)")}
        assert "baglam" not in columns and "context" in columns
    finally:
        store.close()
