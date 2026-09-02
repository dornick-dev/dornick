"""Yaşam benchmark'ı: hafızanın günler içindeki davranışı.

`scale_bench.py` tek turluk bir soru soruyor — "bu sorguya bu yüz hatıradan
hangileri gelmeli". Zamanı, tekrarı ve düzeltmeyi ölçmüyor. Oysa insan
benzeri hafızanın bütün iddiası zamanla ilgili: kullanılan iz güçlenir,
kullanılmayan geride kalır, düzeltilen bilgi eskisinin yerini alır. Bunların
hiçbiri tek turda görünmez.

Burası o eksiği kapatıyor: elde dondurulmuş bir yaşam senaryosu var
(`yasam_dataset.json`, 90 sanal gün) ve bench onu **sanal saatle** gün gün
oynatıyor. Her `sor` olayında ürünün kendi `select_prime`ı ve `mind.soul()`u
çağrılıyor — kopyalanmış seçim mantığı yok, ölçülen yol ürünün kendi yolu
(scale_bench.py ile aynı ilke).

Koşum:

    py eval/context_memory/yasam_bench.py --etiket taban
    py eval/context_memory/yasam_bench.py --etiket f1 --taban taban
    py eval/context_memory/yasam_bench.py --kapat aktivasyon --etiket f1-ablasyon
    py eval/context_memory/yasam_bench.py --veri holdout --etiket holdout
    py eval/context_memory/yasam_bench.py --tablo        # birikmiş özet tablo

Raporlar `docs/charts/yasam-<etiket>.json` ve `.md` olarak düşüyor.

Ölçüm dürüstlüğü üzerine iki not:

* Sorular, beklenen kaydın içerik kelimelerinden en az birini taşıyacak
  şekilde yazıldı. Bu bir kolaylaştırma değil, kapsam kararı: Türkçe
  biçimbiliminin (ünsüz yumuşaması, ekler) sözcüksel aramada açtığı gedik
  ayrı bir sorundur ve bu yol haritasının hiçbir fazı onu çözmeyi
  hedeflemiyor. Veri seti onunla dolduruşsa bütün metrikler o gediğin
  gürültüsünde boğulur ve zaman/pekişme/güncelleme farkı görünmez olurdu.
* `G` kümesi (uzun sessizlik) `prime_precision`/`prime_recall`
  ortalamalarına GİRMİYOR. Unutulmuş bir kaydın kendiliğinden önyüklemeye
  girmemesi tasarımın amacı; onu recall'a saymak, mekaniği kendi hedefiyle
  çelişen bir sayıyla cezalandırmak olurdu. G'nin kendi metriği var
  (`geri_donus_recall`) ve o, modelin AÇIK araması üzerinden ölçülüyor.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

BURASI = Path(__file__).resolve().parent
KOK = BURASI.parents[1]
sys.path.insert(0, str(KOK / "src"))
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
except Exception:
    pass

from dornick.loop import (  # noqa: E402
    RECALL_PRIME_LIMIT,
    prime_note,
    select_prime,
    worth_recalling,
)
from dornick.mind import open_mind  # noqa: E402
from dornick.recall import anahtar  # noqa: E402
from dornick.recall import vector  # noqa: E402

# Türkçe için kaba token tahmini: ~4 karakter = 1 token. Mutlak değer önemli
# değil — bütün yöntemler AYNI cetvelle karşılaştırılıyor.
KARAKTER_BASI_TOKEN = 4.0

# Ruhta görünen türler (Soul alanları). `fact` ve `episode` ruha girmiyor.
RUH_TURLERI = ("user", "preference", "lesson", "voice", "procedure")

# Precision/recall ortalamasına giren kümeler. F'nin beklediği boşluk,
# G'nin beklediği şey uzun sessizlikten dönüş — ikisinin de kendi metriği var.
ADIL_KUMELER = ("A", "B", "D", "E")

# Tazelik penceresi: "son 7 günde düzeltilen kayıt ruha girmiş mi".
TAZE_PENCERE_GUN = 7

# Gecikme ölçümü için doldurulacak düğüm sayısı. 50k, kullanıcının koyduğu
# ölçek şartı; bütçe 20 ms.
OLCEK_DUGUM = 50_000
GECIKME_BUTCE_MS = 20.0

HEDEFLER: dict[str, tuple[str, float | None]] = {
    "prime_precision": (">=", 0.85),
    "prime_recall": (">=", 0.80),
    "yasak_sizinti": ("<=", 0.0),
    "tuzak_sessizlik": (">=", 0.90),
    "bayat_ruh": ("<=", 0.0),
    "taze_ruh": (">=", 0.80),
    "ruh_token": ("<=", None),        # tabanı geçmesin
    "prime_token": ("<=", None),      # tabanın %85'i (Faz 3 hedefi)
    "geri_donus_recall": (">=", 0.70),
    "gecikme_p95": ("<=", GECIKME_BUTCE_MS),
}

YON = {
    "prime_precision": "↑", "prime_recall": "↑", "yasak_sizinti": "↓",
    "tuzak_sessizlik": "↑", "bayat_ruh": "↓", "taze_ruh": "↑",
    "ruh_token": "↓", "prime_token": "↓", "geri_donus_recall": "↑",
    "gecikme_p95": "↓",
}


def token(metin: str) -> float:
    return len(metin) / KARAKTER_BASI_TOKEN


# -- sanal saat --------------------------------------------------------


class SanalSaat:
    """Senaryonun takvimi. Ürün bunu duvar saati sanır (bkz. recall/saat.py).

    Her olay saati en az bir dakika ileri itiyor: aynı anda yazılan iki
    kaydın sırası `created` damgasında kaybolmasın (ruh tazelik sıralaması
    buna bakıyor).
    """

    def __init__(self, baslangic: datetime) -> None:
        self.baslangic = baslangic
        self.an = baslangic

    def __call__(self) -> datetime:
        return self.an

    def ilerle(self, gun: int, saat: int) -> None:
        hedef = self.baslangic + timedelta(days=gun - 1, hours=saat)
        self.an = max(hedef, self.an + timedelta(minutes=1))


# -- senaryo -----------------------------------------------------------


def veri_yukle(ad: str) -> dict[str, Any]:
    dosya = {"ana": "yasam_dataset.json", "holdout": "yasam_holdout.json"}.get(ad, ad)
    return json.loads((BURASI / dosya).read_text(encoding="utf-8"))


class Olcum:
    """Senaryo boyunca biriken sayaçlar."""

    def __init__(self) -> None:
        self.kesisim = 0          # prime'a giren doğru kayıt (adil kümeler)
        self.prime_boyu = 0       # prime'a giren toplam kayıt (adil kümeler)
        self.beklenen_boyu = 0
        self.sizinti = 0
        self.tuzak_toplam = 0
        self.tuzak_sessiz = 0
        self.geri_donus: list[float] = []
        self.gecikmeler: list[float] = []
        self.prime_tokenlar: list[float] = []
        self.ruh_tokenlar: list[float] = []
        self.bayat_gunluk: list[int] = []
        self.taze_oranlar: list[float] = []
        self.soru_sayisi = 0
        self.kume_kesisim: dict[str, int] = {}
        self.kume_beklenen: dict[str, int] = {}
        self.kume_prime: dict[str, int] = {}


def kosu(
    veri: dict[str, Any],
    *,
    kapali: tuple[str, ...] = (),
    kok: Path | None = None,
) -> dict[str, Any]:
    """Senaryoyu gün gün oynatır ve metrikleri döndürür."""
    anahtar.sifirla()
    if kapali:
        anahtar.ayarla(**{ad: False for ad in kapali})

    baslangic = datetime.fromisoformat(veri["baslangic"])
    if baslangic.tzinfo is None:
        baslangic = baslangic.replace(tzinfo=timezone.utc)
    saat = SanalSaat(baslangic)

    gecici = None
    if kok is None:
        gecici = tempfile.TemporaryDirectory(prefix="yasam-bench-")
        kok = Path(gecici.name)

    try:
        mind = open_mind(kok / "mind", kok / "sessions", "bench", saat=saat)
        return _oyna(mind, veri, saat)
    finally:
        anahtar.sifirla()
        if gecici is not None:
            try:
                mind.store.close()
            except Exception:
                pass
            try:
                gecici.cleanup()
            except (OSError, PermissionError):
                pass  # Windows'ta WAL dosyası kilitli kalabilir; geçici dizin


def _oyna(mind: Any, veri: dict[str, Any], saat: SanalSaat) -> dict[str, Any]:
    olaylar: list[dict[str, Any]] = veri["olaylar"]
    gun_sayisi = int(veri["gun_sayisi"])
    gunluk: dict[int, list[dict[str, Any]]] = {}
    for olay in olaylar:
        gunluk.setdefault(int(olay["gun"]), []).append(olay)

    kimlik: dict[str, str] = {}          # slug -> node id
    slug_of: dict[str, str] = {}         # node id -> slug
    baglam_of: dict[str, dict] = {}      # slug -> yazım anındaki bağlam
    bayat: set[str] = set()              # supersede edilmiş slug'lar
    duzeltme_gunu: list[tuple[int, str, str]] = []   # (gün, slug, kind)

    o = Olcum()

    def _yaz(olay: dict[str, Any]) -> None:
        hafiza = mind.remember(
            olay["icerik"],
            kind=olay["kind"],
            title=olay.get("baslik") or "",
            tags=olay.get("etiketler") or [],
        )
        kimlik[olay["slug"]] = hafiza.id
        slug_of[hafiza.id] = olay["slug"]
        if olay.get("baglam"):
            baglam_of[olay["slug"]] = olay["baglam"]

    for gun in range(1, gun_sayisi + 1):
        for olay in sorted(gunluk.get(gun, []), key=lambda e: e["saat"]):
            saat.ilerle(gun, int(olay["saat"]))
            tur = olay["tur"]

            if tur == "sessiz":
                continue

            if tur == "kaydet":
                _yaz(olay)

            elif tur == "duzelt":
                eski_id = kimlik.get(olay["eskisi"], "")
                # Faz 2'den önce ürün böyle davranıyor: çelişen yeni kayıt
                # eskisinin YANINA yazılıyor, eskisi ortada kalıyor. Taban
                # çizgisinin ölçtüğü yara tam olarak bu.
                guncelle = getattr(mind, "guncelle", None)
                if guncelle is not None and eski_id and anahtar.AKTIF.supersede:
                    hafiza = guncelle(
                        eski_id,
                        olay["icerik"],
                        kind=olay["kind"],
                        title=olay.get("baslik") or "",
                        tags=olay.get("etiketler") or [],
                    )
                    kimlik[olay["slug"]] = hafiza.id
                    slug_of[hafiza.id] = olay["slug"]
                else:
                    _yaz(olay)
                bayat.add(olay["eskisi"])
                duzeltme_gunu.append((gun, olay["slug"], olay["kind"]))

            elif tur == "kullan":
                for slug in olay["hedef"]:
                    if nid := kimlik.get(slug):
                        mind.store.open(nid)

            elif tur == "sor":
                _sorgu(mind, olay, o, slug_of, baglam_of)

        # Gün sonu: ruhun o günkü hali. Ruh sistem promptunun parçası,
        # yani her oturumun sabit maliyeti — günde bir kez ölçülüyor.
        saat.ilerle(gun, 23)
        ruh = mind.soul()
        ruh_slugs = {slug_of.get(m.id, "") for m in _ruh_kayitlari(ruh)}
        o.ruh_tokenlar.append(token(ruh.render()))
        o.bayat_gunluk.append(len(ruh_slugs & bayat))

        taze = {s for g, s, k in duzeltme_gunu
                if gun - TAZE_PENCERE_GUN < g <= gun and k in RUH_TURLERI}
        if taze:
            o.taze_oranlar.append(len(taze & ruh_slugs) / len(taze))

    return _rapor(o, mind)


def _ruh_kayitlari(ruh: Any) -> list[Any]:
    return [*ruh.user, *ruh.preferences, *ruh.lessons, *ruh.voice, *ruh.procedures]


def _sorgu(
    mind: Any,
    olay: dict[str, Any],
    o: Olcum,
    slug_of: dict[str, str],
    baglam_of: dict[str, dict],
) -> None:
    soru = olay["icerik"]
    kume = olay["kume"]
    beklenen = set(olay.get("beklenen") or [])
    yasak = set(olay.get("yasak") or [])

    basla = time.perf_counter()
    # Ürünün kendi kapısı: `_prime_recall` önce buna bakıyor. Selamlaşmayı
    # hafızaya götürmemek de ölçülen davranışın parçası.
    if worth_recalling(soru):
        isabetler = _prime(mind, soru, olay.get("baglam"))
    else:
        isabetler = []
    o.gecikmeler.append((time.perf_counter() - basla) * 1000.0)

    prime_slugs = {slug_of.get(h.item.id, "") for h in isabetler}
    prime_slugs.discard("")
    o.prime_tokenlar.append(token(prime_note(isabetler)) if isabetler else 0.0)
    o.soru_sayisi += 1

    o.sizinti += len(prime_slugs & yasak)

    if kume in ADIL_KUMELER:
        kesisim = len(prime_slugs & beklenen)
        o.kesisim += kesisim
        o.prime_boyu += len(prime_slugs)
        o.beklenen_boyu += len(beklenen)
        o.kume_kesisim[kume] = o.kume_kesisim.get(kume, 0) + kesisim
        o.kume_prime[kume] = o.kume_prime.get(kume, 0) + len(prime_slugs)
        o.kume_beklenen[kume] = o.kume_beklenen.get(kume, 0) + len(beklenen)

    if kume == "F":
        o.tuzak_toplam += 1
        o.tuzak_sessiz += int(not isabetler)

    if kume == "G" and beklenen:
        # Uzun sessizlikten dönüş AÇIK arama ile ölçülüyor: kendiliğinden
        # önyükleme unutulmuş kaydı bilerek getirmiyor, ama kullanıcı konuyu
        # açtığında model `mind_recall` çağırınca kayıt hâlâ bulunabilmeli.
        acik = mind.recall(soru, limit=8)
        bulunan = {slug_of.get(h.item.id, "") for h in acik}
        o.geri_donus.append(len(bulunan & beklenen) / len(beklenen))


def _prime(mind: Any, soru: str, baglam: dict | None) -> list[Any]:
    """Ürünün önyükleme seçimi. Bağlam parametresi Faz 5'te geliyor."""
    if baglam:
        try:
            return select_prime(mind, soru, limit=RECALL_PRIME_LIMIT,
                                ham=soru, baglam=baglam)
        except TypeError:
            pass
    return select_prime(mind, soru, limit=RECALL_PRIME_LIMIT, ham=soru)


def _rapor(o: Olcum, mind: Any) -> dict[str, Any]:
    def oran(pay: float, payda: float) -> float:
        return round(pay / payda, 4) if payda else 0.0

    kume_detay = {
        k: {
            "precision": oran(o.kume_kesisim.get(k, 0), o.kume_prime.get(k, 0)),
            "recall": oran(o.kume_kesisim.get(k, 0), o.kume_beklenen.get(k, 0)),
        }
        for k in ADIL_KUMELER
    }
    return {
        "metrikler": {
            "prime_precision": oran(o.kesisim, o.prime_boyu),
            "prime_recall": oran(o.kesisim, o.beklenen_boyu),
            "yasak_sizinti": float(o.sizinti),
            "tuzak_sessizlik": oran(o.tuzak_sessiz, o.tuzak_toplam),
            "bayat_ruh": round(statistics.fmean(o.bayat_gunluk), 4) if o.bayat_gunluk else 0.0,
            "taze_ruh": round(statistics.fmean(o.taze_oranlar), 4) if o.taze_oranlar else 0.0,
            "ruh_token": round(statistics.fmean(o.ruh_tokenlar), 1) if o.ruh_tokenlar else 0.0,
            "prime_token": round(statistics.fmean(o.prime_tokenlar), 1) if o.prime_tokenlar else 0.0,
            "geri_donus_recall": round(statistics.fmean(o.geri_donus), 4) if o.geri_donus else 0.0,
            "gecikme_p95": round(_p95(o.gecikmeler), 2),
        },
        "kume": kume_detay,
        "sayim": {
            "soru": o.soru_sayisi,
            "dugum": mind.store.count(),
            "tuzak": o.tuzak_toplam,
        },
    }


def _p95(degerler: list[float]) -> float:
    if not degerler:
        return 0.0
    sirali = sorted(degerler)
    return sirali[min(len(sirali) - 1, int(round(0.95 * (len(sirali) - 1))))]


# -- ölçekte gecikme ---------------------------------------------------


def gecikme_olc(veri: dict[str, Any], dugum: int) -> dict[str, float]:
    """50k düğümlük bir bellekte `recall` gecikmesi.

    Senaryonun kendi hacmi birkaç yüz düğüm; ölçek şartı ayrı ölçülüyor.
    Dolgu düğümleri doğrudan SQL ile yazılıyor — bu bir fikstür kurulumu,
    ölçülen yol değil; ölçülen yol yine ürünün `recall`ı.
    """
    sorular = [o["icerik"] for o in veri["olaylar"] if o["tur"] == "sor"]
    with tempfile.TemporaryDirectory(prefix="yasam-olcek-") as ad:
        kok = Path(ad)
        saat = SanalSaat(datetime(2025, 1, 6, tzinfo=timezone.utc))
        mind = open_mind(kok / "mind", kok / "sessions", "olcek", saat=saat)
        try:
            _doldur(mind.store, dugum, veri)
            gecikmeler = []
            for i, soru in enumerate(sorular):
                saat.ilerle(90, 9 + i % 8)
                basla = time.perf_counter()
                mind.recall(soru, limit=8)
                gecikmeler.append((time.perf_counter() - basla) * 1000.0)
            return {
                "dugum": mind.store.count(),
                "gecikme_p50": round(statistics.median(gecikmeler), 2),
                "gecikme_p95": round(_p95(gecikmeler), 2),
            }
        finally:
            mind.store.close()


def _doldur(store: Any, hedef: int, veri: dict[str, Any]) -> None:
    """Belleği hedef düğüm sayısına kadar sentetik kayıtla doldurur."""
    govdeler = [o["icerik"] for o in veri["olaylar"] if o.get("icerik")]
    if not govdeler:
        return
    satirlar = []
    for i in range(hedef):
        govde = f"{govdeler[i % len(govdeler)]} (dolgu {i})"
        baslik = govde[:60]
        imza = vector.signature(f"{baslik} {govde} dolgu")
        satirlar.append((f"n_dolgu{i:06d}", "fact", baslik, govde, "dolgu", "",
                         "2025-01-06T00:00:00.000+00:00", vector.to_blob(imza)))
    with store._lock:                                  # noqa: SLF001 — fikstür
        store._db.executemany(
            "INSERT OR IGNORE INTO node(id, kind, title, body, tags, session,"
            " created, sig) VALUES (?,?,?,?,?,?,?,?)", satirlar)
        store._db.commit()
    store._index = None


# -- rapor -------------------------------------------------------------


def CHARTS() -> Path:
    yol = KOK / "docs" / "charts"
    yol.mkdir(parents=True, exist_ok=True)
    return yol


def markdown_yaz(etiket: str, sonuc: dict[str, Any], taban: dict[str, Any] | None) -> Path:
    m = sonuc["metrikler"]
    t = (taban or {}).get("metrikler", {})
    satirlar = [
        f"# Yaşam benchmark'ı — `{etiket}`",
        "",
        f"Senaryo: **{sonuc['veri']}** · {sonuc['sayim']['soru']} soru · "
        f"{sonuc['sayim']['dugum']} düğüm · kapalı mekanik: "
        f"`{', '.join(sonuc['kapali']) or 'yok'}`",
        "",
        "| Metrik | Yön | Değer | Taban | Fark | Hedef |",
        "|---|---|---|---|---|---|",
    ]
    for ad, deger in m.items():
        yon_ok, hedef = HEDEFLER[ad]
        taban_deger = t.get(ad)
        if taban_deger is None:
            fark = "—"
            taban_metin = "—"
        else:
            taban_metin = f"{taban_deger:g}"
            delta = deger - taban_deger
            fark = f"{delta:+.4g}" if delta else "0"
        hedef_metin = f"{yon_ok} {hedef:g}" if hedef is not None else "≤ taban"
        satirlar.append(
            f"| `{ad}` | {YON[ad]} | {deger:g} | {taban_metin} | {fark} | {hedef_metin} |")

    satirlar += ["", "## Küme kırılımı (precision / recall)", "",
                 "| Küme | Ne ölçer | Precision | Recall |", "|---|---|---|---|"]
    ACIKLAMA = {
        "A": "sabit gerçekler", "B": "düzeltme zincirleri",
        "D": "tekrar kullanılan yordamlar", "E": "bağlam çakışması",
    }
    for k, d in sonuc["kume"].items():
        satirlar.append(f"| {k} | {ACIKLAMA[k]} | {d['precision']:g} | {d['recall']:g} |")

    if olcek := sonuc.get("olcek"):
        satirlar += [
            "", "## Ölçekte gecikme", "",
            f"{olcek['dugum']} düğüm · p50 **{olcek['gecikme_p50']:g} ms** · "
            f"p95 **{olcek['gecikme_p95']:g} ms** (bütçe {GECIKME_BUTCE_MS:g} ms)",
        ]

    satirlar += ["", "---", "",
                 "Üretim: `py eval/context_memory/yasam_bench.py --etiket "
                 f"{etiket}`. Sayılar deterministiktir: aynı veri seti, aynı "
                 "sanal takvim, aynı sonuç."]
    yol = CHARTS() / f"yasam-{etiket}.md"
    yol.write_text("\n".join(satirlar) + "\n", encoding="utf-8")
    return yol


def ozet_tablo() -> Path:
    """docs/charts altındaki bütün koşuları tek tabloda toplar."""
    dosyalar = sorted(CHARTS().glob("yasam-*.json"))
    kosular = []
    for dosya in dosyalar:
        try:
            kosular.append(json.loads(dosya.read_text(encoding="utf-8")))
        except ValueError:
            continue
    kosular.sort(key=lambda k: (k.get("sira", 99), k.get("etiket", "")))
    basliklar = [k["etiket"] for k in kosular]
    satirlar = ["# Yaşam benchmark'ı — birikmiş özet", "",
                "| Metrik | Yön | " + " | ".join(basliklar) + " | Hedef |",
                "|---" * (len(basliklar) + 3) + "|"]
    for ad in HEDEFLER:
        yon_ok, hedef = HEDEFLER[ad]
        degerler = [f"{k['metrikler'].get(ad, float('nan')):g}" for k in kosular]
        hedef_metin = f"{yon_ok} {hedef:g}" if hedef is not None else "≤ taban"
        satirlar.append(f"| `{ad}` | {YON[ad]} | " + " | ".join(degerler)
                        + f" | {hedef_metin} |")
    yol = CHARTS() / "yasam-ozet.md"
    yol.write_text("\n".join(satirlar) + "\n", encoding="utf-8")
    return yol


# -- giriş -------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    ayrıştırıcı = argparse.ArgumentParser(description=__doc__)
    ayrıştırıcı.add_argument("--veri", default="ana",
                            help="ana | holdout | dosya adı")
    ayrıştırıcı.add_argument("--etiket", default="", help="rapor adı (docs/charts/yasam-<etiket>)")
    ayrıştırıcı.add_argument("--taban", default="",
                            help="karşılaştırılacak önceki koşunun etiketi")
    ayrıştırıcı.add_argument("--kapat", default="",
                            help=f"virgülle: {', '.join(anahtar.ADLAR)}")
    ayrıştırıcı.add_argument("--sira", type=int, default=99,
                            help="özet tablodaki sütun sırası")
    ayrıştırıcı.add_argument("--hizli", action="store_true",
                            help="ölçek gecikme ölçümünü atla")
    ayrıştırıcı.add_argument("--olcek", type=int, default=OLCEK_DUGUM,
                            help="gecikme ölçümündeki dolgu düğüm sayısı")
    ayrıştırıcı.add_argument("--json", action="store_true", help="yalnız JSON bas")
    ayrıştırıcı.add_argument("--tablo", action="store_true",
                            help="birikmiş özet tabloyu üret ve çık")
    args = ayrıştırıcı.parse_args(argv)

    if args.tablo:
        print(ozet_tablo())
        return 0

    kapali = tuple(a.strip() for a in args.kapat.split(",") if a.strip())
    bilinmeyen = set(kapali) - set(anahtar.ADLAR)
    if bilinmeyen:
        print(f"Bilinmeyen mekanik: {', '.join(sorted(bilinmeyen))}", file=sys.stderr)
        return 2

    veri = veri_yukle(args.veri)
    basla = time.perf_counter()
    sonuc = kosu(veri, kapali=kapali)
    sonuc["veri"] = veri["ad"]
    sonuc["kapali"] = list(kapali)
    sonuc["etiket"] = args.etiket or "adsiz"
    sonuc["sira"] = args.sira
    sonuc["sure_sn"] = round(time.perf_counter() - basla, 1)

    if not args.hizli:
        sonuc["olcek"] = gecikme_olc(veri, args.olcek)
        # Ölçek şartı senaryonun kendi hacminde değil, 50k'da geçerli:
        # raporlanan p95 ölçekteki p95.
        sonuc["metrikler"]["gecikme_p95"] = sonuc["olcek"]["gecikme_p95"]

    if args.json:
        print(json.dumps(sonuc, ensure_ascii=False, indent=1))
        return 0

    taban = None
    if args.taban:
        yol = CHARTS() / f"yasam-{args.taban}.json"
        if yol.exists():
            taban = json.loads(yol.read_text(encoding="utf-8"))
        else:
            print(f"Uyarı: taban raporu yok: {yol}", file=sys.stderr)

    if args.etiket:
        (CHARTS() / f"yasam-{args.etiket}.json").write_text(
            json.dumps(sonuc, ensure_ascii=False, indent=1), encoding="utf-8")
        print(markdown_yaz(args.etiket, sonuc, taban))

    genislik = max(len(a) for a in sonuc["metrikler"])
    for ad, deger in sonuc["metrikler"].items():
        print(f"  {ad:<{genislik}}  {YON[ad]}  {deger:g}")
    print(f"  {'süre':<{genislik}}     {sonuc['sure_sn']:g} sn")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
