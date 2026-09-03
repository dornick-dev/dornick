"""Subagents.

The tool's real job is splitting the context: the subagent's thirty tool
calls must stay in its own log, only the answer must return to the main
conversation. When this breaks, no error appears — the window just fills
twice as fast.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dornick.loop import MAX_DEPTH
from dornick.tools import build_registry
from tests.test_loop import (  # noqa: F401
    FakeClient,
    build_agent,
    registry,
    text_turn,
    tool_turn,
)


@pytest.fixture()
def full(tmp_path: Path):
    """The real tool registry: the `task` tool included."""
    return build_registry()


@pytest.fixture(autouse=True)
def _offline_catalog(monkeypatch):
    """The tests in this file must NOT touch the network.

    When given a model id, the `task` tool validates it against the
    provider's catalog, and the catalog comes via a real HTTP request. A
    test's result cannot depend on the machine's internet: here the
    catalog is EMPTY by default, i.e. the "server gives no list" state —
    validation is skipped and the model passes through as-is. Tests that
    exercise validation pin the catalog themselves.
    """
    from dornick import settings

    monkeypatch.setattr(settings, "scan_models", lambda _config: [])


# -- registration ------------------------------------------------------


def test_the_task_tool_exists_at_the_top_level(full) -> None:
    assert "task" in full


def test_a_subagent_gets_no_task_tool() -> None:
    """Never registering the tool is better than registering and refusing
    it: the model should not try an ability that does not exist."""
    assert "task" not in build_registry(subagents=False)


def test_subagents_can_run_side_by_side(full) -> None:
    """The real win is here: independent pieces run in parallel in the same turn."""
    assert full.get("task").parallel_safe


def test_the_tool_itself_changes_nothing(full) -> None:
    """Side effects come from the subagent's tools and those already pass
    the permission gate; counting the tool itself as a mutation would mean
    a second approval question for every subagent."""
    assert not full.get("task").mutates


# -- running -----------------------------------------------------------


async def test_the_answer_comes_back_but_the_steps_do_not(
    tmp_path: Path, full
) -> None:
    """The subagent's intermediate steps must not fill the main context."""
    client = FakeClient(
        # The main agent launches a subagent.
        tool_turn(("c1", "task", {"title": "ara", "task": "şu dizinde X'i bul"})),
        # The subagent: calls one tool, then answers.
        tool_turn(("c2", "list_dir", {"path": str(tmp_path)})),
        text_turn("X, ayarlar.py içinde geçiyor."),
        # The main agent relays the result.
        text_turn("Buldum: ayarlar.py"),
    )
    agent = build_agent(tmp_path, client, full)

    await agent.run("X nerede geçiyor")

    history = str(agent.session.messages())
    assert "X, ayarlar.py içinde geçiyor." in history   # the answer arrived
    assert "list_dir" not in history                     # the intermediate step did not


async def test_the_subagent_writes_to_its_own_session(tmp_path: Path, full) -> None:
    client = FakeClient(
        tool_turn(("c1", "task", {"task": "bir şey yap"})),
        text_turn("alt ajanın cevabı"),
        text_turn("tamam"),
    )
    agent = build_agent(tmp_path, client, full)
    before = agent.session.id

    await agent.run("başla")

    sessions = list(agent.config.sessions_dir.glob("*.jsonl"))
    assert len(sessions) == 1
    assert sessions[0].stem != before

    marks = agent.session.log.notes("subagent_end")
    assert len(marks) == 1


def test_the_child_registry_inherits_dynamic_tools(tmp_path: Path, full) -> None:
    """Skills and MCP tools were only added to the main registry after
    startup; a subagent could not see a device skill or a connected MCP
    server. Now tools with a non-empty `source` descend from the main
    registry to the subagent.
    """
    from dornick.tools.base import ToolSpec

    def handler(args, ctx):
        return None

    full.register(ToolSpec(name="modbus_oku", description="cihaz yeteneği",
                           input_schema={"type": "object"}, handler=handler,
                           source="yetenek"))
    full.register(ToolSpec(name="mcp__notion__notion-search", description="dış araç",
                           input_schema={"type": "object"}, handler=handler,
                           source="mcp:notion"))

    client = FakeClient(text_turn("bitti"))
    agent = build_agent(tmp_path, client, full)
    child = agent._child_registry()

    # The dynamics came down.
    assert "modbus_oku" in child
    assert "mcp__notion__notion-search" in child
    # The builtin distinction held: task is absent in the subagent.
    assert "task" not in child
    # The source label was carried too — so it can descend to the subagent's own subagent.
    assert child.get("modbus_oku").source == "yetenek"


async def test_a_subagent_cannot_spawn_another(tmp_path: Path, full) -> None:
    """Unbounded nesting opens a single request up like a tree."""
    client = FakeClient(
        tool_turn(("c1", "task", {"task": "birinci seviye"})),
        text_turn("bitti"),
        text_turn("tamam"),
    )
    agent = build_agent(tmp_path, client, full)
    await agent.run("başla")

    assert MAX_DEPTH == 1
    # No tool in the subagent's registry means the model cannot even try.
    assert "task" not in build_registry(subagents=False)


async def test_an_empty_answer_is_reported_as_an_error(tmp_path: Path, full) -> None:
    """A subagent silently returning empty led the main agent to say
    "all done" and move on."""
    client = FakeClient(
        tool_turn(("c1", "task", {"task": "bir şey yap"})),
        text_turn(""),        # the subagent finishes without saying anything
        text_turn("peki"),
    )
    agent = build_agent(tmp_path, client, full)
    await agent.run("başla")

    results = [
        block
        for message in agent.session.messages()
        for block in (message["content"] if isinstance(message["content"], list) else [])
        if isinstance(block, dict) and block.get("type") == "tool_result"
    ]
    assert results and results[0]["is_error"]


async def test_a_blank_instruction_is_refused(tmp_path: Path, full) -> None:
    client = FakeClient(
        tool_turn(("c1", "task", {"task": "   "})),
        text_turn("peki"),
    )
    agent = build_agent(tmp_path, client, full)
    await agent.run("başla")

    # No subagent should be started for an empty task.
    assert not agent.session.log.notes("subagent_start")


async def test_interrupting_the_parent_stops_the_child(tmp_path: Path, full) -> None:
    """When the user says stop, the subagent must not keep running in the back.

    The flag is no longer shared (a background child was left orphaned in
    the parent's `_arm`); the child has its OWN flag and the parent's
    `interrupt()` sets them all derivatively. The contract is the same:
    stop = everything stops.
    """
    client = FakeClient(
        tool_turn(("c1", "task", {"task": "uzun iş"})),
        text_turn("alt ajan cevabı"),
        text_turn("tamam"),
    )
    agent = build_agent(tmp_path, client, full)
    captured: list = []

    original = agent._spawn

    async def watched(title: str, instruction: str, model: str = "") -> str:
        import dornick.loop as loop_module

        made: list = []
        real_agent = loop_module.Agent

        class Recording(real_agent):  # type: ignore[misc, valid-type]
            def __init__(self, **kwargs):
                super().__init__(**kwargs)
                made.append(self)

        loop_module.Agent = Recording
        try:
            return await original(title, instruction, model)
        finally:
            loop_module.Agent = real_agent
            captured.extend(made)

    agent._spawn = watched
    await agent.run("başla")

    assert captured, "the subagent was never built"
    # The child's flag is the handle's flag in the ledger; the parent's interrupt() sets it.
    handle = next(iter(agent._children.values()))
    assert captured[0].cancel is handle.cancel
    assert not captured[0].cancel.is_set()
    agent.interrupt()
    assert agent.cancel.is_set()
    # A finished child's flag is untouched; verify it is set for a running
    # child with a separate fake handle.
    from dornick.loop import ChildHandle

    running = ChildHandle(id="abc123", title="koşan", model="m")
    agent._children[running.id] = running
    agent.interrupt()
    assert running.cancel.is_set()


# -- background helpers -------------------------------------------------


class SlowClient(FakeClient):
    """A fake client that delays every turn a little: so the child finishes
    after the main agent. Timing is not the test's essence, it pins the ordering."""

    def __init__(self, *script, delay: float = 0.05) -> None:
        super().__init__(*script)
        self.delay = delay

    async def turn(self, prepared, tools, *, cancel, callbacks=None):
        import asyncio

        await asyncio.sleep(self.delay)
        return await super().turn(prepared, tools, cancel=cancel, callbacks=callbacks)


async def test_a_background_helper_returns_immediately_and_reports_later(
    tmp_path: Path, full
) -> None:
    """background=true: the tool result returns IMMEDIATELY, the job runs
    in the back and once done its result is dropped as a note at the start
    of the next turn."""
    parent = FakeClient(
        tool_turn(("c1", "task", {"title": "sayım", "task": "dosyaları say",
                                  "arka_plan": True, "model": "kucuk"})),
        text_turn("başlattım, beklemeden devam ediyorum"),
        text_turn("sonucu gördüm"),
    )
    child_client = SlowClient(text_turn("42 dosya var"))
    agent = build_agent(tmp_path, parent, full)
    agent._client_for = lambda name: (child_client, agent.config)

    await agent.run("dosyaları arka planda say")

    # The tool result returned without waiting; a running record is in the ledger.
    history = str(agent.session.messages())
    assert "yardımcı başlatıldı" in history
    handle = next(iter(agent._children.values()))
    assert handle.background and handle.task is not None

    # Wait until the child finishes: the result is in the ledger, not yet reported.
    await handle.task
    assert handle.state == "bitti"
    assert "42 dosya var" in handle.outcome
    assert agent.has_unreported_children()

    # At the start of the next turn the result is dropped as a note.
    await agent.run("nasıl gitti?")
    notes = str(agent.session.messages())
    assert "[Yardımcı bitti" in notes
    assert "42 dosya var" in notes
    assert not agent.has_unreported_children()


async def test_resume_for_children_opens_a_continuation_turn(
    tmp_path: Path, full
) -> None:
    """A helper finishing while the main agent is idle: the resume turn
    opens with a continuation note (not a user message) and evaluates the result."""
    from dornick.loop import ChildHandle

    client = FakeClient(text_turn("başlat"), text_turn("sonucu aktardım"))
    agent = build_agent(tmp_path, client, full)
    await agent.run("merhaba de")   # so there is at least one turn in the history

    handle = ChildHandle(id="ab12cd", title="şiir", model="m",
                         background=True, state="bitti", outcome="beş kelimelik şiir hazır")
    agent._children[handle.id] = handle

    stats = await agent.resume_for_children()
    assert stats is not None and stats.turns == 1

    # The input is NOT a user message: it is marked continuation.
    nudges = [e for e in agent.session.log.messages() if e.meta.get("continuation")]
    assert nudges and "yardımcı(lar) bitti" in str(nudges[-1].content)
    # The result is in the history as a harness note.
    assert "beş kelimelik şiir hazır" in str(agent.session.messages())

    # If nothing is left to report, the model is never called.
    assert await agent.resume_for_children() is None


async def test_interrupt_stops_a_background_helper(tmp_path: Path, full) -> None:
    """Stop = everything stops: the helper running in the background too."""
    import asyncio

    class WaitsForCancel(FakeClient):
        async def turn(self, prepared, tools, *, cancel, callbacks=None):
            await cancel.wait()
            from dornick.backends import TurnResult

            return TurnResult(interrupted=True)

    parent = FakeClient(text_turn("tamam"))
    agent = build_agent(tmp_path, parent, full)
    agent._client_for = lambda name: (WaitsForCancel(), agent.config)

    handle = agent._spawn_bg("uzun iş", "hiç bitmeyecek bir şey yap", "kucuk")
    await asyncio.sleep(0.05)   # let the child take the gate and start running
    assert handle.state == "kosuyor"

    agent.interrupt()
    await handle.task

    assert handle.state == "hata"
    assert handle.notified, "no report turn should open for a cancelled helper"


# -- the mid-turn inbox --------------------------------------------------


async def test_a_mid_turn_note_lands_in_the_same_turn(tmp_path: Path) -> None:
    """A note dropped while the running turn is underway enters the SAME
    run's next request as a harness note."""
    from dornick.tools import ToolRegistry, ToolResult, object_schema

    reg = ToolRegistry()
    holder: dict = {}

    @reg.tool("poke", "dürt", object_schema({}))
    async def _poke(args, ctx):
        holder["agent"].take_note("[Kullanıcı bu arada yazdı] rengi mavi yap")
        return ToolResult("dürtüldü")

    client = FakeClient(tool_turn(("t1", "poke", {})), text_turn("tamam, mavi"))
    agent = build_agent(tmp_path, client, reg)
    holder["agent"] = agent

    stats = await agent.run("bir şey çiz")

    assert stats.turns == 2
    second_request = str(client.seen_messages[-1])
    assert "rengi mavi yap" in second_request
    assert not agent._inbox, "the box must be emptied"


async def test_a_note_after_the_final_answer_gets_one_more_step(
    tmp_path: Path
) -> None:
    """If the user interjected while the model gave its final answer, the
    message is not lost: one more step is granted within the same turn."""
    from dornick.tools import ToolRegistry

    class InterjectedClient(FakeClient):
        """Drops a note in the MIDDLE of the first turn (while the model produces its answer)."""

        def __init__(self, agent_box: dict, *script) -> None:
            super().__init__(*script)
            self.box = agent_box
            self.first = True

        async def turn(self, prepared, tools, *, cancel, callbacks=None):
            result = await super().turn(prepared, tools, cancel=cancel, callbacks=callbacks)
            if self.first:
                self.first = False
                self.box["agent"].take_note("[Kullanıcı bu arada yazdı] bir şey daha var")
            return result

    box: dict = {}
    client = InterjectedClient(box, text_turn("ilk cevap"), text_turn("notu da gördüm"))
    agent = build_agent(tmp_path, client, ToolRegistry())
    box["agent"] = agent

    stats = await agent.run("bir şey anlat")

    assert stats.turns == 2, "one more step should have been granted for the note"
    assert "bir şey daha var" in str(client.seen_messages[-1])


def test_the_inbox_note_is_invisible_in_the_chat(tmp_path: Path) -> None:
    """A harness note must not look like a message in the UI (the bubble
    was already drawn by the `araya` event); when the system channel is
    not suitable it enters through the user channel but still marked
    `internal`."""
    from dornick.events import EventLog
    from dornick.session import Session
    from dornick.web.server import _payload

    session = Session(EventLog(tmp_path / "n.jsonl"), "test")
    session.add_user_text("merhaba")
    session.add_harness_note("[Kullanıcı bu arada yazdı] birinci")   # the system channel
    session.add_harness_note("[Kullanıcı bu arada yazdı] ikinci")    # falls to the user channel
    events = session.log.messages()
    assert [e.role for e in events] == ["user", "system", "user"]
    assert _payload(events[1]) is None
    assert _payload(events[2]) is None
    # Both go to the model.
    sent = str(session.messages())
    assert "birinci" in sent and "ikinci" in sent


# -- task_say / task_status ----------------------------------------------


async def test_task_say_reaches_a_running_child(tmp_path: Path, full) -> None:
    from dornick.loop import ChildHandle

    client = FakeClient(
        tool_turn(("c1", "task_say", {"id": "abc123", "message": "kapsamı daralt"})),
        text_turn("ilettim"),
    )
    agent = build_agent(tmp_path, client, full)

    notes: list[str] = []

    class StubAgent:
        def take_note(self, note, **kw):
            notes.append(note)

    handle = ChildHandle(id="abc123", title="tarama", model="m")
    handle.agent = StubAgent()
    agent._children[handle.id] = handle

    await agent.run("yardımcıya kapsamı daraltmasını söyle")

    assert notes and "kapsamı daralt" in notes[0]
    assert "[Ana ajandan ara mesaj]" in notes[0]


async def test_task_say_resumes_a_finished_child(tmp_path: Path, full) -> None:
    """A finished helper: its session is opened from disk with
    `Session.resume` and continued in the background over the same handle."""
    client = FakeClient(
        tool_turn(("c1", "task", {"title": "iş", "task": "bir şey yap"})),
        text_turn("çocuğun ilk cevabı"),
        text_turn("tamam"),
        text_turn("çocuğun devam cevabı"),   # the resumed run's turn
    )
    agent = build_agent(tmp_path, client, full)
    await agent.run("başla")

    handle = next(iter(agent._children.values()))
    assert handle.state == "bitti" and handle.session_id
    before = handle.session_id

    ok, msg = agent._child_say(handle.id, "şimdi bir de özet çıkar")
    assert ok, msg
    await handle.task

    assert handle.state == "bitti"
    assert handle.session_id == before, "the same session must continue, not a new one"
    assert "devam cevabı" in handle.outcome
    assert agent.has_unreported_children()

    # There is still ONE child session on disk and the resume trace sits inside it.
    files = list(agent.config.sessions_dir.glob("*.jsonl"))
    assert len(files) == 1
    text = files[0].read_text(encoding="utf-8")
    assert "session_resume" in text
    assert "özet çıkar" in text


async def test_task_status_reports_the_ledger(tmp_path: Path, full) -> None:
    from dornick.loop import ChildHandle

    client = FakeClient(
        tool_turn(("c1", "task_status", {})),
        text_turn("durumu aktardım"),
    )
    agent = build_agent(tmp_path, client, full)
    agent._children["aa11"] = ChildHandle(id="aa11", title="koşan", model="m",
                                          background=True)
    agent._children["bb22"] = ChildHandle(id="bb22", title="biten", model="m",
                                          state="bitti", outcome="üç dosya bulundu")

    await agent.run("yardımcılar ne durumda")

    history = str(agent.session.messages())
    assert "id=aa11" in history and "kosuyor" in history
    assert "id=bb22" in history and "üç dosya bulundu" in history


def test_the_ledger_keeps_at_most_eight_finished_children(tmp_path: Path, full) -> None:
    from dornick.loop import MAX_CHILDREN, ChildHandle

    client = FakeClient(text_turn("tamam"))
    agent = build_agent(tmp_path, client, full)
    for i in range(12):
        agent._register_child(ChildHandle(
            id=f"h{i:02d}", title=f"iş {i}", model="m",
            state="bitti", ended_ts=float(i), notified=True))

    assert len(agent._children) == MAX_CHILDREN
    # The oldest dropped, the newest remain.
    assert "h00" not in agent._children and "h11" in agent._children


# -- the bridge: interjection and the resume turn -------------------------


class _Hub:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def emit(self, payload: dict) -> None:
        self.events.append(payload)


async def test_submitting_while_busy_interjects_into_the_running_turn(
    tmp_path: Path
) -> None:
    """Plain text arriving while busy enters the running turn's inbox, not
    the queue; the UI gets an `araya` event (not queued)."""
    import asyncio

    from dornick.desktop import Bridge

    hub = _Hub()
    bridge = Bridge(hub, asyncio.get_running_loop())
    bridge._busy = True

    notes: list[tuple[str, str]] = []

    class StubAgent:
        def take_note(self, note, *, encode=""):
            notes.append((note, encode))

        def inbox_full(self):
            return False

    bridge.agent = StubAgent()
    bridge.submit("rengi mavi yap")
    await asyncio.sleep(0)   # let call_soon_threadsafe run

    assert notes and "rengi mavi yap" in notes[0][0]
    assert "[Kullanıcı bu arada yazdı]" in notes[0][0]
    assert notes[0][1] == "rengi mavi yap"          # goes to instant memory too
    kinds = [e["type"] for e in hub.events]
    assert "araya" in kinds and "queued" not in kinds
    assert bridge.queue.empty(), "an interjected message must not also land in the queue"


async def test_scheduled_and_gate_messages_still_queue(tmp_path: Path) -> None:
    """`queue=True` (scheduled task, external gate): the old queue behaviour."""
    import asyncio

    from dornick.desktop import Bridge

    hub = _Hub()
    bridge = Bridge(hub, asyncio.get_running_loop())
    bridge._busy = True
    bridge.agent = object()   # no take_note: the inbox path is closed anyway

    bridge.submit("zamanlanmış iş", queue=True)
    await asyncio.sleep(0.05)   # let run_coroutine_threadsafe write to the queue

    assert [e["type"] for e in hub.events] == ["queued"]
    assert bridge.queue.qsize() == 1


async def test_child_done_opens_a_resume_turn_when_idle(tmp_path: Path) -> None:
    """The helper-finished signal lands in the queue; when its turn comes
    (agent idle) the resume turn runs and turn_end is emitted."""
    import asyncio

    from dornick.desktop import _CHILD_DONE, Bridge

    hub = _Hub()
    bridge = Bridge(hub, asyncio.get_running_loop())

    resumed = []

    class StubAgent:
        def has_unreported_children(self):
            return True

        async def resume_for_children(self):
            resumed.append(True)

    bridge.agent = StubAgent()
    bridge.child_done()
    assert bridge.queue.get_nowait() is _CHILD_DONE

    await bridge._resume()

    assert resumed == [True]
    kinds = [e["type"] for e in hub.events]
    assert kinds[-1] == "turn_end"
    assert {"type": "status", "busy": True} in hub.events


async def test_a_resume_with_nothing_to_report_is_silent(tmp_path: Path) -> None:
    import asyncio

    from dornick.desktop import Bridge

    hub = _Hub()
    bridge = Bridge(hub, asyncio.get_running_loop())

    class StubAgent:
        def has_unreported_children(self):
            return False

        async def resume_for_children(self):
            raise AssertionError("the model should not have been called")

    bridge.agent = StubAgent()
    await bridge._resume()
    assert hub.events == []


async def test_an_approval_from_a_helper_carries_its_channel(tmp_path: Path) -> None:
    """The approval dialog should know who asked: the helper's id and
    title are in the approval_request event."""
    import asyncio

    from dornick.desktop import Bridge
    from dornick.tools.base import ToolSpec

    hub = _Hub()
    bridge = Bridge(hub, asyncio.get_running_loop())

    async def handler(args, ctx):  # pragma: no cover - signature only
        return None

    spec = ToolSpec(name="shell", description="d", input_schema={}, handler=handler)
    task = asyncio.ensure_future(
        bridge._approve(spec, {"command": "ls"}, {"id": "ab12", "title": "tarama"}))
    await asyncio.sleep(0)

    ask = next(e for e in hub.events if e["type"] == "approval_request")
    assert ask["channel"] == {"id": "ab12", "title": "tarama"}

    bridge.resolve_approval(ask["id"], True)
    await asyncio.sleep(0)
    assert await task is True

    # The main agent's own request has no channel field at all.
    task = asyncio.ensure_future(bridge._approve(spec, {"command": "ls"}))
    await asyncio.sleep(0)
    ask = [e for e in hub.events if e["type"] == "approval_request"][-1]
    assert "channel" not in ask
    bridge.resolve_approval(ask["id"], False)
    await asyncio.sleep(0)
    assert await task is False


# -- the chat list -------------------------------------------------------


async def test_child_sessions_stay_out_of_the_chat_list(tmp_path: Path, full) -> None:
    """Helper sessions do not enter the /api/sessions list (mind.sessions);
    their logs stay on disk and the archive scan still finds them."""
    from dornick.mind import open_mind

    client = FakeClient(
        tool_turn(("c1", "task", {"task": "bir şey yap"})),
        text_turn("çocuk cevabı"),
        text_turn("tamam"),
    )
    agent = build_agent(tmp_path, client, full)
    await agent.run("başla")

    files = list(agent.config.sessions_dir.glob("*.jsonl"))
    assert files, "the child session should have been written to disk"

    mind = open_mind(tmp_path / "mind2", agent.config.sessions_dir, "test")
    listed = [e.session_id for e in mind.sessions()]
    assert files[0].stem not in listed
    # Not deleted: looking directly it is still there and marked as a child.
    episode = mind.episode(files[0].stem)
    assert episode is not None and episode.child
    mind.store.close()


async def test_a_subagent_can_use_another_model(tmp_path: Path, full) -> None:
    """A scan job should be able to go to a small fast model, a job
    needing images to an image-reading one."""
    client = FakeClient(
        tool_turn(("c1", "task", {"task": "şunu tara", "model": "kucuk-model"})),
        text_turn("tarama bitti"),
        text_turn("tamam"),
    )
    agent = build_agent(tmp_path, client, full)

    made: list[str] = []
    agent._client_for = lambda name: (made.append(name), (client, agent.config))[1]

    await agent.run("başla")
    assert made == ["kucuk-model"]


# -- model validation --------------------------------------------------
#
# Seen in the field: the model gave the helper a MADE-UP id
# (`qwen3.1-14b`), the provider returned 400 and the helper burned for the
# whole turn. The error blows up in the subagent's log; the main agent
# only sees "it errored" and does not know why. The id must be checked
# against the catalog BEFORE the spawn.


@pytest.fixture()
def task_ctx(tmp_path: Path):
    """Context + call helper for invoking the tool directly."""
    import asyncio

    from dornick.config import Config
    from dornick.events import EventLog
    from dornick.session import Session
    from dornick.tools.base import ToolContext

    config = Config.load(tmp_path)
    config.ensure_dirs()

    spawned: list[str] = []

    async def spawn(title: str, task: str, model: str) -> str:
        spawned.append(model)
        return "yardımcı sonucu"

    ctx = ToolContext(
        config=config,
        session=Session(EventLog(tmp_path / "s.jsonl"), "test"),
        cancel=asyncio.Event(),
        spawn=spawn,
    )
    return build_registry().get("task"), ctx, spawned


def _catalog(monkeypatch, ids: list[str]) -> None:
    """Pins the provider's model catalog; an empty list = no network."""
    from dornick import settings

    monkeypatch.setattr(settings, "scan_models", lambda _config: [{"id": i} for i in ids])


async def test_a_made_up_model_falls_back_to_the_main_one(task_ctx, monkeypatch) -> None:
    """The job must not die: the helper starts with the main model. But
    not silently — the tool's answer says what happened and where to look."""
    tool, ctx, spawned = task_ctx
    _catalog(monkeypatch, ["qwen3-14b", "llama-3.1-8b"])

    result = await tool.handler({"task": "iş", "model": "qwen3.1-14b"}, ctx)

    assert spawned == [""]                       # started with the main model
    assert "yardımcı sonucu" in result.content    # the job was done
    assert "`qwen3.1-14b` geçerli bir model kimliği değil" in result.content
    assert "`models`" in result.content           # it says where to look
    # Close candidates are suggested: the answer to "which id is right" is at hand.
    assert "qwen3-14b" in result.content


async def test_a_real_model_passes_through_untouched(task_ctx, monkeypatch) -> None:
    tool, ctx, spawned = task_ctx
    _catalog(monkeypatch, ["qwen3-14b", "llama-3.1-8b"])

    result = await tool.handler({"task": "iş", "model": "qwen3-14b"}, ctx)

    assert spawned == ["qwen3-14b"]
    assert "geçerli bir model kimliği değil" not in result.content


async def test_validation_is_skipped_when_the_catalogue_is_unreachable(
    task_ctx, monkeypatch
) -> None:
    """Making the tool unusable on an offline machine is worse than a
    made-up id: without a catalog, validation is skipped and the model
    passes through as-is."""
    tool, ctx, spawned = task_ctx
    _catalog(monkeypatch, [])

    await tool.handler({"task": "iş", "model": "her-neyse"}, ctx)
    assert spawned == ["her-neyse"]


async def test_a_catalogue_lookup_that_explodes_does_not_kill_the_task(
    task_ctx, monkeypatch
) -> None:
    """Validation is a convenience; if it blows up the job itself must not stop."""
    from dornick import settings

    tool, ctx, spawned = task_ctx

    def boom(_config):
        raise RuntimeError("katalog yandı")

    monkeypatch.setattr(settings, "scan_models", boom)

    await tool.handler({"task": "iş", "model": "her-neyse"}, ctx)
    assert spawned == ["her-neyse"]


async def test_only_the_letter_case_is_corrected_silently(task_ctx, monkeypatch) -> None:
    """`Qwen3-14B` is not an invention, it is a spelling drift: it is
    corrected to the catalog's form and things continue — imposing the
    main model would be needless."""
    tool, ctx, spawned = task_ctx
    _catalog(monkeypatch, ["qwen3-14b"])

    result = await tool.handler({"task": "iş", "model": "Qwen3-14B"}, ctx)

    assert spawned == ["qwen3-14b"]
    assert "geçerli bir model kimliği değil" not in result.content


async def test_no_model_asked_means_no_catalogue_lookup(task_ctx, monkeypatch) -> None:
    """With the field empty the main model is used; going to the network
    for the catalog is pointless — adding a request to every `task` call is costly."""
    from dornick import settings

    tool, ctx, spawned = task_ctx
    monkeypatch.setattr(
        settings, "scan_models",
        lambda _c: pytest.fail("the catalog must not be consulted with an empty model field"),
    )

    await tool.handler({"task": "iş"}, ctx)
    assert spawned == [""]


def test_the_tool_tells_the_model_not_to_invent_ids(full) -> None:
    """Validation is the last defence; the first is the tool's own description."""
    schema = full.get("task").input_schema
    note = schema["properties"]["model"]["description"]
    assert "UYDURMA" in note
    assert "boş bırak" in note and "`models`" in note


async def test_the_same_model_reuses_the_parent_client(tmp_path: Path, full) -> None:
    """A second client means a second connection pool."""
    client = FakeClient(
        tool_turn(("c1", "task", {"task": "iş", "model": "test-model"})),
        text_turn("bitti"),
        text_turn("tamam"),
    )
    agent = build_agent(tmp_path, client, full)
    agent.config.model.name = "test-model"

    asked: list[str] = []
    agent._client_for = lambda name: (asked.append(name), (client, agent.config))[1]

    await agent.run("başla")
    assert asked == []
