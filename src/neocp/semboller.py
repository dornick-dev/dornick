"""Sembol araması — LSP'siz, ağır dil sunucusu olmadan yapısal kod gezintisi.

Neden var: ajanın "bu fonksiyon nerede tanımlı, nereden çağrılıyor?" sorusuna
tek cevabı `grep`ti. `grep` metin görür, yapı görmez. `kaydet` diye aratınca
tanımı, çağrıları, yorumları, dizeleri ve `kaydetme_hatasi` gibi başka
isimleri aynı yığında döker — model o yığını okuyup yanlış yeri düzeltir ya
da doğru yeri hiç bulamaz.

Buradaki araç ikisini ayırıyor: TANIM ayrı, KULLANIM ayrı, her biri
`dosya:satır: imza` biçiminde.

İki katman, iki farklı dürüstlük seviyesi — ve bu fark saklanmıyor:

  * **Python: kesin.** `ast` ile ayrıştırılıyor. Yorumdaki, dizedeki bir
    isim asla kullanım sayılmaz; `def` gerçekten `def`tir. Bir dosya
    ayrıştırılamıyorsa (sözdizimi hatası) bu söylenir, tahmine geçilmez.
  * **PHP / JS / TS: dikkatli düzenli ifade.** Dil ayrıştırıcısı yok, o
    yüzden sonuç "kesin" değil "büyük olasılıkla". Yorum satırları eleniyor
    ama bir dize içindeki isim hâlâ karışabilir. Sonucun altında bu yazıyor.
  * **Diğer diller: yok.** Uydurma yapmıyoruz — "bu dilde yapısal arama
    yok, `grep` kullan" deniyor. Yarım bir cevap, dürüst bir yönlendirmeden
    kötüdür.
"""

from __future__ import annotations

import ast
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

# Tek turda bakılacak en fazla dosya. Bir depo taramak istenen şey değil;
# "şu projede şu sembol" istenen şey.
MAX_DOSYA = 400

# Bundle'lar ve üretilmiş dosyalar taranmıyor: tek satırlık 3 MB'lık bir
# `app.min.js` hem yavaş hem anlamsız.
MAX_BOYUT = 400_000

# Kaç klasör derinliğine inilecek. Üçüncü seviye `src/neocp/tools/` demek;
# gerçek projelerde kaynak orada bitiyor.
MAX_DERINLIK = 3

# Sonuçta gösterilen en fazla tanım ve kullanım.
MAX_TANIM = 25
MAX_KULLANIM = 40

# Bağımlılık ve üretilmiş çıktı klasörleri. `tanilar.toplu_yollar` ile aynı
# liste — aynı gerekçe: `node_modules` içindeki on bin dosya ne kullanıcının
# yazdığı ne de ajanın aradığı.
ATLA = {
    "node_modules", "vendor", ".git", "__pycache__", ".venv", "venv",
    "dist", "build", ".next", "writable", "site-packages", ".mypy_cache",
    ".pytest_cache", "coverage", "target", "bin", "obj",
}

DILLER: dict[str, str] = {
    ".py": "python", ".pyw": "python",
    ".php": "php",
    ".js": "js", ".mjs": "js", ".cjs": "js", ".jsx": "js",
    ".ts": "ts", ".tsx": "ts",
}

# Kesin ayrıştırıcısı olan diller. Gerisi düzenli ifadeyle ve bunu söyleyerek.
KESIN = {"python"}


def dil_bul(yol: Path | str) -> str | None:
    return DILLER.get(Path(yol).suffix.lower())


@dataclass(slots=True)
class Sembol:
    """Bir tanım: fonksiyon, sınıf ya da metot."""

    ad: str
    tur: str            # fonksiyon | sinif | metot | sabit
    dosya: str
    satir: int
    imza: str
    kapsam: str = ""    # metotsa sınıf adı

    def bicim(self, kok: Path | None = None) -> str:
        """"tools/files.py:180: async def write_file(args, ctx) -> ToolResult"

        Metot ise sınıfı da yazılıyor: aynı adlı on `handle` arasında hangisi
        olduğunu ancak sahibi söylüyor.
        """
        yer = f"{_kisa(self.dosya, kok)}:{self.satir}"
        kuyruk = f"   [{self.kapsam} sınıfının metodu]" if self.kapsam else ""
        return f"{yer}: {self.imza}{kuyruk}"


@dataclass(slots=True)
class Kullanim:
    """Bir kullanım yeri ve nasıl kullanıldığı."""

    dosya: str
    satir: int
    metin: str
    tur: str = "anma"   # cagri | kurulum | ice_aktarma | anma

    def bicim(self, kok: Path | None = None) -> str:
        return f"{_kisa(self.dosya, kok)}:{self.satir}: {self.metin}"


@dataclass(slots=True)
class Sonuc:
    sorgu: str
    tanimlar: list[Sembol] = field(default_factory=list)
    kullanimlar: list[Kullanim] = field(default_factory=list)
    taranan: int = 0
    diller: set[str] = field(default_factory=set)
    # Ayrıştırılamayan dosyalar: sessizce atlanmıyor, sayılıyor.
    okunamayan: list[str] = field(default_factory=list)
    # Tam ad eşleşmesi bulunamayınca içerene düşüldü mü?
    gevsek: bool = False
    kok: Path | None = None
    # Taramanın tavana çarpıp çarpmadığı: eksik sonuç sessiz kalmamalı.
    tavana_carpti: bool = False

    @property
    def kesin(self) -> bool:
        """Yalnızca gerçek ayrıştırıcıdan gelen sonuç kesindir."""
        return bool(self.diller) and self.diller <= KESIN

    def metin(self, *, tur: str = "hepsi") -> str:
        if not self.diller:
            return (
                f"{self.kok} altında yapısal arama yapabildiğim bir dosya yok. "
                "Python, PHP, JS ve TS için sembol araması var; başka diller "
                "için yapısal arama YOK — `grep` aracını kullan."
            )

        satirlar: list[str] = []
        if tur in ("tanim", "hepsi"):
            satirlar += self._tanim_bolumu()
        if tur in ("kullanim", "hepsi"):
            if satirlar:
                satirlar.append("")
            satirlar += self._kullanim_bolumu()

        satirlar.append("")
        satirlar.append(self._altyazi())
        return "\n".join(satirlar)

    def _tanim_bolumu(self) -> list[str]:
        if not self.tanimlar:
            return [f"'{self.sorgu}' adında bir tanım bulunamadı "
                    f"({self.taranan} dosya tarandı)."]
        basi = f"{len(self.tanimlar)} tanım"
        if self.gevsek:
            basi += f" (tam '{self.sorgu}' yok; adı içerenler)"
        satirlar = [basi + ":"]
        for s in self.tanimlar[:MAX_TANIM]:
            satirlar.append(f"  {s.bicim(self.kok)}")
        if len(self.tanimlar) > MAX_TANIM:
            satirlar.append(f"  ... {len(self.tanimlar) - MAX_TANIM} tanım daha.")
        return satirlar

    def _kullanim_bolumu(self) -> list[str]:
        if not self.kullanimlar:
            if self.tanimlar:
                return [f"Kullanım bulunamadı. '{self.sorgu}' tanımlı ama bu "
                        "kapsamda hiçbir yerden çağrılmıyor — ölü kod olabilir, "
                        "ya da çağrı bu klasörün dışında."]
            return ["Kullanım da bulunamadı."]
        sayim: dict[str, int] = {}
        for k in self.kullanimlar:
            sayim[k.tur] = sayim.get(k.tur, 0) + 1
        ozet = ", ".join(f"{n} {ad.replace('_', ' ')}"
                         for ad, n in sorted(sayim.items()))
        satirlar = [f"{len(self.kullanimlar)} kullanım ({ozet}):"]
        for k in self.kullanimlar[:MAX_KULLANIM]:
            satirlar.append(f"  {k.bicim(self.kok)}")
        if len(self.kullanimlar) > MAX_KULLANIM:
            satirlar.append(f"  ... {len(self.kullanimlar) - MAX_KULLANIM} kullanım daha.")
        return satirlar

    def _altyazi(self) -> str:
        """Sonucun ne kadar güvenilir olduğunu söyleyen satır."""
        parcalar = [f"{self.taranan} dosya tarandı "
                    f"({', '.join(sorted(self.diller))})."]
        if "python" in self.diller:
            parcalar.append("Python dosyaları `ast` ile ayrıştırıldı: yorum ve "
                            "dize içindeki isimler sayılmadı.")
        if self.diller - KESIN:
            parcalar.append("PHP/JS/TS için düzenli ifade kullanıldı — yorum "
                            "satırları elendi ama dize içindeki bir isim "
                            "kullanım gibi görünebilir; şüphelenirsen dosyayı aç.")
        if self.okunamayan:
            parcalar.append(f"{len(self.okunamayan)} dosya ayrıştırılamadı "
                            f"(ilki: {self.okunamayan[0]}).")
        if self.tavana_carpti:
            parcalar.append(f"Tarama {MAX_DOSYA} dosya tavanına çarptı; sonuç "
                            "eksik olabilir — `path` ile daralt.")
        return " ".join(parcalar)


def _kisa(dosya: str, kok: Path | None) -> str:
    if kok is None:
        return Path(dosya).name
    try:
        return str(Path(dosya).relative_to(kok))
    except ValueError:
        return dosya


# -- dosya toplama ------------------------------------------------------


def dosyalar(
    kok: Path,
    *,
    dil: str | None = None,
    tavan: int = MAX_DOSYA,
    derinlik: int = MAX_DERINLIK,
) -> tuple[list[Path], bool]:
    """Taranacak dosyalar ve tavana çarpılıp çarpılmadığı.

    İkili dosya atlanıyor: bir `.py` uzantısı taşısa bile içinde NUL baytı
    varsa o kaynak değildir, ayrıştırmaya çalışmak boşa iş.
    """
    bulunan: list[Path] = []
    kok = Path(kok)
    for temel, klasorler, adlar in os.walk(kok):
        seviye = len(Path(temel).relative_to(kok).parts)
        if seviye >= derinlik:
            klasorler[:] = []
        else:
            klasorler[:] = [k for k in klasorler
                            if k not in ATLA and not k.startswith(".")]
        for ad in sorted(adlar):
            yol = Path(temel) / ad
            bulunan_dil = dil_bul(yol)
            if bulunan_dil is None or (dil and bulunan_dil != dil):
                continue
            try:
                if yol.stat().st_size > MAX_BOYUT:
                    continue
            except OSError:  # pragma: no cover
                continue
            bulunan.append(yol)
            if len(bulunan) >= tavan:
                return bulunan, True
    return bulunan, False


def _oku(yol: Path) -> str | None:
    """Kaynağı okur; ikili ya da okunamıyorsa None."""
    try:
        ham = yol.read_bytes()
    except OSError:
        return None
    if b"\x00" in ham[:4096]:
        return None
    return ham.decode("utf-8", errors="replace")


# -- Python: ast ile kesin ---------------------------------------------


def _imza_python(node: ast.AST) -> str:
    if isinstance(node, ast.ClassDef):
        temeller = ", ".join(_kaynak(t) for t in node.bases)
        return f"class {node.name}({temeller})" if temeller else f"class {node.name}"
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        onek = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
        try:
            argumanlar = ast.unparse(node.args)
        except Exception:  # pragma: no cover - eski sürüm / tuhaf ağaç
            argumanlar = ", ".join(a.arg for a in node.args.args)
        kuyruk = ""
        if node.returns is not None:
            kuyruk = f" -> {_kaynak(node.returns)}"
        return f"{onek} {node.name}({argumanlar}){kuyruk}"
    return getattr(node, "name", "?")  # pragma: no cover


def _kaynak(node: ast.AST) -> str:
    try:
        return ast.unparse(node)
    except Exception:  # pragma: no cover
        return "?"


def tanimlar_python(yol: Path, kaynak: str) -> list[Sembol] | None:
    """Dosyadaki tüm tanımlar; ayrıştırılamıyorsa None.

    None dönmek önemli: bozuk bir dosyayı sessizce "tanımsız" saymak,
    aradığı şeyi tam da orada olan bir modeli yanlış yere gönderirdi.
    """
    try:
        agac = ast.parse(kaynak, filename=str(yol))
    except (SyntaxError, ValueError):
        return None

    bulunan: list[Sembol] = []

    def gez(dugum: ast.AST, kapsam: str) -> None:
        for cocuk in ast.iter_child_nodes(dugum):
            if isinstance(cocuk, ast.ClassDef):
                bulunan.append(Sembol(cocuk.name, "sinif", str(yol),
                                      cocuk.lineno, _imza_python(cocuk), kapsam))
                gez(cocuk, cocuk.name)
            elif isinstance(cocuk, (ast.FunctionDef, ast.AsyncFunctionDef)):
                tur = "metot" if kapsam else "fonksiyon"
                bulunan.append(Sembol(cocuk.name, tur, str(yol), cocuk.lineno,
                                      _imza_python(cocuk), kapsam))
                # İç içe fonksiyonlar da tanımdır; kapsam adı korunuyor.
                gez(cocuk, kapsam)
            else:
                gez(cocuk, kapsam)

    gez(agac, "")
    return bulunan


def kullanimlar_python(
    yol: Path, kaynak: str, ad: str, tanim_satirlari: set[int]
) -> list[Kullanim] | None:
    """`ad`ın bu dosyadaki kullanımları — `ast` ile, yani kesin.

    Yorum ve dize içindeki isimler AĞAÇTA YOKTUR; bu yüzden burada hiç
    görünmüyorlar. Düzenli ifadeyle asla ulaşılamayacak kesinlik bu.
    """
    try:
        agac = ast.parse(kaynak, filename=str(yol))
    except (SyntaxError, ValueError):
        return None

    satirlar = kaynak.splitlines()
    bulunan: dict[int, Kullanim] = {}

    def ekle(satir: int, tur: str) -> None:
        if satir in tanim_satirlari or satir in bulunan:
            return
        ham = satirlar[satir - 1].strip() if 0 < satir <= len(satirlar) else ""
        bulunan[satir] = Kullanim(str(yol), satir, ham[:120], tur)

    for dugum in ast.walk(agac):
        if isinstance(dugum, ast.Call):
            hedef = dugum.func
            isim = (getattr(hedef, "id", None) if isinstance(hedef, ast.Name)
                    else getattr(hedef, "attr", None))
            if isim == ad:
                ekle(dugum.lineno, "cagri")
        elif isinstance(dugum, (ast.Import, ast.ImportFrom)):
            for takma in dugum.names:
                if takma.name.rsplit(".", 1)[-1] == ad or takma.asname == ad:
                    ekle(dugum.lineno, "ice_aktarma")
        elif isinstance(dugum, ast.Name) and dugum.id == ad:
            ekle(dugum.lineno, "anma")
        elif isinstance(dugum, ast.Attribute) and dugum.attr == ad:
            ekle(dugum.lineno, "anma")
    return list(bulunan.values())


# -- PHP / JS / TS: dikkatli düzenli ifade ------------------------------
#
# Her desen belirli bir imzayı hedefliyor; genel bir "şu kelime geçiyor mu"
# taraması bilerek yok. Yakalanan ad daima birinci grup.

_PHP_DESENLER: tuple[tuple[str, str], ...] = (
    ("fonksiyon", r"^\s*(?:(?:public|private|protected|static|final|abstract)\s+)*"
                  r"function\s+&?(\w+)\s*\("),
    ("sinif", r"^\s*(?:abstract\s+|final\s+)?(?:class|interface|trait|enum)\s+(\w+)"),
    ("sabit", r"^\s*(?:public\s+|private\s+|protected\s+)?const\s+(\w+)\s*="),
)

_JS_DESENLER: tuple[tuple[str, str], ...] = (
    ("fonksiyon", r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*\*?\s*(\w+)\s*\("),
    ("sinif", r"^\s*(?:export\s+)?(?:default\s+)?(?:abstract\s+)?class\s+(\w+)"),
    # const ad = (…) => …   /   const ad = function …
    ("fonksiyon", r"^\s*(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*"
                  r"(?:async\s*)?(?:function\b|\([^)]*\)\s*=>|\w+\s*=>)"),
    # sınıf gövdesindeki metot:  ad(arg) {   —  if/for/while/switch elenir
    ("metot", r"^\s{2,}(?:static\s+|async\s+|get\s+|set\s+)*(\w+)\s*\([^;]*\)\s*\{"),
    # TypeScript arayüz/tip
    ("sinif", r"^\s*(?:export\s+)?(?:interface|type|enum)\s+(\w+)\b"),
)

# Metot deseninin yanlışlıkla yakalayacağı denetim yapıları.
_ANAHTAR = {"if", "for", "while", "switch", "catch", "function", "return",
            "else", "do", "try", "with", "case", "typeof", "new", "await"}

# Yorum satırları: kullanım sayılmıyor. Dize içi hâlâ karışabilir ve
# sonucun altyazısı bunu açıkça söylüyor.
_YORUM = re.compile(r"^\s*(//|#|\*|/\*|<!--)")


def tanimlar_desenli(yol: Path, kaynak: str, dil: str) -> list[Sembol]:
    desenler = _PHP_DESENLER if dil == "php" else _JS_DESENLER
    derli = [(tur, re.compile(desen)) for tur, desen in desenler]
    bulunan: list[Sembol] = []
    gorulen: set[tuple[str, int]] = set()
    for i, satir in enumerate(kaynak.splitlines(), start=1):
        if _YORUM.match(satir):
            continue
        for tur, desen in derli:
            if not (m := desen.match(satir)):
                continue
            ad = m.group(1)
            if ad in _ANAHTAR:
                continue
            if (ad, i) in gorulen:
                continue
            gorulen.add((ad, i))
            bulunan.append(Sembol(ad, tur, str(yol), i, satir.strip()[:160]))
    return bulunan


def _kullanim_deseni(ad: str) -> re.Pattern[str]:
    """`ad`ın kullanıldığı satırları yakalayan desen.

    Önüne `$` ve `.` bakışı bilinçli: PHP'de `$kaydet` başka bir şeydir,
    JS'te `nesne.kaydet(` ise ARADIĞIMIZ şeydir — o yüzden nokta engelleyici
    değil, ayrı bir kola alınıyor.
    """
    k = re.escape(ad)
    return re.compile(
        rf"(?:(?<![\w$]){k}\s*\()"          # çağrı: kaydet(
        rf"|(?:->\s*{k}\s*\()"              # PHP metot: $o->kaydet(
        rf"|(?:(?<![\w$]){k}::)"            # PHP statik: Kayit::
        rf"|(?:\bnew\s+{k}(?![\w$]))"       # kurulum: new Kayit
        rf"|(?:\b(?:extends|implements|instanceof)\s+{k}(?![\w$]))"
        rf"|(?:\b(?:use|import|require|from)\b[^\n]*(?<![\w$]){k}(?![\w$]))"
    )


def _kullanim_turu(satir: str, ad: str) -> str:
    duz = satir.strip()
    if re.search(rf"\bnew\s+{re.escape(ad)}\b", duz):
        return "kurulum"
    if re.match(r"^\s*(use|import|require|from|include)\b", duz):
        return "ice_aktarma"
    if re.search(rf"(?<![\w$]){re.escape(ad)}\s*\(", duz) or \
       re.search(rf"->\s*{re.escape(ad)}\s*\(", duz):
        return "cagri"
    return "anma"


def kullanimlar_desenli(
    yol: Path, kaynak: str, ad: str, tanim_satirlari: set[int]
) -> list[Kullanim]:
    desen = _kullanim_deseni(ad)
    bulunan: list[Kullanim] = []
    for i, satir in enumerate(kaynak.splitlines(), start=1):
        if i in tanim_satirlari or _YORUM.match(satir):
            continue
        if not desen.search(satir):
            continue
        bulunan.append(Kullanim(str(yol), i, satir.strip()[:120],
                                _kullanim_turu(satir, ad)))
    return bulunan


# -- arama --------------------------------------------------------------


def ara(
    kok: Path | str,
    sorgu: str,
    *,
    tur: str = "hepsi",
    dil: str | None = None,
    tavan: int = MAX_DOSYA,
    derinlik: int = MAX_DERINLIK,
) -> Sonuc:
    """`sorgu` adlı sembolün tanımlarını ve kullanımlarını bulur.

    Önce tam ad eşleşmesi aranıyor; hiç tanım yoksa adı İÇERENLERE
    düşülüyor ve bu sonuçta yazılıyor — model yanlışlıkla "tam bunu buldum"
    sanmasın.
    """
    kok = Path(kok).expanduser()
    sonuc = Sonuc(sorgu=sorgu, kok=kok)
    if not kok.is_dir():
        return sonuc

    yollar, carpti = dosyalar(kok, dil=dil, tavan=tavan, derinlik=derinlik)
    sonuc.tavana_carpti = carpti

    # Dosya başına: kaynak + dil + tanımlar. İki kez okumamak için tutuluyor.
    okunan: list[tuple[Path, str, str, list[Sembol]]] = []
    for yol in yollar:
        dosya_dili = dil_bul(yol)
        if dosya_dili is None:
            continue  # pragma: no cover
        kaynak = _oku(yol)
        if kaynak is None:
            continue
        sonuc.taranan += 1
        sonuc.diller.add(dosya_dili)
        if dosya_dili == "python":
            tanim = tanimlar_python(yol, kaynak)
            if tanim is None:
                sonuc.okunamayan.append(_kisa(str(yol), kok))
                tanim = []
        else:
            tanim = tanimlar_desenli(yol, kaynak, dosya_dili)
        okunan.append((yol, kaynak, dosya_dili, tanim))

    if not sonuc.diller:
        return sonuc

    tam = [s for _y, _k, _d, tanim in okunan for s in tanim if s.ad == sorgu]
    if tam:
        sonuc.tanimlar = tam
    else:
        alt = sorgu.lower()
        sonuc.tanimlar = [s for _y, _k, _d, tanim in okunan for s in tanim
                          if alt in s.ad.lower()]
        sonuc.gevsek = bool(sonuc.tanimlar)

    if tur == "tanim":
        return sonuc

    # Kullanımlar her zaman TAM ad üzerinden: gevşek eşleşmede "kaydet"
    # ararken "kaydetme_hatasi"nın çağrılarını göstermek gürültüdür.
    hedef = sorgu if tam or not sonuc.tanimlar else sonuc.tanimlar[0].ad
    for yol, kaynak, dosya_dili, tanim in okunan:
        satirlar = {s.satir for s in tanim if s.ad == hedef}
        if dosya_dili == "python":
            bulunan = kullanimlar_python(yol, kaynak, hedef, satirlar)
            if bulunan is None:
                continue
        else:
            bulunan = kullanimlar_desenli(yol, kaynak, hedef, satirlar)
        sonuc.kullanimlar.extend(bulunan)

    # Dosya ve satıra göre sıralı: `ast.walk` ağaç sırasında geziyor ve
    # aynı dosyanın 203. satırı 137.'den önce çıkabiliyordu. Liste okunacaksa
    # kaynaktaki sırayı izlemeli.
    sonuc.kullanimlar.sort(key=lambda k: (k.dosya, k.satir))
    sonuc.tanimlar.sort(key=lambda s: (s.dosya, s.satir))
    return sonuc
