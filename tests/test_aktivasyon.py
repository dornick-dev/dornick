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
from dornick.recall import aktivasyon as A
from dornick.recall.aktivasyon import (
    AZAMI_KULLANIM,
    TABAN_YOK,
    Kullanim,
    aktivasyon_carpani,
    taban_aktivasyon,
    tohum_carpani,
)

SIMDI = datetime(2025, 6, 1, 12, 0, tzinfo=timezone.utc)


def once(**delta) -> datetime:
    return SIMDI - timedelta(**delta)


def _k(*anlar: datetime, w: float = 1.0, etiket: str = A.ACILDI) -> list[Kullanim]:
    return [Kullanim(an, w, etiket) for an in anlar]


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
    bir_saat = taban_aktivasyon(_k(once(hours=1)), SIMDI)
    bir_gun = taban_aktivasyon(_k(once(days=1)), SIMDI)
    otuz_gun = taban_aktivasyon(_k(once(days=30)), SIMDI)
    assert bir_saat > bir_gun > otuz_gun


def test_aralikli_tekrar_ardisik_tekrardan_guclu() -> None:
    """Aralıklı tekrar etkisi: aynı sayıda kullanım, farklı dağılım.

    Beş kullanımın hepsi otuz gün önce bir saate sıkışmışsa iz, aynı beş
    kullanım otuz güne yayıldığındakinden zayıf kalmalı. İnsan hafızasının
    en iyi ölçülmüş özelliklerinden biri; formül onu bedavaya veriyor.
    """
    ardisik = _k(*[once(days=30, minutes=i * 10) for i in range(5)])
    aralikli = _k(once(days=30), once(days=22), once(days=15),
                  once(days=8), once(days=1))
    assert taban_aktivasyon(aralikli, SIMDI) > taban_aktivasyon(ardisik, SIMDI)


def test_cok_kullanim_tek_kullanimdan_guclu() -> None:
    tek = taban_aktivasyon(_k(once(days=5)), SIMDI)
    cok = taban_aktivasyon(_k(once(days=5), once(days=4), once(days=3)), SIMDI)
    assert cok > tek


def test_hic_kullanilmamis_kayit_sifir_degil_taban() -> None:
    """Kayıt kaybolmuyor: en unutulmuş iz bile taban değeri koruyor."""
    assert taban_aktivasyon([], SIMDI) == TABAN_YOK
    assert 0.0 < aktivasyon_carpani(TABAN_YOK) < 0.1
    # Tohum çarpanı skorun yarısını her hâlükârda bırakıyor.
    assert tohum_carpani(TABAN_YOK) >= 0.5


def test_gelecege_damgali_kullanim_patlamaz() -> None:
    """Saat geri alınmış bir makinede damga ileri tarihli olabilir."""
    ileri = taban_aktivasyon(_k(SIMDI + timedelta(days=2)), SIMDI)
    assert ileri == pytest.approx(taban_aktivasyon(_k(SIMDI), SIMDI))


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
        assert [k.t for k in kullanimlar] == sorted(k.t for k in kullanimlar)
        assert kullanimlar[0].etiket == A.YAZILDI
        assert [k.etiket for k in kullanimlar[1:]] == [A.ACILDI, A.ACILDI]
        assert all(k.w == 1.0 for k in kullanimlar)
    finally:
        store.close()


def test_kullanim_listesi_sinirli(tmp_path: Path) -> None:
    """Son 30 kullanım tutuluyor: sütun sınırsız büyümemeli."""
    takvim = Takvim(SIMDI)
    store = open_store(tmp_path, saat=takvim)
    try:
        node = store.remember("çok kullanılan kayıt", kind="fact")
        for _ in range(AZAMI_KULLANIM + 20):
            takvim.ilerle(hours=6)
            store.open(node.id)
        assert len(store.kullanimlar(node.id)) == AZAMI_KULLANIM
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
        # Yayılma da ürünün kendi kodundan geçerek etkisizleşmeli.
        assert A.yayilma_carpani(TABAN_YOK) == 1.0
    assert tohum_carpani(TABAN_YOK) < 1.0
    assert A.yayilma_carpani(TABAN_YOK) < 1.0


# -- ağırlıklı kullanım (Faz 3'ün ters tekrarı buradan geçecek) --------


def test_negatif_agirlik_izi_zayiflatir() -> None:
    """Hataya götüren kullanım pekiştirmez, geri çeker."""
    olumlu = taban_aktivasyon(_k(once(days=2), once(days=1)), SIMDI)
    karisik = taban_aktivasyon(
        [Kullanim(once(days=2), 1.0, A.BASARI),
         Kullanim(once(days=1), -0.3, A.HATA)], SIMDI)
    assert karisik < olumlu


def test_yalnizca_hata_taban_degere_duser() -> None:
    """Toplam sıfırın altına inse bile kayıt silinmiyor — geride kalıyor."""
    yalniz_hata = taban_aktivasyon(
        [Kullanim(once(days=1), -0.5, A.HATA)], SIMDI)
    assert yalniz_hata == TABAN_YOK
    assert tohum_carpani(yalniz_hata) >= 0.5


def test_karisik_sicil_hic_kullanilmamistan_guclu() -> None:
    """3 başarı 1 hata → yine de hiç dokunulmamış kayıttan canlı."""
    karisik = taban_aktivasyon(
        [Kullanim(once(days=4), 0.5, A.BASARI),
         Kullanim(once(days=3), 0.5, A.BASARI),
         Kullanim(once(days=2), 0.5, A.BASARI),
         Kullanim(once(days=1), -0.3, A.HATA)], SIMDI)
    assert karisik > TABAN_YOK


def test_kullanim_ekle_sayaci_artirmaz(tmp_path: Path) -> None:
    """Sorumluluk payı bir "kullanım" değil; `uses` dokunulmamalı."""
    takvim = Takvim(SIMDI)
    store = open_store(tmp_path, saat=takvim)
    try:
        node = store.remember("yordam kaydı", kind="procedure")
        takvim.ilerle(days=1)
        assert store.kullanim_ekle(node.id, w=0.5, etiket=A.BASARI) is True
        takvim.ilerle(days=1)
        assert store.kullanim_ekle(node.id, w=-0.3, etiket=A.HATA) is True
        assert store.peek(node.id).uses == 0
        assert store.sicil(node.id) == (1, 1)
        etiketler = [k.etiket for k in store.kullanimlar(node.id)]
        assert etiketler == [A.YAZILDI, A.BASARI, A.HATA]
    finally:
        store.close()


def test_kullanim_ekle_olmayan_kayitta_sessizce_false(tmp_path: Path) -> None:
    store = open_store(tmp_path, saat=Takvim(SIMDI))
    try:
        assert store.kullanim_ekle("n_yok", w=1.0) is False
    finally:
        store.close()


def test_eski_yalin_damga_bicimi_de_okunur() -> None:
    """Biçim değişmeden önce yazılmış bir bellek açılmaya devam etmeli."""
    import json

    ham = json.dumps([once(days=2).isoformat(timespec="milliseconds"),
                      once(days=1).isoformat(timespec="milliseconds")])
    okunan = A.coz_kullanimlar(ham)
    assert len(okunan) == 2
    assert all(k.w == 1.0 and k.etiket == A.ACILDI for k in okunan)


# -- bozuk kayıt ------------------------------------------------------


def test_bozuk_kullanim_gecmisi_kaydi_dusurmez() -> None:
    """Diskteki JSON bozulsa bile hatırlama çalışmaya devam etmeli."""
    assert A.coz_kullanimlar("bu json değil") == []
    assert A.coz_kullanimlar("{}") == []
    assert A.coz_kullanimlar(42) == []
    assert A.coz_kullanimlar("[]") == []
    # Girdi kısmen bozuksa yalnız o girdi düşer, kayıt değil.
    okunan = A.coz_kullanimlar(
        '[{"t": 5}, {"t": "2025-06-01T10:00:00+00:00", "w": "abc"},'
        ' {"t": "2025-06-01T11:00:00+00:00"}]')
    assert len(okunan) == 2
    assert okunan[0].w == 1.0        # çözülemeyen ağırlık nötre düşüyor
    assert okunan[1].etiket == A.ACILDI


def test_bozuk_gecmis_geriye_donuk_uretime_dusuyor(tmp_path: Path) -> None:
    """Sütun okunamıyorsa created/last_used/uses devreye girer."""
    okunan = A.coz_kullanimlar(
        "bozuk", created="2025-06-01T09:00:00.000+00:00",
        last_used="2025-06-02T09:00:00.000+00:00", uses=3)
    assert len(okunan) == 4          # yazım anı + üç kullanım
    assert okunan[0].etiket == A.YAZILDI
