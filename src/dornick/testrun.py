"""Project test runner: actually RUN the code that was written.

Why it exists: `diagnostics` took one step — a written file goes through its
language's own checker the moment it is written. But the ceiling of the
checkers is syntax. The proven wound was this line:

    public function index(): string { return redirect(); }

`php -l` finds it perfectly sound; in the browser it is a TypeError. Syntax
right, behaviour wrong. The only way to see this class is to run the code —
and most projects ALREADY have the machinery for running: pytest, phpunit,
npm test, go test. The agent was not finding and using it.

This module does three jobs and follows the same principle in all three —
**no command without evidence**:

  1. DETECTION: look at a folder and derive the test command from files that
     are really there. No `pytest.ini`, no pytest suggestion; no
     `scripts.test` in `package.json`, no invented `npm test`. With no
     evidence at all the answer is "no test setup found" — a guessed command
     is worse than a missing guarantee: the model runs it, it blows up, and
     the model believes it knows why.
  2. NORMALISATION: every runner's output speaks a different language. We
     reduce them to a common frame: passed / failed / skipped, the first five
     failures' name + message + file:line, exit code, duration. The raw
     output is trimmed head+tail — the stack traces in the middle teach the
     model nothing.
  3. HONESTY: the result text never says "everything works". It says "12
     tests passed, 0 failed — this verifies as much as the tests that ran
     cover". With no tests it says "no tests; to verify, actually run the
     application".

Also `reminder()`: a one-line note after a file is written. Running tests is
EXPENSIVE (seconds, sometimes minutes) — running them automatically on every
write would freeze the turn and keep the user waiting. Instead the model is
told that the setup EXISTS; whether to run it is the model's decision.
Information is free, a run is expensive.
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

from . import environment, diagnostics

# Default time budget for a test run. A diagnostic was capped at 20 seconds;
# a test suite takes longer than that, but not forever either. The model can
# change it via `zaman_asimi`; the ceiling is fixed: a command that never ends
# freezes the turn.
DEFAULT_TIMEOUT = 300.0
MAX_TIMEOUT = 1800.0

# Ceiling on the raw output sent to the model. Head and tail are kept: runners
# print what they ran at the start and the summary at the end; the stack
# traces in the middle do not help with fixing.
MAX_RAW = 4000

# At most this many failing tests are named in the result. The rest is
# summarised as a count — once the first is fixed the others usually fall too.
MAX_FAILURES = 5

# How many levels to climb at most while looking for the project root. A
# bottomless scan could declare the user's home folder a "project".
MAX_UPWARD = 8


# -- data types ---------------------------------------------------------


@dataclass(slots=True)
class Harness:
    """The test/run setup FOUND in a folder.

    `argv` is built with logical names ("py", "php", "npm"); the real path is
    resolved at run time. That keeps detection pure and testable even on a
    machine where the tool is not installed.
    """

    ecosystem: str          # python | node | php | go | rust | dotnet
    kind: str                # "test" (a real suite) | "saglik" (cheap check)
    label: str             # human/model-readable form: "py -m pytest -q"
    argv: list[str]
    root: Path
    evidence: str              # which file proved this
    # 2 = explicit test configuration, 1 = weak evidence (only a tests/
    # folder, a health command). Used for ordering.
    confidence: int = 2
    notes: list[str] = field(default_factory=list)
    # If non-empty: the setup exists but cannot run (dependencies not
    # installed, for instance). We do NOT suggest installing; we only report.
    blocker: str = ""

    @property
    def runnable(self) -> bool:
        return not self.blocker


@dataclass(slots=True)
class Failure:
    """A single failing test: its name, message, location."""

    name: str
    message: str = ""
    location: str = ""   # "file:line" — when it could be extracted

    def text(self) -> str:
        parts = [self.name]
        if self.location:
            parts.append(f"({self.location})")
        line = " ".join(parts)
        return f"{line}: {self.message}" if self.message else line


@dataclass(slots=True)
class Count:
    """Numbers read from the runner. If `parsed` is False none is reliable."""

    passed: int = 0
    failed: int = 0
    skipped: int = 0
    total: int = 0
    parsed: bool = False


@dataclass(slots=True)
class Result:
    """The normalised result of one run."""

    ecosystem: str
    label: str
    root: str
    status: str              # kostu | zaman_asimi | baslatilamadi | yok
    exit_code: int = 0
    duration: float = 0.0
    count: Count = field(default_factory=Count)
    failures: list[Failure] = field(default_factory=list)
    raw: str = ""
    notes: list[str] = field(default_factory=list)
    kind: str = "test"

    @property
    def succeeded(self) -> bool:
        return self.status == "kostu" and self.exit_code == 0

    def text(self) -> str:
        """The text that goes to the model.

        Three rules: (1) if there are numbers they come first, (2) failures
        by name, (3) the closing sentence never says "everything works".
        """
        if self.status == "kesildi":
            return (
                f"Durduruldu — {self.label} ve altındaki süreçler "
                f"sonlandırıldı ({self.duration:.0f} sn sonra).\n\n"
                + (self.raw or "(çıktı yok)")
            )
        if self.status == "zaman_asimi":
            return (
                f"{self.label} {self.duration:.0f} saniyede bitmedi ve durduruldu. "
                "Takım gerçekten uzunsa `zaman_asimi` değerini artır; bir test "
                "asılı kalıyorsa asıl mesele o — aşağıdaki yarım çıktının son "
                "satırı çoğu zaman nerede takıldığını söyler.\n\n"
                + (self.raw or "(çıktı yok)")
            )
        if self.status == "baslatilamadi":
            return f"{self.label} başlatılamadı — {self.raw}"

        headline = [f"{self.label} koştu · çıkış kodu {self.exit_code} · "
                    f"{self.duration:.1f} sn"]
        c = self.count
        if c.parsed:
            parts = [f"{c.passed} geçti", f"{c.failed} kaldı"]
            if c.skipped:
                parts.append(f"{c.skipped} atlandı")
            headline.append(", ".join(parts) + ".")
        else:
            headline.append(
                "Çıktıdan test sayısı çıkarılamadı — aşağıdaki ham çıktıya bak."
            )

        lines = [" ".join(headline)]

        if self.failures:
            lines.append("")
            lines.append("Başarısız olanlar:")
            for failure in self.failures[:MAX_FAILURES]:
                lines.append(f"  {failure.text()}")
            remaining = len(self.failures) - MAX_FAILURES
            if remaining > 0:
                lines.append(f"  ... {remaining} başarısız test daha.")

        lines.append("")
        lines.append(self._shutdown())

        for note in self.notes:
            lines.append(note)

        if self.raw:
            lines.append("")
            lines.append("Ham çıktı:")
            lines.append(self.raw)
        return "\n".join(lines)

    def _shutdown(self) -> str:
        """The sentence that says HOW MUCH the result proves.

        Every word here is deliberate. Saying "tests passed" gives the model a
        guarantee that does not exist; with that guarantee it tells the user
        "ready" and the error blows up in the user's browser.
        """
        if self.kind == "saglik":
            if self.exit_code == 0:
                return ("Bu bir test takımı değil, ucuz bir sağlık denetimi: "
                        "uygulama ayağa kalkıyor ve bu komutu cevaplıyor. "
                        "Davranışın doğruluğunu göstermez.")
            return ("Sağlık denetimi başarısız — uygulama bu komutu bile "
                    "cevaplayamadı. Testlerden önce bunu çöz.")

        c = self.count
        if self.exit_code != 0 or c.failed or self.failures:
            return ("Bu hatalar senin dokunduğun projede. Düzeltmeden "
                    "'çalışıyor' deme.")
        if c.parsed and c.total == 0:
            return ("Hiç test koşmadı — düzenek var ama içi boş. Bu koşum "
                    "hiçbir şey doğrulamıyor; doğrulama için uygulamayı "
                    "gerçekten çalıştır.")
        if c.parsed:
            return (f"{c.passed} test geçti, 0 kaldı — bu, koşulan testlerin "
                    "kapsadığı kadarını doğrular. Testlerin dokunmadığı yollar "
                    "hâlâ denenmemiş durumda.")
        return ("Komut sıfır çıkış koduyla bitti. Test sayısı okunamadığı "
                "için ne kadarının doğrulandığı belli değil — ham çıktıya bak.")

    def detail(self) -> dict:
        """Machine-readable form so the UI can draw a badge."""
        return {
            "ekosistem": self.ecosystem,
            "komut": self.label,
            "kok": self.root,
            "durum": self.status,
            "cikis_kodu": self.exit_code,
            "sure": round(self.duration, 2),
            "gecen": self.count.passed,
            "kalan": self.count.failed,
            "atlanan": self.count.skipped,
            "okundu": self.count.parsed,
            "basarisizlar": [
                {"ad": f.name, "mesaj": f.message, "yer": f.location}
                for f in self.failures[:MAX_FAILURES]
            ],
        }


# -- project root -------------------------------------------------------

# Markers that make a folder a "project". Order does not matter; presence does.
ROOT_MARKERS = (
    ".git", "pyproject.toml", "package.json", "composer.json", "go.mod",
    "Cargo.toml", "pytest.ini", "setup.py", "phpunit.xml", "phpunit.xml.dist",
    "phpunit.dist.xml", "spark",
)


def project_root(path: Path | str) -> Path:
    """The nearest project root upwards from the given path.

    The model usually gives the only concrete thing it has: the path of the
    file it just wrote. `app/Controllers/Home.php` is not a project; finding
    the root is our job. With no marker at all the starting folder is
    returned as is — we do not climb to an invented parent.
    """
    path = Path(path).expanduser()
    start = path if path.is_dir() else path.parent
    candidate = start
    for _ in range(MAX_UPWARD):
        try:
            if any((candidate / marker).exists() for marker in ROOT_MARKERS):
                return candidate
        except OSError:  # pragma: no cover - inaccessible folder
            break
        if candidate.parent == candidate:
            break
        candidate = candidate.parent
    return start


# -- detection ----------------------------------------------------------


def _python(root: Path) -> Harness | None:
    """Is there a pytest setup? Evidence in order: configuration, then tests/.

    Configuration is an explicit declaration ("this project uses pytest"). A
    `tests/` folder is weaker evidence: we do not count it unless it holds a
    `test_*.py` — documents, fixed data or hand-run scripts can live under
    `tests/` too.
    """
    name, label_exe = ("py", "py") if sys.platform == "win32" else ("python3", "python3")
    argv = [name, "-m", "pytest", "-q"]
    label = f"{label_exe} -m pytest -q"

    if (root / "pytest.ini").is_file():
        return Harness("python", "test", label, argv, root, "pytest.ini", 2)

    toml_path = root / "pyproject.toml"
    if toml_path.is_file():
        try:
            text = toml_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""
        if "[tool.pytest" in text:
            return Harness("python", "test", label, argv, root,
                           "pyproject.toml [tool.pytest]", 2)

    for file_name, stamp in (("setup.cfg", "[tool:pytest]"), ("tox.ini", "[pytest]")):
        candidate = root / file_name
        if candidate.is_file():
            try:
                if stamp in candidate.read_text(encoding="utf-8", errors="replace"):
                    return Harness("python", "test", label, argv, root,
                                   f"{file_name} {stamp}", 2)
            except OSError:  # pragma: no cover
                pass

    for folder in ("tests", "test"):
        directory = root / folder
        if not directory.is_dir():
            continue
        try:
            present = any(
                p.name.startswith("test_") or p.name.endswith("_test.py")
                for p in directory.iterdir() if p.suffix == ".py"
            )
        except OSError:  # pragma: no cover
            continue
        if present:
            return Harness("python", "test", label, argv, root,
                           f"{folder}/ altında test_*.py", 1)
    return None


# The placeholder script `npm init` generates. Counting it as a "test setup"
# would invent a guarantee that does not exist — the command deliberately
# exits with 1 anyway.
_NPM_PLACEHOLDER = "no test specified"


def _node(root: Path) -> Harness | None:
    """`scripts.test` in package.json. Without it there is no setup.

    `scripts.build` and `scripts.dev` are read too but not offered as
    commands: they are passed along as a note, because without knowing them
    the model was groping around the shell asking "how do I build this
    project".
    """
    package = root / "package.json"
    if not package.is_file():
        return None
    try:
        data = json.loads(package.read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    scripts = data.get("scripts")
    if not isinstance(scripts, dict):
        scripts = {}

    notes: list[str] = []
    others = [name for name in ("build", "dev", "start", "lint")
              if isinstance(scripts.get(name), str)]
    if others:
        notes.append("package.json'daki diğer betikler: " + ", ".join(others) + ".")

    test = scripts.get("test")
    if not isinstance(test, str) or not test.strip():
        return None
    if _NPM_PLACEHOLDER in test:
        return None

    blocker = ""
    if not (root / "node_modules").is_dir():
        # We only REPORT. Saying "run npm install" is editing the machine,
        # and that is not the model's job.
        blocker = ("node_modules klasörü yok — bağımlılıklar bu makinede kurulu "
                   "değil, `npm test` çalışmaz.")
    return Harness("node", "test", "npm test", ["npm", "test"], root,
                   f"package.json scripts.test = {test.strip()[:60]}", 2,
                   notes, blocker)


_PHPUNIT_CONFIGS = ("phpunit.xml", "phpunit.xml.dist", "phpunit.dist.xml")


def _phpunit_binary(root: Path) -> str | None:
    """vendor/bin/phpunit — on Windows it may have a .bat sibling."""
    for name in ("vendor/bin/phpunit", "vendor/bin/phpunit.bat"):
        if (root / name).is_file():
            return "vendor/bin/phpunit"
    return None


def _php(root: Path) -> Harness | None:
    """phpunit; failing that, a cheap health command in a CodeIgniter 4 project.

    `php spark routes` is not a test and is not presented as one: it boots
    the application, reads the configuration, prints the routes. In a CI4
    project a broken `Config`, a missing class or a syntax accident brings
    this command down — that is zero-cost, real evidence. The result's
    closing sentence says explicitly that it is no substitute for tests.
    """
    config = next(
        (name for name in _PHPUNIT_CONFIGS if (root / name).is_file()), None
    )
    binary = _phpunit_binary(root)

    if config or binary:
        evidence = config or "vendor/bin/phpunit"
        blocker = ""
        if binary is None:
            blocker = (f"{config} var ama vendor/bin/phpunit yok — composer "
                       "bağımlılıkları bu makinede kurulu değil.")
        return Harness("php", "test", "php vendor/bin/phpunit",
                       ["php", "vendor/bin/phpunit"], root, evidence, 2,
                       [], blocker)

    if (root / "spark").is_file():
        return Harness("php", "saglik", "php spark routes",
                       ["php", "spark", "routes"], root, "spark (CodeIgniter 4)", 1,
                       ["Bu bir test takımı değil; phpunit yapılandırması "
                        "bulunamadı."])
    return None


def _go(root: Path) -> Harness | None:
    if not (root / "go.mod").is_file():
        return None
    return Harness("go", "test", "go test ./...",
                   ["go", "test", "./..."], root, "go.mod", 2)


def _rust(root: Path) -> Harness | None:
    if not (root / "Cargo.toml").is_file():
        return None
    return Harness("rust", "test", "cargo test",
                   ["cargo", "test"], root, "Cargo.toml", 2)


def _dotnet(root: Path) -> Harness | None:
    """.sln or .csproj evidence. Looked for in the root folder; the tree is not walked."""
    try:
        candidate = next(
            (p for p in sorted(root.iterdir())
             if p.suffix in (".sln", ".csproj", ".fsproj")), None
        )
    except OSError:  # pragma: no cover
        return None
    if candidate is None:
        return None
    return Harness("dotnet", "test", "dotnet test",
                   ["dotnet", "test"], root, candidate.name, 2)


_DETECTORS = (_python, _php, _node, _go, _rust, _dotnet)


def detect_all(root: Path | str) -> list[Harness]:
    """ALL setups found in the folder, ordered by confidence.

    A single project can carry several ecosystems (a PHP back end + a front
    end built with npm). Seeing them all and choosing one beats getting stuck
    on the first.
    """
    root = Path(root).expanduser()
    if not root.is_dir():
        return []
    found: list[Harness] = []
    for detect in _DETECTORS:
        try:
            if (harness := detect(root)) is not None:
                found.append(harness)
        except OSError:  # pragma: no cover - an inaccessible file does not stop detection
            continue
    found.sort(key=lambda h: (-h.confidence, h.kind != "test"))
    return found


def detect(root: Path | str) -> Harness | None:
    """The setup with the strongest evidence; None if there is none."""
    all_found = detect_all(root)
    return all_found[0] if all_found else None


def detect_text(root: Path) -> str:
    """What is said when no setup is found. NO invented command."""
    return (
        f"{root} altında test düzeneği bulunamadı — ne pytest yapılandırması, "
        "ne package.json'da `scripts.test`, ne phpunit, ne go.mod/Cargo.toml. "
        "Sana bir komut uydurmayacağım. Bu değişikliği doğrulamak istiyorsan "
        "uygulamayı gerçekten çalıştır (sayfayı aç, betiği koştur) ve çıktısına bak."
    )


# -- output normalisation ----------------------------------------------
#
# Separate, pure functions: so that parsing can be verified even when the
# runner is not installed on this machine. Same rationale as the parsers in
# `diagnostics` — we embed real output texts in the tests and verify against
# those.

_STRIP_EDGES = re.compile(r"^[=\-_\s]+|[=\-_\s]+$")


def _lines(text: str) -> list[str]:
    return text.replace("\r\n", "\n").replace("\r", "\n").split("\n")


# pytest -q last line: "1 failed, 6 passed in 0.42s" (in bold mode it comes
# wrapped in `=`; we recognise both forms).
_PYTEST_SUMMARY = re.compile(r"\b(\d+)\s+(passed|failed|errors?|skipped|xfailed|"
                             r"xpassed|deselected)\b")
_PYTEST_DURATION = re.compile(r"\bin\s+[\d.]+\s*s(econds)?\b")
_PYTEST_FAILED = re.compile(r"^(FAILED|ERROR)\s+(?P<name>\S+?)(?:\s+-\s+(?P<message>.*))?$")
# Header in the FAILURES section: "____________ test_something ____________"
_PYTEST_HEADER = re.compile(r"^_{3,}\s+(?P<name>.+?)\s+_{3,}$")
_PYTEST_LOCATION = re.compile(r"^(?P<file>[A-Za-z]?[^\s:]*\.py):(?P<line>\d+):\s")


def _pytest_locations(output: str) -> dict[str, str]:
    """Test name → "file:line" mapping from the FAILURES blocks.

    The block header gives the test's name; the last `file.py:12:` line in
    the block gives where the error blew up. If we cannot find it we leave
    it empty — inventing a location means opening the wrong file.
    """
    locations: dict[str, str] = {}
    name: str | None = None
    for line in _lines(output):
        if m := _PYTEST_HEADER.match(line.strip()):
            name = m["name"].strip()
            continue
        if name and (m := _PYTEST_LOCATION.match(line.strip())):
            locations[name] = f"{m['file']}:{m['line']}"
    return locations


def _read_pytest(output: str) -> tuple[Count, list[Failure]]:
    count = Count()
    for line in reversed(_lines(output)):
        flat = _STRIP_EDGES.sub("", line).strip()
        if not flat or not _PYTEST_DURATION.search(flat):
            continue
        parts = _PYTEST_SUMMARY.findall(flat)
        if not parts:
            if "no tests ran" in flat:
                count.parsed = True
            break
        for number, kind in parts:
            n = int(number)
            if kind == "passed":
                count.passed += n
            elif kind in ("failed", "error", "errors"):
                count.failed += n
            elif kind in ("skipped", "deselected"):
                count.skipped += n
            elif kind == "xfailed":
                count.skipped += n
            elif kind == "xpassed":
                count.passed += n
        count.parsed = True
        break
    count.total = count.passed + count.failed + count.skipped

    locations = _pytest_locations(output)
    failures: list[Failure] = []
    for line in _lines(output):
        if not (m := _PYTEST_FAILED.match(line.strip())):
            continue
        name = m["name"]
        short = name.rsplit("::", 1)[-1]
        file_name = name.split("::", 1)[0]
        failures.append(
            Failure(name, (m["message"] or "").strip(), locations.get(short, file_name))
        )
    return count, failures


# The phpunit closing comes in two forms:
#   OK (5 tests, 7 assertions)
#   Tests: 5, Assertions: 7, Errors: 1, Failures: 2, Skipped: 1.
_PHPUNIT_OK = re.compile(r"^OK\s*\((?P<tests>\d+) tests?", re.M)
_PHPUNIT_SUMMARY = re.compile(r"^Tests:\s*(?P<tests>\d+)(?P<tail>.*)$", re.M)
_PHPUNIT_PART = re.compile(r"\b(Failures|Errors|Skipped|Incomplete|Risky):\s*(\d+)")
# "1) App\Tests\FooTest::testBar"
_PHPUNIT_HEADER = re.compile(r"^(?P<no>\d+)\)\s+(?P<name>\S+::\S+|\S+)\s*$")
_PHPUNIT_LOCATION = re.compile(r"^(?P<file>.+\.php):(?P<line>\d+)\s*$")


def _read_phpunit(output: str) -> tuple[Count, list[Failure]]:
    count = Count()
    if m := _PHPUNIT_OK.search(output):
        count.passed = int(m["tests"])
        count.total = count.passed
        count.parsed = True
    elif m := _PHPUNIT_SUMMARY.search(output):
        count.total = int(m["tests"])
        numbers = {name: int(value)
                   for name, value in _PHPUNIT_PART.findall(m["tail"])}
        count.failed = numbers.get("Failures", 0) + numbers.get("Errors", 0)
        count.skipped = (numbers.get("Skipped", 0) + numbers.get("Incomplete", 0)
                         + numbers.get("Risky", 0))
        count.passed = max(0, count.total - count.failed - count.skipped)
        count.parsed = True
    elif "No tests executed" in output:
        count.parsed = True

    failures: list[Failure] = []
    name: str | None = None
    messages: list[str] = []
    location = ""

    def close() -> None:
        if name is not None:
            failures.append(
                Failure(name, " ".join(messages).strip()[:300], location))

    for raw in _lines(output):
        line = raw.strip()
        if m := _PHPUNIT_HEADER.match(line):
            close()
            name, messages, location = m["name"], [], ""
            continue
        if name is None:
            continue
        if m := _PHPUNIT_LOCATION.match(line):
            location = f"{Path(m['file']).name}:{m['line']}"
            continue
        if line.startswith(("FAILURES!", "ERRORS!", "OK ", "Tests:")):
            close()
            name = None
            continue
        if line:
            messages.append(line)
    close()
    return count, failures


# jest / vitest / mocha / node --test — we do not know which one stands
# behind `npm test`, so we try them in turn.
_JEST_SUMMARY = re.compile(r"^Tests:\s+(?P<body>.+)$", re.M)
_JEST_PART = re.compile(r"(\d+)\s+(failed|passed|skipped|todo|total|pending)")
_JEST_FAILED = re.compile(r"^\s*●\s+(?P<name>.+?)\s*$", re.M)
_VITEST_SUMMARY = re.compile(r"^\s*Tests\s+(?P<body>.*?\(\d+\))\s*$", re.M)
_VITEST_PART = re.compile(r"(\d+)\s+(failed|passed|skipped|todo)")
_MOCHA_PASSED = re.compile(r"^\s*(\d+)\s+passing\b", re.M)
_MOCHA_FAILED = re.compile(r"^\s*(\d+)\s+failing\b", re.M)
_MOCHA_SKIPPED = re.compile(r"^\s*(\d+)\s+pending\b", re.M)
_NODETEST = re.compile(r"^#\s*(pass|fail|skipped|tests)\s+(\d+)\s*$", re.M)
# A mocha failure spans two lines:
#   1) Hesap makinesi
#        toplar:
#      AssertionError: expected 3 to equal 4
_MOCHA_HEADER = re.compile(r"^\s*\d+\)\s+(?P<name>.+?)\s*$")


def _mocha_failures(output: str) -> list[Failure]:
    """Joins mocha's failure headers that span two lines."""
    lines = _lines(output)
    found: list[Failure] = []
    for i, line in enumerate(lines):
        if not (m := _MOCHA_HEADER.match(line)):
            continue
        name = m["name"].strip()
        message = ""
        for following in lines[i + 1: i + 5]:
            flat = following.strip()
            if not flat:
                continue
            if flat.endswith(":") and not name.endswith(":"):
                name = f"{name} › {flat.rstrip(':')}"
                continue
            message = flat[:200]
            break
        found.append(Failure(name, message))
    return found


def _read_node(output: str) -> tuple[Count, list[Failure]]:
    count = Count()
    failures: list[Failure] = []

    if m := _JEST_SUMMARY.search(output):
        for number, kind in _JEST_PART.findall(m["body"]):
            n = int(number)
            if kind == "passed":
                count.passed = n
            elif kind == "failed":
                count.failed = n
            elif kind in ("skipped", "todo", "pending"):
                count.skipped += n
            elif kind == "total":
                count.total = n
        count.parsed = True
        failures = [Failure(a.strip()) for a in _JEST_FAILED.findall(output)]
    elif m := _VITEST_SUMMARY.search(output):
        for number, kind in _VITEST_PART.findall(m["body"]):
            n = int(number)
            if kind == "passed":
                count.passed = n
            elif kind == "failed":
                count.failed = n
            else:
                count.skipped += n
        count.parsed = True
    elif (passed := _MOCHA_PASSED.search(output)) or (
            failed := _MOCHA_FAILED.search(output)):
        skipped = _MOCHA_SKIPPED.search(output)
        failed = _MOCHA_FAILED.search(output)
        count.passed = int(passed.group(1)) if passed else 0
        count.failed = int(failed.group(1)) if failed else 0
        count.skipped = int(skipped.group(1)) if skipped else 0
        count.parsed = True
        failures = _mocha_failures(output)
    elif parts := _NODETEST.findall(output):
        data = {kind: int(number) for kind, number in parts}
        count.passed = data.get("pass", 0)
        count.failed = data.get("fail", 0)
        count.skipped = data.get("skipped", 0)
        count.total = data.get("tests", 0)
        count.parsed = True

    if not count.total:
        count.total = count.passed + count.failed + count.skipped
    return count, failures


# go test: without `-v` individual test names are not printed; we do not
# invent the count.
_GO_FAIL = re.compile(r"^\s*--- FAIL:\s+(?P<name>\S+)", re.M)
_GO_PASS = re.compile(r"^\s*--- PASS:\s+\S+", re.M)
_GO_PACKAGE = re.compile(r"^(ok|FAIL)\s+(?P<package>\S+)", re.M)
_GO_LOCATION = re.compile(r"^\s+(?P<file>\S+\.go):(?P<line>\d+):\s*(?P<message>.*)$", re.M)


def _read_go(output: str) -> tuple[Count, list[Failure]]:
    count = Count()
    failed = _GO_FAIL.findall(output)
    passed = _GO_PASS.findall(output)
    if failed or passed:
        count.passed = len(passed)
        count.failed = len(failed)
        count.total = count.passed + count.failed
        count.parsed = True

    locations = _GO_LOCATION.findall(output)
    failures = []
    for i, name in enumerate(failed):
        file_name, line, message = locations[i] if i < len(locations) else ("", "", "")
        failures.append(
            Failure(name, message.strip(), f"{file_name}:{line}" if file_name else "")
        )
    return count, failures


# cargo: "test result: FAILED. 3 passed; 1 failed; 0 ignored; ..."
_CARGO_RESULT = re.compile(
    r"^test result:\s+\w+\.\s+(?P<passed>\d+) passed;\s*(?P<failed>\d+) failed;"
    r"\s*(?P<skipped>\d+) ignored", re.M)
_CARGO_FAILED = re.compile(r"^\s{4}(?P<name>[\w:]+)\s*$", re.M)


def _read_cargo(output: str) -> tuple[Count, list[Failure]]:
    count = Count()
    for m in _CARGO_RESULT.finditer(output):
        count.passed += int(m["passed"])
        count.failed += int(m["failed"])
        count.skipped += int(m["skipped"])
        count.parsed = True
    count.total = count.passed + count.failed + count.skipped

    failures: list[Failure] = []
    if "\nfailures:\n" in output and count.failed:
        tail = output.rsplit("\nfailures:\n", 1)[1]
        for name in _CARGO_FAILED.findall(tail):
            if name not in [f.name for f in failures]:
                failures.append(Failure(name))
    return count, failures


# dotnet: "Failed!  - Failed:     1, Passed:     2, Skipped:     0, Total:     3"
_DOTNET_SUMMARY = re.compile(
    r"Failed:\s*(?P<failed>\d+),\s*Passed:\s*(?P<passed>\d+),"
    r"\s*Skipped:\s*(?P<skipped>\d+),\s*Total:\s*(?P<total>\d+)")
_DOTNET_FAILED = re.compile(r"^\s*(?:X|Failed)\s+(?P<name>\S+)", re.M)


def _read_dotnet(output: str) -> tuple[Count, list[Failure]]:
    count = Count()
    for m in _DOTNET_SUMMARY.finditer(output):
        count.failed += int(m["failed"])
        count.passed += int(m["passed"])
        count.skipped += int(m["skipped"])
        count.total += int(m["total"])
        count.parsed = True
    failures = [Failure(name) for name in _DOTNET_FAILED.findall(output)]
    return count, failures


_READERS = {
    "python": _read_pytest,
    "php": _read_phpunit,
    "node": _read_node,
    "go": _read_go,
    "rust": _read_cargo,
    "dotnet": _read_dotnet,
}


def normalize(ecosystem: str, output: str) -> tuple[Count, list[Failure]]:
    """Reduces raw output to the common frame.

    If `ecosystem` is "oto" the readers are tried in turn and the first one
    that can read a count wins — with a hand-given command we do not know
    which runner is speaking. If none can read it, `Count.parsed` stays False
    and the result text says so explicitly: there is no invented "0 failed".
    """
    if ecosystem in _READERS:
        return _READERS[ecosystem](output)
    for read in (_read_pytest, _read_phpunit, _read_node, _read_cargo, _read_dotnet,
                 _read_go):
        count, failures = read(output)
        if count.parsed:
            return count, failures
    return Count(), []


def trim(text: str, limit: int = MAX_RAW) -> str:
    """Trimming that keeps the head and the tail.

    Runners print what they ran at the start and the summary at the end; the
    stack traces in the middle teach the model nothing and eat the window.
    """
    text = text.strip()
    if len(text) <= limit:
        return text
    head = text[: limit // 2].rstrip()
    tail = text[-(limit // 2):].lstrip()
    dropped = len(text) - len(head) - len(tail)
    return f"{head}\n\n... [{dropped} karakter kırpıldı] ...\n\n{tail}"


# -- running ------------------------------------------------------------


def _parse(name: str) -> str | None:
    """Turns the logical tool name into a real executable.

    For `php`, `diagnostics.checker_path` is used: on Windows PHP is often
    not on PATH (XAMPP, Laragon, winget) and it is already looked for there.
    There is no point in writing the same knowledge twice.
    """
    if name in ("py", "python3", "python"):
        return shutil.which(name) or sys.executable
    if name == "php":
        return diagnostics.checker_path("php")
    return shutil.which(name)


async def run_harness(
    harness: Harness,
    *,
    timeout: float = DEFAULT_TIMEOUT,
    cancel: asyncio.Event | None = None,
) -> Result:
    """Runs the setup and returns the normalised result."""
    if not harness.runnable:
        return Result(harness.ecosystem, harness.label, str(harness.root),
                      "yok", raw=harness.blocker, notes=list(harness.notes),
                      kind=harness.kind)

    exe = _parse(harness.argv[0])
    if exe is None:
        return Result(
            harness.ecosystem, harness.label, str(harness.root), "baslatilamadi",
            raw=f"`{harness.argv[0]}` bu makinede bulunamadı.",
            notes=list(harness.notes), kind=harness.kind,
        )
    return await _run(
        [exe, *harness.argv[1:]], harness.root, harness.ecosystem, harness.label,
        timeout=timeout, cancel=cancel, notes=list(harness.notes),
        kind=harness.kind,
    )


async def run_command(
    command: str,
    root: Path,
    *,
    ecosystem: str = "oto",
    timeout: float = DEFAULT_TIMEOUT,
    cancel: asyncio.Event | None = None,
) -> Result:
    """Runs a hand-given command (overriding detection).

    Goes through the shell: in a string like `npm test -- --filter x` pipes
    and flags are expected to work. The permission gate sees this command as
    the subject (`komut` is in `permissions.SUBJECT_KEYS`).
    """
    return await _run(None, root, ecosystem, command, shell=command,
                      timeout=timeout, cancel=cancel)


async def _kill(proc) -> None:
    """Terminates the process and EVERYTHING beneath it.

    The body moved to `environment`: the same wound showed up in the hooks
    (killing the shell leaves the real process behind; because the pipes stay
    open the caller hangs), so this is not a test-runner matter but the right
    way to kill a subprocess in this environment.
    """
    await environment.kill_tree(proc)


async def _run(
    argv: list[str] | None,
    root: Path,
    ecosystem: str,
    label: str,
    *,
    shell: str | None = None,
    timeout: float,
    cancel: asyncio.Event | None,
    notes: list[str] | None = None,
    kind: str = "test",
) -> Result:
    """The shared run path: start, race against cancellation, normalise output.

    With flags that keep a console window from opening
    (`environment.quiet_flags`): while dornick runs under pythonw every test
    run used to flash a cmd window on the screen.
    """
    timeout = max(1.0, min(float(timeout), MAX_TIMEOUT))
    start = time.monotonic()
    common = dict(
        cwd=str(root),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        # Colour escape sequences break parsing and send junk to the model.
        env={**os.environ, "NO_COLOR": "1", "FORCE_COLOR": "0",
             "PYTEST_ADDOPTS": "--color=no"},
        **environment.quiet_flags(),
    )
    if sys.platform != "win32":  # pragma: no cover - POSIX path
        # Own process group: on timeout the whole tree dies in one stroke.
        common["start_new_session"] = True
    try:
        if shell is not None:
            proc = await asyncio.create_subprocess_shell(shell, **common)
        else:
            proc = await asyncio.create_subprocess_exec(*(argv or []), **common)
    except (OSError, ValueError) as exc:
        return Result(ecosystem, label, str(root), "baslatilamadi",
                      raw=f"{type(exc).__name__}: {exc}",
                      notes=notes or [], kind=kind)

    comm = asyncio.ensure_future(proc.communicate())
    pending = {comm}
    stop = None
    if cancel is not None:
        stop = asyncio.ensure_future(cancel.wait())
        pending.add(stop)

    try:
        done, _ = await asyncio.wait(
            pending, timeout=timeout,
            return_when=asyncio.FIRST_COMPLETED,
        )
    except asyncio.CancelledError:  # pragma: no cover - turn cancelled
        proc.kill()
        await proc.wait()
        comm.cancel()
        if stop is not None:
            stop.cancel()
        raise

    elapsed = time.monotonic() - start

    if comm not in done:
        # Timeout or user interruption. Kill the process TREE and be honest
        # with whatever we have: partial output is information too — the
        # name of the hanging test is usually on the last line.
        interrupted = stop is not None and stop in done
        await _kill(proc)
        try:
            partial, _ = await asyncio.wait_for(comm, 5)
        except (asyncio.TimeoutError, asyncio.CancelledError, OSError):
            comm.cancel()
            partial = b""
        if stop is not None:
            stop.cancel()
        piece = (partial or b"").decode("utf-8", errors="replace")
        return Result(ecosystem, label, str(root),
                      "kesildi" if interrupted else "zaman_asimi", duration=elapsed,
                      raw=trim(piece.replace("\r\n", "\n")),
                      notes=notes or [], kind=kind)

    if stop is not None:
        stop.cancel()
    data, _ = comm.result()
    text = (data or b"").decode("utf-8", errors="replace")
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    count, failures = normalize(ecosystem, text)
    return Result(
        ecosystem=ecosystem, label=label, root=str(root), status="kostu",
        exit_code=proc.returncode or 0, duration=elapsed, count=count,
        failures=failures, raw=trim(text), notes=notes or [], kind=kind,
    )


# -- post-write reminder -----------------------------------------------
#
# A test run is EXPENSIVE: seconds, minutes on big suites. Running it
# automatically after every `write_file` freezes the turn and keeps the user
# waiting — and the agent usually writes the same file several times in a
# row, so every run in between is wasted. Instead we report that the setup
# EXISTS: information is free, a run is expensive, the decision is the model's.

# After this many writes to the same file the reminder hardens. A third write
# means "trial and error": the model is trying to fix the code by eye and,
# unable to see, keeps going round in circles. There a run is no longer a
# suggestion but a necessity.
NAG_THRESHOLD = 3


def reminder(path: Path | str, *, writes: int = 1) -> str:
    """A one-line note if the written file's project has a test setup.

    Empty string = nothing to say (not a project, no setup). Producing no
    noise is essential: adding a meaningless sentence under every write makes
    the real warnings go unread too.
    """
    try:
        root = project_root(path)
        harness = detect(root)
    except OSError:  # pragma: no cover - access errors are swallowed silently
        return ""
    if harness is None:
        return ""

    if harness.blocker:
        return (f"koşum: bu projede {harness.label} düzeneği var ama "
                f"{harness.blocker}")

    if harness.kind == "saglik":
        body = (f"bu projede test takımı yok; `{harness.label}` ucuz bir "
                f"sağlık denetimi ({harness.evidence})")
    else:
        body = f"bu projede `{harness.label}` var ({harness.evidence})"

    if writes >= NAG_THRESHOLD:
        return (f"koşum: {body} — aynı dosyaya {writes}. kez yazıyorsun. "
                "Gözle düzeltmeyi bırak, `kos` aracıyla çalıştır ve gerçek "
                "hatayı gör.")
    return f"koşum: {body} — değişikliği doğrulamak için `kos` aracını kullan."


# -- last touched project ----------------------------------------------
#
# `kos` must be callable without a path: the model should not have to write
# the project of the file it just wrote all over again. The file tools update
# this on every write; a single module-level value, because one agent writes
# in one session, and even if guessed wrong the result carries the full path
# of the root — the model corrects it the moment it sees it.
_LAST_PROJECT: list[Path] = []


def touched(path: Path | str) -> None:
    """A file was written/edited: remember its project."""
    try:
        _LAST_PROJECT[:] = [project_root(path)]
    except OSError:  # pragma: no cover
        pass


def last_project() -> Path | None:
    return _LAST_PROJECT[0] if _LAST_PROJECT else None


def forget() -> None:
    """For tests: clears the remembered project."""
    _LAST_PROJECT.clear()
