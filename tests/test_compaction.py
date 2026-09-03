"""Context-compaction tests.

Compaction can break in two separate places: cutting from the wrong place
and dropping the API to a 400 (an unanswered tool_use), and writing the
summary only to the context and forgetting to write it to the mind — the
second is silent, unnoticed until the session closes.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from dornick import compaction
from dornick.backends import TurnResult
from dornick.events import EventLog
from dornick.mind import open_mind
from dornick.session import Session
from tests.test_loop import FakeClient, build_agent, registry, text_turn  # noqa: F401


def user(text: str) -> dict:
    return {"role": "user", "content": [{"type": "text", "text": text}]}


def assistant(text: str) -> dict:
    return {"role": "assistant", "content": [{"type": "text", "text": text}]}


def results(*ids: str) -> dict:
    return {
        "role": "user",
        "content": [{"type": "tool_result", "tool_use_id": i, "content": "çıktı"} for i in ids],
    }


def fill(session: Session, turns: int = 8) -> None:
    for i in range(turns):
        session.add_user_text(f"soru {i}")
        session.add_assistant([{"type": "text", "text": f"cevap {i}"}])


# -- pressure measurement ----------------------------------------------


def test_pressure_uses_the_whole_prompt_not_the_leftover() -> None:
    """input_tokens counts only the residue that did not hit the cache; it
    stays small even when the window is full. Looking at it meant
    compaction never triggering."""
    usage = {"cache_read": 90_000, "cache_write": 0, "uncached": 200, "prompt_total": 90_200}
    assert compaction.measure(usage, 100_000).full


def test_empty_window_is_not_full() -> None:
    assert not compaction.measure({"prompt_total": 1_000}, 200_000).full
    assert compaction.measure({}, 200_000).percent == 0


def test_unknown_window_does_not_divide_by_zero() -> None:
    assert compaction.measure({"prompt_total": 5}, 0).ratio == 0.0


# -- cut point ---------------------------------------------------------


def test_cut_lands_on_a_real_user_turn() -> None:
    messages = [user("bir"), assistant("a"), user("iki"), assistant("b"),
                user("üç"), assistant("c"), user("dört"), assistant("d")]
    cut = compaction.cut_point(messages, keep=2)

    assert messages[cut]["role"] == "user"
    assert messages[cut]["content"][0]["text"] == "dört"


def test_cut_never_orphans_a_tool_use() -> None:
    """A user turn carrying a tool result is the continuation of an assistant
    turn. Cutting in front of it leaves an unanswered tool_use, which means a 400."""
    messages = [
        user("başla"),
        {"role": "assistant",
         "content": [{"type": "tool_use", "id": "t1", "name": "x", "input": {}}]},
        results("t1"),
        assistant("bitti"),
    ]
    # The only real user turn is the very first one; there is no safe cut point.
    assert compaction.cut_point(messages, keep=2) == 0


def test_short_conversation_is_not_cut() -> None:
    assert compaction.cut_point([user("a"), assistant("b")], keep=6) == 0


# -- transcript --------------------------------------------------------


def test_transcript_keeps_the_call_but_trims_the_output() -> None:
    messages = [
        {"role": "assistant",
         "content": [{"type": "tool_use", "id": "t1", "name": "shell",
                      "input": {"command": "ls"}}]},
        {"role": "user",
         "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "x" * 5_000}]},
    ]
    text = compaction.transcript(messages, tool_output_limit=100)

    assert "shell" in text and "ls" in text
    assert len(text) < 500
    assert "karakter" in text  # how much was dropped stays written


def test_thinking_never_reaches_the_summary() -> None:
    """What belongs in the summary is the conclusion reached, not the road taken."""
    messages = [{"role": "assistant", "content": [
        {"type": "thinking", "thinking": "gizli akıl yürütme", "signature": "s"},
        {"type": "text", "text": "cevap"}]}]

    text = compaction.transcript(messages)
    assert "cevap" in text and "gizli" not in text


# -- session projection ------------------------------------------------


def test_window_starts_at_the_summary_after_compaction(tmp_path: Path) -> None:
    session = Session(EventLog(tmp_path / "s.jsonl"), "test")
    fill(session)

    plan = session.compaction_plan(keep=4)
    assert plan is not None
    from_seq, transcript = plan
    assert "soru 0" in transcript

    session.compact("önceki konuşmanın özeti", from_seq)
    window = session.messages()

    assert window[0]["role"] == "user"
    assert "önceki konuşmanın özeti" in window[0]["content"][0]["text"]
    assert len(window) == 5  # summary + the 4 kept
    assert "soru 0" not in str(window)


def test_the_log_itself_is_never_shortened(tmp_path: Path) -> None:
    """The raw truth must stay on disk: extracting a past-session summary,
    hunting for errors and re-weaving the mind are all done from that file."""
    session = Session(EventLog(tmp_path / "s.jsonl"), "test")
    fill(session)
    before = len(session.log.messages())

    plan = session.compaction_plan(keep=4)
    assert plan is not None
    session.compact("özet", plan[0])

    assert len(session.log.messages()) == before
    assert len(session.messages()) < before


def test_compacting_twice_keeps_only_the_latest_horizon(tmp_path: Path) -> None:
    session = Session(EventLog(tmp_path / "s.jsonl"), "test")
    fill(session, turns=12)

    first = session.compaction_plan(keep=8)
    assert first is not None
    session.compact("ilk özet", first[0])

    session.add_user_text("yeni soru")
    session.add_assistant([{"type": "text", "text": "yeni cevap"}])
    second = session.compaction_plan(keep=2)
    assert second is not None
    session.compact("ikinci özet", second[0])

    window = session.messages()
    assert "ikinci özet" in window[0]["content"][0]["text"]
    assert "ilk özet" not in str(window)


# -- agent end to end --------------------------------------------------


def heavy_turn(window: int) -> TurnResult:
    """A turn that has nearly filled the window."""
    return TurnResult(
        message=SimpleNamespace(
            content=[{"type": "text", "text": "uzun cevap"}],
            stop_reason="end_turn",
            stop_details=None,
            usage=SimpleNamespace(
                input_tokens=int(window * 0.9),
                output_tokens=5,
                cache_read_input_tokens=0,
                cache_creation_input_tokens=0,
            ),
        )
    )


async def test_agent_compacts_instead_of_stopping(tmp_path: Path, registry) -> None:
    """Ending the conversation when the window fills cuts the user's work in half."""
    client = FakeClient(text_turn("özet metni"), heavy_turn(200_000))
    agent = build_agent(tmp_path, client, registry)
    fill(agent.session)
    agent._last_usage = {"prompt_total": 180_000}

    await agent.run("son soru")

    assert len(agent.session.log.notes("compacted")) == 1
    assert "soru 0" not in str(agent.session.messages())


async def test_the_summary_also_lands_in_the_mind(tmp_path: Path, registry) -> None:
    """Without writing to the mind compaction would be controlled forgetting:
    when the session closed the summary would go too."""
    client = FakeClient(text_turn("ÖZET: kullanıcı postgres yedeği istedi"))
    agent = build_agent(tmp_path, client, registry)
    agent.mind = open_mind(tmp_path / "mind", tmp_path / "sessions", "test")
    fill(agent.session)

    assert await agent._compact(reason="test")

    episodes = agent.mind.memories("episode")
    assert len(episodes) == 1
    assert "postgres" in episodes[0].content
    # And it must now come back by association.
    assert agent.mind.recall("postgres yedeği")


async def test_a_failed_summary_leaves_the_window_alone(tmp_path: Path, registry) -> None:
    """If the summary cannot be obtained, throwing history away would be plain data loss."""
    client = FakeClient(TurnResult(error="sunucuya ulaşılamadı"))
    agent = build_agent(tmp_path, client, registry)
    fill(agent.session)
    before = len(agent.session.messages())

    assert not await agent._compact(reason="test")
    assert len(agent.session.messages()) == before
    assert agent.session.log.notes("compact_failed")


async def test_force_horizon_when_compact_plan_is_empty(tmp_path: Path, registry) -> None:
    """Even with no turn to compact the horizon is drawn — the work does not stop."""
    client = FakeClient(text_turn("ok"))
    agent = build_agent(tmp_path, client, registry)
    agent.session.add_user_text("tek")
    agent.session.add_assistant([{"type": "text", "text": "yanıt"}])
    assert agent._force_horizon("test")
    assert agent.session.log.notes("compacted")


async def test_refresh_context_tries_tight_keep(tmp_path: Path, registry, monkeypatch) -> None:
    client = FakeClient(text_turn("özet"))
    agent = build_agent(tmp_path, client, registry)
    fill(agent.session, turns=3)
    seen: list[int | None] = []

    async def fake_compact(*, reason: str, keep: int | None = None):
        seen.append(keep)
        return keep == 2

    monkeypatch.setattr(agent, "_compact", fake_compact)
    assert await agent._refresh_context("test")
    assert None in seen and 2 in seen
