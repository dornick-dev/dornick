"""Zihin katmanı testleri.

Odak: kalıcılık (yeniden açınca kaybolmuyor mu), arama isabeti, ve zihnin
döngüye gerçekten bağlanıp bağlanmadığı.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
from pathlib import Path

import pytest

from dornick.config import Config
from dornick.events import EventLog
from dornick.mind import Mind, open_mind
from dornick.mind.search import rank, tokenize
from dornick.session import PendingToolUse, Session
from dornick.tools import ToolContext, build_registry, execute
from dornick.permissions import PermissionEngine


@pytest.fixture()
def mind(tmp_path: Path) -> Mind:
    return open_mind(tmp_path / "mind", tmp_path / "sessions", "cur")


# -- sıralama ----------------------------------------------------------


def test_stopwords_are_dropped() -> None:
    assert "ve" not in tokenize("kahve ve çay")
    assert "kahve" in tokenize("kahve ve çay")


def test_rare_terms_outrank_common_ones() -> None:
    items = [
        "dosya okuma hakkında not",
        "dosya yazma hakkında not",
        "dosya silme ve postgres bağlantısı hakkında not",
    ]
    hits = rank("postgres dosya", items, text_of=lambda s: s, limit=3)
    # "dosya" her belgede var, "postgres" nadir — nadir olan sıralamayı belirlemeli.
    assert "postgres" in hits[0].item


@pytest.mark.parametrize(
    ("query", "document"),
    [
        ("rapor", "raporları hazırladım"),      # sorgu kök, belge ekli
        ("raporları", "rapor formatı"),          # sorgu ekli, belge kök
        ("yedek", "yedeklemeyi otomatikleştir"), # araya ek girmiş
        ("dosya", "dosyaların listesi"),
    ],
)
def test_suffixed_forms_match_the_stem(query: str, document: str) -> None:
    """Türkçe sondan eklemeli — tam sözcük eşleşmesi aramanın yarısını kaybettirir."""
    hits = rank(query, [document, "tamamen alakasız bir metin"], text_of=lambda s: s)
    assert hits and hits[0].item == document


def test_short_words_do_not_prefix_match() -> None:
    """Kısa sözcükler için ön ek eşleşmesi gürültü üretir; birebir olmalı."""
    hits = rank("kar", ["karpuz kavun", "kar yağıyor"], text_of=lambda s: s)
    assert [h.item for h in hits] == ["kar yağıyor"]


def test_empty_query_returns_newest_first(mind: Mind) -> None:
    mind.remember("ilk", title="ilk")
    mind.remember("ikinci", title="ikinci")
    hits = mind.recall("", limit=2)
    assert hits[0].item.title == "ikinci"


# -- semantik bellek ---------------------------------------------------


def test_memories_survive_reopen(tmp_path: Path) -> None:
    first = open_mind(tmp_path / "mind", tmp_path / "sessions", "s1")
    saved = first.remember(
        "Kullanıcı PowerShell kullanıyor, bash değil.", kind="preference", tags=["kabuk"]
    )

    reopened = open_mind(tmp_path / "mind", tmp_path / "sessions", "s2")
    assert [m.id for m in reopened.memories()] == [saved.id]
    assert reopened.memories()[0].kind == "preference"


def test_forget_is_a_tombstone_not_a_deletion(tmp_path: Path) -> None:
    mind = open_mind(tmp_path / "mind", tmp_path / "sessions")
    memory = mind.remember("yanlış bir bilgi")
    mind.forget(memory.id)

    assert mind.memories() == []
    assert mind.forget(memory.id) is None  # iki kez silinmez

    # Mezar taşı: kayıt silinmedi, işaretlendi. Neyin ne zaman unutulduğu
    # da zihnin parçası; depo artık indeksli olduğu için işaret orada.
    with sqlite3.connect(tmp_path / "mind" / "recall.db") as db:
        rows = db.execute("SELECT deleted FROM node WHERE id=?", (memory.id,)).fetchall()
    assert rows == [(1,)]


def test_recall_filters_by_kind(mind: Mind) -> None:
    mind.remember("git rebase yordamı", kind="procedure", title="rebase")
    mind.remember("git hakkında bir olgu", kind="fact", title="olgu")

    hits = mind.recall("git", kind="procedure")
    assert [h.item.title for h in hits] == ["rebase"]


# -- hedefler ----------------------------------------------------------


def test_goal_lifecycle_and_digest(mind: Mind) -> None:
    a = mind.push_goal("veriyi topla")
    b = mind.push_goal("raporu yaz")

    digest = mind.goal_digest()
    assert "veriyi topla" in digest and "raporu yaz" in digest

    mind.set_goal_status(a.id, "done", note="bitti")
    assert "veriyi topla" not in mind.goal_digest()
    assert [g.id for g in mind.goals()] == [b.id]


def test_snapshot_lists_only_active_goals(mind: Mind) -> None:
    """Arayüzdeki hedef paneli sayfa yenilenince snapshot'tan tohumlanıyor:
    döküm yalnız aktifleri taşımalı — id, metin ve maddenin geçmiş bir
    oturumdan kalıp kalmadığı (`eski`). Zihinsiz ajan (ya da patlayan
    okuma) boş liste demek — sohbet düşmemeli."""
    from dornick.desktop import _active_goals

    keep = mind.push_goal("kalan iş")
    done = mind.push_goal("biten iş")
    mind.set_goal_status(done.id, "done")

    agent = type("A", (), {"mind": mind})()
    assert _active_goals(agent) == [
        {"id": keep.id, "text": "kalan iş", "eski": False}]
    assert _active_goals(type("A", (), {"mind": None})()) == []
    assert _active_goals(object()) == []


def test_goals_survive_reopen(tmp_path: Path) -> None:
    first = open_mind(tmp_path / "mind", tmp_path / "sessions")
    goal = first.push_goal("kalıcı hedef")
    first.set_goal_status(goal.id, "done")

    reopened = open_mind(tmp_path / "mind", tmp_path / "sessions")
    assert reopened.goals() == []
    assert reopened.goals(active_only=False)[0].status == "done"


# -- epizodik ----------------------------------------------------------


def _write_session(sessions: Path, name: str, user_text: str, tool: str) -> None:
    sessions.mkdir(parents=True, exist_ok=True)
    log = EventLog(sessions / f"{name}.jsonl")
    log.message("user", [{"type": "text", "text": user_text}])
    log.note("tool_start", tool=tool)
    log.message("assistant", [{"type": "text", "text": "yapıldı"}])
    log.close()


def test_episodes_search_past_sessions(tmp_path: Path) -> None:
    sessions = tmp_path / "sessions"
    _write_session(sessions, "20260101T000000Z", "postgres yedeğini al", "shell")
    _write_session(sessions, "20260102T000000Z", "tatil fotoğraflarını sırala", "list_dir")

    mind = open_mind(tmp_path / "mind", sessions, "cur")
    hits = mind.episodes("postgres yedek")

    assert hits and hits[0].item.session_id == "20260101T000000Z"
    assert "shell" in hits[0].item.tools


def test_current_session_is_excluded_from_episodes(tmp_path: Path) -> None:
    """Mevcut oturum zaten bağlamda; tekrar getirmek boşa token."""
    sessions = tmp_path / "sessions"
    _write_session(sessions, "cur", "postgres yedeğini al", "shell")

    mind = open_mind(tmp_path / "mind", sessions, "cur")
    assert mind.episodes("postgres") == []
    assert mind.episodes("postgres", include_current=True)


# -- araç yüzeyi -------------------------------------------------------


@pytest.fixture()
def ctx(tmp_path: Path, mind: Mind) -> ToolContext:
    config = Config.load(tmp_path)
    config.ensure_dirs()
    session = Session(EventLog(tmp_path / "s.jsonl"), "cur")
    return ToolContext(config=config, session=session, cancel=asyncio.Event())


async def _call(registry, ctx, name: str, args: dict, *, expect_error: bool = False) -> str:
    """Aracı çağırır ve hata durumunu doğrular.

    Yürütücü araç içindeki istisnayı yakalayıp hata sonucuna çeviriyor —
    doğru davranış, ama testte kontrol edilmezse patlayan bir araç sessizce
    'geçti' görünür. Bir kez tam olarak bu oldu.
    """
    blocks = await execute(
        [PendingToolUse("x", name, args)],
        registry=registry,
        permissions=PermissionEngine("yolo", allow=[], deny=[]),
        ctx=ctx,
        approve=lambda *_: asyncio.sleep(0, result=True),
    )
    block = blocks[0]
    assert block["is_error"] is expect_error, block["content"]
    return block["content"]


async def test_mind_tools_are_registered_only_with_a_mind(mind: Mind) -> None:
    assert "mind_recall" not in build_registry()
    assert "mind_recall" in build_registry(mind)


async def test_save_then_recall_through_the_tool_surface(ctx: ToolContext, mind: Mind) -> None:
    registry = build_registry(mind)

    await _call(
        registry,
        ctx,
        "mind_memory",
        {"action": "save", "content": "Kullanıcı raporları xlsx istiyor.", "kind": "preference"},
    )
    found = await _call(registry, ctx, "mind_recall", {"query": "rapor formatı", "scope": "memory"})

    assert "xlsx" in found


async def test_recall_says_so_when_nothing_is_known(ctx: ToolContext, mind: Mind) -> None:
    registry = build_registry(mind)
    out = await _call(registry, ctx, "mind_recall", {"query": "hiç konuşulmamış konu"})
    assert "kayıt yok" in out


async def test_introspect_flags_repeated_identical_calls(ctx: ToolContext, mind: Mind) -> None:
    """Aynı çağrıyı üst üste denemek en sık takılma biçimi; zihin bunu görmeli."""
    for _ in range(3):
        ctx.session.log.note("tool_start", tool="shell", input={"command": "make build"})
        ctx.session.log.note("tool_end", tool="shell", ms=10, error=True)

    registry = build_registry(mind)
    report = await _call(registry, ctx, "mind_introspect", {"aspect": "session"})

    assert "3+ kez aynı argümanlarla" in report
    assert "3 hata" in report


async def test_goal_tool_updates_digest(ctx: ToolContext, mind: Mind) -> None:
    registry = build_registry(mind)
    out = await _call(registry, ctx, "mind_goals", {"action": "push", "text": "testi geçir"})
    assert "testi geçir" in out
    assert mind.goals()[0].text == "testi geçir"


# -- konuşma geçmişi: anı DEĞİL, ham oturumlar -------------------------


def test_sessions_lists_past_conversations_newest_first(tmp_path):
    """Sohbet listesi: geçmiş oturumlar, en yeniden eskiye. Bu bir anı
    listesi değil — ham konuşmaların kendisi."""
    from dornick.events import EventLog
    from dornick.mind import open_mind

    sessions = tmp_path / "sessions"
    sessions.mkdir(parents=True)
    for stem, turns in [
        ("20260610T090000Z", [("user", "çorum pompa verimi ne"), ("assistant", "%72")]),
        ("20260612T140000Z", [("user", "modbus kopuyor"), ("assistant", "yeni bağlantı aç")]),
    ]:
        log = EventLog(sessions / f"{stem}.jsonl")
        for r, t in turns:
            log.append("message", role=r, content=t)
        log.close()

    mind = open_mind(tmp_path / "mind", sessions, "cur")
    got = mind.sessions()
    assert len(got) == 2
    assert got[0].session_id == "20260612T140000Z"  # en yeni başta


def test_transcript_returns_spoken_turns_with_trace(tmp_path):
    """Döküm metin turlarını VE turun izini taşıyor: araç çağrıları tek
    satırlık özet (ham argüman değil), düşünme ayrı alanda — yeniden açılan
    sohbette şerit yeniden kurulabilsin (canlı yara, 01.09)."""
    from dornick.events import EventLog
    from dornick.mind import open_mind

    sessions = tmp_path / "sessions"
    sessions.mkdir(parents=True)
    log = EventLog(sessions / "20260610T090000Z.jsonl")
    log.append("message", role="user", content="kuyu seviyesi ne kadar")
    log.append("message", role="assistant", content=[
        {"type": "thinking", "thinking": "Önce dosyaya bakayım."},
        {"type": "text", "text": "Seviye 2,77 m."},
        {"type": "tool_use", "name": "shell", "input": {"command": "cat x"}},
    ])
    log.close()

    mind = open_mind(tmp_path / "mind", sessions, "cur")
    turns = mind.transcript("20260610T090000Z")
    assert turns == [
        {"role": "user", "text": "kuyu seviyesi ne kadar"},
        {"role": "assistant", "text": "Seviye 2,77 m.",
         "dusunme": "Önce dosyaya bakayım.",
         "adimlar": [{"tool": "shell", "ozet": "cat x"}]},
    ]


def test_transcript_orphan_trace_attaches_to_empty_turn(tmp_path):
    """Metinsiz kesilen turun izi kaybolmuyor: sonraki kullanıcı sözünden
    önce metinsiz bir asistan turuna bağlanıyor."""
    from dornick.events import EventLog
    from dornick.mind import open_mind

    sessions = tmp_path / "sessions"
    sessions.mkdir(parents=True)
    log = EventLog(sessions / "20260610T100000Z.jsonl")
    log.append("message", role="user", content="dosyayı düzelt")
    log.append("message", role="assistant", content=[
        {"type": "tool_use", "name": "edit_file", "input": {"path": "a.py"}},
    ])
    log.append("message", role="user", content="dur, vazgeçtim")
    log.close()

    mind = open_mind(tmp_path / "mind", sessions, "cur")
    turns = mind.transcript("20260610T100000Z")
    assert turns == [
        {"role": "user", "text": "dosyayı düzelt"},
        {"role": "assistant", "text": "",
         "adimlar": [{"tool": "edit_file", "ozet": "a.py"}]},
        {"role": "user", "text": "dur, vazgeçtim"},
    ]


def test_transcript_cache_serves_unchanged_file(tmp_path):
    """Değişmeyen dosyanın dökümü önbellekten dönüyor (derin arama 40
    oturumu her yazışta baştan ayrıştırıyordu)."""
    from dornick.events import EventLog
    from dornick.mind import open_mind

    sessions = tmp_path / "sessions"
    sessions.mkdir(parents=True)
    log = EventLog(sessions / "20260610T110000Z.jsonl")
    log.append("message", role="user", content="merhaba")
    log.close()

    mind = open_mind(tmp_path / "mind", sessions, "cur")
    ilk = mind.transcript("20260610T110000Z")
    assert ilk and ilk[0]["text"] == "merhaba"
    # Aynı nesne dönmeli: dosya değişmedi, ayrıştırma tekrarlanmadı.
    assert mind.transcript("20260610T110000Z") is ilk


def test_projects_assign_and_clear(tmp_path):
    """Bir konuşma bir projeye bağlanıp çözülebiliyor; kalıcı ve boş ad
    bağlamayı kaldırıyor. Bir konuşma bir anı değil — bu yalnızca klasör."""
    from dornick.mind import open_mind

    sessions = tmp_path / "sessions"
    sessions.mkdir(parents=True)
    mind = open_mind(tmp_path / "mind", sessions, "cur")

    assert mind.projects() == {}
    mind.set_project("20260610T090000Z", "Çorum SCADA")
    assert mind.projects()["20260610T090000Z"] == "Çorum SCADA"

    # Yeniden açınca korunuyor (diske yazıldı).
    again = open_mind(tmp_path / "mind", sessions, "cur")
    assert again.projects()["20260610T090000Z"] == "Çorum SCADA"

    # Boş ad bağlamayı kaldırıyor.
    again.set_project("20260610T090000Z", "")
    assert "20260610T090000Z" not in again.projects()


# -- gövde sınırı -------------------------------------------------------


def test_recall_answers_are_body_capped(tmp_path):
    """Sınırsızdı: bir episode kaydı (sıkıştırma özeti 8.000 harfe kadar)
    tek isabette binlerce token yiyip gerçek eşleşmeyi boğuyordu. Kırpılan
    kayıp değil — model sorguyu daraltıp yeniden arayabilir ve cevap bunu
    söylüyor."""
    from dornick.mind.tools import RECALL_BODY_CAP, _bounded

    short = "kısa kayıt"
    assert _bounded(short) == short

    long = "postgres " * 400
    cut = _bounded(long)
    assert len(cut) < len(long)
    assert cut.startswith(long[:RECALL_BODY_CAP])
    assert "kırpıldı" in cut


# -- oturum kimliği ve döküm araması ------------------------------------
#
# Başlık bugüne kadar dijestin ilk sözcüklerinden türetiliyordu: ucuz ama
# kullanıcının seçtiği bir ad değil. "Şu CMS işi neredeydi?" diye bakan
# biri kendi verdiği adı arıyor — ya da konuşmanın ortasında geçen bir söz.


def _oturum_yaz(sessions_dir: Path, sid: str, turlar: list[tuple[str, str]]) -> None:
    """Sahte bir oturum günlüğü: rol + metin satırları."""
    sessions_dir.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps({"kind": "note", "name": "session_start"})]
    for role, text in turlar:
        lines.append(json.dumps({
            "kind": "message", "role": role,
            "content": [{"type": "text", "text": text}],
        }, ensure_ascii=False))
    (sessions_dir / f"{sid}.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_a_conversation_can_be_named_and_tagged(tmp_path: Path, mind: Mind) -> None:
    kayit = mind.set_session_meta("s1", ad="CMS göçü", etiketler=["cms", "acil"])
    # Birebir sozluk esitligi DEGIL: kayit sonradan yeni alanlar kazandi
    # (model/path/provider — pencere devri isi) ve her yeni alan bu testi
    # kirmamali. Test, verdigimiz iki alanin dogru dondugunu sinar.
    assert kayit["ad"] == "CMS göçü"
    assert kayit["etiketler"] == ["cms", "acil"]

    # Diskten taze okunduğunda da orada: panel her açılışta yeniden okuyor.
    taze = open_mind(tmp_path / "mind", tmp_path / "sessions", "cur")
    assert taze.session_meta()["s1"]["ad"] == "CMS göçü"


def test_archive_moves_the_log_out_of_the_list(tmp_path: Path, mind: Mind) -> None:
    """Arşiv kalıcı silme değil: günlük sessions/.arsiv'e gider, listeden
    düşer, ad/proje eşlemesi de gider. Açık oturum taşınmaz."""
    sid = "20260610T090000Z"
    _oturum_yaz(mind.sessions_dir, sid, [("user", "pompa"), ("assistant", "ok")])
    mind.set_session_meta(sid, ad="Pompa")
    mind.set_project(sid, "SCADA")
    assert any(e.session_id == sid for e in mind.sessions())

    out = mind.archive_session(sid)
    assert out["ok"] is True
    assert not (mind.sessions_dir / f"{sid}.jsonl").is_file()
    assert (mind.sessions_dir / ".arsiv" / f"{sid}.jsonl").is_file()
    assert sid not in mind.session_meta()
    assert sid not in mind.projects()
    assert all(e.session_id != sid for e in mind.sessions())

    (mind.sessions_dir / "cur.jsonl").write_text("{}\n", encoding="utf-8")
    assert mind.archive_session("cur")["ok"] is False
    assert mind.archive_session("yok")["ok"] is False


def test_touching_one_field_leaves_the_other_alone(tmp_path: Path, mind: Mind) -> None:
    """Yalnız etiket değiştiren bir istek adı silmemeli."""
    mind.set_session_meta("s1", ad="CMS göçü", etiketler=["cms"])
    kayit = mind.set_session_meta("s1", etiketler=["cms", "borsa"])
    assert kayit["ad"] == "CMS göçü"
    kayit = mind.set_session_meta("s1", ad="Yeni ad")
    assert kayit["etiketler"] == ["cms", "borsa"]


def test_tags_are_normalised_and_bounded(tmp_path: Path, mind: Mind) -> None:
    """Etiket bir süzgeç anahtarı: "CMS" ile "cms" iki ayrı küme olamaz."""
    kayit = mind.set_session_meta(
        "s1", etiketler=["  CMS  ", "cms", "Borsa", "", "   "])
    assert kayit["etiketler"] == ["cms", "borsa"]
    # Sınır: bir konuşmaya sekiz etiketten fazlası panelde okunmuyor.
    cok = mind.set_session_meta("s2", etiketler=[f"e{i}" for i in range(20)])
    assert len(cok["etiketler"]) == 8


def test_an_empty_name_and_no_tags_drops_the_record(tmp_path: Path, mind: Mind) -> None:
    """Adı silmek türetilen başlığa dönmek demek; dosyada boş kayıt birikmesin."""
    mind.set_session_meta("s1", ad="Bir ad")
    mind.set_session_meta("s1", ad="")
    assert "s1" not in mind.session_meta()


def test_session_meta_keeps_path_and_model(tmp_path: Path, mind: Mind) -> None:
    """Klasör/model bağlıysa ad silinse bile kayıt düşmez."""
    mind.set_session_meta(
        "s1", ad="İş", path=r"D:\proj\foo", model="openai/gpt-4o-mini")
    kayit = mind.set_session_meta("s1", ad="")
    assert kayit["path"].endswith("foo")
    assert kayit["model"] == "openai/gpt-4o-mini"
    assert "s1" in mind.session_meta()


def test_binding_a_folder_also_files_the_chat_under_that_project(
    tmp_path: Path, mind: Mind
) -> None:
    """Klasör bağlayınca konuşma o klasör adının altında gruplansın.

    Cursor Repositories gibi: path=...\\dornick → proje etiketi 'dornick'. Elle
    verilmiş proje adı varsa üzerine yazılmaz.
    """
    mind.set_session_meta("s1", path=r"C:\projeler\Fatih\dornick")
    assert mind.projects().get("s1") == "dornick"
    # İkinci path yazımı: zaten etiket var → dokunma.
    mind.set_project("s1", "Dornick SCADA")
    mind.set_session_meta("s1", path=r"C:\projeler\Fatih\dornick")
    assert mind.projects().get("s1") == "Dornick SCADA"
    # Path yokken proje de yoksa boş kalır.
    mind.set_project("s2", "")
    mind.set_session_meta("s2", ad="yalnız ad")
    assert "s2" not in mind.projects()


def test_a_corrupt_meta_file_does_not_break_the_panel(tmp_path: Path, mind: Mind) -> None:
    """Elle düzenlenip bozulan bir dosya geçmiş panelini kapatmamalı."""
    (tmp_path / "sessions").mkdir(parents=True, exist_ok=True)
    (tmp_path / "sessions" / "_oturumlar.json").write_text("{bozuk", encoding="utf-8")
    assert mind.session_meta() == {}


def test_the_raw_logs_are_never_touched_by_naming(tmp_path: Path, mind: Mind) -> None:
    """Anılar günlüklerden üretiliyor: elle verilen bir ad geçmişi yeniden
    yazmak anlamına gelirdi."""
    sessions = tmp_path / "sessions"
    _oturum_yaz(sessions, "20260101T000000Z", [("user", "merhaba")])
    once = (sessions / "20260101T000000Z.jsonl").read_bytes()
    mind.set_session_meta("20260101T000000Z", ad="Selamlaşma", etiketler=["x"])
    assert (sessions / "20260101T000000Z.jsonl").read_bytes() == once


def test_search_finds_words_spoken_inside_a_conversation(tmp_path: Path, mind: Mind) -> None:
    """Aranan söz çoğu zaman başlıkta değil, konuşmanın ortasında."""
    sessions = tmp_path / "sessions"
    _oturum_yaz(sessions, "20260101T000000Z", [
        ("user", "selam"),
        ("assistant", "Kayseri OSB için SCADA teklifini hazırladım."),
    ])
    _oturum_yaz(sessions, "20260102T000000Z", [("user", "hava nasıl")])

    found = mind.search_transcripts("scada")
    assert set(found) == {"20260101T000000Z"}
    hit = found["20260101T000000Z"][0]
    assert hit["role"] == "assistant"
    assert "SCADA" in hit["text"]

    # Eşleşme yoksa boş: "hiç sonuç yok" ile "her şey" karışmamalı.
    assert mind.search_transcripts("bulunmayan-sozcuk") == {}
    # Çok kısa sorgu taranmıyor: tek harf her konuşmada geçer.
    assert mind.search_transcripts("a") == {}


def test_search_clips_the_quote_and_caps_the_hits(tmp_path: Path, mind: Mind) -> None:
    """Turun tamamını döndürmek listeyi duvara çevirirdi."""
    sessions = tmp_path / "sessions"
    uzun = "dolgu " * 200 + "ANAHTAR" + " dolgu" * 200
    _oturum_yaz(sessions, "20260101T000000Z",
                [("user", uzun)] + [("user", "ANAHTAR burada")] * 6)

    found = mind.search_transcripts("anahtar", per_session=3)
    hits = found["20260101T000000Z"]
    assert len(hits) == 3                      # oturum başına sınır
    assert len(hits[0]["text"]) < 200          # alıntı kırpıldı
    assert "ANAHTAR" in hits[0]["text"]
    assert hits[0]["text"].startswith("…")     # kırpma görünür


def test_search_only_scans_the_most_recent_sessions(tmp_path: Path, mind: Mind) -> None:
    """Sınır ucuzluk için: eskiler zaten anılara süzülmüş oluyor."""
    sessions = tmp_path / "sessions"
    for i in range(1, 6):
        _oturum_yaz(sessions, f"2026010{i}T000000Z", [("user", "ANAHTAR")])

    assert len(mind.search_transcripts("anahtar", limit=2)) == 2
