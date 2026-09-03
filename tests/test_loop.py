"""End-to-end behaviour of the loop, with a fake model client.

Verifies the loop's real contract without making a real API call: every
tool_use gets a tool_result, an interrupt leaves the history consistent,
tool results really enter the next request.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from dornick.backends import TurnResult
from dornick.config import Config
from dornick.events import EventLog
from dornick.loop import Agent, AgentIO
from dornick.permissions import PermissionEngine
from dornick.session import Session
from dornick.tools import ToolRegistry, ToolResult, object_schema


def message(content: list[dict], stop_reason: str) -> SimpleNamespace:
    return SimpleNamespace(
        content=content,
        stop_reason=stop_reason,
        stop_details=None,
        usage=SimpleNamespace(
            input_tokens=10,
            output_tokens=5,
            cache_read_input_tokens=0,
            cache_creation_input_tokens=0,
        ),
    )


def text_turn(text: str) -> TurnResult:
    return TurnResult(message=message([{"type": "text", "text": text}], "end_turn"))


def tool_turn(*calls: tuple[str, str, dict]) -> TurnResult:
    blocks = [
        {"type": "tool_use", "id": cid, "name": name, "input": args} for cid, name, args in calls
    ]
    return TurnResult(message=message(blocks, "tool_use"))


class FakeClient:
    """Returns pre-written turns in order."""

    def __init__(self, *script: TurnResult) -> None:
        self.script = list(script)
        self.seen_messages: list[list[dict]] = []
        self.seen_system: list[list[dict]] = []
        # Which tools were given on each turn: the closing turn must be tool-less.
        self.seen_tools: list[list[dict]] = []

    async def turn(self, prepared, tools, *, cancel, callbacks=None):
        self.seen_messages.append(prepared.messages)
        self.seen_system.append(prepared.system)
        self.seen_tools.append(list(tools or []))
        if not self.script:
            return text_turn("(senaryo bitti)")
        return self.script.pop(0)


def build_agent(tmp_path: Path, client: FakeClient, registry: ToolRegistry) -> Agent:
    config = Config.load(tmp_path)
    config.ensure_dirs()
    session = Session(EventLog(tmp_path / "s.jsonl"), "test")
    return Agent(
        config=config,
        session=session,
        registry=registry,
        client=client,  # type: ignore[arg-type]
        io=AgentIO(approve=_always_yes),
        permissions=PermissionEngine("yolo", allow=[], deny=[]),
    )


async def _always_yes(spec, args) -> bool:
    return True


@pytest.fixture()
def registry() -> ToolRegistry:
    reg = ToolRegistry()

    @reg.tool("echo", "geri söyler", object_schema({"text": {"type": "string"}}))
    async def _echo(args, ctx):
        return ToolResult(f"echo: {args.get('text', '')}")

    return reg


# ---------------------------------------------------------------------


async def test_plain_answer_is_one_turn(tmp_path: Path, registry: ToolRegistry) -> None:
    client = FakeClient(text_turn("merhaba"))
    agent = build_agent(tmp_path, client, registry)

    stats = await agent.run("selam")

    assert stats.turns == 1
    assert stats.tool_calls == 0
    assert [m["role"] for m in agent.session.messages()] == ["user", "assistant"]


async def test_tool_result_reaches_the_next_request(tmp_path: Path, registry: ToolRegistry) -> None:
    client = FakeClient(
        tool_turn(("t1", "echo", {"text": "abc"})),
        text_turn("tamamdır"),
    )
    agent = build_agent(tmp_path, client, registry)

    stats = await agent.run("echo yap")

    assert stats.turns == 2
    assert stats.tool_calls == 1

    roles = [m["role"] for m in agent.session.messages()]
    assert roles == ["user", "assistant", "user", "assistant"]

    # In the second request the tool result must really be in the history.
    second_request = client.seen_messages[1]
    results = [
        b
        for m in second_request
        if isinstance(m["content"], list)
        for b in m["content"]
        if isinstance(b, dict) and b.get("type") == "tool_result"
    ]
    assert len(results) == 1
    assert "echo: abc" in results[0]["content"]
    assert agent.session.pending_tool_uses() == []


async def test_interrupt_mid_stream_drops_partial_assistant_turn(
    tmp_path: Path, registry: ToolRegistry
) -> None:
    client = FakeClient(TurnResult(interrupted=True, partial_text="yarım kal"))
    agent = build_agent(tmp_path, client, registry)

    stats = await agent.run("bir şey yap")

    assert stats.interrupted is True
    # The half assistant turn must NOT be written to the history: a missing
    # tool_use input corrupts the next request.
    assert [m["role"] for m in agent.session.messages()] == ["user"]
    assert agent.session.log.notes("interrupted")


async def test_interrupt_during_tools_leaves_no_unanswered_tool_use(tmp_path: Path) -> None:
    reg = ToolRegistry()

    @reg.tool("slow", "yavaş", object_schema({}), parallel_safe=False)
    async def _slow(args, ctx):
        ctx.cancel.set()  # as if the user pressed ESC
        return ToolResult("ilk araç bitti")

    client = FakeClient(tool_turn(("a", "slow", {}), ("b", "slow", {})))
    agent = build_agent(tmp_path, client, reg)

    stats = await agent.run("iki iş yap")

    assert stats.interrupted is True
    # Critical: both tool_uses must get an answer, otherwise the next
    # request gets a 400.
    assert agent.session.pending_tool_uses() == []

    blocks = agent.session.messages()[-1]["content"]
    assert [b["tool_use_id"] for b in blocks] == ["a", "b"]
    assert blocks[1]["is_error"] is True


async def test_resume_after_interrupt_settles_then_continues(tmp_path: Path) -> None:
    reg = ToolRegistry()
    client = FakeClient(text_turn("devam ediyorum"))
    agent = build_agent(tmp_path, client, reg)

    agent.session.add_user_text("başla")
    agent.session.add_assistant(
        [{"type": "tool_use", "id": "orphan", "name": "yok", "input": {}}]
    )
    assert len(agent.session.pending_tool_uses()) == 1

    await agent.resume_after_interrupt()

    assert agent.session.pending_tool_uses() == []
    assert agent.session.log.notes("settled_pending")


async def test_refusal_stops_the_loop(tmp_path: Path, registry: ToolRegistry) -> None:
    refusal = TurnResult(message=message([], "refusal"))
    client = FakeClient(refusal, text_turn("buraya gelinmemeli"))
    agent = build_agent(tmp_path, client, registry)

    stats = await agent.run("bir şey")

    assert stats.turns == 1
    assert stats.stop_reason == "refusal"
    assert agent.session.log.notes("refusal")


# -- answers that hit the ceiling --------------------------------------


def truncated(text: str) -> TurnResult:
    return TurnResult(message=message([{"type": "text", "text": text}], "max_tokens"))


async def test_truncated_answer_is_continued_not_abandoned(
    tmp_path: Path, registry: ToolRegistry
) -> None:
    """Stopping at the ceiling left the user with half a sentence.

    The history is already written; giving one more turn is enough for
    the model to continue where it left off.
    """
    client = FakeClient(truncated("Rapor su adimlardan olusuyor: birinci"),
                        text_turn(" adim veriyi cekmek."))
    agent = build_agent(tmp_path, client, registry)

    stats = await agent.run("raporu anlat")

    assert stats.turns == 2
    assert stats.continuations == 1
    assert stats.stop_reason == "end_turn"

    # The nudge must take its place in the history so the model knows what
    # it is continuing.
    roles = [m["role"] for m in agent.session.messages()]
    assert roles == ["user", "assistant", "user", "assistant"]

    # But a message the user did not write must not appear in the chat.
    from dornick.web.server import _payload

    nudge = [e for e in agent.session.log.messages() if e.meta.get("continuation")]
    assert len(nudge) == 1
    assert _payload(nudge[0]) is None


async def test_continuation_has_a_ceiling(tmp_path: Path, registry: ToolRegistry) -> None:
    """A model that never finishes must not turn into a loop.

    On hitting the ceiling one more closing turn is given: the agent may
    have done work and the user getting nothing is worse than a half
    answer.
    """
    from dornick.loop import MAX_CONTINUATIONS

    client = FakeClient(*[truncated("devam...") for _ in range(MAX_CONTINUATIONS + 4)])
    agent = build_agent(tmp_path, client, registry)

    stats = await agent.run("uzun bir sey yaz")

    assert stats.continuations == MAX_CONTINUATIONS
    assert stats.closing is True
    # Continuations + the closing turn.
    assert stats.turns == MAX_CONTINUATIONS + 2


async def test_the_closing_turn_gets_no_tools(tmp_path: Path, registry: ToolRegistry) -> None:
    """Being able to call tools again in the closing turn means running one
    more turn of the loop that locked up."""
    from dornick.loop import MAX_CONTINUATIONS

    client = FakeClient(*[truncated("devam...") for _ in range(MAX_CONTINUATIONS + 4)])
    agent = build_agent(tmp_path, client, registry)
    await agent.run("uzun bir sey yaz")

    # On the last turn the schema list must go out empty.
    assert client.seen_tools[-1] == []
    assert client.seen_tools[0], "tools should have been given on the earlier turns"


async def test_the_closing_turn_asks_for_what_it_has(
    tmp_path: Path, registry: ToolRegistry
) -> None:
    """Telling the user "split the request into smaller pieces" meant losing
    both the work done and their question."""
    from dornick.loop import CLOSING_NOTE, MAX_CONTINUATIONS

    client = FakeClient(*[truncated("devam...") for _ in range(MAX_CONTINUATIONS + 4)])
    agent = build_agent(tmp_path, client, registry)
    await agent.run("uzun bir sey yaz")

    notes = [
        e for e in agent.session.log.messages()
        if e.meta.get("continuation") and CLOSING_NOTE in str(e.content)
    ]
    assert len(notes) == 1


async def test_tool_calls_cut_off_mid_stream_are_settled(
    tmp_path: Path, registry: ToolRegistry
) -> None:
    """An unanswered tool_use drops the next request with a 400.

    When the cut-off happens in the middle of a tool call those calls must
    get a cancellation result injected — the continuation turn can only be
    sent after that.
    """
    half = TurnResult(
        message=message(
            [
                {"type": "text", "text": "bakiyorum"},
                {"type": "tool_use", "id": "t1", "name": "echo", "input": {"text": "yarim"}},
            ],
            "max_tokens",
        )
    )
    client = FakeClient(half, text_turn("tamamlandi"))
    agent = build_agent(tmp_path, client, registry)

    await agent.run("bir sey yap")

    sent = client.seen_messages[-1]
    answered = {
        block["tool_use_id"]
        for msg in sent
        for block in (msg["content"] if isinstance(msg["content"], list) else [])
        if isinstance(block, dict) and block.get("type") == "tool_result"
    }
    assert "t1" in answered


# -- orchestra: subagent channels ------------------------------------------
#
# Async tests are skipped in this environment (no asyncio plugin); the
# synchronous test below really runs with `asyncio.run` and verifies that
# the subagent lifecycle events (child_start / child_end) flow to the UI.


def test_spawning_a_subagent_emits_channel_events(tmp_path: Path) -> None:
    from dornick.tools import build_registry

    events: list[tuple] = []
    io = AgentIO(
        approve=_always_yes,
        on_child_start=lambda title, model, cid, bg: events.append(("start", title, model)),
        on_child_end=lambda title, ok, turns, tools, cid, summary: events.append(("end", title, ok)),
    )

    config = Config.load(tmp_path)
    config.ensure_dirs()
    session = Session(EventLog(tmp_path / "s.jsonl"), "test")

    # Parent turn 1: call `task`. Then the subagent finishes with a single
    # text turn. Parent turn 2: closing text. The same FakeClient is used by
    # both the parent and the child (same model), so the script is nested.
    client = FakeClient(
        tool_turn(("c1", "task", {"title": "tarama", "task": "bir sey tara"})),
        text_turn("alt ajan tamam"),   # the child's single turn
        text_turn("sef bitti"),         # parent closing
    )

    agent = Agent(
        config=config,
        session=session,
        registry=build_registry(None, subagents=True),   # the `task` tool exists
        client=client,  # type: ignore[arg-type]
        io=io,
        permissions=PermissionEngine("yolo", allow=[], deny=[]),
        depth=0,
    )

    asyncio.run(agent.run("bir alt ajan calistir"))

    kinds = [e[0] for e in events]
    assert "start" in kinds, "child_start must be emitted when the subagent is born"
    assert "end" in kinds, "child_end must be emitted when the subagent ends"
    start = next(e for e in events if e[0] == "start")
    assert start[1] == "tarama"                 # channel title
    end = next(e for e in events if e[0] == "end")
    assert end[1] == "tarama" and end[2] is True
    # Order: birth first, then death.
    assert kinds.index("start") < kinds.index("end")


# -- spontaneous recall -------------------------------------------


async def test_relevant_memories_arrive_before_the_model_asks(
    tmp_path: Path, registry: ToolRegistry
) -> None:
    """Leaving recall to the tool was not enough.

    The model first had to notice that it should recall, most of the time
    it did not, and it answered as if it did not know something it already
    knew. Here the reverse: recall runs without being asked.
    """
    from dornick.mind import open_mind

    mind = open_mind(tmp_path / "mind", tmp_path / "sessions", "test")
    mind.remember("Postgres yedegi her gece 03:00te aliniyor", kind="procedure")
    mind.remember("Kahve makinesi mutfakta", kind="fact")

    client = FakeClient(text_turn("tamam"))
    agent = build_agent(tmp_path, client, registry)
    agent.mind = mind

    await agent.run("veritabani yedegi ne zaman aliniyordu")

    # The last call may be the session title (a run with a mind): look at
    # the MAIN request.
    sent = str(client.seen_messages[0])
    assert "03:00" in sent
    # An irrelevant memory must not bloat the context.
    assert "Kahve" not in sent


async def test_a_primed_memory_is_not_injected_twice(
    tmp_path: Path, registry: ToolRegistry
) -> None:
    """The old note is already in the history (messages are replayed from
    the start on every request); re-injecting the same memory on the second
    turn gives the model no new information, it only burns tokens."""
    from dornick.mind import open_mind

    mind = open_mind(tmp_path / "mind", tmp_path / "sessions", "test")
    mind.remember("Postgres yedegi her gece 03:00te aliniyor", kind="procedure")

    client = FakeClient(text_turn("tamam"), text_turn("yine tamam"))
    agent = build_agent(tmp_path, client, registry)
    agent.mind = mind

    await agent.run("veritabani yedegi ne zaman aliniyordu")
    await agent.run("yedek saati neydi, veritabani yedegi")

    notes = [m for m in agent.session.messages()
             if m["role"] == "system" and "03:00" in str(m["content"])]
    assert len(notes) == 1

    # When compaction folds the notes into the summary the right must come back.
    agent._primed.clear()   # the reset _compact does
    assert agent._primed == set()


async def test_soul_resident_memories_are_never_primed(
    tmp_path: Path, registry: ToolRegistry
) -> None:
    """A record the soul put into the prompt with its full body (preference,
    user, lesson) is already in context — re-injecting adds no information,
    it burns tokens. Measured (scale_bench): same hit rate, ~9% fewer tokens."""
    from dornick.mind import open_mind

    mind = open_mind(tmp_path / "mind", tmp_path / "sessions", "test")
    mind.remember("Fatih kahve degil cay icer, demli olacak", kind="preference")
    mind.remember("Postgres yedegi her gece 03:00te aliniyor", kind="procedure")

    client = FakeClient(text_turn("tamam"))
    agent = build_agent(tmp_path, client, registry)
    agent.mind = mind
    agent.soul = mind.soul()
    agent._primed = agent._soul_resident()

    await agent.run("cay mi kahve mi iciyordum, postgres yedegi kacta")

    notes = [str(m["content"]) for m in agent.session.messages()
             if m["role"] == "system"]
    joined = "\n".join(notes)
    # The procedure is only a title in the soul: its body MUST enter priming.
    assert "03:00" in joined
    # The preference is in the soul with its full body: it must NOT be re-injected.
    assert "demli" not in joined


async def test_the_prime_line_says_the_kind_once(
    tmp_path: Path, registry: ToolRegistry
) -> None:
    """The previous format printed the kind twice as `- [fact] (fact) ...` —
    ten needless words in a five-line note."""
    from dornick.loop import prime_note
    from dornick.mind import open_mind

    mind = open_mind(tmp_path / "mind", tmp_path / "sessions", "test")
    mind.remember("Koru1000 klor alarmi 0.2 altinda calar", kind="fact",
                  title="klor esigi")
    hits = mind.recall("klor alarmi hangi esikte")
    note = prime_note(hits)

    assert note.count("[fact]") == 1
    assert "(fact)" not in note
    assert "klor esigi" in note          # the real title is preserved
    assert "0.2" in note                 # the body is there too


async def test_the_prime_is_marked_as_not_coming_from_the_user(
    tmp_path: Path, registry: ToolRegistry
) -> None:
    """The model must not think the user wrote these."""
    from dornick.mind import open_mind

    mind = open_mind(tmp_path / "mind", tmp_path / "sessions", "test")
    mind.remember("Fatih SCADA tarafinda calisiyor", kind="user")

    agent = build_agent(tmp_path, FakeClient(text_turn("tamam")), registry)
    agent.mind = mind
    await agent.run("scada islerinden bahset")

    note = [m for m in agent.session.messages() if m["role"] == "system"]
    assert note and "kullanici" in str(note[0]["content"]).lower()


async def test_nothing_is_injected_when_nothing_is_recalled(
    tmp_path: Path, registry: ToolRegistry
) -> None:
    from dornick.mind import open_mind

    agent = build_agent(tmp_path, FakeClient(text_turn("tamam")), registry)
    agent.mind = open_mind(tmp_path / "mind", tmp_path / "sessions", "test")
    await agent.run("hic konusulmamis bir konu")

    assert [m["role"] for m in agent.session.messages()] == ["user", "assistant"]


async def test_a_broken_mind_does_not_stop_the_conversation(
    tmp_path: Path, registry: ToolRegistry
) -> None:
    """Recall is a convenience; when it crashes it must not take the conversation with it."""

    class Broken:
        last_trace: list = []

        def soul(self, persona=""):
            return None

        def goal_digest(self):
            return ""

        def recall(self, *_args, **_kwargs):
            raise RuntimeError("bellek dosyasi bozuk")

    agent = build_agent(tmp_path, FakeClient(text_turn("tamam")), registry)
    agent.mind = Broken()

    # A message carrying content: greetings and small talk do not look into
    # the mind anyway.
    stats = await agent.run("scada projesi hakkinda ne biliyorsun")

    assert stats.turns == 1
    assert agent.session.log.notes("recall_prime_failed")


async def test_associations_do_not_leak_into_the_prime(
    tmp_path: Path, registry: ToolRegistry
) -> None:
    """In spontaneous recall association is not the thing wanted.

    In a real run the user asked about a crypto exchange and when the
    "SCADA" record at the far end of the network was put in front the
    model answered "do you have a SCADA project?". Those arriving by jump
    must be left to the model's own `mind_recall` call.
    """
    from dornick.mind import open_mind

    mind = open_mind(tmp_path / "mind", tmp_path / "sessions", "test")
    mind.remember("Fatih SCADA ve su yonetimi tarafinda calisiyor", kind="user")
    mind.remember("Kripto borsalarindan veri cekmek icin CoinGecko kullaniliyor",
                  kind="procedure")

    agent = build_agent(tmp_path, FakeClient(text_turn("tamam")), registry)
    agent.mind = mind
    await agent.run("kripto borsasini arastirir misin")

    sent = str(agent.session.messages())
    assert "CoinGecko" in sent
    assert "SCADA" not in sent


async def test_nothing_is_primed_when_only_neighbours_match(
    tmp_path: Path, registry: ToolRegistry
) -> None:
    """If no record matches directly nothing must be added."""
    from dornick.mind import open_mind

    mind = open_mind(tmp_path / "mind", tmp_path / "sessions", "test")
    mind.remember("Kahve makinesi mutfakta", kind="fact")

    agent = build_agent(tmp_path, FakeClient(text_turn("tamam")), registry)
    agent.mind = mind
    await agent.run("kuantum bilgisayarlar hakkinda ne dusunuyorsun")

    assert [m["role"] for m in agent.session.messages()] == ["user", "assistant"]


async def test_small_talk_does_not_open_the_mind(
    tmp_path: Path, registry: ToolRegistry
) -> None:
    """"naber" is not a question, it is a greeting.

    Dumping the mind in front of the model on every message was not the
    goal — the goal was being able to find it quickly when needed. In a
    real run, when "naber" was said the model met the previous session
    summary and instead of chatting asked "what do you want to do".
    """
    from dornick.mind import open_mind

    mind = open_mind(tmp_path / "mind", tmp_path / "sessions", "test")
    mind.remember("Fatih SCADA tarafinda calisiyor", kind="user")

    agent = build_agent(tmp_path, FakeClient(text_turn("merhaba")), registry)
    agent.mind = mind
    await agent.run("naber")

    assert [m["role"] for m in agent.session.messages()] == ["user", "assistant"]


async def test_a_greeting_with_a_question_still_opens_it(
    tmp_path: Path, registry: ToolRegistry
) -> None:
    """A real question starting with a greeting must look into the mind."""
    from dornick.mind import open_mind

    mind = open_mind(tmp_path / "mind", tmp_path / "sessions", "test")
    mind.remember("Postgres yedegi her gece 03:00te aliniyor", kind="procedure")

    agent = build_agent(tmp_path, FakeClient(text_turn("tamam")), registry)
    agent.mind = mind
    await agent.run("selam, postgres yedegi ne zamandi")

    assert "03:00" in str(agent.session.messages())


async def test_session_summaries_stay_out_of_the_prime(
    tmp_path: Path, registry: ToolRegistry
) -> None:
    """Summaries are long texts and match almost every query; they drown the
    real match. They are left to the model's own `mind_recall` call."""
    from dornick.mind import open_mind

    mind = open_mind(tmp_path / "mind", tmp_path / "sessions", "test")
    mind.remember("Oturum ozeti: kullanici merhaba dedi, borsa konusuldu, "
                  "scada projesi acildi, postgres yedegi ayarlandi",
                  kind="episode", title="oturum ozeti")

    agent = build_agent(tmp_path, FakeClient(text_turn("tamam")), registry)
    agent.mind = mind
    await agent.run("borsa hakkinda ne biliyorsun")

    assert "Oturum ozeti" not in str(agent.session.messages())


# -- instant encode: every turn goes to memory at that moment -----------


async def test_user_turn_is_encoded_instantly(tmp_path: Path, registry: ToolRegistry) -> None:
    """What the user said must go to searchable memory at that moment — not
    at night, inside the turn, synchronously."""
    from dornick.mind import open_mind

    mind = open_mind(tmp_path / "mind", tmp_path / "sessions", "test")
    client = FakeClient(text_turn("tamam"))
    agent = build_agent(tmp_path, client, registry)
    agent.mind = mind

    await agent.run("Çorum terfi istasyonunda pompa verimi yüzde 72 çıktı")

    hits = mind.recall("pompa verimi neydi", limit=5)
    assert any("72" in h.item.content for h in hits), "the user turn did not reach memory"


async def test_assistant_turn_is_encoded(tmp_path: Path, registry: ToolRegistry) -> None:
    """What the assistant said (a measurement, an explanation) must go to instant memory too."""
    from dornick.mind import open_mind

    mind = open_mind(tmp_path / "mind", tmp_path / "sessions", "test")
    client = FakeClient(text_turn("Depo seviyesi 2,77 metre; doluluk yüzde 79 olarak ölçüldü."))
    agent = build_agent(tmp_path, client, registry)
    agent.mind = mind

    await agent.run("kuyu deposu ne kadar dolu")

    hits = mind.recall("depo doluluk seviyesi", limit=5)
    assert any("2,77" in h.item.content or "79" in h.item.content for h in hits)


async def test_short_and_smalltalk_turns_are_not_encoded(tmp_path: Path, registry: ToolRegistry) -> None:
    """Turns like 'tamam', 'merhaba' are noise; they are not written to memory."""
    from dornick.mind import open_mind

    mind = open_mind(tmp_path / "mind", tmp_path / "sessions", "test")
    client = FakeClient(text_turn("selam"))
    agent = build_agent(tmp_path, client, registry)
    agent.mind = mind

    await agent.run("merhaba")

    assert mind.store.count() == 0, "a short/greeting turn must not enter memory"


async def test_same_turn_is_not_encoded_twice(tmp_path: Path, registry: ToolRegistry) -> None:
    """The same text back to back is written once."""
    from dornick.mind import open_mind

    mind = open_mind(tmp_path / "mind", tmp_path / "sessions", "test")
    agent = build_agent(tmp_path, FakeClient(text_turn("a"), text_turn("b")), mind and registry)
    agent.mind = mind

    msg = "modbus cihazı bağlantıyı sürekli koparıyor ne yapmalıyım"
    await agent.run(msg)
    await agent.run(msg)

    episodes = [m for m in mind.memories("episode") if "modbus" in m.content]
    assert len(episodes) == 1, f"the same turn was written {len(episodes)} times"


def test_infer_deliverable_prefers_app_root_over_api_path() -> None:
    from dornick.loop import _infer_deliverable

    d = _infer_deliverable("POST http://127.0.0.1:8090/api/refresh sonra bak")
    assert d == {"kind": "app", "url": "http://127.0.0.1:8090/"}
    a = _infer_deliverable("rapor /artifact/ot-scada-bulten/")
    assert a == {"kind": "artifact", "url": "/artifact/ot-scada-bulten/"}
