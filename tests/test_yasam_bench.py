"""Yaşam benchmark'ının kendisi ölçülebilir mi?

Bir benchmark'a güvenmenin ön şartı iki şey: aynı girdiden aynı sayıyı
üretmesi ve ölçtüğü veri setinin tutarlı olması. İkisi de burada zorlanıyor —
sayılar dalgalanıyorsa faz kabul kriterleri anlamsız, veri seti tutarsızsa
ölçülen şey ürün değil veri setinin hatası olur.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
BENCH_YOLU = KOK / "eval" / "context_memory" / "yasam_bench.py"


def _bench():
    """Bench'i modül olarak yükler (eval/ bir paket değil)."""
    spec = importlib.util.spec_from_file_location("yasam_bench", BENCH_YOLU)
    assert spec and spec.loader
    modul = importlib.util.module_from_spec(spec)
    sys.modules["yasam_bench"] = modul
    spec.loader.exec_module(modul)
    return modul


@pytest.fixture(scope="module")
def bench():
    return _bench()


@pytest.fixture(scope="module")
def holdout(bench):
    return bench.veri_yukle("holdout")


@pytest.fixture(scope="module")
def ana(bench):
    return bench.veri_yukle("ana")


# -- determinizm -------------------------------------------------------


def test_ayni_senaryo_ayni_sonucu_verir(bench, holdout) -> None:
    """Rastgelelik yok: iki koşu birebir aynı metrikleri vermeli."""
    ilk = bench.kosu(holdout)
    ikinci = bench.kosu(holdout)
    # Gecikme duvar saati ölçümü — tek dalgalanan sayı, karşılaştırmadan
    # çıkarılıyor. Kalan her metrik birebir aynı olmalı.
    for sonuc in (ilk, ikinci):
        sonuc["metrikler"].pop("gecikme_p95")
    assert ilk["metrikler"] == ikinci["metrikler"]
    assert ilk["kume"] == ikinci["kume"]
    assert ilk["sayim"]["dugum"] == ikinci["sayim"]["dugum"]


def test_gecikme_disinda_her_metrik_sayidir(bench, holdout) -> None:
    sonuc = bench.kosu(holdout)
    for ad, deger in sonuc["metrikler"].items():
        assert isinstance(deger, (int, float)), ad


# -- veri seti tutarlılığı ---------------------------------------------


@pytest.mark.parametrize("ad", ["ana", "holdout"])
def test_veri_seti_tutarli(bench, ad: str) -> None:
    veri = bench.veri_yukle(ad)
    gun_sayisi = veri["gun_sayisi"]
    yazilan: dict[str, int] = {}     # slug -> yazıldığı gün
    for olay in veri["olaylar"]:
        gun = olay["gun"]
        assert 1 <= gun <= gun_sayisi, olay
        assert olay["tur"] in ("kaydet", "duzelt", "sor", "kullan", "sessiz")

        if olay["tur"] in ("kaydet", "duzelt"):
            assert olay["slug"] not in yazilan, f"aynı slug iki kez: {olay['slug']}"
            assert olay["icerik"].strip(), olay
            yazilan[olay["slug"]] = gun
        if olay["tur"] == "duzelt":
            assert olay["eskisi"] in yazilan, f"düzeltilen kayıt yok: {olay['eskisi']}"
        if olay["tur"] == "kullan":
            for slug in olay["hedef"]:
                assert yazilan.get(slug, 10**9) <= gun, f"yazılmadan kullanıldı: {slug}"
        if olay["tur"] == "sor":
            for slug in [*olay["beklenen"], *olay["yasak"]]:
                assert slug in yazilan, f"tanımsız slug: {slug}"
                assert yazilan[slug] <= gun, f"yazılmadan soruldu: {slug}"


def test_ana_veri_seti_yol_haritasinin_asgarilerini_karsiliyor(bench, ana) -> None:
    """Yol haritası her küme için bir alt sınır koyuyor; veri seti onu tutmalı."""
    sayim: dict[tuple[str, str], int] = {}
    for olay in ana["olaylar"]:
        anahtar = (olay["kume"], olay["tur"])
        sayim[anahtar] = sayim.get(anahtar, 0) + 1

    assert sayim[("A", "kaydet")] >= 15        # sabit gerçekler
    assert sayim[("A", "sor")] >= 30
    assert sayim[("B", "duzelt")] >= 24        # 8 zincir × 3 düzeltme
    assert sayim[("C", "kaydet")] >= 60        # tek seferlik gürültü
    assert sayim[("D", "kaydet")] >= 6         # yordamlar
    assert sayim[("E", "kaydet")] >= 20        # 10 bağlam çifti
    assert sayim[("F", "sor")] >= 40           # tuzak sorular
    assert sayim[("G", "kaydet")] >= 5         # uzun sessizlik


def test_sessiz_gunler_gercekten_var(bench, ana) -> None:
    """Unutma eğrisi ancak hiçbir şeyin olmadığı günlerle ölçülebilir."""
    dolu = {o["gun"] for o in ana["olaylar"] if o["tur"] != "sessiz"}
    sessiz = [g for g in range(1, ana["gun_sayisi"] + 1) if g not in dolu]
    assert len(sessiz) >= 20
    # Kesintisiz en uzun sessizlik: bir haftadan az olursa "uzun sessizlik"
    # kümesi ölçtüğünü iddia ettiği şeyi ölçmüyor demektir.
    en_uzun = 0
    seri = 0
    for gun in range(1, ana["gun_sayisi"] + 1):
        seri = seri + 1 if gun in sessiz else 0
        en_uzun = max(en_uzun, seri)
    assert en_uzun >= 7


def test_uzun_sessizlik_kumesi_gercekten_sessiz(bench, ana) -> None:
    """G kümesindeki kayıt, yazımından sorusuna kadar hiç kullanılmamalı."""
    yazim = {o["slug"]: o["gun"] for o in ana["olaylar"]
             if o["tur"] == "kaydet" and o["kume"] == "G"}
    kullanilan = {s for o in ana["olaylar"] if o["tur"] == "kullan"
                  for s in o["hedef"]}
    for olay in ana["olaylar"]:
        if olay["tur"] == "sor" and olay["kume"] == "G":
            for slug in olay["beklenen"]:
                assert slug not in kullanilan
                assert olay["gun"] - yazim[slug] >= 30, slug


# -- ablation yüzeyi ---------------------------------------------------


def test_bilinmeyen_mekanik_reddedilir(bench) -> None:
    from dornick.recall import anahtar

    with pytest.raises(ValueError):
        anahtar.ayarla(olmayan_mekanik=False)
    assert anahtar.AKTIF.aktivasyon is True


def test_kapali_mekanik_kosudan_sonra_geri_acilir(bench, holdout) -> None:
    from dornick.recall import anahtar

    bench.kosu(holdout, kapali=("aktivasyon",))
    assert anahtar.AKTIF.aktivasyon is True
