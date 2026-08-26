"""Alt ajanlar.

Aracın asıl işi bağlamı bölmek: alt ajanın otuz araç çağrısı kendi
günlüğünde kalmalı, ana konuşmaya yalnızca cevap dönmeli. Bu bozulursa
hiçbir hata çıkmıyor — sadece pencere iki kat hızlı doluyor.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from neocp.loop import MAX_DEPTH
from neocp.tools import build_registry
from tests.test_loop import (  # noqa: F401
    FakeClient,
    build_agent,
    registry,
    text_turn,
    tool_turn,
)


@pytest.fixture()
def full(tmp_path: Path):
    """Gerçek araç defteri: `task` aracı da içinde."""
    return build_registry()


# -- kayıt -------------------------------------------------------------


def test_the_task_tool_exists_at_the_top_level(full) -> None:
    assert "task" in full


def test_a_subagent_gets_no_task_tool() -> None:
    """Aracın hiç kaydedilmemesi, kaydedilip reddedilmesinden iyi: model
    olmayan bir yeteneği denemesin."""
    assert "task" not in build_registry(subagents=False)


def test_subagents_can_run_side_by_side(full) -> None:
    """Asıl kazanç burada: bağımsız parçalar aynı turda paralel koşuyor."""
    assert full.get("task").parallel_safe


def test_the_tool_itself_changes_nothing(full) -> None:
    """Yan etki alt ajanın araçlarından geliyor ve onlar zaten izin
    kapısından geçiyor; aracı da mutasyon saymak her alt ajan için ikinci
    bir onay sorusu demekti."""
    assert not full.get("task").mutates


# -- koşum -------------------------------------------------------------


async def test_the_answer_comes_back_but_the_steps_do_not(
    tmp_path: Path, full
) -> None:
    """Alt ajanın ara adımları ana bağlamı doldurmamalı."""
    client = FakeClient(
        # Ana ajan alt ajan başlatıyor.
        tool_turn(("c1", "task", {"title": "ara", "task": "şu dizinde X'i bul"})),
        # Alt ajan: bir araç çağırıp sonra cevaplıyor.
        tool_turn(("c2", "list_dir", {"path": str(tmp_path)})),
        text_turn("X, ayarlar.py içinde geçiyor."),
        # Ana ajan sonucu aktarıyor.
        text_turn("Buldum: ayarlar.py"),
    )
    agent = build_agent(tmp_path, client, full)

    await agent.run("X nerede geçiyor")

    history = str(agent.session.messages())
    assert "X, ayarlar.py içinde geçiyor." in history   # cevap geldi
    assert "list_dir" not in history                     # ara adım gelmedi


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
    """Yetenekler ve MCP araçları açılıştan sonra yalnızca ana deftere
    ekleniyordu; alt ajan bir cihaz yeteneğini ya da bağlı bir MCP sunucusunu
    göremiyordu. Artık `source`u dolu araçlar ana defterden alt ajana iniyor.
    """
    from neocp.tools.base import ToolSpec

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

    # Dinamikler indi.
    assert "modbus_oku" in child
    assert "mcp__notion__notion-search" in child
    # Yerleşik ayrımı korundu: task alt ajanda yok.
    assert "task" not in child
    # Kaynak etiketi de taşındı — alt ajanın kendi alt ajanına da inebilsin.
    assert child.get("modbus_oku").source == "yetenek"


async def test_a_subagent_cannot_spawn_another(tmp_path: Path, full) -> None:
    """Sınırsız yuvalanma tek bir isteği ağaç gibi açar."""
    client = FakeClient(
        tool_turn(("c1", "task", {"task": "birinci seviye"})),
        text_turn("bitti"),
        text_turn("tamam"),
    )
    agent = build_agent(tmp_path, client, full)
    await agent.run("başla")

    assert MAX_DEPTH == 1
    # Alt ajanın defterinde araç yok demek, modelin denemesi de mümkün değil.
    assert "task" not in build_registry(subagents=False)


async def test_an_empty_answer_is_reported_as_an_error(tmp_path: Path, full) -> None:
    """Sessizce boş dönen bir alt ajan, ana ajanın "tamamdır" deyip
    geçmesine yol açıyordu."""
    client = FakeClient(
        tool_turn(("c1", "task", {"task": "bir şey yap"})),
        text_turn(""),        # alt ajan hiçbir şey söylemeden bitiyor
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

    # Boş görev için alt ajan hiç başlatılmamalı.
    assert not agent.session.log.notes("subagent_start")


async def test_interrupting_the_parent_stops_the_child(tmp_path: Path, full) -> None:
    """Kullanıcı durdur dediğinde alt ajan arkada çalışmaya devam etmemeli."""
    client = FakeClient(
        tool_turn(("c1", "task", {"task": "uzun iş"})),
        text_turn("alt ajan cevabı"),
        text_turn("tamam"),
    )
    agent = build_agent(tmp_path, client, full)
    captured: list = []

    original = agent._spawn

    async def watched(title: str, instruction: str, model: str = "") -> str:
        # Alt ajanın kesme bayrağı ana ajanınkiyle aynı nesne olmalı.
        import neocp.loop as loop_module

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

    assert captured, "alt ajan hiç kurulmadı"
    assert captured[0].cancel is agent.cancel


async def test_a_subagent_can_use_another_model(tmp_path: Path, full) -> None:
    """Tarama işi küçük ve hızlı bir modele, görüntü gerektiren iş görüntü
    okuyan bir modele gidebilmeli."""
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


async def test_the_same_model_reuses_the_parent_client(tmp_path: Path, full) -> None:
    """İkinci bir istemci ikinci bir bağlantı havuzu demek."""
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
