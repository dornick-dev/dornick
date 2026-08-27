"""Kodlama ölçüm düzeneğinin ortak puanlama kütüphanesi.

Felsefe hafıza tarafındaki `eval/context_memory/scale_bench.py`'den geliyor
ve dört maddeye sığıyor:

  1. **Donmuş veri seti.** Görevler ve tohum dosyaları depoda sabit durur.
     Aynı görev bugün de altı ay sonra da aynı şeyi sorar; iki koşunun farkı
     ürünün farkıdır, ölçüğün farkı değil.
  2. **Ürünün GERÇEK kod yolu ölçülür.** Orada `loop.select_prime` doğrudan
     çağrılıyordu; burada görev, ürünün kendi dış kapısından (POST /api/gate)
     gerçek ajana veriliyor. Ajanın taklidi değil kendisi koşuyor.
  3. **Tek atış.** Puanlayıcı ajana ikinci şans, ipucu, düzeltme turu vermez.
     Kullanıcı da vermiyor — "bir kere söyledim, çalışan bir şey istiyorum".
  4. **Parametrik kopya yasağı.** Orada kopyanın üründen ayrışmadığı her
     koşuda doğrulanıyordu. Burada karşılığı: puanlayıcı ajanın yazdığı
     testlere GÜVENMEZ. Kendi koşum dosyasını kendi geçici dizininde kurar,
     regresyon takımlarının bozulmamış kopyasını üstüne yazar. Ajan
     testi değiştirerek puan alamaz.

Beşinci madde bu tarafa özel — **dürüstlük**:

     Ölçülemeyen eksene kısmi puan uydurulmaz. `Eksen.alinan is None`
     "ölçülemedi" demektir ve o eksen paydadan da düşer. Ajandan
     istenmemiş bir iş (istem test istemiyorsa test) `harici=True` ile
     ölçülür, raporlanır, ama puana katılmaz — yapmadığı iş için ceza
     kesilmez, yaptığı iş de karşılıksız kalmaz.

Puan ekseni ve ağırlıkları (Fatih'in koyduğu cetvel):

    ÇALIŞIR MI      40   kurulum/başlatma/HTTP 200/CLI çıkış kodu
    İSTENEN KAPSAM  25   dosya-uç-işlev varlığı + davranış testi
    KOD SAĞLIĞI     20   tanı araçları, dosya boyu/karmaşıklık, tekrar
    TEST KALİTESİ   15   testler koşuyor mu, kaç tane, kritik yolu tutuyor mu
"""

from __future__ import annotations

import http.cookiejar
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

# Eksen adları ve tavanları. Tek yerde durur; rapor da buradan okur.
EKSENLER: dict[str, int] = {
    "calisir": 40,
    "kapsam": 25,
    "saglik": 20,
    "test": 15,
}

EKSEN_BASLIK = {
    "calisir": "çalışır mı",
    "kapsam": "istenen kapsam",
    "saglik": "kod sağlığı",
    "test": "test kalitesi",
}

# Tarama dışı klasörler: araç artıkları, bağımlılık depoları, sürüm kontrolü.
ATLA_KLASOR = frozenset({
    ".git", "__pycache__", "node_modules", ".venv", "venv", "vendor",
    ".pytest_cache", ".ruff_cache", ".geri-donusum", "dist", "build",
    ".neocp", ".idea", ".vscode",
})

KAYNAK_UZANTI = {".py": "python", ".php": "php", ".js": "node", ".mjs": "node"}

# Ölçüm dışı dosyaların listesi (atölye köküne göre POSIX yollar, JSON dizi).
# Koşucu yazıyor: tur BAŞLAMADAN önce atölyede duran ve turda hiç
# DEĞİŞMEYEN dosyalar. İki kaynağı var ve ikisi de ajanın eseri değil:
#   * neo'nun açılışta atölyeye kopyaladığı standart yetenekler
#     (`skills.seed` → `atolye/yetenekler/*.py`),
#   * görevin tohum dosyaları.
# Ölçülen ilk koşuda kod sağlığı puanı bu yüzden düşüyordu: karmaşıklık
# cezası ürünün kendi yetenek dosyalarından geliyordu. Ajanın DOKUNDUĞU
# tohum dosyası listede olmaz — tamir görevlerinde düzeltilen dosya
# ölçüme girmeye devam eder.
HARIC_DOSYA = ".olcum-haric"

# Bir alt sürecin makul üst sınırı. Ajanın kodu sonsuza kadar koşamaz.
VARSAYILAN_ZAMAN_ASIMI = 90.0


# -- alt süreç ----------------------------------------------------------


@dataclass(slots=True)
class Kosum:
    """Bir alt süreç koşusunun ham sonucu."""

    argv: list[str]
    kod: int | None          # None => zaman aşımı ya da hiç başlamadı
    cikti: str
    hata: str
    sn: float
    patlama: str = ""        # süreç hiç başlamadıysa sebebi

    @property
    def tamam(self) -> bool:
        return self.kod == 0

    @property
    def hepsi(self) -> str:
        return f"{self.cikti}\n{self.hata}"

    def ozet(self, n: int = 200) -> str:
        gövde = " ".join(self.hepsi.split())
        return gövde[:n]


def kabuk(
    argv: Sequence[str],
    *,
    cwd: Path | str | None = None,
    zaman_asimi: float = VARSAYILAN_ZAMAN_ASIMI,
    girdi: str | None = None,
    ortam: dict[str, str] | None = None,
) -> Kosum:
    """Bir komutu koşturur ve sonucunu ham haliyle döndürür.

    Hiçbir şey fırlatmaz: puanlayıcı, ölçtüğü şeyin patlamasıyla birlikte
    patlamamalı. Patlayan koşu `kod=None` ile geri gelir ve eksen bunu
    "çalışmadı" (ölçüldü, sıfır) ya da "ölçülemedi" diye YORUMLAR — ikisi
    farklı şeyler ve ayrımı çağıran verir.
    """
    env = dict(os.environ)
    if ortam:
        env.update(ortam)
    # Alt süreçlerin çıktısı Türkçe: Windows'ta cp1254'e düşerse kırılıyor.
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONUTF8", "1")
    basladi = time.perf_counter()
    try:
        tamam = subprocess.run(
            list(argv),
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            input=girdi,
            timeout=zaman_asimi,
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        return Kosum(list(argv), None, exc.stdout or "", exc.stderr or "",
                     time.perf_counter() - basladi, patlama="zaman aşımı")
    except (OSError, ValueError) as exc:
        return Kosum(list(argv), None, "", "", time.perf_counter() - basladi,
                     patlama=f"{type(exc).__name__}: {exc}")
    return Kosum(list(argv), tamam.returncode, tamam.stdout or "",
                 tamam.stderr or "", time.perf_counter() - basladi)


def _py() -> list[str]:
    """Bu düzeneği koşturan yorumlayıcı. `py`/`python` ayrımına takılmamak için."""
    return [sys.executable]


def php_var() -> bool:
    return kabuk(["php", "-v"], zaman_asimi=15).kod == 0


def node_var() -> bool:
    return kabuk(["node", "-v"], zaman_asimi=15).kod == 0


def ruff_var() -> bool:
    return kabuk([*_py(), "-m", "ruff", "--version"], zaman_asimi=20).kod == 0


# -- dosya bulma --------------------------------------------------------


def haric_tutulanlar(kok: Path) -> set[str]:
    """Ölçüm dışı bırakılan dosyalar (bkz. HARIC_DOSYA)."""
    yol = kok / HARIC_DOSYA
    try:
        veri = json.loads(yol.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    return {str(p) for p in veri} if isinstance(veri, list) else set()


def kaynaklar(kok: Path, *uzantilar: str) -> list[Path]:
    """Ajanın ürettiği kaynak dosyalar (araç artıkları ve ölçüm dışı hariç).

    Deterministik sıra: aynı atölye iki kez puanlanınca aynı listeyi verir.
    """
    istenen = set(uzantilar) or set(KAYNAK_UZANTI)
    haric = haric_tutulanlar(kok)
    bulunan: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(kok):
        dirnames[:] = sorted(d for d in dirnames
                             if d not in ATLA_KLASOR and not d.startswith("."))
        for ad in sorted(filenames):
            yol = Path(dirpath) / ad
            if yol.suffix.lower() not in istenen:
                continue
            if yol.relative_to(kok).as_posix() in haric:
                continue
            bulunan.append(yol)
    return bulunan


def bul(kok: Path, *adaylar: str) -> Path | None:
    """Verilen adlardan ilk bulunanı döndürür (kökten başlayarak, sığdan derine).

    Ajan dosyayı kökün altına ya da bir alt klasöre koymuş olabilir; ikisi de
    kabul. Ad hiç tutmuyorsa None — o zaman eksen "yok" der, uydurmaz.
    """
    hedefler = [a.casefold() for a in adaylar]
    bulunan: list[tuple[int, str, Path]] = []
    for dirpath, dirnames, filenames in os.walk(kok):
        dirnames[:] = sorted(d for d in dirnames
                             if d not in ATLA_KLASOR and not d.startswith("."))
        derinlik = len(Path(dirpath).relative_to(kok).parts)
        for ad in filenames:
            if ad.casefold() in hedefler:
                bulunan.append((derinlik, ad.casefold(), Path(dirpath) / ad))
    if not bulunan:
        return None
    # Önce istenen ad sırası, sonra sığ olan.
    bulunan.sort(key=lambda t: (hedefler.index(t[1]), t[0], str(t[2])))
    return bulunan[0][2]


def desenle_bul(kok: Path, desen: str) -> list[Path]:
    """Ada göre regex ile dosya arar (test dosyalarını bulmak için)."""
    kalip = re.compile(desen, re.IGNORECASE)
    return [p for p in kaynaklar(kok) if kalip.search(p.name)]


def oku(yol: Path) -> str:
    try:
        return yol.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


# -- eksen / karne ------------------------------------------------------


@dataclass
class Eksen:
    """Tek bir puan ekseni.

    alinan is None  → ÖLÇÜLEMEDİ. Eksen paydadan düşer, rapor "ölçülemedi"
                      yazar ve `sebep` neden ölçülemediğini söyler.
    harici          → İSTENMEDİ. Ölçüldü ve raporlanıyor ama puana katılmıyor
                      (istem test istemiyorsa test yazmamak kusur değildir).
    """

    ad: str
    tavan: int
    alinan: float | None = None
    kanit: list[str] = field(default_factory=list)
    sebep: str = ""
    harici: bool = False

    @property
    def sayilir(self) -> bool:
        return self.alinan is not None and not self.harici

    @property
    def baslik(self) -> str:
        return EKSEN_BASLIK.get(self.ad, self.ad)

    def yaz(self) -> str:
        if self.alinan is None:
            return "ölçülemedi"
        etiket = f"{self.alinan:.1f}/{self.tavan}"
        return f"{etiket} (istenmedi)" if self.harici else etiket

    def sozluk(self) -> dict[str, Any]:
        return {
            "ad": self.ad, "tavan": self.tavan, "alinan": self.alinan,
            "kanit": self.kanit, "sebep": self.sebep, "harici": self.harici,
        }


class Sayac:
    """Kontrol listesi toplayıcısı: her madde ağırlıklı ve kanıtlı.

    Kısmi puan yalnızca gerçekten yapılmış bir maddeden gelir; bir maddenin
    "yarısı olmuş" diye puan uydurulmaz. Ölçülemeyen madde `atla()` ile
    listeden ve tavandan birlikte düşer.
    """

    def __init__(self) -> None:
        self.tavan = 0.0
        self.alinan = 0.0
        self.kanit: list[str] = []
        self.atlanan: list[str] = []

    def madde(self, ad: str, agirlik: float, gecti: bool, not_: str = "") -> bool:
        self.tavan += agirlik
        if gecti:
            self.alinan += agirlik
        isaret = "+" if gecti else "-"
        ek = f" — {not_}" if not_ else ""
        self.kanit.append(f"{isaret} {ad} ({agirlik:g}p){ek}")
        return gecti

    def oranli(self, ad: str, agirlik: float, oran: float, not_: str = "") -> float:
        """Sürekli ölçüm (ör. sözdizimi temizliği oranı). 0..1 arası kırpılır."""
        oran = max(0.0, min(1.0, float(oran)))
        self.tavan += agirlik
        kazanc = agirlik * oran
        self.alinan += kazanc
        ek = f" — {not_}" if not_ else ""
        self.kanit.append(f"~ {ad} ({kazanc:.1f}/{agirlik:g}p){ek}")
        return kazanc

    def atla(self, ad: str, sebep: str) -> None:
        self.atlanan.append(f"? {ad} — ölçülemedi: {sebep}")
        self.kanit.append(f"? {ad} — ölçülemedi: {sebep}")

    def eksen(self, ad: str, tavan: int, *, harici: bool = False) -> Eksen:
        """Toplanan maddeleri eksenin tavanına ölçekler."""
        if self.tavan <= 0:
            return Eksen(ad, tavan, None, self.kanit,
                         sebep="hiçbir madde ölçülemedi", harici=harici)
        return Eksen(ad, tavan, tavan * (self.alinan / self.tavan),
                     self.kanit, harici=harici)


@dataclass
class Karne:
    """Bir görevin tek koşudaki karnesi."""

    gorev: str
    eksenler: list[Eksen]
    davranis: dict[str, Any] = field(default_factory=dict)
    notlar: list[str] = field(default_factory=list)

    @property
    def olculen_tavan(self) -> float:
        return sum(e.tavan for e in self.eksenler if e.sayilir)

    @property
    def ham(self) -> float:
        return sum(e.alinan or 0.0 for e in self.eksenler if e.sayilir)

    @property
    def puan(self) -> float | None:
        """0-100'e normalize puan; ölçülemiyorsa None.

        ÇALIŞIR ekseni taşıyıcıdır: ölçülemediyse ortada puan YOKTUR. Bu kural
        ölçülen bir yalandan geldi — bir koşuda ajan kendi `php -S`'ini açık
        bırakmıştı, ölçüm portu tutulu bulup çalışır/kapsam eksenlerini
        "ölçülemedi" işaretledi, geriye yalnız kod sağlığı (20/20) kaldı ve
        normalize puan **100.0** çıktı. Teslim edilen şeyin çalışıp
        çalışmadığına bakamadıysak, güzel yazılmış olması not değildir.
        """
        tasiyici = self.eksen("calisir")
        if tasiyici is not None and tasiyici.alinan is None:
            return None
        tav = self.olculen_tavan
        return None if tav <= 0 else 100.0 * self.ham / tav

    @property
    def olculemeyen(self) -> list[str]:
        return [e.baslik for e in self.eksenler if e.alinan is None]

    def eksen(self, ad: str) -> Eksen | None:
        for e in self.eksenler:
            if e.ad == ad:
                return e
        return None

    @property
    def bozuk_teslim(self) -> bool:
        """Teslim edilen şey hiç çalışmıyor mu? (ÇALIŞIR ekseni sıfır)"""
        e = self.eksen("calisir")
        return e is not None and e.alinan is not None and e.alinan <= 0.0

    def sozluk(self) -> dict[str, Any]:
        return {
            "gorev": self.gorev,
            "puan": self.puan,
            "ham": self.ham,
            "olculen_tavan": self.olculen_tavan,
            "olculemeyen": self.olculemeyen,
            "bozuk_teslim": self.bozuk_teslim,
            "eksenler": [e.sozluk() for e in self.eksenler],
            "davranis": self.davranis,
            "notlar": self.notlar,
        }


# -- kod sağlığı --------------------------------------------------------


def sozdizimi(yol: Path) -> tuple[bool, str]:
    """Dosyayı diline göre tanı aracından geçirir.

    Tanınmayan dil ya da eksik araç → (True, "atlandı"): olmayan bir aracın
    yokluğu ajanın kusuru değil. Çağıran bunu `atlandi` sayısıyla görür.
    """
    dil = KAYNAK_UZANTI.get(yol.suffix.lower())
    if dil == "python":
        k = kabuk([*_py(), "-m", "py_compile", str(yol)], zaman_asimi=40)
    elif dil == "php":
        k = kabuk(["php", "-l", str(yol)], zaman_asimi=40)
    elif dil == "node":
        k = kabuk(["node", "--check", str(yol)], zaman_asimi=40)
    else:
        return True, "atlandı"
    if k.kod is None:
        return True, "atlandı"
    return k.tamam, k.ozet(160)


def _girinti_derinligi(satirlar: Iterable[str]) -> int:
    """En derin girinti seviyesi (kaba karmaşıklık göstergesi)."""
    derin = 0
    for satir in satirlar:
        if not satir.strip() or satir.lstrip().startswith(("#", "//", "*")):
            continue
        bosluk = len(satir) - len(satir.lstrip(" \t"))
        derin = max(derin, bosluk // 4 + satir[:bosluk].count("\t"))
    return derin


_ISLEV = re.compile(r"^\s*(def |function |async function |public function |"
                    r"private function |protected function )", re.MULTILINE)


def _en_uzun_islev(metin: str) -> int:
    """İşlev başlangıçları arası en uzun mesafe — kaba "dev fonksiyon" ölçüsü."""
    yerler = [metin[:m.start()].count("\n") for m in _ISLEV.finditer(metin)]
    if not yerler:
        return 0
    yerler.append(metin.count("\n"))
    return max(b - a for a, b in zip(yerler, yerler[1:]))


def tekrar_orani(dosyalar: Sequence[Path], pencere: int = 6) -> tuple[float, int]:
    """Kopyala-yapıştır ölçüsü: aynı 6 satırlık blok kaç yerde tekrar ediyor?

    Satırlar normalize ediliyor (boşluk sadeleştirme) ki girinti farkı
    kopyayı gizlemesin. Dönen: (tekrar eden satır oranı, tekrar eden blok
    sayısı).
    """
    goruldu: dict[str, int] = {}
    tekrarli = 0
    toplam = 0
    for yol in dosyalar:
        satirlar = [" ".join(s.split()) for s in oku(yol).splitlines()]
        satirlar = [s for s in satirlar
                    if s and not s.startswith(("#", "//", "*", "/*"))]
        toplam += len(satirlar)
        for i in range(len(satirlar) - pencere + 1):
            imza = "\n".join(satirlar[i:i + pencere])
            goruldu[imza] = goruldu.get(imza, 0) + 1
            if goruldu[imza] == 2:
                tekrarli += pencere
    if toplam <= pencere:
        return 0.0, 0
    kopya = sum(1 for v in goruldu.values() if v > 1)
    return min(1.0, tekrarli / toplam), kopya


def saglik_ekseni(kok: Path, *, tavan: int = 20) -> Eksen:
    """KOD SAĞLIĞI: tanı araçları (8) + boy/karmaşıklık (6) + tekrar (6).

    Ölçüm ajanın kendi testlerinden bağımsız: dışarıdan bakan bir gözün
    dosyalara söyleyebileceği şeyler.
    """
    dosyalar = [p for p in kaynaklar(kok) if p.suffix.lower() in KAYNAK_UZANTI]
    # Ajanın ürettiği kodu ölçüyoruz; kendi indirdiği bağımlılıkları değil.
    if not dosyalar:
        return Eksen("saglik", tavan, None, [],
                     sebep="atölyede hiç kaynak dosya yok")

    s = Sayac()

    # 1. Sözdizimi / tanı araçları.
    temiz = 0
    atlandi = 0
    bozuklar: list[str] = []
    for yol in dosyalar:
        ok, mesaj = sozdizimi(yol)
        if mesaj == "atlandı":
            atlandi += 1
        if ok:
            temiz += 1
        else:
            bozuklar.append(f"{yol.name}: {mesaj}")
    if atlandi == len(dosyalar):
        s.atla("sözdizimi", "hiçbir dosya için tanı aracı yok")
    else:
        s.oranli("sözdizimi temiz", 8, temiz / len(dosyalar),
                 f"{temiz}/{len(dosyalar)} dosya" +
                 (f"; bozuk: {'; '.join(bozuklar[:3])}" if bozuklar else ""))

    # 2. Boy ve kabaca karmaşıklık. Eşikler kaba bilinçli: bu eksen bir
    #    linter değil, "elden çıkmış dosya var mı" bakışı.
    uzunlar: list[str] = []
    derinler: list[str] = []
    devler: list[str] = []
    for yol in dosyalar:
        metin = oku(yol)
        satirlar = metin.splitlines()
        if len(satirlar) > 400:
            uzunlar.append(f"{yol.name}:{len(satirlar)} satır")
        d = _girinti_derinligi(satirlar)
        if d > 5:
            derinler.append(f"{yol.name}:{d} kat")
        u = _en_uzun_islev(metin)
        if u > 80:
            devler.append(f"{yol.name}:{u} satırlık işlev")
    ihlal = len(uzunlar) + len(derinler) + len(devler)
    s.oranli("boy/karmaşıklık", 6, 1.0 - min(1.0, ihlal / max(2.0, len(dosyalar))),
             "temiz" if not ihlal else "; ".join((uzunlar + derinler + devler)[:3]))

    # 3. Kopyala-yapıştır.
    oran, blok = tekrar_orani(dosyalar)
    # %3'e kadar tolerans (import blokları, standart iskeletler), %25'te sıfır.
    puan_orani = 1.0 - max(0.0, min(1.0, (oran - 0.03) / 0.22))
    s.oranli("tekrar yok", 6, puan_orani,
             f"tekrar eden satır %{oran * 100:.0f}, {blok} yinelenen blok")

    return s.eksen("saglik", tavan)


# -- test kalitesi ------------------------------------------------------


TEST_DESEN = r"(^test_.*\.(py)$)|(_test\.(py|js|mjs)$)|(\.test\.(js|mjs)$)|(^test.*\.(js|mjs)$)|(Test\.php$)|(^test_.*\.php$)"

_TEST_ISLEV = re.compile(
    r"^\s*(?:async\s+)?def\s+test\w*|"           # pytest
    r"\btest\s*\(\s*['\"]|"                       # node:test / jest
    r"\bit\s*\(\s*['\"]|"                          # mocha/jest
    r"^\s*public\s+function\s+test\w*",            # phpunit
    re.MULTILINE,
)

# "assert True" gibi bedava geçen iddialar: sayıyı şişirir, hiçbir şey ölçmez.
_BOS_IDDIA = re.compile(
    r"assert\s+(True|1)\s*$|assertTrue\s*\(\s*true\s*\)|expect\s*\(\s*true\s*\)",
    re.IGNORECASE | re.MULTILINE,
)
_IDDIA = re.compile(
    r"\bassert\b|\bassertEquals?\b|\bexpect\s*\(|\bstrictEqual\b|\bdeepEqual\b",
    re.IGNORECASE,
)


def test_dosyalari(kok: Path) -> list[Path]:
    return desenle_bul(kok, TEST_DESEN)


def test_kos(kok: Path, dosyalar: Sequence[Path]) -> Kosum | None:
    """Ajanın testlerini kendi diliyle koşturur. Dil bilinmiyorsa None."""
    diller = {KAYNAK_UZANTI.get(p.suffix.lower()) for p in dosyalar}
    if "python" in diller:
        return kabuk([*_py(), "-m", "pytest", "-q", "--no-header", "-p",
                      "no:cacheprovider", str(kok)], cwd=kok, zaman_asimi=180)
    if "node" in diller:
        # Yol argümanı bu node sürümünde klasörü kabul etmiyor; koşucu
        # çalışma dizininden kendi tarıyor.
        return kabuk(["node", "--test"], cwd=kok, zaman_asimi=180)
    if "php" in diller:
        # PHPUnit yoksa dosyayı doğrudan koşturmak kalan tek dürüst yol.
        return kabuk(["php", str(dosyalar[0])], cwd=kok, zaman_asimi=120)
    return None


def test_ekseni(
    kok: Path,
    *,
    kritik: Sequence[str] = (),
    tavan: int = 15,
    harici: bool = False,
) -> Eksen:
    """TEST KALİTESİ: koşuyor mu (6) + kaç tane (4) + anlamlı mı (5).

    `kritik`: bu görevde testin dokunması beklenen sembol adları. Testler
    kritik yolun adını hiç anmıyorsa "anlamlı" puanı düşer — sayı çok ama
    hepsi yardımcı fonksiyonu deniyorsa test takımı kritik yolu tutmuyor
    demektir.

    `harici=True`: istem test istemiyordu. Ölçülür, raporlanır, puana
    katılmaz.
    """
    dosyalar = test_dosyalari(kok)
    if not dosyalar:
        # Bu ölçülemedi DEĞİL: bakıldı ve yoktu. Gerçek bir sıfır.
        return Eksen("test", tavan, 0.0, ["- test dosyası yok (0p)"], harici=harici)

    s = Sayac()
    metin = "\n".join(oku(p) for p in dosyalar)
    adet = len(_TEST_ISLEV.findall(metin))

    kosum = test_kos(kok, dosyalar)
    if kosum is None or kosum.kod is None:
        s.atla("testler koşuyor",
               kosum.patlama if kosum else "test dili tanınmadı")
    else:
        s.madde("testler yeşil", 6, kosum.tamam, kosum.ozet(120))

    s.oranli("test adedi", 4, min(1.0, adet / 6.0), f"{adet} test bulundu")

    bos = len(_BOS_IDDIA.findall(metin))
    iddia = len(_IDDIA.findall(metin))
    if not kritik:
        s.atla("kritik yol kapsanıyor", "görev kritik sembol bildirmedi")
    else:
        tutan = [k for k in kritik if k.casefold() in metin.casefold()]
        s.oranli("kritik yol kapsanıyor", 3, len(tutan) / len(kritik),
                 f"{len(tutan)}/{len(kritik)}: {', '.join(tutan) or 'hiçbiri'}")
    s.oranli("iddialar dolu", 2,
             0.0 if iddia == 0 else 1.0 - min(1.0, bos / iddia),
             f"{iddia} iddia, {bos} tanesi bedava geçiyor")

    return s.eksen("test", tavan, harici=harici)


# -- HTTP / sunucu yardımcıları -----------------------------------------


def port_bos_mu(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket() as s:
        s.settimeout(0.4)
        return s.connect_ex((host, port)) != 0


def port_bekle(port: int, sn: float, host: str = "127.0.0.1") -> bool:
    son = time.time() + sn
    while time.time() < son:
        with socket.socket() as s:
            s.settimeout(0.5)
            if s.connect_ex((host, port)) == 0:
                return True
        time.sleep(0.25)
    return False


@dataclass(slots=True)
class Yanit:
    kod: int
    govde: str
    basliklar: dict[str, str]
    url: str
    hata: str = ""


class Tarayici:
    """Çerezli minik istemci: giriş korumalı panelleri ölçmenin tek yolu.

    Yönlendirmeyi takip etmemek seçenekli: "giriş yapmadan ozet.php'ye
    gidince girişe atıyor mu" sorusunun cevabı 302'nin kendisinde.
    """

    def __init__(self) -> None:
        self.kavanoz = http.cookiejar.CookieJar()
        self._takipli = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.kavanoz))

        class _Durdur(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *a: Any, **k: Any) -> None:  # noqa: D401
                return None

        self._takipsiz = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.kavanoz), _Durdur)

    def iste(
        self,
        url: str,
        *,
        veri: bytes | None = None,
        json_govde: dict[str, Any] | None = None,
        takip: bool = True,
        zaman_asimi: float = 15.0,
    ) -> Yanit:
        basliklar = {"User-Agent": "neocp-eval/1.0"}
        if json_govde is not None:
            veri = json.dumps(json_govde).encode("utf-8")
            basliklar["Content-Type"] = "application/json"
        elif veri is not None:
            basliklar["Content-Type"] = "application/x-www-form-urlencoded"
        istek = urllib.request.Request(url, data=veri, headers=basliklar)
        acici = self._takipli if takip else self._takipsiz
        try:
            with acici.open(istek, timeout=zaman_asimi) as yanit:
                govde = yanit.read().decode("utf-8", "replace")
                return Yanit(yanit.status, govde, dict(yanit.headers), yanit.url)
        except urllib.error.HTTPError as exc:
            govde = exc.read().decode("utf-8", "replace") if exc.fp else ""
            return Yanit(exc.code, govde, dict(exc.headers or {}), url)
        except (urllib.error.URLError, OSError, ValueError) as exc:
            return Yanit(0, "", {}, url, hata=f"{type(exc).__name__}: {exc}")


class Sunucu:
    """Ajanın yazdığı sunucuyu ayağa kaldırır ve koşu bitince öldürür.

    `with Sunucu(...) as s:` — `s.acildi` porta bağlanıldığını söyler,
    `s.gunluk` süreçten dökülen her şeyi. Süreç ölmüşse `s.olu` True.
    """

    def __init__(
        self,
        argv: Sequence[str],
        *,
        cwd: Path,
        port: int,
        hazir_sn: float = 25.0,
    ) -> None:
        self.argv = list(argv)
        self.cwd = cwd
        self.port = port
        self.hazir_sn = hazir_sn
        self.surec: subprocess.Popen[str] | None = None
        self.acildi = False
        self.gunluk = ""
        self.patlama = ""

    def __enter__(self) -> "Sunucu":
        env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
        try:
            self.surec = subprocess.Popen(
                self.argv, cwd=str(self.cwd), stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                errors="replace", env=env,
            )
        except (OSError, ValueError) as exc:
            self.patlama = f"{type(exc).__name__}: {exc}"
            return self
        self.acildi = port_bekle(self.port, self.hazir_sn)
        return self

    @property
    def olu(self) -> bool:
        return self.surec is None or self.surec.poll() is not None

    def __exit__(self, *_: Any) -> None:
        if self.surec is None:
            return
        try:
            self.surec.terminate()
            try:
                self.gunluk = self.surec.communicate(timeout=8)[0] or ""
            except subprocess.TimeoutExpired:
                self.surec.kill()
                self.gunluk = self.surec.communicate(timeout=8)[0] or ""
        except Exception:
            pass


PHP_KAZA = re.compile(
    r"Fatal error|Parse error|Warning:|Notice:|Deprecated:|Undefined "
    r"(variable|index|array key)|Uncaught \w*(Error|Exception)",
    re.IGNORECASE,
)


def sayfa_saglam(y: Yanit, *, en_az: int = 120) -> tuple[bool, str]:
    """Bir sayfanın GERÇEKTEN çalıştığını söyler.

    "200 döndü" yetmiyor: PHP ölümcül hatayı da 200 ile servis edebiliyor,
    boş gövde de 200 dönebiliyor. Bugün tam burada kırıldık — o yüzden
    kontrol üç katlı: durum kodu, gövde uzunluğu, hata izi.
    """
    if y.kod != 200:
        return False, f"HTTP {y.kod}{(' — ' + y.hata) if y.hata else ''}"
    if len(y.govde.strip()) < en_az:
        return False, f"gövde {len(y.govde.strip())} karakter (boş sayılır)"
    if m := PHP_KAZA.search(y.govde):
        return False, f"sayfada hata izi: {m.group(0)}"
    return True, f"200, {len(y.govde)} karakter"


# -- sayı yardımcıları (rapor çıktısı ölçmek için) ----------------------


# Ayraç olarak yalnız nokta ve virgül: boşluk/satır sonu sınıfa girerse
# "47553.25\n  2026" tek sayı sanılıyor ve iki komşu rakam birbirini yiyordu
# (ölçülen: doğru raporun aylık cirolarından ikisi görünmüyordu).
_SAYI = re.compile(r"-?\d+(?:[.,]\d+)*")


def sayilar(metin: str) -> list[float]:
    """Metindeki tüm sayıları çıkarır; Türkçe ve İngilizce ayraç toleranslı.

    Ajanın "1.234,56" mı "1234.56" mı yazacağını şart koşmuyoruz — ölçtüğümüz
    şey rakamın DOĞRU olması, biçimi değil.
    """
    cikan: list[float] = []
    for ham in _SAYI.findall(metin):
        gövde = ham.strip()
        for aday in {gövde, gövde.replace(".", "").replace(",", "."),
                     gövde.replace(",", "")}:
            try:
                cikan.append(float(aday))
            except ValueError:
                continue
    return cikan


def sayi_var(metin: str, beklenen: float, tolerans: float = 0.011) -> bool:
    """Beklenen sayı metinde geçiyor mu?

    Tolerans bir kuruş: farklı sırada yuvarlamadan doğan kayma kabul, iki
    kuruşluk hesap hatası değil. Biçim serbest, değer değil.
    """
    return any(abs(s - beklenen) <= tolerans for s in sayilar(metin))


def sira_var(metin: str, sirali: Sequence[str]) -> bool:
    """Verilen parçalar metinde bu SIRAYLA geçiyor mu? (top-3 sıralaması için)"""
    yer = -1
    kucuk = metin.casefold()
    for parca in sirali:
        bulundu = kucuk.find(parca.casefold(), yer + 1)
        if bulundu <= yer:
            return False
        yer = bulundu
    return True


# -- tek başına koşturma ------------------------------------------------


def tek_basina(olc: Callable[[Path], list[Eksen]], gorev_adi: str) -> int:
    """`py olcut.py <atolye>` — puanlayıcıyı koşucusuz denemek için."""
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except Exception:
        pass
    if len(sys.argv) < 2:
        print("kullanım: py olcut.py <atolye-klasoru>")
        return 2
    kok = Path(sys.argv[1]).resolve()
    if not kok.is_dir():
        print(f"klasör yok: {kok}")
        return 2
    karne = Karne(gorev_adi, olc(kok))
    for e in karne.eksenler:
        print(f"\n[{e.baslik}] {e.yaz()}")
        for k in e.kanit:
            print(f"   {k}")
        if e.sebep:
            print(f"   sebep: {e.sebep}")
    puan = karne.puan
    print(f"\nPUAN: {'ölçülemedi' if puan is None else f'{puan:.1f}/100'}"
          f"  (ham {karne.ham:.1f}/{karne.olculen_tavan:.0f})")
    return 0
