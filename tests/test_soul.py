"""Soul and system prompt tests.

The most critical one is `test_soul_stays_byte_identical_within_a_session`:
the soul is part of the system prompt; if it changes mid-session every cache
after it drops. This happens silently — only the bill grows.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dornick.config import Config
from dornick.context import ContextPolicy
from dornick.events import EventLog
from dornick.loop import Agent, AgentIO
from dornick.mind import Mind, open_mind
from dornick.prompt import build as build_prompt
from dornick.session import Session
from dornick.tools import build_registry

from .test_loop import FakeClient, text_turn


@pytest.fixture()
def mind(tmp_path: Path) -> Mind:
    return open_mind(tmp_path / "mind", tmp_path / "sessions", "cur")


# -- the soul's content ------------------------------------------------


def test_blank_soul_says_it_is_the_first_meeting(mind: Mind) -> None:
    rendered = mind.soul().render()
    assert "ilk kez" in rendered
    # Even with a blank mind it must say what to do.
    assert "mind_memory" in rendered


def test_blank_soul_wants_to_meet_the_user(mind: Mind) -> None:
    """The first meeting is short and confident: a single natural question
    (the name — and only if not given), no hardware inventory and no meta
    questions like "how should I address you". This directive lives in the
    soul so it drops out once the mind fills up."""
    rendered = mind.soul().render()
    assert "tanış" in rendered.lower()
    # The name is the one natural question — but not asked if already given in the conversation.
    assert "adını" in rendered and "söylemediyse" in rendered
    # Missing hardware is not listed at the first meeting; the form of address is not asked.
    assert "envanteri sayma" in rendered
    assert "hitap kalıbı sorulmaz" in rendered


def test_the_prompt_carries_the_senses(tmp_path: Path) -> None:
    """The agent must know whether it has a microphone, camera, voice without
    calling a tool — it draws the scene but does not see the scene."""
    config = Config.load(tmp_path)
    config.ensure_dirs()
    prompt = build_prompt(config, build_registry())
    assert "Duyuların:" in prompt.core
    # The organ label is in sentence case ("Mikrofon"); case-insensitive check.
    assert "mikrofon" in prompt.core.lower()


def test_the_prompt_names_saved_cameras(tmp_path: Path) -> None:
    """The agent must know the saved camera's name without calling a tool."""
    from dornick import watch

    config = Config.load(tmp_path)
    config.ensure_dirs()
    watch.save(config.state_dir, [
        watch.Camera(id="cam_1", name="bahçe", kind="rtsp", host="10.0.0.8"),
    ])
    prompt = build_prompt(config, build_registry())
    assert "bahçe" in prompt.core
    assert "Bilgisayar kamerası" in prompt.core
    assert "kamera action=yol" in prompt.core


def test_the_prompt_tells_the_model_its_permission_mode(tmp_path: Path) -> None:
    """The mode did not show in the prompt and the model took a mutation
    denied in plan mode for an error and retried. Even the default mode (ask)
    must be written — the model must know which gate it works behind."""
    config = Config.load(tmp_path)
    config.ensure_dirs()
    prompt = build_prompt(config, build_registry())
    assert "Yetki kipin: ask" in prompt.core


def test_plan_mode_carries_the_planning_contract(tmp_path: Path) -> None:
    """Plan mode is not just a gate but a way of working: explore, write a
    numbered plan, wait for approval — do not move to execution on your own."""
    config = Config.load(tmp_path)
    config.ensure_dirs()
    config.permissions.mode = "plan"

    prompt = build_prompt(config, build_registry())
    assert "PLANLAMAKTIR" in prompt.core
    assert "onayını bekleyerek dur" in prompt.core
    assert "kendiliğinden geçme" in prompt.core

    # The mode does not drop in the narrow window either: a small model that
    # does not know what to do in plan mode burns the turn bumping into the gate.
    config.model.context_window = 4096
    lean = build_prompt(config, build_registry())
    assert "PLANLAMAKTIR" in lean.core


def test_soul_carries_what_it_knows_about_the_user(mind: Mind) -> None:
    mind.remember("Fatih, SCADA sistemleri üzerine çalışıyor.", kind="user")
    mind.remember("Türkçe konuşmayı tercih ediyor.", kind="preference")
    mind.remember("Yol hapsi eklemek istemedi; izin motoru yeterli.", kind="lesson")

    rendered = mind.soul().render()

    assert "SCADA" in rendered
    assert "Türkçe" in rendered
    assert "izin motoru" in rendered


def test_procedures_expose_titles_only(mind: Mind) -> None:
    """Progressive disclosure: the detail goes to mind_recall, not the prompt."""
    mind.remember(
        "Adım adım çok uzun bir yordam metni burada duruyor.",
        kind="procedure",
        title="postgres yedeği alma",
    )
    rendered = mind.soul().render()

    assert "postgres yedeği alma" in rendered
    assert "çok uzun bir yordam" not in rendered
    assert "mind_recall" in rendered


def test_open_goals_from_earlier_sessions_survive(mind: Mind) -> None:
    done = mind.push_goal("biten iş")
    mind.set_goal_status(done.id, "done")
    mind.push_goal("yarım kalan iş")

    rendered = mind.soul().render()
    assert "yarım kalan iş" in rendered
    assert "biten iş" not in rendered


def test_soul_reports_shared_history(tmp_path: Path) -> None:
    sessions = tmp_path / "sessions"
    sessions.mkdir(parents=True)
    for stem in ("20260101T000000Z", "20260102T000000Z", "20260103T000000Z"):
        EventLog(sessions / f"{stem}.jsonl").close()

    mind = open_mind(tmp_path / "mind", sessions, "cur")
    mind.remember("bir şey", kind="user")

    rendered = mind.soul().render()
    assert "3 oturumdur" in rendered
    assert "2026-01-01" in rendered


def test_persona_file_is_folded_into_the_soul(tmp_path: Path) -> None:
    state = tmp_path / ".dornick"
    state.mkdir(parents=True)
    (state / "persona.md").write_text("Kısa ve teknik konuş.", encoding="utf-8")

    config = Config.load(tmp_path)
    mind = open_mind(config.mind_dir, config.sessions_dir, "cur")
    prompt = build_prompt(config, build_registry(mind), soul=mind.soul(persona="Kısa ve teknik konuş."))

    assert "Kısa ve teknik konuş." in prompt.identity
    assert "Kısa ve teknik konuş." not in prompt.core


def test_reconfigure_swaps_the_window_but_keeps_the_soul(tmp_path: Path, mind: Mind) -> None:
    """When the model changes (large → narrow window) the core must switch to
    lean but the soul must stay the same: identity learned mid-session must
    not be lost."""
    import dataclasses

    mind.remember("Kullanıcının adı Fatih.", kind="user")
    client = FakeClient(text_turn("tamam"))
    agent = _agent(tmp_path, mind, client)

    assert not agent.lean
    identity_before = agent._system.identity

    lean_model = dataclasses.replace(agent.config.model, context_window=4096, max_tokens=1024)
    agent.reconfigure(dataclasses.replace(agent.config, model=lean_model))

    assert agent.lean
    # The soul is byte-identical: the identity block and the user's name inside it are preserved.
    assert agent._system.identity == identity_before
    assert "Fatih" in agent._system.identity


# -- the system prompt's cache structure -------------------------------


def _agent(tmp_path: Path, mind: Mind, client: FakeClient) -> Agent:
    config = Config.load(tmp_path)
    config.ensure_dirs()
    return Agent(
        config=config,
        session=Session(EventLog(tmp_path / "s.jsonl"), "cur"),
        registry=build_registry(mind),
        client=client,  # type: ignore[arg-type]
        io=AgentIO(),
        policy=ContextPolicy(config.context),
        mind=mind,
    )


async def test_system_is_split_into_two_cached_blocks(tmp_path: Path, mind: Mind) -> None:
    mind.remember("Kullanıcı hakkında bir gözlem.", kind="user")
    client = FakeClient(text_turn("tamam"))
    agent = _agent(tmp_path, mind, client)

    await agent.run("selam")

    system = client.seen_system[0]
    assert len(system) == 2, "core and identity must be separate blocks"
    assert all(b.get("cache_control") for b in system), "both blocks must be cached"
    # The soul must sit BEHIND the core: in prefix matching the changing part stays at the end.
    assert "Kullanıcı hakkında bir gözlem." in system[1]["text"]


async def test_single_block_when_mind_is_absent(tmp_path: Path) -> None:
    config = Config.load(tmp_path)
    config.ensure_dirs()
    client = FakeClient(text_turn("tamam"))
    agent = Agent(
        config=config,
        session=Session(EventLog(tmp_path / "s.jsonl"), "cur"),
        registry=build_registry(),
        client=client,  # type: ignore[arg-type]
        io=AgentIO(),
        policy=ContextPolicy(config.context),
    )

    await agent.run("selam")
    assert len(client.seen_system[0]) == 1


async def test_soul_stays_byte_identical_within_a_session(tmp_path: Path, mind: Mind) -> None:
    """A memory saved mid-session must NOT CHANGE the system prompt.

    If it did, every new memory would drop the whole cache from that point
    on, and this would show up not as an error but only as a bill.
    """
    client = FakeClient(text_turn("bir"), text_turn("iki"))
    agent = _agent(tmp_path, mind, client)

    await agent.run("ilk istek")
    mind.remember("Oturum ortasında öğrenilen yeni bir şey.", kind="user")
    await agent.run("ikinci istek")

    # The session-title call's own short system slips in between: only the
    # MAIN prompts are compared — the byte contract is for them.
    main = [s for s in client.seen_system if s and "Dornick" in str(s[0].get("text", ""))[:40]]
    assert len(main) >= 2
    assert main[0] == main[1]
    # The new memory is not lost; it just enters the soul at the next open.
    assert "Oturum ortasında" in mind.soul().render()
