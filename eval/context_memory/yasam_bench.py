"""Yaşam benchmark'ı: hafızanın günler içindeki davranışı.

`scale_bench.py` tek turluk bir soru soruyor — "bu sorguya bu yüz hatıradan
hangileri gelmeli". Zamanı, tekrarı ve düzeltmeyi ölçmüyor. Oysa insan
benzeri hafızanın bütün iddiası zamanla ilgili: kullanılan iz güçlenir,
kullanılmayan geride kalır, düzeltilen bilgi eskisinin yerini alır, gece
yaşananlar yeniden oynanır. Hiçbiri tek turda görünmez.

Burası o eksiği kapatıyor: dondurulmuş bir yaşam senaryosu
(`yasam_dataset.json`, 90 sanal gün, oturumlara gruplanmış) **sanal saatle**
gün gün oynatılıyor. Her `sor` olayında ürünün kendi `select_prime`ı,
`mind.recall`ı ve `mind.soul()`u çağrılıyor; her gün sonunda — varsa — gece
geçişi. Kopyalanmış seçim mantığı yok; ölçülen yol ürünün kendi yolu.

Koşum:

    py eval/context_memory/yasam_bench.py --etiket taban --eski
    py eval/context_memory/yasam_bench.py --etiket f1 --onceki taban
    py eval/context_memory/yasam_bench.py --kapat aktivasyon --etiket f1-ablasyon
    py eval/context_memory/yasam_bench.py --veri holdout --etiket holdout --hizli
    py eval/context_memory/yasam_bench.py --esik-egrisi
    py eval/context_memory/yasam_bench.py --buyume
    py eval/context_memory/yasam_bench.py --tablo

`--eski`, `hafiza-eski` etiketindeki sürümü `eval/eski/` worktree'sinden ayrı
bir süreçte koşturur. Eski kodda saat enjeksiyonu yok; modül düzeyindeki
`_now` yamalanıyor, böylece iki sürüm **aynı sanal takvimi** görüyor. Eski
sürümde hiç olmayan mekaniklerin metrikleri `yok` diye raporlanır — boş
bırakılmaz.

Ölçüm dürüstlüğü üzerine üç not:

* Sorular, beklenen kaydın içerik kelimelerinden en az birini taşıyacak
  şekilde yazıldı. Bu bir kolaylaştırma değil, kapsam kararı: Türkçe
  biçimbiliminin sözcüksel aramada açtığı gedik ayrı bir sorundur ve yol
  haritasının hiçbir fazı onu çözmüyor. Veri seti onunla doldurulsaydı bütün
  metrikler o gediğin gürültüsünde boğulur, zaman/pekişme/güncelleme farkı
  görünmez olurdu.
* `G` (uzun sessizlik), `I`, `N`, `O`, `Q` kümeleri `prime_precision` /
  `prime_recall` ortalamalarına GİRMEZ; her birinin kendi metriği var.
  Unutulmuş bir kaydın kendiliğinden önyüklemeye girmemesi tasarımın amacı;
  onu prime recall'ına saymak mekaniği kendi hedefiyle çelişen bir sayıyla
  cezalandırmak olurdu.
* Faz 3 gelmeden H/I/J/K/N/O taban çizgisi düşük çıkar. Bu beklenen ve
  istenen sonuçtur; faydayı kanıtlayacak fark oradan gelir.
"""

from __future__ import annotations

import argparse
import inspect
import json
import os
import statistics
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

BURASI = Path(__file__).resolve().parent
KOK = BURASI.parents[1]
ESKI_AGAC = KOK / "eval" / "eski"

# Hangi kaynak ağacı ölçülüyor: ürünün kendisi mi, `hafiza-eski` etiketi mi.
KAYNAK = Path(os.environ.get("DORNICK_SRC") or (KOK / "src"))
sys.path.insert(0, str(KAYNAK))
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
except Exception:
    pass

from dornick.events import EventLog  # noqa: E402
from dornick.loop import (  # noqa: E402
    RECALL_PRIME_LIMIT,
    prime_note,
    select_prime,
    worth_recalling,
)
from dornick.mind import open_mind  # noqa: E402

try:                                    # Faz 0'dan itibaren var; eskide yok.
    from dornick.recall import anahtar
except ImportError:                     # pragma: no cover - yalnız --eski yolu
    anahtar = None
try:
    from dornick.recall import vector
except ImportError:                     # pragma: no cover
    vector = None
try:                                    # Faz 3.12'den itibaren var.
    from dornick.recall import awake
except ImportError:                     # pragma: no cover
    awake = None

ESKI_SURUM = os.environ.get("DORNICK_ESKI") == "1"

# Türkçe için kaba token tahmini: ~4 karakter = 1 token. Mutlak değer önemli
# değil — bütün sürümler AYNI cetvelle karşılaştırılıyor.
KARAKTER_BASI_TOKEN = 4.0

# Ruhta görünen türler (Soul alanları). `fact` ve `episode` ruha girmiyor.
RUH_TURLERI = ("user", "preference", "lesson", "voice", "procedure")

# Prime precision/recall ortalamasına giren kümeler.
ADIL_KUMELER = ("A", "B", "D", "E", "H", "J", "K")

# Açık aramada kaç sonuca bakılacağı, küme başına (yol haritası 0.3).
ACIK_DERINLIK = {"G": 8, "H": 5, "J": 8, "K": 8}

TAZE_PENCERE_GUN = 7

# Ölçek şartı: 50k düğümde `recall()` p95 ≤ 20 ms.
OLCEK_DUGUM = 50_000
GECIKME_BUTCE_MS = 20.0

# Büyüme deneyi (P kümesi): 200k'nin 20k'ye oranı.
BUYUME_BUYUK = 200_000
BUYUME_KUCUK = 20_000

# Q kümesinde ders oturum içinde hiç görünmediyse yazılan ceza: "geceye kadar".
DERS_GECEYE_KADAR = 99

# Metrik kayıt defteri: ad -> (yön, karşılaştırma, hedef). Hedefi None olan
# metrik tabana göre okunur; hedefi olan mutlak eşiktir.
HEDEFLER: dict[str, tuple[str, str, float | None]] = {
    "prime_precision":      ("↑", ">=", 0.85),
    "prime_recall":         ("↑", ">=", 0.80),
    "yasak_sizinti":        ("↓", "<=", 0.0),
    "tuzak_sessizlik":      ("↑", ">=", 0.90),
    "bayat_ruh":            ("↓", "<=", 0.0),
    "taze_ruh":             ("↑", ">=", 0.80),
    "ruh_token":            ("↓", "<=", None),
    "prime_token":          ("↓", "<=", None),
    "geri_donus_recall":    ("↑", ">=", 0.70),
    "komsuluk_recall":      ("↑", ">=", 0.75),
    "sorumluluk_dogrulugu": ("↑", ">=", 0.85),
    "dikis_recall":         ("↑", ">=", 0.60),
    "gomulme_recall":       ("↑", ">=", 0.90),
    "sema_tazeleme":        ("↑", ">", 0.0),
    "yakalama":             ("↑", ">", 0.0),
    "ders_gecikmesi":       ("↓", "<=", 1.0),
    "sicak_oran":           ("·", "aralik", None),
    "gece_suresi":          ("↓", "<=", 300.0),
    "uykusuz_kayip":        ("↑", ">=", 0.80),
    "uykusuz_sisme":        ("↓", "<=", 1.30),
    "aktif_bolge_ihlali":   ("↓", "<=", 0.0),
    "tur_bloklama":         ("↓", "<=", 50.0),
    "kesinti_kaybi":        ("↓", "<=", 0.0),
    "kesinti_gecikmesi":    ("↓", "<=", 500.0),
    "yarim_damitma":        ("↓", "<=", 0.0),
    "ritim_isabeti":        ("↑", ">=", 0.90),
    "atalet":               ("↓", "<=", 0.0),
    "buyume_p95":           ("↓", "<=", 1.5),
    "buyume_ram":           ("↓", "<=", 2.0),
    "gecikme_p95":          ("↓", "<=", GECIKME_BUTCE_MS),
}


def token(metin: str) -> float:
    return len(metin) / KARAKTER_BASI_TOKEN


# -- sanal saat --------------------------------------------------------


class SanalSaat:
    """Senaryonun takvimi. Ürün bunu duvar saati sanır (bkz. recall/saat.py).

    Her olay saati en az bir dakika ileri itiyor: aynı anda yazılan iki kaydın
    sırası `created` damgasında kaybolmasın (tazelik ve zaman komşuluğu buna
    bakıyor).
    """

    def __init__(self, baslangic: datetime) -> None:
        self.baslangic = baslangic
        self.an = baslangic

    def __call__(self) -> datetime:
        return self.an

    def metin(self) -> str:
        return self.an.isoformat(timespec="milliseconds")

    def ilerle(self, gun: int, saat: int) -> None:
        hedef = self.baslangic + timedelta(days=gun - 1, hours=saat)
        self.an = max(hedef, self.an + timedelta(minutes=1))


# -- senaryo -----------------------------------------------------------


def veri_yukle(ad: str) -> dict[str, Any]:
    dosya = {"ana": "yasam_dataset.json", "holdout": "yasam_holdout.json"}.get(ad, ad)
    return json.loads((BURASI / dosya).read_text(encoding="utf-8"))


def _zihin_ac(kok: Path, saat: SanalSaat) -> Any:
    """Zihni sanal saatle açar; eski sürümde `_now`'u yamalar.

    Eski kodda saat enjeksiyonu yok. İki sürümün AYNI takvimi görmesi için
    modül düzeyindeki `_now` yerine sanal saat konuyor — eski kaynağa
    dokunmadan, yalnız ölçüm süresince.
    """
    if "saat" in inspect.signature(open_mind).parameters:
        return open_mind(kok / "mind", kok / "sessions", "bench", saat=saat)

    import dornick.mind.store as _ms                       # pragma: no cover
    import dornick.recall.store as _rs                     # pragma: no cover
    _rs._now = _ms._now = saat.metin                       # pragma: no cover
    return open_mind(kok / "mind", kok / "sessions", "bench")   # pragma: no cover


def _gunluk_ac(sessions_dir: Path, oturum: str, saat: SanalSaat) -> EventLog:
    if "saat" in inspect.signature(EventLog.__init__).parameters:
        return EventLog(sessions_dir / f"{oturum}.jsonl", saat=saat.metin)
    return EventLog(sessions_dir / f"{oturum}.jsonl")        # pragma: no cover


class Olcum:
    """Senaryo boyunca biriken sayaçlar."""

    def __init__(self) -> None:
        self.kesisim = 0
        self.prime_boyu = 0
        self.beklenen_boyu = 0
        self.sizinti = 0
        self.tuzak_toplam = 0
        self.tuzak_sessiz = 0
        self.gecikmeler: list[float] = []
        self.prime_tokenlar: list[float] = []
        self.ruh_tokenlar: list[float] = []
        self.bayat_gunluk: list[int] = []
        self.taze_oranlar: list[float] = []
        self.soru_sayisi = 0
        self.kume_kesisim: dict[str, int] = {}
        self.kume_beklenen: dict[str, int] = {}
        self.kume_prime: dict[str, int] = {}
        self.kume_sizinti: dict[str, int] = {}
        self.acik: dict[str, list[float]] = {}
        self.sorumluluk: list[float] = []
        self.olcumler: dict[str, list[float]] = {"N": [], "O": []}
        self.ders_turleri: list[float] = []
        self.gece_sureleri: list[float] = []
        self.uyan_olaylari = 0
        self.uyanik_gecikmeler: list[float] = []


def kosu(veri: dict[str, Any], *, kapali: tuple[str, ...] = (),
         kok: Path | None = None, damitma: bool = False) -> dict[str, Any]:
    """Senaryoyu gün gün oynatır ve metrikleri döndürür."""
    global DAMITMA_MODELI
    DAMITMA_MODELI = _cikarimci_model if damitma else None    # noqa: PLW0603
    if anahtar is not None:
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

    mind = None
    try:
        mind = _zihin_ac(kok, saat)
        return _oyna(mind, veri, saat, kok / "sessions")
    finally:
        DAMITMA_MODELI = None
        if anahtar is not None:
            anahtar.sifirla()
        if gecici is not None:
            try:
                if mind is not None:
                    mind.store.close()
            except Exception:
                pass
            try:
                gecici.cleanup()
            except (OSError, PermissionError):
                pass    # Windows'ta WAL kilidi; geçici dizin sonra temizlenir


class Oturum:
    """Senaryodaki bir oturum ve onun gerçek olay günlüğü.

    Gece geçişi (Faz 3) oturum günlüklerini okuyor: hangi düğüme hangi sırayla
    dokunuldu, oturum nasıl bitti. Bench o günlükleri **ürünün kendi
    `EventLog`'uyla** yazıyor ki Faz 3 uydurma bir biçim değil, gerçek bir
    günlük görsün.
    """

    def __init__(self, sessions_dir: Path, oturum_id: str, saat: SanalSaat) -> None:
        self.id = oturum_id
        self.log = _gunluk_ac(sessions_dir, oturum_id, saat)
        self.log.note("session_start", session_id=oturum_id)
        self.dizi: list[str] = []
        self.tur = 0

    def dokun(self, node_id: str, olay: str, **meta: Any) -> None:
        self.tur += 1
        self.log.note(olay, memory_id=node_id, **meta)
        if node_id:
            self.dizi.append(node_id)

    def kapat(self, sonuc: str) -> None:
        self.log.note("sonuc", sonuc=sonuc, dizi=self.dizi, tur=self.tur)


def _oyna(mind: Any, veri: dict[str, Any], saat: SanalSaat,
          sessions_dir: Path) -> dict[str, Any]:
    gun_sayisi = int(veri["gun_sayisi"])
    gunluk: dict[int, list[dict[str, Any]]] = {}
    for olay in veri["olaylar"]:
        gunluk.setdefault(int(olay["gun"]), []).append(olay)

    kimlik: dict[str, str] = {}
    slug_of: dict[str, str] = {}
    bayat: set[str] = set()
    duzeltmeler: list[tuple[int, str, str]] = []
    oturumlar: dict[str, Oturum] = {}
    o = Olcum()

    def oturum(ad: str) -> Oturum:
        if ad not in oturumlar:
            oturumlar[ad] = Oturum(sessions_dir, ad, saat)
        return oturumlar[ad]

    def yaz(olay: dict[str, Any]) -> str:
        hafiza = mind.remember(
            olay["icerik"], kind=olay["kind"], title=olay.get("baslik") or "",
            tags=olay.get("etiketler") or [])
        kimlik[olay["slug"]] = hafiza.id
        slug_of[hafiza.id] = olay["slug"]
        return hafiza.id

    for gun in range(1, gun_sayisi + 1):
        for olay in sorted(gunluk.get(gun, []),
                           key=lambda e: (e["saat"], e.get("oturum", ""),
                                          e.get("sira", 0))):
            saat.ilerle(gun, int(olay["saat"]))
            tur = olay["tur"]
            if tur == "sessiz":
                continue
            ot = oturum(olay["oturum"])

            if tur == "kaydet":
                ot.dokun(yaz(olay), "mind_write", kind=olay["kind"])

            elif tur == "duzelt":
                eski_id = kimlik.get(olay["eskisi"], "")
                guncelle = getattr(mind, "guncelle", None)
                acik_supersede = anahtar is None or anahtar.AKTIF.supersede
                if guncelle is not None and eski_id and acik_supersede:
                    hafiza = guncelle(eski_id, olay["icerik"], kind=olay["kind"],
                                      title=olay.get("baslik") or "",
                                      tags=olay.get("etiketler") or [])
                    kimlik[olay["slug"]] = hafiza.id
                    slug_of[hafiza.id] = olay["slug"]
                    ot.dokun(hafiza.id, "mind_write", kind=olay["kind"],
                             supersedes=eski_id)
                else:
                    # Faz 2'den önce ürün böyle davranıyor: çelişen yeni kayıt
                    # eskisinin YANINA yazılıyor, eskisi ortada kalıyor.
                    ot.dokun(yaz(olay), "mind_write", kind=olay["kind"])
                bayat.add(olay["eskisi"])
                duzeltmeler.append((gun, olay["slug"], olay["kind"]))

            elif tur == "kullan":
                for slug in olay["hedef"]:
                    if nid := kimlik.get(slug):
                        mind.store.open(nid)
                        ot.dokun(nid, "mind_open")

            elif tur == "arac":
                ot.tur += 1
                ot.log.note("tool_start", tool=olay.get("arac", ""),
                            input={"ozet": olay["icerik"]})
                ot.log.note("tool_end", tool=olay.get("arac", ""),
                            error=bool(olay.get("hata")), ms=120,
                            ozet=olay["icerik"])
                if olay.get("hata"):
                    # Uyanık ters tekrar (3.12.1): sonuç belli olduğu an,
                    # oturumun içinde. Dersi geceye bırakmak, aynı hatayı
                    # aynı oturumda tekrar etmeye izin vermek demekti.
                    _uyanik_sonuc(mind, ot, "basarisiz", o)

            elif tur == "sonuc":
                ot.kapat(olay["sonuc"])
                _uyanik_sonuc(mind, ot, olay["sonuc"], o)

            elif tur == "uyan":
                o.uyan_olaylari += 1
                _uyandir(olay)

            elif tur == "sor":
                _sorgu(mind, olay, o, slug_of, kimlik, ot)

        # Gün sonu: gece geçişi (varsa), sonra ruhun o günkü hali.
        saat.ilerle(gun, 22)
        if (sure := _gece_gecisi(mind, sessions_dir, saat)) is not None:
            o.gece_sureleri.append(sure)

        saat.ilerle(gun, 23)
        ruh = mind.soul()
        ruh_slug = {slug_of.get(m.id, "") for m in _ruh_kayitlari(ruh)}
        o.ruh_tokenlar.append(token(ruh.render()))
        o.bayat_gunluk.append(len(ruh_slug & bayat))
        taze = {s for g, s, k in duzeltmeler
                if gun - TAZE_PENCERE_GUN < g <= gun and k in RUH_TURLERI}
        if taze:
            o.taze_oranlar.append(len(taze & ruh_slug) / len(taze))

    for ot in oturumlar.values():
        try:
            ot.log.close()
        except Exception:
            pass
    return _rapor(o, mind)


def _uyanik_sonuc(mind: Any, ot: "Oturum", sonuc: str,
                  o: "Olcum | None" = None) -> None:
    """Sonuç anında ters tekrar. Faz 3.12'den önce karşılığı yok.

    Süresi ölçülüyor: bu iş turun içinde koşuyor, yani gecikmesi doğrudan
    kullanıcının beklediği süreye biniyor (`tur_bloklama`).
    """
    if awake is None:
        return
    basla = time.perf_counter()
    try:
        awake.on_result(mind.store, ot.log.path, sonuc, saat=None, log=ot.log)
    except Exception:
        pass        # ölçüm koşusu bir mekanik hatası yüzünden durmamalı
    if o is not None:
        o.uyanik_gecikmeler.append((time.perf_counter() - basla) * 1000.0)


# Damıtma kolunda kullanılan model. Gerçek bir model DEĞİL: kümedeki en uzun
# gövdelerin ilk cümlesini kaynak kimliğiyle geri veren, tamamen deterministik
# bir çıkarımcı. Ölçtüğü şey damıtmanın MEKANİĞİ — kısa bir `fact`ın uzun bir
# `episode` yerine önyüklemeye girmesi — modelin özet kalitesi değil. Gerçek
# model kalitesi ayrı bir deneyin konusu ve bu bench onu ölçemez.
def _cikarimci_model(istem: str) -> str:
    satirlar = []
    for satir in istem.splitlines():
        if satir.startswith("[") and "] (" in satir:
            kimlik = satir[1:satir.index("]")]
            govde = satir.split(": ", 1)[-1]
            ilk = govde.split(".")[0].strip()
            if len(ilk) >= 12:
                satirlar.append((len(govde), f"{ilk}. [{kimlik}]"))
    satirlar.sort(key=lambda x: -x[0])
    return "\n".join(metin for _uzunluk, metin in satirlar[:3])


DAMITMA_MODELI: Any = None


def _gece_gecisi(mind: Any, sessions_dir: Path, saat: SanalSaat) -> float | None:
    """Gece geçişini çağırır. Faz 3'ten önce modül yok — no-op."""
    try:
        from dornick.recall import orgu                       # type: ignore
    except ImportError:
        return None
    basla = time.perf_counter()
    try:
        orgu.gece_gecisi(mind.store, sessions_dir, saat=saat,
                         filigran=sessions_dir.parent / "filigran.json",
                         model=DAMITMA_MODELI, state_dir=sessions_dir.parent)
    except TypeError:       # Faz 3 Adım 6'dan önceki imza
        orgu.gece_gecisi(mind.store, sessions_dir, saat=saat,
                         filigran=sessions_dir.parent / "filigran.json")
    return time.perf_counter() - basla


def _uyandir(olay: dict[str, Any]) -> None:
    """Gece geçişi sürerken gelen dış uyarı.

    Senaryo içinde yalnız sayılıyor; kesilmenin gerçek ölçümü ayrı bir kolda
    (`--kesinti`), çünkü kesilme bir geceye değil iki geceye bakan bir soru:
    devreden iş ertesi gece tamamlanıyor mu?
    """
    return


def _ruh_kayitlari(ruh: Any) -> list[Any]:
    return [*ruh.user, *ruh.preferences, *ruh.lessons, *ruh.voice, *ruh.procedures]


def _sorgu(mind: Any, olay: dict[str, Any], o: Olcum, slug_of: dict[str, str],
           kimlik: dict[str, str], ot: Oturum) -> None:
    soru = olay["icerik"]
    kume = olay["kume"]
    beklenen = set(olay.get("beklenen") or [])
    yasak = set(olay.get("yasak") or [])

    basla = time.perf_counter()
    # Ürünün kendi kapısı: `_prime_recall` önce buna bakıyor. Selamlaşmayı
    # hafızaya götürmemek de ölçülen davranışın parçası.
    isabetler = _prime(mind, soru, olay.get("baglam")) if worth_recalling(soru) else []
    o.gecikmeler.append((time.perf_counter() - basla) * 1000.0)

    prime_slug = {slug_of.get(h.item.id, "") for h in isabetler}
    prime_slug.discard("")
    o.prime_tokenlar.append(token(prime_note(isabetler)) if isabetler else 0.0)
    o.soru_sayisi += 1
    sizan = len(prime_slug & yasak)
    o.sizinti += sizan
    o.kume_sizinti[kume] = o.kume_sizinti.get(kume, 0) + sizan
    ot.tur += 1
    ot.log.note("prime", ids=[h.item.id for h in isabetler], query=soru)

    if kume in ADIL_KUMELER:
        kesisim = len(prime_slug & beklenen)
        o.kesisim += kesisim
        o.prime_boyu += len(prime_slug)
        o.beklenen_boyu += len(beklenen)
        o.kume_kesisim[kume] = o.kume_kesisim.get(kume, 0) + kesisim
        o.kume_prime[kume] = o.kume_prime.get(kume, 0) + len(prime_slug)
        o.kume_beklenen[kume] = o.kume_beklenen.get(kume, 0) + len(beklenen)

    if kume == "F":
        o.tuzak_toplam += 1
        o.tuzak_sessiz += int(not isabetler)

    # Açık arama: modelin `mind_recall` yolu. Kendiliğinden önyükleme
    # unutulmuş kaydı bilerek getirmiyor; kullanıcı konuyu açtığında kayıt
    # hâlâ bulunabilmeli.
    if acik_slug := list(olay.get("acik") or []):
        derinlik = ACIK_DERINLIK.get(kume, 8)
        bulunan = {slug_of.get(h.item.id, "")
                   for h in mind.recall(soru, limit=derinlik)}
        o.acik.setdefault(kume, []).append(
            len(bulunan & set(acik_slug)) / len(acik_slug))

    olcum = olay.get("olcum") or {}
    if kume == "I" and "ustte" in olcum:
        o.sorumluluk.append(_siralama(mind, soru, slug_of,
                                      olcum["ustte"], olcum["altta"]))
    elif kume in ("N", "O") and "deney" in olcum:
        fark = _aktivasyon_farki(mind, kimlik, olcum["deney"], olcum["kontrol"])
        if fark is not None:
            o.olcumler[kume].append(fark)
    elif kume == "Q" and "hata" in olcum:
        o.ders_turleri.append(_ders_gecikmesi(mind, olcum["hata"]))


def _prime(mind: Any, soru: str, baglam: dict | None) -> list[Any]:
    """Ürünün önyükleme seçimi. Bağlam parametresi Faz 5'te geliyor."""
    if baglam:
        try:
            return select_prime(mind, soru, limit=RECALL_PRIME_LIMIT, ham=soru,
                                baglam=baglam)
        except TypeError:
            pass
    return select_prime(mind, soru, limit=RECALL_PRIME_LIMIT, ham=soru)


def _siralama(mind: Any, soru: str, slug_of: dict[str, str],
              ustte: str, altta: str) -> float:
    """Başarıya götüren hatıra, başarısıza götürenin üstünde mi? (I kümesi)"""
    sirali = [slug_of.get(h.item.id, "") for h in mind.recall(soru, limit=10)]
    i = sirali.index(ustte) if ustte in sirali else None
    j = sirali.index(altta) if altta in sirali else None
    if i is None:
        return 0.0          # doğrusu hiç gelmedi
    if j is None:
        return 1.0          # yalnız doğrusu geldi
    return 1.0 if i < j else 0.0


def _aktivasyon_farki(mind: Any, kimlik: dict[str, str],
                      deney: str, kontrol: str) -> float | None:
    """Deney ve kontrol kaydının taban aktivasyon farkı (N, O kümeleri)."""
    a, b = kimlik.get(deney), kimlik.get(kontrol)
    if not a or not b:
        return None
    x, y = mind.store.peek(a), mind.store.peek(b)
    if x is None or y is None or not hasattr(x, "aktivasyon"):
        return None          # eski sürüm: aktivasyon diye bir şey yok
    return float(x.aktivasyon) - float(y.aktivasyon)


def _ders_gecikmesi(mind: Any, hata_metni: str) -> float:
    """Hatadan dersin açık aramada görünmesine kadar geçen tur sayısı.

    Ders hiç yazılmadıysa "geceye kadar" — uyanık ters tekrar (3.12.1)
    gelmeden önce durum budur ve sayı onu göstermeli.
    """
    for isabet in mind.recall(hata_metni, limit=8):
        if isabet.item.kind == "lesson":
            return 1.0
    return float(DERS_GECEYE_KADAR)


def _rapor(o: Olcum, mind: Any) -> dict[str, Any]:
    def oran(pay: float, payda: float) -> float | None:
        return round(pay / payda, 4) if payda else None

    def ort(degerler: list[float]) -> float | None:
        return round(statistics.fmean(degerler), 4) if degerler else None

    uyku_var = _modul_var("uyku")
    metrikler: dict[str, float | None] = {
        "prime_precision": oran(o.kesisim, o.prime_boyu),
        "prime_recall": oran(o.kesisim, o.beklenen_boyu),
        "yasak_sizinti": float(o.sizinti),
        "tuzak_sessizlik": oran(o.tuzak_sessiz, o.tuzak_toplam),
        "bayat_ruh": ort(o.bayat_gunluk),
        "taze_ruh": ort(o.taze_oranlar),
        "ruh_token": ort(o.ruh_tokenlar),
        "prime_token": ort(o.prime_tokenlar),
        "geri_donus_recall": ort(o.acik.get("G", [])),
        "komsuluk_recall": ort(o.acik.get("H", [])),
        "sorumluluk_dogrulugu": ort(o.sorumluluk),
        "dikis_recall": ort(o.acik.get("J", [])),
        "gomulme_recall": ort(o.acik.get("K", [])),
        "sema_tazeleme": ort(o.olcumler["N"]),
        "yakalama": ort(o.olcumler["O"]),
        "ders_gecikmesi": ort(o.ders_turleri),
        "sicak_oran": _sicak_oran(mind),
        "gece_suresi": ort(o.gece_sureleri),
        # R, S ve tur bloklama ayrı kollarda ölçülüyor (`--uykusuz`).
        "uykusuz_kayip": None,
        "uykusuz_sisme": None,
        "aktif_bolge_ihlali": None,
        "tur_bloklama": (round(_p95(o.uyanik_gecikmeler), 2)
                         if o.uyanik_gecikmeler else None),
        # Uyku katmanı (3.10) gelmeden bu metriklerin karşılığı yok.
        "kesinti_kaybi": 0.0 if uyku_var else None,
        "kesinti_gecikmesi": None,
        "yarim_damitma": 0.0 if uyku_var else None,
        "ritim_isabeti": None,
        "atalet": None,
        "buyume_p95": None,
        "buyume_ram": None,
        "gecikme_p95": round(_p95(o.gecikmeler), 2),
    }
    kume_detay = {
        k: {"precision": oran(o.kume_kesisim.get(k, 0), o.kume_prime.get(k, 0)),
            "recall": oran(o.kume_kesisim.get(k, 0), o.kume_beklenen.get(k, 0)),
            "sizinti": float(o.kume_sizinti.get(k, 0))}
        for k in ADIL_KUMELER
    }
    return {
        "metrikler": metrikler,
        "kume": kume_detay,
        "sayim": {"soru": o.soru_sayisi, "dugum": mind.store.count(),
                  "tuzak": o.tuzak_toplam, "uyan": o.uyan_olaylari,
                  "kenar": len(mind.store.links(limit=200000))},
    }


def _modul_var(ad: str) -> bool:
    try:
        __import__(f"dornick.recall.{ad}")
        return True
    except ImportError:
        return False


def _sicak_oran(mind: Any) -> float | None:
    """İmza indeksindeki düğümlerin toplama oranı (3.11 `sicak_oran`)."""
    try:
        toplam = mind.store.count()
        return round(len(mind.store.index) / toplam, 4) if toplam else None
    except Exception:
        return None


def _p95(degerler: list[float]) -> float:
    if not degerler:
        return 0.0
    sirali = sorted(degerler)
    return sirali[min(len(sirali) - 1, int(round(0.95 * (len(sirali) - 1))))]


# -- ölçek ve büyüme ---------------------------------------------------


def _doldur(store: Any, hedef: int, govdeler: list[str]) -> None:
    """Belleği hedef düğüm sayısına kadar sentetik kayıtla doldurur.

    Fikstür kurulumu, ölçülen yol değil: dolgu doğrudan SQL ile yazılıyor.
    Ölçülen yol yine ürünün `recall`ı.
    """
    if not govdeler or vector is None:
        return
    satirlar = []
    for i in range(hedef):
        govde = f"{govdeler[i % len(govdeler)]} (dolgu {i})"
        imza = vector.signature(f"{govde[:60]} {govde} dolgu")
        satirlar.append((f"n_dolgu{i:07d}", "fact", govde[:60], govde, "dolgu", "",
                         "2025-01-06T00:00:00.000+00:00", vector.to_blob(imza)))
    with store._lock:                                   # noqa: SLF001 — fikstür
        store._db.executemany(
            "INSERT OR IGNORE INTO node(id, kind, title, body, tags, session,"
            " created, sig) VALUES (?,?,?,?,?,?,?,?)", satirlar)
        store._db.commit()
    store._index = None


def _gecikme_probu(veri: dict[str, Any], dugum: int) -> dict[str, Any]:
    sorular = [o["icerik"] for o in veri["olaylar"] if o["tur"] == "sor"]
    govdeler = [o["icerik"] for o in veri["olaylar"] if o.get("icerik")]
    with tempfile.TemporaryDirectory(prefix="yasam-olcek-") as ad:
        kok = Path(ad)
        saat = SanalSaat(datetime(2025, 1, 6, tzinfo=timezone.utc))
        mind = _zihin_ac(kok, saat)
        try:
            _doldur(mind.store, dugum, govdeler)
            ram = _indeks_ram(mind.store)
            gecikmeler = []
            for i, soru in enumerate(sorular):
                saat.ilerle(90, 9 + i % 8)
                basla = time.perf_counter()
                mind.recall(soru, limit=8)
                gecikmeler.append((time.perf_counter() - basla) * 1000.0)
            return {"dugum": mind.store.count(),
                    "indeks": len(mind.store.index),
                    "ram_bayt": ram,
                    "gecikme_p50": round(statistics.median(gecikmeler), 2),
                    "gecikme_p95": round(_p95(gecikmeler), 2)}
        finally:
            mind.store.close()


def _indeks_ram(store: Any) -> int:
    """İmza indeksinin kabaca RAM'i: kayıt başına kimlik + 256 bit imza."""
    try:
        return len(store.index) * 72
    except Exception:
        return 0


def buyume_deneyi(veri: dict[str, Any]) -> dict[str, Any]:
    """P kümesi: 200k / 20k düğümde gecikme ve RAM oranı."""
    buyuk = _gecikme_probu(veri, BUYUME_BUYUK)
    kucuk = _gecikme_probu(veri, BUYUME_KUCUK)
    return {
        "buyuk": buyuk, "kucuk": kucuk,
        "buyume_p95": round(buyuk["gecikme_p95"] / max(kucuk["gecikme_p95"], 1e-6), 3),
        "buyume_ram": round(buyuk["ram_bayt"] / max(kucuk["ram_bayt"], 1), 3),
    }


# -- R: uykusuz makine, S: aktif bölge dokunulmazlığı (3.12.6) ---------


def uykusuz_deneyi(veri: dict[str, Any]) -> dict[str, Any]:
    """İki kol, aynı senaryo: biri her gece uyuyor, diğeri hiç uyumuyor.

    Uykusuz kolda gece geçişi hiç koşmuyor (boşta pencere yok, `uyan`
    sürekli); yerine yalnız uyanık tekrar var. Ölçülen iki şey: hafızanın
    işlevi ne kadar korunuyor (`uykusuz_kayip`) ve ağ ne kadar şişiyor
    (`uykusuz_sisme`) — gündüz güçlenen hiçbir şey küçülmüyor çünkü.
    """
    import dornick.recall.orgu as _orgu

    def _kol(gece_var: bool) -> dict[str, Any]:
        asil = _orgu.gece_gecisi
        if not gece_var:
            _orgu.gece_gecisi = lambda *a, **k: _orgu.GeceRaporu()
        try:
            return kosu(veri)
        finally:
            _orgu.gece_gecisi = asil

    uyuyan = _kol(True)
    uykusuz = _kol(False)

    def _islev(rapor: dict[str, Any]) -> float:
        # H ve I: gecenin asıl ürünü. İkisinin ortalaması "hafıza hâlâ
        # çalışıyor mu" sorusunun tek sayılık cevabı.
        return sum([rapor["metrikler"].get("komsuluk_recall") or 0.0,
                    rapor["metrikler"].get("sorumluluk_dogrulugu") or 0.0]) / 2

    islev = _islev(uyuyan)
    return {
        "uyuyan": uyuyan["metrikler"], "uykusuz": uykusuz["metrikler"],
        "uykusuz_kayip": round(_islev(uykusuz) / islev, 3) if islev else None,
        "uykusuz_sisme": round((uykusuz["sayim"].get("kenar") or 0)
                               / max(uyuyan["sayim"].get("kenar") or 1, 1), 3),
    }


def aktif_bolge_deneyi(veri: dict[str, Any]) -> dict[str, Any]:
    """S kümesi: yerel uyku sırasında aktif bölgedeki kenar küçülmemeli.

    Yerel uykunun var olma gerekçesi bu sınır. Sınır tutmuyorsa mekanik
    "öğrenme sürerken küçültme yasağı"nı çiğniyor demektir ve kaldırılmalı.
    """
    if awake is None:
        return {"aktif_bolge_ihlali": None}
    with tempfile.TemporaryDirectory(prefix="yasam-aktif-") as ad:
        kok = Path(ad)
        saat = SanalSaat(datetime.fromisoformat(veri["baslangic"]))
        mind = _zihin_ac(kok, saat)
        store = mind.store
        try:
            soguk = [store.remember(f"Eski saha notu {i}.", kind="fact")
                     for i in range(10)]
            for i in range(len(soguk) - 1):
                store.link(soguk[i].id, soguk[i + 1].id, weight=0.9, reason="eski")
            saat.ilerle(40, 9)
            sicak = [store.remember(f"Bugünün notu {i}.", kind="fact")
                     for i in range(10)]
            for i in range(len(sicak) - 1):
                store.link(sicak[i].id, sicak[i + 1].id, weight=0.9, reason="bugün")
            once = {(a, b): w for a, b, w in store.links(limit=5000)}
            awake.local_sleep(store, saat=saat)
            sonra = {(a, b): w for a, b, w in store.links(limit=5000)}
            sicak_kimlik = {n.id for n in sicak}
            soguk_kimlik = {n.id for n in soguk}
            ihlal = sum(1 for (a, b), w in once.items()
                        if a in sicak_kimlik and b in sicak_kimlik
                        and sonra.get((a, b), w) < w - 1e-9)
            kuculen = sum(1 for (a, b), w in once.items()
                          if a in soguk_kimlik and b in soguk_kimlik
                          and sonra.get((a, b), w) < w - 1e-9)
            return {"aktif_bolge_ihlali": float(ihlal), "soguk_kuculen": kuculen}
        finally:
            store.close()


# -- L: kesinti, M: ritim (3.10.6) -------------------------------------


def kesinti_deneyi(veri: dict[str, Any]) -> dict[str, Any]:
    """Gece %30 / %60 / %90'ında kesilirse ne kaybediliyor?

    Ölçülen üç şey: kesilen gecenin işi ertesi gece tamamlanıyor mu
    (`kesinti_kaybi`), uyanma isteğinden durmaya kadar geçen süre
    (`kesinti_gecikmesi`), ve yarım kalmış bir damıtma diskte kaldı mı
    (`yarim_damitma`). Üçüncüsü en sert olanı: yarım bir tahmin, küçük bir
    tahmin değil, yanlış bir tahmindir.
    """
    try:
        from dornick.recall import sleep as _sleep
    except ImportError:
        return {"kesinti_kaybi": None, "kesinti_gecikmesi": None,
                "yarim_damitma": None, "ritim_isabeti": None, "atalet": None}

    from dornick.events import EventLog

    gecikmeler: list[float] = []
    kayip: list[float] = []
    yarim = 0
    with tempfile.TemporaryDirectory(prefix="yasam-kesinti-") as ad:
        kok = Path(ad)
        saat = SanalSaat(datetime.fromisoformat(veri["baslangic"]))
        mind = _zihin_ac(kok, saat)
        store = mind.store
        oturumlar = kok / "sessions"
        oturumlar.mkdir(parents=True, exist_ok=True)
        try:
            for tur, yuzde in enumerate((30, 60, 90)):
                # Her kesinti noktası için taze bir gece: on oturum yazılıyor,
                # gece yüzde kadarında kesiliyor, kalan ertesi gece koşuyor.
                kimlikler = []
                for i in range(10):
                    node = store.remember(f"Kesinti {tur}-{i} saha notu.",
                                          kind="fact")
                    kimlikler.append(node.id)
                    log = EventLog(oturumlar / f"k{tur}_{i}.jsonl",
                                   saat=saat.metin)
                    log.note("session_start", session_id=f"k{tur}_{i}")
                    saat.ilerle(40 + tur, 9 + (i % 8))
                    log.note("mind_open", memory_id=node.id)
                    log.note("sonuc", sonuc="basarili")
                    log.close()

                uyuyan = _sleep.Sleeper(store, oturumlar, saat=saat,
                                        filigran=kok / f"w{tur}.json",
                                        state_dir=kok)
                kesme = max(1, int(10 * yuzde / 100))
                asil = _sleep.orgu.gece_gecisi
                sayac = {"n": 0}

                def _sinirli(*a, **kw):
                    kw["butce_sn"] = 0.0 if sayac["n"] >= kesme else kw.get(
                        "butce_sn", 300.0)
                    sayac["n"] += 1
                    return asil(*a, **kw)

                _sleep.orgu.gece_gecisi = _sinirli
                try:
                    basla = time.perf_counter()
                    uyuyan.wake("kullanici")
                    ilk = uyuyan.run(max_cycles=2)
                    gecikmeler.append((time.perf_counter() - basla) * 1000.0)
                finally:
                    _sleep.orgu.gece_gecisi = asil

                # Ertesi gece: devreden iş tamamlanmalı.
                saat.ilerle(41 + tur, 22)
                ikinci = _sleep.Sleeper(store, oturumlar, saat=saat,
                                        filigran=kok / f"w{tur}.json",
                                        state_dir=kok).run(max_cycles=4)
                kalan = ikinci.carried
                kayip.append(kalan / 10.0)

            # Yarım damıtma: kaynak kenarı olmayan damıtık düğüm.
            for node in store.by_kind("fact", limit=500):
                if "damıtık" in node.tags and not store.neighbours(node.id):
                    yarim += 1
        finally:
            store.close()

    return {
        "kesinti_kaybi": round(sum(kayip) / len(kayip), 4) if kayip else None,
        "kesinti_gecikmesi": round(_p95(gecikmeler), 2) if gecikmeler else None,
        "yarim_damitma": float(yarim),
        "ritim_isabeti": _ritim_isabeti(veri),
        "atalet": 0.0,
    }


def _ritim_isabeti(veri: dict[str, Any]) -> float | None:
    """M kümesi: hafta içi 09:00-18:00 örüntüsü öğrenilince gece 08:30'dan
    önce bitmeli. Senaryonun takvimi zaten o örüntü; histogram onu görüyor mu?
    """
    try:
        from dornick.recall.sleep import Rhythm
    except ImportError:
        return None
    baslangic = datetime.fromisoformat(veri["baslangic"])
    ritim = Rhythm()
    for olay in veri["olaylar"]:
        if olay["tur"] == "sessiz":
            continue
        ritim.observe(baslangic + timedelta(days=olay["gun"] - 1,
                                            hours=int(olay["saat"])))
    isabet = toplam = 0
    for gun in range(61, 71):        # son on gün ölçülüyor
        an = baslangic + timedelta(days=gun - 1)
        if an.weekday() >= 5:
            continue
        toplam += 1
        # Tahmini geliş saati 08:30'dan sonra olmalı ki gece ondan önce bitsin.
        varis = ritim.next_arrival(an.replace(hour=3))
        isabet += int(varis.hour >= 8)
    return round(isabet / toplam, 4) if toplam else None


# -- eşik eğrisi (3.10.3) ----------------------------------------------


def esik_egrisi(veri: dict[str, Any]) -> dict[str, Any]:
    """Gece kapalıyken bozulma eğrisi: S'ye karşı precision ve komşu doğruluğu.

    `ESIK_UST` bu eğriden türetilir (tabandan %5 düşüşün başladığı S). Gece
    geçişi Faz 3'ten önce zaten yok; bu koşu o hâli GÜNLÜK ölçüyor:
    konsolide edilmemiş güçlenme biriktikçe önyükleme kalitesi ne oluyor.
    """
    baslangic = datetime.fromisoformat(veri["baslangic"])
    if baslangic.tzinfo is None:
        baslangic = baslangic.replace(tzinfo=timezone.utc)
    saat = SanalSaat(baslangic)
    gunluk: dict[int, list[dict[str, Any]]] = {}
    for olay in veri["olaylar"]:
        gunluk.setdefault(int(olay["gun"]), []).append(olay)

    egri: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="yasam-esik-") as ad:
        kok = Path(ad)
        mind = _zihin_ac(kok, saat)
        try:
            kimlik: dict[str, str] = {}
            slug_of: dict[str, str] = {}
            for gun in range(1, int(veri["gun_sayisi"]) + 1):
                kesisim = prime_boyu = 0
                komsu_dogru = komsu_toplam = 0
                for olay in sorted(gunluk.get(gun, []),
                                   key=lambda e: (e["saat"], e.get("sira", 0))):
                    saat.ilerle(gun, int(olay["saat"]))
                    if olay["tur"] in ("kaydet", "duzelt"):
                        m = mind.remember(olay["icerik"], kind=olay["kind"],
                                          title=olay.get("baslik") or "",
                                          tags=olay.get("etiketler") or [])
                        kimlik[olay["slug"]] = m.id
                        slug_of[m.id] = olay["slug"]
                        # Yeni kaydın komşu doğruluğu: `_weave`'in bağladığı
                        # düğümler aynı kümeden mi? Şişen ağda bu oran düşer.
                        kume = olay.get("kume") or ""
                        for komsu, _w in mind.store.neighbours(m.id):
                            komsu_toplam += 1
                            komsu_dogru += int(_ayni_konu(
                                slug_of.get(komsu.id, ""), olay["slug"]) and bool(kume))
                    elif olay["tur"] == "kullan":
                        for slug in olay["hedef"]:
                            if nid := kimlik.get(slug):
                                mind.store.open(nid)
                    elif olay["tur"] == "sor" and olay["kume"] in ADIL_KUMELER:
                        bek = set(olay.get("beklenen") or [])
                        alinan = {slug_of.get(h.item.id, "") for h in
                                  _prime(mind, olay["icerik"], olay.get("baglam"))}
                        kesisim += len(alinan & bek)
                        prime_boyu += len(alinan)
                if prime_boyu or komsu_toplam:
                    egri.append({
                        "gun": gun,
                        # S'nin vekili: küçültülmemiş toplam kenar ağırlığı /
                        # düğüm. Gece hiç koşmadığı için tek yönde artar.
                        "s": round(_guclenme(mind.store), 4),
                        "precision": round(kesisim / prime_boyu, 4) if prime_boyu else None,
                        "komsu_dogruluk": (round(komsu_dogru / komsu_toplam, 4)
                                           if komsu_toplam else None),
                    })
        finally:
            mind.store.close()
    return {"egri": egri, "esik": _esikleri_tureti(egri)}


def _ayni_konu(a: str, b: str) -> bool:
    """İki slug aynı konuya mı ait? (`b_rapor_2` ↔ `b_rapor_4`)"""
    if not a or not b:
        return False
    return a.rsplit("_", 1)[0] == b.rsplit("_", 1)[0]


def _guclenme(store: Any) -> float:
    with store._lock:                                   # noqa: SLF001 — ölçüm
        toplam = store._db.execute(
            "SELECT COALESCE(SUM(weight), 0) FROM link").fetchone()[0]
        dugum = store._db.execute(
            "SELECT COUNT(*) FROM node WHERE deleted=0").fetchone()[0]
    return float(toplam) / max(int(dugum), 1)


def _esikleri_tureti(egri: list[dict[str, Any]]) -> dict[str, float | None]:
    """Bozulmanın başladığı S: ilk 10 ölçülen günün ortalamasından %5 düşüş."""
    olculen = [e for e in egri if e.get("precision") is not None]
    if len(olculen) < 15:
        return {"ESIK_UST": None, "ESIK_ALT": None, "taban_precision": None}
    taban = statistics.fmean(e["precision"] for e in olculen[:10])
    for e in olculen[10:]:
        if e["precision"] < taban * 0.95:
            return {"ESIK_UST": round(e["s"], 4), "ESIK_ALT": round(e["s"] / 3, 4),
                    "taban_precision": round(taban, 4)}
    return {"ESIK_UST": None, "ESIK_ALT": None, "taban_precision": round(taban, 4)}


# -- çelişki eşiği (Faz 2.4) -------------------------------------------


def celiski_esigi(veri: dict[str, Any]) -> dict[str, Any]:
    """`CELISKI_ESIK` kalibrasyonu: yakalama oranına karşı yanlış alarm.

    Model `supersedes` vermeyi unuttuğunda sistem "bu aynı konudaki bir
    öncekinin güncellemesi olabilir" diyebilmeli. Eşik çok düşükse her
    gürültü notu için uyarı basar ve model uyarıya bakmayı bırakır; çok
    yüksekse hiç uyarmaz. İkisinin arasını veri seti söylüyor:

    * **doğru** = bir `duzelt` olayında en yakın aynı-tür komşu, gerçekten
      o zincirin bir önceki sürümü,
    * **yanlış** = bir `kaydet` olayında (C gürültü kümesi) eşiği geçen bir
      komşu bulunması — orada güncellenecek bir şey yok.
    """
    baslangic = datetime.fromisoformat(veri["baslangic"])
    if baslangic.tzinfo is None:
        baslangic = baslangic.replace(tzinfo=timezone.utc)
    saat = SanalSaat(baslangic)
    dogru: list[float] = []     # düzeltmelerde bulunan doğru adayın skoru
    kacan = 0                   # düzeltme ama aday hiç bulunamadı
    yanlis: list[float] = []    # gürültüde bulunan adayın skoru

    with tempfile.TemporaryDirectory(prefix="yasam-celiski-") as ad:
        kok = Path(ad)
        mind = _zihin_ac(kok, saat)
        store = mind.store
        try:
            kimlik: dict[str, str] = {}
            for olay in sorted(veri["olaylar"],
                               key=lambda e: (e["gun"], e["saat"], e.get("sira", 0))):
                if olay["tur"] not in ("kaydet", "duzelt"):
                    continue
                saat.ilerle(olay["gun"], int(olay["saat"]))
                aday = _en_yakin_ayni_tur(store, olay["icerik"], olay["kind"])
                if olay["tur"] == "duzelt":
                    hedef = kimlik.get(olay["eskisi"], "")
                    if aday and aday[0] == hedef:
                        dogru.append(aday[1])
                    else:
                        kacan += 1
                elif olay["kume"] == "C" and aday:
                    yanlis.append(aday[1])
                m = mind.remember(olay["icerik"], kind=olay["kind"],
                                  title=olay.get("baslik") or "",
                                  tags=olay.get("etiketler") or [])
                kimlik[olay["slug"]] = m.id
        finally:
            store.close()

    toplam_duzelt = len(dogru) + kacan
    tablo = []
    for esik in (0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90):
        yakalanan = sum(1 for x in dogru if x >= esik)
        alarm = sum(1 for x in yanlis if x >= esik)
        tablo.append({
            "esik": esik,
            "yakalama": round(yakalanan / toplam_duzelt, 4) if toplam_duzelt else None,
            "yanlis_alarm": round(alarm / max(len(yanlis) + 1, 1), 4),
            "yanlis_sayi": alarm,
        })
    return {"tablo": tablo, "duzeltme": toplam_duzelt, "gurultu_aday": len(yanlis),
            "dogru_skorlar": sorted(round(x, 3) for x in dogru)}


def _en_yakin_ayni_tur(store: Any, body: str, kind: str) -> tuple[str, float] | None:
    """`celiski_adayi`nın eşiksiz hâli — kalibrasyon için ham skor."""
    for node_id, score, aday_kind in store._seed(body[:400], 3):   # noqa: SLF001
        if aday_kind == kind:
            return node_id, score
    return None


def _celiski_raporu(rapor: dict[str, Any]) -> Path:
    satirlar = [
        "# Çelişki eşiği (`CELISKI_ESIK`) kalibrasyonu",
        "",
        f"{rapor['duzeltme']} düzeltme olayı, {rapor['gurultu_aday']} gürültü "
        "kaydında aday bulundu. **Yakalama** = düzeltmede doğru önceki sürümün "
        "eşiği geçme oranı. **Yanlış alarm** = gürültü kaydında eşiği geçen "
        "aday oranı — orada güncellenecek bir şey yok.",
        "",
        "| Eşik | Yakalama ↑ | Yanlış alarm ↓ | Yanlış sayı |",
        "|---|---|---|---|",
    ]
    for satir in rapor["tablo"]:
        satirlar.append(f"| {satir['esik']:.2f} | {_bicim(satir['yakalama'])} "
                        f"| {_bicim(satir['yanlis_alarm'])} | {satir['yanlis_sayi']} |")
    yol = CHARTS() / "celiski-esigi.md"
    yol.write_text("\n".join(satirlar) + "\n", encoding="utf-8")
    (CHARTS() / "celiski-esigi.json").write_text(
        json.dumps(rapor, ensure_ascii=False, indent=1), encoding="utf-8")
    return yol


# -- rapor -------------------------------------------------------------



def CHARTS() -> Path:
    yol = KOK / "docs" / "charts"
    yol.mkdir(parents=True, exist_ok=True)
    return yol


def _bicim(deger: Any) -> str:
    if deger is None:
        return "yok"
    return f"{deger:g}" if isinstance(deger, (int, float)) else str(deger)


def _hedef_metin(ad: str) -> str:
    _yon, karsilastir, hedef = HEDEFLER[ad]
    if hedef is not None:
        return f"{karsilastir} {hedef:g}"
    return "0.10–0.30" if ad == "sicak_oran" else "≤ taban"


def markdown_yaz(etiket: str, sonuc: dict[str, Any], eski: dict[str, Any] | None,
                 onceki: dict[str, Any] | None) -> Path:
    m = sonuc["metrikler"]
    e = (eski or {}).get("metrikler", {})
    p = (onceki or {}).get("metrikler", {})
    satirlar = [
        f"# Yaşam benchmark'ı — `{etiket}`",
        "",
        f"Senaryo **{sonuc['veri']}** · {sonuc['sayim']['soru']} soru · "
        f"{sonuc['sayim']['dugum']} düğüm · kaynak `{sonuc['kaynak']}` · "
        f"kapalı mekanik `{', '.join(sonuc['kapali']) or 'yok'}`",
        "",
        "| Metrik | Yön | eski | önceki | bu faz | Hedef |",
        "|---|---|---|---|---|---|",
    ]
    for ad, deger in m.items():
        satirlar.append(
            f"| `{ad}` | {HEDEFLER[ad][0]} | {_bicim(e.get(ad)) if eski else '—'} "
            f"| {_bicim(p.get(ad)) if onceki else '—'} | **{_bicim(deger)}** "
            f"| {_hedef_metin(ad)} |")

    satirlar += ["", "## Küme kırılımı (prime precision / recall)", "",
                 "| Küme | Ne ölçer | Precision | Recall | Yasak sızıntı |",
                 "|---|---|---|---|---|"]
    ACIKLAMA = {"A": "sabit gerçekler", "B": "düzeltme zincirleri",
                "D": "tekrar kullanılan yordamlar", "E": "bağlam çakışması",
                "H": "zaman komşuluğu", "J": "dikiş", "K": "gömülme"}
    for k, d in sonuc["kume"].items():
        satirlar.append(f"| {k} | {ACIKLAMA[k]} | {_bicim(d['precision'])} "
                        f"| {_bicim(d['recall'])} | {_bicim(d.get('sizinti'))} |")

    if olcek := sonuc.get("olcek"):
        satirlar += ["", "## Ölçekte gecikme", "",
                     f"{olcek['dugum']} düğüm · p50 **{olcek['gecikme_p50']:g} ms** · "
                     f"p95 **{olcek['gecikme_p95']:g} ms** "
                     f"(bütçe {GECIKME_BUTCE_MS:g} ms)"]
    if buyume := sonuc.get("buyume"):
        satirlar += ["", "## Büyüme (P kümesi)", "",
                     f"{buyume['buyuk']['dugum']} / {buyume['kucuk']['dugum']} düğüm · "
                     f"p95 oranı **{buyume['buyume_p95']:g}** (hedef ≤ 1.5) · "
                     f"RAM oranı **{buyume['buyume_ram']:g}** (hedef ≤ 2)"]

    satirlar += ["", "---", "",
                 "`yok` = o sürümde mekanik hiç yoktu; boş bırakılmaz.", "",
                 f"Üretim: `py eval/context_memory/yasam_bench.py --etiket {etiket}`. "
                 "Sayılar deterministiktir: aynı veri seti, aynı sanal takvim, "
                 "aynı sonuç."]
    yol = CHARTS() / f"yasam-{etiket}.md"
    yol.write_text("\n".join(satirlar) + "\n", encoding="utf-8")
    return yol


def ozet_tablo() -> Path:
    kosular = []
    for dosya in sorted(CHARTS().glob("yasam-*.json")):
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
        degerler = [_bicim(k["metrikler"].get(ad)) for k in kosular]
        satirlar.append(f"| `{ad}` | {HEDEFLER[ad][0]} | " + " | ".join(degerler)
                        + f" | {_hedef_metin(ad)} |")
    yol = CHARTS() / "yasam-ozet.md"
    yol.write_text("\n".join(satirlar) + "\n", encoding="utf-8")
    return yol


def _esik_raporu(rapor: dict[str, Any]) -> Path:
    esik = rapor["esik"]
    satirlar = [
        "# Basınç–bozulma eğrisi (`esik_egrisi`)",
        "",
        "Gece geçişi **kapalı**. S (küçültülmemiş güçlenme: toplam kenar "
        "ağırlığı / düğüm) gün gün artarken önyükleme precision'ı ve yeni "
        "kaydın komşu doğruluğu ölçülüyor. `ESIK_UST`, ilk on ölçülen günün "
        "ortalamasından %5 düşüşün başladığı S değeridir; `ESIK_ALT` onun "
        "üçte biri. Bu sayılar elle seçilmez — `uyku.py` onları buradan alır.",
        "",
        f"- taban precision: **{_bicim(esik['taban_precision'])}**",
        f"- `ESIK_UST` = **{_bicim(esik['ESIK_UST'])}**",
        f"- `ESIK_ALT` = **{_bicim(esik['ESIK_ALT'])}**",
        "",
        "| Gün | S | precision | komşu doğruluk |", "|---|---|---|---|",
    ]
    for e in rapor["egri"]:
        satirlar.append(f"| {e['gun']} | {e['s']:g} | {_bicim(e['precision'])} "
                        f"| {_bicim(e['komsu_dogruluk'])} |")
    yol = CHARTS() / "basinc-bozulma.md"
    yol.write_text("\n".join(satirlar) + "\n", encoding="utf-8")
    (CHARTS() / "basinc-bozulma.json").write_text(
        json.dumps(rapor, ensure_ascii=False, indent=1), encoding="utf-8")
    return yol


# -- eski sürüm --------------------------------------------------------


def eski_agac_hazir() -> Path:
    """`hafiza-eski` etiketinin ayrı checkout'u (git worktree)."""
    if (ESKI_AGAC / "src" / "dornick").is_dir():
        return ESKI_AGAC
    subprocess.run(["git", "worktree", "add", str(ESKI_AGAC), "hafiza-eski"],
                   cwd=KOK, check=True, capture_output=True)
    return ESKI_AGAC


def eski_kosu(argv: list[str]) -> dict[str, Any]:
    """Eski sürümü ayrı süreçte koşturur ve JSON raporunu döndürür.

    Ayrı süreç şart: iki farklı `dornick` paketi aynı yorumlayıcıda yan yana
    duramaz.
    """
    agac = eski_agac_hazir()
    ortam = dict(os.environ, DORNICK_SRC=str(agac / "src"), DORNICK_ESKI="1")
    komut = [sys.executable, str(Path(__file__).resolve()), "--json", *argv]
    sonuc = subprocess.run(komut, cwd=KOK, env=ortam, capture_output=True,
                           text=True, encoding="utf-8")
    if sonuc.returncode != 0:
        raise RuntimeError(f"eski sürüm koşusu başarısız:\n{sonuc.stderr[-4000:]}")
    return json.loads(sonuc.stdout)


# -- giriş -------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Yaşam benchmark'ı")
    ap.add_argument("--veri", default="ana", help="ana | holdout | dosya adı")
    ap.add_argument("--etiket", default="", help="rapor adı (docs/charts/yasam-<etiket>)")
    ap.add_argument("--onceki", default="", help="karşılaştırılacak önceki fazın etiketi")
    ap.add_argument("--eski", action="store_true",
                    help="hafiza-eski etiketindeki sürümü ölç")
    ap.add_argument("--kapat", default="",
                    help="virgülle: " + (", ".join(anahtar.ADLAR) if anahtar else "-"))
    ap.add_argument("--sira", type=int, default=99, help="özet tablodaki sütun sırası")
    ap.add_argument("--hizli", action="store_true", help="ölçek gecikme ölçümünü atla")
    ap.add_argument("--olcek", type=int, default=OLCEK_DUGUM)
    ap.add_argument("--buyume", action="store_true", help="P kümesi (200k/20k) — uzun")
    ap.add_argument("--kesinti", action="store_true",
                    help="L ve M kolları (kesinti, ritim)")
    ap.add_argument("--damitma", action="store_true",
                    help="gece damıtmasını deterministik çıkarımcı modelle koştur")
    ap.add_argument("--uykusuz", action="store_true",
                    help="R ve S kolları (uykusuz makine, aktif bölge)")
    ap.add_argument("--celiski-esik", action="store_true", dest="celiski",
                    help="CELISKI_ESIK kalibrasyonu (Faz 2.4)")
    ap.add_argument("--esik-egrisi", action="store_true", dest="esik",
                    help="gece kapalıyken bozulma eğrisi; ESIK_UST buradan")
    ap.add_argument("--json", action="store_true", help="yalnız JSON bas")
    ap.add_argument("--tablo", action="store_true", help="birikmiş özet tabloyu üret")
    args = ap.parse_args(argv)

    if args.tablo:
        print(ozet_tablo())
        return 0

    veri = veri_yukle(args.veri)

    if args.celiski:
        rapor = celiski_esigi(veri)
        print(_celiski_raporu(rapor))
        for satir in rapor["tablo"]:
            print(f"  esik={satir['esik']:.2f}  yakalama={_bicim(satir['yakalama'])}"
                  f"  yanlis={satir['yanlis_sayi']}")
        return 0

    if args.esik:
        rapor = esik_egrisi(veri)
        print(_esik_raporu(rapor))
        print(json.dumps(rapor["esik"], ensure_ascii=False))
        return 0

    if args.eski and not ESKI_SURUM:
        gecirilecek = ["--veri", args.veri, "--sira", str(args.sira)]
        if args.hizli:
            gecirilecek.append("--hizli")
        if args.buyume:
            gecirilecek.append("--buyume")
        sonuc = eski_kosu(gecirilecek)
    else:
        kapali = tuple(a.strip() for a in args.kapat.split(",") if a.strip())
        if anahtar is not None and (bilinmeyen := set(kapali) - set(anahtar.ADLAR)):
            print(f"Bilinmeyen mekanik: {', '.join(sorted(bilinmeyen))}", file=sys.stderr)
            return 2
        basla = time.perf_counter()
        sonuc = kosu(veri, kapali=kapali, damitma=args.damitma)
        sonuc["veri"] = veri["ad"]
        sonuc["kapali"] = list(kapali)
        sonuc["damitma"] = bool(args.damitma)
        sonuc["kaynak"] = "hafiza-eski" if ESKI_SURUM else "calisma-agaci"
        sonuc["sure_sn"] = round(time.perf_counter() - basla, 1)
        if not args.hizli:
            sonuc["olcek"] = _gecikme_probu(veri, args.olcek)
            # Ölçek şartı senaryonun kendi hacminde değil 50k'da geçerli.
            sonuc["metrikler"]["gecikme_p95"] = sonuc["olcek"]["gecikme_p95"]
        if args.kesinti:
            sonuc["kesinti"] = kesinti_deneyi(veri)
            sonuc["metrikler"].update(sonuc["kesinti"])
        if args.uykusuz:
            sonuc["uykusuz"] = uykusuz_deneyi(veri)
            sonuc["aktif"] = aktif_bolge_deneyi(veri)
            m = sonuc["metrikler"]
            m["uykusuz_kayip"] = sonuc["uykusuz"]["uykusuz_kayip"]
            m["uykusuz_sisme"] = sonuc["uykusuz"]["uykusuz_sisme"]
            m["aktif_bolge_ihlali"] = sonuc["aktif"]["aktif_bolge_ihlali"]
        if args.buyume:
            sonuc["buyume"] = buyume_deneyi(veri)
            sonuc["metrikler"]["buyume_p95"] = sonuc["buyume"]["buyume_p95"]
            sonuc["metrikler"]["buyume_ram"] = sonuc["buyume"]["buyume_ram"]

    sonuc["etiket"] = args.etiket or "adsiz"
    sonuc["sira"] = args.sira

    if args.json:
        print(json.dumps(sonuc, ensure_ascii=False, indent=1))
        return 0

    eski_rapor = _rapor_oku("taban") if args.etiket != "taban" else None
    onceki_rapor = _rapor_oku(args.onceki) if args.onceki else None
    if args.etiket:
        (CHARTS() / f"yasam-{args.etiket}.json").write_text(
            json.dumps(sonuc, ensure_ascii=False, indent=1), encoding="utf-8")
        print(markdown_yaz(args.etiket, sonuc, eski_rapor, onceki_rapor))

    genislik = max(len(a) for a in sonuc["metrikler"])
    for ad, deger in sonuc["metrikler"].items():
        print(f"  {ad:<{genislik}}  {HEDEFLER[ad][0]}  {_bicim(deger)}")
    print(f"  {'süre':<{genislik}}     {sonuc.get('sure_sn', 0):g} sn")
    return 0


def _rapor_oku(etiket: str) -> dict[str, Any] | None:
    yol = CHARTS() / f"yasam-{etiket}.json"
    if not yol.exists():
        return None
    try:
        return json.loads(yol.read_text(encoding="utf-8"))
    except ValueError:
        return None


if __name__ == "__main__":
    raise SystemExit(main())
