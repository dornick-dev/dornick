"""Internal content leaks: harness note, raw reasoning, fake tool call.

All three are members of the same wound — text the user did not write, or
that must not be shown to the user, was drawn STRAIGHT into the chat. They
were caught in screenshots:

  1. "Planını yazdın ama uygulamadın. Şimdi yap: …" — the harness's
     continuation nudge, in the chat like a user message.
  2. The model's internal reasoning, in the chat as italic paragraphs.
  3. `<function_calls><invoke name="shell">…` — a fake tool call the model
     wrote as plain text.

Their roots differ, the line of defence is the same: internal content is
marked, and marked content reaches neither the live stream nor the
transcript.

The head of the chain is a separate wound: the tool layer returned the RAW
exception to the model ("KeyError: 'path'"), the model read it as "the tool
is broken" and started writing the call as text. The schema gate is tested
here too.
"""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

import pytest

from dornick.mind.store import Mind
from dornick.permissions import PermissionEngine
from dornick.tools import ToolContext, ToolRegistry, ToolResult, execute, object_schema
from dornick.tools.base import ToolSpec, schema_violation
from dornick.session import PendingToolUse
from types import SimpleNamespace

from tests.test_loop import (  # noqa: F401  (fixture + helpers)
    FakeClient, build_agent, registry, text_turn, tool_turn,
)


# -- 1. harness note: the transcript filter -----------------------------
#
# On the live stream the hub filtered `_payload`; the TRANSCRIPT did not.
# When a session was resumed or opened from history the internal notes came
# back as user messages — that was the real root of the leak.


def _write_log(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def test_the_transcript_hides_harness_notes(tmp_path: Path) -> None:
    """The continuation nudge, the harness note and the tool result are
    INVISIBLE in the transcript; the real words of the user and the agent show."""
    mind = Mind(tmp_path / "mind", tmp_path / "sessions", "s1")
    mind.sessions_dir.mkdir(parents=True, exist_ok=True)
    _write_log(mind.sessions_dir / "s1.jsonl", [
        {"kind": "message", "role": "user", "ts": 1,
         "content": [{"type": "text", "text": "bir panel yap"}], "meta": {}},
        {"kind": "message", "role": "assistant", "ts": 2,
         "content": [{"type": "text", "text": "Planım şu."}], "meta": {}},
        # The harness's continuation nudge — the user did not write it.
        {"kind": "message", "role": "user", "ts": 3,
         "content": [{"type": "text",
                      "text": "Planını yazdın ama uygulamadın. Şimdi yap: …"}],
         "meta": {"continuation": True}},
        # A harness note (like "helper finished") — the user did not write it.
        {"kind": "message", "role": "user", "ts": 4,
         "content": [{"type": "text", "text": "[Yardımcı bitti · x] Sonucu: y"}],
         "meta": {"internal": True}},
        # A tool result — technically a user turn, not a chat line.
        {"kind": "message", "role": "user", "ts": 5,
         "content": [{"type": "text", "text": "çıktı: 42"}],
         "meta": {"tool_results": True}},
        {"kind": "message", "role": "assistant", "ts": 6,
         "content": [{"type": "text", "text": "Panel hazır."}], "meta": {}},
    ])

    transcript = mind.transcript("s1")

    assert [t["text"] for t in transcript] == ["bir panel yap", "Planım şu.", "Panel hazır."]
    everything = " ".join(t["text"] for t in transcript)
    assert "uygulamadın" not in everything
    assert "Yardımcı bitti" not in everything


def test_the_transcript_hides_reasoning_only_turns(tmp_path: Path) -> None:
    """When the model only reasons and stops, the provider layer turns that
    reasoning into a TEXT block (openai_backend, `empty_turn`). Entering the
    history is right — the model should see its own plan — but it is NOT AN
    ANSWER to the user. The `internal` mark keeps it out of the transcript too."""
    mind = Mind(tmp_path / "mind", tmp_path / "sessions", "s2")
    mind.sessions_dir.mkdir(parents=True, exist_ok=True)
    _write_log(mind.sessions_dir / "s2.jsonl", [
        {"kind": "message", "role": "user", "ts": 1,
         "content": [{"type": "text", "text": "hisse verisi çek"}], "meta": {}},
        {"kind": "message", "role": "assistant", "ts": 2,
         "content": [{"type": "text",
                      "text": "Muhtemelen yfinance importu gerekir. Ama task_status yok…"}],
         "meta": {"internal": True, "usage": {"prompt_total": 10}}},
        {"kind": "message", "role": "assistant", "ts": 3,
         "content": [{"type": "text", "text": "Veri çekildi."}], "meta": {}},
    ])

    transcript = mind.transcript("s2")

    assert [t["text"] for t in transcript] == ["hisse verisi çek", "Veri çekildi."]


# -- 2. the schema gate: guidance instead of a raw exception -------------


def _spec(properties: dict, required: list[str]) -> ToolSpec:
    return ToolSpec(
        name="write_file", description="yazar",
        input_schema=object_schema(properties, required),
        handler=lambda *_: None,   # type: ignore[arg-type]
    )


def test_a_missing_required_field_teaches_instead_of_raising() -> None:
    """The first link of the proven chain: a missing `path` must be a message
    saying what to do instead of a raw `KeyError`."""
    spec = _spec({"path": {"type": "string"}, "text": {"type": "string"}},
                 ["path", "text"])

    warning = schema_violation(spec, {"text": "merhaba"})

    assert warning is not None
    assert "`path`" in warning                    # which field
    assert "Verdiğin alanlar: text" in warning    # what you gave
    assert "path (string, zorunlu)" in warning    # what the schema is
    assert "KeyError" not in warning


def test_a_wrong_type_is_named_with_both_sides() -> None:
    spec = _spec({"timeout": {"type": "number"}}, [])

    warning = schema_violation(spec, {"timeout": "otuz"})

    assert warning and "`timeout` alanı number olmalı" in warning
    assert "str verdin" in warning


def test_an_enum_violation_lists_the_valid_values() -> None:
    spec = _spec({"action": {"type": "string", "enum": ["read", "write"]}}, [])

    warning = schema_violation(spec, {"action": "oku"})

    assert warning and "read, write" in warning


def test_a_valid_call_passes_and_extra_fields_are_tolerated() -> None:
    """An extra field is NOT an error: rejecting a working call because of
    an extra field would break the tool."""
    spec = _spec({"path": {"type": "string"}}, ["path"])

    assert schema_violation(spec, {"path": "a.txt"}) is None
    assert schema_violation(spec, {"path": "a.txt", "encoding": "utf-8"}) is None


async def test_the_executor_gates_every_tool_from_one_place(tmp_path: Path) -> None:
    """The schema gate is in the executor: the same guarantee for every tool,
    no patching of individual tools. The handler is NEVER called — running
    with a missing field would have blown up anyway."""
    from dornick.config import Config
    from dornick.events import EventLog
    from dornick.session import Session

    config = Config.load(tmp_path)
    config.ensure_dirs()
    ctx = ToolContext(config=config,
                      session=Session(EventLog(tmp_path / "s.jsonl"), "t"),
                      cancel=asyncio.Event())

    registry = ToolRegistry()
    ran: list[dict] = []

    @registry.tool("write_file", "yazar",
                   object_schema({"path": {"type": "string"},
                                  "text": {"type": "string"}}, ["path", "text"]))
    async def _write(args, _ctx):
        ran.append(args)
        return ToolResult("yazıldı: " + args["path"])   # would blow up on a missing field

    blocks = await execute(
        [PendingToolUse("1", "write_file", {"text": "merhaba"})],
        registry=registry,
        permissions=PermissionEngine("yolo", allow=[], deny=[]),
        ctx=ctx,
        approve=lambda *_: asyncio.sleep(0, result=True),
    )

    assert ran == [], "şemaya uymayan çağrı handler'a gitmemeliydi"
    assert blocks[0]["is_error"] is True
    assert "`path`" in blocks[0]["content"]
    assert "KeyError" not in blocks[0]["content"]


async def test_a_handler_exception_is_wrapped_with_guidance(tmp_path: Path) -> None:
    """An exception leaking out of the handler does not go raw either: the
    type + message STAY (diagnosis is needed) but what to do is written next
    to them. The model must not read it as "the tool is broken"."""
    from dornick.config import Config
    from dornick.events import EventLog
    from dornick.session import Session

    config = Config.load(tmp_path)
    config.ensure_dirs()
    ctx = ToolContext(config=config,
                      session=Session(EventLog(tmp_path / "s.jsonl"), "t"),
                      cancel=asyncio.Event())

    registry = ToolRegistry()

    @registry.tool("boom", "patlar", object_schema({}))
    async def _boom(args, _ctx):
        raise ValueError("içeride bir şey ters gitti")

    blocks = await execute(
        [PendingToolUse("1", "boom", {})],
        registry=registry,
        permissions=PermissionEngine("yolo", allow=[], deny=[]),
        ctx=ctx,
        approve=lambda *_: asyncio.sleep(0, result=True),
    )

    content = blocks[0]["content"]
    assert blocks[0]["is_error"] is True
    assert "ValueError" in content and "ters gitti" in content   # the diagnosis stays
    assert "yeniden dene" in content                             # guidance added
    assert "Traceback" not in content


# -- 3. fake tool call --------------------------------------------------


@pytest.mark.parametrize("text", [
    '<function_calls><invoke name="shell">',
    'Şimdi çalıştırıyorum:\n<invoke name="write_file">\n<parameter name="path">a</parameter>',
    "<invoke name=\"shell\">",
])
def test_tool_call_xml_in_text_is_recognised(text: str) -> None:
    from dornick.loop import fake_tool_call

    assert fake_tool_call(text) is True


@pytest.mark.parametrize("text", [
    "Dosyayı yazdım ve testleri koşturdum.",
    "HTML'de <div> ve <span> kullandım.",
    "",
])
def test_ordinary_text_is_not_mistaken_for_a_tool_call(text: str) -> None:
    """The pattern must be NARROW: if the user's answer gets swallowed because
    of tags in an ordinary reply, the defence becomes the wound itself."""
    from dornick.loop import fake_tool_call

    assert fake_tool_call(text) is False


# -- fake call: the loop side -------------------------------------------


async def test_a_faked_tool_call_does_not_end_the_turn(
    tmp_path: Path, registry: ToolRegistry
) -> None:
    """The model wrote the call as text and ended the turn. Stopping here
    would silently leave the user halfway: a harness note drops, the turn
    CONTINUES and the model makes the real call."""
    from tests.test_loop import FakeClient, build_agent, text_turn, tool_turn

    client = FakeClient(
        text_turn('Şimdi çalıştırıyorum:\n<function_calls>'
                  '<invoke name="shell"><parameter name="command">dir</parameter>'
                  '</invoke></function_calls>'),
        tool_turn(("t1", "echo", {"text": "gerçek çağrı"})),
        text_turn("iş bitti"),
    )
    agent = build_agent(tmp_path, client, registry)

    stats = await agent.run("klasörü listele")

    assert stats.stop_reason == "end_turn"
    assert stats.fake_calls == 1
    # The correction note really went to the model.
    sent = str(client.seen_messages[-1])
    assert "DÜZ METİN olarak yazdın" in sent
    # The note comes through the harness channel: the user did not write it, it must not show in the chat.
    marked = [e for e in agent.session.log.messages()
              if e.meta.get("internal") and "DÜZ METİN" in str(e.content)]
    assert marked, "düzeltme notu `internal` işaretli olmalı"


async def test_a_repeated_fake_call_hardens_the_note(
    tmp_path: Path, registry: ToolRegistry
) -> None:
    """If the soft note did not work it hardens — the turn is still not closed."""
    from tests.test_loop import FakeClient, build_agent, text_turn

    xml = '<invoke name="shell"><parameter name="command">dir</parameter></invoke>'
    client = FakeClient(text_turn(xml), text_turn(xml), text_turn("tamam, düzeldim"))
    agent = build_agent(tmp_path, client, registry)

    stats = await agent.run("listele")

    assert stats.fake_calls == 2
    assert "YİNE metin olarak yazdın" in str(client.seen_messages[-1])


async def test_a_hopeless_model_stops_holding_the_turn(
    tmp_path: Path, registry: ToolRegistry, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The absolute fuse: a model that does not recover must not occupy the
    turn forever. At the ceiling the turn is left to its own flow and the user
    is told the situation — the fix is in their hands (switching model)."""
    import dornick.loop as loop_module
    from tests.test_loop import FakeClient, build_agent, text_turn

    monkeypatch.setattr(loop_module, "FAKE_CALL_CAP", 2)
    xml = '<invoke name="shell">'
    client = FakeClient(*[text_turn(xml) for _ in range(10)])
    agent = build_agent(tmp_path, client, registry)
    notices: list[str] = []
    agent.io.on_notice = notices.append

    stats = await agent.run("listele")

    assert stats.fake_calls == 3, "tavanı bir aşınca bırakılmalı"
    assert any("başka bir model" in n for n in notices)


async def test_a_real_tool_call_is_never_hijacked(
    tmp_path: Path, registry: ToolRegistry
) -> None:
    """Even with XML in the text, if there is a REAL tool call we do not
    interfere: it means the work is moving."""
    from dornick.backends import TurnResult
    from tests.test_loop import FakeClient, build_agent, message, text_turn

    mixed = TurnResult(message=message([
        {"type": "text", "text": '<invoke name="shell">'},
        {"type": "tool_use", "id": "t1", "name": "echo", "input": {"text": "x"}},
    ], "tool_use"))
    client = FakeClient(mixed, text_turn("bitti"))
    agent = build_agent(tmp_path, client, registry)

    stats = await agent.run("çalış")

    assert stats.fake_calls == 0
    assert stats.tool_calls == 1


# -- auto pool health penalty -------------------------------------------
#
# In the free pool an endpoint that cannot call tools is no different from
# one that errors: it does not move the work forward, it only spends turns.
# A schema violation and a fake tool call are now health signals alongside
# error/timeout/empty reply.


def _auto_backend():
    from dornick.backends.openai_backend import OpenAIBackend
    from dornick.config import OPENROUTER_URL, OTO_MODEL, ModelConfig

    return OpenAIBackend(ModelConfig(
        provider="openai", name=OTO_MODEL, base_url=OPENROUTER_URL))


def test_content_faults_penalise_the_auto_pool() -> None:
    """A schema violation and a fake call write a failure into the health
    ledger; a model past the threshold sinks to the bottom of the pool."""
    from dornick import automode

    backend = _auto_backend()
    backend._last_selected = "ucuz/model"
    for _ in range(automode.ERROR_THRESHOLD):
        backend.kusurlu("sahte araç çağrısı")

    assert backend._health.cezali("ucuz/model")
    assert backend._health.rank(["ucuz/model", "saglam/model"]) \
        == ["saglam/model", "ucuz/model"]


def test_a_chosen_model_is_never_punished_behind_the_users_back() -> None:
    """OUTSIDE auto mode there is no consequence: the user chose the model
    themselves, ranking it behind their back is not our place."""
    from dornick.backends.openai_backend import OpenAIBackend
    from dornick.config import ModelConfig

    backend = OpenAIBackend(ModelConfig(
        provider="openai", name="anthropic/claude", base_url="https://x"))
    backend._last_selected = "anthropic/claude"
    backend.kusurlu("şema ihlali")

    assert not backend._health.cezali("anthropic/claude")


async def test_the_loop_reports_content_faults_to_the_backend(
    tmp_path: Path, registry: ToolRegistry  # noqa: F811
) -> None:
    """The loop really passes the signal on: a fake call and a schema
    violation are reported to the provider with `client.kusurlu`."""
    from tests.test_loop import FakeClient, build_agent, text_turn, tool_turn

    class _Counting(FakeClient):
        def __init__(self, *script):
            super().__init__(*script)
            self.reasons: list[str] = []

        def kusurlu(self, sebep: str = "") -> None:
            self.reasons.append(sebep)

    client = _Counting(
        text_turn('<invoke name="shell">'),
        # The `echo` schema expects `text`; `metin` is not a wrong field but
        # there is no required field — so it is tested with a type violation.
        tool_turn(("t1", "echo", {"text": 42})),
        text_turn("bitti"),
    )
    agent = build_agent(tmp_path, client, registry)

    await agent.run("çalış")

    assert "sahte araç çağrısı" in client.reasons
    assert "şema ihlali" in client.reasons


# -- the goals panel: the management endpoint ----------------------------
#
# The panel was display-only and the user rightly asked: "where do these get
# added, where do they get cleared?" The agent adds with `mind_goals`; the
# user had nothing in hand, and goals left over from old sessions kept piling
# up. Now the user can write to the same ledger too.


def _goals_server(tmp_path: Path):
    import urllib.request

    from dornick.config import Config
    from dornick.events import EventLog
    from dornick.mind import open_mind
    from dornick.web import MindServer

    config = Config.load(tmp_path)
    config.ensure_dirs()
    mind = open_mind(tmp_path / "mind", tmp_path / "sessions", "cur")
    log = EventLog(tmp_path / "s.jsonl")
    server = MindServer(mind, log, port=0, config=config)
    server.start()

    def send(payload: dict) -> dict:
        request = urllib.request.Request(
            server.url + "api/goals",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(request, timeout=5) as response:
            return json.loads(response.read().decode("utf-8"))

    return server, log, mind, send


def test_the_user_can_finish_and_drop_a_goal(tmp_path: Path) -> None:
    server, log, mind, send = _goals_server(tmp_path)
    try:
        finishing = mind.push_goal("testleri yeşile al")
        dropping = mind.push_goal("bayat hedef")

        assert send({"action": "done", "id": finishing.id})["ok"] is True
        assert send({"action": "drop", "id": dropping.id})["ok"] is True

        # The active list emptied; the statuses in the ledger really changed.
        assert mind.goals() == []
        assert mind._goals[finishing.id].status == "done"
        assert mind._goals[dropping.id].status == "dropped"
    finally:
        server.stop()
        log.close()


def test_clear_empties_the_whole_stack(tmp_path: Path) -> None:
    """A piled-up list must be clearable with one gesture — in the UI it
    sits behind a two-step confirmation."""
    server, log, mind, send = _goals_server(tmp_path)
    try:
        for i in range(6):
            mind.push_goal(f"eski hedef {i}")
        assert len(mind.goals()) == 6

        assert send({"action": "clear"})["ok"] is True
        assert mind.goals() == []
    finally:
        server.stop()
        log.close()


def test_a_bad_goal_request_is_refused_without_touching_the_ledger(
    tmp_path: Path
) -> None:
    """An invented action and an invalid id are refused without touching the ledger."""
    server, log, mind, send = _goals_server(tmp_path)
    try:
        goal = mind.push_goal("duran hedef")

        assert send({"action": "sil-hepsini"})["ok"] is False
        assert send({"action": "done", "id": "../../etc"})["ok"] is False
        assert send({"action": "done", "id": "goal-yok"})["ok"] is False

        assert [g.id for g in mind.goals()] == [goal.id]
    finally:
        server.stop()
        log.close()


async def test_a_faked_call_turn_is_marked_internal(
    tmp_path: Path, registry: ToolRegistry  # noqa: F811
) -> None:
    """The raw XML enters the history (the model must see what it did) but is
    marked `internal`: when the session is resumed it does not come back as an
    agent message."""
    from tests.test_loop import FakeClient, build_agent, text_turn

    client = FakeClient(text_turn('<invoke name="shell">'), text_turn("düzeldim"))
    agent = build_agent(tmp_path, client, registry)

    await agent.run("listele")

    xml_turn = [e for e in agent.session.log.messages()
                if e.role == "assistant" and "invoke" in str(e.content)]
    assert xml_turn and xml_turn[0].meta.get("internal") is True
    # The real answer is NOT marked: the user must see it.
    real = [e for e in agent.session.log.messages()
            if e.role == "assistant" and "düzeldim" in str(e.content)]
    assert real and not real[0].meta.get("internal")


def test_the_user_can_add_their_own_item(tmp_path: Path) -> None:
    """The list is two-sided: the agent writes with `mind_goals`, the user
    from the panel. The same ledger — the agent sees its own item too."""
    server, log, mind, send = _goals_server(tmp_path)
    try:
        response = send({"action": "add", "text": "faturayi ode"})
        assert response["ok"] is True and response["id"]
        assert [g.text for g in mind.goals()] == ["faturayi ode"]

        # An empty item is refused; the ledger is not polluted.
        assert send({"action": "add", "text": "   "})["ok"] is False
        assert len(mind.goals()) == 1

        # A novel-length item is trimmed.
        send({"action": "add", "text": "x" * 500})
        assert max(len(g.text) for g in mind.goals()) <= 200
    finally:
        server.stop()
        log.close()


def test_goals_from_earlier_sessions_stay_out_of_the_panel(tmp_path: Path) -> None:
    """The answer to "who creates these tasks": the goal ledger is the
    CHAT's ledger. Another session's item never reaches the panel (live
    wound: at the end of a PDF chat the agent was discussing another chat's
    "home automation" goal); the places that look at the whole mind ask with
    all_sessions."""
    from types import SimpleNamespace

    from dornick.desktop import _active_goals
    from dornick.mind import open_mind

    mind = open_mind(tmp_path / "mind", tmp_path / "sessions", "eski-oturum")
    stale = mind.push_goal("geçen oturumdan kalan")
    mind.session_id = "yeni-oturum"
    fresh = mind.push_goal("bu oturumda açıldı")

    shown = {g["id"] for g in _active_goals(SimpleNamespace(mind=mind))}
    assert fresh.id in shown
    assert stale.id not in shown

    # The acceptance gate and the source of the system notes go through the same filter.
    assert stale.text not in mind.goal_digest()
    assert fresh.text in mind.goal_digest()

    # The brain graph asks for the whole mind — the filter's gate is open.
    everything = {g.id for g in mind.goals(all_sessions=True)}
    assert {stale.id, fresh.id} <= everything


# -- the mind-writing reflex --------------------------------------------
#
# Measured regression: ZERO `mind_memory` calls in the last six sessions,
# even in a turn with 91 tool calls. The automatic path (episode) was
# flowing, model-driven persistent writing had stopped. Two roots fixed at
# once: (1) writing to its own ledger was behind the approval gate, (2)
# writing was only advice.


class _Mind:
    """A fake mind that counts writes."""

    def __init__(self) -> None:
        self.session_id = "s"
        self.written: list[str] = []

    def remember(self, body, **kw):
        self.written.append(body)
        return SimpleNamespace(id="m1")

    def goals(self, **kw):
        return []

    def goal_digest(self):
        return ""


async def test_a_preference_nudges_the_agent_to_remember(
    tmp_path: Path, registry: ToolRegistry
) -> None:
    """The user said something lasting and the model did not write it into
    its own ledger: at the end of the turn a ONE-LINE note is put in front of
    the model. The note goes through the harness channel — invisible in the chat."""
    client = FakeClient(text_turn("tamam, öyle yapacağım"))
    agent = build_agent(tmp_path, client, registry)
    agent.mind = _Mind()

    await agent.run("bundan sonra raporları hep tablo yaz")

    notes = [e for e in agent.session.log.messages()
             if e.meta.get("internal") and "[Zihin]" in str(e.content)]
    assert notes, "kalıcı bir şey geçti, dürtü düşmeliydi"
    content = str(notes[0].content)
    assert "mind_memory" in content
    assert "tablo yaz" in content, "not neyi kastettiğini söylemeli"
    assert "yok say" in content, "emir değil davet: yanlış pozitifte zararsız"
    assert agent.session.log.notes("zihin_durtusu")


async def test_no_nudge_when_the_agent_already_wrote(
    tmp_path: Path, registry: ToolRegistry
) -> None:
    """If the model already wrote, nudging is needless noise."""
    reg = ToolRegistry()

    @reg.tool("mind_memory", "yazar", object_schema({"action": {"type": "string"}}))
    async def _mem(args, ctx):
        return ToolResult("yazıldı")

    client = FakeClient(
        tool_turn(("t1", "mind_memory", {"action": "save"})),
        text_turn("kaydettim"),
    )
    agent = build_agent(tmp_path, client, reg)
    agent.mind = _Mind()

    await agent.run("bundan sonra raporları hep tablo yaz")

    assert not agent.session.log.notes("zihin_durtusu")


async def test_no_nudge_without_a_lasting_signal(
    tmp_path: Path, registry: ToolRegistry
) -> None:
    """An ordinary question produces no nudge: the heuristic is cheap but must not be noisy."""
    client = FakeClient(text_turn("saat 14:00"))
    agent = build_agent(tmp_path, client, registry)
    agent.mind = _Mind()

    await agent.run("saat kaç")

    assert not agent.session.log.notes("zihin_durtusu")


async def test_the_nudge_does_not_repeat_for_the_same_sentence(
    tmp_path: Path, registry: ToolRegistry
) -> None:
    """Nudging about the same thing back to back is tiresome: it is said once."""
    client = FakeClient(text_turn("tamam"), text_turn("tamam"))
    agent = build_agent(tmp_path, client, registry)
    agent.mind = _Mind()

    await agent.run("bundan sonra hep tablo yaz")
    await agent.run("bundan sonra hep tablo yaz")

    assert len(agent.session.log.notes("zihin_durtusu")) == 1


def test_the_scent_reads_both_languages() -> None:
    """The user writes in both languages; the signal list must recognise both."""
    from dornick.loop import persistent_root

    assert persistent_root("bundan sonra raporları hep tablo yaz")
    assert persistent_root("benim adım Fatih")
    assert persistent_root("hayır, öyle değil — düzelt")
    assert persistent_root("from now on always use tables")
    assert persistent_root("i prefer short answers")
    # Ordinary sentences must give no scent.
    assert not persistent_root("saat kaç")
    assert not persistent_root("bu dosyayı okur musun")
    assert not persistent_root("")


# -- writing to its own ledger needs no approval -------------------------


def test_writing_to_its_own_mind_needs_no_approval() -> None:
    """THE REAL ROOT: `mind_memory save` counted as a mutation — every memory
    an approval window, and in plan mode an outright DENY. That is why the
    mind went silent. Writing to its own ledger asks for no approval;
    DELETING still does."""
    from dornick.permissions import Decision, PermissionEngine
    from dornick.tools.base import ToolSpec, object_schema

    spec = ToolSpec(
        name="mind_memory", description="", handler=lambda *_: None,  # type: ignore[arg-type]
        input_schema=object_schema({"action": {"type": "string"}}, ["action"]),
        mutates=True, safe_actions=("save", "list", "link", "series"),
    )

    for mode in ("ask", "auto", "plan"):
        engine = PermissionEngine(mode, allow=[], deny=[])
        decision, _ = engine.evaluate(spec, {"action": "save"})
        assert decision is Decision.ALLOW, f"{mode}: kaydetmek sorulmamalı"

    # Deleting is something else: permanent loss, the gate stays closed.
    assert PermissionEngine("ask", allow=[], deny=[]).evaluate(
        spec, {"action": "forget"})[0] is Decision.ASK
    assert PermissionEngine("plan", allow=[], deny=[]).evaluate(
        spec, {"action": "forget"})[0] is Decision.DENY


def test_the_real_mind_tools_declare_their_safe_actions(tmp_path: Path) -> None:
    """The flag is really on the registered tools: the pattern must not stay in one place."""
    from dornick.mind import open_mind
    from dornick.mind.tools import register as register_mind

    reg = ToolRegistry()
    register_mind(reg, open_mind(tmp_path / "mind", tmp_path / "sessions", "s"))

    memory = reg.get("mind_memory")
    assert memory and "save" in memory.safe_actions
    assert "forget" not in memory.safe_actions, "silme gated kalmalı"
    goals = reg.get("mind_goals")
    assert goals and "push" in goals.safe_actions


def test_the_guide_asks_for_writing_in_the_moment() -> None:
    """The guide writes it as a general rule: a principle, not a prescription."""
    from dornick import prompt as builder

    flat = " ".join(builder.MEMORY_RULES.split())
    assert "sen sormasan da" in flat
    assert "o an" in flat or "konu geçerken" in flat
    assert "oturum kapanınca bağlam gider, zihin kalır" in flat


# -- "Train now" does not stay silent -----------------------------------
#
# The user pressed the button, nothing happened on screen. The truth: the
# loop started and within a second said "too little new data: 0/50" and
# exited. The result now returns WITH ITS REASON and the UI says it in one line.


def test_train_now_reports_why_it_did_not_start(tmp_path: Path) -> None:
    """A disabled feature, a missing setup and a lack of data are named
    separately — none of them is a silent "nothing happened"."""
    from dornick import recognition

    class _Hub:
        def emit(self, payload: dict) -> None:
            pass

    hub = _Hub()

    # While disabled: it is named.
    assert recognition.maybe_start(tmp_path, hub, force=True) == "kapali"

    recognition.configure(tmp_path, True)
    reason = recognition.maybe_start(tmp_path, hub, force=True)
    # If the setup is not installed it stops there; if it is, there is no
    # data to train on — both are a NAMED outcome, not silence.
    assert reason in ("duzenek_yok", "veri_yok")
    assert reason != "basladi", "boş veriyle koşu başlatılmamalı"


def test_the_ui_has_a_line_for_every_outcome() -> None:
    """Every reason code has a counterpart: the user must be able to read
    "why it did not happen". No code may fall silently."""
    APP_JS = (Path(__file__).resolve().parents[1]
              / "src" / "dornick" / "web" / "static" / "app.js").read_text(encoding="utf-8")
    for code in ("basladi", "veri_yok", "kosuyor", "duzenek_yok",
                 "kapali", "ara_yok", "baslatilamadi"):
        assert re.search(rf"\b{code}:", APP_JS), code
    # The pulse must show even on very short runs.
    assert re.search(r"const TRAINING_MIN_PULSE_MS = \d+", APP_JS)


def test_derived_session_titles_skip_one_letter_keystrokes() -> None:
    """Live wound: when the first message was accidentally a single letter
    ("e" + Enter) the chat was listed on the left under that letter. The
    derived title skips the crumb."""
    from dornick.web.server import _session_title

    assert _session_title(
        "e ev otomasyonu yapıyorum mock data ile"
    ) == "ev otomasyonu yapıyorum mock data ile"
    assert _session_title("b") == "b"          # if there is a single word it stays
    assert _session_title("2 sayı topla") == "2 sayı topla"  # a digit can be a title


def test_generated_titles_reject_single_letter_junk() -> None:
    """The small model sometimes returns junk ("e"); the weak filter made it
    the PERMANENT name, and once a name was written it was never generated again."""
    from dornick.loop import _title_valid

    assert not _title_valid("e")
    assert not _title_valid("")
    assert not _title_valid("----")
    assert not _title_valid("x" * 61)
    assert _title_valid("Ev otomasyonu simülasyonu")
    assert _title_valid("PLC taraması")


def test_goal_note_frames_the_ledger_as_reminder(tmp_path: Path, registry) -> None:
    """Live wound (31.08): the bare "Aktif hedefler" note read like an
    INSTRUCTION to the small model — to a user saying "selam yaz" the model
    replied by discussing the goal in the ledger. A priority frame is embedded
    in the note: the agenda is set by the user's last word."""
    from dornick.mind import open_mind

    agent = build_agent(tmp_path, FakeClient([]), registry)
    mind = open_mind(tmp_path / "mind", tmp_path / "sessions", "test")
    agent.mind = mind
    agent._last_goal_digest = ""
    agent.session.add_user_text("selam")
    mind.push_goal("pdf dönüşümü")

    agent._sync_goals()

    notes = [m for m in agent.session.messages() if m.get("role") == "system"]
    assert notes, "hedef notu hic yazilmadi"
    text = str(notes[-1].get("content"))
    assert "pdf dönüşümü" in text
    assert "talimat değil" in text
    assert "son sözü" in text


def test_soul_goal_block_carries_the_same_framing(tmp_path: Path) -> None:
    """The soul's goal block carries the same frame and does not say "from
    earlier sessions" — the ledger is now filtered per session, only the
    resumed chat's own items arrive here."""
    from dornick.mind import open_mind

    mind = open_mind(tmp_path / "mind", tmp_path / "sessions", "s1")
    mind.push_goal("ev otomasyonu simülasyonu")

    text = mind.soul().render()

    assert "ev otomasyonu simülasyonu" in text
    assert "talimat değil" in text
    assert "Önceki oturumlardan" not in text


def test_the_tree_carries_no_provider_keys() -> None:
    """Move to the single-folder layout (31.08): the key scan used to live in
    the publish-sync script; now that the code lives directly in the open
    repository the scan runs on every test run. If the OpenRouter/generic key
    pattern shows up in the tree the suite goes red — a leak cannot reach a push."""
    root = Path(__file__).resolve().parents[1]
    # REAL key length: short placeholders ("sk-ant-...", test fakes) are not
    # an alarm — documentation and fixtures are legitimate.
    pattern = re.compile(r"sk-or-v1-[0-9a-f]{60,}|sk-ant-[A-Za-z0-9_-]{60,}")
    skip = {".git", ".dornick", "atolye", "__pycache__", ".pytest_cache",
            "node_modules", "dist"}
    suspects: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file() or path.stat().st_size > 2_000_000:
            continue
        parts = set(path.relative_to(root).parts)
        if parts & skip:
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if pattern.search(content):
            suspects.append(str(path.relative_to(root)))
    assert not suspects, f"anahtar deseni tasiyan dosyalar: {suspects}"
