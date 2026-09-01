"""Sembol araması: `grep` gürültüsü yerine yapısal cevap.

Sınanan vaat: "bu fonksiyon nerede tanımlı, nereden çağrılıyor?" sorusuna
TANIM ve KULLANIM ayrı ayrı cevap gelmeli. `grep kaydet` tanımı, çağrıları,
yorumları, dizeleri ve `kaydetme_hatasi` gibi başka isimleri aynı yığında
döküyordu.

İkinci vaat dürüstlük: Python `ast` ile kesin, PHP/JS/TS düzenli ifadeyle
"büyük olasılıkla", başka diller için hiç — ve hangisinin geçerli olduğu
sonucun altında yazıyor.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from dornick import semboller
from dornick.config import Config
from dornick.events import EventLog
from dornick.session import Session
from dornick.tools import ToolContext, ToolRegistry
from dornick.tools import kod as kod_tools

PY_KAYNAK = '''\
"""Örnek modül — kaydet burada da geçiyor ama bu bir dize."""

import json


def kaydet(veri: dict, yol: str = "x.json") -> bool:
    """kaydet fonksiyonunun belgesi."""
    return bool(json.dumps(veri))


class Depo:
    def kaydet(self, veri):
        return kaydet(veri)

    def yukle(self):
        # kaydet burada yalnızca yorumda geçiyor
        return "kaydet"


async def toplu_kaydet(hepsi):
    for v in hepsi:
        kaydet(v)
    return Depo().kaydet(hepsi)
'''

PHP_KAYNAK = """\
<?php
namespace App\\Controllers;

class Home extends BaseController
{
    // kaydet burada yalnızca yorumda
    public function index(): string
    {
        $depo = new Depo();
        return $depo->kaydet(['a' => 1]);
    }

    private static function kaydet(array $veri)
    {
        return Kayit::kaydet($veri);
    }
}

function kaydet($x) { return $x; }
"""

JS_KAYNAK = """\
// kaydet burada yorumda
export function kaydet(veri) {
  return JSON.stringify(veri);
}

const yukle = async (yol) => {
  return kaydet(yol);
};

export class Depo {
  kaydet(veri) {
    return kaydet(veri);
  }
}
"""


@pytest.fixture()
def proje(tmp_path: Path) -> Path:
    (tmp_path / "depo.py").write_text(PY_KAYNAK, encoding="utf-8")
    return tmp_path


# -- Python: ast ile kesin ---------------------------------------------


def test_python_definitions_are_exact(proje: Path) -> None:
    sonuc = semboller.ara(proje, "kaydet")
    adlar = [(s.tur, s.kapsam, s.satir) for s in sonuc.tanimlar]
    assert ("fonksiyon", "", 6) in adlar        # modül düzeyi def kaydet
    assert ("metot", "Depo", 12) in adlar       # Depo.kaydet
    assert sonuc.kesin


def test_python_signature_carries_arguments_and_return(proje: Path) -> None:
    sonuc = semboller.ara(proje, "kaydet", tur="tanim")
    imza = next(s.imza for s in sonuc.tanimlar if s.kapsam == "")
    assert imza.startswith("def kaydet(")
    assert "yol: str" in imza
    assert "-> bool" in imza


def test_a_method_names_its_class(proje: Path) -> None:
    sonuc = semboller.ara(proje, "kaydet", tur="tanim")
    metin = sonuc.metin(tur="tanim")
    assert "Depo sınıfının metodu" in metin


def test_async_definitions_are_found(proje: Path) -> None:
    sonuc = semboller.ara(proje, "toplu_kaydet", tur="tanim")
    assert len(sonuc.tanimlar) == 1
    assert sonuc.tanimlar[0].imza.startswith("async def toplu_kaydet(")


def test_classes_are_found(proje: Path) -> None:
    sonuc = semboller.ara(proje, "Depo", tur="tanim")
    assert [s.tur for s in sonuc.tanimlar] == ["sinif"]
    assert sonuc.tanimlar[0].imza == "class Depo"


def test_python_ignores_comments_and_strings(proje: Path) -> None:
    """`ast`in asıl değeri bu: yorumdaki ve dizedeki isim AĞAÇTA YOKTUR."""
    sonuc = semboller.ara(proje, "kaydet")
    satirlar = {k.satir for k in sonuc.kullanimlar}
    # 1: modül belgesindeki "kaydet", 18: yorum, 19: dize dönüşü
    assert 1 not in satirlar
    assert 18 not in satirlar
    assert 19 not in satirlar


def test_python_usages_are_classified(proje: Path) -> None:
    sonuc = semboller.ara(proje, "kaydet")
    turler = {k.tur for k in sonuc.kullanimlar}
    assert "cagri" in turler
    # Tanım satırları kullanım sayılmaz.
    tanim_satirlari = {s.satir for s in sonuc.tanimlar}
    assert not (tanim_satirlari & {k.satir for k in sonuc.kullanimlar})


def test_imports_count_as_usage(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("def kaydet():\n    pass\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("from a import kaydet\n", encoding="utf-8")
    sonuc = semboller.ara(tmp_path, "kaydet")
    assert any(k.tur == "ice_aktarma" for k in sonuc.kullanimlar)


def test_a_broken_python_file_is_reported_not_silently_skipped(tmp_path: Path) -> None:
    """Bozuk dosyayı sessizce 'tanımsız' saymak, modeli yanlış yere gönderir."""
    (tmp_path / "bozuk.py").write_text("def kaydet(:\n", encoding="utf-8")
    sonuc = semboller.ara(tmp_path, "kaydet")
    assert sonuc.okunamayan
    assert "ayrıştırılamadı" in sonuc.metin()


# -- PHP ----------------------------------------------------------------


def test_php_definitions(tmp_path: Path) -> None:
    (tmp_path / "Home.php").write_text(PHP_KAYNAK, encoding="utf-8")
    sonuc = semboller.ara(tmp_path, "kaydet", tur="tanim")
    satirlar = sorted(s.satir for s in sonuc.tanimlar)
    assert 13 in satirlar          # private static function kaydet
    assert 19 in satirlar          # serbest function kaydet
    assert not sonuc.kesin         # düzenli ifade: "kesin" demiyoruz


def test_php_class_definition(tmp_path: Path) -> None:
    (tmp_path / "Home.php").write_text(PHP_KAYNAK, encoding="utf-8")
    sonuc = semboller.ara(tmp_path, "Home", tur="tanim")
    assert [s.tur for s in sonuc.tanimlar] == ["sinif"]


def test_php_usages_cover_arrow_and_static_calls(tmp_path: Path) -> None:
    (tmp_path / "Home.php").write_text(PHP_KAYNAK, encoding="utf-8")
    sonuc = semboller.ara(tmp_path, "kaydet")
    metinler = " ".join(k.metin for k in sonuc.kullanimlar)
    assert "$depo->kaydet" in metinler       # nesne metodu
    assert "Kayit::kaydet" in metinler       # statik çağrı


def test_php_comment_lines_are_dropped(tmp_path: Path) -> None:
    (tmp_path / "Home.php").write_text(PHP_KAYNAK, encoding="utf-8")
    sonuc = semboller.ara(tmp_path, "kaydet")
    assert all("yalnızca yorumda" not in k.metin for k in sonuc.kullanimlar)


def test_php_new_is_an_instantiation(tmp_path: Path) -> None:
    (tmp_path / "Home.php").write_text(PHP_KAYNAK, encoding="utf-8")
    sonuc = semboller.ara(tmp_path, "Depo")
    assert any(k.tur == "kurulum" for k in sonuc.kullanimlar)


# -- JS -----------------------------------------------------------------


def test_js_function_class_and_arrow(tmp_path: Path) -> None:
    (tmp_path / "depo.js").write_text(JS_KAYNAK, encoding="utf-8")
    hepsi = semboller.ara(tmp_path, "kaydet", tur="tanim")
    assert any(s.satir == 2 for s in hepsi.tanimlar)     # export function

    ok = semboller.ara(tmp_path, "yukle", tur="tanim")   # const yukle = async () =>
    assert ok.tanimlar and ok.tanimlar[0].tur == "fonksiyon"

    sinif = semboller.ara(tmp_path, "Depo", tur="tanim")
    assert sinif.tanimlar and sinif.tanimlar[0].tur == "sinif"


def test_js_control_keywords_are_not_symbols(tmp_path: Path) -> None:
    """`if (x) {` bir metot tanımı değildir."""
    (tmp_path / "a.js").write_text(
        "class A {\n  metot() {\n    if (x) {\n      return 1;\n    }\n  }\n}\n",
        encoding="utf-8")
    sonuc = semboller.ara(tmp_path, "if", tur="tanim")
    assert sonuc.tanimlar == []
    metot = semboller.ara(tmp_path, "metot", tur="tanim")
    assert metot.tanimlar and metot.tanimlar[0].tur == "metot"


# -- kapsam ve sınırlar -------------------------------------------------


def test_unsupported_language_says_so_and_points_at_grep(tmp_path: Path) -> None:
    """Ölçemediğimiz dilde yarım cevap değil, dürüst yönlendirme."""
    (tmp_path / "ana.go").write_text("func Kaydet() {}\n", encoding="utf-8")
    (tmp_path / "notlar.md").write_text("# kaydet\n", encoding="utf-8")
    sonuc = semboller.ara(tmp_path, "Kaydet")
    metin = sonuc.metin()
    assert "yapısal arama YOK" in metin
    assert "`grep`" in metin


def test_dependency_folders_are_skipped(tmp_path: Path) -> None:
    (tmp_path / "kod.py").write_text("def kaydet(): pass\n", encoding="utf-8")
    icerde = tmp_path / "node_modules" / "paket"
    icerde.mkdir(parents=True)
    (icerde / "kaydet.js").write_text("function kaydet() {}\n", encoding="utf-8")
    sonuc = semboller.ara(tmp_path, "kaydet")
    assert sonuc.taranan == 1
    assert all("node_modules" not in s.dosya for s in sonuc.tanimlar)


def test_depth_is_limited(tmp_path: Path) -> None:
    derin = tmp_path / "a" / "b" / "c" / "d"
    derin.mkdir(parents=True)
    (derin / "gizli.py").write_text("def kaydet(): pass\n", encoding="utf-8")
    (tmp_path / "yuzey.py").write_text("def kaydet(): pass\n", encoding="utf-8")
    sonuc = semboller.ara(tmp_path, "kaydet", derinlik=3)
    assert all("gizli" not in s.dosya for s in sonuc.tanimlar)


def test_binary_files_are_skipped(tmp_path: Path) -> None:
    (tmp_path / "veri.py").write_bytes(b"def kaydet():\x00\x00 pass")
    sonuc = semboller.ara(tmp_path, "kaydet")
    assert sonuc.taranan == 0


def test_the_file_ceiling_is_announced(tmp_path: Path) -> None:
    """Eksik sonuç sessiz kalmamalı."""
    for i in range(6):
        (tmp_path / f"m{i}.py").write_text("def kaydet(): pass\n", encoding="utf-8")
    sonuc = semboller.ara(tmp_path, "kaydet", tavan=3)
    assert sonuc.tavana_carpti
    assert "tavanına çarptı" in sonuc.metin()


def test_language_filter(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("def kaydet(): pass\n", encoding="utf-8")
    (tmp_path / "a.js").write_text("function kaydet() {}\n", encoding="utf-8")
    sonuc = semboller.ara(tmp_path, "kaydet", dil="python")
    assert sonuc.diller == {"python"}
    assert len(sonuc.tanimlar) == 1


def test_a_loose_match_says_it_is_loose(tmp_path: Path) -> None:
    """Tam ad yoksa içerenler gösteriliyor ama bu SAKLANMIYOR."""
    (tmp_path / "a.py").write_text(
        "def kaydet_hepsini(): pass\n", encoding="utf-8")
    sonuc = semboller.ara(tmp_path, "kaydet")
    assert sonuc.gevsek
    assert "adı içerenler" in sonuc.metin()


def test_a_defined_but_unused_symbol_is_called_out(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("def kaydet(): pass\n", encoding="utf-8")
    sonuc = semboller.ara(tmp_path, "kaydet")
    assert "ölü kod olabilir" in sonuc.metin()


def test_nothing_found_is_not_an_invention(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("def baska(): pass\n", encoding="utf-8")
    sonuc = semboller.ara(tmp_path, "kaydet")
    assert sonuc.tanimlar == [] and sonuc.kullanimlar == []
    assert "bulunamadı" in sonuc.metin()


# -- araç yüzeyi --------------------------------------------------------


@pytest.fixture()
def ctx(tmp_path: Path) -> ToolContext:
    config = Config.load(tmp_path)
    config.ensure_dirs()
    return ToolContext(
        config=config,
        session=Session(EventLog(tmp_path / ".dornick" / "s.jsonl"), "test-sembol"),
        cancel=asyncio.Event(),
    )


@pytest.fixture()
def registry() -> ToolRegistry:
    reg = ToolRegistry()
    kod_tools.register(reg)
    return reg


async def call(registry: ToolRegistry, ctx: ToolContext, **args):
    return await registry.get("semboller").handler(args, ctx)


def test_the_tool_is_registered_and_read_only() -> None:
    from dornick.tools import build_registry

    registry = build_registry(subagents=False)
    spec = registry.get("semboller")
    assert spec is not None
    # Hiçbir şey çalıştırmıyor, hiçbir şey yazmıyor: kapıya takılmamalı.
    assert spec.mutates is False


async def test_the_tool_finds_a_definition(
    registry: ToolRegistry, ctx: ToolContext, proje: Path
) -> None:
    sonuc = await call(registry, ctx, sorgu="kaydet", path=str(proje))
    assert "def kaydet(" in sonuc.content
    assert sonuc.detail["tanim"] >= 2
    assert sonuc.detail["kesin"] is True


async def test_the_tool_refuses_free_text(
    registry: ToolRegistry, ctx: ToolContext, proje: Path
) -> None:
    """Boşluklu sorgu bir sembol adı değil; doğru araç `grep`."""
    sonuc = await call(registry, ctx, sorgu="veri kaydedilemedi", path=str(proje))
    assert sonuc.is_error
    assert "`grep`" in sonuc.content


async def test_the_tool_accepts_a_file_path(
    registry: ToolRegistry, ctx: ToolContext, proje: Path
) -> None:
    """Model elindeki tek şeyi verir: dosyanın yolu."""
    sonuc = await call(registry, ctx, sorgu="Depo", path=str(proje / "depo.py"))
    assert "class Depo" in sonuc.content


async def test_the_tool_can_show_definitions_only(
    registry: ToolRegistry, ctx: ToolContext, proje: Path
) -> None:
    sonuc = await call(registry, ctx, sorgu="kaydet", path=str(proje), tur="tanim")
    assert "tanım" in sonuc.content
    assert "kullanım" not in sonuc.content


async def test_the_tool_rejects_a_missing_folder(
    registry: ToolRegistry, ctx: ToolContext, tmp_path: Path
) -> None:
    sonuc = await call(registry, ctx, sorgu="x", path=str(tmp_path / "yok" / "yok"))
    assert sonuc.is_error


def test_the_description_admits_its_limits(registry: ToolRegistry) -> None:
    aciklama = registry.get("semboller").description
    assert "kesin" in aciklama
    assert "yapısal arama YOKTUR" in aciklama
    assert "`grep`" in aciklama
