"""İç içerik sızıntıları: harness notu, ham muhakeme, sahte araç çağrısı.

Üçü de aynı yaranın üyeleri — kullanıcının yazmadığı ya da kullanıcıya
gösterilmemesi gereken bir metin sohbete DÜZ ÇİZİLİYORDU. Ekran
görüntüsüyle yakalandılar:

  1. "Planını yazdın ama uygulamadın. Şimdi yap: …" — harness'ın sürdürme
     dürtüsü, sohbette kullanıcı mesajı gibi.
  2. Modelin iç muhakemesi, sohbette italik paragraflar hâlinde.
  3. `<function_calls><invoke name="shell">…` — modelin düz metin yazdığı
     sahte araç çağrısı.

Kökleri farklı, savunma hattı aynı: iç içerik işaretlenir ve işaretli
içerik ne canlı akışa ne de döküme çıkar.

Zincirin başı ayrı bir yarada: araç katmanı modele HAM istisna
döndürüyordu ("KeyError: 'path'"), model bunu "araç bozuk" diye okuyup
çağrıyı metin olarak yazmaya başlıyordu. Şema kapısı da burada sınanıyor.
"""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

import pytest

from neocp.mind.store import Mind
from neocp.permissions import PermissionEngine
from neocp.tools import ToolContext, ToolRegistry, ToolResult, execute, object_schema
from neocp.tools.base import ToolSpec, sema_ihlali
from neocp.session import PendingToolUse
from types import SimpleNamespace

from tests.test_loop import (  # noqa: F401  (fixture + yardımcılar)
    FakeClient, build_agent, registry, text_turn, tool_turn,
)


# -- 1. harness notu: döküm süzgeci ------------------------------------
#
# Canlı akışta hub `_payload` süzüyordu; DÖKÜM süzmüyordu. Oturum
# sürdürülünce ya da geçmişten açılınca iç notlar kullanıcı mesajı olarak
# geri geliyordu — sızıntının gerçek kökü buydu.


def _log_yaz(path: Path, satirlar: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for satir in satirlar:
            fh.write(json.dumps(satir, ensure_ascii=False) + "\n")


def test_the_transcript_hides_harness_notes(tmp_path: Path) -> None:
    """Sürdürme dürtüsü, harness notu ve araç sonucu dökümde GÖRÜNMEZ;
    kullanıcının ve ajanın gerçek sözleri görünür."""
    mind = Mind(tmp_path / "mind", tmp_path / "sessions", "s1")
    mind.sessions_dir.mkdir(parents=True, exist_ok=True)
    _log_yaz(mind.sessions_dir / "s1.jsonl", [
        {"kind": "message", "role": "user", "ts": 1,
         "content": [{"type": "text", "text": "bir panel yap"}], "meta": {}},
        {"kind": "message", "role": "assistant", "ts": 2,
         "content": [{"type": "text", "text": "Planım şu."}], "meta": {}},
        # Harness'ın sürdürme dürtüsü — kullanıcı yazmadı.
        {"kind": "message", "role": "user", "ts": 3,
         "content": [{"type": "text",
                      "text": "Planını yazdın ama uygulamadın. Şimdi yap: …"}],
         "meta": {"continuation": True}},
        # Harness notu (yardımcı bitti gibi) — kullanıcı yazmadı.
        {"kind": "message", "role": "user", "ts": 4,
         "content": [{"type": "text", "text": "[Yardımcı bitti · x] Sonucu: y"}],
         "meta": {"internal": True}},
        # Araç sonucu — teknik olarak kullanıcı turu, sohbet satırı değil.
        {"kind": "message", "role": "user", "ts": 5,
         "content": [{"type": "text", "text": "çıktı: 42"}],
         "meta": {"tool_results": True}},
        {"kind": "message", "role": "assistant", "ts": 6,
         "content": [{"type": "text", "text": "Panel hazır."}], "meta": {}},
    ])

    dokum = mind.transcript("s1")

    assert [t["text"] for t in dokum] == ["bir panel yap", "Planım şu.", "Panel hazır."]
    hepsi = " ".join(t["text"] for t in dokum)
    assert "uygulamadın" not in hepsi
    assert "Yardımcı bitti" not in hepsi


def test_the_transcript_hides_reasoning_only_turns(tmp_path: Path) -> None:
    """Model yalnızca akıl yürütüp durduğunda sağlayıcı katmanı o muhakemeyi
    METİN bloğuna çeviriyor (openai_backend, `empty_turn`). Geçmişe girmesi
    doğru — model kendi planını görmeli — ama kullanıcıya CEVAP DEĞİL.
    `internal` işareti onu dökümden de uzak tutuyor."""
    mind = Mind(tmp_path / "mind", tmp_path / "sessions", "s2")
    mind.sessions_dir.mkdir(parents=True, exist_ok=True)
    _log_yaz(mind.sessions_dir / "s2.jsonl", [
        {"kind": "message", "role": "user", "ts": 1,
         "content": [{"type": "text", "text": "hisse verisi çek"}], "meta": {}},
        {"kind": "message", "role": "assistant", "ts": 2,
         "content": [{"type": "text",
                      "text": "Muhtemelen yfinance importu gerekir. Ama task_status yok…"}],
         "meta": {"internal": True, "usage": {"prompt_total": 10}}},
        {"kind": "message", "role": "assistant", "ts": 3,
         "content": [{"type": "text", "text": "Veri çekildi."}], "meta": {}},
    ])

    dokum = mind.transcript("s2")

    assert [t["text"] for t in dokum] == ["hisse verisi çek", "Veri çekildi."]


# -- 2. şema kapısı: ham istisna yerine yönerge -------------------------


def _spec(properties: dict, required: list[str]) -> ToolSpec:
    return ToolSpec(
        name="write_file", description="yazar",
        input_schema=object_schema(properties, required),
        handler=lambda *_: None,   # type: ignore[arg-type]
    )


def test_a_missing_required_field_teaches_instead_of_raising() -> None:
    """Kanıtlanmış zincirin ilk halkası: eksik `path` ham `KeyError` yerine
    ne yapılacağını söyleyen bir mesaj olmalı."""
    spec = _spec({"path": {"type": "string"}, "text": {"type": "string"}},
                 ["path", "text"])

    uyari = sema_ihlali(spec, {"text": "merhaba"})

    assert uyari is not None
    assert "`path`" in uyari                    # hangi alan
    assert "Verdiğin alanlar: text" in uyari    # ne verdin
    assert "path (string, zorunlu)" in uyari    # şema ne
    assert "KeyError" not in uyari


def test_a_wrong_type_is_named_with_both_sides() -> None:
    spec = _spec({"timeout": {"type": "number"}}, [])

    uyari = sema_ihlali(spec, {"timeout": "otuz"})

    assert uyari and "`timeout` alanı number olmalı" in uyari
    assert "str verdin" in uyari


def test_an_enum_violation_lists_the_valid_values() -> None:
    spec = _spec({"action": {"type": "string", "enum": ["read", "write"]}}, [])

    uyari = sema_ihlali(spec, {"action": "oku"})

    assert uyari and "read, write" in uyari


def test_a_valid_call_passes_and_extra_fields_are_tolerated() -> None:
    """Fazladan alan hata DEĞİL: çalışan bir çağrıyı fazladan alan yüzünden
    reddetmek, aracı bozmak olurdu."""
    spec = _spec({"path": {"type": "string"}}, ["path"])

    assert sema_ihlali(spec, {"path": "a.txt"}) is None
    assert sema_ihlali(spec, {"path": "a.txt", "encoding": "utf-8"}) is None


async def test_the_executor_gates_every_tool_from_one_place(tmp_path: Path) -> None:
    """Şema kapısı yürütücüde: her araç için aynı güvence, tek tek araçlara
    yama yok. Handler HİÇ çağrılmıyor — eksik alanla çalıştırmak zaten
    patlardı."""
    from neocp.config import Config
    from neocp.events import EventLog
    from neocp.session import Session

    config = Config.load(tmp_path)
    config.ensure_dirs()
    ctx = ToolContext(config=config,
                      session=Session(EventLog(tmp_path / "s.jsonl"), "t"),
                      cancel=asyncio.Event())

    registry = ToolRegistry()
    kosuldu: list[dict] = []

    @registry.tool("write_file", "yazar",
                   object_schema({"path": {"type": "string"},
                                  "text": {"type": "string"}}, ["path", "text"]))
    async def _write(args, _ctx):
        kosuldu.append(args)
        return ToolResult("yazıldı: " + args["path"])   # eksik alanda patlardı

    blocks = await execute(
        [PendingToolUse("1", "write_file", {"text": "merhaba"})],
        registry=registry,
        permissions=PermissionEngine("yolo", allow=[], deny=[]),
        ctx=ctx,
        approve=lambda *_: asyncio.sleep(0, result=True),
    )

    assert kosuldu == [], "şemaya uymayan çağrı handler'a gitmemeliydi"
    assert blocks[0]["is_error"] is True
    assert "`path`" in blocks[0]["content"]
    assert "KeyError" not in blocks[0]["content"]


async def test_a_handler_exception_is_wrapped_with_guidance(tmp_path: Path) -> None:
    """Handler içinden sızan istisna da ham gitmiyor: tip + mesaj DURUYOR
    (teşhis lazım) ama yanında ne yapılacağı yazıyor. Model "araç bozuk"
    diye okumasın."""
    from neocp.config import Config
    from neocp.events import EventLog
    from neocp.session import Session

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

    icerik = blocks[0]["content"]
    assert blocks[0]["is_error"] is True
    assert "ValueError" in icerik and "ters gitti" in icerik   # teşhis kalıyor
    assert "yeniden dene" in icerik                             # yönerge eklendi
    assert "Traceback" not in icerik


# -- 3. sahte araç çağrısı ----------------------------------------------


@pytest.mark.parametrize("metin", [
    '<function_calls><invoke name="shell">',
    'Şimdi çalıştırıyorum:\n<invoke name="write_file">\n<parameter name="path">a</parameter>',
    "<invoke name=\"shell\">",
])
def test_tool_call_xml_in_text_is_recognised(metin: str) -> None:
    from neocp.loop import sahte_arac_cagrisi

    assert sahte_arac_cagrisi(metin) is True


@pytest.mark.parametrize("metin", [
    "Dosyayı yazdım ve testleri koşturdum.",
    "HTML'de <div> ve <span> kullandım.",
    "",
])
def test_ordinary_text_is_not_mistaken_for_a_tool_call(metin: str) -> None:
    """Kalıp DAR olmalı: sıradan bir cevapta geçen etiketler yüzünden
    kullanıcının cevabı yutulursa savunma yaranın kendisi olur."""
    from neocp.loop import sahte_arac_cagrisi

    assert sahte_arac_cagrisi(metin) is False


# -- sahte çağrı: döngü tarafı ------------------------------------------


async def test_a_faked_tool_call_does_not_end_the_turn(
    tmp_path: Path, registry: ToolRegistry
) -> None:
    """Model çağrıyı metin olarak yazdı ve turu bitirdi. Burada durmak
    kullanıcıyı sessizce yarım bırakırdı: harness notu düşer, tur SÜRER ve
    model gerçek çağrıyı yapar."""
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
    assert stats.sahte_cagri == 1
    # Düzeltme notu modele gerçekten gitti.
    gonderilen = str(client.seen_messages[-1])
    assert "DÜZ METİN olarak yazdın" in gonderilen
    # Not harness kanalından: kullanıcı yazmadı, sohbette görünmemeli.
    isaretli = [e for e in agent.session.log.messages()
                if e.meta.get("internal") and "DÜZ METİN" in str(e.content)]
    assert isaretli, "düzeltme notu `internal` işaretli olmalı"


async def test_a_repeated_fake_call_hardens_the_note(
    tmp_path: Path, registry: ToolRegistry
) -> None:
    """Yumuşak not işe yaramadıysa sertleşir — tur yine kapatılmaz."""
    from tests.test_loop import FakeClient, build_agent, text_turn

    xml = '<invoke name="shell"><parameter name="command">dir</parameter></invoke>'
    client = FakeClient(text_turn(xml), text_turn(xml), text_turn("tamam, düzeldim"))
    agent = build_agent(tmp_path, client, registry)

    stats = await agent.run("listele")

    assert stats.sahte_cagri == 2
    assert "YİNE metin olarak yazdın" in str(client.seen_messages[-1])


async def test_a_hopeless_model_stops_holding_the_turn(
    tmp_path: Path, registry: ToolRegistry, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mutlak sigorta: düzelmeyen model turu sonsuza kadar meşgul etmesin.
    Tavanda tur kendi akışına bırakılıyor ve kullanıcıya durum söyleniyor —
    çözüm onun elinde (model değiştirmek)."""
    import neocp.loop as loop_module
    from tests.test_loop import FakeClient, build_agent, text_turn

    monkeypatch.setattr(loop_module, "SAHTE_CAGRI_TAVANI", 2)
    xml = '<invoke name="shell">'
    client = FakeClient(*[text_turn(xml) for _ in range(10)])
    agent = build_agent(tmp_path, client, registry)
    notices: list[str] = []
    agent.io.on_notice = notices.append

    stats = await agent.run("listele")

    assert stats.sahte_cagri == 3, "tavanı bir aşınca bırakılmalı"
    assert any("başka bir model" in n for n in notices)


async def test_a_real_tool_call_is_never_hijacked(
    tmp_path: Path, registry: ToolRegistry
) -> None:
    """Metinde XML geçse bile GERÇEK bir araç çağrısı varsa karışılmaz:
    iş yürüyor demektir."""
    from neocp.backends import TurnResult
    from tests.test_loop import FakeClient, build_agent, message, text_turn

    karma = TurnResult(message=message([
        {"type": "text", "text": '<invoke name="shell">'},
        {"type": "tool_use", "id": "t1", "name": "echo", "input": {"text": "x"}},
    ], "tool_use"))
    client = FakeClient(karma, text_turn("bitti"))
    agent = build_agent(tmp_path, client, registry)

    stats = await agent.run("çalış")

    assert stats.sahte_cagri == 0
    assert stats.tool_calls == 1


# -- oto havuz sağlık cezası --------------------------------------------
#
# Ücretsiz havuzda araç çağıramayan bir uç, hata veren uçtan farksız: işi
# ilerletmiyor, yalnızca tur harcıyor. Şema ihlali ve sahte araç çağrısı
# artık hata/zaman aşımı/boş yanıtın yanında sağlık sinyali.


def _oto_backend():
    from neocp.backends.openai_backend import OpenAIBackend
    from neocp.config import OPENROUTER_URL, OTO_MODEL, ModelConfig

    return OpenAIBackend(ModelConfig(
        provider="openai", name=OTO_MODEL, base_url=OPENROUTER_URL))


def test_content_faults_penalise_the_auto_pool() -> None:
    """Şema ihlali ve sahte çağrı sağlık defterine başarısızlık yazar;
    eşiği aşan model havuzun sonuna iner."""
    from neocp import otomod

    backend = _oto_backend()
    backend._son_secilen = "ucuz/model"
    for _ in range(otomod.HATA_ESIGI):
        backend.kusurlu("sahte araç çağrısı")

    assert backend._saglik.cezali("ucuz/model")
    assert backend._saglik.sirala(["ucuz/model", "saglam/model"]) \
        == ["saglam/model", "ucuz/model"]


def test_a_chosen_model_is_never_punished_behind_the_users_back() -> None:
    """Oto kipi DIŞINDA karşılığı yok: kullanıcı modeli kendi seçti, onu
    arkasından sıralamaya sokmak bize düşmez."""
    from neocp.backends.openai_backend import OpenAIBackend
    from neocp.config import ModelConfig

    backend = OpenAIBackend(ModelConfig(
        provider="openai", name="anthropic/claude", base_url="https://x"))
    backend._son_secilen = "anthropic/claude"
    backend.kusurlu("şema ihlali")

    assert not backend._saglik.cezali("anthropic/claude")


async def test_the_loop_reports_content_faults_to_the_backend(
    tmp_path: Path, registry: ToolRegistry  # noqa: F811
) -> None:
    """Döngü sinyali gerçekten geçiriyor: sahte çağrı ve şema ihlali
    `client.kusurlu` ile sağlayıcıya bildiriliyor."""
    from tests.test_loop import FakeClient, build_agent, text_turn, tool_turn

    class _Sayan(FakeClient):
        def __init__(self, *script):
            super().__init__(*script)
            self.sebepler: list[str] = []

        def kusurlu(self, sebep: str = "") -> None:
            self.sebepler.append(sebep)

    client = _Sayan(
        text_turn('<invoke name="shell">'),
        # `echo` şeması `text` bekliyor; `metin` yanlış alan değil ama
        # zorunlu alan yok — bu yüzden tip ihlaliyle sınanıyor.
        tool_turn(("t1", "echo", {"text": 42})),
        text_turn("bitti"),
    )
    agent = build_agent(tmp_path, client, registry)

    await agent.run("çalış")

    assert "sahte araç çağrısı" in client.sebepler
    assert "şema ihlali" in client.sebepler


# -- hedef paneli: yönetim ucu ------------------------------------------
#
# Panel salt gösterimdi ve kullanıcı haklı olarak soruyordu: "bunlar
# nereden ekleniyor, nereden temizleniyor?" Ajan `mind_goals` ile ekliyor;
# kullanıcının elinde hiçbir şey yoktu ve eski oturumlardan kalan hedefler
# birikip duruyordu. Artık aynı deftere kullanıcı da yazabiliyor.


def _goals_server(tmp_path: Path):
    import urllib.request

    from neocp.config import Config
    from neocp.events import EventLog
    from neocp.mind import open_mind
    from neocp.web import MindServer

    config = Config.load(tmp_path)
    config.ensure_dirs()
    mind = open_mind(tmp_path / "mind", tmp_path / "sessions", "cur")
    log = EventLog(tmp_path / "s.jsonl")
    server = MindServer(mind, log, port=0, config=config)
    server.start()

    def gonder(payload: dict) -> dict:
        istek = urllib.request.Request(
            server.url + "api/goals",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(istek, timeout=5) as cevap:
            return json.loads(cevap.read().decode("utf-8"))

    return server, log, mind, gonder


def test_the_user_can_finish_and_drop_a_goal(tmp_path: Path) -> None:
    server, log, mind, gonder = _goals_server(tmp_path)
    try:
        bitecek = mind.push_goal("testleri yeşile al")
        kalkacak = mind.push_goal("bayat hedef")

        assert gonder({"action": "done", "id": bitecek.id})["ok"] is True
        assert gonder({"action": "drop", "id": kalkacak.id})["ok"] is True

        # Aktif liste boşaldı; defterde durumlar gerçekten değişti.
        assert mind.goals() == []
        assert mind._goals[bitecek.id].status == "done"
        assert mind._goals[kalkacak.id].status == "dropped"
    finally:
        server.stop()
        log.close()


def test_clear_empties_the_whole_stack(tmp_path: Path) -> None:
    """Birikmiş liste tek jestle temizlenebilmeli — arayüzde iki adımlı
    onayın arkasında duruyor."""
    server, log, mind, gonder = _goals_server(tmp_path)
    try:
        for i in range(6):
            mind.push_goal(f"eski hedef {i}")
        assert len(mind.goals()) == 6

        assert gonder({"action": "clear"})["ok"] is True
        assert mind.goals() == []
    finally:
        server.stop()
        log.close()


def test_a_bad_goal_request_is_refused_without_touching_the_ledger(
    tmp_path: Path
) -> None:
    """Uydurma eylem ve geçersiz id deftere dokunmadan reddedilir."""
    server, log, mind, gonder = _goals_server(tmp_path)
    try:
        hedef = mind.push_goal("duran hedef")

        assert gonder({"action": "sil-hepsini"})["ok"] is False
        assert gonder({"action": "done", "id": "../../etc"})["ok"] is False
        assert gonder({"action": "done", "id": "goal-yok"})["ok"] is False

        assert [g.id for g in mind.goals()] == [hedef.id]
    finally:
        server.stop()
        log.close()


async def test_a_faked_call_turn_is_marked_internal(
    tmp_path: Path, registry: ToolRegistry  # noqa: F811
) -> None:
    """Ham XML geçmişe girer (model ne yaptığını görmeli) ama `internal`
    işaretlidir: oturum sürdürülünce ajan mesajı olarak geri gelmez."""
    from tests.test_loop import FakeClient, build_agent, text_turn

    client = FakeClient(text_turn('<invoke name="shell">'), text_turn("düzeldim"))
    agent = build_agent(tmp_path, client, registry)

    await agent.run("listele")

    xml_turu = [e for e in agent.session.log.messages()
                if e.role == "assistant" and "invoke" in str(e.content)]
    assert xml_turu and xml_turu[0].meta.get("internal") is True
    # Gerçek cevap işaretli DEĞİL: kullanıcı onu görmeli.
    gercek = [e for e in agent.session.log.messages()
              if e.role == "assistant" and "düzeldim" in str(e.content)]
    assert gercek and not gercek[0].meta.get("internal")


def test_the_user_can_add_their_own_item(tmp_path: Path) -> None:
    """Liste iki taraflı: ajan `mind_goals` ile yazıyor, kullanıcı panelden.
    Aynı defter — ajan kendi maddesini de görüyor."""
    server, log, mind, gonder = _goals_server(tmp_path)
    try:
        cevap = gonder({"action": "add", "text": "faturayi ode"})
        assert cevap["ok"] is True and cevap["id"]
        assert [g.text for g in mind.goals()] == ["faturayi ode"]

        # Boş madde reddediliyor; defter kirlenmiyor.
        assert gonder({"action": "add", "text": "   "})["ok"] is False
        assert len(mind.goals()) == 1

        # Roman uzunluğunda madde kırpılıyor.
        gonder({"action": "add", "text": "x" * 500})
        assert max(len(g.text) for g in mind.goals()) <= 200
    finally:
        server.stop()
        log.close()


def test_goals_from_earlier_sessions_stay_out_of_the_panel(tmp_path: Path) -> None:
    """"Bu görevleri kim oluşturuyor" sorusunun cevabı: hedef defteri
    SOHBETİN defteri. Başka oturumun maddesi panele hiç gelmez (canlı yara:
    PDF sohbetinin sonunda ajan başka sohbetin "ev otomasyonu" hedefini
    tartışıyordu); zihnin tamamına bakan yerler all_sessions ile ister."""
    from types import SimpleNamespace

    from neocp.desktop import _active_goals
    from neocp.mind import open_mind

    mind = open_mind(tmp_path / "mind", tmp_path / "sessions", "eski-oturum")
    bayat = mind.push_goal("geçen oturumdan kalan")
    mind.session_id = "yeni-oturum"
    taze = mind.push_goal("bu oturumda açıldı")

    dokum = {g["id"] for g in _active_goals(SimpleNamespace(mind=mind))}
    assert taze.id in dokum
    assert bayat.id not in dokum

    # Kabul kapısının ve sistem notlarının kaynağı da aynı süzgeçten geçer.
    assert bayat.text not in mind.goal_digest()
    assert taze.text in mind.goal_digest()

    # Beyin grafiği zihnin tamamını ister — süzgecin kapısı açık.
    hepsi = {g.id for g in mind.goals(all_sessions=True)}
    assert {bayat.id, taze.id} <= hepsi


# -- zihin yazma refleksi ------------------------------------------------
#
# Ölçülmüş regresyon: son altı oturumda `mind_memory` çağrısı SIFIR, 91
# araç çağrılı turda bile. Otomatik yol (episode) akıyordu, model-güdümlü
# kalıcı yazma durmuştu. İki kök birden düzeltildi: (1) kendi defterine
# yazmak onay kapısının arkasındaydı, (2) yazma yalnızca bir öğüttü.


class _Zihin:
    """Yazmayı sayan sahte zihin."""

    def __init__(self) -> None:
        self.session_id = "s"
        self.yazilanlar: list[str] = []

    def remember(self, body, **kw):
        self.yazilanlar.append(body)
        return SimpleNamespace(id="m1")

    def goals(self, **kw):
        return []

    def goal_digest(self):
        return ""


async def test_a_preference_nudges_the_agent_to_remember(
    tmp_path: Path, registry: ToolRegistry
) -> None:
    """Kullanıcı kalıcı bir şey söyledi ve model kendi defterine yazmadı:
    tur sonunda modelin önüne TEK SATIR not konuyor. Not harness kanalından
    gidiyor — sohbette görünmez."""
    client = FakeClient(text_turn("tamam, öyle yapacağım"))
    agent = build_agent(tmp_path, client, registry)
    agent.mind = _Zihin()

    await agent.run("bundan sonra raporları hep tablo yaz")

    notlar = [e for e in agent.session.log.messages()
              if e.meta.get("internal") and "[Zihin]" in str(e.content)]
    assert notlar, "kalıcı bir şey geçti, dürtü düşmeliydi"
    icerik = str(notlar[0].content)
    assert "mind_memory" in icerik
    assert "tablo yaz" in icerik, "not neyi kastettiğini söylemeli"
    assert "yok say" in icerik, "emir değil davet: yanlış pozitifte zararsız"
    assert agent.session.log.notes("zihin_durtusu")


async def test_no_nudge_when_the_agent_already_wrote(
    tmp_path: Path, registry: ToolRegistry
) -> None:
    """Model zaten yazdıysa dürtmek gereksiz gürültü."""
    reg = ToolRegistry()

    @reg.tool("mind_memory", "yazar", object_schema({"action": {"type": "string"}}))
    async def _mem(args, ctx):
        return ToolResult("yazıldı")

    client = FakeClient(
        tool_turn(("t1", "mind_memory", {"action": "save"})),
        text_turn("kaydettim"),
    )
    agent = build_agent(tmp_path, client, reg)
    agent.mind = _Zihin()

    await agent.run("bundan sonra raporları hep tablo yaz")

    assert not agent.session.log.notes("zihin_durtusu")


async def test_no_nudge_without_a_lasting_signal(
    tmp_path: Path, registry: ToolRegistry
) -> None:
    """Sıradan bir soru dürtü üretmez: sezgi ucuz ama gürültücü olmamalı."""
    client = FakeClient(text_turn("saat 14:00"))
    agent = build_agent(tmp_path, client, registry)
    agent.mind = _Zihin()

    await agent.run("saat kaç")

    assert not agent.session.log.notes("zihin_durtusu")


async def test_the_nudge_does_not_repeat_for_the_same_sentence(
    tmp_path: Path, registry: ToolRegistry
) -> None:
    """Art arda aynı konuda dürtmek bıkkınlık: bir kez söylenir."""
    client = FakeClient(text_turn("tamam"), text_turn("tamam"))
    agent = build_agent(tmp_path, client, registry)
    agent.mind = _Zihin()

    await agent.run("bundan sonra hep tablo yaz")
    await agent.run("bundan sonra hep tablo yaz")

    assert len(agent.session.log.notes("zihin_durtusu")) == 1


def test_the_scent_reads_both_languages() -> None:
    """Kullanıcı iki dilde de yazıyor; sinyal listesi ikisini de tanımalı."""
    from neocp.loop import kalici_koku

    assert kalici_koku("bundan sonra raporları hep tablo yaz")
    assert kalici_koku("benim adım Fatih")
    assert kalici_koku("hayır, öyle değil — düzelt")
    assert kalici_koku("from now on always use tables")
    assert kalici_koku("i prefer short answers")
    # Sıradan cümleler koku vermemeli.
    assert not kalici_koku("saat kaç")
    assert not kalici_koku("bu dosyayı okur musun")
    assert not kalici_koku("")


# -- kendi defterine yazmak onay istemez ---------------------------------


def test_writing_to_its_own_mind_needs_no_approval() -> None:
    """ASIL KÖK: `mind_memory save` mutasyon sayılıyordu — her hatıra bir
    onay penceresi, plan kipinde ise düpedüz RET. Zihin bu yüzden sustu.
    Kendi defterine yazmak onay istemiyor; SİLMEK hâlâ istiyor."""
    from neocp.permissions import Decision, PermissionEngine
    from neocp.tools.base import ToolSpec, object_schema

    spec = ToolSpec(
        name="mind_memory", description="", handler=lambda *_: None,  # type: ignore[arg-type]
        input_schema=object_schema({"action": {"type": "string"}}, ["action"]),
        mutates=True, safe_actions=("save", "list", "link", "series"),
    )

    for mode in ("ask", "auto", "plan"):
        engine = PermissionEngine(mode, allow=[], deny=[])
        karar, _ = engine.evaluate(spec, {"action": "save"})
        assert karar is Decision.ALLOW, f"{mode}: kaydetmek sorulmamalı"

    # Silmek başka bir şey: kalıcı kayıp, kapı kapalı kalıyor.
    assert PermissionEngine("ask", allow=[], deny=[]).evaluate(
        spec, {"action": "forget"})[0] is Decision.ASK
    assert PermissionEngine("plan", allow=[], deny=[]).evaluate(
        spec, {"action": "forget"})[0] is Decision.DENY


def test_the_real_mind_tools_declare_their_safe_actions(tmp_path: Path) -> None:
    """Bayrak gerçekten kayıtlı araçlarda: kalıp bir yerde kalmasın."""
    from neocp.mind import open_mind
    from neocp.mind.tools import register as register_mind

    reg = ToolRegistry()
    register_mind(reg, open_mind(tmp_path / "mind", tmp_path / "sessions", "s"))

    hafiza = reg.get("mind_memory")
    assert hafiza and "save" in hafiza.safe_actions
    assert "forget" not in hafiza.safe_actions, "silme gated kalmalı"
    hedef = reg.get("mind_goals")
    assert hedef and "push" in hedef.safe_actions


def test_the_guide_asks_for_writing_in_the_moment() -> None:
    """Rehber genel kural olarak yazıyor: reçete değil, ilke."""
    from neocp import prompt as builder

    duz = " ".join(builder.MEMORY_RULES.split())
    assert "sen sormasan da" in duz
    assert "o an" in duz or "konu geçerken" in duz
    assert "oturum kapanınca bağlam gider, zihin kalır" in duz


# -- "Şimdi eğit" sessiz kalmaz -----------------------------------------
#
# Kullanıcı düğmeye basıyor, ekranda hiçbir şey olmuyordu. Gerçek: döngü
# başlıyor ve bir saniyeden kısa sürede "yeni veri az: 0/50" deyip
# çıkıyordu. Sonuç artık SEBEBİYLE dönüyor ve arayüz tek satırla söylüyor.


def test_train_now_reports_why_it_did_not_start(tmp_path: Path) -> None:
    """Kapalı özellik, eksik düzenek ve veri yokluğu ayrı ayrı adlandırılıyor
    — hepsi sessiz bir "hiçbir şey olmadı" değil."""
    from neocp import tanima

    class _Hub:
        def emit(self, payload: dict) -> None:
            pass

    hub = _Hub()

    # Kapalıyken: adı konuyor.
    assert tanima.belki_baslat(tmp_path, hub, zorla=True) == "kapali"

    tanima.ayarla(tmp_path, True)
    sebep = tanima.belki_baslat(tmp_path, hub, zorla=True)
    # Düzenek kurulu değilse orada durur; kuruluysa eğitecek veri yoktur —
    # ikisi de ADLANDIRILMIŞ bir sonuç, sessizlik değil.
    assert sebep in ("duzenek_yok", "veri_yok")
    assert sebep != "basladi", "boş veriyle koşu başlatılmamalı"


def test_the_ui_has_a_line_for_every_outcome() -> None:
    """Her sebep kodunun bir karşılığı var: kullanıcı "neden olmadı"yı
    okuyabilmeli. Sessiz düşen bir kod kalmamalı."""
    APP_JS = (Path(__file__).resolve().parents[1]
              / "src" / "neocp" / "web" / "static" / "app.js").read_text(encoding="utf-8")
    for kod in ("basladi", "veri_yok", "kosuyor", "duzenek_yok",
                "kapali", "ara_yok", "baslatilamadi"):
        assert re.search(rf"\b{kod}:", APP_JS), kod
    # Nabız çok kısa koşularda bile görünsün.
    assert re.search(r"const TANIMA_EN_AZ_MS = \d+", APP_JS)


def test_derived_session_titles_skip_one_letter_keystrokes() -> None:
    """Canli yara: ilk mesaj kazara tek harf olunca ("e" + Enter) sohbet
    solda o harfle listeleniyordu. Turetilmis baslik kirintiyi atlar."""
    from neocp.web.server import _session_title

    assert _session_title(
        "e ev otomasyonu yapıyorum mock data ile"
    ) == "ev otomasyonu yapıyorum mock data ile"
    assert _session_title("b") == "b"          # tek soz varsa o kalir
    assert _session_title("2 sayı topla") == "2 sayı topla"  # rakam baslik olabilir


def test_generated_titles_reject_single_letter_junk() -> None:
    """Kucuk model bazen cop donduruyor ("e"); zayif suzgec bunu KALICI ad
    yapiyordu ve ad bir kez yazilinca bir daha uretilmiyordu."""
    from neocp.loop import _baslik_gecerli

    assert not _baslik_gecerli("e")
    assert not _baslik_gecerli("")
    assert not _baslik_gecerli("----")
    assert not _baslik_gecerli("x" * 61)
    assert _baslik_gecerli("Ev otomasyonu simülasyonu")
    assert _baslik_gecerli("PLC taraması")
