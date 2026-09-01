"""Kod tanıları: yazılan dosya, yazıldığı anda denetleniyor mu?

Sınanan vaat şu: ajan bir dosyayı yazdıktan sonra hatayı ANINDA görmeli.
"Yazdım, çalıştırmadım, bitti dedim" sınıfı hatalar (bildirilen dönüş tipiyle
uyuşmayan bir return, kapanmamış parantez, tanımsız isim) tur kapanmadan
modelin önüne düşmeli.

İkinci vaat dürüstlük: tanı asla hata uydurmaz ve asla "her şey yolunda"
demez. Denetleyici yoksa bunu söyler; kapsamı dışındaki hata sınıflarını
temiz sonucun yanında açıkça yazar.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from dornick import tanilar
from dornick.config import Config
from dornick.events import EventLog
from dornick.session import Session
from dornick.tools import ToolContext, ToolRegistry
from dornick.tools import files as file_tools

PHP = tanilar.denetleyici_yolu("php")
NODE = tanilar.denetleyici_yolu("node")

php_gerekli = pytest.mark.skipif(PHP is None, reason="php bu makinede yok")
node_gerekli = pytest.mark.skipif(NODE is None, reason="node bu makinede yok")


@pytest.fixture()
def ctx(tmp_path: Path) -> ToolContext:
    config = Config.load(tmp_path)
    config.ensure_dirs()
    return ToolContext(
        config=config,
        session=Session(EventLog(tmp_path / ".dornick" / "s.jsonl"), "test-tani"),
        cancel=asyncio.Event(),
    )


@pytest.fixture()
def registry() -> ToolRegistry:
    reg = ToolRegistry()
    file_tools.register(reg)
    return reg


async def call(registry: ToolRegistry, name: str, ctx: ToolContext, **args):
    return await registry.get(name).handler(args, ctx)


# -- dil seçimi ---------------------------------------------------------


def test_unknown_extension_stays_silent(tmp_path: Path) -> None:
    """Tanımadığımız uzantıda hiçbir şey söylenmez — uydurma hata yok."""
    yol = tmp_path / "notlar.rtf"
    yol.write_text("bu bir kod bile degil {{{", encoding="utf-8")

    assert tanilar.dil_bul(yol) is None
    assert tanilar.denetle(yol) is None


def test_jsx_is_deliberately_not_checked(tmp_path: Path) -> None:
    """`node --check` JSX'i tanımaz; sapasağlam dosyaya hata uydururdu."""
    yol = tmp_path / "Bilesen.jsx"
    yol.write_text("const A = () => <div>merhaba</div>;\n", encoding="utf-8")

    assert tanilar.denetle(yol) is None


def test_a_missing_file_is_not_an_error(tmp_path: Path) -> None:
    assert tanilar.denetle(tmp_path / "yok.py") is None


def test_a_huge_file_is_skipped_honestly(tmp_path: Path) -> None:
    yol = tmp_path / "kocaman.js"
    yol.write_text("x=1;\n" * 500_000, encoding="utf-8")

    tani = tanilar.denetle(yol)
    assert tani is not None and tani.durum == "yok"
    assert "büyük" in tani.neden


# -- python -------------------------------------------------------------


def test_broken_python_is_caught_with_a_line_number(tmp_path: Path) -> None:
    yol = tmp_path / "bozuk.py"
    yol.write_text("def f():\n    return (1, 2\n\nprint('x')\n", encoding="utf-8")

    tani = tanilar.denetle(yol)
    assert tani is not None
    assert tani.durum == "hata"
    assert tani.bulgular
    assert tani.bulgular[0].satir > 0
    assert "satır" in tani.metin()


def test_clean_python_never_claims_everything_is_fine(tmp_path: Path) -> None:
    yol = tmp_path / "temiz.py"
    yol.write_text("def f():\n    return 1\n", encoding="utf-8")

    tani = tanilar.denetle(yol)
    assert tani is not None and tani.durum == "temiz"
    metin = tani.metin()
    # "Denetleyici hata görmedi" der; "kod çalışıyor" DEMEZ.
    assert "hata görmedi" in metin
    assert tani.kapsam  # neyi göremediği yazılı


def test_python_null_byte_is_reported_not_crashed(tmp_path: Path) -> None:
    yol = tmp_path / "nul.py"
    yol.write_bytes(b"x = 1\x00\n")

    tani = tanilar.denetle(yol)
    assert tani is not None and tani.durum == "hata"


# -- php ----------------------------------------------------------------


@php_gerekli
def test_broken_php_is_caught(tmp_path: Path) -> None:
    yol = tmp_path / "bozuk.php"
    yol.write_text(
        '<?php\nclass C {\n    public function f(): string { return "x"\n}\n',
        encoding="utf-8",
    )

    tani = tanilar.denetle(yol)
    assert tani is not None and tani.durum == "hata"
    assert tani.bulgular[0].satir == 4
    assert "syntax error" in tani.bulgular[0].mesaj


@php_gerekli
def test_php_catches_a_void_function_returning_a_value(tmp_path: Path) -> None:
    """`php -l` sözdiziminin ötesinde derleme zamanı ölümcül hatalarını da görür."""
    yol = tmp_path / "void.php"
    yol.write_text(
        "<?php\nclass C {\n    public function f(): void { return 1; }\n}\n",
        encoding="utf-8",
    )

    tani = tanilar.denetle(yol)
    assert tani is not None and tani.durum == "hata"
    assert "void" in tani.bulgular[0].mesaj.lower()


@php_gerekli
def test_php_says_out_loud_what_it_cannot_see(tmp_path: Path) -> None:
    """Bugünkü gerçek hata: `: string` deyip redirect() döndürmek.

    `php -l` bunu GÖRMEZ — ve tanı bunu saklamak yerine temiz sonucun
    yanında açıkça yazar. Yalancı bir "temiz" en tehlikeli çıktı olurdu.
    """
    yol = tmp_path / "Tip.php"
    yol.write_text(
        "<?php\nclass C {\n    public function index(): string "
        "{ return redirect(); }\n}\n",
        encoding="utf-8",
    )

    tani = tanilar.denetle(yol)
    assert tani is not None and tani.durum == "temiz"
    assert "tip hataları" in tani.kapsam
    assert "tip hataları" in tani.metin()


def test_php_without_the_checker_is_honest(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(tanilar, "denetleyici_yolu", lambda ad: None)
    yol = tmp_path / "a.php"
    yol.write_text("<?php echo 1;\n", encoding="utf-8")

    tani = tanilar.denetle(yol)
    assert tani is not None and tani.durum == "yok"
    assert "bulunamadı" in tani.neden
    assert "kontrol edilemedi" in tani.metin()


# -- js / json / yaml ---------------------------------------------------


@node_gerekli
def test_broken_js_is_caught(tmp_path: Path) -> None:
    yol = tmp_path / "bozuk.js"
    yol.write_text("function f() {\n  const x = ;\n}\n", encoding="utf-8")

    tani = tanilar.denetle(yol)
    assert tani is not None and tani.durum == "hata"
    assert tani.bulgular[0].satir == 2
    assert "SyntaxError" in tani.bulgular[0].mesaj


@node_gerekli
def test_clean_js_is_clean(tmp_path: Path) -> None:
    yol = tmp_path / "temiz.js"
    yol.write_text("const x = 1;\nconsole.log(x);\n", encoding="utf-8")

    tani = tanilar.denetle(yol)
    assert tani is not None and tani.durum == "temiz"


def test_broken_json_gets_a_line(tmp_path: Path) -> None:
    yol = tmp_path / "ayar.json"
    yol.write_text('{\n  "a": 1,\n  "b":\n}\n', encoding="utf-8")

    tani = tanilar.denetle(yol)
    assert tani is not None and tani.durum == "hata"
    assert tani.bulgular[0].satir == 4


def test_clean_json_is_clean(tmp_path: Path) -> None:
    yol = tmp_path / "ayar.json"
    yol.write_text('{"a": 1}\n', encoding="utf-8")

    tani = tanilar.denetle(yol)
    assert tani is not None and tani.durum == "temiz"


def test_broken_yaml_gets_a_line(tmp_path: Path) -> None:
    pytest.importorskip("yaml")
    yol = tmp_path / "iş.yaml"
    yol.write_text("a: 1\n  b: 2\n", encoding="utf-8")

    tani = tanilar.denetle(yol)
    assert tani is not None and tani.durum == "hata"
    assert tani.bulgular[0].satir >= 1


def test_typescript_without_a_project_says_so(tmp_path: Path) -> None:
    """tsconfig yoksa tek dosyayı derlemek uydurma hata üretirdi."""
    yol = tmp_path / "a.ts"
    yol.write_text("const x: number = 1;\n", encoding="utf-8")

    tani = tanilar.denetle(yol)
    assert tani is not None and tani.durum == "yok"
    assert "tsconfig" in tani.neden


# -- ayrıştırıcılar (denetleyici kurulu olmasa da sınanır) --------------


def test_the_php_parser_reads_a_real_lint_line() -> None:
    cikti = (
        'PHP Parse error:  syntax error, unexpected token "}", expecting ";" '
        "in C:\\site\\Home.php on line 12\n"
        "Errors parsing C:\\site\\Home.php"
    )
    bulgular = tanilar._php_bulgulari(cikti)
    assert len(bulgular) == 1
    assert bulgular[0].satir == 12
    assert bulgular[0].mesaj.startswith("syntax error")


def test_the_php_parser_reports_a_doubled_error_once() -> None:
    """php aynı hatayı önekli ve öneksiz iki kez basar; modele bir kez gitsin."""
    cikti = (
        "PHP Parse error:  syntax error in a.php on line 3\n"
        "\nParse error: syntax error in a.php on line 3\n"
        "Errors parsing a.php"
    )
    assert len(tanilar._php_bulgulari(cikti)) == 1


def test_the_ruff_parser_survives_a_windows_drive_letter() -> None:
    cikti = (
        "D:\\proje\\src\\a.py:7:5: F821 Undefined name `foo`\n"
        "D:\\proje\\src\\a.py:1:1: F401 `os` imported but unused\n"
    )
    bulgular = tanilar._py_bulgulari(cikti)
    assert [b.satir for b in bulgular] == [7, 1]
    assert "F821" in bulgular[0].mesaj


def test_the_tsc_parser_reads_a_diagnostic_line() -> None:
    cikti = "src/app.ts(12,5): error TS2322: Type 'string' is not assignable.\n"
    bulgular = tanilar._ts_bulgulari(cikti)
    assert len(bulgular) == 1 and bulgular[0].satir == 12
    assert "TS2322" in bulgular[0].mesaj


def test_the_node_parser_reads_the_location_and_the_message() -> None:
    cikti = (
        "D:\\proje\\bozuk.js:2\n  const x = ;\n            ^\n\n"
        "SyntaxError: Unexpected token ';'\n    at wrapSafe (node:internal)\n"
    )
    bulgular = tanilar._node_bulgulari(cikti)
    assert len(bulgular) == 1 and bulgular[0].satir == 2


# -- zaman aşımı --------------------------------------------------------


def test_a_slow_checker_is_reported_as_unchecked(tmp_path: Path, monkeypatch) -> None:
    """Denetleyici takılırsa yazma durmaz; dürüstçe 'kontrol edilemedi' denir."""
    monkeypatch.setattr(tanilar, "denetleyici_yolu", lambda ad: "sahte-php")
    monkeypatch.setattr(tanilar, "_kos", lambda komut, zaman_asimi: None)
    yol = tmp_path / "yavas.php"
    yol.write_text("<?php echo 1;\n", encoding="utf-8")

    tani = tanilar.denetle(yol, zaman_asimi=0.01)
    assert tani.durum == "yok"
    assert "bitmedi" in tani.neden


def test_a_crashing_checker_never_invents_a_finding(tmp_path: Path, monkeypatch) -> None:
    def patla(*_a, **_k):
        raise RuntimeError("denetleyici çöktü")

    monkeypatch.setitem(tanilar._DENETLEYICILER, "php", patla)
    yol = tmp_path / "a.php"
    yol.write_text("<?php echo 1;\n", encoding="utf-8")

    tani = tanilar.denetle(yol)
    assert tani.durum == "yok" and not tani.bulgular


# -- yazma araçlarıyla bütünleşme ---------------------------------------


async def test_write_file_hands_the_error_back_to_the_model(
    registry: ToolRegistry, ctx: ToolContext
) -> None:
    """Çekirdek senaryo: bozuk dosya yazıldı, hata AYNI cevapta döndü."""
    sonuc = await call(
        registry, "write_file", ctx,
        path="bozuk.py", content="def f():\n    return (1, 2\n",
    )

    assert not sonuc.is_error  # dosya gerçekten yazıldı
    assert "yazıldı" in sonuc.content
    assert "tanı:" in sonuc.content
    assert "satır 2" in sonuc.content
    assert "Düzeltmeden devam etme" in sonuc.content
    assert sonuc.detail["tani"]["durum"] == "hata"
    assert sonuc.detail["tani"]["bulgular"][0]["satir"] == 2


async def test_write_file_reports_a_clean_check_in_one_line(
    registry: ToolRegistry, ctx: ToolContext
) -> None:
    sonuc = await call(
        registry, "write_file", ctx, path="temiz.py", content="x = 1\n"
    )

    assert "tanı: temiz" in sonuc.content
    assert sonuc.detail["tani"]["durum"] == "temiz"


async def test_write_file_says_nothing_for_an_unknown_language(
    registry: ToolRegistry, ctx: ToolContext
) -> None:
    sonuc = await call(
        registry, "write_file", ctx, path="notlar.txt", content="merhaba {{{\n"
    )

    assert "tanı" not in sonuc.content
    assert "tani" not in sonuc.detail


async def test_edit_file_checks_what_the_edit_produced(
    registry: ToolRegistry, ctx: ToolContext
) -> None:
    """Düzenleme dosyayı bozarsa bu, düzenlemenin cevabında görünmeli."""
    await call(registry, "write_file", ctx, path="a.py", content="x = 1\ny = 2\n")
    await call(registry, "read_file", ctx, path="a.py")

    sonuc = await call(registry, "edit_file", ctx, path="a.py", old="y = 2", new="y = (2")

    assert "güncellendi" in sonuc.content
    assert sonuc.detail["tani"]["durum"] == "hata"
    assert "tanı:" in sonuc.content


async def test_a_broken_write_is_still_a_write(
    registry: ToolRegistry, ctx: ToolContext
) -> None:
    """Tanı yazmayı geçersiz kılmaz: dosya diskte, sonuç hata değil.

    Aksi halde model dosyanın yazılmadığını sanıp baştan yazardı."""
    await call(registry, "write_file", ctx, path="b.py", content="def f(:\n")

    assert (ctx.sandbox.root / "b.py").read_text(encoding="utf-8") == "def f(:\n"


async def test_a_failed_write_gets_no_diagnosis(
    registry: ToolRegistry, ctx: ToolContext
) -> None:
    """Bayatlık reddi bir yazma değildir; tanı da koşmamalı."""
    (ctx.sandbox.root / "c.py").write_text("x = 1\n", encoding="utf-8")

    sonuc = await call(registry, "write_file", ctx, path="c.py", content="y = (2\n")

    assert sonuc.is_error
    assert "tanı" not in sonuc.content


# -- elle denetim aracı -------------------------------------------------


async def test_the_manual_tool_checks_the_last_written_file(
    registry: ToolRegistry, ctx: ToolContext
) -> None:
    await call(registry, "write_file", ctx, path="son.py", content="def f(:\n")

    sonuc = await call(registry, "denetle", ctx)

    assert "son.py" in sonuc.content
    assert sonuc.detail["hatali"] == 1


async def test_the_manual_tool_without_a_target_is_honest(
    registry: ToolRegistry, ctx: ToolContext
) -> None:
    sonuc = await call(registry, "denetle", ctx)

    assert sonuc.is_error
    assert "henüz bir dosya yazmadın" in sonuc.content


async def test_the_manual_tool_walks_a_folder(
    registry: ToolRegistry, ctx: ToolContext
) -> None:
    await call(registry, "write_file", ctx, path="proje/iyi.py", content="x = 1\n")
    await call(registry, "write_file", ctx, path="proje/kotu.py", content="def f(:\n")
    await call(registry, "write_file", ctx, path="proje/okuma.md", content="# not\n")

    sonuc = await call(registry, "denetle", ctx, path="proje")

    assert "kotu.py" in sonuc.content
    assert sonuc.detail["hatali"] == 1
    # Temiz dosya sayılır ama "sağlam" ilan edilmez.
    assert "çalıştığı anlamına gelmez" in sonuc.content


async def test_the_manual_tool_narrows_with_a_pattern(
    registry: ToolRegistry, ctx: ToolContext
) -> None:
    await call(registry, "write_file", ctx, path="p/a.py", content="def f(:\n")
    await call(registry, "write_file", ctx, path="p/b.json", content="{oops}\n")

    sonuc = await call(registry, "denetle", ctx, path="p", pattern="*.json")

    assert sonuc.detail["hatali"] == 1
    assert "a.py" not in sonuc.content


async def test_the_manual_tool_skips_dependency_folders(
    registry: ToolRegistry, ctx: ToolContext
) -> None:
    """node_modules/vendor taramak ne kullanıcının istediği ne ajanın yazdığı."""
    kok = ctx.sandbox.root / "site"
    (kok / "node_modules").mkdir(parents=True)
    (kok / "node_modules" / "x.js").write_text("var = ;", encoding="utf-8")
    (kok / "app.py").write_text("x = 1\n", encoding="utf-8")

    yollar = tanilar.toplu_yollar(kok)
    assert [y.name for y in yollar] == ["app.py"]


async def test_the_manual_tool_refuses_a_missing_path(
    registry: ToolRegistry, ctx: ToolContext
) -> None:
    sonuc = await call(registry, "denetle", ctx, path="olmayan/yer.py")

    assert sonuc.is_error and "Yol yok" in sonuc.content


async def test_the_manual_tool_admits_an_unknown_language(
    registry: ToolRegistry, ctx: ToolContext
) -> None:
    await call(registry, "write_file", ctx, path="not.txt", content="merhaba\n")

    sonuc = await call(registry, "denetle", ctx, path="not.txt")

    assert "denetleyici tanımıyorum" in sonuc.content


# -- denetleyici bulma --------------------------------------------------


def test_the_finder_looks_beyond_path(monkeypatch, tmp_path: Path) -> None:
    """PATH'te olmayan ama kurulu bir php'yi bulabilmeli (winget/XAMPP)."""
    sahte = tmp_path / "php.exe"
    sahte.write_text("", encoding="utf-8")
    monkeypatch.setattr("shutil.which", lambda ad: None)
    monkeypatch.setitem(
        tanilar._EK_YERLER, "php", (str(tmp_path / "*.exe"),)
    )
    tanilar.denetleyici_yolu.cache_clear()
    try:
        assert tanilar.denetleyici_yolu("php") == str(sahte)
    finally:
        tanilar.denetleyici_yolu.cache_clear()


def test_the_finder_returns_none_for_a_ghost() -> None:
    tanilar.denetleyici_yolu.cache_clear()
    try:
        assert tanilar.denetleyici_yolu("boyle-bir-arac-yok-12345") is None
    finally:
        tanilar.denetleyici_yolu.cache_clear()
