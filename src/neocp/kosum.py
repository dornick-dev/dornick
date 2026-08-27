"""Proje test koşucusu: yazılan kodu gerçekten ÇALIŞTIR.

Neden var: `tanilar` bir adım attı — yazılan dosya, yazıldığı anda dilinin
kendi denetleyicisinden geçiyor. Ama denetleyicilerin tavanı sözdizimi.
Kanıtlanmış yara şu satırdı:

    public function index(): string { return redirect(); }

`php -l` bunu sapasağlam bulur; tarayıcıda TypeError olur. Sözdizimi doğru,
davranış yanlış. Bu sınıfı görmenin tek yolu kodu koşturmak — ve çoğu
projede koşturma düzeneği ZATEN var: pytest, phpunit, npm test, go test.
Ajan onu bulup kullanmıyordu.

Bu modül üç iş yapar ve üçünde de aynı ilkeye bağlıdır — **kanıt olmadan
komut üretme**:

  1. TESPİT: bir klasöre bakar, orada gerçekten bulunan dosyalardan test
     komutunu çıkarır. `pytest.ini` yoksa pytest önerilmez; `package.json`
     içinde `scripts.test` yoksa `npm test` uydurulmaz. Hiçbir kanıt yoksa
     cevap "test düzeneği bulunamadı" — tahmin edilmiş bir komut, olmayan
     bir güvenceden beterdir: model onu koşturur, patlar, ve neden
     patladığını sanır.
  2. NORMALLEŞTİRME: her koşucunun çıktısı başka bir dilde konuşuyor.
     Ortak bir çerçeveye indiriyoruz: geçen / kalan / atlanan, ilk beş
     başarısızın adı + mesajı + dosya:satır, çıkış kodu, süre. Ham çıktı
     baş+son kırpılıyor — ortadaki yığın izleri modele bir şey öğretmiyor.
  3. DÜRÜSTLÜK: sonuç metni asla "her şey çalışıyor" demez. "12 test geçti,
     0 kaldı — bu, koşulan testlerin kapsadığı kadarını doğrular" der. Test
     yoksa "test yok; doğrulama için uygulamayı gerçekten çalıştır" der.

Ayrıca `hatirlatma()`: dosya yazıldıktan sonra tek satırlık bir not. Test
koşmak PAHALI (saniyeler, bazen dakikalar) — her yazımda kendiliğinden
koşturmak turu dondurur ve kullanıcıyı bekletir. Onun yerine modele
düzeneğin VARLIĞI bildiriliyor; koşturup koşturmamaya o karar veriyor.
Bilgi bedava, koşum pahalı.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import ortam, tanilar

# Test koşumuna verilen varsayılan süre. Bir tanı 20 saniyeyle sınırlıydı;
# test takımı ondan uzun sürer ama sonsuz da değildir. Model `zaman_asimi`
# ile değiştirebilir, tavan bellidir: hiç bitmeyen bir komut turu dondurur.
VARSAYILAN_ZAMAN_ASIMI = 300.0
MAX_ZAMAN_ASIMI = 1800.0

# Modele giden ham çıktının tavanı. Baş ve son korunuyor: koşucular başta
# ne koştuklarını, sonda özeti yazar; ortadaki yığın izleri düzeltmeye
# yaramıyor.
MAX_HAM = 4000

# Sonuçta adı geçen en fazla başarısız test. Gerisi sayıyla özetlenir —
# ilki düzeltilince çoğu zaman kalanlar da düşer.
EN_FAZLA_BASARISIZ = 5

# Proje kökü ararken yukarı doğru en fazla kaç kat çıkılır. Dipsiz bir
# tarama, kullanıcının ev klasörünü "proje" ilan edebilirdi.
MAX_YUKARI = 8


# -- veri tipleri -------------------------------------------------------


@dataclass(slots=True)
class Duzenek:
    """Bir klasörde BULUNAN test/çalıştırma düzeneği.

    `argv` mantıksal adlarla kurulur ("py", "php", "npm"); gerçek yol
    koşum anında çözülür. Böylece tespit saf kalır ve makinede o araç
    kurulu olmasa da sınanabilir.
    """

    ekosistem: str          # python | node | php | go | rust | dotnet
    tur: str                # "test" (gerçek takım) | "saglik" (ucuz denetim)
    etiket: str             # insan/model okur hali: "py -m pytest -q"
    argv: list[str]
    kok: Path
    kanit: str              # hangi dosya bunu kanıtladı
    # 2 = açık test yapılandırması, 1 = zayıf kanıt (yalnız tests/ klasörü,
    # sağlık komutu). Sıralamada kullanılıyor.
    guven: int = 2
    notlar: list[str] = field(default_factory=list)
    # Boş değilse: düzenek var ama koşulamaz (bağımlılık kurulu değil gibi).
    # Kurulum ÖNERMİYORUZ; yalnızca durumu bildiriyoruz.
    engel: str = ""

    @property
    def kosulabilir(self) -> bool:
        return not self.engel


@dataclass(slots=True)
class Basarisiz:
    """Tek bir başarısız test: adı, mesajı, yeri."""

    ad: str
    mesaj: str = ""
    yer: str = ""   # "dosya:satır" — çıkarılabildiyse

    def metin(self) -> str:
        parcalar = [self.ad]
        if self.yer:
            parcalar.append(f"({self.yer})")
        satir = " ".join(parcalar)
        return f"{satir}: {self.mesaj}" if self.mesaj else satir


@dataclass(slots=True)
class Sayim:
    """Koşucudan okunan sayılar. `okundu` False ise hiçbiri güvenilir değil."""

    gecen: int = 0
    kalan: int = 0
    atlanan: int = 0
    toplam: int = 0
    okundu: bool = False


@dataclass(slots=True)
class Sonuc:
    """Bir koşumun normalleştirilmiş sonucu."""

    ekosistem: str
    etiket: str
    kok: str
    durum: str              # kostu | zaman_asimi | baslatilamadi | yok
    cikis_kodu: int = 0
    sure: float = 0.0
    sayim: Sayim = field(default_factory=Sayim)
    basarisizlar: list[Basarisiz] = field(default_factory=list)
    ham: str = ""
    notlar: list[str] = field(default_factory=list)
    tur: str = "test"

    @property
    def basarili(self) -> bool:
        return self.durum == "kostu" and self.cikis_kodu == 0

    def metin(self) -> str:
        """Modele giden metin.

        Üç kural: (1) sayılar varsa önce onlar, (2) başarısızlar adıyla
        sanıyla, (3) kapanış cümlesi asla "her şey çalışıyor" demez.
        """
        if self.durum == "kesildi":
            return (
                f"Durduruldu — {self.etiket} ve altındaki süreçler "
                f"sonlandırıldı ({self.sure:.0f} sn sonra).\n\n"
                + (self.ham or "(çıktı yok)")
            )
        if self.durum == "zaman_asimi":
            return (
                f"{self.etiket} {self.sure:.0f} saniyede bitmedi ve durduruldu. "
                "Takım gerçekten uzunsa `zaman_asimi` değerini artır; bir test "
                "asılı kalıyorsa asıl mesele o — aşağıdaki yarım çıktının son "
                "satırı çoğu zaman nerede takıldığını söyler.\n\n"
                + (self.ham or "(çıktı yok)")
            )
        if self.durum == "baslatilamadi":
            return f"{self.etiket} başlatılamadı — {self.ham}"

        basliklar = [f"{self.etiket} koştu · çıkış kodu {self.cikis_kodu} · "
                     f"{self.sure:.1f} sn"]
        s = self.sayim
        if s.okundu:
            parcalar = [f"{s.gecen} geçti", f"{s.kalan} kaldı"]
            if s.atlanan:
                parcalar.append(f"{s.atlanan} atlandı")
            basliklar.append(", ".join(parcalar) + ".")
        else:
            basliklar.append(
                "Çıktıdan test sayısı çıkarılamadı — aşağıdaki ham çıktıya bak."
            )

        satirlar = [" ".join(basliklar)]

        if self.basarisizlar:
            satirlar.append("")
            satirlar.append("Başarısız olanlar:")
            for b in self.basarisizlar[:EN_FAZLA_BASARISIZ]:
                satirlar.append(f"  {b.metin()}")
            kalan = len(self.basarisizlar) - EN_FAZLA_BASARISIZ
            if kalan > 0:
                satirlar.append(f"  ... {kalan} başarısız test daha.")

        satirlar.append("")
        satirlar.append(self._kapanis())

        for not_ in self.notlar:
            satirlar.append(not_)

        if self.ham:
            satirlar.append("")
            satirlar.append("Ham çıktı:")
            satirlar.append(self.ham)
        return "\n".join(satirlar)

    def _kapanis(self) -> str:
        """Sonucun ne KADAR şey kanıtladığını söyleyen cümle.

        Buradaki her kelime bilinçli. "Testler geçti" demek, modele
        olmayan bir güvence verir; o güvenceyle kullanıcıya "hazır" der ve
        hata kullanıcının tarayıcısında patlar.
        """
        if self.tur == "saglik":
            if self.cikis_kodu == 0:
                return ("Bu bir test takımı değil, ucuz bir sağlık denetimi: "
                        "uygulama ayağa kalkıyor ve bu komutu cevaplıyor. "
                        "Davranışın doğruluğunu göstermez.")
            return ("Sağlık denetimi başarısız — uygulama bu komutu bile "
                    "cevaplayamadı. Testlerden önce bunu çöz.")

        s = self.sayim
        if self.cikis_kodu != 0 or s.kalan or self.basarisizlar:
            return ("Bu hatalar senin dokunduğun projede. Düzeltmeden "
                    "'çalışıyor' deme.")
        if s.okundu and s.toplam == 0:
            return ("Hiç test koşmadı — düzenek var ama içi boş. Bu koşum "
                    "hiçbir şey doğrulamıyor; doğrulama için uygulamayı "
                    "gerçekten çalıştır.")
        if s.okundu:
            return (f"{s.gecen} test geçti, 0 kaldı — bu, koşulan testlerin "
                    "kapsadığı kadarını doğrular. Testlerin dokunmadığı yollar "
                    "hâlâ denenmemiş durumda.")
        return ("Komut sıfır çıkış koduyla bitti. Test sayısı okunamadığı "
                "için ne kadarının doğrulandığı belli değil — ham çıktıya bak.")

    def detay(self) -> dict:
        """Arayüzün rozet çizebilmesi için makine okur hali."""
        return {
            "ekosistem": self.ekosistem,
            "komut": self.etiket,
            "kok": self.kok,
            "durum": self.durum,
            "cikis_kodu": self.cikis_kodu,
            "sure": round(self.sure, 2),
            "gecen": self.sayim.gecen,
            "kalan": self.sayim.kalan,
            "atlanan": self.sayim.atlanan,
            "okundu": self.sayim.okundu,
            "basarisizlar": [
                {"ad": b.ad, "mesaj": b.mesaj, "yer": b.yer}
                for b in self.basarisizlar[:EN_FAZLA_BASARISIZ]
            ],
        }


# -- proje kökü ---------------------------------------------------------

# Bir klasörü "proje" yapan izler. Sıra önemsiz; varlıkları yeter.
KOK_IZLERI = (
    ".git", "pyproject.toml", "package.json", "composer.json", "go.mod",
    "Cargo.toml", "pytest.ini", "setup.py", "phpunit.xml", "phpunit.xml.dist",
    "phpunit.dist.xml", "spark",
)


def proje_koku(yol: Path | str) -> Path:
    """Verilen yoldan yukarı doğru en yakın proje kökü.

    Model çoğu zaman elindeki tek somut şeyi verir: az önce yazdığı dosyanın
    yolu. `app/Controllers/Home.php` bir proje değil; kökü bulmak bizim
    işimiz. Hiçbir iz yoksa başlangıç klasörü aynen dönüyor — uydurma bir
    üst klasöre tırmanmıyoruz.
    """
    yol = Path(yol).expanduser()
    baslangic = yol if yol.is_dir() else yol.parent
    aday = baslangic
    for _ in range(MAX_YUKARI):
        try:
            if any((aday / iz).exists() for iz in KOK_IZLERI):
                return aday
        except OSError:  # pragma: no cover - erişilemeyen klasör
            break
        if aday.parent == aday:
            break
        aday = aday.parent
    return baslangic


# -- tespit -------------------------------------------------------------


def _python(kok: Path) -> Duzenek | None:
    """pytest düzeneği var mı? Kanıt sırasıyla: yapılandırma, sonra tests/.

    Yapılandırma açık bir beyandır ("bu projede pytest kullanılıyor").
    `tests/` klasörü daha zayıf bir kanıt: içinde `test_*.py` bulunmadıkça
    saymıyoruz — belge, sabit veri ya da elle çalıştırılan betikler de
    `tests/` altında durabiliyor.
    """
    ad, etiket_exe = ("py", "py") if sys.platform == "win32" else ("python3", "python3")
    argv = [ad, "-m", "pytest", "-q"]
    etiket = f"{etiket_exe} -m pytest -q"

    if (kok / "pytest.ini").is_file():
        return Duzenek("python", "test", etiket, argv, kok, "pytest.ini", 2)

    tomlyol = kok / "pyproject.toml"
    if tomlyol.is_file():
        try:
            metin = tomlyol.read_text(encoding="utf-8", errors="replace")
        except OSError:
            metin = ""
        if "[tool.pytest" in metin:
            return Duzenek("python", "test", etiket, argv, kok,
                           "pyproject.toml [tool.pytest]", 2)

    for dosya, damga in (("setup.cfg", "[tool:pytest]"), ("tox.ini", "[pytest]")):
        aday = kok / dosya
        if aday.is_file():
            try:
                if damga in aday.read_text(encoding="utf-8", errors="replace"):
                    return Duzenek("python", "test", etiket, argv, kok,
                                   f"{dosya} {damga}", 2)
            except OSError:  # pragma: no cover
                pass

    for klasor in ("tests", "test"):
        dizin = kok / klasor
        if not dizin.is_dir():
            continue
        try:
            varmi = any(
                p.name.startswith("test_") or p.name.endswith("_test.py")
                for p in dizin.iterdir() if p.suffix == ".py"
            )
        except OSError:  # pragma: no cover
            continue
        if varmi:
            return Duzenek("python", "test", etiket, argv, kok,
                           f"{klasor}/ altında test_*.py", 1)
    return None


# npm'in `npm init` ile ürettiği yer tutucu betik. Bunu "test düzeneği" saymak,
# olmayan bir güvence uydurmak olurdu — komut zaten kasten 1 ile çıkıyor.
_NPM_YERTUTUCU = "no test specified"


def _node(kok: Path) -> Duzenek | None:
    """package.json'daki `scripts.test`. Yoksa düzenek de yok.

    `scripts.build` ve `scripts.dev` de okunuyor ama komut olarak
    önerilmiyor: not olarak geçiliyor, çünkü model bunları bilmeden
    "projeyi nasıl derlerim" diye kabukta el yordamıyla dolaşıyordu.
    """
    paket = kok / "package.json"
    if not paket.is_file():
        return None
    try:
        veri = json.loads(paket.read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError):
        return None
    if not isinstance(veri, dict):
        return None
    betikler = veri.get("scripts")
    if not isinstance(betikler, dict):
        betikler = {}

    notlar: list[str] = []
    digerleri = [ad for ad in ("build", "dev", "start", "lint")
                 if isinstance(betikler.get(ad), str)]
    if digerleri:
        notlar.append("package.json'daki diğer betikler: " + ", ".join(digerleri) + ".")

    test = betikler.get("test")
    if not isinstance(test, str) or not test.strip():
        return None
    if _NPM_YERTUTUCU in test:
        return None

    engel = ""
    if not (kok / "node_modules").is_dir():
        # Yalnızca BİLDİRİYORUZ. "npm install çalıştır" demek makineyi
        # düzenlemektir ve modelin işi değil.
        engel = ("node_modules klasörü yok — bağımlılıklar bu makinede kurulu "
                 "değil, `npm test` çalışmaz.")
    return Duzenek("node", "test", "npm test", ["npm", "test"], kok,
                   f"package.json scripts.test = {test.strip()[:60]}", 2,
                   notlar, engel)


_PHPUNIT_YAPILANDIRMA = ("phpunit.xml", "phpunit.xml.dist", "phpunit.dist.xml")


def _phpunit_ikili(kok: Path) -> str | None:
    """vendor/bin/phpunit — Windows'ta .bat kardeşi de olabilir."""
    for ad in ("vendor/bin/phpunit", "vendor/bin/phpunit.bat"):
        if (kok / ad).is_file():
            return "vendor/bin/phpunit"
    return None


def _php(kok: Path) -> Duzenek | None:
    """phpunit; yoksa CodeIgniter 4 projesinde ucuz bir sağlık komutu.

    `php spark routes` test değildir ve öyle sunulmuyor: uygulamayı ayağa
    kaldırır, yapılandırmayı okur, rotaları basar. Bir CI4 projesinde
    bozuk bir `Config`, eksik bir sınıf ya da sözdizimi kazası bu komutu
    düşürür — yani sıfır maliyetli, gerçek bir kanıt. Testin yerini
    tutmadığını sonucun kapanış cümlesi açıkça söylüyor.
    """
    yapilandirma = next(
        (ad for ad in _PHPUNIT_YAPILANDIRMA if (kok / ad).is_file()), None
    )
    ikili = _phpunit_ikili(kok)

    if yapilandirma or ikili:
        kanit = yapilandirma or "vendor/bin/phpunit"
        engel = ""
        if ikili is None:
            engel = (f"{yapilandirma} var ama vendor/bin/phpunit yok — composer "
                     "bağımlılıkları bu makinede kurulu değil.")
        return Duzenek("php", "test", "php vendor/bin/phpunit",
                       ["php", "vendor/bin/phpunit"], kok, kanit, 2,
                       [], engel)

    if (kok / "spark").is_file():
        return Duzenek("php", "saglik", "php spark routes",
                       ["php", "spark", "routes"], kok, "spark (CodeIgniter 4)", 1,
                       ["Bu bir test takımı değil; phpunit yapılandırması "
                        "bulunamadı."])
    return None


def _go(kok: Path) -> Duzenek | None:
    if not (kok / "go.mod").is_file():
        return None
    return Duzenek("go", "test", "go test ./...",
                   ["go", "test", "./..."], kok, "go.mod", 2)


def _rust(kok: Path) -> Duzenek | None:
    if not (kok / "Cargo.toml").is_file():
        return None
    return Duzenek("rust", "test", "cargo test",
                   ["cargo", "test"], kok, "Cargo.toml", 2)


def _dotnet(kok: Path) -> Duzenek | None:
    """.sln ya da .csproj kanıtı. Kök klasörde aranıyor, ağaç taranmıyor."""
    try:
        aday = next(
            (p for p in sorted(kok.iterdir())
             if p.suffix in (".sln", ".csproj", ".fsproj")), None
        )
    except OSError:  # pragma: no cover
        return None
    if aday is None:
        return None
    return Duzenek("dotnet", "test", "dotnet test",
                   ["dotnet", "test"], kok, aday.name, 2)


_TESPITCILER = (_python, _php, _node, _go, _rust, _dotnet)


def tespit_hepsi(kok: Path | str) -> list[Duzenek]:
    """Klasörde bulunan TÜM düzenekler, güvene göre sıralı.

    Tek proje birden çok ekosistem taşıyabiliyor (PHP arka uç + npm ile
    derlenen ön yüz). Hepsini görüp birini seçmek, ilkine takılıp kalmaktan
    iyi.
    """
    kok = Path(kok).expanduser()
    if not kok.is_dir():
        return []
    bulunan: list[Duzenek] = []
    for bul in _TESPITCILER:
        try:
            if (duzenek := bul(kok)) is not None:
                bulunan.append(duzenek)
        except OSError:  # pragma: no cover - erişilemeyen dosya tespiti durdurmaz
            continue
    bulunan.sort(key=lambda d: (-d.guven, d.tur != "test"))
    return bulunan


def tespit(kok: Path | str) -> Duzenek | None:
    """En güçlü kanıta sahip düzenek; hiçbiri yoksa None."""
    hepsi = tespit_hepsi(kok)
    return hepsi[0] if hepsi else None


def tespit_metni(kok: Path) -> str:
    """Düzenek bulunamadığında söylenen şey. Uydurma komut YOK."""
    return (
        f"{kok} altında test düzeneği bulunamadı — ne pytest yapılandırması, "
        "ne package.json'da `scripts.test`, ne phpunit, ne go.mod/Cargo.toml. "
        "Sana bir komut uydurmayacağım. Bu değişikliği doğrulamak istiyorsan "
        "uygulamayı gerçekten çalıştır (sayfayı aç, betiği koştur) ve çıktısına bak."
    )


# -- çıktı normalleştirme ----------------------------------------------
#
# Ayrı, saf fonksiyonlar: koşucu bu makinede kurulu olmasa da ayrıştırmanın
# doğruluğu sınanabilsin. `tanilar`daki ayrıştırıcılarla aynı gerekçe —
# gerçek çıktı metinlerini teste gömüp öyle doğruluyoruz.

_TEMIZ = re.compile(r"^[=\-_\s]+|[=\-_\s]+$")


def _sat(metin: str) -> list[str]:
    return metin.replace("\r\n", "\n").replace("\r", "\n").split("\n")


# pytest -q son satırı: "1 failed, 6 passed in 0.42s" (kalın kipte `=` ile
# çevrili gelir; iki biçimi de tanıyoruz).
_PYTEST_OZET = re.compile(r"\b(\d+)\s+(passed|failed|errors?|skipped|xfailed|"
                          r"xpassed|deselected)\b")
_PYTEST_SURE = re.compile(r"\bin\s+[\d.]+\s*s(econds)?\b")
_PYTEST_HATA = re.compile(r"^(FAILED|ERROR)\s+(?P<ad>\S+?)(?:\s+-\s+(?P<mesaj>.*))?$")
# FAILURES bölümündeki başlık: "____________ test_falan ____________"
_PYTEST_BASLIK = re.compile(r"^_{3,}\s+(?P<ad>.+?)\s+_{3,}$")
_PYTEST_YER = re.compile(r"^(?P<dosya>[A-Za-z]?[^\s:]*\.py):(?P<satir>\d+):\s")


def _pytest_yerleri(cikti: str) -> dict[str, str]:
    """FAILURES bloklarından test adı → "dosya:satır" eşlemesi.

    Blok başlığı testin adını, blok içindeki son `dosya.py:12:` satırı da
    hatanın patladığı yeri veriyor. Bulamazsak boş bırakıyoruz — yer
    uydurmak, yanlış dosyayı açtırmak demek.
    """
    yerler: dict[str, str] = {}
    ad: str | None = None
    for satir in _sat(cikti):
        if m := _PYTEST_BASLIK.match(satir.strip()):
            ad = m["ad"].strip()
            continue
        if ad and (m := _PYTEST_YER.match(satir.strip())):
            yerler[ad] = f"{m['dosya']}:{m['satir']}"
    return yerler


def _oku_pytest(cikti: str) -> tuple[Sayim, list[Basarisiz]]:
    sayim = Sayim()
    for satir in reversed(_sat(cikti)):
        duz = _TEMIZ.sub("", satir).strip()
        if not duz or not _PYTEST_SURE.search(duz):
            continue
        parcalar = _PYTEST_OZET.findall(duz)
        if not parcalar:
            if "no tests ran" in duz:
                sayim.okundu = True
            break
        for sayi, tur in parcalar:
            n = int(sayi)
            if tur == "passed":
                sayim.gecen += n
            elif tur in ("failed", "error", "errors"):
                sayim.kalan += n
            elif tur in ("skipped", "deselected"):
                sayim.atlanan += n
            elif tur == "xfailed":
                sayim.atlanan += n
            elif tur == "xpassed":
                sayim.gecen += n
        sayim.okundu = True
        break
    sayim.toplam = sayim.gecen + sayim.kalan + sayim.atlanan

    yerler = _pytest_yerleri(cikti)
    basarisizlar: list[Basarisiz] = []
    for satir in _sat(cikti):
        if not (m := _PYTEST_HATA.match(satir.strip())):
            continue
        ad = m["ad"]
        kisa = ad.rsplit("::", 1)[-1]
        dosya = ad.split("::", 1)[0]
        basarisizlar.append(
            Basarisiz(ad, (m["mesaj"] or "").strip(), yerler.get(kisa, dosya))
        )
    return sayim, basarisizlar


# phpunit kapanışı iki biçimde gelir:
#   OK (5 tests, 7 assertions)
#   Tests: 5, Assertions: 7, Errors: 1, Failures: 2, Skipped: 1.
_PHPUNIT_OK = re.compile(r"^OK\s*\((?P<tests>\d+) tests?", re.M)
_PHPUNIT_OZET = re.compile(r"^Tests:\s*(?P<tests>\d+)(?P<kuyruk>.*)$", re.M)
_PHPUNIT_PARCA = re.compile(r"\b(Failures|Errors|Skipped|Incomplete|Risky):\s*(\d+)")
# "1) App\Tests\FooTest::testBar"
_PHPUNIT_BASLIK = re.compile(r"^(?P<no>\d+)\)\s+(?P<ad>\S+::\S+|\S+)\s*$")
_PHPUNIT_YER = re.compile(r"^(?P<dosya>.+\.php):(?P<satir>\d+)\s*$")


def _oku_phpunit(cikti: str) -> tuple[Sayim, list[Basarisiz]]:
    sayim = Sayim()
    if m := _PHPUNIT_OK.search(cikti):
        sayim.gecen = int(m["tests"])
        sayim.toplam = sayim.gecen
        sayim.okundu = True
    elif m := _PHPUNIT_OZET.search(cikti):
        sayim.toplam = int(m["tests"])
        sayilar = {ad: int(deger)
                   for ad, deger in _PHPUNIT_PARCA.findall(m["kuyruk"])}
        sayim.kalan = sayilar.get("Failures", 0) + sayilar.get("Errors", 0)
        sayim.atlanan = (sayilar.get("Skipped", 0) + sayilar.get("Incomplete", 0)
                         + sayilar.get("Risky", 0))
        sayim.gecen = max(0, sayim.toplam - sayim.kalan - sayim.atlanan)
        sayim.okundu = True
    elif "No tests executed" in cikti:
        sayim.okundu = True

    basarisizlar: list[Basarisiz] = []
    ad: str | None = None
    mesajlar: list[str] = []
    yer = ""

    def kapat() -> None:
        if ad is not None:
            basarisizlar.append(
                Basarisiz(ad, " ".join(mesajlar).strip()[:300], yer))

    for ham in _sat(cikti):
        satir = ham.strip()
        if m := _PHPUNIT_BASLIK.match(satir):
            kapat()
            ad, mesajlar, yer = m["ad"], [], ""
            continue
        if ad is None:
            continue
        if m := _PHPUNIT_YER.match(satir):
            yer = f"{Path(m['dosya']).name}:{m['satir']}"
            continue
        if satir.startswith(("FAILURES!", "ERRORS!", "OK ", "Tests:")):
            kapat()
            ad = None
            continue
        if satir:
            mesajlar.append(satir)
    kapat()
    return sayim, basarisizlar


# jest / vitest / mocha / node --test — `npm test` arkasında hangisinin
# durduğunu bilmiyoruz, o yüzden sırayla deniyoruz.
_JEST_OZET = re.compile(r"^Tests:\s+(?P<govde>.+)$", re.M)
_JEST_PARCA = re.compile(r"(\d+)\s+(failed|passed|skipped|todo|total|pending)")
_JEST_HATA = re.compile(r"^\s*●\s+(?P<ad>.+?)\s*$", re.M)
_VITEST_OZET = re.compile(r"^\s*Tests\s+(?P<govde>.*?\(\d+\))\s*$", re.M)
_VITEST_PARCA = re.compile(r"(\d+)\s+(failed|passed|skipped|todo)")
_MOCHA_GECEN = re.compile(r"^\s*(\d+)\s+passing\b", re.M)
_MOCHA_KALAN = re.compile(r"^\s*(\d+)\s+failing\b", re.M)
_MOCHA_ATLANAN = re.compile(r"^\s*(\d+)\s+pending\b", re.M)
_NODETEST = re.compile(r"^#\s*(pass|fail|skipped|tests)\s+(\d+)\s*$", re.M)
# mocha başarısızlığı iki satıra yayılır:
#   1) Hesap makinesi
#        toplar:
#      AssertionError: expected 3 to equal 4
_MOCHA_BASLIK = re.compile(r"^\s*\d+\)\s+(?P<ad>.+?)\s*$")


def _mocha_basarisizlar(cikti: str) -> list[Basarisiz]:
    """Mocha'nın iki satıra yayılan başarısızlık başlıklarını birleştirir."""
    satirlar = _sat(cikti)
    bulunan: list[Basarisiz] = []
    for i, satir in enumerate(satirlar):
        if not (m := _MOCHA_BASLIK.match(satir)):
            continue
        ad = m["ad"].strip()
        mesaj = ""
        for sonraki in satirlar[i + 1: i + 5]:
            duz = sonraki.strip()
            if not duz:
                continue
            if duz.endswith(":") and not ad.endswith(":"):
                ad = f"{ad} › {duz.rstrip(':')}"
                continue
            mesaj = duz[:200]
            break
        bulunan.append(Basarisiz(ad, mesaj))
    return bulunan


def _oku_node(cikti: str) -> tuple[Sayim, list[Basarisiz]]:
    sayim = Sayim()
    basarisizlar: list[Basarisiz] = []

    if m := _JEST_OZET.search(cikti):
        for sayi, tur in _JEST_PARCA.findall(m["govde"]):
            n = int(sayi)
            if tur == "passed":
                sayim.gecen = n
            elif tur == "failed":
                sayim.kalan = n
            elif tur in ("skipped", "todo", "pending"):
                sayim.atlanan += n
            elif tur == "total":
                sayim.toplam = n
        sayim.okundu = True
        basarisizlar = [Basarisiz(a.strip()) for a in _JEST_HATA.findall(cikti)]
    elif m := _VITEST_OZET.search(cikti):
        for sayi, tur in _VITEST_PARCA.findall(m["govde"]):
            n = int(sayi)
            if tur == "passed":
                sayim.gecen = n
            elif tur == "failed":
                sayim.kalan = n
            else:
                sayim.atlanan += n
        sayim.okundu = True
    elif (gecen := _MOCHA_GECEN.search(cikti)) or (
            kalan := _MOCHA_KALAN.search(cikti)):
        atlanan = _MOCHA_ATLANAN.search(cikti)
        kalan = _MOCHA_KALAN.search(cikti)
        sayim.gecen = int(gecen.group(1)) if gecen else 0
        sayim.kalan = int(kalan.group(1)) if kalan else 0
        sayim.atlanan = int(atlanan.group(1)) if atlanan else 0
        sayim.okundu = True
        basarisizlar = _mocha_basarisizlar(cikti)
    elif parcalar := _NODETEST.findall(cikti):
        veri = {tur: int(sayi) for tur, sayi in parcalar}
        sayim.gecen = veri.get("pass", 0)
        sayim.kalan = veri.get("fail", 0)
        sayim.atlanan = veri.get("skipped", 0)
        sayim.toplam = veri.get("tests", 0)
        sayim.okundu = True

    if not sayim.toplam:
        sayim.toplam = sayim.gecen + sayim.kalan + sayim.atlanan
    return sayim, basarisizlar


# go test: `-v` olmadan tek tek test adı basılmaz; sayıyı uydurmuyoruz.
_GO_FAIL = re.compile(r"^\s*--- FAIL:\s+(?P<ad>\S+)", re.M)
_GO_PASS = re.compile(r"^\s*--- PASS:\s+\S+", re.M)
_GO_PAKET = re.compile(r"^(ok|FAIL)\s+(?P<paket>\S+)", re.M)
_GO_YER = re.compile(r"^\s+(?P<dosya>\S+\.go):(?P<satir>\d+):\s*(?P<mesaj>.*)$", re.M)


def _oku_go(cikti: str) -> tuple[Sayim, list[Basarisiz]]:
    sayim = Sayim()
    kalanlar = _GO_FAIL.findall(cikti)
    gecenler = _GO_PASS.findall(cikti)
    if kalanlar or gecenler:
        sayim.gecen = len(gecenler)
        sayim.kalan = len(kalanlar)
        sayim.toplam = sayim.gecen + sayim.kalan
        sayim.okundu = True

    yerler = _GO_YER.findall(cikti)
    basarisizlar = []
    for i, ad in enumerate(kalanlar):
        dosya, satir, mesaj = yerler[i] if i < len(yerler) else ("", "", "")
        basarisizlar.append(
            Basarisiz(ad, mesaj.strip(), f"{dosya}:{satir}" if dosya else "")
        )
    return sayim, basarisizlar


# cargo: "test result: FAILED. 3 passed; 1 failed; 0 ignored; ..."
_CARGO_SONUC = re.compile(
    r"^test result:\s+\w+\.\s+(?P<gecen>\d+) passed;\s*(?P<kalan>\d+) failed;"
    r"\s*(?P<atlanan>\d+) ignored", re.M)
_CARGO_HATA = re.compile(r"^\s{4}(?P<ad>[\w:]+)\s*$", re.M)


def _oku_cargo(cikti: str) -> tuple[Sayim, list[Basarisiz]]:
    sayim = Sayim()
    for m in _CARGO_SONUC.finditer(cikti):
        sayim.gecen += int(m["gecen"])
        sayim.kalan += int(m["kalan"])
        sayim.atlanan += int(m["atlanan"])
        sayim.okundu = True
    sayim.toplam = sayim.gecen + sayim.kalan + sayim.atlanan

    basarisizlar: list[Basarisiz] = []
    if "\nfailures:\n" in cikti and sayim.kalan:
        kuyruk = cikti.rsplit("\nfailures:\n", 1)[1]
        for ad in _CARGO_HATA.findall(kuyruk):
            if ad not in [b.ad for b in basarisizlar]:
                basarisizlar.append(Basarisiz(ad))
    return sayim, basarisizlar


# dotnet: "Failed!  - Failed:     1, Passed:     2, Skipped:     0, Total:     3"
_DOTNET_OZET = re.compile(
    r"Failed:\s*(?P<kalan>\d+),\s*Passed:\s*(?P<gecen>\d+),"
    r"\s*Skipped:\s*(?P<atlanan>\d+),\s*Total:\s*(?P<toplam>\d+)")
_DOTNET_HATA = re.compile(r"^\s*(?:X|Failed)\s+(?P<ad>\S+)", re.M)


def _oku_dotnet(cikti: str) -> tuple[Sayim, list[Basarisiz]]:
    sayim = Sayim()
    for m in _DOTNET_OZET.finditer(cikti):
        sayim.kalan += int(m["kalan"])
        sayim.gecen += int(m["gecen"])
        sayim.atlanan += int(m["atlanan"])
        sayim.toplam += int(m["toplam"])
        sayim.okundu = True
    basarisizlar = [Basarisiz(ad) for ad in _DOTNET_HATA.findall(cikti)]
    return sayim, basarisizlar


_OKUYUCULAR = {
    "python": _oku_pytest,
    "php": _oku_phpunit,
    "node": _oku_node,
    "go": _oku_go,
    "rust": _oku_cargo,
    "dotnet": _oku_dotnet,
}


def normalize(ekosistem: str, cikti: str) -> tuple[Sayim, list[Basarisiz]]:
    """Ham çıktıyı ortak çerçeveye indirir.

    `ekosistem` "oto" ise okuyucular sırayla denenir ve sayı okuyabilen ilki
    kazanır — elle verilen komutta hangi koşucunun konuştuğunu bilmiyoruz.
    Hiçbiri okuyamazsa `Sayim.okundu` False kalıyor ve sonuç metni bunu
    açıkça söylüyor: uydurulmuş bir "0 kaldı" olmuyor.
    """
    if ekosistem in _OKUYUCULAR:
        return _OKUYUCULAR[ekosistem](cikti)
    for oku in (_oku_pytest, _oku_phpunit, _oku_node, _oku_cargo, _oku_dotnet,
                _oku_go):
        sayim, basarisizlar = oku(cikti)
        if sayim.okundu:
            return sayim, basarisizlar
    return Sayim(), []


def kirp(metin: str, limit: int = MAX_HAM) -> str:
    """Baş ve son korunarak kırpma.

    Koşucular başta ne koştuklarını, sonda özeti yazar; ortadaki yığın
    izleri modele bir şey öğretmiyor ve pencereyi yiyor.
    """
    metin = metin.strip()
    if len(metin) <= limit:
        return metin
    bas = metin[: limit // 2].rstrip()
    son = metin[-(limit // 2):].lstrip()
    atilan = len(metin) - len(bas) - len(son)
    return f"{bas}\n\n... [{atilan} karakter kırpıldı] ...\n\n{son}"


# -- koşum --------------------------------------------------------------


def _cozumle(ad: str) -> str | None:
    """Mantıksal araç adını gerçek çalıştırılabilire çevirir.

    `php` için `tanilar.denetleyici_yolu` kullanılıyor: Windows'ta PHP
    çoğu zaman PATH'te değil (XAMPP, Laragon, winget) ve orada zaten
    aranıyor. Aynı bilgiyi ikinci kez yazmanın anlamı yok.
    """
    if ad in ("py", "python3", "python"):
        return shutil.which(ad) or sys.executable
    if ad == "php":
        return tanilar.denetleyici_yolu("php")
    return shutil.which(ad)


async def kos(
    duzenek: Duzenek,
    *,
    zaman_asimi: float = VARSAYILAN_ZAMAN_ASIMI,
    cancel: asyncio.Event | None = None,
) -> Sonuc:
    """Düzeneği koşturur ve normalleştirilmiş sonucu döndürür."""
    if not duzenek.kosulabilir:
        return Sonuc(duzenek.ekosistem, duzenek.etiket, str(duzenek.kok),
                     "yok", ham=duzenek.engel, notlar=list(duzenek.notlar),
                     tur=duzenek.tur)

    exe = _cozumle(duzenek.argv[0])
    if exe is None:
        return Sonuc(
            duzenek.ekosistem, duzenek.etiket, str(duzenek.kok), "baslatilamadi",
            ham=f"`{duzenek.argv[0]}` bu makinede bulunamadı.",
            notlar=list(duzenek.notlar), tur=duzenek.tur,
        )
    return await _calistir(
        [exe, *duzenek.argv[1:]], duzenek.kok, duzenek.ekosistem, duzenek.etiket,
        zaman_asimi=zaman_asimi, cancel=cancel, notlar=list(duzenek.notlar),
        tur=duzenek.tur,
    )


async def kos_komut(
    komut: str,
    kok: Path,
    *,
    ekosistem: str = "oto",
    zaman_asimi: float = VARSAYILAN_ZAMAN_ASIMI,
    cancel: asyncio.Event | None = None,
) -> Sonuc:
    """Elle verilen komutu koşturur (tespitin geçersiz kılınması).

    Kabuk üzerinden çalışıyor: `npm test -- --filter x` gibi bir dizede
    boruların ve bayrakların çalışması bekleniyor. İzin kapısı bu komutu
    özne olarak görüyor (`permissions.SUBJECT_KEYS` içinde `komut` var).
    """
    return await _calistir(None, kok, ekosistem, komut, kabuk=komut,
                           zaman_asimi=zaman_asimi, cancel=cancel)


async def _oldur(proc) -> None:
    """Süreci ve ALTINDAKİLERİ sonlandırır.

    Gövde `ortam`a taşındı: aynı yara kancalarda da çıktı (kabuğu öldürmek
    asıl süreci bırakıyor, borular açık kaldığı için çağıran asılı
    kalıyor), yani bu bir test koşucusu meselesi değil, bu ortamda alt
    süreç öldürmenin doğru yolu.
    """
    await ortam.agaci_oldur(proc)


async def _calistir(
    argv: list[str] | None,
    kok: Path,
    ekosistem: str,
    etiket: str,
    *,
    kabuk: str | None = None,
    zaman_asimi: float,
    cancel: asyncio.Event | None,
    notlar: list[str] | None = None,
    tur: str = "test",
) -> Sonuc:
    """Ortak koşum yolu: başlat, kesmeyle yarıştır, çıktıyı normalleştir.

    Konsol penceresi açtırmayan bayraklarla (`ortam.sessiz_bayraklar`): neo
    pythonw altında koşarken her test koşumu ekranda bir cmd penceresi
    parlatırdı.
    """
    zaman_asimi = max(1.0, min(float(zaman_asimi), MAX_ZAMAN_ASIMI))
    baslangic = time.monotonic()
    ortak = dict(
        cwd=str(kok),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        # Renk kaçış dizileri ayrıştırmayı bozuyor ve modele çöp gidiyor.
        env={**os.environ, "NO_COLOR": "1", "FORCE_COLOR": "0",
             "PYTEST_ADDOPTS": "--color=no"},
        **ortam.sessiz_bayraklar(),
    )
    if sys.platform != "win32":  # pragma: no cover - POSIX yolu
        # Kendi süreç grubu: zaman aşımında bütün ağaç tek hamlede ölsün.
        ortak["start_new_session"] = True
    try:
        if kabuk is not None:
            proc = await asyncio.create_subprocess_shell(kabuk, **ortak)
        else:
            proc = await asyncio.create_subprocess_exec(*(argv or []), **ortak)
    except (OSError, ValueError) as exc:
        return Sonuc(ekosistem, etiket, str(kok), "baslatilamadi",
                     ham=f"{type(exc).__name__}: {exc}",
                     notlar=notlar or [], tur=tur)

    comm = asyncio.ensure_future(proc.communicate())
    bekleyenler = {comm}
    stop = None
    if cancel is not None:
        stop = asyncio.ensure_future(cancel.wait())
        bekleyenler.add(stop)

    try:
        bitenler, _ = await asyncio.wait(
            bekleyenler, timeout=zaman_asimi,
            return_when=asyncio.FIRST_COMPLETED,
        )
    except asyncio.CancelledError:  # pragma: no cover - tur iptali
        proc.kill()
        await proc.wait()
        comm.cancel()
        if stop is not None:
            stop.cancel()
        raise

    sure = time.monotonic() - baslangic

    if comm not in bitenler:
        # Zaman aşımı ya da kullanıcı kesmesi. Süreç AĞACINI öldürüp elde
        # ne varsa onunla dürüst ol: yarım çıktı da bilgidir — asılı kalan
        # testin adı çoğu zaman son satırda yazıyor.
        kesildi = stop is not None and stop in bitenler
        await _oldur(proc)
        try:
            yarim, _ = await asyncio.wait_for(comm, 5)
        except (asyncio.TimeoutError, asyncio.CancelledError, OSError):
            comm.cancel()
            yarim = b""
        if stop is not None:
            stop.cancel()
        parca = (yarim or b"").decode("utf-8", errors="replace")
        return Sonuc(ekosistem, etiket, str(kok),
                     "kesildi" if kesildi else "zaman_asimi", sure=sure,
                     ham=kirp(parca.replace("\r\n", "\n")),
                     notlar=notlar or [], tur=tur)

    if stop is not None:
        stop.cancel()
    veri, _ = comm.result()
    metin = (veri or b"").decode("utf-8", errors="replace")
    metin = metin.replace("\r\n", "\n").replace("\r", "\n")

    sayim, basarisizlar = normalize(ekosistem, metin)
    return Sonuc(
        ekosistem=ekosistem, etiket=etiket, kok=str(kok), durum="kostu",
        cikis_kodu=proc.returncode or 0, sure=sure, sayim=sayim,
        basarisizlar=basarisizlar, ham=kirp(metin), notlar=notlar or [], tur=tur,
    )


# -- yazma sonrası hatırlatma ------------------------------------------
#
# Test koşumu PAHALI: saniyeler, büyük takımlarda dakikalar. Her
# `write_file` sonrası kendiliğinden koşturmak turu dondurur ve kullanıcıyı
# bekletir — üstelik ajan çoğu zaman aynı dosyaya arka arkaya yazar, yani
# aradaki koşumların hepsi boşa gider. Onun yerine düzeneğin VARLIĞINI
# bildiriyoruz: bilgi bedava, koşum pahalı, karar modelin.

# Aynı dosyaya bu kadar yazımdan sonra hatırlatma sertleşir. Üçüncü yazım
# "deneme yanılma" demek: model kodu gözüyle düzeltmeye çalışıyor ve
# göremediği için dönüp duruyor. Orada koşum artık öneri değil, gereklilik.
ISRAR_ESIGI = 3


def hatirlatma(yol: Path | str, *, yazim: int = 1) -> str:
    """Yazılan dosyanın projesinde test düzeneği varsa tek satırlık not.

    Boş dize = söylenecek bir şey yok (proje değil, düzenek yok). Gürültü
    üretmemek şart: her yazmanın altına anlamsız bir cümle eklemek, gerçek
    uyarıların da okunmamasına yol açar.
    """
    try:
        kok = proje_koku(yol)
        duzenek = tespit(kok)
    except OSError:  # pragma: no cover - erişim hatası sessizce yutulur
        return ""
    if duzenek is None:
        return ""

    if duzenek.engel:
        return (f"koşum: bu projede {duzenek.etiket} düzeneği var ama "
                f"{duzenek.engel}")

    if duzenek.tur == "saglik":
        govde = (f"bu projede test takımı yok; `{duzenek.etiket}` ucuz bir "
                 f"sağlık denetimi ({duzenek.kanit})")
    else:
        govde = f"bu projede `{duzenek.etiket}` var ({duzenek.kanit})"

    if yazim >= ISRAR_ESIGI:
        return (f"koşum: {govde} — aynı dosyaya {yazim}. kez yazıyorsun. "
                "Gözle düzeltmeyi bırak, `kos` aracıyla çalıştır ve gerçek "
                "hatayı gör.")
    return f"koşum: {govde} — değişikliği doğrulamak için `kos` aracını kullan."


# -- son dokunulan proje ------------------------------------------------
#
# `kos` yolsuz çağrılabilmeli: model az önce yazdığı dosyanın projesini
# tekrar yazmak zorunda kalmasın. Dosya araçları her yazmada burayı
# güncelliyor; modül düzeyinde tek bir değer, çünkü tek oturumda tek ajan
# yazıyor ve yanlış tahmin edilse bile sonucun içinde kökün tam yolu
# yazıyor — model gördüğü an düzeltir.
_SON_PROJE: list[Path] = []


def dokunuldu(yol: Path | str) -> None:
    """Bir dosya yazıldı/düzenlendi: projesini hatırla."""
    try:
        _SON_PROJE[:] = [proje_koku(yol)]
    except OSError:  # pragma: no cover
        pass


def son_proje() -> Path | None:
    return _SON_PROJE[0] if _SON_PROJE else None


def unut() -> None:
    """Testler için: hatırlanan projeyi temizler."""
    _SON_PROJE.clear()
