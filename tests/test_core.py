"""Harness'ın sessizce bozulabilecek kısımlarının testleri.

Buradaki her test, üretimde fark edilmesi zor bir hataya karşılık gelir:
eksik tool_result (400), ıskalanan önbellek (sessiz maliyet), budanmayan
görüntüler (bağlam patlaması), atlanan izin kapısı (güvenlik).
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from dornick.config import Config
from dornick.context import place_breakpoints, prune_images
from dornick.events import EventLog
from dornick.permissions import Decision, PermissionEngine
from dornick.session import Session, cancelled_result
from dornick.tools import ToolContext, ToolRegistry, ToolResult, execute, object_schema
from dornick.tools.base import ToolSpec


# -- olay günlüğü ------------------------------------------------------


def test_event_log_survives_reopen(tmp_path: Path) -> None:
    path = tmp_path / "s.jsonl"
    with EventLog(path) as log:
        log.message("user", [{"type": "text", "text": "merhaba"}])
        log.note("tool_start", tool="shell")

    reopened = EventLog(path)
    assert len(reopened) == 2
    assert len(reopened.messages()) == 1
    assert reopened.notes("tool_start")[0].meta["tool"] == "shell"
    # Sıra numarası kaldığı yerden devam etmeli, çakışmamalı.
    assert reopened.append("meta", content="x").seq == 2
    reopened.close()


def test_meta_keys_may_shadow_event_fields(tmp_path: Path) -> None:
    """meta **kwargs olsaydı "kind" adlı bir alan çağrıyı TypeError ile düşürürdü.

    Zihin kayıtları gerçekten "kind" gönderiyor; bu üretimde her hatıra
    yazımında patlıyordu ve yürütücünün geniş except'i hatayı yutuyordu.
    """
    log = EventLog(tmp_path / "s.jsonl")
    event = log.note("mind_write", kind="preference", role="x", content="y")

    assert event.content == "mind_write"
    assert event.meta == {"kind": "preference", "role": "x", "content": "y"}
    log.close()


# -- oturum / kesme güvenliği -----------------------------------------


def _session(tmp_path: Path) -> Session:
    return Session(EventLog(tmp_path / "s.jsonl"), "test")


def test_pending_tool_uses_finds_unanswered(tmp_path: Path) -> None:
    s = _session(tmp_path)
    s.add_user_text("iki şey yap")
    s.add_assistant(
        [
            {"type": "tool_use", "id": "a", "name": "shell", "input": {"command": "ls"}},
            {"type": "tool_use", "id": "b", "name": "shell", "input": {"command": "pwd"}},
        ]
    )
    s.add_tool_results([{"type": "tool_result", "tool_use_id": "a", "content": "ok"}])

    pending = s.pending_tool_uses()
    assert [p.id for p in pending] == ["b"]

    # İptal sonucu enjekte edilince açık kalan kalmamalı.
    s.add_tool_results([cancelled_result(p.id) for p in pending])
    assert s.pending_tool_uses() == []


def test_system_note_needs_user_turn_first(tmp_path: Path) -> None:
    s = _session(tmp_path)
    s.add_system_note("ilk mesaj olamaz")
    assert s.messages() == []

    s.add_user_text("selam")
    s.add_system_note("bu geçerli")
    assert [m["role"] for m in s.messages()] == ["user", "system"]


def test_resume_son_kullanilan_oturumu_aciyor(tmp_path: Path) -> None:
    """`--resume` en son AÇILAN'ı değil en son KULLANILAN'ı sürdürmeli.

    Kullanıcı geçmişten eski bir konuşmaya dönüp oradan devam ettiğinde
    ada göre sıralama, yeniden başlatmada onu bambaşka bir konuşmaya
    atıyordu — canlıda birebir bu yaşandı.
    """
    import os

    eski = tmp_path / "20260827T095449Z.jsonl"   # önce açıldı, SON kullanıldı
    yeni = tmp_path / "20260827T101349Z.jsonl"   # sonra açıldı, bırakıldı
    for yol in (eski, yeni):
        yol.write_text("", encoding="utf-8")
    os.utime(yeni, (1_700_000_000, 1_700_000_000))
    os.utime(eski, (1_700_003_600, 1_700_003_600))

    oturum = Session.latest(tmp_path)
    assert oturum is not None
    assert oturum.id == "20260827T095449Z"

    bos = tmp_path / "bos"
    bos.mkdir()
    assert Session.latest(bos) is None, "boş klasörde patlamamalı"


# -- önbellek breakpoint'leri -----------------------------------------


def _msg(role: str, n: int) -> dict:
    return {"role": role, "content": [{"type": "text", "text": f"b{i}"} for i in range(n)]}


def test_breakpoints_respect_limit_and_cover_tail() -> None:
    messages = [_msg("user", 8) for _ in range(10)]  # 80 blok
    place_breakpoints(messages, limit=3, stride=15)

    marked = [i for i, m in enumerate(messages) if "cache_control" in m["content"][-1]]
    assert len(marked) <= 3
    # Son mesaj her zaman işaretli olmalı: yeni yazılan önek orası.
    assert len(messages) - 1 in marked


def test_breakpoint_gap_stays_under_lookback_window() -> None:
    """İki breakpoint arası 20 bloğu aşarsa önbellek sessizce ıskalar."""
    messages = [_msg("user", 4) for _ in range(12)]  # 48 blok
    place_breakpoints(messages, limit=3, stride=15)

    cumulative, gaps, last = 0, [], 0
    for m in messages:
        cumulative += len(m["content"])
        if "cache_control" in m["content"][-1]:
            gaps.append(cumulative - last)
            last = cumulative

    assert gaps, "hiç breakpoint konmadı"
    assert max(gaps) <= 20


def test_breakpoints_are_cleared_before_replacement() -> None:
    messages = [_msg("user", 5) for _ in range(6)]
    place_breakpoints(messages, limit=3, stride=15)
    messages.append(_msg("assistant", 5))
    place_breakpoints(messages, limit=3, stride=15)

    total = sum(
        1 for m in messages for b in m["content"] if "cache_control" in b
    )
    assert total <= 3, "eski breakpoint'ler temizlenmemiş"


# -- görüntü budama ---------------------------------------------------


def _image() -> dict:
    return {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "x"}}


def test_prune_images_keeps_only_recent() -> None:
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": f"t{i}", "content": [_image()]}
            ],
        }
        for i in range(5)
    ]
    prune_images(messages, keep=2)

    kinds = [m["content"][0]["content"][0]["type"] for m in messages]
    assert kinds == ["text", "text", "text", "image", "image"]


# -- izinler ----------------------------------------------------------


def _spec(name: str, mutates: bool) -> ToolSpec:
    async def handler(args, ctx):  # pragma: no cover - çağrılmıyor
        return ToolResult("ok")

    return ToolSpec(name, "d", object_schema({}), handler, mutates=mutates)


def test_deny_beats_allow() -> None:
    engine = PermissionEngine("yolo", allow=["*"], deny=["shell:rm *"])
    decision, _ = engine.evaluate(_spec("shell", True), {"command": "rm -rf /"})
    assert decision is Decision.DENY


def test_plan_mode_blocks_mutation_only() -> None:
    engine = PermissionEngine("plan", allow=[], deny=[])
    assert engine.evaluate(_spec("write_file", True), {"path": "a"})[0] is Decision.DENY
    assert engine.evaluate(_spec("read_file", False), {"path": "a"})[0] is Decision.ALLOW


def test_auto_mode_asks_only_for_mutation() -> None:
    engine = PermissionEngine("auto", allow=[], deny=[])
    assert engine.evaluate(_spec("shell", True), {"command": "ls"})[0] is Decision.ASK
    assert engine.evaluate(_spec("list_dir", False), {"path": "."})[0] is Decision.ALLOW


def test_remember_allow_creates_matching_rule() -> None:
    engine = PermissionEngine("ask", allow=[], deny=[])
    spec = _spec("shell", True)
    engine.remember_allow(spec, {"command": "git status"})
    assert engine.evaluate(spec, {"command": "git status"})[0] is Decision.ALLOW


# -- yürütücü ---------------------------------------------------------


@pytest.fixture()
def ctx(tmp_path: Path) -> ToolContext:
    config = Config.load(tmp_path)
    config.ensure_dirs()
    return ToolContext(config=config, session=_session(tmp_path), cancel=asyncio.Event())


async def test_every_call_gets_a_result_even_when_unknown_or_denied(ctx: ToolContext) -> None:
    """Eksik bir tool_result bir sonraki isteği 400 ile düşürür."""
    from dornick.session import PendingToolUse

    registry = ToolRegistry()

    @registry.tool("ok_tool", "çalışır", object_schema({}))
    async def _ok(args, _ctx):
        return ToolResult("tamam")

    @registry.tool("bad_tool", "patlar", object_schema({}), mutates=True)
    async def _bad(args, _ctx):
        raise RuntimeError("beklenmedik")

    calls = [
        PendingToolUse("1", "ok_tool", {}),
        PendingToolUse("2", "yok_boyle_arac", {}),
        PendingToolUse("3", "bad_tool", {}),
    ]

    async def approve(spec, args):
        return False  # bad_tool reddedilecek

    blocks = await execute(
        calls,
        registry=registry,
        permissions=PermissionEngine("ask", allow=["ok_tool:*"], deny=[]),
        ctx=ctx,
        approve=approve,
    )

    assert [b["tool_use_id"] for b in blocks] == ["1", "2", "3"]
    assert blocks[0]["is_error"] is False
    assert "yok_boyle_arac" in blocks[1]["content"]  # bilinmeyen araç öğretici hata
    assert blocks[2]["is_error"] is True  # reddedildi


async def test_handler_exception_does_not_kill_the_loop(ctx: ToolContext) -> None:
    from dornick.session import PendingToolUse

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
    assert blocks[0]["is_error"] is True
    assert "ValueError" in blocks[0]["content"]


async def test_stop_cancels_a_pending_approval(ctx: ToolContext) -> None:
    """İzin kartı açıkken Durdur: tur onay bekleyişinde asılı kalmıyor.

    Canlı yara (01.09): kart cevapsız kaldığında Durdur dahil hiçbir şey
    turu kurtaramıyordu — bekleyiş artık kesme olayıyla yarıştırılıyor.
    """
    from dornick.session import PendingToolUse

    registry = ToolRegistry()
    kostu = False

    @registry.tool("sorulan", "sorar", object_schema({}), mutates=True)
    async def _sorulan(args, _ctx):
        nonlocal kostu
        kostu = True
        return ToolResult("olmamalıydı")

    async def cevapsiz_kart(spec, args):
        await asyncio.sleep(3600)
        return True

    async def durdur():
        await asyncio.sleep(0.05)
        ctx.cancel.set()

    stop = asyncio.ensure_future(durdur())
    blocks = await asyncio.wait_for(
        execute(
            [PendingToolUse("1", "sorulan", {})],
            registry=registry,
            permissions=PermissionEngine("ask", allow=[], deny=[]),
            ctx=ctx,
            approve=cevapsiz_kart,
        ),
        timeout=5,
    )
    await stop
    assert not kostu, "onaysız çağrı çalışmamalı"
    assert blocks[0]["tool_use_id"] == "1"
    assert blocks[0]["is_error"] is True


# -- eksik öncül -------------------------------------------------------
#
# "Yarın hava nasıl?" sorusuna model İstanbul'u varsayıp cevap vermişti.
# Kullanıcı İstanbul'da olmayabilir ve varsayım cevabın içine gizlenmişti:
# yanlış olduğu bile anlaşılmıyordu.


def test_the_prompt_says_what_day_it_is(tmp_path: Path) -> None:
    """"Yarın" sorusunun cevabı bugünün ne olduğuna bağlı ve model bunu
    hiçbir yerden öğrenemiyordu."""
    from datetime import datetime

    from dornick import prompt as builder

    text = builder._environment(Config.load(tmp_path))
    today = datetime.now().astimezone()

    assert f"{today:%d.%m.%Y}" in text
    assert builder.DAYS[today.weekday()] in text


def test_the_prompt_says_where_the_machine_is(tmp_path: Path) -> None:
    """Saat dilimi ülkeyi söylüyor — şehri değil. Ayrım kasıtlı: makinenin
    bildiği kadarı veriliyor, gerisi soruluyor."""
    from dornick import prompt as builder

    text = builder._environment(Config.load(tmp_path))
    assert "Saat dilimi:" in text and "UTC" in text


def test_the_day_name_is_turkish_whatever_the_system_language(tmp_path: Path) -> None:
    """`strftime("%A")` sistemin diline bağlı ve İngilizce dönebiliyor;
    istemde karışık dil istemiyoruz."""
    from dornick import prompt as builder

    assert builder.DAYS[0] == "Pazartesi"
    assert all(day.isalpha() for day in builder.DAYS)


def test_the_prompt_forbids_inventing_a_missing_premise() -> None:
    """Her soru için ayrı kural yazmak ölçeklenmiyor; tek bir ilke var."""
    from dornick import prompt as builder

    assert "Eksik öncül" in builder.IDENTITY
    # Üç basamak: zihnine bak, kendin bul, soramıyorsan sor.
    assert "mind_recall" in builder.IDENTITY
    assert "tek cümlelik bir soru sor" in builder.IDENTITY


def test_the_prompt_forbids_the_youre_welcome_loop() -> None:
    """Teşekkür / tamamdır / bakayım → 'rica ederim' asistan döngüsü."""
    from dornick import prompt as builder

    assert "Rica ederim" in builder.IDENTITY
    assert "tamamdır" in builder.IDENTITY
    assert "cevap yazma" in builder.IDENTITY
    assert "Rica ederim" in builder.LEAN_IDENTITY


def test_the_prompt_asks_before_forgetting_memories_tied_to_a_deleted_device() -> None:
    """Cihaz silinince anılar sessizce kalıyordu; kullanıcı 'hafızadan da
    sil' demek zorunda kalıyordu. Sormak kural: dursun mu, sileyim mi?"""
    from dornick import prompt as builder

    assert "dursun mu, sileyim mi" in builder.IDENTITY


def test_big_open_ended_work_must_lead_with_a_visible_plan() -> None:
    """Kanıtlanmış atlama: 55 dakikalık bir işte ilk mesaj plansız geldi.

    Kural artık öneri değil sıra kuralı: İLK yazılan şey modül planı ve
    kabul ölçütleri; "kafandaki plan sayılmaz". Uzun koşuda anlatım ritmi
    de bağlayıcı — her kilometre taşında kullanıcıya bir cümle durum.
    """
    from dornick import prompt as builder

    duz = " ".join(builder.IDENTITY.split())   # satır kırılımından bağımsız
    assert "İLK yazdığın şey modül planı ve kabul ölçütleridir" in duz
    assert "planı yazmadan koda başlama" in duz
    assert "kafandaki plan sayılmaz" in duz
    # Anlatım ritmi: kullanıcı dakikalarca sessizliğe bakmamalı.
    assert "her kilometre taşında kullanıcıya bir cümle durum yaz" in duz


def test_the_long_run_checkpoint_also_addresses_the_user() -> None:
    """Kontrol noktası kullanıcıya konuşur ve kabul edilince end_turn serbest."""
    from dornick.loop import CHECKPOINT_NOTE

    assert "kullanıcıya da yaz" in CHECKPOINT_NOTE
    assert "end_turn" in CHECKPOINT_NOTE
    assert "iş bitmeden durma" not in CHECKPOINT_NOTE


# -- eski araç yüklerinin kısaltılması ----------------------------------


def _talk(n_old: int, big: str):
    """n_old eski mesaj + 6 taze mesaj; ilkinde dev bir write_file turu."""
    from copy import deepcopy

    old = [
        {"role": "assistant", "content": [
            {"type": "tool_use", "id": "c1", "name": "write_file",
             "input": {"path": "site/index.html", "content": big}}]},
        {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "c1", "content": big}]},
    ] * max(1, n_old // 2)
    fresh = [{"role": "user", "content": [{"type": "text", "text": f"m{i}"}]}
             for i in range(6)]
    return deepcopy(old + fresh)


def test_old_tool_payloads_are_trimmed_but_the_tail_is_not() -> None:
    """Ölçülen yara: HTML'in tamamı write_file argümanında geçmişe girip
    SONRAKİ HER istekle yeniden gidiyordu (51.6k'lık istemin ~12-14k'sı).
    Dosya diskte; geçmişte iz yeter — gerekirse read_file ile açılır."""
    from dornick.context import TRIM_TOOL_CHARS, prune_tool_payloads

    big = "x" * 10_000
    messages = _talk(2, big)
    fresh_big = {"role": "assistant", "content": [
        {"type": "tool_use", "id": "c9", "name": "write_file",
         "input": {"path": "yeni.html", "content": big}}]}
    messages.append(fresh_big)

    prune_tool_payloads(messages)

    trimmed = messages[0]["content"][0]["input"]["content"]
    assert len(trimmed) < TRIM_TOOL_CHARS + 200
    assert "kısaltıldı" in trimmed
    assert trimmed.startswith("x")            # baş korunur
    assert trimmed.endswith("x")              # son korunur
    # Küçük argümanlara dokunulmaz: yol olduğu gibi.
    assert messages[0]["content"][0]["input"]["path"] == "site/index.html"
    # Sonuç bloğu da kısaldı.
    assert "kısaltıldı" in messages[1]["content"][0]["content"]
    # Kuyruktaki TAZE dev içerik olduğu gibi durur.
    assert messages[-1]["content"][0]["input"]["content"] == big


def test_trimming_is_deterministic_for_the_cache() -> None:
    """Aynı geçmiş her istekte aynı bayta inmeli — önek önbelleği
    istekten isteğe tutmaya devam etsin."""
    import json

    from dornick.context import prune_tool_payloads

    big = "y" * 8_000
    a, b = _talk(4, big), _talk(4, big)
    prune_tool_payloads(a)
    prune_tool_payloads(b)
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_browser_dumps_are_trimmed_more_aggressively() -> None:
    """Browser HTML dump'ları keep=2 dışında agresif kısaltılır."""
    from dornick.context import TRIM_BROWSER_CHARS, prune_tool_payloads

    html = "<html>" + ("z" * 5_000) + "</html>"
    messages = [
        {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "b1", "content": html}]},
        {"role": "assistant", "content": "ok1"},
        {"role": "user", "content": "devam"},
        {"role": "assistant", "content": "ok2"},
        {"role": "user", "content": "son"},
        {"role": "assistant", "content": "ok3"},
    ]
    prune_tool_payloads(messages)
    trimmed = messages[0]["content"][0]["content"]
    assert len(trimmed) < TRIM_BROWSER_CHARS + 200
    assert "kısaltıldı" in trimmed


def test_trimming_flows_through_prepare() -> None:
    """Politika hattına gerçekten bağlı: prepare edilen istek küçülür,
    ham günlük değişmez."""
    from dornick.config import ContextConfig
    from dornick.context import ContextPolicy
    from dornick.prompt import SystemPrompt

    big = "z" * 20_000
    messages = _talk(2, big)
    before = sum(len(str(m)) for m in messages)

    policy = ContextPolicy(ContextConfig())
    prepared = policy.prepare(SystemPrompt(core="test", identity=""), messages)

    after = sum(len(str(m)) for m in prepared.messages)
    assert after < before * 0.4               # ciddi küçülme
    # Ham geçmiş (olay günlüğünün gerçeği) el sürülmemiş.
    assert messages[0]["content"][0]["input"]["content"] == big


def test_prompt_tells_the_model_to_match_the_user_language() -> None:
    """Yönergeler Türkçe yazıldı diye model Türkçe cevaplamamalı.

    Canlı yara (02.09): arayüz dili İngilizceyken ve kullanıcı İngilizce
    yazarken ajan Türkçe cevap veriyordu — sistem promptunun tamamı Türkçe
    olduğu için. Kural üslubun parçası: kimlik bloğunda, "nasıl konuşursun"
    başlığının ilk maddesi.
    """
    from dornick import prompt as builder

    kimlik = builder.IDENTITY
    assert "KULLANICININ YAZDIĞI DİLDE" in kimlik
    # Kuralın yeri önemli: üslup bölümünün başında olmalı ki ağırlığı olsun.
    nasil = kimlik.find("Nasıl konuşursun:")
    dil = kimlik.find("KULLANICININ YAZDIĞI DİLDE")
    gercek = kimlik.find("Gerçek biri gibi")
    assert nasil < dil < gercek, "dil kuralı üslup bölümünün başında olmalı"
    # Ara anlatımlar ve üretilen dosyalar da aynı dilde.
    assert "ara anlatım" in kimlik and "dosyaların içeriği" in kimlik


def test_turn_carries_a_language_reminder(tmp_path: Path) -> None:
    """Cevap dili hatırlatması BU TURUN İSTEĞİNE gider, oturum günlüğüne değil.

    Canlı yara (02.09): sistem promptunun tamamı ve anıların çoğu Türkçe
    olduğu için model İngilizce yazana da Türkçe cevap veriyordu. Hatırlatma
    modelin en son okuduğu yere konuyor. Günlüğe YAZILMAMASI şart: "tur
    başına tek sistem notu" kotası hatırlama notunun (`_prime_recall`)
    hakkı — testler bunu bir regresyonda yakaladı.
    """
    from types import SimpleNamespace

    from dornick.loop import Agent

    session = _session(tmp_path)
    session.add_user_text("baslangic")

    ajan = Agent.__new__(Agent)
    ajan.session = session

    # İngilizce girdi → İngilizce hatırlatma, günlüğe dokunulmadan.
    onceki = len(session.messages())
    ajan._dil_notu("Please write a short report about solar batteries.")
    assert len(session.messages()) == onceki, "günlüğe yazılmamalı"

    hazir = SimpleNamespace(messages=[])
    ajan._dil_hatirlatmasini_ekle(hazir)
    assert hazir.messages and hazir.messages[-1]["role"] == "system"
    assert "SAME language" in str(hazir.messages[-1]["content"])

    # Türkçe girdi → Türkçe hatırlatma.
    ajan._dil_notu("Bana güneş pilleri hakkında kısa bir rapor yazar mısın?")
    hazir2 = SimpleNamespace(messages=[])
    ajan._dil_hatirlatmasini_ekle(hazir2)
    assert "TÜRKÇE" in str(hazir2.messages[-1]["content"])

    # Çok kısa girdide çıkarım yok: hiçbir şey eklenmiyor.
    ajan._dil_notu("ok")
    hazir3 = SimpleNamespace(messages=[])
    ajan._dil_hatirlatmasini_ekle(hazir3)
    assert hazir3.messages == []
