"""Orphaned helpers.

When the user closes the app at night, the helpers running in the
background die with the process: the main log has a subagent_start but no
subagent_end. If nothing is reported in the morning the user is left with
"I don't know what happened"; the panel could show a stale "running" too.
The tests here verify the boot scan (yetim_tara), the tombstone
(mark_orphan), adoption into the ledger + the harness note (adopt_orphans)
and the panel seed (snapshot channels).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dornick.events import EventLog
from dornick.loop import ChildHandle, mark_orphan, yetim_tara
from tests.test_loop import (  # noqa: F401
    FakeClient,
    build_agent,
    registry,
    text_turn,
    tool_turn,
)


def _main_log(sessions_dir: Path, name: str = "20250101T000000Z") -> EventLog:
    sessions_dir.mkdir(parents=True, exist_ok=True)
    log = EventLog(sessions_dir / f"{name}.jsonl")
    log.note("session_start", session_id=name)
    return log

def _child_log(sessions_dir: Path, sid: str, title: str, parent: str) -> None:
    log = EventLog(sessions_dir / f"{sid}.jsonl")
    log.note("subagent_start", title=title, parent=parent)
    log.close()


# -- scan ----------------------------------------------------------------


def test_a_start_without_an_end_is_an_orphan(tmp_path: Path) -> None:
    """The core scenario: the app closed at night, the trace found at the morning boot."""
    sessions = tmp_path / "sessions"
    main = _main_log(sessions)
    main.note("subagent_start", title="gece taraması", session="20250101T000100Z")
    main.close()
    _child_log(sessions, "20250101T000100Z", "gece taraması", "20250101T000000Z")

    orphans = yetim_tara(sessions)
    assert orphans == [{"title": "gece taraması", "session": "20250101T000100Z"}]


def test_a_finished_helper_is_not_an_orphan(tmp_path: Path) -> None:
    sessions = tmp_path / "sessions"
    main = _main_log(sessions)
    main.note("subagent_start", title="tarama", session="c1")
    main.note("subagent_end", title="tarama", session="c1", turns=3, tools=5)
    main.close()
    _child_log(sessions, "c1", "tarama", "ana")

    assert yetim_tara(sessions) == []


def test_an_old_style_end_matches_by_title(tmp_path: Path) -> None:
    """In old records subagent_end carried no session id; it must match by
    title — otherwise the whole archive gets declared 'orphan' overnight."""
    sessions = tmp_path / "sessions"
    main = _main_log(sessions)
    main.note("subagent_start", title="tarama", session="c1")
    main.note("subagent_end", title="tarama", turns=3, tools=5)   # no session
    main.close()
    _child_log(sessions, "c1", "tarama", "ana")

    assert yetim_tara(sessions) == []


def test_a_crashed_helper_is_not_an_orphan(tmp_path: Path) -> None:
    """subagent_failed is a closure too: the crash was already reported, it
    must not be announced as an orphan on top."""
    sessions = tmp_path / "sessions"
    main = _main_log(sessions)
    main.note("subagent_start", title="tarama", session="c1")
    main.note("subagent_failed", title="tarama", session="c1", error="patladı")
    main.close()
    _child_log(sessions, "c1", "tarama", "ana")

    assert yetim_tara(sessions) == []


def test_a_missing_child_file_is_not_reported(tmp_path: Path) -> None:
    """If the session file was never born there is no trace to resume;
    reporting it would be promising the user something we can't keep."""
    sessions = tmp_path / "sessions"
    main = _main_log(sessions)
    main.note("subagent_start", title="tarama", session="hic-dogmadi")
    main.close()

    assert yetim_tara(sessions) == []


def test_child_logs_are_not_scanned_as_main_sessions(tmp_path: Path) -> None:
    """A child session's own log must not be taken for a main session: the
    parent-bearing subagent_start inside gives it away."""
    sessions = tmp_path / "sessions"
    main = _main_log(sessions)
    main.note("subagent_start", title="tarama", session="zzz-cocuk")
    main.close()
    # The child log also has (from its own view) a start without an end;
    # taken for a main it would produce no candidate since its meta has no
    # session, but it is tested deliberately anyway: a single orphan, the
    # one found from the main log.
    _child_log(sessions, "zzz-cocuk", "tarama", "20250101T000000Z")

    orphans = yetim_tara(sessions)
    assert [y["session"] for y in orphans] == ["zzz-cocuk"]


def test_marking_prevents_a_second_report(tmp_path: Path) -> None:
    """A second boot must not report the same orphan again: the
    subagent_end(orphaned=True) dropped into the child log is the tombstone."""
    sessions = tmp_path / "sessions"
    main = _main_log(sessions)
    main.note("subagent_start", title="tarama", session="c1")
    main.close()
    _child_log(sessions, "c1", "tarama", "ana")

    orphans = yetim_tara(sessions)
    assert len(orphans) == 1

    mark_orphan(sessions, orphans)
    # The marker is in the child log and carries orphaned.
    text = (sessions / "c1.jsonl").read_text(encoding="utf-8")
    assert "subagent_end" in text and '"orphaned":true' in text.replace(" ", "")
    # Second scan: silence.
    assert yetim_tara(sessions) == []


def test_a_torn_last_line_does_not_break_the_scan(tmp_path: Path) -> None:
    """A hard shutdown can leave the last line half written; the scan and the
    marking must still work (EventLog won't open on a corrupt line, the
    manual append kicks in)."""
    sessions = tmp_path / "sessions"
    main = _main_log(sessions)
    main.note("subagent_start", title="tarama", session="c1")
    main.close()
    _child_log(sessions, "c1", "tarama", "ana")
    with (sessions / "c1.jsonl").open("a", encoding="utf-8") as fh:
        fh.write('{"seq": 99, "ts": "yarim')   # torn line, no newline

    orphans = yetim_tara(sessions)
    assert len(orphans) == 1

    mark_orphan(sessions, orphans)
    assert yetim_tara(sessions) == []


# -- adoption into the ledger + harness note ----------------------------


async def test_adopt_orphans_registers_and_briefs_the_model(
    tmp_path: Path, registry
) -> None:
    client = FakeClient(text_turn("gördüm, kullanıcıya haber veririm"))
    agent = build_agent(tmp_path, client, registry)

    adopted = agent.adopt_orphans(
        [{"title": "gece taraması", "session": "c1"}])

    assert len(adopted) == 1
    handle = adopted[0]
    assert handle.state == "yetim" and handle.session_id == "c1"
    assert handle.bildirildi, "no separate notice turn should open for an orphan"
    assert handle.id in agent._children

    # The harness note lands in front of the model at the start of the first turn.
    await agent.run("günaydın")
    first_request = str(client.seen_messages[0])
    assert "yarım kaldı" in first_request
    assert "gece taraması" in first_request
    assert "task_say" in first_request


async def test_task_say_resumes_an_adopted_orphan(tmp_path: Path, registry) -> None:
    """If the user says 'resume': task_say must be able to revive the orphan
    handle from the session on disk — the same path as a finished helper."""
    client = FakeClient(text_turn("kaldığım yerden devam ettim"))
    agent = build_agent(tmp_path, client, registry)
    sid = "20250101T000100Z"
    _child_log(agent.config.sessions_dir, sid, "gece taraması", "ana")

    (handle,) = agent.adopt_orphans([{"title": "gece taraması", "session": sid}])
    ok, msg = agent._child_say(handle.id, "kaldığın yerden sürdür")
    assert ok, msg
    await handle.task

    assert handle.state == "bitti"
    assert "devam ettim" in handle.sonuc
    text = (agent.config.sessions_dir / f"{sid}.jsonl").read_text(encoding="utf-8")
    assert "session_resume" in text


async def test_bridge_resume_task_resumes_orphan(tmp_path: Path, registry) -> None:
    """UI 'Continue' → Bridge.resume_task → _child_say (HTTP-thread safe)."""
    import asyncio

    from dornick.desktop import Bridge

    class _Hub:
        def emit(self, *_a, **_k):
            pass

    client = FakeClient(text_turn("panelden sürdürüldü"))
    agent = build_agent(tmp_path, client, registry)
    sid = "20250101T000200Z"
    _child_log(agent.config.sessions_dir, sid, "Market Lens", "ana")
    (handle,) = agent.adopt_orphans([{"title": "Market Lens", "session": sid}])

    bridge = Bridge(_Hub(), asyncio.get_running_loop())
    bridge.agent = agent

    # resume_task uses call_soon + wait — don't call it on the loop thread.
    result = await asyncio.to_thread(bridge.resume_task, "c:" + handle.id)
    assert result.get("ok"), result
    await handle.task
    assert handle.state == "bitti"
    assert "sürdürüldü" in handle.sonuc

    missing = await asyncio.to_thread(bridge.resume_task, "c:yokid")
    assert missing.get("ok") is False

    running = ChildHandle(id="run1", title="koşan", model="m",
                          session_id="x", state="kosuyor")
    agent._children["run1"] = running
    busy = await asyncio.to_thread(bridge.resume_task, "c:run1")
    assert busy.get("ok") is False
    assert "koşuyor" in (busy.get("error") or "").lower() or "zaten" in (
        busy.get("error") or "").lower()


def test_tasks_marks_orphans_as_resumable(tmp_path: Path, registry) -> None:
    """The live list puts the surdurulebilir flag on the orphan row."""
    import asyncio

    from dornick.desktop import Bridge

    class _Hub:
        def emit(self, *_a, **_k):
            pass

    async def scenario() -> dict:
        agent = build_agent(tmp_path, FakeClient(), registry)
        agent._children["y1"] = ChildHandle(
            id="y1", title="yarım", model="", arka_plan=True,
            state="yetim", session_id="sess1", sonuc="yarım kaldı")
        agent._children["r1"] = ChildHandle(
            id="r1", title="koşan", model="m", arka_plan=True,
            state="kosuyor", session_id="sess2")
        bridge = Bridge(_Hub(), asyncio.get_running_loop())
        bridge.agent = agent
        return bridge.tasks()

    payload = asyncio.run(scenario())
    by_id = {r["id"]: r for r in payload["gorevler"]}
    assert by_id["c:y1"]["surdurulebilir"] is True
    assert by_id["c:r1"]["surdurulebilir"] is False
    assert by_id["c:r1"]["durdurulabilir"] is True


# -- panel seed (snapshot channels) --------------------------------------


def test_snapshot_channels_mirror_the_ledger(tmp_path: Path, registry) -> None:
    """The panel is built from this list at boot: running 'run', finished
    'done', orphan 'yetim', failed 'fail' — a channel absent from the
    snapshot is not drawn."""
    from dornick.desktop import _live_channels

    agent = build_agent(tmp_path, FakeClient(), registry)
    agent._children["a1"] = ChildHandle(id="a1", title="koşan", model="m",
                                        arka_plan=True)
    agent._children["b2"] = ChildHandle(id="b2", title="biten", model="m",
                                        state="bitti", sonuc="üç dosya bulundu")
    agent._children["c3"] = ChildHandle(id="c3", title="yarım", model="",
                                        arka_plan=True, state="yetim",
                                        sonuc="Uygulama kapanınca yarım kaldı.")
    agent._children["d4"] = ChildHandle(id="d4", title="çöken", model="m",
                                        state="hata", sonuc="patladı")

    rows = {r["id"]: r for r in _live_channels(agent)}
    assert rows["a1"]["state"] == "run" and rows["a1"]["ozet"] == ""
    assert rows["b2"]["state"] == "done" and "üç dosya" in rows["b2"]["ozet"]
    assert rows["c3"]["state"] == "yetim" and rows["c3"]["bg"]
    assert rows["d4"]["state"] == "fail"

    # On an agent-less (model not configured) boot, silently empty.
    assert _live_channels(None) == []
    assert _live_channels(object()) == []


def test_the_bridge_snapshot_carries_the_channel_list(tmp_path: Path, registry) -> None:
    import asyncio

    from dornick.desktop import Bridge

    class _Hub:
        def __init__(self) -> None:
            self.events: list[dict] = []

        def emit(self, payload: dict) -> None:
            self.events.append(payload)

    async def scenario() -> dict:
        agent = build_agent(tmp_path, FakeClient(), registry)
        agent._children["y1"] = ChildHandle(id="y1", title="gece işi", model="",
                                            arka_plan=True, state="yetim")
        bridge = Bridge(_Hub(), asyncio.get_running_loop())
        bridge.agent = agent
        return bridge.snapshot()

    snap = asyncio.run(scenario())
    assert snap["channels"] == [{
        "id": "y1", "title": "gece işi", "model": "", "bg": True,
        "kind": "yardımcı", "state": "yetim", "ozet": "",
    }]


# -- UI contract ---------------------------------------------------------

STATIC = Path(__file__).resolve().parents[1] / "src" / "dornick" / "web" / "static"


def test_the_deck_seeds_from_the_snapshot() -> None:
    """app.js seeds the channels into the orchestra at boot; the orchestra
    rebuilds its map from scratch so no ghost 'running' card is left."""
    app_js = (STATIC / "app.js").read_text(encoding="utf-8")
    orch_js = (STATIC / "orchestra.js").read_text(encoding="utf-8")

    assert "orchSeed(s.channels || [])" in app_js
    # When an orphan is found at boot the server also sends the real list as
    # an event (the page may have pulled the snapshot before the agent was
    # ready), and when a dropped SSE comes back the open tab refreshes itself.
    assert 'case "channels": orchSeed(e.channels || [])' in app_js
    assert "resyncChannels" in app_js
    assert "channels.clear()" in orch_js          # ghosts are wiped
    assert '"Yarım kaldı"' in orch_js             # the orphan state is drawn
    assert '"Yarım kaldı": "Left unfinished"' in orch_js   # EN translation
    assert "/api/gorevler/devam" in orch_js
    assert "Devam et" in orch_js

    tasks_js = (STATIC / "gorevler.js").read_text(encoding="utf-8")
    assert "/api/gorevler/devam" in tasks_js
    assert "surdurulebilir" in tasks_js or 'durum === "yetim"' in tasks_js

    server = (Path(__file__).resolve().parents[1]
              / "src" / "dornick" / "web" / "server.py").read_text(encoding="utf-8")
    assert "/api/gorevler/devam" in server
    assert "resume_task" in (
        Path(__file__).resolve().parents[1] / "src" / "dornick" / "desktop.py"
    ).read_text(encoding="utf-8")

    css = (STATIC / "app.css").read_text(encoding="utf-8")
    # With tokens that work in both themes: the orphan state is tied to the visual language.
    assert ".orch-ch.yetim" in css and "--amber" in css
    assert ".task-resume" in css and ".orch-resume" in css
