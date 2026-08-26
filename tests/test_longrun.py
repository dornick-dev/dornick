"""Saatlerce süren işler: tur bütçesi, iş ortası sıkıştırma, arka plan
işleri ve model kesintisi dayanıklılığı.

Uzun bir agentik işi bugüne kadar dört şey öldürüyordu: 60 turluk sert
tavan, 180 sn'lik araç zaman aşımı, tek koşuda kesim noktası bulamayan
sıkıştırma ve tek model hatasında biten döngü. Buradaki testler dördünün
de kapandığını kanıtlıyor.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

import neocp.loop as loop_module
from neocp.backends import TurnResult
from neocp.loop import Agent, clear_park, read_park, write_park
from neocp.session import PendingToolUse
from neocp.tools import ToolRegistry, ToolResult, object_schema
from tests.test_loop import (  # noqa: F401
    FakeClient,
    build_agent,
    message,
    registry,
    text_turn,
    tool_turn,
)


# -- tur bütçesi: sert tavan → kontrol noktası ---------------------------


async def test_a_long_run_survives_past_sixty_turns(
    tmp_path: Path, registry: ToolRegistry
) -> None:
    """Eski kod 60. turda `turn_limit` ile ölürdü; artık kontrol noktasıyla
    ilerleme notu istenip iş sürüyor."""
    script = [tool_turn((f"t{i}", "echo", {"text": str(i)})) for i in range(80)]
    script.append(text_turn("80 adımlık iş bitti"))
    client = FakeClient(*script)
    agent = build_agent(tmp_path, client, registry)

    stats = await agent.run("uzun bir iş yap")

    assert stats.turns == 81, "koşu 60 turda kesilmemeliydi"
    assert stats.stop_reason == "end_turn"
    assert not agent.session.log.notes("turn_limit"), "sigortaya çarpmamalıydı"
    marks = agent.session.log.notes("turn_checkpoint")
    assert marks and marks[0].meta["turns"] == 60
    # Kontrol noktası dürtüsü modele gerçekten gitti.
    assert "kontrol noktası" in str(client.seen_messages[-1])


async def test_the_hard_limit_still_guards(
    tmp_path: Path, registry: ToolRegistry, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mutlak sigorta duruyor: kaçak döngü sonsuza kadar koşamaz."""
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
    """Uzun koşuda arada bir max_tokens tavanına çarpmak, işi kapanış
    turuna sürüklememeli: araç çağıran tur sayacı tazeler."""

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

    assert stats.closing is False, "kapanış turuna sürüklenmemeliydi"
    assert stats.stop_reason == "end_turn"


# -- iş ortası sıkıştırma ------------------------------------------------


def test_work_cut_finds_an_assistant_boundary() -> None:
    """Tek koşuda gerçek kullanıcı turu yalnız başta: cut_point 0 döner,
    work_cut asistan sınırından güvenli kesim bulur."""
    from neocp.compaction import cut_point, work_cut

    def a() -> dict:
        return {"role": "assistant", "content": [{"type": "tool_use", "id": "x",
                                                  "name": "echo", "input": {}}]}

    def tr() -> dict:
        return {"role": "user", "content": [{"type": "tool_result",
                                             "tool_use_id": "x", "content": "ok"}]}

    msgs = [{"role": "user", "content": [{"type": "text", "text": "başla"}]},
            a(), tr(), a(), tr(), a(), tr(), a(), tr()]
    assert cut_point(msgs) == 0, "gerçek kullanıcı turu yok; eski yol kesemez"
    cut = work_cut(msgs)
    assert cut == 3
    assert msgs[cut]["role"] == "assistant", "kesim asistan sınırında olmalı"
    # Kesimden sonraki pencere karşılıksız tool_result ile başlamıyor.
    first = msgs[cut]["content"][0]
    assert first.get("type") != "tool_result"


async def test_mid_run_compaction_keeps_the_run_alive(
    tmp_path: Path, registry: ToolRegistry
) -> None:
    """Pencere tek koşunun ortasında dolunca: sıkıştır, iş durumunu özetin
    başına sabitle, koşu kaldığı yerden sürsün."""
    client = FakeClient(
        tool_turn(("t1", "echo", {"text": "a"})),
        tool_turn(("t2", "echo", {"text": "b"})),
        # 3. turun BAŞINDA pencere dolu ve artık kesim noktası var:
        # sıkıştırma tetiklenir ve bu metni özetleyici tüketir.
        text_turn("ÖZET: beş modüllü proje kuruluyordu; iki modül tamam."),
        tool_turn(("t3", "echo", {"text": "c"})),
        # Sahte pencere hep dolu göründüğü için bir sıkıştırma daha olur.
        text_turn("ÖZET 2: üçüncü modül de bitti."),
        text_turn("iş tamamlandı"),
    )
    agent = build_agent(tmp_path, client, registry)
    # Her tur "pencere dolu" görünsün: FakeClient 10 token bildiriyor.
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

    # Katlanacak bölgede modelin kendi ilerleme anlatımı dursun.
    agent.session.add_user_text("projeye başla")
    agent.session.add_assistant(
        [{"type": "text", "text": "Plan hazır: beş modül kuracağım, ikisi bitti."}])

    stats = await agent.run("kaldığın yerden devam et")

    # Sıkıştırma koşunun ORTASINDA oldu ve koşu tamamlandı.
    resets = agent.session.log.notes("context_reset")
    assert resets, "sıkıştırma hiç tetiklenmedi"
    assert agent.session.log.notes("compacted")
    assert stats.stop_reason == "end_turn"
    assert "iş tamamlandı" in str(agent.session.messages())

    # Özetin başında iş durumu: hedefler + son ilerleme + özet gövdesi.
    carried = str(resets[0].meta.get("summary"))
    assert "[İŞ DURUMU]" in carried
    assert "küçük projeyi bitir" in carried
    assert "beş modül kuracağım" in carried
    assert "ÖZET:" in carried

    # Sıkıştırmadan SONRA araç çağrısı sürdü (t3 cevabı geçmişte).
    assert "echo: c" in str(agent.session.log.messages())

    # Hedef dijesti sıfırlandı: canlı hedefler sıkıştırma sonrası yeniden
    # enjekte edildi (eski not + taze not — ikincisi sıfırlamanın kanıtı).
    fresh = [e for e in agent.session.log.messages()
             if e.role == "system" and "küçük projeyi bitir" in str(e.content)]
    assert len(fresh) >= 2, "hedefler sıkıştırma sonrası bağlama geri dönmedi"


# -- arka plan işleri (uzun süreçler) ------------------------------------


async def test_a_background_job_reports_when_done(
    tmp_path: Path, registry: ToolRegistry
) -> None:
    """Uzun iş defterde koşar; bitince çıktısı bir sonraki turun başında
    harness notuyla düşer — yardımcı bildirimiyle aynı yol."""
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


async def test_shell_arka_plan_returns_immediately(tmp_path: Path) -> None:
    from neocp.config import Config
    from neocp.events import EventLog
    from neocp.session import Session
    from neocp.tools import ToolContext
    from neocp.tools import shell as shell_tool

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
    assert "id=j1" in result.content, "araç beklemeden dönmeli"
    # Runner gerçekten komutu koşturuyor ve çıktıyı döndürüyor.
    out = await started["runner"](asyncio.Event())
    assert "merhaba-dunya" in out


async def test_the_executor_honours_a_requested_timeout(tmp_path: Path) -> None:
    """Araç açıkça süre istediyse (shell'e timeout: 600 gibi) yürütücünün
    genel sınırı onu 180 sn'de öldürmemeli."""
    from neocp.config import Config
    from neocp.events import EventLog
    from neocp.permissions import PermissionEngine
    from neocp.session import Session
    from neocp.tools import ToolContext
    from neocp.tools.executor import execute

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
        ctx=ctx, approve=yes, timeout_s=0.05)   # genel sınır kasıtlı küçük

    assert blocks[0]["is_error"] is False, "istenen süre genel sınırı aşmalıydı"


# -- model kesintisi dayanıklılığı ---------------------------------------


async def test_transient_model_errors_are_retried(
    tmp_path: Path, registry: ToolRegistry, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Bağlantı/5xx hatası koşuyu öldürmez: geri çekilip yeniden dener.
    (Eski davranış: TEK hata turu bitiriyordu.)"""
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
    assert stats.turns == 1, "başarısız denemeler tur sigortasını yememeli"


async def test_a_malformed_request_still_stops(
    tmp_path: Path, registry: ToolRegistry
) -> None:
    """Bozuk istek (400) yeniden denemekle düzelmez: eski davranış korunur."""
    client = FakeClient(
        TurnResult(error="API 400: her tool_use için bir tool_result dönmeli"),
        text_turn("buraya gelinmemeli"),
    )
    agent = build_agent(tmp_path, client, registry)

    await agent.run("bir şey")

    assert len(agent.session.log.notes("api_error")) == 1
    assert client.script, "ikinci tur hiç denenmemeliydi"


async def test_a_long_outage_parks_then_resumes(
    tmp_path: Path, registry: ToolRegistry, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Denemeler tükenince iş ölmez, PARK edilir; model dönünce kaldığı
    yerden sürer ve park kaydı temizlenir."""
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
    assert agent.session.log.notes("parked"), "park kaydı düşülmeliydi"
    assert agent.session.log.notes("unparked")
    assert read_park(agent.config.state_dir) is None, "iş bitince kayıt silinmeli"
    assert any("bekletiliyor" in n for n in notices)
    assert any("geri geldi" in n for n in notices)
    assert "iş bitti" in str(agent.session.messages())


async def test_interrupt_during_backoff_stops_and_unparks(
    tmp_path: Path, registry: ToolRegistry, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Bekleme kesilebilir: kullanıcı 'dur' derse park kaydı da düşer."""
    monkeypatch.setattr(loop_module, "RETRY_DELAYS", (0.01,))
    monkeypatch.setattr(loop_module, "PARK_PROBE_S", 30.0)   # parkta bekleyecek
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
    """Kesinti sırasında düzeltilen ayar (yeni adres/anahtar) bir sonraki
    denemede devreye girer — parklı tur bitmediği için tur sonu bekleyemez."""
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
    assert swaps, "yeniden denemeden önce bekleyen değişiklik uygulanmalıydı"


def test_outage_rotates_the_auto_pool() -> None:
    """Oto kipinde kesinti hata sayılır: cezalı model havuzun sonuna düşer,
    bir sonraki deneme başka modelle gider."""
    from neocp import otomod

    saglik = otomod.Saglik()
    for _ in range(otomod.HATA_ESIGI):
        saglik.kaydet("a/model", False)

    assert saglik.cezali("a/model")
    assert saglik.sirala(["a/model", "b/model"]) == ["b/model", "a/model"]


def test_park_records_round_trip(tmp_path: Path) -> None:
    write_park(tmp_path, "20260826T000000Z", "bağlantı yok")
    kayit = read_park(tmp_path)
    assert kayit and kayit["session"] == "20260826T000000Z"
    clear_park(tmp_path)
    assert read_park(tmp_path) is None
    clear_park(tmp_path)   # ikinci silme patlamaz


async def test_the_bridge_resumes_a_parked_run(tmp_path: Path) -> None:
    """Açılışta bulunan park kaydının karşılığı: pump işareti görünce
    koşuyu kaldığı yerden sürdürür."""
    from neocp.desktop import _PARK_RESUME, Bridge

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
    await bridge._park_surdur()

    assert resumed == [True]
    assert [e["type"] for e in hub.events][-1] == "turn_end"
