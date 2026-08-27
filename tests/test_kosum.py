"""Proje test koşucusu: ajan yazdığı kodu gerçekten çalıştırıyor mu?

Sınanan vaat: `denetle` sözdizimine bakar, `kos` kodu ÇALIŞTIRIR. Aradaki
boşluk kullanıcının ekranında patlayan hata sınıfıydı —

    public function index(): string { return redirect(); }

`php -l` bunu temiz bulur, tarayıcı TypeError verir.

Üç şey ayrı ayrı doğrulanıyor:

  1. TESPİT kanıta dayalı: yapılandırma dosyası yoksa komut da yok. Uydurma
     komut, olmayan bir güvenceden beter.
  2. NORMALLEŞTİRME gerçek çıktı metinleriyle sınanıyor — pytest, phpunit,
     jest, mocha, go, cargo, dotnet bu makinede kurulu olmasa da çıktılarını
     doğru okuduğumuzu ancak böyle kanıtlayabiliyoruz.
  3. DÜRÜSTLÜK: hiçbir metin "her şey çalışıyor" demiyor.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

import pytest

from neocp import kosum
from neocp.config import Config
from neocp.events import EventLog
from neocp.session import Session
from neocp.tools import ToolContext, ToolRegistry
from neocp.tools import kosucu as kos_tools


@pytest.fixture()
def ctx(tmp_path: Path) -> ToolContext:
    config = Config.load(tmp_path)
    config.ensure_dirs()
    return ToolContext(
        config=config,
        session=Session(EventLog(tmp_path / ".neocp" / "s.jsonl"), "test-kos"),
        cancel=asyncio.Event(),
    )


@pytest.fixture()
def registry() -> ToolRegistry:
    reg = ToolRegistry()
    kos_tools.register(reg)
    return reg


@pytest.fixture(autouse=True)
def temiz_hafiza():
    """Modül düzeyindeki "son dokunulan proje" testler arasında sızmasın."""
    kosum.unut()
    yield
    kosum.unut()


async def call(registry: ToolRegistry, ctx: ToolContext, **args):
    return await registry.get("kos").handler(args, ctx)


# -- tespit: python -----------------------------------------------------


def test_pytest_ini_is_evidence(tmp_path: Path) -> None:
    (tmp_path / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    duzenek = kosum.tespit(tmp_path)
    assert duzenek is not None
    assert duzenek.ekosistem == "python"
    assert duzenek.argv[1:] == ["-m", "pytest", "-q"]
    assert duzenek.kanit == "pytest.ini"
    assert duzenek.guven == 2


def test_pyproject_pytest_section_is_evidence(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\n\n[tool.pytest.ini_options]\ntestpaths = ["tests"]\n',
        encoding="utf-8",
    )
    duzenek = kosum.tespit(tmp_path)
    assert duzenek is not None and duzenek.ekosistem == "python"
    assert "pyproject.toml" in duzenek.kanit


def test_pyproject_without_pytest_is_not_evidence(tmp_path: Path) -> None:
    """pyproject'in varlığı pytest'in varlığı değildir."""
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\n', encoding="utf-8")
    assert kosum.tespit(tmp_path) is None


def test_tests_folder_is_weaker_evidence(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_a.py").write_text("def test_a(): pass\n", encoding="utf-8")
    duzenek = kosum.tespit(tmp_path)
    assert duzenek is not None and duzenek.guven == 1


def test_tests_folder_without_test_files_is_not_evidence(tmp_path: Path) -> None:
    """`tests/` altında belge de durabiliyor; test dosyası yoksa kanıt yok."""
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "veriler.json").write_text("{}", encoding="utf-8")
    (tmp_path / "tests" / "yardimci.py").write_text("x = 1\n", encoding="utf-8")
    assert kosum.tespit(tmp_path) is None


def test_python_command_matches_platform(tmp_path: Path) -> None:
    (tmp_path / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    duzenek = kosum.tespit(tmp_path)
    beklenen = "py -m pytest -q" if sys.platform == "win32" else "python3 -m pytest -q"
    assert duzenek is not None and duzenek.etiket == beklenen


# -- tespit: node -------------------------------------------------------


def _paket(tmp_path: Path, betikler: dict) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps({"name": "x", "scripts": betikler}), encoding="utf-8")


def test_package_json_test_script_is_evidence(tmp_path: Path) -> None:
    _paket(tmp_path, {"test": "jest", "build": "vite build", "dev": "vite"})
    (tmp_path / "node_modules").mkdir()
    duzenek = kosum.tespit(tmp_path)
    assert duzenek is not None
    assert duzenek.ekosistem == "node" and duzenek.etiket == "npm test"
    assert "scripts.test = jest" in duzenek.kanit
    # build/dev komut olarak önerilmiyor ama model bilsin diye not düşülüyor.
    assert any("build" in n and "dev" in n for n in duzenek.notlar)


def test_npm_placeholder_test_script_is_not_evidence(tmp_path: Path) -> None:
    """`npm init`in bıraktığı yer tutucu bir test düzeneği değildir."""
    _paket(tmp_path, {"test": 'echo "Error: no test specified" && exit 1'})
    assert kosum.tespit(tmp_path) is None


def test_package_json_without_test_script_is_not_evidence(tmp_path: Path) -> None:
    _paket(tmp_path, {"build": "vite build"})
    assert kosum.tespit(tmp_path) is None


def test_missing_node_modules_is_reported_not_prescribed(tmp_path: Path) -> None:
    """Bağımlılık yoksa BİLDİRİLİR; kurulum önerilmez."""
    _paket(tmp_path, {"test": "jest"})
    duzenek = kosum.tespit(tmp_path)
    assert duzenek is not None
    assert not duzenek.kosulabilir
    assert "node_modules" in duzenek.engel
    assert "npm install" not in duzenek.engel.lower()


def test_broken_package_json_is_not_evidence(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text("{ bozuk", encoding="utf-8")
    assert kosum.tespit(tmp_path) is None


# -- tespit: php --------------------------------------------------------


@pytest.mark.parametrize("ad", ["phpunit.xml", "phpunit.xml.dist", "phpunit.dist.xml"])
def test_phpunit_configuration_names(tmp_path: Path, ad: str) -> None:
    """CodeIgniter 4 `phpunit.dist.xml` kullanıyor — üç ad da tanınmalı."""
    (tmp_path / ad).write_text("<phpunit/>", encoding="utf-8")
    (tmp_path / "vendor" / "bin").mkdir(parents=True)
    (tmp_path / "vendor" / "bin" / "phpunit").write_text("#!/usr/bin/env php\n",
                                                         encoding="utf-8")
    duzenek = kosum.tespit(tmp_path)
    assert duzenek is not None
    assert duzenek.ekosistem == "php"
    assert duzenek.etiket == "php vendor/bin/phpunit"
    assert duzenek.kosulabilir


def test_phpunit_config_without_vendor_is_blocked(tmp_path: Path) -> None:
    (tmp_path / "phpunit.xml").write_text("<phpunit/>", encoding="utf-8")
    duzenek = kosum.tespit(tmp_path)
    assert duzenek is not None and not duzenek.kosulabilir
    assert "vendor/bin/phpunit" in duzenek.engel


def test_spark_is_a_health_command_not_a_test_suite(tmp_path: Path) -> None:
    """phpunit yoksa CI4'te ucuz sağlık komutu — ama test diye sunulmuyor."""
    (tmp_path / "spark").write_text("#!/usr/bin/env php\n", encoding="utf-8")
    duzenek = kosum.tespit(tmp_path)
    assert duzenek is not None
    assert duzenek.tur == "saglik"
    assert duzenek.etiket == "php spark routes"


def test_phpunit_beats_spark(tmp_path: Path) -> None:
    (tmp_path / "spark").write_text("#!/usr/bin/env php\n", encoding="utf-8")
    (tmp_path / "phpunit.dist.xml").write_text("<phpunit/>", encoding="utf-8")
    (tmp_path / "vendor" / "bin").mkdir(parents=True)
    (tmp_path / "vendor" / "bin" / "phpunit").write_text("x", encoding="utf-8")
    duzenek = kosum.tespit(tmp_path)
    assert duzenek is not None and duzenek.tur == "test"


# -- tespit: go / rust / dotnet ----------------------------------------


def test_go_mod(tmp_path: Path) -> None:
    (tmp_path / "go.mod").write_text("module example.com/x\n", encoding="utf-8")
    duzenek = kosum.tespit(tmp_path)
    assert duzenek is not None and duzenek.etiket == "go test ./..."


def test_cargo_toml(tmp_path: Path) -> None:
    (tmp_path / "Cargo.toml").write_text("[package]\nname = 'x'\n", encoding="utf-8")
    duzenek = kosum.tespit(tmp_path)
    assert duzenek is not None and duzenek.etiket == "cargo test"


def test_dotnet_project(tmp_path: Path) -> None:
    (tmp_path / "Uygulama.csproj").write_text("<Project/>", encoding="utf-8")
    duzenek = kosum.tespit(tmp_path)
    assert duzenek is not None and duzenek.etiket == "dotnet test"


# -- tespit: hiçbiri ----------------------------------------------------


def test_empty_folder_yields_nothing(tmp_path: Path) -> None:
    """En önemli test: kanıt yoksa komut da yok."""
    assert kosum.tespit(tmp_path) is None
    assert kosum.tespit_hepsi(tmp_path) == []


def test_no_setup_message_refuses_to_invent(tmp_path: Path) -> None:
    metin = kosum.tespit_metni(tmp_path)
    assert "test düzeneği bulunamadı" in metin
    assert "uydurmayacağım" in metin
    assert "gerçekten çalıştır" in metin


def test_a_folder_of_source_files_alone_is_not_a_test_setup(tmp_path: Path) -> None:
    (tmp_path / "index.php").write_text("<?php echo 1;", encoding="utf-8")
    (tmp_path / "app.js").write_text("console.log(1)", encoding="utf-8")
    assert kosum.tespit(tmp_path) is None


def test_multiple_ecosystems_are_all_reported(tmp_path: Path) -> None:
    """PHP arka uç + npm ile derlenen ön yüz: ikisi de görünmeli."""
    (tmp_path / "phpunit.xml").write_text("<phpunit/>", encoding="utf-8")
    (tmp_path / "vendor" / "bin").mkdir(parents=True)
    (tmp_path / "vendor" / "bin" / "phpunit").write_text("x", encoding="utf-8")
    _paket(tmp_path, {"test": "vitest"})
    (tmp_path / "node_modules").mkdir()
    hepsi = kosum.tespit_hepsi(tmp_path)
    assert {d.ekosistem for d in hepsi} == {"php", "node"}


# -- proje kökü ---------------------------------------------------------


def test_project_root_is_found_from_a_nested_file(tmp_path: Path) -> None:
    """Model elindeki tek şeyi verir: az önce yazdığı dosyanın yolu."""
    (tmp_path / "composer.json").write_text("{}", encoding="utf-8")
    derin = tmp_path / "app" / "Controllers"
    derin.mkdir(parents=True)
    dosya = derin / "Home.php"
    dosya.write_text("<?php", encoding="utf-8")
    assert kosum.proje_koku(dosya) == tmp_path


def test_project_root_falls_back_to_the_folder_itself(tmp_path: Path) -> None:
    """Hiçbir iz yoksa uydurma bir üst klasöre tırmanmıyoruz."""
    derin = tmp_path / "a" / "b"
    derin.mkdir(parents=True)
    assert kosum.proje_koku(derin) == derin


# -- normalleştirme: pytest --------------------------------------------

PYTEST_BASARISIZ = """\
..F..                                                                    [100%]
=================================== FAILURES ===================================
_________________________________ test_toplama _________________________________

    def test_toplama():
>       assert topla(1, 2) == 4
E       assert 3 == 4

tests/test_hesap.py:12: AssertionError
=========================== short test summary info ============================
FAILED tests/test_hesap.py::test_toplama - assert 3 == 4
1 failed, 4 passed in 0.42s
"""

PYTEST_TEMIZ = """\
.........................................................................
978 passed, 3 skipped in 45.12s
"""


def test_pytest_failure_output(tmp_path: Path) -> None:
    sayim, basarisizlar = kosum.normalize("python", PYTEST_BASARISIZ)
    assert (sayim.gecen, sayim.kalan, sayim.okundu) == (4, 1, True)
    assert len(basarisizlar) == 1
    assert basarisizlar[0].ad == "tests/test_hesap.py::test_toplama"
    assert basarisizlar[0].mesaj == "assert 3 == 4"
    assert basarisizlar[0].yer == "tests/test_hesap.py:12"


def test_pytest_clean_output(tmp_path: Path) -> None:
    sayim, basarisizlar = kosum.normalize("python", PYTEST_TEMIZ)
    assert (sayim.gecen, sayim.kalan, sayim.atlanan) == (978, 0, 3)
    assert basarisizlar == []


def test_pytest_error_line_counts_as_failure() -> None:
    cikti = ("ERROR tests/test_x.py::test_y - ImportError: yok\n"
             "1 error in 0.10s\n")
    sayim, basarisizlar = kosum.normalize("python", cikti)
    assert sayim.kalan == 1 and sayim.okundu
    assert basarisizlar[0].mesaj == "ImportError: yok"


def test_pytest_no_tests_ran() -> None:
    sayim, _ = kosum.normalize("python", "no tests ran in 0.01s\n")
    assert sayim.okundu and sayim.toplam == 0


# -- normalleştirme: phpunit -------------------------------------------

PHPUNIT_BASARISIZ = """\
PHPUnit 10.5.11 by Sebastian Bergmann and contributors.

Runtime:       PHP 8.2.12
Configuration: C:\\atolye\\cms\\phpunit.dist.xml

..F.                                                                4 / 4 (100%)

Time: 00:00.312, Memory: 12.00 MB

There was 1 failure:

1) App\\Tests\\HomeTest::testIndexReturnsString
Failed asserting that null is of type string.

C:\\atolye\\cms\\tests\\HomeTest.php:23

FAILURES!
Tests: 4, Assertions: 6, Failures: 1.
"""

PHPUNIT_TEMIZ = """\
PHPUnit 10.5.11 by Sebastian Bergmann and contributors.

....                                                                4 / 4 (100%)

Time: 00:00.201, Memory: 12.00 MB

OK (4 tests, 6 assertions)
"""


def test_phpunit_failure_output() -> None:
    sayim, basarisizlar = kosum.normalize("php", PHPUNIT_BASARISIZ)
    assert (sayim.toplam, sayim.gecen, sayim.kalan) == (4, 3, 1)
    assert sayim.okundu
    assert len(basarisizlar) == 1
    assert basarisizlar[0].ad == "App\\Tests\\HomeTest::testIndexReturnsString"
    assert "null is of type string" in basarisizlar[0].mesaj
    assert basarisizlar[0].yer == "HomeTest.php:23"


def test_phpunit_clean_output() -> None:
    sayim, basarisizlar = kosum.normalize("php", PHPUNIT_TEMIZ)
    assert (sayim.gecen, sayim.kalan, sayim.okundu) == (4, 0, True)
    assert basarisizlar == []


def test_phpunit_errors_and_skips() -> None:
    cikti = "ERRORS!\nTests: 10, Assertions: 12, Errors: 2, Failures: 1, Skipped: 3.\n"
    sayim, _ = kosum.normalize("php", cikti)
    assert (sayim.toplam, sayim.kalan, sayim.atlanan, sayim.gecen) == (10, 3, 3, 4)


# -- normalleştirme: node ----------------------------------------------

JEST = """\
 FAIL  src/hesap.test.js
  ● Hesap › toplar

    expect(received).toBe(expected)

Test Suites: 1 failed, 1 total
Tests:       1 failed, 2 passed, 3 total
Snapshots:   0 total
Time:        1.234 s
"""

MOCHA = """\
  Hesap
    √ toplar
    1) çıkarır


  1 passing (12ms)
  1 failing

  1) Hesap
       çıkarır:
     AssertionError: expected 1 to equal 2
"""

NODE_TEST = """\
# tests 4
# suites 1
# pass 3
# fail 1
# cancelled 0
# skipped 0
"""

VITEST = """\
 Test Files  1 failed | 1 passed (2)
      Tests  1 failed | 5 passed (6)
   Start at  10:00:00
"""


def test_jest_output() -> None:
    sayim, basarisizlar = kosum.normalize("node", JEST)
    assert (sayim.gecen, sayim.kalan, sayim.toplam) == (2, 1, 3)
    assert basarisizlar and basarisizlar[0].ad == "Hesap › toplar"


def test_mocha_output() -> None:
    sayim, basarisizlar = kosum.normalize("node", MOCHA)
    assert (sayim.gecen, sayim.kalan, sayim.okundu) == (1, 1, True)
    assert basarisizlar and "çıkarır" in basarisizlar[0].ad


def test_node_test_runner_output() -> None:
    sayim, _ = kosum.normalize("node", NODE_TEST)
    assert (sayim.gecen, sayim.kalan, sayim.toplam) == (3, 1, 4)


def test_vitest_output() -> None:
    sayim, _ = kosum.normalize("node", VITEST)
    assert (sayim.gecen, sayim.kalan) == (5, 1)


def test_unreadable_node_output_admits_it() -> None:
    """Tanımadığımız koşucuda uydurma sayı yok — `okundu` False kalır."""
    sayim, _ = kosum.normalize("node", "bilinmeyen koşucu bir şeyler yazdı\n")
    assert not sayim.okundu


# -- normalleştirme: go / cargo / dotnet -------------------------------

GO = """\
--- FAIL: TestTopla (0.00s)
    hesap_test.go:14: 3 bekleniyordu, 4 geldi
--- PASS: TestCikar (0.00s)
FAIL
FAIL    example.com/hesap  0.123s
"""

CARGO = """\
running 4 tests
test tests::cikar ... ok
test tests::topla ... FAILED

failures:

    tests::topla

test result: FAILED. 3 passed; 1 failed; 0 ignored; 0 measured; 0 filtered out
"""

DOTNET = """\
Failed!  - Failed:     1, Passed:     2, Skipped:     0, Total:     3, Duration: 5 ms
"""


def test_go_output() -> None:
    sayim, basarisizlar = kosum.normalize("go", GO)
    assert (sayim.gecen, sayim.kalan) == (1, 1)
    assert basarisizlar[0].ad == "TestTopla"
    assert basarisizlar[0].yer == "hesap_test.go:14"


def test_cargo_output() -> None:
    sayim, basarisizlar = kosum.normalize("rust", CARGO)
    assert (sayim.gecen, sayim.kalan) == (3, 1)
    assert basarisizlar and basarisizlar[0].ad == "tests::topla"


def test_dotnet_output() -> None:
    sayim, _ = kosum.normalize("dotnet", DOTNET)
    assert (sayim.gecen, sayim.kalan, sayim.toplam) == (2, 1, 3)


def test_auto_detection_picks_the_right_reader() -> None:
    """Elle verilen komutta hangi koşucunun konuştuğunu bilmiyoruz."""
    sayim, _ = kosum.normalize("oto", PYTEST_TEMIZ)
    assert sayim.gecen == 978
    sayim, _ = kosum.normalize("oto", PHPUNIT_TEMIZ)
    assert sayim.gecen == 4


# -- kırpma -------------------------------------------------------------


def test_long_output_keeps_head_and_tail() -> None:
    metin = "BAS\n" + ("x" * 20000) + "\nSON"
    kirpik = kosum.kirp(metin, limit=400)
    assert kirpik.startswith("BAS")
    assert kirpik.endswith("SON")
    assert "kırpıldı" in kirpik
    assert len(kirpik) < 600


def test_short_output_is_untouched() -> None:
    assert kosum.kirp("kısa çıktı") == "kısa çıktı"


# -- dürüstlük metinleri -----------------------------------------------


def _sonuc(**kw) -> kosum.Sonuc:
    temel = dict(ekosistem="python", etiket="py -m pytest -q", kok="C:/x",
                 durum="kostu")
    temel.update(kw)
    return kosum.Sonuc(**temel)


def test_a_green_run_never_claims_everything_works() -> None:
    sonuc = _sonuc(sayim=kosum.Sayim(gecen=12, toplam=12, okundu=True))
    metin = sonuc.metin()
    assert "12 geçti, 0 kaldı" in metin
    assert "koşulan testlerin kapsadığı kadarını doğrular" in metin
    assert "her şey" not in metin.lower()
    assert "denenmemiş" in metin


def test_a_red_run_says_do_not_call_it_done() -> None:
    sonuc = _sonuc(cikis_kodu=1,
                   sayim=kosum.Sayim(gecen=4, kalan=1, toplam=5, okundu=True),
                   basarisizlar=[kosum.Basarisiz("test_x", "assert 3 == 4",
                                                 "tests/test_h.py:12")])
    metin = sonuc.metin()
    assert "1 kaldı" in metin
    assert "tests/test_h.py:12" in metin
    assert "'çalışıyor' deme" in metin


def test_only_five_failures_are_named() -> None:
    sonuc = _sonuc(cikis_kodu=1,
                   sayim=kosum.Sayim(kalan=9, toplam=9, okundu=True),
                   basarisizlar=[kosum.Basarisiz(f"test_{i}") for i in range(9)])
    metin = sonuc.metin()
    assert "test_4" in metin and "test_5" not in metin
    assert "4 başarısız test daha" in metin


def test_unreadable_counts_are_admitted() -> None:
    sonuc = _sonuc(sayim=kosum.Sayim(), ham="anlaşılmaz çıktı")
    metin = sonuc.metin()
    assert "Test sayısı okunamadığı için" in metin


def test_empty_suite_proves_nothing() -> None:
    sonuc = _sonuc(sayim=kosum.Sayim(okundu=True))
    assert "Hiç test koşmadı" in sonuc.metin()
    assert "gerçekten çalıştır" in sonuc.metin()


def test_health_check_is_not_sold_as_a_test() -> None:
    sonuc = _sonuc(ekosistem="php", etiket="php spark routes", tur="saglik",
                   sayim=kosum.Sayim())
    metin = sonuc.metin()
    assert "test takımı değil" in metin
    assert "Davranışın doğruluğunu göstermez" in metin


def test_timeout_text_explains_both_causes() -> None:
    sonuc = _sonuc(durum="zaman_asimi", sure=300.0)
    metin = sonuc.metin()
    assert "bitmedi ve durduruldu" in metin
    assert "zaman_asimi" in metin


# -- gerçek koşum -------------------------------------------------------


def _sahte_python_projesi(kok: Path, govde: str) -> None:
    kok.mkdir(parents=True, exist_ok=True)
    (kok / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    tests = kok / "tests"
    tests.mkdir(exist_ok=True)
    (tests / "test_ornek.py").write_text(govde, encoding="utf-8")


@pytest.fixture()
def kendi_python(monkeypatch: pytest.MonkeyPatch):
    """Uçtan uca koşumlar bu takımın Python'unu kullansın.

    Tespit `py -m pytest -q` üretiyor (kullanıcının projesi için doğrusu bu)
    ama CI makinesinde `py` başka bir yoruma işaret edip pytest'siz olabilir.
    Burada sınadığımız şey koşucunun kendisi, makinenin Python düzeni değil.
    """
    gercek = kosum._cozumle

    def sahte(ad: str) -> str | None:
        if ad in ("py", "python3", "python"):
            return sys.executable
        return gercek(ad)

    monkeypatch.setattr(kosum, "_cozumle", sahte)


async def test_a_real_passing_suite_runs(tmp_path: Path, kendi_python) -> None:
    """Uçtan uca: sahte projede gerçek pytest koşuyor ve sayılar okunuyor."""
    _sahte_python_projesi(tmp_path, "def test_gecer():\n    assert True\n")
    duzenek = kosum.tespit(tmp_path)
    assert duzenek is not None
    sonuc = await kosum.kos(duzenek, zaman_asimi=120)
    assert sonuc.durum == "kostu"
    assert sonuc.cikis_kodu == 0
    assert sonuc.sayim.okundu and sonuc.sayim.gecen == 1


async def test_a_real_failing_suite_is_reported(tmp_path: Path, kendi_python) -> None:
    """Yaranın kendisi: kod sözdizimi olarak sağlam ama davranışı yanlış."""
    _sahte_python_projesi(
        tmp_path,
        "def topla(a, b):\n"
        "    return a - b\n"     # sözdizimi temiz, davranış yanlış
        "\n"
        "def test_toplama():\n"
        "    assert topla(1, 2) == 3\n",
    )
    duzenek = kosum.tespit(tmp_path)
    assert duzenek is not None
    sonuc = await kosum.kos(duzenek, zaman_asimi=120)
    assert sonuc.cikis_kodu != 0
    assert sonuc.sayim.kalan == 1
    assert sonuc.basarisizlar
    assert "test_toplama" in sonuc.basarisizlar[0].ad


ASILAN = "import time; print('asilan_test_basladi', flush=True); time.sleep(120)"


async def test_timeout_kills_the_whole_process_tree(tmp_path: Path) -> None:
    """Hiç bitmeyen bir komut turu dondurmamalı — ve arkada da kalmamalı.

    Kabuk üzerinden koşan komutta `proc` cmd.exe/bash; asıl süreç onun
    çocuğu. Yalnızca kabuğu öldürmek koşucuyu makinede bırakıyor ve boruyu
    açık tuttuğu için çağıran taraf ÖLÇÜLEBİLİR biçimde asılı kalıyordu:
    2 saniyelik zaman aşımı, 30 saniyelik bir bekleyişe dönüşmüştü.
    """
    basla = time.monotonic()
    sonuc = await kosum.kos_komut(
        f'"{sys.executable}" -c "{ASILAN}"', tmp_path, zaman_asimi=2,
    )
    gecen = time.monotonic() - basla
    assert sonuc.durum == "zaman_asimi"
    # Asıl güvence: çağrı zaman aşımından hemen sonra dönüyor.
    assert gecen < 20, f"koşum {gecen:.0f} sn asılı kaldı"


async def test_timeout_keeps_the_partial_output(tmp_path: Path) -> None:
    """Yarım çıktı da bilgidir: son satır nerede takıldığını söyler."""
    sonuc = await kosum.kos_komut(
        f'"{sys.executable}" -c "{ASILAN}"', tmp_path, zaman_asimi=3,
    )
    assert "asilan_test_basladi" in sonuc.ham
    assert "nerede takıldığını" in sonuc.metin()


async def test_cancel_stops_the_run(tmp_path: Path) -> None:
    """Kullanıcı 'durdur' dediğinde koşan süreç ölmeli — ve öyle raporlanmalı."""
    cancel = asyncio.Event()

    async def dur() -> None:
        await asyncio.sleep(0.3)
        cancel.set()

    gorev = asyncio.ensure_future(dur())
    basla = time.monotonic()
    sonuc = await kosum.kos_komut(
        f'"{sys.executable}" -c "{ASILAN}"', tmp_path, zaman_asimi=120,
        cancel=cancel,
    )
    gecen = time.monotonic() - basla
    await gorev
    assert sonuc.durum == "kesildi"          # zaman aşımı DEĞİL
    assert "Durduruldu" in sonuc.metin()
    assert gecen < 20, f"kesme {gecen:.0f} sn sürdü"


async def test_missing_executable_is_honest(tmp_path: Path) -> None:
    duzenek = kosum.Duzenek(
        "go", "test", "go test ./...", ["kesinlikle-olmayan-arac", "test"],
        tmp_path, "go.mod",
    )
    sonuc = await kosum.kos(duzenek)
    assert sonuc.durum == "baslatilamadi"
    assert "bulunamadı" in sonuc.metin()


async def test_blocked_setup_is_not_run(tmp_path: Path) -> None:
    _paket(tmp_path, {"test": "jest"})   # node_modules yok
    duzenek = kosum.tespit(tmp_path)
    assert duzenek is not None
    sonuc = await kosum.kos(duzenek)
    assert sonuc.durum == "yok"
    assert "node_modules" in sonuc.ham


# -- yazma sonrası hatırlatma ------------------------------------------


def test_reminder_names_the_command(tmp_path: Path) -> None:
    (tmp_path / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    (tmp_path / "modul.py").write_text("x = 1\n", encoding="utf-8")
    metin = kosum.hatirlatma(tmp_path / "modul.py")
    assert "pytest -q" in metin
    assert "`kos`" in metin
    assert len(metin.splitlines()) == 1   # TEK satır: gürültü yok


def test_no_reminder_without_a_setup(tmp_path: Path) -> None:
    (tmp_path / "not.txt").write_text("selam", encoding="utf-8")
    assert kosum.hatirlatma(tmp_path / "not.txt") == ""


def test_reminder_hardens_after_repeated_writes(tmp_path: Path) -> None:
    """Aynı dosyaya üçüncü yazım: model gözle düzeltmeye çalışıyor demektir."""
    (tmp_path / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    dosya = tmp_path / "modul.py"
    dosya.write_text("x = 1\n", encoding="utf-8")
    yumusak = kosum.hatirlatma(dosya, yazim=1)
    sert = kosum.hatirlatma(dosya, yazim=3)
    assert "Gözle düzeltmeyi bırak" in sert
    assert "3. kez" in sert
    assert sert != yumusak


def test_reminder_reports_a_blocked_setup(tmp_path: Path) -> None:
    _paket(tmp_path, {"test": "jest"})
    metin = kosum.hatirlatma(tmp_path / "index.js")
    assert "node_modules" in metin


def test_reminder_marks_a_health_command_as_such(tmp_path: Path) -> None:
    (tmp_path / "spark").write_text("#!/usr/bin/env php\n", encoding="utf-8")
    metin = kosum.hatirlatma(tmp_path / "app" / "Controllers" / "Home.php")
    assert "test takımı yok" in metin
    assert "sağlık denetimi" in metin


# -- araç yüzeyi --------------------------------------------------------


def test_tool_is_registered_in_the_real_registry() -> None:
    from neocp.tools import build_registry

    assert "kos" in build_registry(subagents=False)


def test_tool_is_gated(registry: ToolRegistry) -> None:
    """Test koşmak projenin kodunu koşturur: izin kipine tabi olmalı."""
    spec = registry.get("kos")
    assert spec.mutates is True
    assert spec.parallel_safe is False


def test_manual_command_is_the_permission_subject() -> None:
    """Elle verilen komut kapıya `path` olarak görünmemeli."""
    from neocp.permissions import describe

    assert describe({"path": "C:/proje", "komut": "npm test"}) == "npm test"
    assert describe({"path": "C:/proje"}) == "C:/proje"


async def test_tool_reports_no_setup_without_erroring(
    registry: ToolRegistry, ctx: ToolContext, tmp_path: Path
) -> None:
    bos = tmp_path / "bos"
    bos.mkdir()
    sonuc = await call(registry, ctx, path=str(bos))
    assert not sonuc.is_error      # bilgi, hata değil
    assert "test düzeneği bulunamadı" in sonuc.content


async def test_tool_detection_only_mode_runs_nothing(
    registry: ToolRegistry, ctx: ToolContext, tmp_path: Path
) -> None:
    (tmp_path / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    (tmp_path / "spark").write_text("#!/usr/bin/env php\n", encoding="utf-8")
    sonuc = await call(registry, ctx, path=str(tmp_path), sadece_tespit=True)
    assert "pytest -q" in sonuc.content
    assert "php spark routes" in sonuc.content
    assert "hiçbiri koşturulmadı" in sonuc.content
    assert sonuc.detail["tespit"] is True


async def test_tool_uses_the_last_touched_project(
    registry: ToolRegistry, ctx: ToolContext, tmp_path: Path
) -> None:
    """`path` yoksa en son dosya yazılan proje."""
    proje = tmp_path / "proje"
    proje.mkdir()
    (proje / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    kosum.dokunuldu(proje / "modul.py")
    sonuc = await call(registry, ctx, sadece_tespit=True)
    assert str(proje) in sonuc.content


async def test_tool_refuses_a_missing_folder(
    registry: ToolRegistry, ctx: ToolContext, tmp_path: Path
) -> None:
    sonuc = await call(registry, ctx, path=str(tmp_path / "yok" / "burada"))
    assert sonuc.is_error
    assert "Klasör yok" in sonuc.content


async def test_tool_runs_a_real_suite_end_to_end(
    registry: ToolRegistry, ctx: ToolContext, tmp_path: Path, kendi_python
) -> None:
    _sahte_python_projesi(tmp_path, "def test_gecer():\n    assert True\n")
    sonuc = await call(registry, ctx, path=str(tmp_path), zaman_asimi=120)
    assert not sonuc.is_error
    assert "1 geçti, 0 kaldı" in sonuc.content
    assert sonuc.detail["gecen"] == 1


async def test_tool_marks_a_failing_suite_as_an_error(
    registry: ToolRegistry, ctx: ToolContext, tmp_path: Path, kendi_python
) -> None:
    _sahte_python_projesi(tmp_path, "def test_kalir():\n    assert 1 == 2\n")
    sonuc = await call(registry, ctx, path=str(tmp_path), zaman_asimi=120)
    assert sonuc.is_error
    assert sonuc.detail["kalan"] == 1


async def test_tool_honours_a_manual_command(
    registry: ToolRegistry, ctx: ToolContext, tmp_path: Path
) -> None:
    """Elle komut: tespit atlanır."""
    sonuc = await call(
        registry, ctx, path=str(tmp_path),
        komut=f'"{sys.executable}" -c "print(\'merhaba\')"', zaman_asimi=60,
    )
    assert "merhaba" in sonuc.content


def test_the_tool_description_warns_about_scope(registry: ToolRegistry) -> None:
    """Araç şeması modelin gördüğü tek belge: sınırı orada da yazmalı."""
    aciklama = registry.get("kos").description
    assert "uydurulmaz" in aciklama
    assert "her şey çalışıyor" in aciklama
