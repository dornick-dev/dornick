"""Bağlam sıkıştırma testleri.

Sıkıştırmanın iki ayrı yerde bozulma riski var: yanlış yerden kesip API'yi
400'e düşürmek (karşılıksız tool_use), ve özeti yalnızca bağlama yazıp
zihne yazmayı unutmak — ikincisi sessizdir, oturum kapanana kadar fark
edilmez.
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


# -- basınç ölçümü -----------------------------------------------------


def test_pressure_uses_the_whole_prompt_not_the_leftover() -> None:
    """input_tokens yalnızca önbelleğe girmemiş artığı sayar; pencere
    doluyken bile küçük kalır. Ona bakmak sıkıştırmanın hiç tetiklenmemesi
    demekti."""
    usage = {"cache_read": 90_000, "cache_write": 0, "uncached": 200, "prompt_total": 90_200}
    assert compaction.measure(usage, 100_000).full


def test_empty_window_is_not_full() -> None:
    assert not compaction.measure({"prompt_total": 1_000}, 200_000).full
    assert compaction.measure({}, 200_000).percent == 0


def test_unknown_window_does_not_divide_by_zero() -> None:
    assert compaction.measure({"prompt_total": 5}, 0).ratio == 0.0


# -- kesme noktası -----------------------------------------------------


def test_cut_lands_on_a_real_user_turn() -> None:
    messages = [user("bir"), assistant("a"), user("iki"), assistant("b"),
                user("üç"), assistant("c"), user("dört"), assistant("d")]
    cut = compaction.cut_point(messages, keep=2)

    assert messages[cut]["role"] == "user"
    assert messages[cut]["content"][0]["text"] == "dört"


def test_cut_never_orphans_a_tool_use() -> None:
    """Araç sonucu taşıyan kullanıcı turu bir asistan turunun devamıdır.
    Önünden kesmek karşılıksız tool_use bırakır, o da 400 demek."""
    messages = [
        user("başla"),
        {"role": "assistant",
         "content": [{"type": "tool_use", "id": "t1", "name": "x", "input": {}}]},
        results("t1"),
        assistant("bitti"),
    ]
    # Tek gerçek kullanıcı turu en baştaki; kesilecek güvenli nokta yok.
    assert compaction.cut_point(messages, keep=2) == 0


def test_short_conversation_is_not_cut() -> None:
    assert compaction.cut_point([user("a"), assistant("b")], keep=6) == 0


# -- döküm -------------------------------------------------------------


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
    assert "karakter" in text  # ne kadarının atıldığı yazılı kalıyor


def test_thinking_never_reaches_the_summary() -> None:
    """Özete girmesi gereken varılan sonuç, oraya varılan yol değil."""
    messages = [{"role": "assistant", "content": [
        {"type": "thinking", "thinking": "gizli akıl yürütme", "signature": "s"},
        {"type": "text", "text": "cevap"}]}]

    text = compaction.transcript(messages)
    assert "cevap" in text and "gizli" not in text


# -- oturum projeksiyonu -----------------------------------------------


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
    assert len(window) == 5  # özet + korunan 4
    assert "soru 0" not in str(window)


def test_the_log_itself_is_never_shortened(tmp_path: Path) -> None:
    """Ham gerçek diskte kalmalı: geçmiş oturum özeti çıkarmak, hata aramak
    ve zihni yeniden örmek hep o dosyadan yapılıyor."""
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


# -- ajan uçtan uca ----------------------------------------------------


def heavy_turn(window: int) -> TurnResult:
    """Pencereyi neredeyse doldurmuş bir tur."""
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
    """Pencere dolduğunda konuşmayı bitirmek kullanıcının işini böler."""
    client = FakeClient(text_turn("özet metni"), heavy_turn(200_000))
    agent = build_agent(tmp_path, client, registry)
    fill(agent.session)
    agent._last_usage = {"prompt_total": 180_000}

    await agent.run("son soru")

    assert len(agent.session.log.notes("compacted")) == 1
    assert "soru 0" not in str(agent.session.messages())


async def test_the_summary_also_lands_in_the_mind(tmp_path: Path, registry) -> None:
    """Zihne yazılmasaydı sıkıştırma kontrollü bir unutma olurdu: oturum
    kapandığında özet de giderdi."""
    client = FakeClient(text_turn("ÖZET: kullanıcı postgres yedeği istedi"))
    agent = build_agent(tmp_path, client, registry)
    agent.mind = open_mind(tmp_path / "mind", tmp_path / "sessions", "test")
    fill(agent.session)

    assert await agent._compact(reason="test")

    episodes = agent.mind.memories("episode")
    assert len(episodes) == 1
    assert "postgres" in episodes[0].content
    # Ve artık çağrışımla geri gelebilmeli.
    assert agent.mind.recall("postgres yedeği")


async def test_a_failed_summary_leaves_the_window_alone(tmp_path: Path, registry) -> None:
    """Özet alınamazsa geçmişi atmak düpedüz veri kaybı olurdu."""
    client = FakeClient(TurnResult(error="sunucuya ulaşılamadı"))
    agent = build_agent(tmp_path, client, registry)
    fill(agent.session)
    before = len(agent.session.messages())

    assert not await agent._compact(reason="test")
    assert len(agent.session.messages()) == before
    assert agent.session.log.notes("compact_failed")


async def test_force_horizon_when_compact_plan_is_empty(tmp_path: Path, registry) -> None:
    """Sıkıştıracak tur yoksa bile ufuk çekilir — iş durmaz."""
    client = FakeClient(text_turn("ok"))
    agent = build_agent(tmp_path, client, registry)
    agent.session.add_user_text("tek")
    agent.session.add_assistant([{"type": "text", "text": "yanıt"}])
    assert agent._force_horizon("test")
    assert agent.session.log.notes("compacted")


async def test_yenile_baglam_tries_tight_keep(tmp_path: Path, registry, monkeypatch) -> None:
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
