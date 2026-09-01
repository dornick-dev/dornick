"""Alt ajanlar.

Aracın asıl işi bağlamı bölmek: alt ajanın otuz araç çağrısı kendi
günlüğünde kalmalı, ana konuşmaya yalnızca cevap dönmeli. Bu bozulursa
hiçbir hata çıkmıyor — sadece pencere iki kat hızlı doluyor.
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
    """Gerçek araç defteri: `task` aracı da içinde."""
    return build_registry()


@pytest.fixture(autouse=True)
def _agsiz_katalog(monkeypatch):
    """Bu dosyadaki testler AĞA ÇIKMAMALI.

    `task` aracı, kendisine bir model kimliği verildiğinde onu sağlayıcının
    kataloğuyla doğruluyor ve katalog gerçek bir HTTP isteğiyle geliyor.
    Testin sonucu makinenin internetine bağlı olamaz: burada katalog
    varsayılan olarak BOŞ, yani "sunucu liste vermiyor" hali — doğrulama
    atlanır ve model aynen geçer. Doğrulamayı sınayan testler kataloğu
    kendileri sabitliyor.
    """
    from dornick import settings

    monkeypatch.setattr(settings, "scan_models", lambda _config: [])


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
    """Kullanıcı durdur dediğinde alt ajan arkada çalışmaya devam etmemeli.

    Bayrak artık paylaşılmıyor (arka plandaki çocuk, ananın `_arm`inde
    sahipsiz kalıyordu); çocuğun KENDİ bayrağı var ve ana `interrupt()`
    hepsini türev olarak kuruyor. Sözleşme aynı: dur = her şey durur.
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

    assert captured, "alt ajan hiç kurulmadı"
    # Çocuğun bayrağı defterdeki handle'ın bayrağı; ana interrupt() onu kurar.
    handle = next(iter(agent._children.values()))
    assert captured[0].cancel is handle.cancel
    assert not captured[0].cancel.is_set()
    agent.interrupt()
    assert agent.cancel.is_set()
    # Bitmiş çocuğun bayrağına dokunulmaz; koşan çocuk için kurulduğunu
    # ayrı bir sahte handle ile doğrula.
    from dornick.loop import ChildHandle

    running = ChildHandle(id="abc123", title="koşan", model="m")
    agent._children[running.id] = running
    agent.interrupt()
    assert running.cancel.is_set()


# -- arka plan yardımcıları ---------------------------------------------


class SlowClient(FakeClient):
    """Her turu biraz geciktiren sahte istemci: çocuk, ana ajandan sonra
    bitsin diye. Zamanlama testin özü değil, sıralamayı sabitliyor."""

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
    """arka_plan=true: araç sonucu HEMEN dönüyor, iş arkada koşuyor ve
    bitince sonucu bir sonraki turun başında nota dökülüyor."""
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

    # Araç sonucu beklemeden döndü; defterde koşan kayıt var.
    history = str(agent.session.messages())
    assert "yardımcı başlatıldı" in history
    handle = next(iter(agent._children.values()))
    assert handle.arka_plan and handle.task is not None

    # Çocuk bitene kadar bekle: sonuç defterde, henüz bildirilmedi.
    await handle.task
    assert handle.state == "bitti"
    assert "42 dosya var" in handle.sonuc
    assert agent.has_unreported_children()

    # Bir sonraki turun başında sonuç nota dökülüyor.
    await agent.run("nasıl gitti?")
    notes = str(agent.session.messages())
    assert "[Yardımcı bitti" in notes
    assert "42 dosya var" in notes
    assert not agent.has_unreported_children()


async def test_resume_for_children_opens_a_continuation_turn(
    tmp_path: Path, full
) -> None:
    """Ana ajan boştayken biten yardımcı: sürdürme turu continuation
    notuyla açılıyor (kullanıcı mesajı değil) ve sonucu değerlendiriyor."""
    from dornick.loop import ChildHandle

    client = FakeClient(text_turn("başlat"), text_turn("sonucu aktardım"))
    agent = build_agent(tmp_path, client, full)
    await agent.run("merhaba de")   # geçmişte en az bir tur olsun

    handle = ChildHandle(id="ab12cd", title="şiir", model="m",
                         arka_plan=True, state="bitti", sonuc="beş kelimelik şiir hazır")
    agent._children[handle.id] = handle

    stats = await agent.resume_for_children()
    assert stats is not None and stats.turns == 1

    # Girdi kullanıcı mesajı DEĞİL: continuation işaretli.
    nudges = [e for e in agent.session.log.messages() if e.meta.get("continuation")]
    assert nudges and "yardımcı(lar) bitti" in str(nudges[-1].content)
    # Sonuç harness notu olarak geçmişte.
    assert "beş kelimelik şiir hazır" in str(agent.session.messages())

    # Bildirilecek bir şey kalmadıysa model hiç çağrılmıyor.
    assert await agent.resume_for_children() is None


async def test_interrupt_stops_a_background_helper(tmp_path: Path, full) -> None:
    """Dur = her şey durur: arka planda koşan yardımcı da."""
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
    await asyncio.sleep(0.05)   # çocuk kapıyı alıp koşmaya başlasın
    assert handle.state == "kosuyor"

    agent.interrupt()
    await handle.task

    assert handle.state == "hata"
    assert handle.bildirildi, "kesilen yardımcı için bildirim turu açılmamalı"


# -- tur ortası gelen kutusu --------------------------------------------


async def test_a_mid_turn_note_lands_in_the_same_turn(tmp_path: Path) -> None:
    """Koşan tur sürerken düşen not, AYNI koşunun bir sonraki isteğine
    harness notu olarak giriyor."""
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
    assert not agent._inbox, "kutu boşalmalı"


async def test_a_note_after_the_final_answer_gets_one_more_step(
    tmp_path: Path
) -> None:
    """Model son cevabını verirken kullanıcı araya yazdıysa mesaj
    kaybolmuyor: aynı tur içinde bir adım daha veriliyor."""
    from dornick.tools import ToolRegistry

    class InterjectedClient(FakeClient):
        """İlk turun ORTASINDA (model cevap üretirken) not düşer."""

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

    assert stats.turns == 2, "not için bir adım daha verilmeliydi"
    assert "bir şey daha var" in str(client.seen_messages[-1])


def test_the_inbox_note_is_invisible_in_the_chat(tmp_path: Path) -> None:
    """Harness notu arayüzde mesaj gibi görünmemeli (balon zaten `araya`
    olayıyla çizildi); system kanalı uygun değilse user kanalından girer
    ama yine `internal` işaretli."""
    from dornick.events import EventLog
    from dornick.session import Session
    from dornick.web.server import _payload

    session = Session(EventLog(tmp_path / "n.jsonl"), "test")
    session.add_user_text("merhaba")
    session.add_harness_note("[Kullanıcı bu arada yazdı] birinci")   # system kanalı
    session.add_harness_note("[Kullanıcı bu arada yazdı] ikinci")    # user kanalına düşer
    events = session.log.messages()
    assert [e.role for e in events] == ["user", "system", "user"]
    assert _payload(events[1]) is None
    assert _payload(events[2]) is None
    # İkisi de modele gidiyor.
    sent = str(session.messages())
    assert "birinci" in sent and "ikinci" in sent


# -- task_say / task_status ---------------------------------------------


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
    """Bitmiş yardımcı: oturumu diskten `Session.resume` ile açılıp aynı
    handle üzerinden arka planda sürdürülüyor."""
    client = FakeClient(
        tool_turn(("c1", "task", {"title": "iş", "task": "bir şey yap"})),
        text_turn("çocuğun ilk cevabı"),
        text_turn("tamam"),
        text_turn("çocuğun devam cevabı"),   # sürdürülen koşunun turu
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
    assert handle.session_id == before, "aynı oturum sürdürülmeli, yenisi açılmamalı"
    assert "devam cevabı" in handle.sonuc
    assert agent.has_unreported_children()

    # Diskte hâlâ TEK çocuk oturumu var ve içinde sürdürme izi duruyor.
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
                                          arka_plan=True)
    agent._children["bb22"] = ChildHandle(id="bb22", title="biten", model="m",
                                          state="bitti", sonuc="üç dosya bulundu")

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
            state="bitti", bitis_ts=float(i), bildirildi=True))

    assert len(agent._children) == MAX_CHILDREN
    # En eskiler düştü, en yeniler duruyor.
    assert "h00" not in agent._children and "h11" in agent._children


# -- köprü: araya girme ve sürdürme turu ---------------------------------


class _Hub:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def emit(self, payload: dict) -> None:
        self.events.append(payload)


async def test_submitting_while_busy_interjects_into_the_running_turn(
    tmp_path: Path
) -> None:
    """Meşgulken gelen düz metin kuyruğa değil, koşan turun gelen kutusuna
    giriyor; arayüze `araya` olayı basılıyor (queued değil)."""
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
    await asyncio.sleep(0)   # call_soon_threadsafe işlesin

    assert notes and "rengi mavi yap" in notes[0][0]
    assert "[Kullanıcı bu arada yazdı]" in notes[0][0]
    assert notes[0][1] == "rengi mavi yap"          # anlık belleğe de gidiyor
    kinds = [e["type"] for e in hub.events]
    assert "araya" in kinds and "queued" not in kinds
    assert bridge.queue.empty(), "araya giren mesaj kuyruğa da düşmemeli"


async def test_scheduled_and_gate_messages_still_queue(tmp_path: Path) -> None:
    """`siraya=True` (zamanlanmış görev, dış kapı): eski kuyruk davranışı."""
    import asyncio

    from dornick.desktop import Bridge

    hub = _Hub()
    bridge = Bridge(hub, asyncio.get_running_loop())
    bridge._busy = True
    bridge.agent = object()   # take_note'suz: inbox yolu zaten kapalı

    bridge.submit("zamanlanmış iş", siraya=True)
    await asyncio.sleep(0.05)   # run_coroutine_threadsafe kuyruğa yazsın

    assert [e["type"] for e in hub.events] == ["queued"]
    assert bridge.queue.qsize() == 1


async def test_child_done_opens_a_resume_turn_when_idle(tmp_path: Path) -> None:
    """Yardımcı bitti sinyali kuyruğa düşüyor; sırası gelince (ajan boş)
    sürdürme turu koşuluyor ve turn_end yayılıyor."""
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

    await bridge._surdur()

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
            raise AssertionError("model çağrılmamalıydı")

    bridge.agent = StubAgent()
    await bridge._surdur()
    assert hub.events == []


async def test_an_approval_from_a_helper_carries_its_channel(tmp_path: Path) -> None:
    """Onay diyaloğu kimin izin istediğini bilsin: yardımcının kimliği ve
    başlığı approval_request olayında."""
    import asyncio

    from dornick.desktop import Bridge
    from dornick.tools.base import ToolSpec

    hub = _Hub()
    bridge = Bridge(hub, asyncio.get_running_loop())

    async def handler(args, ctx):  # pragma: no cover - sadece imza
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

    # Ana ajanın kendi isteğinde kanal alanı hiç yok.
    task = asyncio.ensure_future(bridge._approve(spec, {"command": "ls"}))
    await asyncio.sleep(0)
    ask = [e for e in hub.events if e["type"] == "approval_request"][-1]
    assert "channel" not in ask
    bridge.resolve_approval(ask["id"], False)
    await asyncio.sleep(0)
    assert await task is False


# -- sohbet listesi ------------------------------------------------------


async def test_child_sessions_stay_out_of_the_chat_list(tmp_path: Path, full) -> None:
    """Yardımcı oturumları /api/sessions listesine (mind.sessions) girmiyor;
    günlükleri diskte duruyor ve arşiv taramasında hâlâ bulunuyorlar."""
    from dornick.mind import open_mind

    client = FakeClient(
        tool_turn(("c1", "task", {"task": "bir şey yap"})),
        text_turn("çocuk cevabı"),
        text_turn("tamam"),
    )
    agent = build_agent(tmp_path, client, full)
    await agent.run("başla")

    files = list(agent.config.sessions_dir.glob("*.jsonl"))
    assert files, "çocuk oturumu diske yazılmalıydı"

    mind = open_mind(tmp_path / "mind2", agent.config.sessions_dir, "test")
    listed = [e.session_id for e in mind.sessions()]
    assert files[0].stem not in listed
    # Silinmedi: doğrudan bakınca hâlâ orada ve çocuk işaretli.
    episode = mind.episode(files[0].stem)
    assert episode is not None and episode.child
    mind.store.close()


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


# -- model doğrulaması -------------------------------------------------
#
# Sahada görülen: model yardımcıya UYDURMA bir kimlik verdi
# (`qwen3.1-14b`), sağlayıcı 400 döndürdü ve yardımcı tur boyunca boşa
# yandı. Hata alt ajanın günlüğünde patlıyor; ana ajan yalnızca "hata
# verdi" görüyor ve sebebini bilmiyor. Kimlik spawn'dan ÖNCE katalogla
# karşılaştırılmalı.


@pytest.fixture()
def kayit(tmp_path: Path):
    """Aracı doğrudan çağırmak için bağlam + çağrı yardımcısı."""
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


def _katalog(monkeypatch, ids: list[str]) -> None:
    """Sağlayıcının model kataloğunu sabitler; boş liste = ağ yok."""
    from dornick import settings

    monkeypatch.setattr(settings, "scan_models", lambda _config: [{"id": i} for i in ids])


async def test_a_made_up_model_falls_back_to_the_main_one(kayit, monkeypatch) -> None:
    """İş ölmemeli: yardımcı ana modelle başlar. Ama sessizce değil —
    aracın cevabı ne olduğunu ve nereye bakılacağını söyler."""
    tool, ctx, spawned = kayit
    _katalog(monkeypatch, ["qwen3-14b", "llama-3.1-8b"])

    result = await tool.handler({"task": "iş", "model": "qwen3.1-14b"}, ctx)

    assert spawned == [""]                       # ana modelle başladı
    assert "yardımcı sonucu" in result.content    # iş yapıldı
    assert "`qwen3.1-14b` geçerli bir model kimliği değil" in result.content
    assert "`models`" in result.content           # nereye bakacağını söylüyor
    # Yakın adaylar öneriliyor: "hangi kimlik doğru" sorusunun cevabı elde.
    assert "qwen3-14b" in result.content


async def test_a_real_model_passes_through_untouched(kayit, monkeypatch) -> None:
    tool, ctx, spawned = kayit
    _katalog(monkeypatch, ["qwen3-14b", "llama-3.1-8b"])

    result = await tool.handler({"task": "iş", "model": "qwen3-14b"}, ctx)

    assert spawned == ["qwen3-14b"]
    assert "geçerli bir model kimliği değil" not in result.content


async def test_validation_is_skipped_when_the_catalogue_is_unreachable(
    kayit, monkeypatch
) -> None:
    """Çevrimdışı bir makinede aracı çalışmaz yapmak, uydurma kimlikten
    daha kötü: katalog yoksa doğrulama atlanır ve model aynen geçer."""
    tool, ctx, spawned = kayit
    _katalog(monkeypatch, [])

    await tool.handler({"task": "iş", "model": "her-neyse"}, ctx)
    assert spawned == ["her-neyse"]


async def test_a_catalogue_lookup_that_explodes_does_not_kill_the_task(
    kayit, monkeypatch
) -> None:
    """Doğrulama bir kolaylık; patlarsa işin kendisi durmamalı."""
    from dornick import settings

    tool, ctx, spawned = kayit

    def patla(_config):
        raise RuntimeError("katalog yandı")

    monkeypatch.setattr(settings, "scan_models", patla)

    await tool.handler({"task": "iş", "model": "her-neyse"}, ctx)
    assert spawned == ["her-neyse"]


async def test_only_the_letter_case_is_corrected_silently(kayit, monkeypatch) -> None:
    """`Qwen3-14B` bir uydurma değil, bir yazım kayması: katalogdaki
    hâliyle düzeltilip devam ediliyor — ana model dayatmak gereksiz."""
    tool, ctx, spawned = kayit
    _katalog(monkeypatch, ["qwen3-14b"])

    result = await tool.handler({"task": "iş", "model": "Qwen3-14B"}, ctx)

    assert spawned == ["qwen3-14b"]
    assert "geçerli bir model kimliği değil" not in result.content


async def test_no_model_asked_means_no_catalogue_lookup(kayit, monkeypatch) -> None:
    """Alan boşsa ana model kullanılıyor; katalog için ağa çıkmanın anlamı
    yok — her `task` çağrısına bir istek eklemek pahalı."""
    from dornick import settings

    tool, ctx, spawned = kayit
    monkeypatch.setattr(
        settings, "scan_models",
        lambda _c: pytest.fail("boş model alanında kataloğa bakılmamalı"),
    )

    await tool.handler({"task": "iş"}, ctx)
    assert spawned == [""]


def test_the_tool_tells_the_model_not_to_invent_ids(full) -> None:
    """Doğrulama son savunma; ilk savunma aracın kendi açıklaması."""
    schema = full.get("task").input_schema
    note = schema["properties"]["model"]["description"]
    assert "UYDURMA" in note
    assert "boş bırak" in note and "`models`" in note


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
