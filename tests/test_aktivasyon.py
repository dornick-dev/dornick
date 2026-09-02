"""Zaman bazlı aktivasyon (ACT-R taban seviyesi).

`uses` sayacı zamanı bilmiyordu: üç yüz gün önce yazılmış bir kayıt dünkü
kadar güçlüydü ve çok kullanılmış eski bir kayıt, yeni bir düzeltmeyi ruhun
dışında tutabiliyordu. Buradaki testler o eksiği kapatan formülü ve onun
depoya bağlandığı yerleri zorluyor.

Değişmez: hiçbir şey kaybolmuyor. "Unutma" = aktivasyonun eşik altına
inmesi; kayıt açık aramayla her zaman bulunabilir.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from dornick.recall import RecallStore, anahtar, open_store
from dornick.recall.aktivasyon import (
    TABAN_YOK,
    aktivasyon_carpani,
    taban_aktivasyon,
    tohum_carpani,
)

SIMDI = datetime(2025, 6, 1, 12, 0, tzinfo=timezone.utc)


def once(**delta) -> datetime:
    return SIMDI - timedelta(**delta)


class Takvim:
    def __init__(self, an: datetime) -> None:
        self.an = an

    def __call__(self) -> datetime:
        return self.an

    def ilerle(self, **delta) -> None:
        self.an += timedelta(**delta)


# -- formül ------------------------------------------------------------


def test_taze_iz_eski_izden_guclu() -> None:
    """Tek kullanım: bir saat önce > bir gün önce > otuz gün önce."""
    bir_saat = taban_aktivasyon([once(hours=1)], SIMDI)
    bir_gun = taban_aktivasyon([once(days=1)], SIMDI)
    otuz_gun = taban_aktivasyon([once(days=30)], SIMDI)
    assert bir_saat > bir_gun > otuz_gun


def test_araliklі_tekrar_ardisik_tekrardan_guclu() -> None:
    """Aralıklı tekrar etkisi: aynı sayıda kullanım, farklı dağılım.

    Beş kullanımın hepsi otuz gün önce bir saate sıkışmışsa iz, aynı beş
    kullanım otuz güne yayıldığındakinden zayıf kalmalı. İnsan hafızasının
    en iyi ölçülmüş özelliklerinden biri; formül onu bedavaya veriyor.
    """
    ardisik = [once(days=30, minutes=i * 10) for i in range(5)]
    aralikli = [once(days=30), once(days=22), once(days=15),
                once(days=8), once(days=1)]
    assert taban_aktivasyon(aralikli, SIMDI) > taban_aktivasyon(ardisik, SIMDI)


def test_cok_kullanim_tek_kullanimdan_guclu() -> None:
    tek = taban_aktivasyon([once(days=5)], SIMDI)
    cok = taban_aktivasyon([once(days=5), once(days=4), once(days=3)], SIMDI)
    assert cok > tek


def test_hic_kullanilmamis_kayit_sifir_degil_taban() -> None:
    """Kayıt kaybolmuyor: en unutulmuş iz bile taban değeri koruyor."""
    assert taban_aktivasyon([], SIMDI) == TABAN_YOK
    assert 0.0 < aktivasyon_carpani(TABAN_YOK) < 0.1
    # Tohum çarpanı skorun yarısını her hâlükârda bırakıyor.
    assert tohum_carpani(TABAN_YOK) >= 0.5


def test_gelecege_damgali_kullanim_patlamaz() -> None:
    """Saat geri alınmış bir makinede damga ileri tarihli olabilir."""
    ileri = taban_aktivasyon([SIMDI + timedelta(days=2)], SIMDI)
    assert ileri == pytest.approx(taban_aktivasyon([SIMDI], SIMDI))


def test_carpan_sinirli_ve_monoton() -> None:
    degerler = [aktivasyon_carpani(b) for b in (-10, -5, -2, 0, 2, 5)]
    assert degerler == sorted(degerler)
    assert all(0.0 < d < 1.0 for d in degerler)
    assert all(0.5 <= tohum_carpani(b) <= 1.0 for b in (-10, -5, 0, 5))


# -- depoya bağlanışı --------------------------------------------------


def test_kullanim_damgalari_diske_yaziliyor(tmp_path: Path) -> None:
    takvim = Takvim(SIMDI)
    store = open_store(tmp_path, saat=takvim)
    try:
        node = store.remember("yordam: yedek al", kind="procedure")
        takvim.ilerle(days=3)
        store.open(node.id)
        takvim.ilerle(days=3)
        store.open(node.id)
        kullanimlar = store.kullanimlar(node.id)
        assert len(kullanimlar) == 3          # yazım anı ilk kullanımdır
        assert kullanimlar == sorted(kullanimlar)
    finally:
        store.close()


def test_kullanim_listesi_sinirli(tmp_path: Path) -> None:
    """Son 20 kullanım tutuluyor: sütun sınırsız büyümemeli."""
    takvim = Takvim(SIMDI)
    store = open_store(tmp_path, saat=takvim)
    try:
        node = store.remember("çok kullanılan kayıt", kind="fact")
        for _ in range(40):
            takvim.ilerle(hours=6)
            store.open(node.id)
        assert len(store.kullanimlar(node.id)) == 20
    finally:
        store.close()


def test_kullanilan_kayit_ruh_siralamasinda_one_gecer(tmp_path: Path) -> None:
    """`by_kind` artık `uses DESC` değil, aktivasyona göre sıralıyor."""
    takvim = Takvim(SIMDI)
    store = open_store(tmp_path, saat=takvim)
    try:
        eski = store.remember("eskiden beri duran yordam", kind="procedure")
        takvim.ilerle(days=120)
        yeni = store.remember("yeni yazılmış yordam", kind="procedure")
        takvim.ilerle(days=2)
        # Eski kayıt düzenli kullanılıyor; yeni olan hiç açılmadı.
        for _ in range(5):
            takvim.ilerle(hours=8)
            store.open(eski.id)
        sirali = [n.id for n in store.by_kind("procedure", limit=5)]
        assert sirali[0] == eski.id

        # Ve tersi: aylardır dokunulmayan eski kayıt yeni olanın altına düşer.
        takvim.ilerle(days=200)
        taze = store.remember("bugün yazılan yordam", kind="procedure")
        sirali = [n.id for n in store.by_kind("procedure", limit=5)]
        assert sirali[0] == taze.id
        assert sirali.index(eski.id) > sirali.index(taze.id)
        assert yeni.id in sirali          # kimse listeden düşmüyor
    finally:
        store.close()


def test_unutulmus_kayit_acik_aramayla_hala_bulunur(tmp_path: Path) -> None:
    """Değişmez: aktivasyon düşer, kayıt durur."""
    takvim = Takvim(SIMDI)
    store = open_store(tmp_path, saat=takvim)
    try:
        node = store.remember(
            "Debimetre kalibrasyonu iki yılda bir yetkili serviste yapılıyor.",
            kind="fact")
        takvim.ilerle(days=400)
        sonuc = store.recall("debimetre kalibrasyonu", limit=5)
        assert node.id in {n.id for n in sonuc.hits}
    finally:
        store.close()


def test_unutulmus_dugum_cagrisim_yolunu_zayif_iletir(tmp_path: Path) -> None:
    """Aylardır dokunulmamış bir düğüm, komşusunu eskisi kadar uyandırmamalı."""
    takvim = Takvim(SIMDI)
    store = open_store(tmp_path, saat=takvim)
    try:
        kaynak = store.remember("Karatay deposu seviye ölçümü", kind="fact")
        uzak = store.remember("Sıcaklık sensörü kalibrasyon notu", kind="fact")
        store.link(kaynak.id, uzak.id, weight=1.0, reason="aynı saha")

        taze = store.recall("Karatay deposu seviye", limit=6)
        taze_aktivasyon = {s.node: s.activation for s in taze.trace}[uzak.id]

        takvim.ilerle(days=300)
        eskimis = store.recall("Karatay deposu seviye", limit=6)
        eski_aktivasyon = {s.node: s.activation for s in eskimis.trace}.get(uzak.id, 0.0)
        assert eski_aktivasyon < taze_aktivasyon
    finally:
        store.close()


# -- göç ---------------------------------------------------------------


def test_eski_kayitlarin_aktivasyonu_geriye_donuk_uretilir(tmp_path: Path) -> None:
    """`kullanimlar` sütunu olmayan bir bellek, created/last_used/uses'tan
    kabaca doldurulmalı — yoksa bütün eski hatıralar bir anda "hiç
    kullanılmamış" sayılırdı."""
    import shutil

    fikstur = Path(__file__).resolve().parent / "fixtures" / "recall-v1.db"
    hedef = tmp_path / "recall.db"
    shutil.copy2(fikstur, hedef)

    store = RecallStore(hedef)
    try:
        cok = store.kullanimlar("n_v1scada")      # uses=5
        az = store.kullanimlar("n_v1kedi")        # uses=1
        assert len(cok) > len(az) >= 1
        node = store.peek("n_v1scada")
        assert node is not None and node.aktivasyon > TABAN_YOK
    finally:
        store.close()


# -- ablation ----------------------------------------------------------


def test_mekanik_kapaliyken_carpan_etkisiz(tmp_path: Path) -> None:
    """`--kapat aktivasyon`: ölçüm mekaniği tek tek kapatabilmeli."""
    with anahtar.kapali("aktivasyon"):
        assert tohum_carpani(TABAN_YOK) == 1.0
        assert tohum_carpani(5.0) == 1.0
    assert tohum_carpani(TABAN_YOK) < 1.0
