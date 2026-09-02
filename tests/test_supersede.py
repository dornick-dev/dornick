"""Supersede — güncellenen kaydın eskisinin yerini alması.

Araç açıklaması "aynı konuda kayıt varsa eskisini sil ve güncelini yaz"
diyordu; sistem bunu yapmıyordu. `save` onaysız, `forget` onaylıydı: model
çelişki üretmekte serbest, temizlemekte değildi. Sonuç, ölçülmüş hâliyle,
aynı konunun dört sürümünün birden önyüklemeye girmesiydi.

Buradaki çözüm silmek değil — mezar taşı felsefesi duruyor. Yeni kayıt
eskisinin **yerini alıyor**: eski satır diskte, `series`'te ve açık aramada
kalıyor; yalnız tohumlamadan ve ruhtan düşüyor, ve kendisine gelen çağrışım
yeni sürüme yönleniyor.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from dornick.recall import RecallStore, anahtar, open_store
from dornick.recall.aktivasyon import TABAN_YOK

SIMDI = datetime(2025, 6, 1, 9, 0, tzinfo=timezone.utc)


class Takvim:
    def __init__(self, an: datetime) -> None:
        self.an = an

    def __call__(self) -> datetime:
        return self.an

    def ilerle(self, **delta) -> None:
        self.an += timedelta(**delta)


@pytest.fixture()
def takvim() -> Takvim:
    return Takvim(SIMDI)


@pytest.fixture()
def store(tmp_path: Path, takvim: Takvim):
    s = open_store(tmp_path, saat=takvim)
    yield s
    s.close()


def _zincir(store: RecallStore, takvim: Takvim) -> tuple[str, str, str]:
    """A → B → C: aynı konunun üç sürümü."""
    a = store.remember("Raporları PDF olarak istiyorum.", kind="preference",
                       tags=["rapor-format"])
    takvim.ilerle(days=10)
    b = store.guncelle(a.id, "Raporları artık xlsx istiyorum.",
                       kind="preference", tags=["rapor-format"])
    takvim.ilerle(days=10)
    c = store.guncelle(b.id, "Rapor formatı csv olsun.",
                       kind="preference", tags=["rapor-format"])
    return a.id, b.id, c.id


# -- zincir ------------------------------------------------------------


def test_eski_surum_tohumlanmaz_yenisi_gelir(store, takvim) -> None:
    a, b, c = _zincir(store, takvim)
    hits = {n.id for n in store.recall("rapor formatı", limit=8).hits}
    assert c in hits
    assert a not in hits and b not in hits


def test_eski_surum_silinmiyor(store, takvim) -> None:
    """Mezar taşı felsefesi: yerini aldı, yok olmadı."""
    a, b, c = _zincir(store, takvim)
    for node_id in (a, b):
        node = store.peek(node_id)
        assert node is not None
        assert node.deleted is False


def test_supersede_zinciri_iki_yonlu_yaziliyor(store, takvim) -> None:
    a, b, c = _zincir(store, takvim)
    assert store.peek(a).superseded_by == b
    assert store.peek(b).superseded_by == c
    assert store.peek(c).superseded_by == ""
    assert store.peek(b).supersedes == a
    assert store.peek(c).supersedes == b
    assert store.peek(a).supersedes == ""


def test_guncelleyen_kayit_eskisine_bagli(store, takvim) -> None:
    """Zincir bir kenar olarak da duruyor: arayüz onu çizebilmeli."""
    a, b, _c = _zincir(store, takvim)
    gerekceler = {n.id: r for n, _w, r in store.komsular_gerekceli(b)}
    assert gerekceler.get(a) == "günceller"


def test_ruh_ve_liste_yalniz_gecerli_surumu_goruyor(store, takvim) -> None:
    a, b, c = _zincir(store, takvim)
    kimlikler = [n.id for n in store.by_kind("preference", limit=10)]
    assert kimlikler == [c]
    assert [n.id for n in store.recent(10)] == [c]


def test_seri_butun_surumleri_donduruyor(store, takvim) -> None:
    """Zaman dizisi zaten geçmişi istiyor: `series` süzmez."""
    a, b, c = _zincir(store, takvim)
    kimlikler = [n.id for n in store.by_kind_any(limit=50, tum_surumler=True)]
    assert {a, b, c} <= set(kimlikler)


# -- yayılma -----------------------------------------------------------


def test_eski_dugume_gelen_cagrisim_yeniye_yonleniyor(store, takvim) -> None:
    """Eski sürümün komşuluğu kayboluyor değil, güncel sürüme taşınıyor."""
    kaynak = store.remember("Vardiya defteri kasada duruyor.", kind="fact")
    eski = store.remember("Raporları PDF olarak istiyorum.", kind="preference")
    store.link(kaynak.id, eski.id, weight=1.0, reason="aynı iş")
    takvim.ilerle(days=5)
    yeni = store.guncelle(eski.id, "Raporları xlsx istiyorum.", kind="preference")

    sonuc = store.recall("Vardiya defteri kasada", limit=8)
    dokunulan = {s.node for s in sonuc.trace}
    assert yeni.id in dokunulan
    assert eski.id not in {n.id for n in sonuc.hits}


def test_supersede_dongusu_sonsuz_donguye_girmez(store, takvim) -> None:
    """A → B, B → A elle yazılırsa hatırlama yine de bitmeli."""
    a = store.remember("birinci sürüm", kind="fact")
    b = store.guncelle(a.id, "ikinci sürüm", kind="fact")
    with store._lock:                      # noqa: SLF001 — bilerek bozuk veri
        store._db.execute("UPDATE node SET superseded_by=? WHERE id=?", (a.id, b.id))
        store._db.commit()
    sonuc = store.recall("sürüm", limit=5)
    assert isinstance(sonuc.hits, list)    # dönmesi yeter: takılmadı


def test_gecerli_surum_kendini_gosteriyor(store, takvim) -> None:
    a, b, c = _zincir(store, takvim)
    assert store.gecerli_surum(a) == c
    assert store.gecerli_surum(c) == c
    assert store.gecerli_surum("n_yok") == "n_yok"


# -- pekişme mirası ----------------------------------------------------


def test_duzeltme_eskinin_aktivasyonunu_devraliyor(store, takvim) -> None:
    """Düzeltme sıfırdan başlasaydı ruhta düzelttiği şeyin altında kalırdı."""
    eski = store.remember("Testler pytest ile koşuluyor.", kind="procedure")
    for _ in range(10):
        takvim.ilerle(days=3)
        store.open(eski.id)
    onceki_b = store.peek(eski.id).aktivasyon

    takvim.ilerle(hours=1)
    yeni = store.guncelle(eski.id, "Testler py -m pytest ile koşuluyor.",
                          kind="procedure")
    assert store.peek(yeni.id).aktivasyon >= onceki_b
    # Miras gerçekten kopyalandı, uydurulmadı:
    assert len(store.kullanimlar(yeni.id)) > 1


def test_miras_devralan_kayit_taze_bir_kayitin_ustunde(store, takvim) -> None:
    eski = store.remember("Yedekler harici diske alınıyor.", kind="procedure")
    for _ in range(8):
        takvim.ilerle(days=2)
        store.open(eski.id)
    takvim.ilerle(days=1)
    rakip = store.remember("Sahaya seri kablo götürülüyor.", kind="procedure")
    takvim.ilerle(hours=2)
    yeni = store.guncelle(eski.id, "Yedekler NAS'a alınıyor.", kind="procedure")

    sirali = [n.id for n in store.by_kind("procedure", limit=5)]
    assert sirali.index(yeni.id) < sirali.index(rakip.id)


def test_supersede_edilen_kayit_aktivasyon_hesabini_bozmaz(store, takvim) -> None:
    a, b, c = _zincir(store, takvim)
    assert store.peek(a).aktivasyon > TABAN_YOK      # hâlâ hesaplanıyor


# -- açık arama --------------------------------------------------------


def test_eski_kayit_acilinca_guncellendigini_soyluyor(store, takvim) -> None:
    """Model eski bir kimliği elinde tutuyorsa yönü görmeli."""
    a, _b, c = _zincir(store, takvim)
    node = store.open(a)
    assert node is not None
    assert f"[güncellendi → {c}]" in node.body


def test_guncel_kayit_acilinca_not_dusmuyor(store, takvim) -> None:
    _a, _b, c = _zincir(store, takvim)
    assert "güncellendi" not in store.open(c).body


# -- ablation ----------------------------------------------------------


def test_mekanik_kapaliyken_eski_surum_yine_tohumlaniyor(store, takvim) -> None:
    """`--kapat supersede`: ölçüm mekaniği tek tek kapatabilmeli."""
    a, b, c = _zincir(store, takvim)
    with anahtar.kapali("supersede"):
        hits = {n.id for n in store.recall("rapor formatı", limit=8).hits}
        assert a in hits or b in hits
        assert [n.id for n in store.by_kind("preference", limit=10)] != [c]


# -- göç ---------------------------------------------------------------


def test_eski_bellek_supersede_sutunlariyla_aciliyor(tmp_path: Path) -> None:
    import shutil

    fikstur = Path(__file__).resolve().parent / "fixtures" / "recall-v1.db"
    hedef = tmp_path / "recall.db"
    shutil.copy2(fikstur, hedef)
    store = RecallStore(hedef)
    try:
        node = store.peek("n_v1rapor")
        assert node is not None
        assert node.superseded_by == "" and node.supersedes == ""
        yeni = store.guncelle("n_v1rapor", "Raporları xlsx istiyorum.",
                              kind="preference")
        assert store.peek("n_v1rapor").superseded_by == yeni.id
    finally:
        store.close()


# -- araç yüzeyi -------------------------------------------------------


async def test_arac_supersedes_ile_guncelliyor(tmp_path: Path) -> None:
    from tests.test_mind import _arac_ortami

    registry, ctx, mind = _arac_ortami(tmp_path)
    ilk = mind.remember("Raporları PDF istiyorum.", kind="preference")
    out = await _cagir(registry, ctx, "mind_memory", {
        "action": "save", "kind": "preference",
        "content": "Raporları xlsx istiyorum.", "supersedes": ilk.id})
    assert "Güncellendi" in out and ilk.id in out
    assert mind.store.peek(ilk.id).superseded_by != ""


async def test_arac_celiskiyi_kendiliginden_isaret_ediyor(tmp_path: Path) -> None:
    """Model `supersedes` vermeyi unutursa sistem sessiz kalmamalı."""
    from tests.test_mind import _arac_ortami

    registry, ctx, mind = _arac_ortami(tmp_path)
    ilk = mind.remember("Testler pytest ile kök dizinden koşuluyor.",
                        kind="procedure")
    out = await _cagir(registry, ctx, "mind_memory", {
        "action": "save", "kind": "procedure",
        "content": "Testler pytest ile kök dizinden koşuluyor artık."})
    assert "Kaydedildi" in out          # kayıt her hâlükârda yazıldı
    assert f"supersedes={ilk.id}" in out


async def test_arac_alakasiz_kayitta_celiski_uydurmuyor(tmp_path: Path) -> None:
    from tests.test_mind import _arac_ortami

    registry, ctx, mind = _arac_ortami(tmp_path)
    mind.remember("Testler pytest ile koşuluyor.", kind="procedure")
    out = await _cagir(registry, ctx, "mind_memory", {
        "action": "save", "kind": "preference",
        "content": "Kahvesini sütsüz içiyor."})
    assert "Benzer kayıt var" not in out


async def test_arac_olmayan_kaydi_guncellemeyi_reddediyor(tmp_path: Path) -> None:
    from tests.test_mind import _arac_ortami

    registry, ctx, mind = _arac_ortami(tmp_path)
    out = await _cagir(registry, ctx, "mind_memory", {
        "action": "save", "content": "bir şey", "supersedes": "n_yok"},
        hata_bekle=True)
    assert "n_yok" in out


async def _cagir(registry, ctx, name: str, args: dict, *, hata_bekle: bool = False) -> str:
    from tests.test_mind import _call

    return await _call(registry, ctx, name, args, expect_error=hata_bekle)
