"""Ruh ve sistem promptu testleri.

En kritik olanı `test_soul_stays_byte_identical_within_a_session`: ruh
sistem promptunun parçası, oturum ortasında değişirse ondan sonraki tüm
önbellek düşer. Bu sessizce olur — sadece fatura büyür.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from neocp.config import Config
from neocp.context import ContextPolicy
from neocp.events import EventLog
from neocp.loop import Agent, AgentIO
from neocp.mind import Mind, open_mind
from neocp.prompt import build as build_prompt
from neocp.session import Session
from neocp.tools import build_registry

from .test_loop import FakeClient, text_turn


@pytest.fixture()
def mind(tmp_path: Path) -> Mind:
    return open_mind(tmp_path / "mind", tmp_path / "sessions", "cur")


# -- ruhun içeriği -----------------------------------------------------


def test_blank_soul_says_it_is_the_first_meeting(mind: Mind) -> None:
    rendered = mind.soul().render()
    assert "ilk kez" in rendered
    # Boş zihinde bile ne yapması gerektiğini söylemeli.
    assert "mind_memory" in rendered


def test_blank_soul_wants_to_meet_the_user(mind: Mind) -> None:
    """İlk karşılaşma kısa ve kendinden emin: tek doğal soru (ad — o da
    verilmemişse), donanım envanteri ve "nasıl hitap edeyim" gibi meta
    sorular yok. Bu yönerge ruhta duruyor ki zihin dolunca düşsün."""
    rendered = mind.soul().render()
    assert "tanış" in rendered.lower()
    # Ad tek doğal soru — ama konuşmada zaten verilmişse sorulmaz.
    assert "adını" in rendered and "söylemediyse" in rendered
    # Eksik donanım tanışmada sayılmaz; hitap kalıbı sorulmaz.
    assert "envanteri sayma" in rendered
    assert "hitap kalıbı sorulmaz" in rendered


def test_the_prompt_carries_the_senses(tmp_path: Path) -> None:
    """Ajan mikrofonu, kamerası, sesi olup olmadığını araç çağırmadan
    bilmeli — sahne çiziyor ama ajan sahneyi görmüyor."""
    config = Config.load(tmp_path)
    config.ensure_dirs()
    prompt = build_prompt(config, build_registry())
    assert "Duyuların:" in prompt.core
    # Organ etiketi Cümle düzeninde ("Mikrofon"); büyük/küçük harften bağımsız.
    assert "mikrofon" in prompt.core.lower()


def test_soul_carries_what_it_knows_about_the_user(mind: Mind) -> None:
    mind.remember("Fatih, SCADA sistemleri üzerine çalışıyor.", kind="user")
    mind.remember("Türkçe konuşmayı tercih ediyor.", kind="preference")
    mind.remember("Yol hapsi eklemek istemedi; izin motoru yeterli.", kind="lesson")

    rendered = mind.soul().render()

    assert "SCADA" in rendered
    assert "Türkçe" in rendered
    assert "izin motoru" in rendered


def test_procedures_expose_titles_only(mind: Mind) -> None:
    """Kademeli açığa çıkarma: detay prompta değil, mind_recall'a."""
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
    state = tmp_path / ".neocp"
    state.mkdir(parents=True)
    (state / "persona.md").write_text("Kısa ve teknik konuş.", encoding="utf-8")

    config = Config.load(tmp_path)
    mind = open_mind(config.mind_dir, config.sessions_dir, "cur")
    prompt = build_prompt(config, build_registry(mind), soul=mind.soul(persona="Kısa ve teknik konuş."))

    assert "Kısa ve teknik konuş." in prompt.identity
    assert "Kısa ve teknik konuş." not in prompt.core


def test_reconfigure_swaps_the_window_but_keeps_the_soul(tmp_path: Path, mind: Mind) -> None:
    """Model değişince (büyük → dar pencere) çekirdek lean'e dönmeli ama
    ruh aynı kalmalı: oturum ortasında öğrenilen kimlik kaybolmamalı."""
    import dataclasses

    mind.remember("Kullanıcının adı Fatih.", kind="user")
    client = FakeClient(text_turn("tamam"))
    agent = _agent(tmp_path, mind, client)

    assert not agent.lean
    identity_before = agent._system.identity

    lean_model = dataclasses.replace(agent.config.model, context_window=4096, max_tokens=1024)
    agent.reconfigure(dataclasses.replace(agent.config, model=lean_model))

    assert agent.lean
    # Ruh birebir aynı: kimlik bloğu ve içindeki kullanıcı adı korunuyor.
    assert agent._system.identity == identity_before
    assert "Fatih" in agent._system.identity


# -- sistem promptunun önbellek yapısı ---------------------------------


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
    assert len(system) == 2, "core ve identity ayrı bloklar olmalı"
    assert all(b.get("cache_control") for b in system), "iki blok da önbelleklenmeli"
    # Ruh core'un ARKASINDA olmalı: önek eşleşmesinde değişen parça sonda durur.
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
    """Oturum ortasında kaydedilen hatıra sistem promptunu DEĞİŞTİRMEMELİ.

    Değiştirseydi her yeni hatıra o noktadan sonraki tüm önbelleği düşürürdü
    ve bu hiçbir hata vermeden, sadece fatura olarak görünürdü.
    """
    client = FakeClient(text_turn("bir"), text_turn("iki"))
    agent = _agent(tmp_path, mind, client)

    await agent.run("ilk istek")
    mind.remember("Oturum ortasında öğrenilen yeni bir şey.", kind="user")
    await agent.run("ikinci istek")

    assert client.seen_system[0] == client.seen_system[1]
    # Yeni hatıra kaybolmadı; sadece bir sonraki açılışta ruha girecek.
    assert "Oturum ortasında" in mind.soul().render()
