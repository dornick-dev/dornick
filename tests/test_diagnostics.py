"""Code diagnostics: is a written file checked the moment it is written?

The promise under test: after the agent writes a file it must see the error
IMMEDIATELY. Errors of the "I wrote it, I did not run it, I said done" class
(a return that disagrees with the declared return type, an unclosed
parenthesis, an undefined name) must land in front of the model before the
turn closes.

The second promise is honesty: a diagnosis never invents an error and never
says "all is well". If there is no checker it says so; it writes the error
classes outside its scope explicitly next to a clean result.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from dornick import diagnostics
from dornick.config import Config
from dornick.events import EventLog
from dornick.session import Session
from dornick.tools import ToolContext, ToolRegistry
from dornick.tools import files as file_tools

PHP = diagnostics.checker_path("php")
NODE = diagnostics.checker_path("node")

php_required = pytest.mark.skipif(PHP is None, reason="php bu makinede yok")
node_required = pytest.mark.skipif(NODE is None, reason="node bu makinede yok")


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


# -- language selection -------------------------------------------------


def test_unknown_extension_stays_silent(tmp_path: Path) -> None:
    """Nothing is said for an extension we do not know — no invented error."""
    path = tmp_path / "notlar.rtf"
    path.write_text("bu bir kod bile degil {{{", encoding="utf-8")

    assert diagnostics.detect_language(path) is None
    assert diagnostics.check(path) is None


def test_jsx_is_deliberately_not_checked(tmp_path: Path) -> None:
    """`node --check` does not understand JSX; it would invent an error for a sound file."""
    path = tmp_path / "Bilesen.jsx"
    path.write_text("const A = () => <div>merhaba</div>;\n", encoding="utf-8")

    assert diagnostics.check(path) is None


def test_a_missing_file_is_not_an_error(tmp_path: Path) -> None:
    assert diagnostics.check(tmp_path / "yok.py") is None


def test_a_huge_file_is_skipped_honestly(tmp_path: Path) -> None:
    path = tmp_path / "kocaman.js"
    path.write_text("x=1;\n" * 500_000, encoding="utf-8")

    diagnosis = diagnostics.check(path)
    assert diagnosis is not None and diagnosis.status == "yok"
    assert "büyük" in diagnosis.reason


# -- python -------------------------------------------------------------


def test_broken_python_is_caught_with_a_line_number(tmp_path: Path) -> None:
    path = tmp_path / "bozuk.py"
    path.write_text("def f():\n    return (1, 2\n\nprint('x')\n", encoding="utf-8")

    diagnosis = diagnostics.check(path)
    assert diagnosis is not None
    assert diagnosis.status == "hata"
    assert diagnosis.findings
    assert diagnosis.findings[0].line > 0
    assert "satır" in diagnosis.text()


def test_clean_python_never_claims_everything_is_fine(tmp_path: Path) -> None:
    path = tmp_path / "temiz.py"
    path.write_text("def f():\n    return 1\n", encoding="utf-8")

    diagnosis = diagnostics.check(path)
    assert diagnosis is not None and diagnosis.status == "temiz"
    text = diagnosis.text()
    # Says "the checker saw no error"; does NOT say "the code works".
    assert "hata görmedi" in text
    assert diagnosis.scope  # what it cannot see is written down


def test_python_null_byte_is_reported_not_crashed(tmp_path: Path) -> None:
    path = tmp_path / "nul.py"
    path.write_bytes(b"x = 1\x00\n")

    diagnosis = diagnostics.check(path)
    assert diagnosis is not None and diagnosis.status == "hata"


# -- php ----------------------------------------------------------------


@php_required
def test_broken_php_is_caught(tmp_path: Path) -> None:
    path = tmp_path / "bozuk.php"
    path.write_text(
        '<?php\nclass C {\n    public function f(): string { return "x"\n}\n',
        encoding="utf-8",
    )

    diagnosis = diagnostics.check(path)
    assert diagnosis is not None and diagnosis.status == "hata"
    assert diagnosis.findings[0].line == 4
    assert "syntax error" in diagnosis.findings[0].message


@php_required
def test_php_catches_a_void_function_returning_a_value(tmp_path: Path) -> None:
    """`php -l` also sees compile-time fatal errors beyond syntax."""
    path = tmp_path / "void.php"
    path.write_text(
        "<?php\nclass C {\n    public function f(): void { return 1; }\n}\n",
        encoding="utf-8",
    )

    diagnosis = diagnostics.check(path)
    assert diagnosis is not None and diagnosis.status == "hata"
    assert "void" in diagnosis.findings[0].message.lower()


@php_required
def test_php_says_out_loud_what_it_cannot_see(tmp_path: Path) -> None:
    """Today's real error: saying `: string` and returning redirect().

    `php -l` does NOT see this — and instead of hiding that, the diagnosis
    writes it explicitly next to the clean result. A lying "clean" would be
    the most dangerous output.
    """
    path = tmp_path / "Tip.php"
    path.write_text(
        "<?php\nclass C {\n    public function index(): string "
        "{ return redirect(); }\n}\n",
        encoding="utf-8",
    )

    diagnosis = diagnostics.check(path)
    assert diagnosis is not None and diagnosis.status == "temiz"
    assert "tip hataları" in diagnosis.scope
    assert "tip hataları" in diagnosis.text()


def test_php_without_the_checker_is_honest(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(diagnostics, "checker_path", lambda name: None)
    path = tmp_path / "a.php"
    path.write_text("<?php echo 1;\n", encoding="utf-8")

    diagnosis = diagnostics.check(path)
    assert diagnosis is not None and diagnosis.status == "yok"
    assert "bulunamadı" in diagnosis.reason
    assert "kontrol edilemedi" in diagnosis.text()


# -- js / json / yaml ---------------------------------------------------


@node_required
def test_broken_js_is_caught(tmp_path: Path) -> None:
    path = tmp_path / "bozuk.js"
    path.write_text("function f() {\n  const x = ;\n}\n", encoding="utf-8")

    diagnosis = diagnostics.check(path)
    assert diagnosis is not None and diagnosis.status == "hata"
    assert diagnosis.findings[0].line == 2
    assert "SyntaxError" in diagnosis.findings[0].message


@node_required
def test_clean_js_is_clean(tmp_path: Path) -> None:
    path = tmp_path / "temiz.js"
    path.write_text("const x = 1;\nconsole.log(x);\n", encoding="utf-8")

    diagnosis = diagnostics.check(path)
    assert diagnosis is not None and diagnosis.status == "temiz"


def test_broken_json_gets_a_line(tmp_path: Path) -> None:
    path = tmp_path / "ayar.json"
    path.write_text('{\n  "a": 1,\n  "b":\n}\n', encoding="utf-8")

    diagnosis = diagnostics.check(path)
    assert diagnosis is not None and diagnosis.status == "hata"
    assert diagnosis.findings[0].line == 4


def test_clean_json_is_clean(tmp_path: Path) -> None:
    path = tmp_path / "ayar.json"
    path.write_text('{"a": 1}\n', encoding="utf-8")

    diagnosis = diagnostics.check(path)
    assert diagnosis is not None and diagnosis.status == "temiz"


def test_broken_yaml_gets_a_line(tmp_path: Path) -> None:
    pytest.importorskip("yaml")
    path = tmp_path / "iş.yaml"
    path.write_text("a: 1\n  b: 2\n", encoding="utf-8")

    diagnosis = diagnostics.check(path)
    assert diagnosis is not None and diagnosis.status == "hata"
    assert diagnosis.findings[0].line >= 1


def test_typescript_without_a_project_says_so(tmp_path: Path) -> None:
    """Without tsconfig, compiling a single file would produce invented errors."""
    path = tmp_path / "a.ts"
    path.write_text("const x: number = 1;\n", encoding="utf-8")

    diagnosis = diagnostics.check(path)
    assert diagnosis is not None and diagnosis.status == "yok"
    assert "tsconfig" in diagnosis.reason


# -- parsers (tested even when the checker is not installed) -------------


def test_the_php_parser_reads_a_real_lint_line() -> None:
    output = (
        'PHP Parse error:  syntax error, unexpected token "}", expecting ";" '
        "in C:\\site\\Home.php on line 12\n"
        "Errors parsing C:\\site\\Home.php"
    )
    findings = diagnostics._php_findings(output)
    assert len(findings) == 1
    assert findings[0].line == 12
    assert findings[0].message.startswith("syntax error")


def test_the_php_parser_reports_a_doubled_error_once() -> None:
    """php prints the same error twice, with and without the prefix; it reaches the model once."""
    output = (
        "PHP Parse error:  syntax error in a.php on line 3\n"
        "\nParse error: syntax error in a.php on line 3\n"
        "Errors parsing a.php"
    )
    assert len(diagnostics._php_findings(output)) == 1


def test_the_ruff_parser_survives_a_windows_drive_letter() -> None:
    output = (
        "D:\\proje\\src\\a.py:7:5: F821 Undefined name `foo`\n"
        "D:\\proje\\src\\a.py:1:1: F401 `os` imported but unused\n"
    )
    findings = diagnostics._py_findings(output)
    assert [f.line for f in findings] == [7, 1]
    assert "F821" in findings[0].message


def test_the_tsc_parser_reads_a_diagnostic_line() -> None:
    output = "src/app.ts(12,5): error TS2322: Type 'string' is not assignable.\n"
    findings = diagnostics._ts_findings(output)
    assert len(findings) == 1 and findings[0].line == 12
    assert "TS2322" in findings[0].message


def test_the_node_parser_reads_the_location_and_the_message() -> None:
    output = (
        "D:\\proje\\bozuk.js:2\n  const x = ;\n            ^\n\n"
        "SyntaxError: Unexpected token ';'\n    at wrapSafe (node:internal)\n"
    )
    findings = diagnostics._node_findings(output)
    assert len(findings) == 1 and findings[0].line == 2


# -- timeout ------------------------------------------------------------


def test_a_slow_checker_is_reported_as_unchecked(tmp_path: Path, monkeypatch) -> None:
    """If the checker hangs the write does not stop; 'could not be checked' is said honestly."""
    monkeypatch.setattr(diagnostics, "checker_path", lambda name: "sahte-php")
    monkeypatch.setattr(diagnostics, "_run", lambda command, timeout: None)
    path = tmp_path / "yavas.php"
    path.write_text("<?php echo 1;\n", encoding="utf-8")

    diagnosis = diagnostics.check(path, timeout=0.01)
    assert diagnosis.status == "yok"
    assert "bitmedi" in diagnosis.reason


def test_a_crashing_checker_never_invents_a_finding(tmp_path: Path, monkeypatch) -> None:
    def crash(*_a, **_k):
        raise RuntimeError("denetleyici çöktü")

    monkeypatch.setitem(diagnostics._CHECKERS, "php", crash)
    path = tmp_path / "a.php"
    path.write_text("<?php echo 1;\n", encoding="utf-8")

    diagnosis = diagnostics.check(path)
    assert diagnosis.status == "yok" and not diagnosis.findings


# -- integration with the write tools -----------------------------------


async def test_write_file_hands_the_error_back_to_the_model(
    registry: ToolRegistry, ctx: ToolContext
) -> None:
    """The core scenario: a broken file was written, the error came back in the SAME reply."""
    result = await call(
        registry, "write_file", ctx,
        path="bozuk.py", content="def f():\n    return (1, 2\n",
    )

    assert not result.is_error  # the file really was written
    assert "yazıldı" in result.content
    assert "tanı:" in result.content
    assert "satır 2" in result.content
    assert "Düzeltmeden devam etme" in result.content
    assert result.detail["tani"]["durum"] == "hata"
    assert result.detail["tani"]["bulgular"][0]["satir"] == 2


async def test_write_file_reports_a_clean_check_in_one_line(
    registry: ToolRegistry, ctx: ToolContext
) -> None:
    result = await call(
        registry, "write_file", ctx, path="temiz.py", content="x = 1\n"
    )

    assert "tanı: temiz" in result.content
    assert result.detail["tani"]["durum"] == "temiz"


async def test_write_file_says_nothing_for_an_unknown_language(
    registry: ToolRegistry, ctx: ToolContext
) -> None:
    result = await call(
        registry, "write_file", ctx, path="notlar.txt", content="merhaba {{{\n"
    )

    assert "tanı" not in result.content
    assert "tani" not in result.detail


async def test_edit_file_checks_what_the_edit_produced(
    registry: ToolRegistry, ctx: ToolContext
) -> None:
    """If an edit breaks the file, that must show in the edit's reply."""
    await call(registry, "write_file", ctx, path="a.py", content="x = 1\ny = 2\n")
    await call(registry, "read_file", ctx, path="a.py")

    result = await call(registry, "edit_file", ctx, path="a.py", old="y = 2", new="y = (2")

    assert "güncellendi" in result.content
    assert result.detail["tani"]["durum"] == "hata"
    assert "tanı:" in result.content


async def test_a_broken_write_is_still_a_write(
    registry: ToolRegistry, ctx: ToolContext
) -> None:
    """The diagnosis does not void the write: the file is on disk, the result is not an error.

    Otherwise the model would think the file was not written and write it again."""
    await call(registry, "write_file", ctx, path="b.py", content="def f(:\n")

    assert (ctx.sandbox.root / "b.py").read_text(encoding="utf-8") == "def f(:\n"


async def test_a_failed_write_gets_no_diagnosis(
    registry: ToolRegistry, ctx: ToolContext
) -> None:
    """A staleness refusal is not a write; the diagnosis must not run either."""
    (ctx.sandbox.root / "c.py").write_text("x = 1\n", encoding="utf-8")

    result = await call(registry, "write_file", ctx, path="c.py", content="y = (2\n")

    assert result.is_error
    assert "tanı" not in result.content


# -- the manual check tool ---------------------------------------------


async def test_the_manual_tool_checks_the_last_written_file(
    registry: ToolRegistry, ctx: ToolContext
) -> None:
    await call(registry, "write_file", ctx, path="son.py", content="def f(:\n")

    result = await call(registry, "denetle", ctx)

    assert "son.py" in result.content
    assert result.detail["hatali"] == 1


async def test_the_manual_tool_without_a_target_is_honest(
    registry: ToolRegistry, ctx: ToolContext
) -> None:
    result = await call(registry, "denetle", ctx)

    assert result.is_error
    assert "henüz bir dosya yazmadın" in result.content


async def test_the_manual_tool_walks_a_folder(
    registry: ToolRegistry, ctx: ToolContext
) -> None:
    await call(registry, "write_file", ctx, path="proje/iyi.py", content="x = 1\n")
    await call(registry, "write_file", ctx, path="proje/kotu.py", content="def f(:\n")
    await call(registry, "write_file", ctx, path="proje/okuma.md", content="# not\n")

    result = await call(registry, "denetle", ctx, path="proje")

    assert "kotu.py" in result.content
    assert result.detail["hatali"] == 1
    # The clean file is counted but not declared "solid".
    assert "çalıştığı anlamına gelmez" in result.content


async def test_the_manual_tool_narrows_with_a_pattern(
    registry: ToolRegistry, ctx: ToolContext
) -> None:
    await call(registry, "write_file", ctx, path="p/a.py", content="def f(:\n")
    await call(registry, "write_file", ctx, path="p/b.json", content="{oops}\n")

    result = await call(registry, "denetle", ctx, path="p", pattern="*.json")

    assert result.detail["hatali"] == 1
    assert "a.py" not in result.content


async def test_the_manual_tool_skips_dependency_folders(
    registry: ToolRegistry, ctx: ToolContext
) -> None:
    """Scanning node_modules/vendor is neither what the user asked nor what the agent wrote."""
    root = ctx.sandbox.root / "site"
    (root / "node_modules").mkdir(parents=True)
    (root / "node_modules" / "x.js").write_text("var = ;", encoding="utf-8")
    (root / "app.py").write_text("x = 1\n", encoding="utf-8")

    paths = diagnostics.batch_paths(root)
    assert [p.name for p in paths] == ["app.py"]


async def test_the_manual_tool_refuses_a_missing_path(
    registry: ToolRegistry, ctx: ToolContext
) -> None:
    result = await call(registry, "denetle", ctx, path="olmayan/yer.py")

    assert result.is_error and "Yol yok" in result.content


async def test_the_manual_tool_admits_an_unknown_language(
    registry: ToolRegistry, ctx: ToolContext
) -> None:
    await call(registry, "write_file", ctx, path="not.txt", content="merhaba\n")

    result = await call(registry, "denetle", ctx, path="not.txt")

    assert "denetleyici tanımıyorum" in result.content


# -- finding the checker ------------------------------------------------


def test_the_finder_looks_beyond_path(monkeypatch, tmp_path: Path) -> None:
    """It must find an installed php that is not on PATH (winget/XAMPP)."""
    fake = tmp_path / "php.exe"
    fake.write_text("", encoding="utf-8")
    monkeypatch.setattr("shutil.which", lambda name: None)
    monkeypatch.setitem(
        diagnostics._EXTRA_LOCATIONS, "php", (str(tmp_path / "*.exe"),)
    )
    diagnostics.checker_path.cache_clear()
    try:
        assert diagnostics.checker_path("php") == str(fake)
    finally:
        diagnostics.checker_path.cache_clear()


def test_the_finder_returns_none_for_a_ghost() -> None:
    diagnostics.checker_path.cache_clear()
    try:
        assert diagnostics.checker_path("boyle-bir-arac-yok-12345") is None
    finally:
        diagnostics.checker_path.cache_clear()
