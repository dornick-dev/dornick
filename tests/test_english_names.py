"""Every name in the code base is English (owner's rule, 2026-09-05).

Turkish stays where it is CONTENT — README.tr.md, the Turkish corpus, text
shown to the user or the model, the eval seeds that imitate a Turkish
user's repo — never in a name: no Turkish function, class, method,
variable, parameter, file or folder. This test reads every tracked path
and every Python definition and fails on the first Turkish word it finds.
The keys that travel over the wire or sit on disk (settings/state JSON,
session-log fields, SQLite columns, night events) are outside its reach on
purpose: renaming those would orphan existing installs.
"""

from __future__ import annotations

import ast
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# Whole tokens (a name is split on `_` and camelCase). Only words that are
# unmistakably Turkish are listed: `son`, `kat`, `plan` and other look-alikes
# of English words are left out so an honest English name never trips.
TURKISH_WORDS = frozenset("""
hafiza karar kararlar karakter ornek ornekler yasam taban egitim atolye gorev gorevler komut komutlar
olcum ozet sonda sondalari arsiv arsivle resim kimlik mizac basvuru buyume aktivasyon aktivasyonsuz
orgu orgusuz taze kos denetle semboller sembol bellek dusun zihin duyu duyular sohbet mesaj mesajlar
kullanici ayar ayarlar durum hata deneme calisma duzen duzeni rapor sonuc kayit hedef hedefler metin
metni icerik uygula gunluk gunlugu uyku iptal sure sureler tekrar kiyas dosya dosyalar klasor dizin
cevap soru istek istekler yetenek yetenekler tohum tohumlar onay onayli surum surumler yeni eski deger
ilerleme sayi sayfa satir satirlar sutun baslik basliklar liste kisisel korpus tanima zaman kaynak
kaynaklar esik egri bozulma basinc celiski anahtar izin izinli agirlik ogretici sinav puan kanca kancalar
fiyat fiyatlama filigran ritim havuz projeler proje tavan tavani temizlenen temiz kokler akilli ajan
adet adim adimlar adlar atamalar bahce beklenen birikimli bloklar bos ceviri cezali desen dugme etiket
etiketler fark fiyatlama govde govdesi gecen gecikme genis giris gomme imlec istenen izler kafa kalip
kapsuller katalog kisa konum kopru koru kuresel kuyruk medyan nitelik notlar notlari olaylar olaylari
ortam pano planlar sayac sebep sistem skor sonrasi sunulan turlar uyandirildi uygulanan uygulananlar
yalniz yazilan yazan kabul kisalik esnek esle evet hayir yardim yardimci yetki sifirla durdur gecmis
uygulamalar kusurlu guvenilir indirme sahte kirmizi yesil hafizali dokum dongu oturum oturumlar
tamamlanan tahmini uyanma uzerinden paylar kenarlar borc devreden faz sira siralar sorgu seviye
tespit arka plan_ dil kod kodu kok yol harita yolu haritasi calisma benzeri insan geri donusum yedek
belge kural mekanizma bulunamadi okunamadi calistirilamadi
""".split())

# Deliberate exceptions. Each one is a name that is ALSO an on-disk or wire
# key, or an English abbreviation that happens to look Turkish.
ALLOWED_NAMES = frozenset({
    "BOS",            # beginning-of-sequence token (training rig)
    "uygulama",       # `Uygulama` = the dataclass behind the apps API
    "tutarlilik_zaman", "kimlik_farki",        # character-report JSON keys
})

# Paths that may carry Turkish words: content, not names.
ALLOWED_PATHS = (
    "README.tr.md",
    "eval/coding/tasks/",            # seeds imitate a Turkish user's repo; graders name its API
    "training/data/corpus.jsonl",
)

_CAMEL = re.compile(r"[A-Z]+(?![a-z])|[A-Z]?[a-z0-9]+")


def _tokens(name: str) -> list[str]:
    return [p.lower() for p in _CAMEL.findall(name)]


def _turkish(name: str) -> str | None:
    """The Turkish token inside `name`, or None."""
    if name in ALLOWED_NAMES:
        return None
    for tok in _tokens(name):
        if tok in TURKISH_WORDS:
            return tok
    return None


def _tracked() -> list[str]:
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True)
    return [line for line in out.stdout.splitlines() if line]


def test_no_tracked_path_carries_a_turkish_word() -> None:
    bad = []
    for rel in _tracked():
        if any(rel.startswith(p) or rel == p for p in ALLOWED_PATHS):
            continue
        for segment in rel.split("/"):
            for piece in re.split(r"[-_.]", segment):
                if piece in TURKISH_WORDS:
                    bad.append(rel)
                    break
    assert not bad, "Turkish file or folder names:\n  " + "\n  ".join(sorted(set(bad)))


class _Definitions(ast.NodeVisitor):
    """Every DEFINED name: functions, classes, parameters, assignment targets,
    `self.x = ...` attributes, `import ... as` aliases. Keyword arguments at
    call sites are NOT definitions (they are how the wire keys travel)."""

    def __init__(self) -> None:
        self.found: list[tuple[int, str]] = []

    def _add(self, name: str, node: ast.AST) -> None:
        self.found.append((getattr(node, "lineno", 0), name))

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._add(node.name, node)
        args = node.args
        for a in args.posonlyargs + args.args + args.kwonlyargs:
            self._add(a.arg, a)
        for a in (args.vararg, args.kwarg):
            if a is not None:
                self._add(a.arg, a)
        self.generic_visit(node)

    visit_AsyncFunctionDef = visit_FunctionDef  # type: ignore[assignment]

    def visit_Lambda(self, node: ast.Lambda) -> None:
        for a in node.args.args + node.args.kwonlyargs:
            self._add(a.arg, a)
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._add(node.name, node)
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Store):
            self._add(node.id, node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if isinstance(node.ctx, ast.Store) and isinstance(node.value, ast.Name) and node.value.id == "self":
            self._add(node.attr, node)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        for alias in node.names:
            if alias.asname:
                self._add(alias.asname, node)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            if alias.asname:
                self._add(alias.asname, node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if node.name:
            self._add(node.name, node)
        self.generic_visit(node)


def _python_files() -> list[str]:
    return [rel for rel in _tracked()
            if rel.endswith(".py") and not any(rel.startswith(p) for p in ALLOWED_PATHS)]


@pytest.mark.parametrize("rel", _python_files())
def test_python_definitions_are_english(rel: str) -> None:
    tree = ast.parse((ROOT / rel).read_text(encoding="utf-8"))
    visitor = _Definitions()
    visitor.visit(tree)
    bad = sorted({(line, name, _turkish(name)) for line, name in visitor.found if _turkish(name)})
    assert not bad, "Turkish names in " + rel + ":\n  " + "\n  ".join(
        f"line {line}: {name} ({word})" for line, name, word in bad)
