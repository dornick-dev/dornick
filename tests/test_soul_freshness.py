"""Ruhun bileşimi: taze düzeltme ve gecenin tekrarlayan dersleri.

Ölçülen iki gerileme (eski sürüme karşı): `taze_ruh` 1.00 → 0.70 ve
`ruh_token` 325 → 348. İkisinin de kökü ayrı ve ikisi de tasarım değil kusur.

**Taze düzeltme.** Aktivasyona göre sıralamak doğru olanı yapıyor — düzenli
kullanılan bir yordam, bir haftalık düzeltmeden gerçekten daha canlı. Ama
düzeltme sıradan bir hatıra değil, bir **değişiklik**: ruhun sistem
promptunda durmasının sebebi ajanın eskimiş bir kurala göre davranmaması.
Bu hafta düzeltilmiş bir kayıt yuvasını garanti etmeli.

**Tekrarlayan ders.** Gece her başarısız oturum için bir `lesson` yazıyordu.
Aynı hata beş kez olduğunda beş ayrı ders oluyor, hepsi ruhun sekiz yuvası
için yarışıyor. Yol haritasının yordamlar için söylediği kural ("aynı
başlıklı varsa supersede değil, kullanım ekle") asıl burada gerekiyordu:
aynı ders ikinci kez öğrenilmez, **pekişir**.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from dornick.events import EventLog
from dornick.mind import open_mind
from dornick.recall import weave

NOW = datetime(2025, 6, 2, 9, 0, tzinfo=timezone.utc)


class Clock:
    def __init__(self, moment: datetime) -> None:
        self.moment = moment

    def __call__(self) -> datetime:
        return self.moment

    def advance(self, **delta) -> None:
        self.moment += timedelta(**delta)

    def text(self) -> str:
        return self.moment.isoformat(timespec="milliseconds")


@pytest.fixture()
def clock() -> Clock:
    return Clock(NOW)


@pytest.fixture()
def mind(tmp_path: Path, clock: Clock):
    m = open_mind(tmp_path / "mind", tmp_path / "sessions", "t", clock=clock)
    yield m
    m.store.close()


def _session(sessions: Path, name: str, node_ids, clock: Clock,
             *, outcome: str, tool: str = "kos", error: str = "") -> None:
    sessions.mkdir(parents=True, exist_ok=True)
    log = EventLog(sessions / f"{name}.jsonl", clock=clock.text)
    log.note("session_start", session_id=name)
    for node_id in node_ids:
        clock.advance(minutes=1)
        log.note("mind_open", memory_id=node_id)
    log.note("tool_end", tool=tool, error=bool(error), ms=10, ozet=error)
    log.note("sonuc", sonuc=outcome)
    log.close()


# -- taze düzeltme ruhta yer bulur -------------------------------------


def test_bu_hafta_duzeltilen_kayit_ruha_giriyor(mind, clock) -> None:
    """Düzenli kullanılan sekiz yordam varken bile."""
    # Sekiz yordam, hepsi düzenli kullanılıyor: yuvaların tamamını hak ediyorlar.
    dolu = [mind.remember(f"Yordam {i}: saha kontrolü {i} adımları.",
                          kind="procedure") for i in range(8)]
    for _ in range(6):
        clock.advance(days=2)
        for m in dolu:
            mind.store.open(m.id)

    eski = mind.remember("Testler pytest ile kök dizinden koşuluyor.",
                         kind="procedure")
    clock.advance(days=30)
    yeni = mind.update(eski.id, "Testler py -m pytest tests ile koşuluyor.",
                         kind="procedure")
    clock.advance(days=2)

    ruh = mind.soul()
    kimlikler = [m.id for m in ruh.procedures]
    assert yeni.id in kimlikler, "bu hafta yapılan düzeltme ruhta yok"
    assert eski.id not in kimlikler          # eski sürüm yine de dışarıda


def test_taze_duzeltme_ruhu_ele_gecirmiyor(mind, clock) -> None:
    """Ayrılan yer yarıyı geçmiyor: ruh bir düzeltme listesi değil."""
    dolu = [mind.remember(f"Yordam {i}: saha kontrolü {i}.", kind="procedure")
            for i in range(8)]
    for _ in range(6):
        clock.advance(days=2)
        for m in dolu:
            mind.store.open(m.id)

    for i in range(8):
        eski = mind.remember(f"Eski kural {i}: elle yapılıyor.", kind="procedure")
        clock.advance(hours=1)
        mind.update(eski.id, f"Yeni kural {i}: otomatik yapılıyor.",
                      kind="procedure")

    ruh = mind.soul()
    duzeltme = [m for m in ruh.procedures if m.supersedes]
    assert len(duzeltme) <= len(ruh.procedures) // 2
    assert any(not m.supersedes for m in ruh.procedures)


def test_eski_duzeltme_ayricalik_kaybediyor(mind, clock) -> None:
    """Ayrıcalık tazeliğe ait, düzeltme olmaya değil."""
    dolu = [mind.remember(f"Yordam {i}: saha kontrolü {i}.", kind="procedure")
            for i in range(8)]
    for _ in range(6):
        clock.advance(days=2)
        for m in dolu:
            mind.store.open(m.id)

    eski = mind.remember("Testler pytest ile koşuluyor.", kind="procedure")
    clock.advance(hours=1)
    yeni = mind.update(eski.id, "Testler py -m pytest ile koşuluyor.",
                         kind="procedure")
    clock.advance(days=40)                    # düzeltme artık taze değil

    assert yeni.id not in [m.id for m in mind.soul().procedures]


# -- aynı ders ikinci kez öğrenilmez, pekişir --------------------------


def test_ayni_hata_ikinci_kez_ders_yazmiyor(mind, tmp_path, clock) -> None:
    kaynak = mind.remember("Gate servisi doğrudan kill ile durduruluyor.",
                           kind="procedure")
    sessions = tmp_path / "sessions"
    for i in range(4):
        clock.advance(days=1)
        _session(sessions, f"hata{i}", [kaynak.id], clock,
                 outcome="basarisiz", error="sqlite database is locked")
        weave.night_pass(mind.store, sessions, clock=clock,
                         watermark=tmp_path / "w.json")

    dersler = mind.store.by_kind("lesson", limit=20)
    assert len(dersler) == 1, [d.body[:40] for d in dersler]


def test_tekrarlanan_ders_pekisiyor(mind, tmp_path, clock) -> None:
    """İkinci kez yazılmıyor ama ikinci kez YAŞANDIĞI kayda geçiyor."""
    kaynak = mind.remember("Şema göçü doğrudan üretimde koşuluyor.",
                           kind="procedure")
    sessions = tmp_path / "sessions"
    _session(sessions, "h1", [kaynak.id], clock, outcome="basarisiz",
             error="göç yarıda kaldı")
    weave.night_pass(mind.store, sessions, clock=clock, watermark=tmp_path / "w.json")
    ders = mind.store.by_kind("lesson", limit=5)[0]
    ilk = len(mind.store.use_log(ders.id))

    clock.advance(days=1)
    _session(sessions, "h2", [kaynak.id], clock, outcome="basarisiz",
             error="göç yarıda kaldı")
    weave.night_pass(mind.store, sessions, clock=clock, watermark=tmp_path / "w.json")

    assert len(mind.store.by_kind("lesson", limit=5)) == 1
    assert len(mind.store.use_log(ders.id)) > ilk


def test_farkli_hata_yeni_ders_yaziyor(mind, tmp_path, clock) -> None:
    """Pekişme birleştirme değil: başka bir hata başka bir derstir."""
    kaynak = mind.remember("Bir yordam.", kind="procedure")
    sessions = tmp_path / "sessions"
    for i, hata in enumerate(("sqlite database is locked",
                              "sertifika doğrulanamadı")):
        clock.advance(days=1)
        _session(sessions, f"h{i}", [kaynak.id], clock, outcome="basarisiz",
                 error=hata)
        weave.night_pass(mind.store, sessions, clock=clock,
                         watermark=tmp_path / "w.json")

    assert len(mind.store.by_kind("lesson", limit=10)) == 2


def test_ayni_yordam_ikinci_kez_yazilmiyor(mind, tmp_path, clock) -> None:
    """Yol haritasının yordamlar için söylediği kural, aynı yerde."""
    dugumler = [mind.remember(f"Adım {i}: saha kontrolü.", kind="fact")
                for i in range(3)]
    sessions = tmp_path / "sessions"
    for i in range(3):
        clock.advance(days=1)
        log = EventLog(sessions / f"ok{i}.jsonl", clock=clock.text)
        sessions.mkdir(parents=True, exist_ok=True)
        for m in dugumler:
            clock.advance(minutes=1)
            log.note("mind_open", memory_id=m.id)
        log.note("tool_end", tool="kos", error=False, ms=10)
        log.note("tool_end", tool="dosya_yaz", error=False, ms=10)
        log.note("sonuc", sonuc="basarili")
        log.close()
        weave.night_pass(mind.store, sessions, clock=clock,
                         watermark=tmp_path / "w.json")

    gece_yordamlari = [n for n in mind.store.by_kind("procedure", limit=20)
                       if "gece" in n.tags]
    assert len(gece_yordamlari) <= 1
