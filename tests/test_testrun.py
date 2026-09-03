"""Project test runner: does the agent really run the code it wrote?

The promise under test: `denetle` looks at syntax, `kos` RUNS the code. The
gap between them was the class of error that blew up on the user's screen —

    public function index(): string { return redirect(); }

`php -l` finds this clean, the browser gives a TypeError.

Three things are verified separately:

  1. DETECTION is evidence-based: no configuration file, no command. An
     invented command is worse than a missing guarantee.
  2. NORMALISATION is tested with real output texts — pytest, phpunit, jest,
     mocha, go, cargo, dotnet may not be installed on this machine, and this
     is the only way to prove we read their output correctly.
  3. HONESTY: no text says "everything works".
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

import pytest

from dornick import testrun
from dornick.config import Config
from dornick.events import EventLog
from dornick.session import Session
from dornick.tools import ToolContext, ToolRegistry
from dornick.tools import runner as run_tools


@pytest.fixture()
def ctx(tmp_path: Path) -> ToolContext:
    config = Config.load(tmp_path)
    config.ensure_dirs()
    return ToolContext(
        config=config,
        session=Session(EventLog(tmp_path / ".dornick" / "s.jsonl"), "test-kos"),
        cancel=asyncio.Event(),
    )


@pytest.fixture()
def registry() -> ToolRegistry:
    reg = ToolRegistry()
    run_tools.register(reg)
    return reg


@pytest.fixture(autouse=True)
def clean_memory():
    """The module-level "last touched project" must not leak between tests."""
    testrun.forget()
    yield
    testrun.forget()


async def call(registry: ToolRegistry, ctx: ToolContext, **args):
    return await registry.get("kos").handler(args, ctx)


# -- detection: python --------------------------------------------------


def test_pytest_ini_is_evidence(tmp_path: Path) -> None:
    (tmp_path / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    harness = testrun.detect(tmp_path)
    assert harness is not None
    assert harness.ecosystem == "python"
    assert harness.argv[1:] == ["-m", "pytest", "-q"]
    assert harness.evidence == "pytest.ini"
    assert harness.confidence == 2


def test_pyproject_pytest_section_is_evidence(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\n\n[tool.pytest.ini_options]\ntestpaths = ["tests"]\n',
        encoding="utf-8",
    )
    harness = testrun.detect(tmp_path)
    assert harness is not None and harness.ecosystem == "python"
    assert "pyproject.toml" in harness.evidence


def test_pyproject_without_pytest_is_not_evidence(tmp_path: Path) -> None:
    """The presence of a pyproject is not the presence of pytest."""
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\n', encoding="utf-8")
    assert testrun.detect(tmp_path) is None


def test_tests_folder_is_weaker_evidence(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_a.py").write_text("def test_a(): pass\n", encoding="utf-8")
    harness = testrun.detect(tmp_path)
    assert harness is not None and harness.confidence == 1


def test_tests_folder_without_test_files_is_not_evidence(tmp_path: Path) -> None:
    """Documents can live under `tests/` too; without a test file there is no evidence."""
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "veriler.json").write_text("{}", encoding="utf-8")
    (tmp_path / "tests" / "yardimci.py").write_text("x = 1\n", encoding="utf-8")
    assert testrun.detect(tmp_path) is None


def test_python_command_matches_platform(tmp_path: Path) -> None:
    (tmp_path / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    harness = testrun.detect(tmp_path)
    expected = "py -m pytest -q" if sys.platform == "win32" else "python3 -m pytest -q"
    assert harness is not None and harness.label == expected


# -- detection: node ----------------------------------------------------


def _package(tmp_path: Path, scripts: dict) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps({"name": "x", "scripts": scripts}), encoding="utf-8")


def test_package_json_test_script_is_evidence(tmp_path: Path) -> None:
    _package(tmp_path, {"test": "jest", "build": "vite build", "dev": "vite"})
    (tmp_path / "node_modules").mkdir()
    harness = testrun.detect(tmp_path)
    assert harness is not None
    assert harness.ecosystem == "node" and harness.label == "npm test"
    assert "scripts.test = jest" in harness.evidence
    # build/dev are not offered as commands but noted so the model knows.
    assert any("build" in n and "dev" in n for n in harness.notes)


def test_npm_placeholder_test_script_is_not_evidence(tmp_path: Path) -> None:
    """The placeholder `npm init` leaves behind is not a test setup."""
    _package(tmp_path, {"test": 'echo "Error: no test specified" && exit 1'})
    assert testrun.detect(tmp_path) is None


def test_package_json_without_test_script_is_not_evidence(tmp_path: Path) -> None:
    _package(tmp_path, {"build": "vite build"})
    assert testrun.detect(tmp_path) is None


def test_missing_node_modules_is_reported_not_prescribed(tmp_path: Path) -> None:
    """Missing dependencies are REPORTED; installing is not prescribed."""
    _package(tmp_path, {"test": "jest"})
    harness = testrun.detect(tmp_path)
    assert harness is not None
    assert not harness.runnable
    assert "node_modules" in harness.blocker
    assert "npm install" not in harness.blocker.lower()


def test_broken_package_json_is_not_evidence(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text("{ bozuk", encoding="utf-8")
    assert testrun.detect(tmp_path) is None


# -- detection: php -----------------------------------------------------


@pytest.mark.parametrize("name", ["phpunit.xml", "phpunit.xml.dist", "phpunit.dist.xml"])
def test_phpunit_configuration_names(tmp_path: Path, name: str) -> None:
    """CodeIgniter 4 uses `phpunit.dist.xml` — all three names must be recognised."""
    (tmp_path / name).write_text("<phpunit/>", encoding="utf-8")
    (tmp_path / "vendor" / "bin").mkdir(parents=True)
    (tmp_path / "vendor" / "bin" / "phpunit").write_text("#!/usr/bin/env php\n",
                                                         encoding="utf-8")
    harness = testrun.detect(tmp_path)
    assert harness is not None
    assert harness.ecosystem == "php"
    assert harness.label == "php vendor/bin/phpunit"
    assert harness.runnable


def test_phpunit_config_without_vendor_is_blocked(tmp_path: Path) -> None:
    (tmp_path / "phpunit.xml").write_text("<phpunit/>", encoding="utf-8")
    harness = testrun.detect(tmp_path)
    assert harness is not None and not harness.runnable
    assert "vendor/bin/phpunit" in harness.blocker


def test_spark_is_a_health_command_not_a_test_suite(tmp_path: Path) -> None:
    """Without phpunit a CI4 project gets a cheap health command — but not sold as a test."""
    (tmp_path / "spark").write_text("#!/usr/bin/env php\n", encoding="utf-8")
    harness = testrun.detect(tmp_path)
    assert harness is not None
    assert harness.kind == "saglik"
    assert harness.label == "php spark routes"


def test_phpunit_beats_spark(tmp_path: Path) -> None:
    (tmp_path / "spark").write_text("#!/usr/bin/env php\n", encoding="utf-8")
    (tmp_path / "phpunit.dist.xml").write_text("<phpunit/>", encoding="utf-8")
    (tmp_path / "vendor" / "bin").mkdir(parents=True)
    (tmp_path / "vendor" / "bin" / "phpunit").write_text("x", encoding="utf-8")
    harness = testrun.detect(tmp_path)
    assert harness is not None and harness.kind == "test"


# -- detection: go / rust / dotnet -------------------------------------


def test_go_mod(tmp_path: Path) -> None:
    (tmp_path / "go.mod").write_text("module example.com/x\n", encoding="utf-8")
    harness = testrun.detect(tmp_path)
    assert harness is not None and harness.label == "go test ./..."


def test_cargo_toml(tmp_path: Path) -> None:
    (tmp_path / "Cargo.toml").write_text("[package]\nname = 'x'\n", encoding="utf-8")
    harness = testrun.detect(tmp_path)
    assert harness is not None and harness.label == "cargo test"


def test_dotnet_project(tmp_path: Path) -> None:
    (tmp_path / "Uygulama.csproj").write_text("<Project/>", encoding="utf-8")
    harness = testrun.detect(tmp_path)
    assert harness is not None and harness.label == "dotnet test"


# -- detection: none ----------------------------------------------------


def test_empty_folder_yields_nothing(tmp_path: Path) -> None:
    """The most important test: no evidence, no command."""
    assert testrun.detect(tmp_path) is None
    assert testrun.detect_all(tmp_path) == []


def test_no_setup_message_refuses_to_invent(tmp_path: Path) -> None:
    text = testrun.detect_text(tmp_path)
    assert "test düzeneği bulunamadı" in text
    assert "uydurmayacağım" in text
    assert "gerçekten çalıştır" in text


def test_a_folder_of_source_files_alone_is_not_a_test_setup(tmp_path: Path) -> None:
    (tmp_path / "index.php").write_text("<?php echo 1;", encoding="utf-8")
    (tmp_path / "app.js").write_text("console.log(1)", encoding="utf-8")
    assert testrun.detect(tmp_path) is None


def test_multiple_ecosystems_are_all_reported(tmp_path: Path) -> None:
    """PHP back end + front end built with npm: both must show up."""
    (tmp_path / "phpunit.xml").write_text("<phpunit/>", encoding="utf-8")
    (tmp_path / "vendor" / "bin").mkdir(parents=True)
    (tmp_path / "vendor" / "bin" / "phpunit").write_text("x", encoding="utf-8")
    _package(tmp_path, {"test": "vitest"})
    (tmp_path / "node_modules").mkdir()
    all_found = testrun.detect_all(tmp_path)
    assert {h.ecosystem for h in all_found} == {"php", "node"}


# -- project root -------------------------------------------------------


def test_project_root_is_found_from_a_nested_file(tmp_path: Path) -> None:
    """The model gives the only thing it has: the path of the file it just wrote."""
    (tmp_path / "composer.json").write_text("{}", encoding="utf-8")
    deep = tmp_path / "app" / "Controllers"
    deep.mkdir(parents=True)
    file = deep / "Home.php"
    file.write_text("<?php", encoding="utf-8")
    assert testrun.project_root(file) == tmp_path


def test_project_root_falls_back_to_the_folder_itself(tmp_path: Path) -> None:
    """With no marker at all we do not climb to an invented parent."""
    deep = tmp_path / "a" / "b"
    deep.mkdir(parents=True)
    assert testrun.project_root(deep) == deep


# -- normalisation: pytest ---------------------------------------------

PYTEST_FAILING = """\
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

PYTEST_CLEAN = """\
.........................................................................
978 passed, 3 skipped in 45.12s
"""


def test_pytest_failure_output(tmp_path: Path) -> None:
    count, failures = testrun.normalize("python", PYTEST_FAILING)
    assert (count.passed, count.failed, count.parsed) == (4, 1, True)
    assert len(failures) == 1
    assert failures[0].name == "tests/test_hesap.py::test_toplama"
    assert failures[0].message == "assert 3 == 4"
    assert failures[0].location == "tests/test_hesap.py:12"


def test_pytest_clean_output(tmp_path: Path) -> None:
    count, failures = testrun.normalize("python", PYTEST_CLEAN)
    assert (count.passed, count.failed, count.skipped) == (978, 0, 3)
    assert failures == []


def test_pytest_error_line_counts_as_failure() -> None:
    output = ("ERROR tests/test_x.py::test_y - ImportError: yok\n"
              "1 error in 0.10s\n")
    count, failures = testrun.normalize("python", output)
    assert count.failed == 1 and count.parsed
    assert failures[0].message == "ImportError: yok"


def test_pytest_no_tests_ran() -> None:
    count, _ = testrun.normalize("python", "no tests ran in 0.01s\n")
    assert count.parsed and count.total == 0


# -- normalisation: phpunit --------------------------------------------

PHPUNIT_FAILING = """\
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

PHPUNIT_CLEAN = """\
PHPUnit 10.5.11 by Sebastian Bergmann and contributors.

....                                                                4 / 4 (100%)

Time: 00:00.201, Memory: 12.00 MB

OK (4 tests, 6 assertions)
"""


def test_phpunit_failure_output() -> None:
    count, failures = testrun.normalize("php", PHPUNIT_FAILING)
    assert (count.total, count.passed, count.failed) == (4, 3, 1)
    assert count.parsed
    assert len(failures) == 1
    assert failures[0].name == "App\\Tests\\HomeTest::testIndexReturnsString"
    assert "null is of type string" in failures[0].message
    assert failures[0].location == "HomeTest.php:23"


def test_phpunit_clean_output() -> None:
    count, failures = testrun.normalize("php", PHPUNIT_CLEAN)
    assert (count.passed, count.failed, count.parsed) == (4, 0, True)
    assert failures == []


def test_phpunit_errors_and_skips() -> None:
    output = "ERRORS!\nTests: 10, Assertions: 12, Errors: 2, Failures: 1, Skipped: 3.\n"
    count, _ = testrun.normalize("php", output)
    assert (count.total, count.failed, count.skipped, count.passed) == (10, 3, 3, 4)


# -- normalisation: node -----------------------------------------------

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
    count, failures = testrun.normalize("node", JEST)
    assert (count.passed, count.failed, count.total) == (2, 1, 3)
    assert failures and failures[0].name == "Hesap › toplar"


def test_mocha_output() -> None:
    count, failures = testrun.normalize("node", MOCHA)
    assert (count.passed, count.failed, count.parsed) == (1, 1, True)
    assert failures and "çıkarır" in failures[0].name


def test_node_test_runner_output() -> None:
    count, _ = testrun.normalize("node", NODE_TEST)
    assert (count.passed, count.failed, count.total) == (3, 1, 4)


def test_vitest_output() -> None:
    count, _ = testrun.normalize("node", VITEST)
    assert (count.passed, count.failed) == (5, 1)


def test_unreadable_node_output_admits_it() -> None:
    """No invented count for a runner we do not recognise — `parsed` stays False."""
    count, _ = testrun.normalize("node", "bilinmeyen koşucu bir şeyler yazdı\n")
    assert not count.parsed


# -- normalisation: go / cargo / dotnet --------------------------------

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
    count, failures = testrun.normalize("go", GO)
    assert (count.passed, count.failed) == (1, 1)
    assert failures[0].name == "TestTopla"
    assert failures[0].location == "hesap_test.go:14"


def test_cargo_output() -> None:
    count, failures = testrun.normalize("rust", CARGO)
    assert (count.passed, count.failed) == (3, 1)
    assert failures and failures[0].name == "tests::topla"


def test_dotnet_output() -> None:
    count, _ = testrun.normalize("dotnet", DOTNET)
    assert (count.passed, count.failed, count.total) == (2, 1, 3)


def test_auto_detection_picks_the_right_reader() -> None:
    """With a hand-given command we do not know which runner is speaking."""
    count, _ = testrun.normalize("oto", PYTEST_CLEAN)
    assert count.passed == 978
    count, _ = testrun.normalize("oto", PHPUNIT_CLEAN)
    assert count.passed == 4


# -- trimming -----------------------------------------------------------


def test_long_output_keeps_head_and_tail() -> None:
    text = "BAS\n" + ("x" * 20000) + "\nSON"
    trimmed = testrun.trim(text, limit=400)
    assert trimmed.startswith("BAS")
    assert trimmed.endswith("SON")
    assert "kırpıldı" in trimmed
    assert len(trimmed) < 600


def test_short_output_is_untouched() -> None:
    assert testrun.trim("kısa çıktı") == "kısa çıktı"


# -- honesty texts -----------------------------------------------------


def _result(**kw) -> testrun.Result:
    base = dict(ecosystem="python", label="py -m pytest -q", root="C:/x",
                status="kostu")
    base.update(kw)
    return testrun.Result(**base)


def test_a_green_run_never_claims_everything_works() -> None:
    result = _result(count=testrun.Count(passed=12, total=12, parsed=True))
    text = result.text()
    assert "12 geçti, 0 kaldı" in text
    assert "koşulan testlerin kapsadığı kadarını doğrular" in text
    assert "her şey" not in text.lower()
    assert "denenmemiş" in text


def test_a_red_run_says_do_not_call_it_done() -> None:
    result = _result(exit_code=1,
                     count=testrun.Count(passed=4, failed=1, total=5, parsed=True),
                     failures=[testrun.Failure("test_x", "assert 3 == 4",
                                                   "tests/test_h.py:12")])
    text = result.text()
    assert "1 kaldı" in text
    assert "tests/test_h.py:12" in text
    assert "'çalışıyor' deme" in text


def test_only_five_failures_are_named() -> None:
    result = _result(exit_code=1,
                     count=testrun.Count(failed=9, total=9, parsed=True),
                     failures=[testrun.Failure(f"test_{i}") for i in range(9)])
    text = result.text()
    assert "test_4" in text and "test_5" not in text
    assert "4 başarısız test daha" in text


def test_unreadable_counts_are_admitted() -> None:
    result = _result(count=testrun.Count(), raw="anlaşılmaz çıktı")
    text = result.text()
    assert "Test sayısı okunamadığı için" in text


def test_empty_suite_proves_nothing() -> None:
    result = _result(count=testrun.Count(parsed=True))
    assert "Hiç test koşmadı" in result.text()
    assert "gerçekten çalıştır" in result.text()


def test_health_check_is_not_sold_as_a_test() -> None:
    result = _result(ecosystem="php", label="php spark routes", kind="saglik",
                     count=testrun.Count())
    text = result.text()
    assert "test takımı değil" in text
    assert "Davranışın doğruluğunu göstermez" in text


def test_timeout_text_explains_both_causes() -> None:
    result = _result(status="zaman_asimi", duration=300.0)
    text = result.text()
    assert "bitmedi ve durduruldu" in text
    assert "zaman_asimi" in text


# -- a real run ---------------------------------------------------------


def _fake_python_project(root: Path, body: str) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    tests = root / "tests"
    tests.mkdir(exist_ok=True)
    (tests / "test_ornek.py").write_text(body, encoding="utf-8")


@pytest.fixture()
def own_python(monkeypatch: pytest.MonkeyPatch):
    """End-to-end runs should use this suite's own Python.

    Detection produces `py -m pytest -q` (the right thing for the user's
    project), but on a CI machine `py` may point at another interpreter
    without pytest. What we test here is the runner itself, not the
    machine's Python layout.
    """
    real = testrun._parse

    def fake(name: str) -> str | None:
        if name in ("py", "python3", "python"):
            return sys.executable
        return real(name)

    monkeypatch.setattr(testrun, "_parse", fake)


async def test_a_real_passing_suite_runs(tmp_path: Path, own_python) -> None:
    """End to end: real pytest runs in a fake project and the numbers are read."""
    _fake_python_project(tmp_path, "def test_gecer():\n    assert True\n")
    harness = testrun.detect(tmp_path)
    assert harness is not None
    result = await testrun.run_harness(harness, timeout=120)
    assert result.status == "kostu"
    assert result.exit_code == 0
    assert result.count.parsed and result.count.passed == 1


async def test_a_real_failing_suite_is_reported(tmp_path: Path, own_python) -> None:
    """The wound itself: the code is syntactically sound but behaves wrong."""
    _fake_python_project(
        tmp_path,
        "def topla(a, b):\n"
        "    return a - b\n"     # syntax clean, behaviour wrong
        "\n"
        "def test_toplama():\n"
        "    assert topla(1, 2) == 3\n",
    )
    harness = testrun.detect(tmp_path)
    assert harness is not None
    result = await testrun.run_harness(harness, timeout=120)
    assert result.exit_code != 0
    assert result.count.failed == 1
    assert result.failures
    assert "test_toplama" in result.failures[0].name


HANGING = "import time; print('asilan_test_basladi', flush=True); time.sleep(120)"


async def test_timeout_kills_the_whole_process_tree(tmp_path: Path) -> None:
    """A command that never ends must not freeze the turn — nor linger behind.

    For a command run through the shell, `proc` is cmd.exe/bash; the real
    process is its child. Killing only the shell left the runner on the
    machine and, because it kept the pipe open, the caller hung MEASURABLY:
    a 2-second timeout had become a 30-second wait.
    """
    start = time.monotonic()
    result = await testrun.run_command(
        f'"{sys.executable}" -c "{HANGING}"', tmp_path, timeout=2,
    )
    elapsed = time.monotonic() - start
    assert result.status == "zaman_asimi"
    # The real guarantee: the call returns right after the timeout.
    assert elapsed < 20, f"koşum {elapsed:.0f} sn asılı kaldı"


async def test_timeout_keeps_the_partial_output(tmp_path: Path) -> None:
    """Partial output is information too: the last line says where it got stuck."""
    result = await testrun.run_command(
        f'"{sys.executable}" -c "{HANGING}"', tmp_path, timeout=3,
    )
    assert "asilan_test_basladi" in result.raw
    assert "nerede takıldığını" in result.text()


async def test_cancel_stops_the_run(tmp_path: Path) -> None:
    """When the user says 'stop' the running process must die — and be reported so."""
    cancel = asyncio.Event()

    async def stop() -> None:
        await asyncio.sleep(0.3)
        cancel.set()

    task = asyncio.ensure_future(stop())
    start = time.monotonic()
    result = await testrun.run_command(
        f'"{sys.executable}" -c "{HANGING}"', tmp_path, timeout=120,
        cancel=cancel,
    )
    elapsed = time.monotonic() - start
    await task
    assert result.status == "kesildi"          # NOT a timeout
    assert "Durduruldu" in result.text()
    assert elapsed < 20, f"kesme {elapsed:.0f} sn sürdü"


async def test_missing_executable_is_honest(tmp_path: Path) -> None:
    harness = testrun.Harness(
        "go", "test", "go test ./...", ["kesinlikle-olmayan-arac", "test"],
        tmp_path, "go.mod",
    )
    result = await testrun.run_harness(harness)
    assert result.status == "baslatilamadi"
    assert "bulunamadı" in result.text()


async def test_blocked_setup_is_not_run(tmp_path: Path) -> None:
    _package(tmp_path, {"test": "jest"})   # no node_modules
    harness = testrun.detect(tmp_path)
    assert harness is not None
    result = await testrun.run_harness(harness)
    assert result.status == "yok"
    assert "node_modules" in result.raw


# -- post-write reminder -----------------------------------------------


def test_reminder_names_the_command(tmp_path: Path) -> None:
    (tmp_path / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    (tmp_path / "modul.py").write_text("x = 1\n", encoding="utf-8")
    text = testrun.reminder(tmp_path / "modul.py")
    assert "pytest -q" in text
    assert "`kos`" in text
    assert len(text.splitlines()) == 1   # ONE line: no noise


def test_no_reminder_without_a_setup(tmp_path: Path) -> None:
    (tmp_path / "not.txt").write_text("selam", encoding="utf-8")
    assert testrun.reminder(tmp_path / "not.txt") == ""


def test_reminder_hardens_after_repeated_writes(tmp_path: Path) -> None:
    """A third write to the same file: the model is trying to fix it by eye."""
    (tmp_path / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    file = tmp_path / "modul.py"
    file.write_text("x = 1\n", encoding="utf-8")
    soft = testrun.reminder(file, writes=1)
    hard = testrun.reminder(file, writes=3)
    assert "Gözle düzeltmeyi bırak" in hard
    assert "3. kez" in hard
    assert hard != soft


def test_reminder_reports_a_blocked_setup(tmp_path: Path) -> None:
    _package(tmp_path, {"test": "jest"})
    text = testrun.reminder(tmp_path / "index.js")
    assert "node_modules" in text


def test_reminder_marks_a_health_command_as_such(tmp_path: Path) -> None:
    (tmp_path / "spark").write_text("#!/usr/bin/env php\n", encoding="utf-8")
    text = testrun.reminder(tmp_path / "app" / "Controllers" / "Home.php")
    assert "test takımı yok" in text
    assert "sağlık denetimi" in text


# -- tool surface -------------------------------------------------------


def test_tool_is_registered_in_the_real_registry() -> None:
    from dornick.tools import build_registry

    assert "kos" in build_registry(subagents=False)


def test_tool_is_gated(registry: ToolRegistry) -> None:
    """Running tests runs the project's code: it must be subject to the permission mode."""
    spec = registry.get("kos")
    assert spec.mutates is True
    assert spec.parallel_safe is False


def test_manual_command_is_the_permission_subject() -> None:
    """A hand-given command must not appear at the gate as `path`."""
    from dornick.permissions import describe

    assert describe({"path": "C:/proje", "komut": "npm test"}) == "npm test"
    assert describe({"path": "C:/proje"}) == "C:/proje"


async def test_tool_reports_no_setup_without_erroring(
    registry: ToolRegistry, ctx: ToolContext, tmp_path: Path
) -> None:
    empty = tmp_path / "bos"
    empty.mkdir()
    result = await call(registry, ctx, path=str(empty))
    assert not result.is_error      # information, not an error
    assert "test düzeneği bulunamadı" in result.content


async def test_tool_detection_only_mode_runs_nothing(
    registry: ToolRegistry, ctx: ToolContext, tmp_path: Path
) -> None:
    (tmp_path / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    (tmp_path / "spark").write_text("#!/usr/bin/env php\n", encoding="utf-8")
    result = await call(registry, ctx, path=str(tmp_path), sadece_tespit=True)
    assert "pytest -q" in result.content
    assert "php spark routes" in result.content
    assert "hiçbiri koşturulmadı" in result.content
    assert result.detail["tespit"] is True


async def test_tool_uses_the_last_touched_project(
    registry: ToolRegistry, ctx: ToolContext, tmp_path: Path
) -> None:
    """Without `path`: the project of the last written file."""
    project = tmp_path / "proje"
    project.mkdir()
    (project / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    testrun.touched(project / "modul.py")
    result = await call(registry, ctx, sadece_tespit=True)
    assert str(project) in result.content


async def test_tool_refuses_a_missing_folder(
    registry: ToolRegistry, ctx: ToolContext, tmp_path: Path
) -> None:
    result = await call(registry, ctx, path=str(tmp_path / "yok" / "burada"))
    assert result.is_error
    assert "Klasör yok" in result.content


async def test_tool_runs_a_real_suite_end_to_end(
    registry: ToolRegistry, ctx: ToolContext, tmp_path: Path, own_python
) -> None:
    _fake_python_project(tmp_path, "def test_gecer():\n    assert True\n")
    result = await call(registry, ctx, path=str(tmp_path), zaman_asimi=120)
    assert not result.is_error
    assert "1 geçti, 0 kaldı" in result.content
    assert result.detail["gecen"] == 1


async def test_tool_marks_a_failing_suite_as_an_error(
    registry: ToolRegistry, ctx: ToolContext, tmp_path: Path, own_python
) -> None:
    _fake_python_project(tmp_path, "def test_kalir():\n    assert 1 == 2\n")
    result = await call(registry, ctx, path=str(tmp_path), zaman_asimi=120)
    assert result.is_error
    assert result.detail["kalan"] == 1


async def test_tool_honours_a_manual_command(
    registry: ToolRegistry, ctx: ToolContext, tmp_path: Path
) -> None:
    """A manual command: detection is skipped."""
    result = await call(
        registry, ctx, path=str(tmp_path),
        komut=f'"{sys.executable}" -c "print(\'merhaba\')"', zaman_asimi=60,
    )
    assert "merhaba" in result.content


def test_the_tool_description_warns_about_scope(registry: ToolRegistry) -> None:
    """The tool schema is the only document the model sees: the limit must be written there too."""
    description = registry.get("kos").description
    assert "uydurulmaz" in description
    assert "her şey çalışıyor" in description
