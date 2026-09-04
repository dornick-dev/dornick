"""Recall store.

The design starts from a single complaint: memory must not slow down as it
grows. The previous version read and scanned every session log on every
query — unnoticeable at ten sessions, unusable at ten thousand.

There is no scanning here. SQLite's FTS5 index goes from term to record; the
query cost depends on the number of matching records, not on total volume.
No extra dependency either: sqlite3 is in the standard library.

Two layers:

    disk    Persistent. Survives the computer being switched off. One file:
            recall.db
    RAM     SQLite's own page cache. Its limit is configurable (default
            2 GB). When it fills, the least-used pages drop out — but no
            data is lost, it keeps living on disk.

We do not hand-write that second layer because SQLite's is exactly what is
wanted: what is hot stays in RAM, what cools goes to disk, nothing is deleted.
"""

from __future__ import annotations

import json
import math
import re
import sqlite3
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path
from datetime import datetime
from typing import Any, Iterable, Sequence
from uuid import uuid4

from . import activation, switches, vector
from .clock import Clock, parse, stamp, wall_clock

# Three subjects (Phase 7): what the user SAID (`user`/`preference`/`voice`),
# what the agent SAW (`world`, together with its source), what the outcomes
# showed (`self`, written only by the night's reverse replay). The
# provenance rule looks at the source, not the topic: an observation is not
# a preference.
KINDS = ("fact", "preference", "lesson", "procedure", "user", "voice",
         "goal", "episode", "world", "self")

# Default RAM budget. The user can raise it; when it fills, the least-used
# pages drop out and the record stays on disk.
DEFAULT_CACHE_BYTES = 2 * 1024**3

# Attenuation at every hop of spreading activation. At 1.0 distant
# associations would look as strong as direct matches.
# The signature channel's score is scaled by this factor. It sits below one
# because a term that matches verbatim is stronger evidence than a text that
# merely looks similar.
SIGNATURE_WEIGHT = 0.9

# Number of characters taken as the stem guess of a term. Shorter means
# unrelated matches, longer means failing to catch the suffix.
STEM_CHARS = 5

# Similarity required for a record to count as "already present on the same
# topic". Calibration (life bench, `--celiski-esik`, 2026-09-02): the rate of
# catching the correct previous version over 24 correction events was swept
# against the number of false alarms over 60 noise records:
#     0.50 → catch 0.79, false 24     0.60 → catch 0.25, false 2
#     0.55 → catch 0.75, false  5     0.75 → catch 0.00, false 1
# The roadmap's suggested starting point of 0.75 catches nothing; the curve
# steepens between 0.55 and 0.60. The knee was chosen: three-quarters catch
# rate, five warnings over sixty noise records. A warning is a suggestion,
# the record is written regardless — a false alarm costs a sentence, a miss
# costs a contradiction.
# See docs/charts/celiski-esigi.md.
CONFLICT_THRESHOLD = 0.55

# Share gained by a record written in the same context. If all three fields
# (project, directory, time of day) overlap fully, the multiplier is
# (1 + CONTEXT_BONUS). Calibration: docs/hafiza-fazlar.md "Faz 5".
CONTEXT_BONUS = 0.15
# Share lost by a record carrying a CONFLICTING value in the same field. The
# bonus alone was not enough and the reason was measured: `select_prime`
# tries to fill five slots, and pushing the right one up does not push the
# wrong one out. An empty context is still neutral — the penalty is only for
# conflict.
CONTEXT_PENALTY = 1.0
# Minimum share a conflicting context keeps. Dropping it to zero would have
# meant "NEVER find that record while in another project"; this floor is the
# search-side counterpart of the tombstone philosophy.
CONTEXT_FLOOR = 0.15

HOP_DECAY = 0.45
# How many FTS candidates the literal channel re-scores by IDF coverage.
# bm25 order is only a coarse net here; the real ranking is the coverage.
LITERAL_POOL = 40
# Minimum edge weight over which warmth spreads one hop (update_heat). 0 = off.
# Calibration: docs/hafiza-fazlar.md "sıcak küme".
WARM_EDGE = 0.8
# Document-frequency counting stops here: beyond it a stem is simply common.
DF_CAP = 500
MIN_ACTIVATION = 0.02

_WORD = re.compile(r"\w+", re.UNICODE)

SCHEMA = """
CREATE TABLE IF NOT EXISTS node (
    id        TEXT PRIMARY KEY,
    kind      TEXT NOT NULL,
    title     TEXT NOT NULL,
    body      TEXT NOT NULL,
    tags      TEXT NOT NULL DEFAULT '',
    session   TEXT NOT NULL DEFAULT '',
    created   TEXT NOT NULL,
    last_used TEXT,
    uses      INTEGER NOT NULL DEFAULT 0,
    deleted   INTEGER NOT NULL DEFAULT 0,
    sig       BLOB,
    -- Usage history: the last 30 uses, as a JSON array.
    --   [{"t": "<ISO>", "w": 1.0, "etiket": "acildi"}, ...]
    -- The moment of writing is the first use (w = 1.0; Phase 4 replaces this
    -- with surprise). w can be negative (Phase 3 reverse replay): a use that
    -- led to a failure weakens the trace. etiket: yazildi | acildi | basari |
    -- hata | sema | yakalandi. Phase 1 writes only the first two; the field
    -- is opened in this shape from the start so later phases need not
    -- change the schema.
    -- `uses`/`last_used` are kept (the UI reads them) but activation is
    -- computed from this column — a counter does not know time.
    use_log TEXT NOT NULL DEFAULT '[]',
    -- Update chain. Not deletion but REPLACEMENT: the old row stays on disk,
    -- in `series` and in open search; it only drops out of seeding and the
    -- soul, and association arriving at it is redirected to the new version.
    supersedes    TEXT NOT NULL DEFAULT '',   -- which record this one replaced
    superseded_by TEXT NOT NULL DEFAULT '',   -- which record replaced this one
    -- Active set. As memory grew, the signature scan and RAM grew linearly;
    -- the brain's answer is not to shrink the archive but to keep the active
    -- set bounded. A hot node is in the signature index: it comes on its
    -- own. A cold node is only in FTS: it wakes to a cue (an exact word),
    -- it does not come on its own. It is not deleted, gets no tombstone,
    -- does not drop out of `series`.
    hot           INTEGER NOT NULL DEFAULT 1,
    -- Context at the moment of writing: {"proje": "koru1000", "dizin_kok":
    -- "...", "saat_dilimi": "sabah"}. The model does not fill it in, the
    -- harness writes it — not the model's claim but the event itself.
    context       TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS node_kind ON node(kind) WHERE deleted = 0;
-- The node_superseded index is built in _add_missing_columns: when opening
-- an old memory the column has not been added yet, and a CREATE INDEX here
-- would bring down the whole schema script.

CREATE TABLE IF NOT EXISTS link (
    src    TEXT NOT NULL,
    dst    TEXT NOT NULL,
    weight REAL NOT NULL DEFAULT 1.0,
    reason TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (src, dst)
);
CREATE INDEX IF NOT EXISTS link_dst ON link(dst);

CREATE VIRTUAL TABLE IF NOT EXISTS node_fts USING fts5(
    title, body, tags,
    content='node', content_rowid='rowid',
    tokenize='unicode61 remove_diacritics 0'
);

CREATE TRIGGER IF NOT EXISTS node_ai AFTER INSERT ON node BEGIN
    INSERT INTO node_fts(rowid, title, body, tags)
    VALUES (new.rowid, new.title, new.body, new.tags);
END;
CREATE TRIGGER IF NOT EXISTS node_ad AFTER DELETE ON node BEGIN
    INSERT INTO node_fts(node_fts, rowid, title, body, tags)
    VALUES ('delete', old.rowid, old.title, old.body, old.tags);
END;
CREATE TRIGGER IF NOT EXISTS node_au AFTER UPDATE ON node BEGIN
    INSERT INTO node_fts(node_fts, rowid, title, body, tags)
    VALUES ('delete', old.rowid, old.title, old.body, old.tags);
    INSERT INTO node_fts(rowid, title, body, tags)
    VALUES (new.rowid, new.title, new.body, new.tags);
END;
"""


def _new_id() -> str:
    return f"n_{uuid4().hex[:10]}"


@dataclass(slots=True)
class Node:
    id: str
    kind: str
    title: str
    body: str
    tags: list[str] = field(default_factory=list)
    session: str = ""
    created: str = ""
    last_used: str | None = None
    uses: int = 0
    # Base-level activation (ACT-R B). Computed at read time: how "alive" a
    # trace is right now is not a number that can sit on disk, it is a
    # function of time.
    activation: float = activation.NO_BASE
    # Update chain. If `superseded_by` is set this record is history: it is
    # not searched, it does not enter the soul — but it is not deleted.
    supersedes: str = ""
    superseded_by: str = ""
    deleted: bool = False
    # In the active set? A cold record is not deleted: it sits in FTS, it is
    # found by an exact word, it shows up in `series` — it just does not
    # come on its own and cannot enter priming.
    hot: bool = True
    # Context at the moment it was written. The search side reads this and
    # brings records from the same context forward; old records with an
    # empty context get no bonus but no penalty either.
    context: dict = field(default_factory=dict)

    def headline(self) -> str:
        """This goes to the model first: identity and one line. The body
        arrives once opened."""
        tags = f" [{', '.join(self.tags)}]" if self.tags else ""
        return f"{self.id} ({self.kind}) {self.title}{tags}"


@dataclass(slots=True)
class Step:
    """One step of activation — a place visited while recalling.

    The UI animates these in order: the path along which the synapse fired.
    """

    node: str
    kind: str
    activation: float
    hop: int
    via: str  # "query" or the id of the node that passed the activation on


@dataclass(slots=True)
class Recollection:
    query: str
    hits: list[Node]
    trace: list[Step]

    def headlines(self) -> str:
        return "\n".join(h.headline() for h in self.hits)


class RecallStore:
    def __init__(
        self,
        path: Path,
        *,
        cache_bytes: int = DEFAULT_CACHE_BYTES,
        clock: Clock | None = None,
    ) -> None:
        self.path = path
        # Time is read from a single place (see clock.py): the product uses
        # the wall clock, the benchmark supplies a virtual calendar. A direct
        # datetime.now() call would make the question "what happens thirty
        # days later" unmeasurable.
        self._clock: Clock = clock or wall_clock
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row

        # WAL: readers do not block the writer. Required when several
        # processes open the same memory (agent + UI + MCP client).
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA synchronous=NORMAL")
        # A negative value means a budget in KiB, not a page count.
        self._db.execute(f"PRAGMA cache_size={-(cache_bytes // 1024)}")
        self._db.executescript(SCHEMA)
        self._add_missing_columns()
        self._db.commit()
        # The signature index is loaded on the first search: processes that
        # open the memory without ever searching (a write-only MCP client,
        # say) should not pay for it. The process that opens a session can
        # pull it into RAM early in the background with `warm()`.
        self._index: vector.Index | None = None
        # Stem -> document frequency, see `_idf`.
        self._df_cache: dict[str, int] = {}
        self._df_live = 0
        self._index_lock = threading.Lock()

    def _now(self) -> str:
        """The "now" stamp that goes to disk."""
        return stamp(self._clock)

    def _add_missing_columns(self) -> None:
        """Carries a memory opened before forward with new columns.

        The memories on the user's disk must not be lost on a version
        upgrade; the missing column is added and signatures are produced
        retroactively on the first search.
        """
        have = {row["name"] for row in self._db.execute("PRAGMA table_info(node)")}
        # A memory written by a pre-release build of this branch carries the
        # same three columns under their Turkish names. Renaming keeps the
        # data; adding an empty English twin would have lost it.
        for old_name, new_name in (("baglam", "context"), ("sicak", "hot"),
                                   ("kullanimlar", "use_log")):
            if old_name in have and new_name not in have:
                self._db.execute(
                    f"ALTER TABLE node RENAME COLUMN {old_name} TO {new_name}")
                have.discard(old_name)
                have.add(new_name)
        if "sig" not in have:
            self._db.execute("ALTER TABLE node ADD COLUMN sig BLOB")
        for column in ("supersedes", "superseded_by"):
            if column not in have:
                self._db.execute(
                    f"ALTER TABLE node ADD COLUMN {column} TEXT NOT NULL DEFAULT ''")
        if "context" not in have:
            self._db.execute(
                "ALTER TABLE node ADD COLUMN context TEXT NOT NULL DEFAULT '{}'")
        if "hot" not in have:
            # Default 1: no record is lost at migration time. The first night
            # pass decides which ones have cooled.
            self._db.execute(
                "ALTER TABLE node ADD COLUMN hot INTEGER NOT NULL DEFAULT 1")
        self._db.execute(
            "CREATE INDEX IF NOT EXISTS node_superseded ON node(superseded_by)"
            " WHERE superseded_by != ''")
        if "use_log" not in have:
            self._db.execute(
                "ALTER TABLE node ADD COLUMN use_log TEXT NOT NULL DEFAULT '[]'")
            # Even if the column stays empty, the read side reconstructs it
            # from created/last_used/uses (activation.parse_use_log); writing
            # it to disk once here removes that computation from every read.
            self._backfill_use_log()

    def _backfill_use_log(self) -> None:
        """Roughly fills in records written before the `use_log` column existed.

        Without this, the moment the column is added every memory the user
        accumulated over years would count as "never used" and the memory
        would behave as if reset by a single version upgrade.
        """
        rows_to_write = []
        for row in self._db.execute(
                "SELECT id, created, last_used, uses FROM node"
                " WHERE use_log IN ('', '[]')"):
            history = activation.parse_use_log(
                "", created=row["created"], last_used=row["last_used"],
                uses=int(row["uses"] or 0))
            if not history:
                continue
            rows_to_write.append((activation.encode(history), row["id"]))
        if rows_to_write:
            self._db.executemany(
                "UPDATE node SET use_log=? WHERE id=?", rows_to_write)

    def add_use(self, node_id: str, *, w: float = 1.0,
                      label: str = activation.OPENED) -> bool:
        """Writes a use into the trace — without bumping the counter.

        `open()` is the model reading the record; this is the system giving
        it a share: the night replay writes positive weight to the node that
        led to success and negative weight to the one that led to failure.
        `uses` is left alone because the record was not really "used" — its
        responsibility was distributed.
        """
        with self._lock:
            row = self._db.execute(
                "SELECT created, last_used, uses, use_log FROM node"
                " WHERE id=? AND deleted=0", (node_id,)).fetchone()
            if row is None:
                return False
            history = activation.parse_use_log(
                row["use_log"], created=row["created"],
                last_used=row["last_used"], uses=int(row["uses"] or 0))
            self._db.execute(
                "UPDATE node SET use_log=? WHERE id=?",
                (activation.append_use(history, self._clock(), w=w, label=label), node_id))
            self._db.commit()
        return True

    def track_record(self, node_id: str) -> tuple[int, int]:
        """A memory's (success, failure) record. If the model sees this it
        also sees "this one sometimes misleads"."""
        return activation.track_record(self.use_log(node_id))

    def _node(self, row: sqlite3.Row) -> Node:
        """Turns a row into a node and computes its activation at this moment."""
        return _to_node(row, level=self._base_level(row))

    def _base_level(self, row: sqlite3.Row) -> float:
        history = activation.parse_use_log(
            _field(row, "use_log"),
            created=_field(row, "created"),
            last_used=_field(row, "last_used"),
            uses=int(_field(row, "uses") or 0),
        )
        return activation.base_activation(history, self._clock())

    def use_log(self, node_id: str) -> list:
        """A record's usage history. For introspection and measurement."""
        with self._lock:
            row = self._db.execute(
                "SELECT created, last_used, uses, use_log FROM node WHERE id=?",
                (node_id,),
            ).fetchone()
        if row is None:
            return []
        return activation.parse_use_log(
            row["use_log"], created=row["created"],
            last_used=row["last_used"], uses=int(row["uses"] or 0))

    @property
    def index(self) -> vector.Index:
        """The signatures as they live in RAM; built from disk on first access."""
        if self._index is None:
            # Double-checked lock: if the first search arrives while warm()
            # is building in the background, the index must not be built
            # twice.
            with self._index_lock:
                if self._index is None:
                    self._index = self._load_index()
        return self._index

    def warm(self) -> None:
        """Pulls the signature index from disk into RAM in the background.

        Called at session start: the memories are ready in RAM before the
        model receives its first message, and the first recall does not wait
        for the index build. On a separate thread — blocking startup would
        slow down the very thing we want to speed up.
        """
        if self._index is None:
            threading.Thread(
                target=lambda: self.index, name="recall-warm", daemon=True
            ).start()

    def _load_index(self) -> vector.Index:
        # Episodes (turn transcripts) are DELIBERATELY in the index: automatic
        # priming and harvesting exclude them, but model-driven `mind_recall`
        # must be able to find a conversation by synonyms too — the signature
        # channel provides exactly that, FTS only catches the exact word. The
        # price is a bigger scan; measured: one XOR+popcount per record,
        # ~3-5 ms at 50k records — a thousandth of a model call. Until the
        # episode count really tires the scan (hundreds of thousands) this
        # trade is right.
        with self._lock:
            # The signature index holds ONLY hot nodes. The scan cost now
            # grows with active memory, not with the total. FTS keeps
            # covering everything: a cold record is found by an exact word.
            rows = self._db.execute(
                "SELECT id, title, body, tags, sig FROM node WHERE deleted=0"
                + self._history_filter()
                + (" AND hot=1" if switches.ACTIVE.weave else "")
            ).fetchall()

        index = vector.Index()
        backfill: list[tuple[bytes, str]] = []
        for row in rows:
            value = vector.from_blob(row["sig"])
            if not value:
                # Record without a signature: written before this version.
                # Produced once and written to disk, never computed again.
                value = vector.signature(f"{row['title']} {row['body']} {row['tags']}")
                if value:
                    backfill.append((vector.to_blob(value), row["id"]))
            index.add(row["id"], value)

        if backfill:
            with self._lock:
                self._db.executemany("UPDATE node SET sig=? WHERE id=?", backfill)
                self._db.commit()
        return index

    def close(self) -> None:
        with self._lock:
            self._db.close()

    # -- writing -------------------------------------------------------

    def remember(
        self,
        body: str,
        *,
        kind: str = "fact",
        title: str = "",
        tags: Iterable[str] = (),
        session: str = "",
        links: Iterable[str] = (),
        supersedes: str = "",
        use_log: str = "",
        context: dict | None = None,
    ) -> Node:
        if kind not in KINDS:
            raise ValueError(f"Bilinmeyen tür: {kind}. Geçerli olanlar: {', '.join(KINDS)}")
        body = body.strip()
        if not body:
            raise ValueError("Boş içerik kaydedilmez.")

        # Encoding strength (Phase 4): measured BEFORE the record is written,
        # otherwise the nearest neighbour would be the record itself and
        # everything would look "not surprising at all".
        neighbours = self._seed(f"{title or _first_line(body)} {body}"[:400], 1)
        surprise = 1.0 - (neighbours[0][1] if neighbours else 0.0)
        strength = activation.encoding_strength(surprise, kind=kind, supersedes=supersedes)

        node = Node(
            id=_new_id(),
            kind=kind,
            title=(title.strip() or _first_line(body))[:140],
            body=body,
            tags=[t.strip() for t in tags if t.strip()],
            session=session,
            created=self._now(),
            supersedes=supersedes,
            context=dict(context or {}),
        )
        tag_text = " ".join(node.tags)
        sign = vector.signature(f"{node.title} {node.body} {tag_text}")
        with self._lock:
            self._db.execute(
                "INSERT INTO node(id, kind, title, body, tags, session, created,"
                " sig, use_log, supersedes, context)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (node.id, node.kind, node.title, node.body,
                 tag_text, node.session, node.created, vector.to_blob(sign),
                 use_log or activation.first_stamp(node.created, strength),
                 supersedes,
                 json.dumps(node.context, ensure_ascii=False)),
            )
            for other in links:
                self._link(node.id, other, 1.0, "birlikte kaydedildi")
            self._db.commit()

        # The new signature is written both to disk (the INSERT above) and to
        # RAM. The RAM addition is under the index lock: while warm() builds
        # the index in the background, this record must not fall through the
        # gap — neither in the snapshot read from disk nor in RAM. If the
        # index is not built yet there is nothing to add — when it is built
        # it will read this row from disk anyway.
        with self._index_lock:
            if self._index is not None:
                self._index.add(node.id, sign)

        # Let the network weave itself: a new record links to the few
        # memories closest to its content. Waiting for manual linking meant
        # the network never formed; association walks over these links.
        self._weave(node)
        return node

    def update(
        self,
        old_id: str,
        body: str,
        *,
        kind: str = "",
        title: str = "",
        tags: Iterable[str] = (),
        session: str = "",
    ) -> Node:
        """Writes a new record in place of an old one. The old one is NOT deleted.

        Four jobs in one:

        1. The new record is written with `supersedes=old_id`.
        2. The old one gets `superseded_by=new_id`; `deleted` stays 0.
        3. The two are linked by an edge with the reason "günceller" — so the
           UI can draw the chain and association can walk that path.
        4. The old record's usage history is **copied** to the new one.
           Without inheriting the consolidation, a correction would start
           from zero and sit below the thing it corrected in the soul — the
           opposite of the correction's whole purpose.

        The old record is dropped from the signature index: not searched,
        does not enter the soul, but keeps living on disk, in `series` and
        in open search.
        """
        old = self.peek(old_id)
        if old is None:
            raise ValueError(f"Güncellenecek kayıt yok: {old_id}")

        # Inheritance + a new write stamp: the correction takes over the
        # consolidation of what it corrects and puts its own freshness on top.
        inherited = activation.append_use(self.use_log(old_id), self._clock(),
                                          label=activation.WRITTEN)
        new = self.remember(
            body,
            kind=kind or old.kind,
            title=title,
            tags=tags or old.tags,
            session=session or old.session,
            supersedes=old_id,
            use_log=inherited,
            context=old.context,
        )
        with self._lock:
            self._db.execute("UPDATE node SET superseded_by=? WHERE id=?",
                             (new.id, old_id))
            self._link(new.id, old_id, 1.0, "günceller")
            self._db.commit()
        # The old version drops out of the signature channel; it stays in
        # FTS (still found by an exact word — "wakes to a cue").
        with self._index_lock:
            if self._index is not None:
                self._index.drop(old_id)
        return new

    def find_by_title(self, kind: str, title: str) -> Node | None:
        """A record with the same title. Not similarity, EXACT match.

        The uniqueness of the lessons and procedures the night writes cannot
        be left to a threshold: the same error text yields the same title,
        and the answer to "is this the same lesson" should look at equality,
        not at a number like 0.55.
        """
        if not title:
            return None
        with self._lock:
            row = self._db.execute(
                "SELECT * FROM node WHERE deleted=0 AND kind=? AND title=?"
                + self._history_filter()
                + " ORDER BY created DESC LIMIT 1",
                (kind, title[:140])).fetchone()
        return self._node(row) if row else None

    def similar_record(self, body: str, kind: str, *,
                       threshold: float = CONFLICT_THRESHOLD) -> Node | None:
        """Is there a sufficiently similar record of the same kind?

        The shared question of two separate jobs: did the model forget to
        pass `supersedes` (`conflict_candidate`), and is the night writing
        the same lesson a second time (`weave.reverse_replay`). The second
        does not depend on the supersede switch — the same lesson must not
        be written twice even with the mechanism off.
        """
        for node_id, score, candidate_kind in self._seed(body[:400], 3):
            if candidate_kind == kind and score >= threshold:
                return self.peek(node_id)
        return None

    def conflict_candidate(self, body: str, kind: str, *,
                           threshold: float = CONFLICT_THRESHOLD) -> Node | None:
        """Could this body be an update of an existing record of the same kind?

        If the model forgets to pass `supersedes` the system must not stay
        silent: the nearest few neighbours are examined, and if one is of the
        same kind and similar enough, its name appears in the tool reply. The
        decision is the model's — the record is written regardless. Not
        missing matters more than being clean.
        """
        if not switches.ACTIVE.supersede:
            return None
        return self.similar_record(body, kind, threshold=threshold)

    def current_version(self, node_id: str) -> str:
        """The record at the tip of the chain. Cycle-safe.

        In a hand-corrupted db A→B, B→A can be written; recall would then
        spin forever. If a seen id comes up a second time, we stop.
        """
        seen = {node_id}
        current = node_id
        while True:
            with self._lock:
                row = self._db.execute(
                    "SELECT superseded_by FROM node WHERE id=?", (current,)
                ).fetchone()
            next_id = (row["superseded_by"] if row else "") or ""
            if not next_id or next_id in seen:
                return current
            seen.add(next_id)
            current = next_id

    def neighbours_with_reasons(self, node_id: str) -> list[tuple[Node, float, str]]:
        """Neighbours, together with the reason for the link.

        `neighbours` returns only the weight; the reason is needed both by
        the UI (drawing the supersede edge differently) and by the
        `mind_recall` output (telling the model "why linked").
        """
        with self._lock:
            rows = self._db.execute(
                "SELECT n.*, l.weight, l.reason FROM link l"
                " JOIN node n ON n.id = l.dst"
                " WHERE l.src=? AND n.deleted=0 ORDER BY l.weight DESC",
                (node_id,),
            ).fetchall()
        return [(self._node(r), float(r["weight"]), r["reason"]) for r in rows]

    def _weave(self, node: Node, neighbours: int = 3) -> None:
        seeds = self._seed(f"{node.title} {node.body}"[:400], neighbours + 1)
        with self._lock:
            for position, (other, _score, _kind) in enumerate(seeds):
                if other == node.id:
                    continue
                self._link(node.id, other, round(0.8 - position * 0.15, 3), "benzer icerik")
            self._db.commit()

    def connect(self, src: str, dst: str, *, weight: float = 1.0, reason: str = "",
                birikimli: bool = False, yalniz_yeni: bool = False) -> bool:
        """Creates a link; returns whether the edge actually changed.

        `birikimli` (cumulative): when a link with the same reason comes
        again, the weight must not freeze at MAX but accumulate towards 1.0.
        Two things used together often should be strongly linked — a pair
        that came back to back in five sessions must not keep the same
        weight as a one-off.

        `yalniz_yeni` (only-if-new): if the edge already exists, leave it.
        Stitching (Step 4) works this way — an assumption is never written
        over a link that was actually lived.
        """
        if src == dst or not src or not dst:
            return False
        with self._lock:
            existing = self._db.execute(
                "SELECT weight FROM link WHERE src=? AND dst=?", (src, dst)
            ).fetchone()
            if existing is not None and yalniz_yeni:
                return False
            if birikimli and existing is not None:
                weight = min(1.0, float(existing["weight"]) + weight * 0.5)
            self._link(src, dst, weight, reason)
            self._db.commit()
        return True

    def cold_nodes(self, cutoff: datetime) -> tuple[list[str], int]:
        """Nodes nothing has touched since `cutoff`, and how many were skipped.

        "Touched" means the last usage stamp, not the write time: a record
        written a year ago but opened yesterday is warm. Local sleep uses
        this to stay out of the region that is currently being learned.
        """
        with self._lock:
            rows = self._db.execute(
                "SELECT id, created, last_used, uses, use_log FROM node"
                " WHERE deleted=0" + self._history_filter()).fetchall()
        cold: list[str] = []
        hot = 0
        for row in rows:
            history = activation.parse_use_log(
                row["use_log"], created=row["created"],
                last_used=row["last_used"], uses=int(row["uses"] or 0))
            last = max((k.t for k in history), default=None)
            if last is not None and last >= cutoff:
                hot += 1
            else:
                cold.append(row["id"])
        return cold, hot

    def shrink_edges_between(self, node_ids: Sequence[str], epsilon: float,
                             floor: float) -> tuple[int, int]:
        """Shrink only the edges whose BOTH ends are in `node_ids`.

        An edge with one end in the active region is left alone: shrinking it
        would touch a trace that is still being strengthened, which is the
        single thing downscaling must never do while learning is in progress.
        """
        if not node_ids:
            return 0, 0
        shrunk = removed = 0
        with self._lock:
            for i in range(0, len(node_ids), 400):
                chunk = list(node_ids[i:i + 400])
                placeholders = ",".join("?" * len(chunk))
                shrunk += self._db.execute(
                    f"UPDATE link SET weight = weight * ?"
                    f" WHERE src IN ({placeholders}) AND dst IN ({placeholders})",
                    (1.0 - epsilon, *chunk, *chunk)).rowcount
                removed += self._db.execute(
                    f"DELETE FROM link WHERE weight < ?"
                    f" AND src IN ({placeholders}) AND dst IN ({placeholders})",
                    (floor, *chunk, *chunk)).rowcount
            self._db.commit()
        return int(shrunk), int(removed)

    def update_heat(self, threshold: float, fresh_days: int = 7,
                    distilled_days: int = 14) -> tuple[int, int]:
        """Recomputes the hot set. Runs at the end of the night.

        Three rules, in order:

        * a new record is always hot (the first `fresh_days` after writing),
        * one whose activation is above the threshold is hot,
        * a distilled `episode` cools **unconditionally** after
          `distilled_days` — the detail lives on disk, the summary in the hot
          set (systems consolidation).

        Returns: (warmed, cooled). The signature index is updated at the same
        time.
        """
        now = self._clock()
        with self._lock:
            rows = self._db.execute(
                "SELECT id, kind, created, last_used, uses, use_log, hot,"
                " superseded_by FROM node WHERE deleted=0").fetchall()
        warming: list[str] = []
        cooling: list[str] = []
        level: dict[str, float] = {}
        own: dict[str, bool] = {}
        aged_ids: set[str] = set()
        for row in rows:
            history = activation.parse_use_log(
                row["use_log"], created=row["created"],
                last_used=row["last_used"], uses=int(row["uses"] or 0))
            b = activation.base_activation(history, now)
            written = parse(row["created"])
            fresh = (written is not None
                     and (now - written).days < fresh_days
                     and not (row["superseded_by"] or ""))
            distilled = any(k.label == activation.DISTILLED for k in history)
            aged = distilled and history and (
                now - max(k.t for k in history
                          if k.label == activation.DISTILLED)).days >= distilled_days
            level[row["id"]] = b
            own[row["id"]] = bool((fresh or b >= threshold) and not aged)
            aged_ids.add(row["id"]) if aged else None
        # Warmth spreads one hop over strong edges: a record tied to something
        # in use is part of the schema in use, not an isolated trace. The hot
        # set is the associative NEIGHBOURHOOD of what is used — that is what
        # the night's schema refresh was reaching for, and what keeps a
        # user's stack/preference facts warm while an isolated note (the
        # bench's K cluster) still cools. Off when WARM_EDGE is 0.
        hot_by_id = dict(own)
        if WARM_EDGE > 0 and any(own.values()):
            core = [i for i, h in own.items() if h]
            with self._lock:
                for chunk_start in range(0, len(core), 400):
                    chunk = core[chunk_start:chunk_start + 400]
                    marks = ",".join("?" * len(chunk))
                    for (other,) in self._db.execute(
                            f"SELECT dst FROM link WHERE src IN ({marks}) AND weight >= ?"
                            f" UNION SELECT src FROM link WHERE dst IN ({marks}) AND weight >= ?",
                            (*chunk, WARM_EDGE, *chunk, WARM_EDGE)):
                        if other in hot_by_id and other not in aged_ids:
                            hot_by_id[other] = True
        for row in rows:
            hot = hot_by_id[row["id"]]
            if hot and not row["hot"]:
                warming.append(row["id"])
            elif not hot and row["hot"]:
                cooling.append(row["id"])
        if warming or cooling:
            with self._lock:
                self._db.executemany("UPDATE node SET hot=1 WHERE id=?",
                                     [(i,) for i in warming])
                self._db.executemany("UPDATE node SET hot=0 WHERE id=?",
                                     [(i,) for i in cooling])
                self._db.commit()
            with self._index_lock:
                self._index = None      # the index is rebuilt on the next search
        return len(warming), len(cooling)

    def hot_share(self) -> float:
        """Share of hot nodes over the total. Target 10-30% (roadmap 3.11)."""
        with self._lock:
            total = self._db.execute(
                "SELECT COUNT(*) FROM node WHERE deleted=0").fetchone()[0]
            hot = self._db.execute(
                "SELECT COUNT(*) FROM node WHERE deleted=0 AND hot=1").fetchone()[0]
        return round(float(hot) / max(int(total), 1), 4)

    def strengthening(self) -> float:
        """Un-downscaled strengthening: total edge weight / node.

        The main term of sleep pressure (SHY). The threshold was measured
        against this quantity (see docs/charts/basinc-bozulma.md); were it
        not the same quantity, the threshold would be a threshold of
        something else.
        """
        with self._lock:
            total = self._db.execute(
                "SELECT COALESCE(SUM(weight), 0) FROM link").fetchone()[0]
            nodes = self._db.execute(
                "SELECT COUNT(*) FROM node WHERE deleted=0").fetchone()[0]
        return round(float(total) / max(int(nodes), 1), 4)

    def checkpoint(self) -> int:
        """Fully closes the WAL. Done when there is no writer — that is, only in sleep."""
        with self._lock:
            self._db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            self._db.commit()
        try:
            return (self.path.parent / f"{self.path.name}-wal").stat().st_size
        except OSError:
            return 0

    def optimize_fts(self) -> bool:
        """FTS b-tree merge: I/O heavy, must not be done while awake."""
        with self._lock:
            self._db.execute(
                "INSERT INTO node_fts(node_fts) VALUES('optimize')")
            self._db.commit()
        return True

    def vacuum(self) -> bool:
        """Wants an exclusive lock; impossible underneath a live session."""
        with self._lock:
            self._db.execute("VACUUM")
        return True

    def update_edge(self, src: str, dst: str, *, weight: float | None = None,
                    reason: str | None = None) -> bool:
        """OVERWRITES the weight or the reason of an existing edge.

        `connect` deliberately only strengthens (max/accumulate); this one
        can deliberately weaken. Its single user is distillation's
        edge-reason step: when the model says "these two are unrelated" the
        link is not cut but its weight drops, and the sentence "why related"
        stays on the edge — the one place that compensates, without
        embeddings, for SimHash not knowing synonyms.
        """
        if src == dst or not src or not dst:
            return False
        with self._lock:
            changed = 0
            for a, b in ((src, dst), (dst, src)):
                if weight is not None and reason is not None:
                    changed += self._db.execute(
                        "UPDATE link SET weight=?, reason=? WHERE src=? AND dst=?",
                        (weight, reason, a, b)).rowcount
                elif weight is not None:
                    changed += self._db.execute(
                        "UPDATE link SET weight=? WHERE src=? AND dst=?",
                        (weight, a, b)).rowcount
                elif reason is not None:
                    changed += self._db.execute(
                        "UPDATE link SET reason=? WHERE src=? AND dst=?",
                        (reason, a, b)).rowcount
            self._db.commit()
        return bool(changed)

    def shrink_edges(self, epsilon: float, floor: float) -> tuple[int, int]:
        """Shrinks every edge proportionally, deletes those below the floor.

        Synaptic homeostasis (Tononi-Cirelli): everything strengthened by day
        shrinks proportionally at night. The strong stays strong, the weak
        sinks below the noise and is pruned. A single SQL statement — under
        a second at 300k edges.
        """
        with self._lock:
            shrunk = self._db.execute(
                "UPDATE link SET weight = weight * ?", (1.0 - epsilon,)).rowcount
            removed = self._db.execute(
                "DELETE FROM link WHERE weight < ?", (floor,)).rowcount
            self._db.commit()
        return int(shrunk), int(removed)

    def link(self, src: str, dst: str, *, weight: float = 1.0, reason: str = "") -> None:
        """Links two memories to each other. Association walks over these links."""
        with self._lock:
            self._link(src, dst, weight, reason)
            self._db.commit()

    def _link(self, src: str, dst: str, weight: float, reason: str) -> None:
        if src == dst:
            return
        # The link is bidirectional: recall has no direction.
        for a, b in ((src, dst), (dst, src)):
            self._db.execute(
                "INSERT INTO link(src, dst, weight, reason) VALUES (?,?,?,?)"
                " ON CONFLICT(src, dst) DO UPDATE SET"
                "   weight=max(weight, excluded.weight),"
                # The reason travels with the weight: a stronger link means a
                # better explanation. A "günceller" written over "benzer
                # icerik" must not be lost — the UI draws the chain from it.
                "   reason=CASE WHEN excluded.weight >= weight"
                "               THEN excluded.reason ELSE reason END",
                (a, b, weight, reason),
            )

    def merge_from(self, other_path: Path) -> dict[str, int]:
        """Merges another memory into this one (without overwriting).

        For portability: the memories and links Dornick accumulated on
        another machine join this one. `INSERT OR IGNORE` — since the id is
        the primary key, the same memory does not enter twice (idempotent);
        only new ones are added. What two machines learned can be gathered
        into a single Dornick. FTS updates itself through the trigger; the
        signature index is rebuilt from disk on the next search.
        """
        if not Path(other_path).exists():
            return {"nodes": 0, "links": 0}
        with self._lock:
            # ATTACH does not work inside a transaction: flush everything
            # pending first.
            self._db.commit()
            before_n = self._db.execute("SELECT COUNT(*) FROM node").fetchone()[0]
            before_l = self._db.execute("SELECT COUNT(*) FROM link").fetchone()[0]
            self._db.execute("ATTACH DATABASE ? AS incoming", (str(other_path),))
            try:
                cols = [r["name"] for r in self._db.execute("PRAGMA incoming.table_info(node)")]
                known = ["id", "kind", "title", "body", "tags", "session",
                         "created", "last_used", "uses", "deleted", "sig",
                         "use_log", "supersedes", "superseded_by", "hot",
                         "context"]
                common = ",".join(c for c in known if c in cols)
                if common:
                    self._db.execute(
                        f"INSERT OR IGNORE INTO node({common}) SELECT {common} FROM incoming.node")
                has_link = self._db.execute(
                    "SELECT 1 FROM incoming.sqlite_master WHERE type='table' AND name='link'"
                ).fetchone()
                if has_link:
                    self._db.execute(
                        "INSERT OR IGNORE INTO link(src, dst, weight, reason)"
                        " SELECT src, dst, weight, reason FROM incoming.link")
                self._db.commit()
                after_n = self._db.execute("SELECT COUNT(*) FROM node").fetchone()[0]
                after_l = self._db.execute("SELECT COUNT(*) FROM link").fetchone()[0]
            finally:
                self._db.execute("DETACH DATABASE incoming")
        # Let the signature index be rebuilt from scratch: the new
        # signatures enter RAM.
        with self._index_lock:
            self._index = None
        return {"nodes": after_n - before_n, "links": after_l - before_l}

    def backup_to(self, dest_path: Path) -> None:
        """Writes a consistent, single-file copy of the memory (WAL included).

        Copying the raw file can miss the latest writes in the WAL; SQLite's
        backup API produces a complete copy without locking up. Export uses
        this.
        """
        Path(dest_path).parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            dest = sqlite3.connect(str(dest_path))
            try:
                self._db.backup(dest)
            finally:
                dest.close()

    def reset(self) -> int:
        """Removes every memory and link; returns how many records went.

        Irreversible — the caller must have taken its backup first
        (backup_to). Row-by-row DELETE: the node_ad trigger already cleans
        FTS for every row, no separate 'delete-all' path is needed. The
        signature index is replaced with an empty one so that no ghost
        record stays in RAM and the live app can be reset without closing
        the file.
        """
        with self._lock:
            n = self._db.execute("SELECT COUNT(*) FROM node").fetchone()[0]
            self._db.execute("DELETE FROM node")
            self._db.execute("DELETE FROM link")
            self._db.commit()
        with self._index_lock:
            self._index = vector.Index()
        return int(n)

    def forget(self, node_id: str) -> bool:
        """Leaves a tombstone: what was forgotten and when is part of the
        knowledge too."""
        with self._lock:
            changed = self._db.execute(
                "UPDATE node SET deleted=1 WHERE id=? AND deleted=0", (node_id,)
            ).rowcount
            self._db.commit()
        if changed:
            # Same rationale as remember(): dropped under the lock so that
            # the deleted record does not stay alive in RAM while warm() is
            # building the index.
            with self._index_lock:
                if self._index is not None:
                    self._index.drop(node_id)
        return bool(changed)

    # -- reading -------------------------------------------------------

    def _history_filter(self, prefix: str = "") -> str:
        """SQL fragment that leaves out past versions.

        Returns empty with the mechanism off: the ablation run should go
        through the product's own code, not through a version copied into
        the bench.
        """
        if not switches.ACTIVE.supersede:
            return ""
        return f" AND {prefix}superseded_by=''"

    def open(self, node_id: str) -> Node | None:
        """Fetches the full record and strengthens the trace.

        A memory that is used grows stronger; one that is not falls behind.
        Ranking looks at this.

        Three fields are updated together: `uses` and `last_used` for the UI
        (and for the retroactive fill of old memories), `use_log` for
        activation. The counter knows how many times, the stamp knows when
        — recall needs the second.
        """
        with self._lock:
            row = self._db.execute(
                "SELECT * FROM node WHERE id=? AND deleted=0", (node_id,)
            ).fetchone()
            if row is None:
                return None
            now = self._now()
            history = activation.parse_use_log(
                _field(row, "use_log"), created=row["created"],
                last_used=row["last_used"], uses=int(row["uses"] or 0))
            self._db.execute(
                "UPDATE node SET uses=uses+1, last_used=?, use_log=? WHERE id=?",
                (now, activation.append_use(history, self._clock(),
                                            label=activation.OPENED), node_id),
            )
            self._db.commit()
        node = self._node(row)
        if node.superseded_by:
            # The model may be holding an old id; it should see the way.
            tip = self.current_version(node_id)
            node.body = f"{node.body}\n[güncellendi → {tip}]"
        return node

    def peek(self, node_id: str) -> Node | None:
        """Looks without strengthening. For internal workings; not counted as a use."""
        with self._lock:
            row = self._db.execute(
                "SELECT * FROM node WHERE id=? AND deleted=0", (node_id,)
            ).fetchone()
        return self._node(row) if row else None

    def neighbours(self, node_id: str) -> list[tuple[Node, float]]:
        with self._lock:
            rows = self._db.execute(
                "SELECT n.*, l.weight FROM link l JOIN node n ON n.id = l.dst"
                " WHERE l.src=? AND n.deleted=0 ORDER BY l.weight DESC",
                (node_id,),
            ).fetchall()
        return [(self._node(r), float(r["weight"])) for r in rows]

    def links(self, limit: int = 4000) -> list[tuple[str, str, float]]:
        """All links. The UI draws the network with this.

        Since every link is stored in both directions only one direction is
        returned; otherwise every edge would be drawn twice.
        """
        with self._lock:
            rows = self._db.execute(
                "SELECT l.src, l.dst, l.weight FROM link l"
                " JOIN node a ON a.id = l.src AND a.deleted = 0"
                " JOIN node b ON b.id = l.dst AND b.deleted = 0"
                " WHERE l.src < l.dst LIMIT ?",
                (limit,),
            ).fetchall()
        return [(r["src"], r["dst"], float(r["weight"])) for r in rows]

    def count(self, kind: str | None = None) -> int:
        sql = "SELECT count(*) FROM node WHERE deleted=0" + self._history_filter()
        args: tuple[Any, ...] = ()
        if kind:
            sql += " AND kind=?"
            args = (kind,)
        with self._lock:
            return int(self._db.execute(sql, args).fetchone()[0])

    def recent(self, limit: int = 20) -> list[Node]:
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM node WHERE deleted=0"
                + self._history_filter()
                + " ORDER BY created DESC, rowid DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._node(r) for r in rows]

    def by_kind_any(self, limit: int = 500, *,
                    all_versions: bool = False) -> list[Node]:
        """Undeleted records, newest to oldest. For tag scans.

        `all_versions` is for the time series (`series`): there, past
        versions are not noise but the very thing that is wanted.
        """
        filter_sql = "" if all_versions else self._history_filter()
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM node WHERE deleted=0" + filter_sql
                + " ORDER BY created DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._node(r) for r in rows]

    def by_kind(self, kind: str, limit: int = 50) -> list[Node]:
        """A kind's records, from the liveliest trace to the faintest.

        The ordering cannot be done in SQL: activation is a function of time,
        not a number sitting on disk. So the candidate set is narrowed in
        SQL (usage and freshness, both of which point the same way as
        activation) and the ordering is done in Python. The candidate set is
        kept several times wider than what is asked for so that the
        pre-selection does not drop a genuinely lively trace.

        The old version was `ORDER BY uses DESC` and did not know time: a
        record used heavily years ago could keep yesterday's correction out
        of the soul.
        """
        if not switches.ACTIVE.activation:
            # Ablation: with the mechanism off, the old SQL order (usage,
            # then freshness) is returned as is.
            with self._lock:
                rows = self._db.execute(
                    "SELECT * FROM node WHERE deleted=0 AND kind=?"
                    + self._history_filter()
                    + " ORDER BY uses DESC, created DESC LIMIT ?",
                    (kind, limit),
                ).fetchall()
            return [self._node(r) for r in rows]

        candidates = max(limit * 4, 50)
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM node WHERE deleted=0 AND kind=?"
                + self._history_filter()
                + " ORDER BY uses DESC, created DESC LIMIT ?",
                (kind, candidates),
            ).fetchall()
        nodes = [self._node(r) for r in rows]
        # Stable sort: at equal activation the order SQL gave (usage, then
        # freshness) is preserved.
        nodes.sort(key=lambda n: -n.activation)
        return nodes[:limit]

    # -- recalling -----------------------------------------------------

    def recall(self, query: str, *, limit: int = 8, hops: int = 2,
               context: dict | None = None) -> Recollection:
        """Seeded from the query, spread over the links.

        The returned `trace` carries, in order, the places activation
        visited: the UI can animate it and show recall itself.

        The query first passes through the synonym bridge: a user who types
        "bitcoin" must be able to find a record written as "BTC". The bridge
        is on the search side only — the record stays as written, and the
        index is not rebuilt when the table changes.
        """
        from . import bridge

        query = bridge.expand(query)
        if not _match_expression(query):
            # An empty query is not a search but a browse: the newest records.
            recent = self.recent(limit)
            return Recollection(
                query=query,
                hits=recent,
                trace=[Step(node=n.id, kind=n.kind, activation=1.0, hop=0, via="query")
                       for n in recent],
            )

        seeds = self._seed(query, limit * 2, context=context)
        scores: dict[str, float] = {}
        trace: list[Step] = []

        frontier: list[tuple[str, float, str]] = []
        for node_id, score, kind in seeds:
            scores[node_id] = score
            trace.append(Step(node=node_id, kind=kind, activation=score, hop=0, via="query"))
            frontier.append((node_id, score, kind))

        for hop in range(1, hops + 1):
            nxt: list[tuple[str, float, str]] = []
            for node_id, strength, _kind in frontier:
                for neighbour, weight in self.neighbours(node_id):
                    # Association arriving at a past version is redirected to
                    # the current one: the old record's neighbourhood is not
                    # lost, it is carried over.
                    target = neighbour
                    if neighbour.superseded_by and switches.ACTIVE.supersede:
                        tip = self.peek(self.current_version(neighbour.id))
                        if tip is None or tip.id == node_id:
                            continue
                        target = tip
                    # A forgotten node does not pass the association path on:
                    # a path running over a record whose activation has died
                    # out was the quietest way of drifting off topic.
                    spread = (strength * weight * HOP_DECAY
                              * activation.spread_factor(target.activation))
                    if spread < MIN_ACTIVATION or spread <= scores.get(target.id, 0.0):
                        continue
                    scores[target.id] = spread
                    trace.append(
                        Step(node=target.id, kind=target.kind,
                             activation=spread, hop=hop, via=node_id)
                    )
                    nxt.append((target.id, spread, target.kind))
            frontier = nxt
            if not frontier:
                break

        ranked = sorted(scores.items(), key=lambda kv: -kv[1])[:limit]
        hits = [node for node in (self.peek(nid) for nid, _ in ranked) if node]
        return Recollection(query=query, hits=hits, trace=trace)

    def _seed(self, query: str, limit: int,
              *, context: dict | None = None) -> list[tuple[str, float, str]]:
        """The records the query first touches.

        Two channels work together because each alone is incomplete:

            literal    the FTS5 index — finds a record saying "postgres"
                       for certain, never finds one saying "database dump".
            signature  the association vector — brings close text even when
                       the words do not match, but cannot single out an
                       exact match.

        The union of the two is taken; a record in both keeps the high score.
        The literal channel is kept slightly ahead: a term that matches
        verbatim is stronger evidence than a text that merely looks similar.
        """
        lit: dict[str, float] = {}
        sig: dict[str, float] = {}
        kinds: dict[str, str] = {}

        for node_id, score, kind in self._seed_literal(query, limit):
            lit[node_id] = score
            kinds[node_id] = kind

        for node_id, score in self._seed_signature(query, limit):
            sig[node_id] = round(score * SIGNATURE_WEIGHT, 4)

        # Noisy-or combination: merge two independent pieces of evidence
        # while preserving MAGNITUDE. The score is high if EITHER channel is
        # confident; low only if BOTH are weak. So a paraphrase with no word
        # overlap gains confidence from the signature channel, an exact match
        # from the literal; an empty query (both channels weak) stays low and
        # can be separated by a threshold. The old MAX combination let the
        # literal swallow the signature; the old rank-based literal score
        # also threw away magnitude and always made top1 1.0 — both had the
        # same root.
        scores: dict[str, float] = {}
        for node_id in set(lit) | set(sig):
            miss = (1.0 - lit.get(node_id, 0.0)) * (1.0 - sig.get(node_id, 0.0))
            scores[node_id] = round(1.0 - miss, 4)

        if missing := [n for n in scores if n not in kinds]:
            kinds.update(self._kinds_of(missing))

        if context:
            scores = self._context_bonus(scores, context)

        ranked = sorted(scores.items(), key=lambda kv: -kv[1])[:limit]
        return [(node_id, score, kinds.get(node_id, "fact")) for node_id, score in ranked]

    def _context_bonus(self, scores: dict[str, float],
                       context: dict) -> dict[str, float]:
        """Brings records written in the same context forward.

        The "crypto note while in SCADA" leak had until now been held down
        with digit-stripping and stem-counting tricks; both were filters
        bolted on afterwards, not belonging to the search itself. The
        context field was already being written, search just did not read
        it.

        Old records with an empty context get no bonus but **no penalty
        either**: migration must not push what the user accumulated over
        years to the back.
        """
        if not switches.ACTIVE.context or not scores:
            return scores
        ids = list(scores)
        placeholders = ",".join("?" * len(ids))
        with self._lock:
            rows = self._db.execute(
                f"SELECT id, context FROM node WHERE id IN ({placeholders})",
                tuple(ids)).fetchall()
        for row in rows:
            stored = _parse_context(row["context"])
            if not stored:
                continue
            shared = sum(1 for key, value in context.items()
                         if key in stored and stored[key] == value)
            conflicting = sum(1 for key, value in context.items()
                              if key in stored and stored[key] != value)
            # Scaled by the fields the QUERY context carries, not a fixed
            # three: a session that knows only its project must be able to
            # apply the whole penalty on a project conflict. With "/3" a
            # single-field conflict kept two thirds of its score, and the
            # kobyte record out-ranked the koru1000 one on a two-word match
            # (E cluster: 11 forbidden leaks, precision 0.22).
            fields = max(1, len(context))
            if shared:
                scores[row["id"]] = round(
                    min(1.0, scores[row["id"]] * (1 + CONTEXT_BONUS * shared / fields)), 4)
            elif conflicting:
                # A record carrying a DIFFERENT value in the same field:
                # kobyte's report while in the koru1000 session. Not the
                # same thing as an empty context — emptiness is missing
                # information, conflict is information itself. Not deleted,
                # just harder to get ahead.
                scores[row["id"]] = round(
                    scores[row["id"]]
                    * max(CONTEXT_FLOOR, 1 - CONTEXT_PENALTY * conflicting / fields), 4)
        return scores

    def _seed_literal(self, query: str, limit: int) -> list[tuple[str, float, str]]:
        """Exact contact through FTS. No scan: the index goes from term to record.

        Two stages. FTS narrows the field (any query stem, bm25 order); the
        candidates are then RE-SCORED by IDF-weighted coverage:

            score = Σ idf(stem matched) / Σ idf(stem in query)

        The previous score was bm25 squashed with x/(1+x). Measured on the
        life bench (2026-09-04): a record matching ONE common word ("eski",
        "hangi", "yapılıyor", "kodu") scored 0.45 and the expected record
        matching four rare words scored 0.50 — no separation, so every
        question dragged five near-ties into the prime and precision sat at
        0.27. That is the "seed saturation" the roadmap named. Coverage
        weighted by rarity gives the four-word match 0.76 and the one-word
        match 0.20 on the same question.

        Question words ("neydi", "hangi", "nerede") are function words and
        never reach the stems (vector.STOPWORDS). A content word no record
        contains stays in the denominator at full rarity weight: a query
        about a topic memory has never seen scores low on every record, and
        silence is the right answer.
        """
        expression = _match_expression(query)
        if not expression:
            return []
        stems = _query_prefixes(query)
        weights = self._idf(stems)
        total = sum(weights.values())
        if total <= 0.0:
            return []
        with self._lock:
            rows = self._db.execute(
                "SELECT n.id, n.kind, n.title, n.body, n.tags, n.uses, n.created,"
                " n.last_used, n.use_log, bm25(node_fts) AS rank"
                " FROM node_fts JOIN node n ON n.rowid = node_fts.rowid"
                " WHERE node_fts MATCH ? AND n.deleted=0"
                + self._history_filter("n.")
                + " ORDER BY rank LIMIT ?",
                (expression, max(LITERAL_POOL, limit * 4)),
            ).fetchall()

        out: list[tuple[str, float, str]] = []
        for row in rows:
            words = _WORD.findall(f"{row['title']} {row['body']} {row['tags']}".casefold())
            covered = sum(w for stem, w in weights.items()
                          if any(word.startswith(stem) for word in words))
            coverage = covered / total
            if coverage <= 0.0:
                continue
            # A lively trace wakes more easily; even the most forgotten record
            # keeps half its score (activation.SEED_FLOOR) so it falls behind
            # but does not drop out of the search.
            factor = activation.seed_factor(self._base_level(row))
            out.append((row["id"], round(min(1.0, coverage * factor), 4), row["kind"]))
        out.sort(key=lambda t: -t[1])
        return out[:limit]

    def _idf(self, stems: Sequence[str]) -> dict[str, float]:
        """Rarity weight of each stem: ln(1 + N / df) over the live records.

        Document frequency is a prefix MATCH count on the FTS index — the
        same prefix semantics the seed expression uses, and an index walk,
        not a scan. (An `fts5vocab` range query was tried first and corrupted
        the interpreter under load; the MATCH path is the well-trodden one.)
        A stem no record contains is the RAREST stem of all, and it counts
        fully — dropping it from the denominator was tried first and it
        backfired on trap questions: "Kuzenimin düğünü ne zamandı?" lost
        "düğün" and "kuzen" as unknown, "zaman" alone became 100% coverage,
        and a procedure about "zamanlanmış görev" primed at 0.55. The user
        asked about a wedding; memory holding nothing about weddings is the
        evidence, not noise.
        """
        if not stems:
            return {}
        with self._lock:
            live = self._db.execute(
                "SELECT count(*) FROM node WHERE deleted=0").fetchone()[0]
            # The count is CAPPED and CACHED so search cost does not grow
            # with memory: counting every posting of a word that is in three
            # thousand records made recall scale with the archive again (the
            # P-set growth test caught it). Past DF_CAP a stem is "common"
            # and its exact count changes the weight by nothing that matters;
            # the cache is refreshed when the store has grown by a tenth.
            if live > self._df_live * 1.1 or live < self._df_live:
                self._df_cache.clear()
                self._df_live = live
            out: dict[str, float] = {}
            for stem in stems:
                term = stem.replace('"', "")
                if not term:
                    continue
                df = self._df_cache.get(stem)
                if df is None:
                    df = self._db.execute(
                        "SELECT count(*) FROM (SELECT rowid FROM node_fts"
                        " WHERE node_fts MATCH ? LIMIT ?)",
                        (f'"{term}"*', DF_CAP)).fetchone()[0]
                    self._df_cache[stem] = df
                out[stem] = math.log(1.0 + live / max(1, df))
        return out

    def _seed_signature(self, query: str, limit: int) -> list[tuple[str, float]]:
        """Associative contact: records that sit close even when the words differ."""
        # The index property takes its own lock; the lock is not reentrant,
        # so it must be touched here outside the lock.
        index = self.index
        if not len(index):
            return []
        found = index.search(vector.signature(query), limit)
        if not found:
            return []
        # The signature channel returns only id and similarity; a single
        # batch query suffices for activation (as many candidates as
        # `limit`, dozens).
        levels = self._base_levels([n for n, _ in found])
        return [(n, round(p * activation.seed_factor(levels.get(n, activation.NO_BASE)), 4))
                for n, p in found]

    def _base_levels(self, node_ids: Sequence[str]) -> dict[str, float]:
        if not node_ids:
            return {}
        placeholders = ",".join("?" * len(node_ids))
        with self._lock:
            rows = self._db.execute(
                "SELECT id, created, last_used, uses, use_log FROM node"
                f" WHERE id IN ({placeholders}) AND deleted=0",
                tuple(node_ids),
            ).fetchall()
        return {row["id"]: self._base_level(row) for row in rows}

    def _kinds_of(self, node_ids: Sequence[str]) -> dict[str, str]:
        placeholders = ",".join("?" * len(node_ids))
        with self._lock:
            rows = self._db.execute(
                f"SELECT id, kind FROM node WHERE id IN ({placeholders}) AND deleted=0",
                tuple(node_ids),
            ).fetchall()
        return {row["id"]: row["kind"] for row in rows}


# ---------------------------------------------------------------------


def _match_expression(query: str) -> str:
    """Turns the query into an FTS5 expression.

    Because Turkish is agglutinative, the suffix shows up in both
    directions: the user may type "rapor" while the record says "raporlari",
    or the reverse. So every term goes in twice —

        "rapor"*    the term itself, also catches records carrying a suffix
        "rapor"     the stem guess, catches it when the term itself came
                    with a suffix

    No stemming is done: a proper stemmer for Turkish means an extra
    dependency, and a wrong stem is worse than no match at all. The first
    STEM_CHARS characters do the same job in practice.

    Terms are OR'ed — a record matching one of them must also be able to
    start the association; bm25 does the ranking anyway.
    """
    # Function words are dropped (same list as the signature side): words
    # like "bir", "ne" were wrongly waking up general memories in FTS.
    terms = [t for t in (m.group(0) for m in _WORD.finditer(query or ""))
             if len(t) > 1 and t.lower() not in vector.STOPWORDS]
    if not terms:
        return ""

    parts: list[str] = []
    for term in terms:
        parts.append(f'"{term}"*')
        if len(term) > STEM_CHARS:
            parts.append(f'"{term[:STEM_CHARS]}"*')
    # Asking for the same stem twice does not break bm25 but bloats the
    # expression.
    return " OR ".join(dict.fromkeys(parts))


def _query_prefixes(query: str) -> list[str]:
    """The stems `_match_expression` searches for, as plain prefixes."""
    terms = [t for t in (m.group(0) for m in _WORD.finditer((query or "").casefold()))
             if len(t) > 1 and t not in vector.STOPWORDS]
    return list(dict.fromkeys(t[:STEM_CHARS] for t in terms))


def _parse_context(raw) -> dict:
    """The context field on disk. Empty if broken — not a penalty, missing
    information."""
    if not raw:
        return {}
    try:
        value = json.loads(raw) if isinstance(raw, str) else raw
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def _first_line(text: str) -> str:
    return next((line.strip() for line in text.splitlines() if line.strip()), "(başlıksız)")


def _field(row: sqlite3.Row, name: str):
    """Reads a column that may be absent from the row.

    An old memory may be read before migration, or a query may not have
    selected the column; absence is not an error, it is missing information.
    """
    try:
        return row[name]
    except (IndexError, KeyError):
        return None


def _to_node(row: sqlite3.Row, *, level: float = activation.NO_BASE) -> Node:
    return Node(
        activation=level,
        supersedes=_field(row, "supersedes") or "",
        superseded_by=_field(row, "superseded_by") or "",
        deleted=bool(_field(row, "deleted") or 0),
        hot=bool(1 if _field(row, "hot") is None else _field(row, "hot")),
        context=_parse_context(_field(row, "context")),
        id=row["id"],
        kind=row["kind"],
        title=row["title"],
        body=row["body"],
        tags=[t for t in (row["tags"] or "").split() if t],
        session=row["session"],
        created=row["created"],
        last_used=row["last_used"],
        uses=int(row["uses"]),
    )


def trace_to_json(trace: Sequence[Step]) -> str:
    return json.dumps([asdict(step) for step in trace], ensure_ascii=False)
