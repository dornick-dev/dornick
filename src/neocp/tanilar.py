"""Kod tanıları: yazılan dosyayı, daha kimse çalıştırmadan denetle.

Neden var: ajanın en pahalı hata sınıfı "yazdım, çalıştırmadım, bitti dedim".
Dosya diske düşüyor, tur kapanıyor, hata ancak kullanıcı sayfayı açtığında
ortaya çıkıyor — ve o noktada modelin bağlamı çoktan dağılmış oluyor. Oysa
her dilin zaten bir denetleyicisi var (Python'un derleyicisi, `php -l`,
`node --check`); tek eksik, yazma bittiği anda onu koşturup sonucu ARACIN
CEVABINA koymak. Model bir sonraki turda hatayı görür ve düzeltir.

Üç kural bu modülün omurgası:

  1. **Asla hata uydurma.** Bulgular yalnızca gerçek bir denetleyicinin
     çıktısından gelir. Kendi yazdığımız sezgisel tip analizi yok — yanlış
     alarm, hiç bakmamaktan kötüdür: modeli olmayan bir hatayı "düzeltmeye"
     gönderir.
  2. **Asla "her şey yolunda" deme.** Temiz sonuç, "şu denetleyici şunu
     görmedi" demektir. Her denetleyicinin görmediği bir hata sınıfı var
     (`php -l` tip hatası görmez) ve bunu sonucun içinde açıkça yazıyoruz.
  3. **Denetleyici yoksa sus, kurulum önerme.** "kontrol edilemedi" tek
     satırla söylenir; makineyi düzenlemek modelin işi değil.

Denetleyici seçimi uzantıdan yapılır. Tanımadığımız uzantıda `denetle()`
None döner — çağıran hiçbir şey eklemez, gürültü olmaz.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from . import ortam

# Denetleyiciye verilen süre tavanı. Bir yazma sonrası geri besleme bu kadar
# beklerse zaten çok beklemiştir; aşarsa dürüstçe "kontrol edilemedi" denir.
ZAMAN_ASIMI = 20.0

# Ham çıktının modele giden kırpılmış hali.
MAX_HAM = 1500

# Geri beslemede gösterilen en fazla bulgu. Gerisi sayıyla özetlenir:
# ilk hata düzeltilince çoğu zaten kaybolur.
EN_FAZLA_BULGU = 5

# Devasa dosyalar (paketlenmiş bundle, üretilmiş veri) denetlenmez: hem
# yavaş hem de ajanın elle yazdığı bir şey değil.
MAX_BOYUT = 2_000_000


@dataclass(slots=True)
class Bulgu:
    """Tek bir denetleyici bulgusu. `satir` bilinmiyorsa 0."""

    satir: int
    mesaj: str
    dosya: str = ""


@dataclass(slots=True)
class Tani:
    """Bir dosyanın denetim sonucu.

    durum üç değerden biri:
      temiz  denetleyici koştu, bulgu çıkmadı
      hata   denetleyici koştu, bulgu çıktı
      yok    denetleyici koşturulamadı (kurulu değil, zaman aşımı, çöktü)
    """

    dosya: str
    dil: str
    denetleyici: str
    durum: str
    bulgular: list[Bulgu] = field(default_factory=list)
    ham: str = ""
    # Bu denetleyicinin GÖREMEDİĞİ hata sınıfları. Temiz sonucun yanında
    # yazılır ki "kontrol ettim, sağlam" yanılsaması doğmasın.
    kapsam: str = ""
    # durum == "yok" iken: neden koşturulamadı.
    neden: str = ""

    @property
    def hatali(self) -> bool:
        return self.durum == "hata"

    def metin(self) -> str:
        """Araç sonucuna eklenen insan (ve model) okur metin."""
        ad = Path(self.dosya).name
        if self.durum == "yok":
            return f"tanı: {ad} kontrol edilemedi — {self.neden}."

        if self.durum == "temiz":
            son = f"tanı: temiz — {self.denetleyici} bu dosyada hata görmedi."
            if self.kapsam:
                son += f" ({self.kapsam})"
            return son

        satirlar = [f"tanı: {self.denetleyici} {len(self.bulgular)} hata buldu:"]
        for bulgu in self.bulgular[:EN_FAZLA_BULGU]:
            yer = f"satır {bulgu.satir}" if bulgu.satir else "yer belirsiz"
            satirlar.append(f"  {yer}: {bulgu.mesaj}")
        kalan = len(self.bulgular) - EN_FAZLA_BULGU
        if kalan > 0:
            satirlar.append(f"  ... {kalan} bulgu daha.")
        satirlar.append(
            f"Bu hatalar senin az önce yazdığın dosyada ({ad}). "
            "Düzeltmeden devam etme."
        )
        return "\n".join(satirlar)

    def detay(self) -> dict:
        """Arayüzün rozet çizebilmesi için makine okur hali."""
        return {
            "dosya": self.dosya,
            "dil": self.dil,
            "denetleyici": self.denetleyici,
            "durum": self.durum,
            "bulgular": [
                {"satir": b.satir, "mesaj": b.mesaj} for b in self.bulgular
            ],
        }


# -- denetleyici bulma --------------------------------------------------
#
# Windows'ta kurulu araçlar PATH'te olmayabiliyor: winget paketleri kendi
# klasörlerinde, XAMPP/Laragon kendi ağacında duruyor. PATH'e bakıp "yok"
# demek, kurulu bir denetleyiciyi görmezden gelmek olurdu.

_EK_YERLER: dict[str, tuple[str, ...]] = {
    "php": (
        r"~\AppData\Local\Microsoft\WinGet\Packages\PHP.PHP.*\php.exe",
        r"C:\xampp*\php\php.exe",
        r"C:\laragon\bin\php\*\php.exe",
        r"C:\php*\php.exe",
    ),
}


@lru_cache(maxsize=32)
def denetleyici_yolu(ad: str) -> str | None:
    """`ad` adlı çalıştırılabilirin tam yolu; bulunamazsa None.

    Sonuç önbelleklenir — her yazmada diski taramanın anlamı yok. Testler
    `denetleyici_yolu.cache_clear()` ile temizler.
    """
    import shutil

    if yol := shutil.which(ad):
        return yol
    for desen in _EK_YERLER.get(ad, ()):
        genis = Path(desen).expanduser()
        kok = Path(genis.anchor)
        try:
            adaylar = sorted(kok.glob(str(genis.relative_to(kok))))
        except (OSError, ValueError):  # pragma: no cover - bozuk desen/izin
            continue
        for aday in adaylar:
            if aday.is_file():
                return str(aday)
    return None


def _kos(komut: list[str], zaman_asimi: float) -> tuple[int, str] | None:
    """Denetleyiciyi koşturur: (çıkış kodu, çıktı). Bitmezse None.

    Konsol penceresi açtırmayan bayraklarla: neo pythonw altında koşarken
    her denetim ekranda bir cmd penceresi parlatırdı.
    """
    try:
        sonuc = subprocess.run(
            komut,
            capture_output=True,
            timeout=zaman_asimi,
            **ortam.sessiz_bayraklar(),
        )
    except subprocess.TimeoutExpired:
        return None
    ciktilar = (sonuc.stdout or b"") + b"\n" + (sonuc.stderr or b"")
    # Satır sonları tekleştiriliyor: Windows'un \r'si satır sonu deseninin
    # ($) önünde durup satır numarasını okunamaz hale getiriyordu.
    metin = ciktilar.decode("utf-8", errors="replace").replace("\r\n", "\n")
    return sonuc.returncode, metin.replace("\r", "\n").strip()


def _kirp(metin: str, limit: int = MAX_HAM) -> str:
    return metin if len(metin) <= limit else metin[:limit] + "\n... [kırpıldı]"


# -- çıktı ayrıştırıcıları ----------------------------------------------
#
# Ayrı fonksiyonlar: denetleyici makinede kurulu olmasa da ayrıştırma
# sınanabilsin. Kurulu olmayan bir aracın çıktısını doğru okuduğumuzu ancak
# böyle kanıtlayabiliyoruz.

# ruff/pyflakes: "yol:satır:sütun: mesaj" (sütun kimi sürümde yok)
_PYSATIR = re.compile(r"^(?P<dosya>.+?):(?P<satir>\d+)(?::\d+)?: (?P<mesaj>.+)$")

# php -l: "PHP Parse error:  syntax error, ... in DOSYA on line 4"
# "PHP " öneki php.ini'ye bağlı: aynı hata hem önekli (stderr) hem öneksiz
# (stdout) gelebiliyor — ikisini de tanıyıp sonra tekrarları eliyoruz.
_PHPSATIR = re.compile(
    r"^(?:PHP )?(?:Parse|Fatal) error:\s*(?P<mesaj>.*?) in (?P<dosya>.*) "
    r"on line (?P<satir>\d+)"
)

# node --check: ilk satır "DOSYA:SATIR", sonra kod, sonra "SyntaxError: mesaj"
_NODEYER = re.compile(r"^(?P<dosya>.+):(?P<satir>\d+)$", re.MULTILINE)
_NODEMESAJ = re.compile(r"^(?P<mesaj>\w*Error: .+)$", re.MULTILINE)

# tsc: "dosya(12,5): error TS2322: mesaj"
_TSSATIR = re.compile(
    r"^(?P<dosya>.+?)\((?P<satir>\d+),\d+\): error (?P<mesaj>.+)$", re.MULTILINE
)


def _py_bulgulari(cikti: str) -> list[Bulgu]:
    bulgular = []
    for satir in cikti.splitlines():
        if m := _PYSATIR.match(satir.strip()):
            bulgular.append(
                Bulgu(int(m["satir"]), m["mesaj"].strip(), m["dosya"].strip())
            )
    return bulgular


def _php_bulgulari(cikti: str) -> list[Bulgu]:
    bulgular: list[Bulgu] = []
    gorulen: set[tuple[str, int, str]] = set()
    for satir in cikti.splitlines():
        if not (m := _PHPSATIR.match(satir.strip())):
            continue
        bulgu = Bulgu(int(m["satir"]), m["mesaj"].strip(), m["dosya"].strip())
        # Aynı hata önekli ve öneksiz iki kez gelir; modele bir kez gitsin.
        imza = (bulgu.dosya, bulgu.satir, bulgu.mesaj)
        if imza in gorulen:
            continue
        gorulen.add(imza)
        bulgular.append(bulgu)
    return bulgular


def _node_bulgulari(cikti: str) -> list[Bulgu]:
    yer = _NODEYER.search(cikti)
    mesaj = _NODEMESAJ.search(cikti)
    if not mesaj:
        return []
    return [
        Bulgu(
            int(yer["satir"]) if yer else 0,
            mesaj["mesaj"].strip(),
            yer["dosya"].strip() if yer else "",
        )
    ]


def _ts_bulgulari(cikti: str) -> list[Bulgu]:
    return [
        Bulgu(int(m["satir"]), m["mesaj"].strip(), m["dosya"].strip())
        for m in _TSSATIR.finditer(cikti)
    ]


# -- diller -------------------------------------------------------------

UZANTILAR: dict[str, str] = {
    ".py": "python",
    ".pyw": "python",
    ".php": "php",
    ".js": "js",
    ".mjs": "js",
    ".cjs": "js",
    ".ts": "ts",
    ".tsx": "ts",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
}
# .jsx bilerek listede yok: `node --check` JSX sözdizimini tanımaz ve
# sapasağlam bir dosyaya hata uydururdu.


def dil_bul(yol: Path | str) -> str | None:
    """Uzantıdan dil; tanımıyorsak None (= sessizce atla)."""
    return UZANTILAR.get(Path(yol).suffix.lower())


def desteklenir(yol: Path | str) -> bool:
    return dil_bul(yol) is not None


def _python(yol: Path, zaman_asimi: float) -> Tani:
    """Önce derleyici (her zaman var), sonra varsa ruff/pyflakes.

    Derleyici sözdizimini görür; ruff/pyflakes bir adım öteye geçip tanımsız
    isim, kullanılmayan içe aktarma gibi "çalıştırınca patlar" sınıfını da
    yakalar. İkisi de yoksa yine de bir şey demiş oluyoruz — Python'un
    derleyicisi yorumlayıcının kendisiyle gelir.
    """
    kapsam_temel = "çalışma zamanı hataları bu denetimin dışında"
    try:
        kaynak = yol.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return Tani(str(yol), "python", "python derleyicisi", "yok",
                    neden=f"dosya okunamadı ({exc.strerror or exc})")

    try:
        compile(kaynak, str(yol), "exec")
    except SyntaxError as exc:
        return Tani(
            str(yol), "python", "python derleyicisi", "hata",
            bulgular=[Bulgu(exc.lineno or 0, exc.msg or "sözdizimi hatası", str(yol))],
            ham=f"{type(exc).__name__}: {exc}",
        )
    except ValueError as exc:  # kaynakta NUL baytı gibi
        return Tani(
            str(yol), "python", "python derleyicisi", "hata",
            bulgular=[Bulgu(0, str(exc), str(yol))], ham=str(exc),
        )

    # Sözdizimi sağlam. Daha derin bakabilecek bir araç var mı?
    for ad, komut in (
        ("ruff", ["check", "--quiet", "--output-format=concise"]),
        ("pyflakes", []),
    ):
        if (exe := denetleyici_yolu(ad)) is None:
            continue
        sonuc = _kos([exe, *komut, str(yol)], zaman_asimi)
        if sonuc is None:
            break  # zaman aşımı: derleyici sonucuna güven, sessizce dur
        _kod, cikti = sonuc
        bulgular = _py_bulgulari(cikti)
        etiket = f"python derleyicisi + {ad}"
        if bulgular:
            return Tani(str(yol), "python", etiket, "hata",
                        bulgular=bulgular, ham=_kirp(cikti))
        return Tani(str(yol), "python", etiket, "temiz", kapsam=kapsam_temel)

    return Tani(
        str(yol), "python", "python derleyicisi", "temiz",
        kapsam="yalnızca sözdizimi denetlendi; tanımsız isim ve tip hataları "
               "ancak çalıştırınca görünür",
    )


def _php(yol: Path, zaman_asimi: float) -> Tani:
    """`php -l`: sözdizimi ve derleme zamanı ölümcül hataları.

    Kapsamı hakkında dürüst olmak şart: `php -l` TİP hatası görmez. Bildirdiği
    dönüş tipiyle uyuşmayan bir `return` (`: string` deyip nesne döndürmek)
    ondan geçer ve ancak istek geldiğinde TypeError olur. Bunu temiz sonucun
    yanına yazıyoruz ki model "linter geçti" diye rahatlamasın.
    """
    exe = denetleyici_yolu("php")
    if exe is None:
        return Tani(str(yol), "php", "php -l", "yok",
                    neden="php bu makinede bulunamadı")
    # -n: php.ini okunmasın — eksik eklenti uyarıları bulguya karışmasın.
    sonuc = _kos([exe, "-n", "-l", str(yol)], zaman_asimi)
    if sonuc is None:
        return Tani(str(yol), "php", "php -l", "yok",
                    neden=f"php -l {zaman_asimi:.0f} sn'de bitmedi")
    kod, cikti = sonuc
    bulgular = _php_bulgulari(cikti)
    if bulgular:
        return Tani(str(yol), "php", "php -l", "hata",
                    bulgular=bulgular, ham=_kirp(cikti))
    if kod != 0:
        # Çıkış kodu hata diyor ama satırı çözemedik: ham çıktıyı olduğu
        # gibi ver, uydurma yapma.
        return Tani(str(yol), "php", "php -l", "hata",
                    bulgular=[Bulgu(0, cikti.splitlines()[0] if cikti else
                                    f"çıkış kodu {kod}", str(yol))],
                    ham=_kirp(cikti))
    return Tani(str(yol), "php", "php -l", "temiz",
                kapsam="php -l yalnızca sözdizimini görür; tip hataları "
                       "(bildirilen dönüş tipiyle uyuşmayan return) ve "
                       "bulunamayan sınıflar ancak çalıştırınca ortaya çıkar")


def _js(yol: Path, zaman_asimi: float) -> Tani:
    exe = denetleyici_yolu("node")
    if exe is None:
        return Tani(str(yol), "js", "node --check", "yok",
                    neden="node bu makinede bulunamadı")
    sonuc = _kos([exe, "--check", str(yol)], zaman_asimi)
    if sonuc is None:
        return Tani(str(yol), "js", "node --check", "yok",
                    neden=f"node --check {zaman_asimi:.0f} sn'de bitmedi")
    kod, cikti = sonuc
    if kod == 0:
        return Tani(str(yol), "js", "node --check", "temiz",
                    kapsam="yalnızca sözdizimi; tanımsız değişken ve tip "
                           "hataları ancak çalıştırınca görünür")
    bulgular = _node_bulgulari(cikti) or [
        Bulgu(0, cikti.splitlines()[0] if cikti else f"çıkış kodu {kod}", str(yol))
    ]
    return Tani(str(yol), "js", "node --check", "hata",
                bulgular=bulgular, ham=_kirp(cikti))


def _tsconfig(yol: Path) -> Path | None:
    """Dosyanın üstünde bir tsconfig.json var mı? (proje sınırı)"""
    for klasor in [yol.parent, *yol.parent.parents]:
        aday = klasor / "tsconfig.json"
        if aday.is_file():
            return aday
        if (klasor / ".git").exists():
            break
    return None


def _ts(yol: Path, zaman_asimi: float) -> Tani:
    """TypeScript ancak proje bağlamında anlamlı: tsconfig yoksa hiç deneme.

    Tek dosyayı projeden koparıp derlemek, gerçekte olmayan "modül bulunamadı"
    hataları üretirdi — birinci kuralın ihlali.
    """
    if _tsconfig(yol) is None:
        return Tani(str(yol), "ts", "tsc", "yok",
                    neden="tsconfig.json bulunamadı, proje bağlamı olmadan "
                          "TypeScript denetlenemez")
    exe = denetleyici_yolu("npx") or denetleyici_yolu("npx.cmd")
    if exe is None:
        return Tani(str(yol), "ts", "tsc", "yok", neden="npx bulunamadı")
    sonuc = _kos([exe, "--no-install", "tsc", "--noEmit", str(yol)], zaman_asimi)
    if sonuc is None:
        return Tani(str(yol), "ts", "tsc", "yok",
                    neden=f"tsc {zaman_asimi:.0f} sn'de bitmedi")
    kod, cikti = sonuc
    bulgular = _ts_bulgulari(cikti)
    if bulgular:
        return Tani(str(yol), "ts", "tsc", "hata",
                    bulgular=bulgular, ham=_kirp(cikti))
    if kod != 0:
        # tsc kurulu değilse npx --no-install burada patlar: bu bir kod
        # hatası değil, denetleyicinin yokluğu.
        return Tani(str(yol), "ts", "tsc", "yok",
                    neden="tsc çalıştırılamadı (projede kurulu olmayabilir)")
    return Tani(str(yol), "ts", "tsc", "temiz",
                kapsam="tsc çalışma zamanı davranışını değil tipleri denetler")


def _json(yol: Path, zaman_asimi: float) -> Tani:
    try:
        metin = yol.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return Tani(str(yol), "json", "json ayrıştırıcı", "yok",
                    neden=f"dosya okunamadı ({exc})")
    try:
        json.loads(metin)
    except json.JSONDecodeError as exc:
        return Tani(str(yol), "json", "json ayrıştırıcı", "hata",
                    bulgular=[Bulgu(exc.lineno, exc.msg, str(yol))], ham=str(exc))
    return Tani(str(yol), "json", "json ayrıştırıcı", "temiz",
                kapsam="yalnızca biçim; alanların doğruluğu denetlenmedi")


def _yaml(yol: Path, zaman_asimi: float) -> Tani:
    try:
        import yaml  # type: ignore
    except ImportError:
        return Tani(str(yol), "yaml", "yaml ayrıştırıcı", "yok",
                    neden="PyYAML kurulu değil")
    try:
        metin = yol.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return Tani(str(yol), "yaml", "yaml ayrıştırıcı", "yok",
                    neden=f"dosya okunamadı ({exc})")
    try:
        list(yaml.safe_load_all(metin))
    except yaml.YAMLError as exc:
        isaret = getattr(exc, "problem_mark", None)
        mesaj = getattr(exc, "problem", None) or str(exc).splitlines()[0]
        satir = (isaret.line + 1) if isaret is not None else 0
        return Tani(str(yol), "yaml", "yaml ayrıştırıcı", "hata",
                    bulgular=[Bulgu(satir, mesaj, str(yol))], ham=_kirp(str(exc)))
    return Tani(str(yol), "yaml", "yaml ayrıştırıcı", "temiz",
                kapsam="yalnızca biçim; alanların doğruluğu denetlenmedi")


_DENETLEYICILER = {
    "python": _python,
    "php": _php,
    "js": _js,
    "ts": _ts,
    "json": _json,
    "yaml": _yaml,
}


def denetle(yol: Path | str, *, zaman_asimi: float = ZAMAN_ASIMI) -> Tani | None:
    """Tek dosyayı denetler. Dil tanınmıyorsa None — çağıran hiçbir şey demez.

    Bloklayıcıdır (alt süreç çalıştırır); asenkron çağıranlar
    `asyncio.to_thread` ile sarmalı.
    """
    yol = Path(yol)
    dil = dil_bul(yol)
    if dil is None:
        return None
    try:
        if not yol.is_file():
            return None
        if yol.stat().st_size > MAX_BOYUT:
            return Tani(str(yol), dil, "-", "yok",
                        neden="dosya denetim için fazla büyük")
    except OSError:
        return None

    try:
        return _DENETLEYICILER[dil](yol, zaman_asimi)
    except Exception as exc:  # denetleyici çöktü: sahte bulgu üretme
        return Tani(str(yol), dil, "-", "yok",
                    neden=f"denetleyici çalıştırılamadı ({type(exc).__name__})",
                    ham=_kirp(str(exc)))


def denetle_coklu(
    yollar: list[Path], *, zaman_asimi: float = ZAMAN_ASIMI
) -> list[Tani]:
    """Birden çok dosya; desteklenmeyenler listeden düşer."""
    sonuclar = []
    for yol in yollar:
        if (tani := denetle(yol, zaman_asimi=zaman_asimi)) is not None:
            sonuclar.append(tani)
    return sonuclar


def ozet(taniler: list[Tani], *, kok: Path | None = None) -> str:
    """Çok dosyalı denetimin özeti — `denetle` aracının cevabı.

    Önce hatalılar (asıl mesele onlar), sonra tek satırlık sayım. "Hepsi
    temiz" demiyoruz: hangi denetleyicinin baktığı yazıyor.
    """
    if not taniler:
        return ("Denetlenecek dosya bulunamadı. Tanınan uzantılar: "
                + ", ".join(sorted(UZANTILAR)) + ".")

    def ad(t: Tani) -> str:
        if kok is None:
            return Path(t.dosya).name
        try:
            return str(Path(t.dosya).relative_to(kok))
        except ValueError:
            return t.dosya

    hatali = [t for t in taniler if t.durum == "hata"]
    temiz = [t for t in taniler if t.durum == "temiz"]
    bakilamayan = [t for t in taniler if t.durum == "yok"]

    satirlar: list[str] = []
    for tani in hatali:
        satirlar.append(f"{ad(tani)} — {tani.denetleyici}, {len(tani.bulgular)} hata:")
        for bulgu in tani.bulgular[:EN_FAZLA_BULGU]:
            yer = f"satır {bulgu.satir}" if bulgu.satir else "yer belirsiz"
            satirlar.append(f"  {yer}: {bulgu.mesaj}")
        kalan = len(tani.bulgular) - EN_FAZLA_BULGU
        if kalan > 0:
            satirlar.append(f"  ... {kalan} bulgu daha.")

    if temiz:
        araclar = sorted({t.denetleyici for t in temiz})
        satirlar.append(
            f"{len(temiz)} dosyada bulgu yok ({', '.join(araclar)} baktı). "
            "Bu, kodun çalıştığı anlamına gelmez — denetleyiciler çoğunlukla "
            "sözdizimine bakar."
        )
    for tani in bakilamayan:
        satirlar.append(f"{ad(tani)} kontrol edilemedi — {tani.neden}.")

    if hatali:
        satirlar.append("Hataları düzeltmeden devam etme.")
    return "\n".join(satirlar)


def toplu_yollar(kok: Path, *, desen: str | None = None, tavan: int = 60) -> list[Path]:
    """Bir klasörün altındaki denetlenebilir dosyalar.

    Bağımlılık ve üretilmiş çıktı klasörleri atlanır: `node_modules` içindeki
    on bin dosyayı denetlemek ne kullanıcının istediği ne de ajanın yazdığı.
    """
    atla = {"node_modules", "vendor", ".git", "__pycache__", ".venv", "venv",
            "dist", "build", ".next", "writable"}
    bulunan: list[Path] = []
    for temel, klasorler, dosyalar in os.walk(kok):
        klasorler[:] = [k for k in klasorler if k not in atla and not k.startswith(".")]
        for dosya in sorted(dosyalar):
            yol = Path(temel) / dosya
            if not desteklenir(yol):
                continue
            if desen and not yol.match(desen):
                continue
            bulunan.append(yol)
            if len(bulunan) >= tavan:
                return bulunan
    return bulunan
