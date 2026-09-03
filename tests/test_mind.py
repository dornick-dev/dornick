"""Mind layer tests.

Focus: persistence (does it survive a reopen), search precision, and whether
the mind is really wired into the loop.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
from pathlib import Path

import pytest

from dornick.config import Config
from dornick.events import EventLog
from dornick.mind import Mind, open_mind
from dornick.mind.search import rank, tokenize
from dornick.session import PendingToolUse, Session
from dornick.tools import ToolContext, build_registry, execute
from dornick.permissions import PermissionEngine


@pytest.fixture()
def mind(tmp_path: Path) -> Mind:
    return open_mind(tmp_path / "mind", tmp_path / "sessions", "cur")


# -- ranking -----------------------------------------------------------


def test_stopwords_are_dropped() -> None:
    assert "ve" not in tokenize("kahve ve çay")
    assert "kahve" in tokenize("kahve ve çay")


def test_rare_terms_outrank_common_ones() -> None:
    items = [
        "dosya okuma hakkında not",
        "dosya yazma hakkında not",
        "dosya silme ve postgres bağlantısı hakkında not",
    ]
    hits = rank("postgres dosya", items, text_of=lambda s: s, limit=3)
    # "dosya" is in every document, "postgres" is rare — the rare one must decide the order.
    assert "postgres" in hits[0].item


@pytest.mark.parametrize(
    ("query", "document"),
    [
        ("rapor", "raporları hazırladım"),      # query is the stem, document suffixed
        ("raporları", "rapor formatı"),          # query suffixed, document is the stem
        ("yedek", "yedeklemeyi otomatikleştir"), # a suffix inserted in between
        ("dosya", "dosyaların listesi"),
    ],
)
def test_suffixed_forms_match_the_stem(query: str, document: str) -> None:
    """Turkish is agglutinative — exact word matching loses half of search."""
    hits = rank(query, [document, "tamamen alakasız bir metin"], text_of=lambda s: s)
    assert hits and hits[0].item == document


def test_short_words_do_not_prefix_match() -> None:
    """Prefix matching produces noise for short words; they must match exactly."""
    hits = rank("kar", ["karpuz kavun", "kar yağıyor"], text_of=lambda s: s)
    assert [h.item for h in hits] == ["kar yağıyor"]


def test_empty_query_returns_newest_first(mind: Mind) -> None:
    mind.remember("ilk", title="ilk")
    mind.remember("ikinci", title="ikinci")
    hits = mind.recall("", limit=2)
    assert hits[0].item.title == "ikinci"


# -- semantic memory ---------------------------------------------------


def test_memories_survive_reopen(tmp_path: Path) -> None:
    first = open_mind(tmp_path / "mind", tmp_path / "sessions", "s1")
    saved = first.remember(
        "Kullanıcı PowerShell kullanıyor, bash değil.", kind="preference", tags=["kabuk"]
    )

    reopened = open_mind(tmp_path / "mind", tmp_path / "sessions", "s2")
    assert [m.id for m in reopened.memories()] == [saved.id]
    assert reopened.memories()[0].kind == "preference"


def test_forget_is_a_tombstone_not_a_deletion(tmp_path: Path) -> None:
    mind = open_mind(tmp_path / "mind", tmp_path / "sessions")
    memory = mind.remember("yanlış bir bilgi")
    mind.forget(memory.id)

    assert mind.memories() == []
    assert mind.forget(memory.id) is None  # cannot be deleted twice

    # Tombstone: the record was not deleted, it was marked. What was
    # forgotten and when is part of the mind too; since the store is now
    # indexed the mark lives there.
    with sqlite3.connect(tmp_path / "mind" / "recall.db") as db:
        rows = db.execute("SELECT deleted FROM node WHERE id=?", (memory.id,)).fetchall()
    assert rows == [(1,)]


def test_recall_filters_by_kind(mind: Mind) -> None:
    mind.remember("git rebase yordamı", kind="procedure", title="rebase")
    mind.remember("git hakkında bir olgu", kind="fact", title="olgu")

    hits = mind.recall("git", kind="procedure")
    assert [h.item.title for h in hits] == ["rebase"]


# -- goals -------------------------------------------------------------


def test_goal_lifecycle_and_digest(mind: Mind) -> None:
    a = mind.push_goal("veriyi topla")
    b = mind.push_goal("raporu yaz")

    digest = mind.goal_digest()
    assert "veriyi topla" in digest and "raporu yaz" in digest

    mind.set_goal_status(a.id, "done", note="bitti")
    assert "veriyi topla" not in mind.goal_digest()
    assert [g.id for g in mind.goals()] == [b.id]


def test_snapshot_lists_only_active_goals(mind: Mind) -> None:
    """The goal panel in the UI is seeded from the snapshot on page refresh:
    the dump must carry only the active ones — id, text and whether the item
    is left over from a past session (`eski`). A mindless agent (or a read
    that blows up) means an empty list — the chat must not go down."""
    from dornick.desktop import _active_goals

    keep = mind.push_goal("kalan iş")
    done = mind.push_goal("biten iş")
    mind.set_goal_status(done.id, "done")

    agent = type("A", (), {"mind": mind})()
    assert _active_goals(agent) == [
        {"id": keep.id, "text": "kalan iş", "eski": False}]
    assert _active_goals(type("A", (), {"mind": None})()) == []
    assert _active_goals(object()) == []


def test_goals_survive_reopen(tmp_path: Path) -> None:
    first = open_mind(tmp_path / "mind", tmp_path / "sessions")
    goal = first.push_goal("kalıcı hedef")
    first.set_goal_status(goal.id, "done")

    reopened = open_mind(tmp_path / "mind", tmp_path / "sessions")
    assert reopened.goals() == []
    assert reopened.goals(active_only=False)[0].status == "done"


# -- episodic ----------------------------------------------------------


def _write_session(sessions: Path, name: str, user_text: str, tool: str) -> None:
    sessions.mkdir(parents=True, exist_ok=True)
    log = EventLog(sessions / f"{name}.jsonl")
    log.message("user", [{"type": "text", "text": user_text}])
    log.note("tool_start", tool=tool)
    log.message("assistant", [{"type": "text", "text": "yapıldı"}])
    log.close()


def test_episodes_search_past_sessions(tmp_path: Path) -> None:
    sessions = tmp_path / "sessions"
    _write_session(sessions, "20260101T000000Z", "postgres yedeğini al", "shell")
    _write_session(sessions, "20260102T000000Z", "tatil fotoğraflarını sırala", "list_dir")

    mind = open_mind(tmp_path / "mind", sessions, "cur")
    hits = mind.episodes("postgres yedek")

    assert hits and hits[0].item.session_id == "20260101T000000Z"
    assert "shell" in hits[0].item.tools


def test_current_session_is_excluded_from_episodes(tmp_path: Path) -> None:
    """The current session is already in the context; bringing it back wastes tokens."""
    sessions = tmp_path / "sessions"
    _write_session(sessions, "cur", "postgres yedeğini al", "shell")

    mind = open_mind(tmp_path / "mind", sessions, "cur")
    assert mind.episodes("postgres") == []
    assert mind.episodes("postgres", include_current=True)


# -- tool surface ------------------------------------------------------


@pytest.fixture()
def ctx(tmp_path: Path, mind: Mind) -> ToolContext:
    config = Config.load(tmp_path)
    config.ensure_dirs()
    session = Session(EventLog(tmp_path / "s.jsonl"), "cur")
    return ToolContext(config=config, session=session, cancel=asyncio.Event())


async def _call(registry, ctx, name: str, args: dict, *, expect_error: bool = False) -> str:
    """Calls the tool and verifies the error state.

    The executor catches the exception inside the tool and turns it into an
    error result — correct behaviour, but if the test does not check it a
    crashing tool silently looks like it 'passed'. That happened exactly
    once.
    """
    blocks = await execute(
        [PendingToolUse("x", name, args)],
        registry=registry,
        permissions=PermissionEngine("yolo", allow=[], deny=[]),
        ctx=ctx,
        approve=lambda *_: asyncio.sleep(0, result=True),
    )
    block = blocks[0]
    assert block["is_error"] is expect_error, block["content"]
    return block["content"]


async def test_mind_tools_are_registered_only_with_a_mind(mind: Mind) -> None:
    assert "mind_recall" not in build_registry()
    assert "mind_recall" in build_registry(mind)


async def test_save_then_recall_through_the_tool_surface(ctx: ToolContext, mind: Mind) -> None:
    registry = build_registry(mind)

    await _call(
        registry,
        ctx,
        "mind_memory",
        {"action": "save", "content": "Kullanıcı raporları xlsx istiyor.", "kind": "preference"},
    )
    found = await _call(registry, ctx, "mind_recall", {"query": "rapor formatı", "scope": "memory"})

    assert "xlsx" in found


async def test_recall_says_so_when_nothing_is_known(ctx: ToolContext, mind: Mind) -> None:
    registry = build_registry(mind)
    out = await _call(registry, ctx, "mind_recall", {"query": "hiç konuşulmamış konu"})
    assert "kayıt yok" in out


async def test_introspect_flags_repeated_identical_calls(ctx: ToolContext, mind: Mind) -> None:
    """Retrying the same call back to back is the most common way of getting stuck; the mind must see it."""
    for _ in range(3):
        ctx.session.log.note("tool_start", tool="shell", input={"command": "make build"})
        ctx.session.log.note("tool_end", tool="shell", ms=10, error=True)

    registry = build_registry(mind)
    report = await _call(registry, ctx, "mind_introspect", {"aspect": "session"})

    assert "3+ kez aynı argümanlarla" in report
    assert "3 hata" in report


async def test_goal_tool_updates_digest(ctx: ToolContext, mind: Mind) -> None:
    registry = build_registry(mind)
    out = await _call(registry, ctx, "mind_goals", {"action": "push", "text": "testi geçir"})
    assert "testi geçir" in out
    assert mind.goals()[0].text == "testi geçir"


# -- conversation history: NOT memories, raw sessions ------------------


def test_sessions_lists_past_conversations_newest_first(tmp_path):
    """The chat list: past sessions, newest to oldest. This is not a list of
    memories — it is the raw conversations themselves."""
    from dornick.events import EventLog
    from dornick.mind import open_mind

    sessions = tmp_path / "sessions"
    sessions.mkdir(parents=True)
    for stem, turns in [
        ("20260610T090000Z", [("user", "çorum pompa verimi ne"), ("assistant", "%72")]),
        ("20260612T140000Z", [("user", "modbus kopuyor"), ("assistant", "yeni bağlantı aç")]),
    ]:
        log = EventLog(sessions / f"{stem}.jsonl")
        for r, t in turns:
            log.append("message", role=r, content=t)
        log.close()

    mind = open_mind(tmp_path / "mind", sessions, "cur")
    got = mind.sessions()
    assert len(got) == 2
    assert got[0].session_id == "20260612T140000Z"  # newest first


def test_transcript_returns_spoken_turns_with_trace(tmp_path):
    """The transcript carries the text turns AND the turn's trace: tool calls
    as a one-line summary (not raw arguments), thinking in a separate field —
    so the strip can be rebuilt in a reopened chat (live wound, 01.09)."""
    from dornick.events import EventLog
    from dornick.mind import open_mind

    sessions = tmp_path / "sessions"
    sessions.mkdir(parents=True)
    log = EventLog(sessions / "20260610T090000Z.jsonl")
    log.append("message", role="user", content="kuyu seviyesi ne kadar")
    log.append("message", role="assistant", content=[
        {"type": "thinking", "thinking": "Önce dosyaya bakayım."},
        {"type": "text", "text": "Seviye 2,77 m."},
        {"type": "tool_use", "name": "shell", "input": {"command": "cat x"}},
    ])
    log.close()

    mind = open_mind(tmp_path / "mind", sessions, "cur")
    turns = mind.transcript("20260610T090000Z")
    assert turns == [
        {"role": "user", "text": "kuyu seviyesi ne kadar"},
        {"role": "assistant", "text": "Seviye 2,77 m.",
         "dusunme": "Önce dosyaya bakayım.",
         "adimlar": [{"tool": "shell", "ozet": "cat x"}]},
    ]


def test_transcript_orphan_trace_attaches_to_empty_turn(tmp_path):
    """The trace of a turn cut without text is not lost: it attaches to a
    textless assistant turn before the next user utterance."""
    from dornick.events import EventLog
    from dornick.mind import open_mind

    sessions = tmp_path / "sessions"
    sessions.mkdir(parents=True)
    log = EventLog(sessions / "20260610T100000Z.jsonl")
    log.append("message", role="user", content="dosyayı düzelt")
    log.append("message", role="assistant", content=[
        {"type": "tool_use", "name": "edit_file", "input": {"path": "a.py"}},
    ])
    log.append("message", role="user", content="dur, vazgeçtim")
    log.close()

    mind = open_mind(tmp_path / "mind", sessions, "cur")
    turns = mind.transcript("20260610T100000Z")
    assert turns == [
        {"role": "user", "text": "dosyayı düzelt"},
        {"role": "assistant", "text": "",
         "adimlar": [{"tool": "edit_file", "ozet": "a.py"}]},
        {"role": "user", "text": "dur, vazgeçtim"},
    ]


def test_transcript_cache_serves_unchanged_file(tmp_path):
    """The transcript of an unchanged file comes from the cache (the deep
    search used to re-parse 40 sessions on every exchange)."""
    from dornick.events import EventLog
    from dornick.mind import open_mind

    sessions = tmp_path / "sessions"
    sessions.mkdir(parents=True)
    log = EventLog(sessions / "20260610T110000Z.jsonl")
    log.append("message", role="user", content="merhaba")
    log.close()

    mind = open_mind(tmp_path / "mind", sessions, "cur")
    first = mind.transcript("20260610T110000Z")
    assert first and first[0]["text"] == "merhaba"
    # The same object must come back: the file did not change, parsing was not repeated.
    assert mind.transcript("20260610T110000Z") is first


def test_projects_assign_and_clear(tmp_path):
    """A conversation can be attached to a project and detached; it persists
    and an empty name removes the attachment. A conversation is not a memory
    — this is only a folder."""
    from dornick.mind import open_mind

    sessions = tmp_path / "sessions"
    sessions.mkdir(parents=True)
    mind = open_mind(tmp_path / "mind", sessions, "cur")

    assert mind.projects() == {}
    mind.set_project("20260610T090000Z", "Çorum SCADA")
    assert mind.projects()["20260610T090000Z"] == "Çorum SCADA"

    # Preserved on reopen (written to disk).
    again = open_mind(tmp_path / "mind", sessions, "cur")
    assert again.projects()["20260610T090000Z"] == "Çorum SCADA"

    # An empty name removes the attachment.
    again.set_project("20260610T090000Z", "")
    assert "20260610T090000Z" not in again.projects()


# -- body cap ----------------------------------------------------------


def test_recall_answers_are_body_capped(tmp_path):
    """It was unbounded: one episode record (a compaction digest of up to
    8,000 characters) ate thousands of tokens in a single hit and drowned the
    real match. The clipped part is not a loss — the model can narrow the
    query and search again, and the answer says so."""
    from dornick.mind.tools import RECALL_BODY_CAP, _bounded

    short = "kısa kayıt"
    assert _bounded(short) == short

    long = "postgres " * 400
    cut = _bounded(long)
    assert len(cut) < len(long)
    assert cut.startswith(long[:RECALL_BODY_CAP])
    assert "kırpıldı" in cut


# -- session identity and transcript search ----------------------------
#
# Until now the title was derived from the first words of the digest: cheap
# but not a name the user chose. Someone looking for "where was that CMS
# job?" is looking for the name they gave it — or a phrase spoken in the
# middle of the conversation.


def _fake_session(sessions_dir: Path, sid: str, turns: list[tuple[str, str]]) -> None:
    """A fake session log: role + text lines."""
    sessions_dir.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps({"kind": "note", "name": "session_start"})]
    for role, text in turns:
        lines.append(json.dumps({
            "kind": "message", "role": role,
            "content": [{"type": "text", "text": text}],
        }, ensure_ascii=False))
    (sessions_dir / f"{sid}.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_a_conversation_can_be_named_and_tagged(tmp_path: Path, mind: Mind) -> None:
    record = mind.set_session_meta("s1", name="CMS göçü", tags=["cms", "acil"])
    # NOT exact dict equality: the record later gained new fields
    # (model/path/provider — the window handover work) and every new field
    # must not break this test. The test checks that the two fields we gave
    # come back correctly.
    assert record["ad"] == "CMS göçü"
    assert record["etiketler"] == ["cms", "acil"]

    # Also there when read fresh from disk: the panel re-reads on every open.
    fresh = open_mind(tmp_path / "mind", tmp_path / "sessions", "cur")
    assert fresh.session_meta()["s1"]["ad"] == "CMS göçü"


def test_archive_moves_the_log_out_of_the_list(tmp_path: Path, mind: Mind) -> None:
    """Archiving is not permanent deletion: the log goes to sessions/.arsiv,
    drops from the list, and the name/project mapping goes too. The open
    session is not moved."""
    sid = "20260610T090000Z"
    _fake_session(mind.sessions_dir, sid, [("user", "pompa"), ("assistant", "ok")])
    mind.set_session_meta(sid, name="Pompa")
    mind.set_project(sid, "SCADA")
    assert any(e.session_id == sid for e in mind.sessions())

    out = mind.archive_session(sid)
    assert out["ok"] is True
    assert not (mind.sessions_dir / f"{sid}.jsonl").is_file()
    assert (mind.sessions_dir / ".arsiv" / f"{sid}.jsonl").is_file()
    assert sid not in mind.session_meta()
    assert sid not in mind.projects()
    assert all(e.session_id != sid for e in mind.sessions())

    (mind.sessions_dir / "cur.jsonl").write_text("{}\n", encoding="utf-8")
    assert mind.archive_session("cur")["ok"] is False
    assert mind.archive_session("yok")["ok"] is False


def test_touching_one_field_leaves_the_other_alone(tmp_path: Path, mind: Mind) -> None:
    """A request that changes only the tags must not delete the name."""
    mind.set_session_meta("s1", name="CMS göçü", tags=["cms"])
    record = mind.set_session_meta("s1", tags=["cms", "borsa"])
    assert record["ad"] == "CMS göçü"
    record = mind.set_session_meta("s1", name="Yeni ad")
    assert record["etiketler"] == ["cms", "borsa"]


def test_tags_are_normalised_and_bounded(tmp_path: Path, mind: Mind) -> None:
    """A tag is a filter key: "CMS" and "cms" cannot be two separate sets."""
    record = mind.set_session_meta(
        "s1", tags=["  CMS  ", "cms", "Borsa", "", "   "])
    assert record["etiketler"] == ["cms", "borsa"]
    # Bound: more than eight tags on one conversation is unreadable in the panel.
    many = mind.set_session_meta("s2", tags=[f"e{i}" for i in range(20)])
    assert len(many["etiketler"]) == 8


def test_an_empty_name_and_no_tags_drops_the_record(tmp_path: Path, mind: Mind) -> None:
    """Deleting the name means falling back to the derived title; empty records must not pile up in the file."""
    mind.set_session_meta("s1", name="Bir ad")
    mind.set_session_meta("s1", name="")
    assert "s1" not in mind.session_meta()


def test_session_meta_keeps_path_and_model(tmp_path: Path, mind: Mind) -> None:
    """If a folder/model is attached the record does not drop even when the name is deleted."""
    mind.set_session_meta(
        "s1", name="İş", path=r"D:\proj\foo", model="openai/gpt-4o-mini")
    record = mind.set_session_meta("s1", name="")
    assert record["path"].endswith("foo")
    assert record["model"] == "openai/gpt-4o-mini"
    assert "s1" in mind.session_meta()


def test_binding_a_folder_also_files_the_chat_under_that_project(
    tmp_path: Path, mind: Mind
) -> None:
    """Attaching a folder groups the conversation under that folder's name.

    Like Cursor Repositories: path=...\\dornick → project label 'dornick'. A
    manually given project name is not overwritten.
    """
    mind.set_session_meta("s1", path=r"C:\projeler\Fatih\dornick")
    assert mind.projects().get("s1") == "dornick"
    # Second path write: a label already exists → leave it alone.
    mind.set_project("s1", "Dornick SCADA")
    mind.set_session_meta("s1", path=r"C:\projeler\Fatih\dornick")
    assert mind.projects().get("s1") == "Dornick SCADA"
    # No path and no project either → stays empty.
    mind.set_project("s2", "")
    mind.set_session_meta("s2", name="yalnız ad")
    assert "s2" not in mind.projects()


def test_a_corrupt_meta_file_does_not_break_the_panel(tmp_path: Path, mind: Mind) -> None:
    """A file corrupted by hand editing must not shut down the history panel."""
    (tmp_path / "sessions").mkdir(parents=True, exist_ok=True)
    (tmp_path / "sessions" / "_oturumlar.json").write_text("{bozuk", encoding="utf-8")
    assert mind.session_meta() == {}


def test_the_raw_logs_are_never_touched_by_naming(tmp_path: Path, mind: Mind) -> None:
    """Memories are produced from the logs: a manually given name would mean
    rewriting history."""
    sessions = tmp_path / "sessions"
    _fake_session(sessions, "20260101T000000Z", [("user", "merhaba")])
    before = (sessions / "20260101T000000Z.jsonl").read_bytes()
    mind.set_session_meta("20260101T000000Z", name="Selamlaşma", tags=["x"])
    assert (sessions / "20260101T000000Z.jsonl").read_bytes() == before


def test_search_finds_words_spoken_inside_a_conversation(tmp_path: Path, mind: Mind) -> None:
    """The searched phrase is mostly not in the title but in the middle of the conversation."""
    sessions = tmp_path / "sessions"
    _fake_session(sessions, "20260101T000000Z", [
        ("user", "selam"),
        ("assistant", "Kayseri OSB için SCADA teklifini hazırladım."),
    ])
    _fake_session(sessions, "20260102T000000Z", [("user", "hava nasıl")])

    found = mind.search_transcripts("scada")
    assert set(found) == {"20260101T000000Z"}
    hit = found["20260101T000000Z"][0]
    assert hit["role"] == "assistant"
    assert "SCADA" in hit["text"]

    # Empty when nothing matches: "no results" and "everything" must not be confused.
    assert mind.search_transcripts("bulunmayan-sozcuk") == {}
    # A very short query is not scanned: a single letter occurs in every conversation.
    assert mind.search_transcripts("a") == {}


def test_search_clips_the_quote_and_caps_the_hits(tmp_path: Path, mind: Mind) -> None:
    """Returning the whole turn would turn the list into a wall."""
    sessions = tmp_path / "sessions"
    long_text = "dolgu " * 200 + "ANAHTAR" + " dolgu" * 200
    _fake_session(sessions, "20260101T000000Z",
                  [("user", long_text)] + [("user", "ANAHTAR burada")] * 6)

    found = mind.search_transcripts("anahtar", per_session=3)
    hits = found["20260101T000000Z"]
    assert len(hits) == 3                      # per-session cap
    assert len(hits[0]["text"]) < 200          # quote clipped
    assert "ANAHTAR" in hits[0]["text"]
    assert hits[0]["text"].startswith("…")     # clipping is visible


def test_search_only_scans_the_most_recent_sessions(tmp_path: Path, mind: Mind) -> None:
    """The bound is for cheapness: older ones have already been distilled into memories."""
    sessions = tmp_path / "sessions"
    for i in range(1, 6):
        _fake_session(sessions, f"2026010{i}T000000Z", [("user", "ANAHTAR")])

    assert len(mind.search_transcripts("anahtar", limit=2)) == 2


def _arac_ortami(tmp_path: Path):
    """Tool registry + context + mind — other test files use this too."""
    mind = open_mind(tmp_path / "mind", tmp_path / "sessions", "cur")
    config = Config.load(tmp_path)
    config.ensure_dirs()
    session = Session(EventLog(tmp_path / "s.jsonl"), "cur")
    context = ToolContext(config=config, session=session, cancel=asyncio.Event())
    return build_registry(mind), context, mind
