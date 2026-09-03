"""Yetim yardımcılar.

Kullanıcı gece uygulamayı kapatınca arka planda koşan yardımcılar süreçle
birlikte ölüyor: ana günlükte subagent_start var, subagent_end yok. Sabah
hiçbir haber verilmezse kullanıcı "ne oldu bilmiyorum" kalıyor; panel de
bayat "çalışıyor" gösterebiliyordu. Buradaki testler açılış taramasını
(yetim_tara), mezar taşını (yetim_isaretle), deftere alma + harness notunu
(adopt_orphans) ve panel tohumunu (snapshot kanalları) doğruluyor.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dornick.events import EventLog
from dornick.loop import ChildHandle, mark_orphan, yetim_tara
from tests.test_loop import (  # noqa: F401
    FakeClient,
    build_agent,
    registry,
    text_turn,
    tool_turn,
)


def _ana_gunluk(sessions_dir: Path, name: str = "20250101T000000Z") -> EventLog:
    sessions_dir.mkdir(parents=True, exist_ok=True)
    log = EventLog(sessions_dir / f"{name}.jsonl")
    log.note("session_start", session_id=name)
    return log

def _cocuk_gunluk(sessions_dir: Path, sid: str, title: str, parent: str) -> None:
    log = EventLog(sessions_dir / f"{sid}.jsonl")
    log.note("subagent_start", title=title, parent=parent)
    log.close()


# -- tarama --------------------------------------------------------------


def test_a_start_without_an_end_is_an_orphan(tmp_path: Path) -> None:
    """Çekirdek senaryo: gece kapanan uygulama, sabah açılışta bulunan iz."""
    sessions = tmp_path / "sessions"
    main = _ana_gunluk(sessions)
    main.note("subagent_start", title="gece taraması", session="20250101T000100Z")
    main.close()
    _cocuk_gunluk(sessions, "20250101T000100Z", "gece taraması", "20250101T000000Z")

    yetimler = yetim_tara(sessions)
    assert yetimler == [{"title": "gece taraması", "session": "20250101T000100Z"}]


def test_a_finished_helper_is_not_an_orphan(tmp_path: Path) -> None:
    sessions = tmp_path / "sessions"
    main = _ana_gunluk(sessions)
    main.note("subagent_start", title="tarama", session="c1")
    main.note("subagent_end", title="tarama", session="c1", turns=3, tools=5)
    main.close()
    _cocuk_gunluk(sessions, "c1", "tarama", "ana")

    assert yetim_tara(sessions) == []


def test_an_old_style_end_matches_by_title(tmp_path: Path) -> None:
    """Eski kayıtlarda subagent_end oturum kimliği taşımıyordu; başlıkla
    eşleşmeli — yoksa bütün arşiv bir gecede 'yetim' kesilir."""
    sessions = tmp_path / "sessions"
    main = _ana_gunluk(sessions)
    main.note("subagent_start", title="tarama", session="c1")
    main.note("subagent_end", title="tarama", turns=3, tools=5)   # session yok
    main.close()
    _cocuk_gunluk(sessions, "c1", "tarama", "ana")

    assert yetim_tara(sessions) == []


def test_a_crashed_helper_is_not_an_orphan(tmp_path: Path) -> None:
    """subagent_failed da bir kapanış: çöküş zaten bildirildi, bir de yetim
    diye anons edilmesin."""
    sessions = tmp_path / "sessions"
    main = _ana_gunluk(sessions)
    main.note("subagent_start", title="tarama", session="c1")
    main.note("subagent_failed", title="tarama", session="c1", error="patladı")
    main.close()
    _cocuk_gunluk(sessions, "c1", "tarama", "ana")

    assert yetim_tara(sessions) == []


def test_a_missing_child_file_is_not_reported(tmp_path: Path) -> None:
    """Oturum dosyası hiç doğmamışsa sürdürülecek bir iz de yok; bildirmek
    kullanıcıya tutamayacağımız bir söz vermek olur."""
    sessions = tmp_path / "sessions"
    main = _ana_gunluk(sessions)
    main.note("subagent_start", title="tarama", session="hic-dogmadi")
    main.close()

    assert yetim_tara(sessions) == []


def test_child_logs_are_not_scanned_as_main_sessions(tmp_path: Path) -> None:
    """Çocuk oturumun kendi günlüğü ana oturum sanılmamalı: içindeki
    parent'lı subagent_start onu ele veriyor."""
    sessions = tmp_path / "sessions"
    main = _ana_gunluk(sessions)
    main.note("subagent_start", title="tarama", session="zzz-cocuk")
    main.close()
    # Çocuk günlüğünde de (kendi açısından) end'siz bir start var; ana
    # sanılsaydı meta'sında session olmadığı için aday üretmezdi ama yine
    # de bilinçli sınanıyor: tek yetim, ana günlükten bulunan.
    _cocuk_gunluk(sessions, "zzz-cocuk", "tarama", "20250101T000000Z")

    yetimler = yetim_tara(sessions)
    assert [y["session"] for y in yetimler] == ["zzz-cocuk"]


def test_marking_prevents_a_second_report(tmp_path: Path) -> None:
    """İkinci açılış aynı yetimi yeniden bildirmemeli: çocuk günlüğüne
    düşen subagent_end(orphaned=True) mezar taşıdır."""
    sessions = tmp_path / "sessions"
    main = _ana_gunluk(sessions)
    main.note("subagent_start", title="tarama", session="c1")
    main.close()
    _cocuk_gunluk(sessions, "c1", "tarama", "ana")

    yetimler = yetim_tara(sessions)
    assert len(yetimler) == 1

    mark_orphan(sessions, yetimler)
    # İşaret çocuk günlüğünde ve orphaned taşıyor.
    text = (sessions / "c1.jsonl").read_text(encoding="utf-8")
    assert "subagent_end" in text and '"orphaned":true' in text.replace(" ", "")
    # İkinci tarama: sessizlik.
    assert yetim_tara(sessions) == []


def test_a_torn_last_line_does_not_break_the_scan(tmp_path: Path) -> None:
    """Sert kapanış son satırı yarım bırakabilir; tarama ve işaretleme yine
    çalışmalı (EventLog bozuk satırda açılmıyor, elle ekleme devreye girer)."""
    sessions = tmp_path / "sessions"
    main = _ana_gunluk(sessions)
    main.note("subagent_start", title="tarama", session="c1")
    main.close()
    _cocuk_gunluk(sessions, "c1", "tarama", "ana")
    with (sessions / "c1.jsonl").open("a", encoding="utf-8") as fh:
        fh.write('{"seq": 99, "ts": "yarim')   # kesik satır, newline yok

    yetimler = yetim_tara(sessions)
    assert len(yetimler) == 1

    mark_orphan(sessions, yetimler)
    assert yetim_tara(sessions) == []


# -- deftere alma + harness notu -----------------------------------------


async def test_adopt_orphans_registers_and_briefs_the_model(
    tmp_path: Path, registry
) -> None:
    client = FakeClient(text_turn("gördüm, kullanıcıya haber veririm"))
    agent = build_agent(tmp_path, client, registry)

    adopted = agent.adopt_orphans(
        [{"title": "gece taraması", "session": "c1"}])

    assert len(adopted) == 1
    handle = adopted[0]
    assert handle.state == "yetim" and handle.session_id == "c1"
    assert handle.bildirildi, "yetim için ayrıca bildirim turu açılmamalı"
    assert handle.id in agent._children

    # Harness notu ilk turun başında modelin önüne düşüyor.
    await agent.run("günaydın")
    first_request = str(client.seen_messages[0])
    assert "yarım kaldı" in first_request
    assert "gece taraması" in first_request
    assert "task_say" in first_request


async def test_task_say_resumes_an_adopted_orphan(tmp_path: Path, registry) -> None:
    """Kullanıcı 'sürdür' derse: yetim handle'ı task_say diskteki oturumdan
    diriltebilmeli — bitmiş yardımcıyla aynı yol."""
    client = FakeClient(text_turn("kaldığım yerden devam ettim"))
    agent = build_agent(tmp_path, client, registry)
    sid = "20250101T000100Z"
    _cocuk_gunluk(agent.config.sessions_dir, sid, "gece taraması", "ana")

    (handle,) = agent.adopt_orphans([{"title": "gece taraması", "session": sid}])
    ok, msg = agent._child_say(handle.id, "kaldığın yerden sürdür")
    assert ok, msg
    await handle.task

    assert handle.state == "bitti"
    assert "devam ettim" in handle.sonuc
    text = (agent.config.sessions_dir / f"{sid}.jsonl").read_text(encoding="utf-8")
    assert "session_resume" in text


async def test_bridge_resume_task_resumes_orphan(tmp_path: Path, registry) -> None:
    """UI 'Devam et' → Bridge.resume_task → _child_say (HTTP thread güvenli)."""
    import asyncio

    from dornick.desktop import Bridge

    class _Hub:
        def emit(self, *_a, **_k):
            pass

    client = FakeClient(text_turn("panelden sürdürüldü"))
    agent = build_agent(tmp_path, client, registry)
    sid = "20250101T000200Z"
    _cocuk_gunluk(agent.config.sessions_dir, sid, "Market Lens", "ana")
    (handle,) = agent.adopt_orphans([{"title": "Market Lens", "session": sid}])

    bridge = Bridge(_Hub(), asyncio.get_running_loop())
    bridge.agent = agent

    # resume_task call_soon + wait kullanır — döngü thread'inde çağırma.
    result = await asyncio.to_thread(bridge.resume_task, "c:" + handle.id)
    assert result.get("ok"), result
    await handle.task
    assert handle.state == "bitti"
    assert "sürdürüldü" in handle.sonuc

    missing = await asyncio.to_thread(bridge.resume_task, "c:yokid")
    assert missing.get("ok") is False

    running = ChildHandle(id="run1", title="koşan", model="m",
                          session_id="x", state="kosuyor")
    agent._children["run1"] = running
    busy = await asyncio.to_thread(bridge.resume_task, "c:run1")
    assert busy.get("ok") is False
    assert "koşuyor" in (busy.get("error") or "").lower() or "zaten" in (
        busy.get("error") or "").lower()


def test_gorevler_marks_orphans_as_resumable(tmp_path: Path, registry) -> None:
    """Canlı liste surdurulebilir bayrağını yetim satırına koyar."""
    import asyncio

    from dornick.desktop import Bridge

    class _Hub:
        def emit(self, *_a, **_k):
            pass

    async def scenario() -> dict:
        agent = build_agent(tmp_path, FakeClient(), registry)
        agent._children["y1"] = ChildHandle(
            id="y1", title="yarım", model="", arka_plan=True,
            state="yetim", session_id="sess1", sonuc="yarım kaldı")
        agent._children["r1"] = ChildHandle(
            id="r1", title="koşan", model="m", arka_plan=True,
            state="kosuyor", session_id="sess2")
        bridge = Bridge(_Hub(), asyncio.get_running_loop())
        bridge.agent = agent
        return bridge.tasks()

    payload = asyncio.run(scenario())
    by_id = {r["id"]: r for r in payload["gorevler"]}
    assert by_id["c:y1"]["surdurulebilir"] is True
    assert by_id["c:r1"]["surdurulebilir"] is False
    assert by_id["c:r1"]["durdurulabilir"] is True


# -- panel tohumu (snapshot kanalları) ------------------------------------


def test_snapshot_channels_mirror_the_ledger(tmp_path: Path, registry) -> None:
    """Panel açılışta bu listeyle kurulur: koşan 'run', biten 'done',
    yetim 'yetim', hata 'fail' — snapshot'ta olmayan kanal çizilmez."""
    from dornick.desktop import _live_channels

    agent = build_agent(tmp_path, FakeClient(), registry)
    agent._children["a1"] = ChildHandle(id="a1", title="koşan", model="m",
                                        arka_plan=True)
    agent._children["b2"] = ChildHandle(id="b2", title="biten", model="m",
                                        state="bitti", sonuc="üç dosya bulundu")
    agent._children["c3"] = ChildHandle(id="c3", title="yarım", model="",
                                        arka_plan=True, state="yetim",
                                        sonuc="Uygulama kapanınca yarım kaldı.")
    agent._children["d4"] = ChildHandle(id="d4", title="çöken", model="m",
                                        state="hata", sonuc="patladı")

    rows = {r["id"]: r for r in _live_channels(agent)}
    assert rows["a1"]["state"] == "run" and rows["a1"]["ozet"] == ""
    assert rows["b2"]["state"] == "done" and "üç dosya" in rows["b2"]["ozet"]
    assert rows["c3"]["state"] == "yetim" and rows["c3"]["bg"]
    assert rows["d4"]["state"] == "fail"

    # Ajansız (model yapılandırılmamış) açılışta sessizce boş.
    assert _live_channels(None) == []
    assert _live_channels(object()) == []


def test_the_bridge_snapshot_carries_the_channel_list(tmp_path: Path, registry) -> None:
    import asyncio

    from dornick.desktop import Bridge

    class _Hub:
        def __init__(self) -> None:
            self.events: list[dict] = []

        def emit(self, payload: dict) -> None:
            self.events.append(payload)

    async def scenario() -> dict:
        agent = build_agent(tmp_path, FakeClient(), registry)
        agent._children["y1"] = ChildHandle(id="y1", title="gece işi", model="",
                                            arka_plan=True, state="yetim")
        bridge = Bridge(_Hub(), asyncio.get_running_loop())
        bridge.agent = agent
        return bridge.snapshot()

    snap = asyncio.run(scenario())
    assert snap["channels"] == [{
        "id": "y1", "title": "gece işi", "model": "", "bg": True,
        "kind": "yardımcı", "state": "yetim", "ozet": "",
    }]


# -- arayüz sözleşmesi ----------------------------------------------------

STATIC = Path(__file__).resolve().parents[1] / "src" / "dornick" / "web" / "static"


def test_the_deck_seeds_from_the_snapshot() -> None:
    """app.js açılışta kanalları orkestraya tohumluyor; orkestra hayalet
    'çalışıyor' kartı bırakmamak için haritayı baştan kuruyor."""
    app_js = (STATIC / "app.js").read_text(encoding="utf-8")
    orch_js = (STATIC / "orchestra.js").read_text(encoding="utf-8")

    assert "orchSeed(s.channels || [])" in app_js
    # Açılışta yetim bulununca sunucu gerçek listeyi olayla da gönderiyor
    # (sayfa snapshot'ı ajan hazır olmadan çekmiş olabilir) ve kopan SSE
    # geri gelince açık sekme kendini tazeliyor.
    assert 'case "channels": orchSeed(e.channels || [])' in app_js
    assert "resyncChannels" in app_js
    assert "channels.clear()" in orch_js          # hayaletler silinir
    assert '"Yarım kaldı"' in orch_js             # yetim durumu çiziliyor
    assert '"Yarım kaldı": "Left unfinished"' in orch_js   # EN çevirisi
    assert "/api/gorevler/devam" in orch_js
    assert "Devam et" in orch_js

    gorev_js = (STATIC / "gorevler.js").read_text(encoding="utf-8")
    assert "/api/gorevler/devam" in gorev_js
    assert "surdurulebilir" in gorev_js or 'durum === "yetim"' in gorev_js

    server = (Path(__file__).resolve().parents[1]
              / "src" / "dornick" / "web" / "server.py").read_text(encoding="utf-8")
    assert "/api/gorevler/devam" in server
    assert "resume_task" in (
        Path(__file__).resolve().parents[1] / "src" / "dornick" / "desktop.py"
    ).read_text(encoding="utf-8")

    css = (STATIC / "app.css").read_text(encoding="utf-8")
    # İki temada da çalışan token'larla: yetim durumu görsel dile bağlı.
    assert ".orch-ch.yetim" in css and "--amber" in css
    assert ".task-resume" in css and ".orch-resume" in css
