"""Jobs that run for hours: turn budget, mid-run compaction, background
jobs and model-outage resilience.

Until now four things killed a long agentic job: the hard 60-turn ceiling,
the 180 s tool timeout, compaction that could not find a cut point within a
single run, and the loop ending on a single model error. The tests here
prove that all four are closed.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

import dornick.loop as loop_module
from dornick.backends import TurnResult
from dornick.loop import Agent, clear_park, read_park, write_park
from dornick.session import PendingToolUse
from dornick.tools import ToolRegistry, ToolResult, object_schema
from tests.test_loop import (  # noqa: F401
    FakeClient,
    build_agent,
    message,
    registry,
    text_turn,
    tool_turn,
)


# -- turn budget: hard ceiling → checkpoint ------------------------------


async def test_a_long_run_survives_past_sixty_turns(
    tmp_path: Path, registry: ToolRegistry
) -> None:
    """The old code died at turn 60 with `turn_limit`; now a progress note is
    requested at the checkpoint and the work goes on."""
    script = [tool_turn((f"t{i}", "echo", {"text": str(i)})) for i in range(80)]
    script.append(text_turn("80 adımlık iş bitti"))
    client = FakeClient(*script)
    agent = build_agent(tmp_path, client, registry)

    stats = await agent.run("uzun bir iş yap")

    assert stats.turns == 81, "the run should not have been cut at 60 turns"
    assert stats.stop_reason == "end_turn"
    assert not agent.session.log.notes("turn_limit"), "should not have hit the fuse"
    marks = agent.session.log.notes("turn_checkpoint")
    assert marks and marks[0].meta["turns"] == 60
    # The checkpoint nudge really went to the model.
    assert "kontrol noktası" in str(client.seen_messages[-1])


async def test_the_hard_limit_still_guards(
    tmp_path: Path, registry: ToolRegistry, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The absolute fuse stays: a runaway loop cannot run forever."""
    monkeypatch.setattr(loop_module, "HARD_TURN_LIMIT", 5)
    client = FakeClient(*[tool_turn((f"t{i}", "echo", {})) for i in range(10)])
    agent = build_agent(tmp_path, client, registry)

    stats = await agent.run("dur durak bilme")

    assert stats.turns == 5
    marks = agent.session.log.notes("turn_limit")
    assert marks and marks[0].meta["limit"] == 5


async def test_tool_progress_refreshes_the_continuation_budget(
    tmp_path: Path, registry: ToolRegistry
) -> None:
    """Occasionally hitting the max_tokens ceiling in a long run must not
    drag the job into the closing turn: a turn that calls a tool refreshes
    the counter."""

    def truncated(text: str) -> TurnResult:
        return TurnResult(message=message([{"type": "text", "text": text}], "max_tokens"))

    client = FakeClient(
        truncated("uzun..."), truncated("devam..."),
        tool_turn(("t1", "echo", {"text": "a"})),
        truncated("yine uzun..."), truncated("devam..."),
        tool_turn(("t2", "echo", {"text": "b"})),
        truncated("son kez..."),
        text_turn("bitti"),
    )
    agent = build_agent(tmp_path, client, registry)

    stats = await agent.run("upuzun bir iş")

    assert stats.closing is False, "should not have been dragged into the closing turn"
    assert stats.stop_reason == "end_turn"


# -- mid-run compaction -------------------------------------------------


def test_work_cut_finds_an_assistant_boundary() -> None:
    """In a single run the only real user turn is at the start: cut_point
    returns 0, work_cut finds a safe cut at an assistant boundary."""
    from dornick.compaction import cut_point, work_cut

    def a() -> dict:
        return {"role": "assistant", "content": [{"type": "tool_use", "id": "x",
                                                  "name": "echo", "input": {}}]}

    def tr() -> dict:
        return {"role": "user", "content": [{"type": "tool_result",
                                             "tool_use_id": "x", "content": "ok"}]}

    msgs = [{"role": "user", "content": [{"type": "text", "text": "başla"}]},
            a(), tr(), a(), tr(), a(), tr(), a(), tr()]
    assert cut_point(msgs) == 0, "no real user turn; the old path cannot cut"
    cut = work_cut(msgs)
    assert cut == 3
    assert msgs[cut]["role"] == "assistant", "the cut must be at an assistant boundary"
    # The window after the cut does not start with an unanswered tool_result.
    first = msgs[cut]["content"][0]
    assert first.get("type") != "tool_result"


async def test_mid_run_compaction_keeps_the_run_alive(
    tmp_path: Path, registry: ToolRegistry
) -> None:
    """When the window fills in the middle of a single run: compact, pin the
    job status to the head of the summary, let the run carry on where it
    left off."""
    client = FakeClient(
        tool_turn(("t1", "echo", {"text": "a"})),
        tool_turn(("t2", "echo", {"text": "b"})),
        # At the START of turn 3 the window is full and there is now a cut
        # point: compaction triggers and the summariser consumes this text.
        text_turn("ÖZET: beş modüllü proje kuruluyordu; iki modül tamam."),
        tool_turn(("t3", "echo", {"text": "c"})),
        # Because the fake window always looks full, one more compaction happens.
        text_turn("ÖZET 2: üçüncü modül de bitti."),
        text_turn("iş tamamlandı"),
    )
    agent = build_agent(tmp_path, client, registry)
    # Let every turn look like "window full": FakeClient reports 10 tokens.
    agent.config.model.context_window = 10

    class GoalMind:
        last_trace: list = []

        def goal_digest(self) -> str:
            return "Açık hedefler: küçük projeyi bitir"

        def soul(self, persona: str = ""):
            return None

        def remember(self, *a, **k) -> None:
            return None

        def recall(self, *a, **k) -> list:
            return []

    agent.mind = GoalMind()

    # Let the model's own progress narrative sit in the region to be folded.
    agent.session.add_user_text("projeye başla")
    agent.session.add_assistant(
        [{"type": "text", "text": "Plan hazır: beş modül kuracağım, ikisi bitti."}])

    stats = await agent.run("kaldığın yerden devam et")

    # Compaction happened in the MIDDLE of the run and the run completed.
    resets = agent.session.log.notes("context_reset")
    assert resets, "compaction never triggered"
    assert agent.session.log.notes("compacted")
    assert stats.stop_reason == "end_turn"
    assert "iş tamamlandı" in str(agent.session.messages())

    # Job status at the head of the summary: goals + last progress + summary body.
    carried = str(resets[0].meta.get("summary"))
    assert "[İŞ DURUMU]" in carried
    assert "küçük projeyi bitir" in carried
    assert "beş modül kuracağım" in carried
    assert "ÖZET:" in carried

    # The tool call continued AFTER compaction (the t3 answer is in the history).
    assert "echo: c" in str(agent.session.log.messages())

    # The goal digest was reset: the live goals were re-injected after
    # compaction (old note + fresh note — the second is the proof of the reset).
    fresh = [e for e in agent.session.log.messages()
             if e.role == "system" and "küçük projeyi bitir" in str(e.content)]
    assert len(fresh) >= 2, "goals did not come back into the context after compaction"


# -- background jobs (long processes) ------------------------------------


async def test_a_background_job_reports_when_done(
    tmp_path: Path, registry: ToolRegistry
) -> None:
    """The long job runs in the ledger; when finished its output lands with
    a harness note at the start of the next turn — the same path as the
    helper notification."""
    client = FakeClient(text_turn("başlattım"), text_turn("çıktıyı gördüm"))
    agent = build_agent(tmp_path, client, registry)

    async def runner(cancel: asyncio.Event) -> str:
        await asyncio.sleep(0.01)
        return "derleme tamam: 0 hata"

    handle = agent._job_bg("derleme", runner)
    assert handle.state == "kosuyor" and handle.kind == "iş"
    await handle.task
    assert handle.state == "bitti"
    assert agent.has_unreported_children()

    await agent.run("nasıl gitti?")
    history = str(agent.session.messages())
    assert "[Arka plan işi bitti" in history
    assert "derleme tamam: 0 hata" in history


async def test_a_failed_background_job_is_not_reported_as_done(
    tmp_path: Path, registry: ToolRegistry
) -> None:
    """A job that ends with exit code 1 must not say 'task completed'."""
    from dornick.tools.base import JobFailed
    from dornick.tools.shell import job_report

    client = FakeClient(text_turn("gördüm"))
    agent = build_agent(tmp_path, client, registry)
    oks: list[bool] = []
    agent.io.on_child_end = (
        lambda title, ok, turns, tools, cid, summary: oks.append(ok)
    )

    async def runner(cancel: asyncio.Event) -> str:
        raise JobFailed(job_report(
            command="py tarama_modbus.py",
            code=1,
            text="ModuleNotFoundError: No module named 'pymodbus'",
        ))

    handle = agent._job_bg("$ py tarama_modbus.py", runner)
    await handle.task
    assert handle.state == "hata"
    assert oks == [False]
    assert "pymodbus" in (handle.outcome or "")
    assert "Traceback" not in (handle.outcome or "")


async def test_shell_background_returns_immediately(tmp_path: Path) -> None:
    from dornick.config import Config
    from dornick.events import EventLog
    from dornick.session import Session
    from dornick.tools import ToolContext
    from dornick.tools import shell as shell_tool

    reg = ToolRegistry()
    shell_tool.register(reg)

    config = Config.load(tmp_path)
    config.ensure_dirs()
    session = Session(EventLog(tmp_path / "s.jsonl"), "test")

    started: dict = {}

    def job_bg(title, runner):
        started["title"] = title
        started["runner"] = runner
        return SimpleNamespace(id="j1", title=title)

    ctx = ToolContext(config=config, session=session,
                      cancel=asyncio.Event(), job_bg=job_bg)

    result = await reg.get("shell").handler(
        {"command": "echo merhaba-dunya", "arka_plan": True}, ctx)

    assert not result.is_error
    assert "id=j1" in result.content, "the tool must return without waiting"
    # The runner really runs the command and returns the output.
    out = await started["runner"](asyncio.Event())
    assert "merhaba-dunya" in out


async def test_shell_background_failure_raises_a_readable_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If the background shell ends with 1: JobFailed — the package name, not a traceback."""
    from dornick.config import Config
    from dornick.events import EventLog
    from dornick.session import Session
    from dornick.tools import ToolContext
    from dornick.tools import shell as shell_tool
    from dornick.tools.base import JobFailed

    async def fake_run(command, cwd, session_id, timeout, cancel):
        return ("ok", "ModuleNotFoundError: No module named 'pymodbus'", 1)

    monkeypatch.setattr(shell_tool, "_run_shell", fake_run)

    reg = ToolRegistry()
    shell_tool.register(reg)
    config = Config.load(tmp_path)
    config.ensure_dirs()
    session = Session(EventLog(tmp_path / "s.jsonl"), "test")
    started: dict = {}

    def job_bg(title, runner):
        started["runner"] = runner
        return SimpleNamespace(id="j1", title=title)

    ctx = ToolContext(config=config, session=session,
                      cancel=asyncio.Event(), job_bg=job_bg)
    await reg.get("shell").handler(
        {"command": "py tarama_modbus.py", "arka_plan": True}, ctx)
    with pytest.raises(JobFailed) as caught:
        await started["runner"](asyncio.Event())
    msg = str(caught.value)
    assert "pymodbus" in msg
    assert "pip install pymodbus" in msg
    assert "Traceback" not in msg


async def test_the_executor_honours_a_requested_timeout(tmp_path: Path) -> None:
    """If the tool explicitly asked for time (like timeout: 600 to shell) the
    executor's general limit must not kill it at 180 s."""
    from dornick.config import Config
    from dornick.events import EventLog
    from dornick.permissions import PermissionEngine
    from dornick.session import Session
    from dornick.tools import ToolContext
    from dornick.tools.executor import execute

    reg = ToolRegistry()

    @reg.tool("slowish", "yavaş ama meşru", object_schema({"timeout": {"type": "integer"}}))
    async def _slow(args, ctx):
        await asyncio.sleep(0.2)
        return ToolResult("bitti")

    config = Config.load(tmp_path)
    config.ensure_dirs()
    ctx = ToolContext(config=config,
                      session=Session(EventLog(tmp_path / "s.jsonl"), "test"),
                      cancel=asyncio.Event())

    async def yes(spec, args):
        return True

    blocks = await execute(
        [PendingToolUse(id="a", name="slowish", input={"timeout": 600})],
        registry=reg, permissions=PermissionEngine("yolo", allow=[], deny=[]),
        ctx=ctx, approve=yes, timeout_s=0.05)   # the general limit is deliberately small

    assert blocks[0]["is_error"] is False, "the requested time should have exceeded the general limit"


# -- model-outage resilience ---------------------------------------------


async def test_transient_model_errors_are_retried(
    tmp_path: Path, registry: ToolRegistry, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A connection/5xx error does not kill the run: it backs off and retries.
    (Old behaviour: a SINGLE error ended the turn.)"""
    monkeypatch.setattr(loop_module, "RETRY_DELAYS", (0.01, 0.01, 0.01))
    client = FakeClient(
        TurnResult(error="Bağlantı kurulamadı: connection refused"),
        TurnResult(error="openrouter 503: overloaded"),
        text_turn("kesinti atlatıldı, cevap bu"),
    )
    agent = build_agent(tmp_path, client, registry)

    stats = await agent.run("uzun iş")

    assert stats.stop_reason == "end_turn"
    assert len(agent.session.log.notes("api_error")) == 2
    assert "kesinti atlatıldı" in str(agent.session.messages())
    assert stats.turns == 1, "failed attempts must not eat the turn fuse"


async def test_a_malformed_request_still_stops(
    tmp_path: Path, registry: ToolRegistry
) -> None:
    """A malformed request (400) is not fixed by retrying: the old behaviour is kept."""
    client = FakeClient(
        TurnResult(error="API 400: her tool_use için bir tool_result dönmeli"),
        text_turn("buraya gelinmemeli"),
    )
    agent = build_agent(tmp_path, client, registry)

    await agent.run("bir şey")

    assert len(agent.session.log.notes("api_error")) == 1
    assert client.script, "the second turn should never have been attempted"


async def test_a_long_outage_parks_then_resumes(
    tmp_path: Path, registry: ToolRegistry, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When the retries run out the job does not die, it is PARKED; when the
    model comes back it carries on where it left off and the park record is
    cleared."""
    monkeypatch.setattr(loop_module, "RETRY_DELAYS", (0.01, 0.01))
    monkeypatch.setattr(loop_module, "PARK_PROBE_S", 0.01)
    client = FakeClient(
        *[TurnResult(error="Bağlantı kurulamadı") for _ in range(5)],
        text_turn("model döndü, iş bitti"),
    )
    agent = build_agent(tmp_path, client, registry)

    notices: list[str] = []
    agent.io.on_notice = notices.append

    stats = await agent.run("saatlik iş")

    assert stats.stop_reason == "end_turn"
    assert agent.session.log.notes("parked"), "the park record should have been written"
    assert agent.session.log.notes("unparked")
    assert read_park(agent.config.state_dir) is None, "the record must be deleted when the job ends"
    assert any("bekletiliyor" in n for n in notices)
    assert any("geri geldi" in n for n in notices)
    assert "iş bitti" in str(agent.session.messages())


async def test_child_agent_fails_instead_of_parking_forever(
    tmp_path: Path, registry: ToolRegistry, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A subagent (task/orchestra) does NOT park after max retries — it ends with an error.

    This was the root cause of Market Lens staying stuck at 'Model
    bekleniyor (5/5) · 300s' while the main chat worked.
    """
    monkeypatch.setattr(loop_module, "RETRY_DELAYS", (0.01, 0.01))
    monkeypatch.setattr(loop_module, "PARK_PROBE_S", 30.0)
    client = FakeClient(
        *[TurnResult(error="Bağlantı kurulamadı") for _ in range(6)],
        text_turn("buraya gelinmemeli"),
    )
    agent = build_agent(tmp_path, client, registry)
    agent.depth = 1

    waits: list[dict] = []
    agent.io.on_wait = waits.append

    stats = await agent.run("zamanlanmış tarama")

    assert stats.interrupted is True
    assert stats.fail_reason
    assert not agent.session.log.notes("parked"), "a subagent must not park"
    assert read_park(agent.config.state_dir) is None
    assert any(w.get("kip") == "hata" for w in waits)
    assert client.script, "the successful turn should never have been attempted"


async def test_interrupt_during_backoff_stops_and_unparks(
    tmp_path: Path, registry: ToolRegistry, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The wait is interruptible: if the user says 'stop' the park record goes too."""
    monkeypatch.setattr(loop_module, "RETRY_DELAYS", (0.01,))
    monkeypatch.setattr(loop_module, "PARK_PROBE_S", 30.0)   # will wait in park
    client = FakeClient(*[TurnResult(error="Bağlantı kurulamadı") for _ in range(9)])
    agent = build_agent(tmp_path, client, registry)

    async def stop_soon() -> None:
        await asyncio.sleep(0.1)
        agent.interrupt()

    stopper = asyncio.ensure_future(stop_soon())
    stats = await agent.run("iş")
    await stopper

    assert stats.interrupted is True
    assert read_park(agent.config.state_dir) is None


async def test_retry_wait_applies_a_pending_model_swap(
    tmp_path: Path, registry: ToolRegistry, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A setting fixed during the outage (new address/key) takes effect on
    the next attempt — since the parked turn never ends it cannot wait for
    the end of the turn."""
    monkeypatch.setattr(loop_module, "RETRY_DELAYS", (0.01, 0.01))
    client = FakeClient(
        TurnResult(error="Bağlantı kurulamadı"),
        text_turn("yeni istemciyle geldi"),
    )
    agent = build_agent(tmp_path, client, registry)
    swaps: list[bool] = []
    agent.on_retry_wait = lambda: swaps.append(True)

    stats = await agent.run("iş")

    assert stats.stop_reason == "end_turn"
    assert swaps, "the pending change should have been applied before retrying"


async def test_wait_events_carry_the_structured_fields(
    tmp_path: Path, registry: ToolRegistry, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The waiting-state event contract: with the structured channel
    (on_wait) attached every attempt goes with the kip/deneme/toplam/saniye/
    detay fields, the recovery is a single "bitti" event and NO RAW ERROR
    LANDS in the chat channel (on_notice) — the UI draws this as a single
    live line in the work strip."""
    monkeypatch.setattr(loop_module, "RETRY_DELAYS", (0.01, 0.01, 0.01))
    client = FakeClient(
        TurnResult(error="APIStatusError 402: {'detail': 'insufficient credits'}"),
        TurnResult(error="Bağlantı kurulamadı: connection refused"),
        text_turn("kesinti atlatıldı"),
    )
    agent = build_agent(tmp_path, client, registry)

    events: list[dict] = []
    notices: list[str] = []
    agent.io.on_wait = events.append
    agent.io.on_notice = notices.append

    stats = await agent.run("uzun iş")

    assert stats.stop_reason == "end_turn"
    assert [e["kip"] for e in events] == ["deneme", "deneme", "bitti"]
    first = events[0]
    assert first["deneme"] == 1 and first["toplam"] == len(loop_module.RETRY_DELAYS)
    assert first["saniye"] == 0          # int(0.01) — the field exists and is numeric
    assert "402" in first["detay"]
    assert events[-1]["deneme"] == 2, "the bitti event must carry how many attempts it took"
    # The chat is clean: neither a raw error wall nor a separate "geri geldi" line.
    assert not any("402" in n for n in notices)
    assert not any("geri geldi" in n for n in notices)


async def test_wait_events_fall_back_to_notices_without_the_channel(
    tmp_path: Path, registry: ToolRegistry, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If on_wait is not attached (CLI, tests) the old plain-text behaviour
    stays as it is: the attempt notice and the "geri geldi" line flow from
    on_notice."""
    monkeypatch.setattr(loop_module, "RETRY_DELAYS", (0.01,))
    client = FakeClient(
        TurnResult(error="openrouter 503: overloaded"),
        text_turn("döndü"),
    )
    agent = build_agent(tmp_path, client, registry)
    notices: list[str] = []
    agent.io.on_notice = notices.append

    await agent.run("iş")

    assert any("yeniden denenecek" in n for n in notices)
    assert any("geri geldi" in n for n in notices)


async def test_parked_wait_emits_park_events_but_keeps_the_notice(
    tmp_path: Path, registry: ToolRegistry, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The park edge case: the strip gets the "park" event (live line), and
    the single park notice in the chat stays too — it is the only place
    where the user can take action (the Oto mode hint)."""
    monkeypatch.setattr(loop_module, "RETRY_DELAYS", (0.01,))
    monkeypatch.setattr(loop_module, "PARK_PROBE_S", 0.01)
    client = FakeClient(
        *[TurnResult(error="Bağlantı kurulamadı") for _ in range(3)],
        text_turn("model döndü"),
    )
    agent = build_agent(tmp_path, client, registry)
    events: list[dict] = []
    notices: list[str] = []
    agent.io.on_wait = events.append
    agent.io.on_notice = notices.append

    stats = await agent.run("saatlik iş")

    assert stats.stop_reason == "end_turn"
    modes = [e["kip"] for e in events]
    assert modes[0] == "deneme" and "park" in modes and modes[-1] == "bitti"
    park = next(e for e in events if e["kip"] == "park")
    assert park["saniye"] == int(0.01) and "Bağlantı" in park["detay"]
    assert any("bekletiliyor" in n for n in notices), "the park notice stays in the chat"


async def test_interrupting_a_wait_emits_the_cancel_event(
    tmp_path: Path, registry: ToolRegistry, monkeypatch: pytest.MonkeyPatch
) -> None:
    """"Stop" while waiting: the live line in the strip closes with the "iptal" event."""
    monkeypatch.setattr(loop_module, "RETRY_DELAYS", (30.0,))   # will be interrupted while waiting
    client = FakeClient(*[TurnResult(error="Bağlantı kurulamadı") for _ in range(3)])
    agent = build_agent(tmp_path, client, registry)
    events: list[dict] = []
    agent.io.on_wait = events.append

    async def stop_soon() -> None:
        await asyncio.sleep(0.05)
        agent.interrupt()

    stopper = asyncio.ensure_future(stop_soon())
    stats = await agent.run("iş")
    await stopper

    assert stats.interrupted is True
    assert [e["kip"] for e in events] == ["deneme", "iptal"]


async def test_the_bridge_publishes_wait_events_to_the_hub(tmp_path: Path) -> None:
    """Bridge contract: the on_wait payload lands in the hub with the
    "bekleme" type, fields carried as they are — app.js draws the single
    live line with this."""
    from dornick.desktop import Bridge

    class _Hub:
        def __init__(self) -> None:
            self.events: list[dict] = []

        def emit(self, payload: dict) -> None:
            self.events.append(payload)

    hub = _Hub()
    bridge = Bridge(hub, asyncio.get_running_loop())
    io = bridge.io()

    assert io.on_wait is not None, "the desktop bridge must attach the structured channel"
    io.on_wait({"kip": "deneme", "deneme": 2, "toplam": 5,
                "saniye": 30, "detay": "APIStatusError 402"})

    assert hub.events == [{"type": "bekleme", "kip": "deneme", "deneme": 2,
                           "toplam": 5, "saniye": 30, "detay": "APIStatusError 402"}]


async def test_full_authority_resolves_pending_approval_cards(tmp_path: Path) -> None:
    """Switching to full authority approves open permission cards BY ITSELF.

    Live wound (01.09): with a card open the user picks "tam yetki", the
    card stays hanging, the turn waits for permission forever. When the
    mode changes the pending requests are re-evaluated with the new engine.
    """
    from types import SimpleNamespace

    from dornick.config import Config
    from dornick.desktop import Bridge, Pending
    from dornick.permissions import PermissionEngine
    from dornick.tools.base import ToolSpec, object_schema

    class _Hub:
        def __init__(self) -> None:
            self.events: list[dict] = []

        def emit(self, payload: dict) -> None:
            self.events.append(payload)

    config = Config.load(tmp_path)
    config.ensure_dirs()

    bridge = Bridge(_Hub(), asyncio.get_running_loop())
    agent = SimpleNamespace(
        session=SimpleNamespace(id="s1"),
        permissions=PermissionEngine("ask", allow=[], deny=[]),
        config=config,
        reconfigure=lambda cfg: None,
    )
    bridge.agent = agent

    async def _handler(args, ctx):  # pragma: no cover - never runs
        return None

    spec = ToolSpec(name="shell", description="", input_schema=object_schema({}),
                    handler=_handler, mutates=True)
    fut: asyncio.Future[bool] = asyncio.get_running_loop().create_future()
    bridge._pending["kart1"] = Pending(future=fut, spec=spec,
                                       args={"command": "ls"})

    config.permissions.mode = "yolo"
    bridge.reload(config)
    await asyncio.sleep(0)   # let the call_soon_threadsafe resolution run

    assert fut.done() and fut.result() is True


def test_outage_rotates_the_auto_pool() -> None:
    """In auto mode an outage counts as an error: the penalised model drops
    to the end of the pool, the next attempt goes with another model."""
    from dornick import automode

    health = automode.Health()
    for _ in range(automode.ERROR_THRESHOLD):
        health.save("a/model", False)

    assert health.cezali("a/model")
    assert health.rank(["a/model", "b/model"]) == ["b/model", "a/model"]


def test_park_records_round_trip(tmp_path: Path) -> None:
    write_park(tmp_path, "20260826T000000Z", "bağlantı yok")
    record = read_park(tmp_path)
    assert record and record["session"] == "20260826T000000Z"
    clear_park(tmp_path)
    assert read_park(tmp_path) is None
    clear_park(tmp_path)   # a second delete does not blow up


async def test_the_bridge_resumes_a_parked_run(tmp_path: Path) -> None:
    """The counterpart of the park record found at startup: on seeing the
    pump marker it resumes the run where it left off."""
    from dornick.desktop import _PARK_RESUME, Bridge

    class _Hub:
        def __init__(self) -> None:
            self.events: list[dict] = []

        def emit(self, payload: dict) -> None:
            self.events.append(payload)

    hub = _Hub()
    bridge = Bridge(hub, asyncio.get_running_loop())

    resumed: list[bool] = []

    class StubAgent:
        async def resume_after_interrupt(self):
            resumed.append(True)

    bridge.agent = StubAgent()
    bridge.queue.put_nowait(_PARK_RESUME)
    item = bridge.queue.get_nowait()
    assert item is _PARK_RESUME
    await bridge._resume_parked()

    assert resumed == [True]
    assert [e["type"] for e in hub.events][-1] == "turn_end"


# -- counters of a resumed session --------------------------------------
#
# Proven wound: when the app closed and reopened, or a conversation from
# the history was resumed, the context bar and the token counter in the
# dock started from ZERO. The history was loaded, the context really was
# full — the user lost the "how full am I" information. The right source
# is the session log.


def _session_with(tmp_path: Path, rows: list[tuple[str, str, dict]]):
    """Builds a session with the given messages and returns the fake agent carrying it."""
    from dornick.events import EventLog
    from dornick.session import Session

    session = Session(EventLog(tmp_path / "s.jsonl"), "s")
    for role, text, meta in rows:
        session.log.message(role, [{"type": "text", "text": text}], **meta)
    return SimpleNamespace(session=session)


def test_a_resumed_session_seeds_the_counters_from_real_usage(tmp_path: Path) -> None:
    """The most accurate source: the `usage` meta of the last assistant turn
    — the real figure the provider counted. The estimate flag is DOWN: no
    making things up."""
    from dornick.desktop import _past_usage

    agent = _session_with(tmp_path, [
        ("user", "merhaba", {}),
        ("assistant", "selam", {"usage": {"prompt_total": 1200, "output": 40}}),
        ("user", "devam", {}),
        ("assistant", "tamam", {"usage": {"prompt_total": 5400, "output": 90}}),
    ])

    status = _past_usage(agent)

    assert status["prompt_total"] == 5400, "the LAST turn's prompt is the valid one"
    assert status["girdi"] == 6600, "cost: the prompts of all turns are summed"
    assert status["output"] == 130, "output is summed over the session"
    assert status["cagri"] == 2
    assert status["tahmin"] is False


def test_an_old_log_without_usage_falls_back_to_an_estimate(tmp_path: Path) -> None:
    """Without usage (an old log or a provider that gives no counter)
    showing an approximation is better than showing zero — as long as it is
    said to be an estimate. The `tahmin` flag becomes a title in the UI."""
    from dornick.desktop import _past_usage

    agent = _session_with(tmp_path, [
        ("user", "a" * 400, {}),
        ("assistant", "b" * 400, {}),
    ])

    status = _past_usage(agent)

    assert status["tahmin"] is True
    assert status["prompt_total"] > 0
    assert status["girdi"] == status["prompt_total"]
    assert status["cagri"] == 0


def test_a_fresh_session_really_starts_at_zero(tmp_path: Path) -> None:
    """NO seed in a new conversation: the counter must really start from zero."""
    from dornick.desktop import _past_usage

    agent = _session_with(tmp_path, [])

    assert _past_usage(agent) == {
        "prompt_total": 0, "girdi": 0, "output": 0, "cagri": 0, "tahmin": False}


async def test_the_snapshot_carries_the_resumed_context(tmp_path: Path) -> None:
    """Bridge contract: the snapshot carries the context fullness and the
    spend total — app.js is seeded with these at startup (the same pattern
    as the goals/channels seeding)."""
    from dornick.desktop import Bridge

    class _Hub:
        def emit(self, payload: dict) -> None:
            pass

    bridge = Bridge(_Hub(), asyncio.get_running_loop())
    agent = _session_with(tmp_path, [
        ("user", "merhaba", {}),
        ("assistant", "selam", {"usage": {"prompt_total": 3000, "output": 50}}),
    ])
    # The snapshot also looks at the agent's settings; a real Config suffices.
    from dornick.config import Config
    from dornick.permissions import PermissionEngine

    config = Config.load(tmp_path)
    config.ensure_dirs()
    agent.config = config
    agent.permissions = PermissionEngine("ask", allow=[], deny=[])
    agent.mind = None
    agent._children = None
    agent._last_usage = None
    agent.registry = ToolRegistry()
    bridge.agent = agent

    state = bridge.snapshot()

    assert state["prompt_total"] == 3000
    assert state["tahmin"] is False
    # Item-by-item breakdown: statics + the remaining conversation = prompt_total.
    breakdown = {p["id"]: p["n"] for p in state["kirilim"]}
    assert set(breakdown) == {
        "sistem", "arac", "ruh", "yetenek", "mcp", "yardimci", "sohbet"}
    assert sum(breakdown.values()) == 3000
    assert breakdown["sohbet"] == 3000 - (
        breakdown["sistem"] + breakdown["arac"] + breakdown["ruh"]
        + breakdown["yetenek"] + breakdown["mcp"] + breakdown["yardimci"])
    # The cost chip's session total was seeded from the same source too.
    assert state["kullanim"]["oturum"] == {"girdi": 3000, "cikti": 50, "cagri": 1}
    # A second snapshot (page reloaded) does NOT INFLATE the total: seeded once.
    assert bridge.snapshot()["kullanim"]["oturum"]["cagri"] == 1


def test_context_breakdown_puts_the_remainder_in_conversation() -> None:
    """The provider gives only the total: statics are characters/4, the rest is conversation."""
    import json

    from dornick.desktop import context_breakdown

    schema = {"name": "x", "description": "yyyy", "input_schema": {}}
    skill = {"name": "sk", "description": "z" * 20, "input_schema": {}}
    mcp = {"name": "m", "description": "m" * 16, "input_schema": {}}
    task = {"name": "task", "description": "y" * 24, "input_schema": {}}

    def tok(obj: dict) -> int:
        return len(json.dumps(obj, ensure_ascii=False, separators=(",", ":"))) // 4

    agent = SimpleNamespace(
        _system=SimpleNamespace(core="S" * 40, identity="R" * 20),
        registry=SimpleNamespace(all=lambda: [
            SimpleNamespace(name="x", source="", api_schema=lambda: schema),
            SimpleNamespace(name="sk", source="yetenek", api_schema=lambda: skill),
            SimpleNamespace(name="m", source="mcp:uzak", api_schema=lambda: mcp),
            SimpleNamespace(name="task", source="", api_schema=lambda: task),
        ]),
        brief_schema=False,
    )
    parts = context_breakdown(agent, 1000)
    by_n = {p["id"]: p["n"] for p in parts}
    assert by_n["sistem"] == 10
    assert by_n["ruh"] == 5
    assert by_n["arac"] == tok(schema)
    assert by_n["yetenek"] == tok(skill)
    assert by_n["mcp"] == tok(mcp)
    assert by_n["yardimci"] == tok(task)
    assert by_n["sohbet"] == 1000 - sum(n for k, n in by_n.items() if k != "sohbet")
    assert [p["ad"] for p in parts] == [
        "Sistem istemi", "Araç tanımları", "Ruh / kurallar",
        "Yetenekler", "MCP ve dinamik araçlar", "Yardımcı tanımları", "Konuşma",
    ]


def test_context_breakdown_scales_when_static_exceeds_total() -> None:
    """If the statics exceed the provider total they are scaled — conversation stays zero."""
    from dornick.desktop import context_breakdown

    agent = SimpleNamespace(
        _system=SimpleNamespace(core="x" * 400, identity=""),
        registry=None,
    )
    parts = {p["id"]: p["n"] for p in context_breakdown(agent, 40)}
    assert parts["sistem"] == 40
    assert parts["sohbet"] == 0
    assert sum(parts.values()) == 40


def test_context_breakdown_without_agent_is_all_conversation() -> None:
    from dornick.desktop import context_breakdown

    parts = {p["id"]: p["n"] for p in context_breakdown(None, 500)}
    assert parts["sohbet"] == 500
    assert parts["sistem"] == parts["arac"] == parts["ruh"] == 0
    assert parts["yetenek"] == parts["mcp"] == parts["yardimci"] == 0


def test_context_breakdown_shows_statics_before_the_first_turn() -> None:
    """System/tools must show before the first turn too — no zero-percent lie."""
    from dornick.desktop import context_breakdown

    agent = SimpleNamespace(
        _system=SimpleNamespace(core="x" * 40, identity=""),
        registry=None,
    )
    parts = {p["id"]: p["n"] for p in context_breakdown(agent, 0)}
    assert parts["sistem"] == 10
    assert parts["sohbet"] == 0
