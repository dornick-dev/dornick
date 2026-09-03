"""Yaşam benchmark'ının kendisi ölçülebilir mi?

Bir benchmark'a güvenmenin ön şartı iki şey: aynı girdiden aynı sayıyı
üretmesi ve ölçtüğü veri setinin tutarlı olması. İkisi de burada zorlanıyor —
sayılar dalgalanıyorsa faz kabul kriterleri anlamsız, veri seti tutarsızsa
ölçülen şey ürün değil veri setinin hatası olur.

Ayrıca veri setinin **kümelerin vaat ettiği şeyi gerçekten kurduğu**
doğrulanıyor: uzun sessizlik gerçekten sessiz mi, zaman komşuluğu çifti aynı
oturumda peş peşe mi kullanılmış, dikişin iki ucu hiç birlikte yaşanmamış mı.
Bunlar tutmuyorsa metrikler ölçtüklerini iddia ettikleri şeyi ölçmüyor.
"""

from __future__ import annotations

import importlib.util
import sys
from collections import defaultdict
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
BENCH_YOLU = KOK / "eval" / "context_memory" / "life_bench.py"

# Yol haritası 0.2'deki asgari olay sayıları. Küme -> (olay türü, en az).
ASGARI = [
    ("A", "kaydet", 15), ("A", "sor", 30),
    ("B", "duzelt", 24),                      # 8 zincir × 3 düzeltme
    ("C", "kaydet", 60),
    ("D", "kaydet", 6),
    ("E", "kaydet", 20),                      # 10 çift
    ("F", "sor", 40),
    ("G", "kaydet", 5),
    ("H", "kaydet", 24), ("H", "sor", 12),    # 12 çift
    ("I", "kaydet", 8), ("I", "sor", 8),
    ("J", "kaydet", 18), ("J", "sor", 6),     # 6 üçlü
    ("K", "kaydet", 20), ("K", "sor", 20),    # 10 yalıtık + 10 şemalı
    ("N", "kaydet", 20), ("N", "sor", 10),    # 10 çift + kontrol
    ("O", "kaydet", 16), ("O", "sor", 8),     # 8 çift + kontrol
    ("L", "uyan", 9),                         # 3 kesinti noktası × 3
    ("Q", "arac", 10), ("Q", "sor", 10),
]

OLAY_TURLERI = {"kaydet", "sor", "duzelt", "kullan", "arac", "sonuc", "sessiz", "uyan"}


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
    # Süre ölçümleri duvar saatinden geliyor — tek dalgalanan sayılar,
    # karşılaştırmadan çıkarılıyor. Kalan her metrik birebir aynı olmalı.
    for sonuc in (ilk, ikinci):
        for sure in ("gecikme_p95", "gece_suresi", "tur_bloklama"):
            sonuc["metrikler"].pop(sure)
    assert ilk["metrikler"] == ikinci["metrikler"]
    assert ilk["kume"] == ikinci["kume"]
    assert ilk["sayim"] == ikinci["sayim"]


def test_her_metrik_sayi_ya_da_yok(bench, holdout) -> None:
    """`None` = "o sürümde mekanik yoktu"; başka bir tür raporda anlamsız."""
    sonuc = bench.kosu(holdout)
    assert set(sonuc["metrikler"]) == set(bench.HEDEFLER)
    for ad, deger in sonuc["metrikler"].items():
        assert deger is None or isinstance(deger, (int, float)), ad


def test_gunlukler_urunun_kendi_bicimiyle_yaziliyor(bench, holdout, tmp_path) -> None:
    """Gece geçişi (Faz 3) bu günlükleri okuyacak: uydurma biçim olmamalı."""
    bench.kosu(holdout, kok=tmp_path)
    gunlukler = list((tmp_path / "sessions").glob("*.jsonl"))
    assert gunlukler, "oturum günlüğü yazılmamış"

    import json

    turler = set()
    for yol in gunlukler:
        for satir in yol.read_text(encoding="utf-8").splitlines():
            olay = json.loads(satir)
            assert set(olay) >= {"seq", "ts", "kind", "content", "meta"}
            if olay["kind"] == "meta":
                turler.add(olay["content"])
    # Gece tekrarının ihtiyacı: neye dokunuldu, oturum nasıl bitti.
    assert {"session_start", "mind_write", "mind_open", "prime", "sonuc"} <= turler


def test_gunluk_damgalari_sanal_takvimden(bench, holdout, tmp_path) -> None:
    """Oturum günlüğü duvar saatinden yazsaydı doksan gün ölçülemezdi."""
    import json

    bench.kosu(holdout, kok=tmp_path)
    damgalar = []
    for yol in (tmp_path / "sessions").glob("*.jsonl"):
        for satir in yol.read_text(encoding="utf-8").splitlines():
            damgalar.append(json.loads(satir)["ts"])
    assert damgalar
    assert all(d.startswith("2025-") for d in damgalar)


# -- veri seti tutarlılığı ---------------------------------------------


@pytest.mark.parametrize("ad", ["ana", "holdout"])
def test_veri_seti_tutarli(bench, ad: str) -> None:
    veri = bench.veri_yukle(ad)
    gun_sayisi = veri["gun_sayisi"]
    yazilan: dict[str, int] = {}
    for olay in veri["olaylar"]:
        gun = olay["gun"]
        assert 1 <= gun <= gun_sayisi, olay
        assert olay["tur"] in OLAY_TURLERI, olay
        assert olay["oturum"], olay
        assert olay["sira"] >= 1, olay

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
            for slug in [*olay.get("beklenen", []), *olay.get("yasak", []),
                         *olay.get("acik", [])]:
                assert slug in yazilan, f"tanımsız slug: {slug}"
                assert yazilan[slug] <= gun, f"yazılmadan soruldu: {slug}"
            for alan in ("deney", "kontrol", "ustte", "altta"):
                if hedef := (olay.get("olcum") or {}).get(alan):
                    assert hedef in yazilan, f"tanımsız ölçüm hedefi: {hedef}"


@pytest.mark.parametrize("ad", ["ana", "holdout"])
def test_her_oturum_bir_sonucla_kapaniyor(bench, ad: str) -> None:
    """Gece tekrarı oturumu bütün olarak yürüyor; sonucu olmayan oturum
    kaynak değil gürültüdür (yol haritası 3.1)."""
    veri = bench.veri_yukle(ad)
    gecerli = {"basarili", "basarisiz", "duzeltildi", "acik"}
    acik: dict[str, str] = {}
    for olay in veri["olaylar"]:
        if olay["tur"] in ("sessiz", "uyan"):
            continue
        if olay["tur"] == "sonuc":
            assert olay["sonuc"] in gecerli, olay
            acik.pop(olay["oturum"], None)
        else:
            acik.setdefault(olay["oturum"], olay["tur"])
    assert not acik, f"kapanmayan oturum: {sorted(acik)[:5]}"


def test_ana_veri_seti_asgari_olay_sayilarini_karsiliyor(bench, ana) -> None:
    """Yol haritası her küme için bir alt sınır koyuyor; veri seti onu tutmalı."""
    sayim: dict[tuple[str, str], int] = defaultdict(int)
    for olay in ana["olaylar"]:
        sayim[(olay["kume"], olay["tur"])] += 1
    eksik = [(k, t, en_az, sayim[(k, t)])
             for k, t, en_az in ASGARI if sayim[(k, t)] < en_az]
    assert not eksik, f"asgari olay sayısı tutmayan kümeler: {eksik}"


def test_sessiz_gunler_gercekten_var(bench, ana) -> None:
    """Unutma eğrisi ancak hiçbir şeyin olmadığı günlerle ölçülebilir."""
    dolu = {o["gun"] for o in ana["olaylar"] if o["tur"] != "sessiz"}
    sessiz = [g for g in range(1, ana["gun_sayisi"] + 1) if g not in dolu]
    assert len(sessiz) >= 20
    en_uzun = seri = 0
    for gun in range(1, ana["gun_sayisi"] + 1):
        seri = seri + 1 if gun in sessiz else 0
        en_uzun = max(en_uzun, seri)
    assert en_uzun >= 7, "kesintisiz bir haftalık sessizlik yok"


def test_calisma_ritmi_hafta_ici_mesai_saatlerinde(bench, ana) -> None:
    """M kümesi ritim örüntüsü buradan öğreniliyor: hafta içi 09:00-18:00."""
    for olay in ana["olaylar"]:
        if olay["tur"] in ("sessiz", "uyan"):
            continue
        assert 9 <= olay["saat"] <= 18, olay
        assert (olay["gun"] - 1) % 7 < 5, f"hafta sonuna olay düşmüş: {olay}"


# -- kümelerin vaadi ---------------------------------------------------


def test_uzun_sessizlik_kumesi_gercekten_sessiz(bench, ana) -> None:
    """G: yazımından sorusuna kadar kayda hiç dokunulmamalı."""
    yazim = {o["slug"]: o["gun"] for o in ana["olaylar"]
             if o["tur"] == "kaydet" and o["kume"] == "G"}
    kullanilan = {s for o in ana["olaylar"] if o["tur"] == "kullan" for s in o["hedef"]}
    for olay in ana["olaylar"]:
        if olay["tur"] == "sor" and olay["kume"] == "G":
            for slug in olay.get("acik", []):
                assert slug not in kullanilan
                assert olay["gun"] - yazim[slug] >= 30, slug


def test_zaman_komsulugu_cifti_ayni_oturumda_pes_pese(bench, ana) -> None:
    """H: kenarın tek kaynağı bu sıra. Farklı oturumlarda olsa mekanik
    ölçtüğünü iddia ettiği şeyi ölçmezdi."""
    dizi: dict[str, list[str]] = defaultdict(list)
    for olay in ana["olaylar"]:
        if olay["tur"] == "kullan" and olay["kume"] == "H":
            dizi[olay["oturum"]].extend(olay["hedef"])
    ciftler = {tuple(v) for v in dizi.values() if len(v) == 2}
    assert len(ciftler) >= 12
    for x, y in ciftler:
        assert x.endswith("_x") and y.endswith("_y")
        assert x[:-2] == y[:-2]


def test_zaman_komsulugu_cifti_icerikce_benzemiyor(bench, ana) -> None:
    """H'nin bütün anlamı bu: içerik araması bu bağı asla kuramamalı."""
    metin = {o["slug"]: o["icerik"] for o in ana["olaylar"]
             if o["tur"] == "kaydet" and o["kume"] == "H"}
    for slug, icerik in metin.items():
        if not slug.endswith("_x"):
            continue
        es = metin[slug[:-2] + "_y"]
        ortak = ({w[:5].casefold() for w in icerik.split() if len(w) > 4}
                 & {w[:5].casefold() for w in es.split() if len(w) > 4})
        assert not ortak, f"{slug}: çift içerikçe benziyor ({ortak})"


def test_dikis_ucu_hic_birlikte_yasanmadi(bench, ana) -> None:
    """J: A ile C aynı oturumda hiç geçmemeli, yoksa dikiş değil tekrar olur."""
    dizi: dict[str, set[str]] = defaultdict(set)
    for olay in ana["olaylar"]:
        if olay["tur"] == "kullan" and olay["kume"] == "J":
            dizi[olay["oturum"]].update(olay["hedef"])
    ucler = {s.rsplit("_", 1)[0] for v in dizi.values() for s in v}
    assert len(ucler) >= 6
    for kok in ucler:
        for uyeler in dizi.values():
            assert not {f"{kok}_a", f"{kok}_c"} <= uyeler, kok


def test_yalitik_kayit_hic_kullanilmiyor(bench, ana) -> None:
    """K: yalıtık kol gerçekten yalıtık olmalı; kendi oturumunda tek başına."""
    yalitik = {o["slug"]: o["oturum"] for o in ana["olaylar"]
               if o["tur"] == "kaydet" and o["kume"] == "K"
               and o["slug"].startswith("k_y")}
    assert len(yalitik) >= 10
    kullanilan = {s for o in ana["olaylar"] if o["tur"] == "kullan" for s in o["hedef"]}
    oturum_boyu: dict[str, int] = defaultdict(int)
    for olay in ana["olaylar"]:
        if olay["tur"] in ("kaydet", "kullan"):
            oturum_boyu[olay["oturum"]] += 1
    for slug, oturum in yalitik.items():
        assert slug not in kullanilan, slug
        assert oturum_boyu[oturum] == 1, f"{slug} yalnız değil"


def test_ters_tekrar_ayni_hatirayi_iki_sonuca_baglıyor(bench, ana) -> None:
    """I: iyi yordam başarılı, kötü yordam başarısız oturumda kullanılmalı."""
    sonuclar = {o["oturum"]: o["sonuc"] for o in ana["olaylar"] if o["tur"] == "sonuc"}
    goren: dict[str, set[str]] = defaultdict(set)
    for olay in ana["olaylar"]:
        if olay["tur"] == "kullan" and olay["kume"] == "I":
            for slug in olay["hedef"]:
                goren[slug].add(sonuclar.get(olay["oturum"], ""))
    iyiler = [s for s in goren if s.endswith("_iyi")]
    assert len(iyiler) >= 8
    for slug, sonuc_kumesi in goren.items():
        beklenen = "basarili" if slug.endswith("_iyi") else "basarisiz"
        assert sonuc_kumesi == {beklenen}, (slug, sonuc_kumesi)


def test_anlik_ders_sorusu_ayni_oturumda(bench, ana) -> None:
    """Q: soru, hatanın geldiği oturumun İÇİNDE sorulmalı — gece beklenmeden."""
    faulty: dict[str, int] = {}
    for olay in ana["olaylar"]:
        if olay["tur"] == "arac" and olay["kume"] == "Q" and olay.get("hata"):
            faulty[olay["oturum"]] = olay["sira"]
    assert len(faulty) >= 10
    sorular = [o for o in ana["olaylar"] if o["tur"] == "sor" and o["kume"] == "Q"]
    assert len(sorular) >= 10
    for olay in sorular:
        assert olay["oturum"] in faulty, olay
        assert olay["sira"] > faulty[olay["oturum"]], olay


def test_kesinti_noktalari_uce_bolunmus(bench, ana) -> None:
    """L: %30 / %60 / %90'da kesilen üçer gece."""
    yuzdeler = [o["baglam"]["yuzde"] for o in ana["olaylar"] if o["tur"] == "uyan"]
    assert len(yuzdeler) >= 9
    for hedef in (30, 60, 90):
        assert yuzdeler.count(hedef) >= 3


# -- ablation yüzeyi ---------------------------------------------------


def test_bilinmeyen_mekanik_reddedilir() -> None:
    from dornick.recall import switches

    with pytest.raises(ValueError):
        switches.configure(olmayan_mekanik=False)
    assert switches.ACTIVE.activation is True


def test_kapali_mekanik_kosudan_sonra_geri_acilir(bench, holdout) -> None:
    from dornick.recall import switches

    bench.kosu(holdout, disabled=("activation",))
    assert switches.ACTIVE.activation is True


def test_ablation_adlari_hedeflerle_ortusuyor(bench) -> None:
    """Her mekaniğin bir anahtarı, her metriğin bir hedefi olmalı."""
    from dornick.recall import switches

    assert set(switches.NAMES) == {"activation", "supersede", "weave", "distillation",
                                  "encoding", "context"}
    assert all(len(v) == 3 for v in bench.HEDEFLER.values())
