"""Shared grading library of the coding benchmark.

The philosophy comes from the memory-side `eval/context_memory/scale_bench.py`
and fits in four points:

  1. **Frozen dataset.** Tasks and seed files sit fixed in the repo. The
     same task asks the same thing today and six months from now; the
     difference between two runs is the product's difference, never the
     ruler's.
  2. **The product's REAL code path is measured.** There, `loop.select_prime`
     was called directly; here, the task goes to the real agent through the
     product's own external gate (POST /api/gate). Not an imitation of the
     agent — the agent itself.
  3. **One shot.** The grader gives the agent no second chance, no hint, no
     fix-up round. Neither does the user — "I said it once, I want
     something that works."
  4. **No parametric-copy drift.** There, the copy was asserted equal to the
     product on every run. The counterpart here: the grader does NOT trust
     the agent's tests. It builds its own harness in its own temp dir and
     overwrites regression suites with pristine copies. Editing the tests
     earns no points.

A fifth point specific to this side — **honesty**:

     No partial credit is invented for an unmeasurable axis.
     `Axis.earned is None` means "unmeasurable" and the axis leaves the
     denominator too. Work the brief did not request (tests, when the
     brief asked for none) is measured with `external=True`, reported,
     but never scored — no penalty for work not asked, no free points
     for it either.

Score axes and weights:

    WORKS            40   setup / boot / HTTP 200 / CLI exit codes
    REQUESTED SCOPE  25   file-endpoint-function presence + behaviour tests
    CODE HEALTH      20   diagnostics, file size/complexity, duplication
    TEST QUALITY     15   do the tests run, how many, do they hit the critical path
"""

from __future__ import annotations

import http.cookiejar
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

# Axis names and ceilings. One place; the report reads from here too.
AXES: dict[str, int] = {
    "works": 40,
    "scope": 25,
    "health": 20,
    "tests": 15,
}

AXIS_TITLES = {
    "works": "works",
    "scope": "requested scope",
    "health": "code health",
    "tests": "test quality",
}

# Folders excluded from scanning: tool debris, dependency stores, VCS.
SKIP_DIRS = frozenset({
    ".git", "__pycache__", "node_modules", ".venv", "venv", "vendor",
    ".pytest_cache", ".ruff_cache", ".geri-donusum", "dist", "build",
    ".neocp", ".idea", ".vscode",
})

SOURCE_EXT = {".py": "python", ".php": "php", ".js": "node", ".mjs": "node"}

# List of files excluded from grading (POSIX paths relative to the workshop
# root, JSON array). The runner writes it: files that were in the workshop
# BEFORE the turn and never CHANGED during it. Two sources, neither the
# agent's work:
#   * the standard skills neo copies into the workshop at boot,
#   * the task's seed files.
# The code-health score suffered for exactly this in an early run: the
# whole complexity penalty came from the product's own skill files. A seed
# file the agent TOUCHED is not listed — repair tasks depend on the fixed
# file staying in scope.
EXCLUDE_FILE = ".olcum-haric"

# Sane upper bound for a subprocess. The agent's code cannot run forever.
DEFAULT_TIMEOUT = 90.0


# -- subprocess ---------------------------------------------------------


@dataclass(slots=True)
class Run:
    """Raw result of one subprocess run."""

    argv: list[str]
    code: int | None         # None => timeout, or never started
    out: str
    err: str
    seconds: float
    crash: str = ""          # why the process never started, if it didn't

    @property
    def ok(self) -> bool:
        return self.code == 0

    @property
    def both(self) -> str:
        return f"{self.out}\n{self.err}"

    def brief(self, n: int = 200) -> str:
        body = " ".join(self.both.split())
        return body[:n]


def shell(
    argv: Sequence[str],
    *,
    cwd: Path | str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    stdin_text: str | None = None,
    env_extra: dict[str, str] | None = None,
) -> Run:
    """Run a command and return the raw result.

    Never raises: the grader must not crash together with the thing it is
    measuring. A crashed run comes back with `code=None`, and the axis
    INTERPRETS that as either "did not work" (measured, zero) or
    "unmeasurable" — different things, and the caller decides which.
    """
    env = dict(os.environ)
    if env_extra:
        env.update(env_extra)
    # Subprocess output may be non-ASCII: on Windows a cp1254 fallback breaks it.
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONUTF8", "1")
    started = time.perf_counter()
    try:
        done = subprocess.run(
            list(argv),
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            input=stdin_text,
            timeout=timeout,
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        return Run(list(argv), None, exc.stdout or "", exc.stderr or "",
                   time.perf_counter() - started, crash="timeout")
    except (OSError, ValueError) as exc:
        return Run(list(argv), None, "", "", time.perf_counter() - started,
                   crash=f"{type(exc).__name__}: {exc}")
    return Run(list(argv), done.returncode, done.stdout or "",
               done.stderr or "", time.perf_counter() - started)


def _py() -> list[str]:
    """The interpreter running this rig — sidesteps the `py`/`python` split."""
    return [sys.executable]


def has_php() -> bool:
    return shell(["php", "-v"], timeout=15).code == 0


def has_node() -> bool:
    return shell(["node", "-v"], timeout=15).code == 0


def has_ruff() -> bool:
    return shell([*_py(), "-m", "ruff", "--version"], timeout=20).code == 0


# -- file discovery -----------------------------------------------------


def excluded(root: Path) -> set[str]:
    """Files excluded from grading (see EXCLUDE_FILE)."""
    path = root / EXCLUDE_FILE
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    return {str(p) for p in data} if isinstance(data, list) else set()


def sources(root: Path, *exts: str) -> list[Path]:
    """Source files the agent produced (tool debris and exclusions removed).

    Deterministic order: grading the same workshop twice gives the same list.
    """
    wanted = set(exts) or set(SOURCE_EXT)
    skip = excluded(root)
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames
                             if d not in SKIP_DIRS and not d.startswith("."))
        for name in sorted(filenames):
            path = Path(dirpath) / name
            if path.suffix.lower() not in wanted:
                continue
            if path.relative_to(root).as_posix() in skip:
                continue
            found.append(path)
    return found


def find(root: Path, *names: str) -> Path | None:
    """Return the first of the given names found (root first, shallow first).

    The agent may have put the file at the root or in a subfolder; both are
    fine. No name matches → None — the axis then says "missing", it never
    invents.
    """
    targets = [n.casefold() for n in names]
    found: list[tuple[int, str, Path]] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames
                             if d not in SKIP_DIRS and not d.startswith("."))
        depth = len(Path(dirpath).relative_to(root).parts)
        for name in filenames:
            if name.casefold() in targets:
                found.append((depth, name.casefold(), Path(dirpath) / name))
    if not found:
        return None
    # Requested name order first, then the shallower one.
    found.sort(key=lambda t: (targets.index(t[1]), t[0], str(t[2])))
    return found[0][2]


def find_pattern(root: Path, pattern: str) -> list[Path]:
    """Regex search by file name (used to locate test files)."""
    rx = re.compile(pattern, re.IGNORECASE)
    return [p for p in sources(root) if rx.search(p.name)]


def read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


# -- axis / scorecard ---------------------------------------------------


@dataclass
class Axis:
    """One score axis.

    earned is None → UNMEASURABLE. The axis leaves the denominator, the
                     report prints "unmeasurable", and `reason` says why.
    external       → NOT REQUESTED. Measured and reported but not scored
                     (skipping tests is no flaw when the brief asked for none).
    """

    name: str
    ceiling: int
    earned: float | None = None
    evidence: list[str] = field(default_factory=list)
    reason: str = ""
    external: bool = False

    @property
    def counted(self) -> bool:
        return self.earned is not None and not self.external

    @property
    def title(self) -> str:
        return AXIS_TITLES.get(self.name, self.name)

    def render(self) -> str:
        if self.earned is None:
            return "unmeasurable"
        label = f"{self.earned:.1f}/{self.ceiling}"
        return f"{label} (not requested)" if self.external else label

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name, "ceiling": self.ceiling, "earned": self.earned,
            "evidence": self.evidence, "reason": self.reason,
            "external": self.external,
        }


class Tally:
    """Checklist accumulator: every item weighted and evidenced.

    Partial credit only comes from an item actually done; no score is
    invented because an item is "half there". An unmeasurable item drops
    from the list AND the ceiling via `skip()`.
    """

    def __init__(self) -> None:
        self.ceiling = 0.0
        self.earned = 0.0
        self.evidence: list[str] = []
        self.skipped: list[str] = []

    def item(self, name: str, weight: float, passed: bool, note: str = "") -> bool:
        self.ceiling += weight
        if passed:
            self.earned += weight
        mark = "+" if passed else "-"
        extra = f" — {note}" if note else ""
        self.evidence.append(f"{mark} {name} ({weight:g}p){extra}")
        return passed

    def ratio(self, name: str, weight: float, fraction: float, note: str = "") -> float:
        """Continuous measurement (e.g. clean-syntax ratio). Clamped to 0..1."""
        fraction = max(0.0, min(1.0, float(fraction)))
        self.ceiling += weight
        gain = weight * fraction
        self.earned += gain
        extra = f" — {note}" if note else ""
        self.evidence.append(f"~ {name} ({gain:.1f}/{weight:g}p){extra}")
        return gain

    def skip(self, name: str, reason: str) -> None:
        self.skipped.append(f"? {name} — unmeasurable: {reason}")
        self.evidence.append(f"? {name} — unmeasurable: {reason}")

    def axis(self, name: str, ceiling: int, *, external: bool = False) -> Axis:
        """Scale the collected items to the axis ceiling."""
        if self.ceiling <= 0:
            return Axis(name, ceiling, None, self.evidence,
                        reason="no item could be measured", external=external)
        return Axis(name, ceiling, ceiling * (self.earned / self.ceiling),
                    self.evidence, external=external)


@dataclass
class Scorecard:
    """One task's card for a single run."""

    task: str
    axes: list[Axis]
    behavior: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    @property
    def measured_ceiling(self) -> float:
        return sum(a.ceiling for a in self.axes if a.counted)

    @property
    def raw(self) -> float:
        return sum(a.earned or 0.0 for a in self.axes if a.counted)

    @property
    def score(self) -> float | None:
        """Score normalised to 0–100; None if unmeasurable.

        The WORKS axis is the carrier: if it could not be measured, there
        is NO score. The rule comes from a measured lie — in one run the
        agent left its own `php -S` open, the grader found the port held
        and marked works/scope unmeasurable, only code health (20/20)
        remained, and the normalised score came out **100.0**. If we could
        not check whether the delivery runs, being nicely written is not a
        grade.
        """
        carrier = self.axis("works")
        if carrier is not None and carrier.earned is None:
            return None
        ceiling = self.measured_ceiling
        return None if ceiling <= 0 else 100.0 * self.raw / ceiling

    @property
    def unmeasured(self) -> list[str]:
        return [a.title for a in self.axes if a.earned is None]

    def axis(self, name: str) -> Axis | None:
        for a in self.axes:
            if a.name == name:
                return a
        return None

    @property
    def broken_delivery(self) -> bool:
        """Does the delivery not run at all? (WORKS axis at zero)"""
        a = self.axis("works")
        return a is not None and a.earned is not None and a.earned <= 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "task": self.task,
            "score": self.score,
            "raw": self.raw,
            "measured_ceiling": self.measured_ceiling,
            "unmeasured": self.unmeasured,
            "broken_delivery": self.broken_delivery,
            "axes": [a.as_dict() for a in self.axes],
            "behavior": self.behavior,
            "notes": self.notes,
        }


# -- code health --------------------------------------------------------


def syntax(path: Path) -> tuple[bool, str]:
    """Run the file through its language's diagnostic tool.

    Unknown language or missing tool → (True, "skipped"): the absence of a
    tool is not the agent's flaw. The caller sees this via the skip count.
    """
    lang = SOURCE_EXT.get(path.suffix.lower())
    if lang == "python":
        r = shell([*_py(), "-m", "py_compile", str(path)], timeout=40)
    elif lang == "php":
        r = shell(["php", "-l", str(path)], timeout=40)
    elif lang == "node":
        r = shell(["node", "--check", str(path)], timeout=40)
    else:
        return True, "skipped"
    if r.code is None:
        return True, "skipped"
    return r.ok, r.brief(160)


def _indent_depth(lines: Iterable[str]) -> int:
    """Deepest indent level (a rough complexity signal)."""
    deepest = 0
    for line in lines:
        if not line.strip() or line.lstrip().startswith(("#", "//", "*")):
            continue
        pad = len(line) - len(line.lstrip(" \t"))
        deepest = max(deepest, pad // 4 + line[:pad].count("\t"))
    return deepest


_FUNC = re.compile(r"^\s*(def |function |async function |public function |"
                   r"private function |protected function )", re.MULTILINE)


def _longest_function(text: str) -> int:
    """Longest gap between function starts — a rough "giant function" measure."""
    starts = [text[:m.start()].count("\n") for m in _FUNC.finditer(text)]
    if not starts:
        return 0
    starts.append(text.count("\n"))
    return max(b - a for a, b in zip(starts, starts[1:]))


def duplication(files: Sequence[Path], window: int = 6) -> tuple[float, int]:
    """Copy-paste measure: how often does the same 6-line block repeat?

    Lines are normalised (whitespace collapsed) so an indent change cannot
    hide a copy. Returns (fraction of repeated lines, repeated block count).
    """
    seen: dict[str, int] = {}
    repeated = 0
    total = 0
    for path in files:
        lines = [" ".join(l.split()) for l in read(path).splitlines()]
        lines = [l for l in lines
                 if l and not l.startswith(("#", "//", "*", "/*"))]
        total += len(lines)
        for i in range(len(lines) - window + 1):
            sig = "\n".join(lines[i:i + window])
            seen[sig] = seen.get(sig, 0) + 1
            if seen[sig] == 2:
                repeated += window
    if total <= window:
        return 0.0, 0
    blocks = sum(1 for v in seen.values() if v > 1)
    return min(1.0, repeated / total), blocks


def health_axis(root: Path, *, ceiling: int = 20) -> Axis:
    """CODE HEALTH: diagnostics (8) + size/complexity (6) + duplication (6).

    Independent of the agent's own tests: things an outside eye can say
    about the files.
    """
    files = [p for p in sources(root) if p.suffix.lower() in SOURCE_EXT]
    # We measure the code the agent produced, not dependencies it pulled.
    if not files:
        return Axis("health", ceiling, None, [],
                    reason="no source files in the workshop")

    t = Tally()

    # 1. Syntax / diagnostics.
    clean = 0
    skipped = 0
    broken: list[str] = []
    for path in files:
        ok, message = syntax(path)
        if message == "skipped":
            skipped += 1
        if ok:
            clean += 1
        else:
            broken.append(f"{path.name}: {message}")
    if skipped == len(files):
        t.skip("syntax", "no diagnostic tool for any file")
    else:
        t.ratio("clean syntax", 8, clean / len(files),
                f"{clean}/{len(files)} files" +
                (f"; broken: {'; '.join(broken[:3])}" if broken else ""))

    # 2. Size and rough complexity. The thresholds are deliberately coarse:
    #    this axis is not a linter, it is a "did any file get away" glance.
    long_files: list[str] = []
    deep_files: list[str] = []
    giants: list[str] = []
    for path in files:
        text = read(path)
        lines = text.splitlines()
        if len(lines) > 400:
            long_files.append(f"{path.name}:{len(lines)} lines")
        d = _indent_depth(lines)
        if d > 5:
            deep_files.append(f"{path.name}:{d} levels")
        g = _longest_function(text)
        if g > 80:
            giants.append(f"{path.name}:{g}-line function")
    violations = len(long_files) + len(deep_files) + len(giants)
    t.ratio("size/complexity", 6,
            1.0 - min(1.0, violations / max(2.0, len(files))),
            "clean" if not violations
            else "; ".join((long_files + deep_files + giants)[:3]))

    # 3. Copy-paste.
    fraction, blocks = duplication(files)
    # Up to 3% tolerated (import blocks, standard scaffolds); zero at 25%.
    score_fraction = 1.0 - max(0.0, min(1.0, (fraction - 0.03) / 0.22))
    t.ratio("no duplication", 6, score_fraction,
            f"repeated lines {fraction * 100:.0f}%, {blocks} recurring blocks")

    return t.axis("health", ceiling)


# -- test quality -------------------------------------------------------


TEST_PATTERN = r"(^test_.*\.(py)$)|(_test\.(py|js|mjs)$)|(\.test\.(js|mjs)$)|(^test.*\.(js|mjs)$)|(Test\.php$)|(^test_.*\.php$)"

_TEST_FUNC = re.compile(
    r"^\s*(?:async\s+)?def\s+test\w*|"           # pytest
    r"\btest\s*\(\s*['\"]|"                       # node:test / jest
    r"\bit\s*\(\s*['\"]|"                          # mocha/jest
    r"^\s*public\s+function\s+test\w*",            # phpunit
    re.MULTILINE,
)

# "assert True"-style freebies: they inflate the count and measure nothing.
_EMPTY_ASSERT = re.compile(
    r"assert\s+(True|1)\s*$|assertTrue\s*\(\s*true\s*\)|expect\s*\(\s*true\s*\)",
    re.IGNORECASE | re.MULTILINE,
)
_ASSERT = re.compile(
    r"\bassert\b|\bassertEquals?\b|\bexpect\s*\(|\bstrictEqual\b|\bdeepEqual\b",
    re.IGNORECASE,
)


def test_files(root: Path) -> list[Path]:
    return find_pattern(root, TEST_PATTERN)


def run_tests(root: Path, files: Sequence[Path]) -> Run | None:
    """Run the agent's tests in their own language. Unknown language → None."""
    langs = {SOURCE_EXT.get(p.suffix.lower()) for p in files}
    if "python" in langs:
        return shell([*_py(), "-m", "pytest", "-q", "--no-header", "-p",
                      "no:cacheprovider", str(root)], cwd=root, timeout=180)
    if "node" in langs:
        # The path argument rejects folders on this node version; the
        # runner scans from the working directory itself.
        return shell(["node", "--test"], cwd=root, timeout=180)
    if "php" in langs:
        # Without PHPUnit, running the file directly is the only honest way.
        return shell(["php", str(files[0])], cwd=root, timeout=120)
    return None


def tests_axis(
    root: Path,
    *,
    critical: Sequence[str] = (),
    ceiling: int = 15,
    external: bool = False,
) -> Axis:
    """TEST QUALITY: do they run (6) + how many (4) + are they meaningful (5).

    `critical`: symbol names the tests are expected to touch in this task.
    If the tests never mention the critical path, the "meaningful" score
    drops — lots of tests that all poke a helper function means the suite
    does not hold the critical path.

    `external=True`: the brief asked for no tests. Measured, reported,
    not scored.
    """
    files = test_files(root)
    if not files:
        # This is NOT unmeasurable: we looked, and there were none. A real zero.
        return Axis("tests", ceiling, 0.0, ["- no test file (0p)"],
                    external=external)

    t = Tally()
    text = "\n".join(read(p) for p in files)
    count = len(_TEST_FUNC.findall(text))

    run = run_tests(root, files)
    if run is None or run.code is None:
        t.skip("tests run", run.crash if run else "test language unrecognised")
    else:
        t.item("tests green", 6, run.ok, run.brief(120))

    t.ratio("test count", 4, min(1.0, count / 6.0), f"{count} tests found")

    empty = len(_EMPTY_ASSERT.findall(text))
    asserts = len(_ASSERT.findall(text))
    if not critical:
        t.skip("critical path covered", "task declared no critical symbols")
    else:
        hit = [c for c in critical if c.casefold() in text.casefold()]
        t.ratio("critical path covered", 3, len(hit) / len(critical),
                f"{len(hit)}/{len(critical)}: {', '.join(hit) or 'none'}")
    t.ratio("assertions substantive", 2,
            0.0 if asserts == 0 else 1.0 - min(1.0, empty / asserts),
            f"{asserts} assertions, {empty} freebies")

    return t.axis("tests", ceiling, external=external)


# -- HTTP / server helpers ----------------------------------------------


def port_free(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket() as s:
        s.settimeout(0.4)
        return s.connect_ex((host, port)) != 0


def wait_port(port: int, seconds: float, host: str = "127.0.0.1") -> bool:
    deadline = time.time() + seconds
    while time.time() < deadline:
        with socket.socket() as s:
            s.settimeout(0.5)
            if s.connect_ex((host, port)) == 0:
                return True
        time.sleep(0.25)
    return False


@dataclass(slots=True)
class Response:
    code: int
    body: str
    headers: dict[str, str]
    url: str
    error: str = ""


class Browser:
    """Tiny cookie-aware client: the only way to measure login-guarded panels.

    Not following redirects is an option: the answer to "does ozet.php
    bounce me to login when I am not signed in" lives in the 302 itself.
    """

    def __init__(self) -> None:
        self.jar = http.cookiejar.CookieJar()
        self._following = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar))

        class _Stop(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *a: Any, **k: Any) -> None:  # noqa: D401
                return None

        self._nofollow = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar), _Stop)

    def request(
        self,
        url: str,
        *,
        data: bytes | None = None,
        json_body: dict[str, Any] | None = None,
        follow: bool = True,
        timeout: float = 15.0,
    ) -> Response:
        headers = {"User-Agent": "neocp-eval/1.0"}
        if json_body is not None:
            data = json.dumps(json_body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        elif data is not None:
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        request = urllib.request.Request(url, data=data, headers=headers)
        opener = self._following if follow else self._nofollow
        try:
            with opener.open(request, timeout=timeout) as answer:
                body = answer.read().decode("utf-8", "replace")
                return Response(answer.status, body, dict(answer.headers),
                                answer.url)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace") if exc.fp else ""
            return Response(exc.code, body, dict(exc.headers or {}), url)
        except (urllib.error.URLError, OSError, ValueError) as exc:
            return Response(0, "", {}, url, error=f"{type(exc).__name__}: {exc}")


class Server:
    """Boot the server the agent wrote; kill it when the run ends.

    `with Server(...) as s:` — `s.opened` says the port accepted a
    connection, `s.log` is everything the process printed. `s.dead` is
    True if the process died.
    """

    def __init__(
        self,
        argv: Sequence[str],
        *,
        cwd: Path,
        port: int,
        ready_s: float = 25.0,
    ) -> None:
        self.argv = list(argv)
        self.cwd = cwd
        self.port = port
        self.ready_s = ready_s
        self.process: subprocess.Popen[str] | None = None
        self.opened = False
        self.log = ""
        self.crash = ""

    def __enter__(self) -> "Server":
        env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
        try:
            self.process = subprocess.Popen(
                self.argv, cwd=str(self.cwd), stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                errors="replace", env=env,
            )
        except (OSError, ValueError) as exc:
            self.crash = f"{type(exc).__name__}: {exc}"
            return self
        self.opened = wait_port(self.port, self.ready_s)
        return self

    @property
    def dead(self) -> bool:
        return self.process is None or self.process.poll() is not None

    def __exit__(self, *_: Any) -> None:
        if self.process is None:
            return
        try:
            self.process.terminate()
            try:
                self.log = self.process.communicate(timeout=8)[0] or ""
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.log = self.process.communicate(timeout=8)[0] or ""
        except Exception:
            pass


PHP_CRASH = re.compile(
    r"Fatal error|Parse error|Warning:|Notice:|Deprecated:|Undefined "
    r"(variable|index|array key)|Uncaught \w*(Error|Exception)",
    re.IGNORECASE,
)


def page_healthy(r: Response, *, min_chars: int = 120) -> tuple[bool, str]:
    """Says whether a page ACTUALLY works.

    "It returned 200" is not enough: PHP happily serves a fatal error with
    a 200, and an empty body can be a 200 too. We broke on exactly this —
    hence the three-layer check: status code, body length, crash trail.
    """
    if r.code != 200:
        return False, f"HTTP {r.code}{(' — ' + r.error) if r.error else ''}"
    if len(r.body.strip()) < min_chars:
        return False, f"body {len(r.body.strip())} chars (counts as empty)"
    if m := PHP_CRASH.search(r.body):
        return False, f"crash trail on the page: {m.group(0)}"
    return True, f"200, {len(r.body)} chars"


# -- number helpers (for grading report output) -------------------------


# Only dot and comma as separators: letting whitespace into the class made
# "47553.25\n  2026" parse as one number and neighbouring figures ate each
# other (measured: two monthly totals of a correct report went missing).
_NUMBER = re.compile(r"-?\d+(?:[.,]\d+)*")


def numbers(text: str) -> list[float]:
    """Extract all numbers; tolerant of Turkish and English separators.

    We do not dictate whether the agent writes "1.234,56" or "1234.56" —
    what we measure is the VALUE being right, not the format.
    """
    out: list[float] = []
    for raw in _NUMBER.findall(text):
        body = raw.strip()
        for candidate in {body, body.replace(".", "").replace(",", "."),
                          body.replace(",", "")}:
            try:
                out.append(float(candidate))
            except ValueError:
                continue
    return out


def has_number(text: str, expected: float, tolerance: float = 0.011) -> bool:
    """Does the expected number appear in the text?

    The tolerance is one cent: drift from a different rounding order is
    accepted, a two-cent arithmetic error is not. Format free, value not.
    """
    return any(abs(n - expected) <= tolerance for n in numbers(text))


def in_order(text: str, ordered: Sequence[str]) -> bool:
    """Do the given fragments appear in THIS order? (for top-3 rankings)"""
    pos = -1
    lower = text.casefold()
    for piece in ordered:
        found = lower.find(piece.casefold(), pos + 1)
        if found <= pos:
            return False
        pos = found
    return True


# -- standalone run -----------------------------------------------------


def standalone(score: Callable[[Path], list[Axis]], task_id: str) -> int:
    """`py grader.py <workshop>` — try a grader without the runner."""
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except Exception:
        pass
    if len(sys.argv) < 2:
        print("usage: py grader.py <workshop-folder>")
        return 2
    root = Path(sys.argv[1]).resolve()
    if not root.is_dir():
        print(f"no such folder: {root}")
        return 2
    card = Scorecard(task_id, score(root))
    for a in card.axes:
        print(f"\n[{a.title}] {a.render()}")
        for e in a.evidence:
            print(f"   {e}")
        if a.reason:
            print(f"   reason: {a.reason}")
    s = card.score
    print(f"\nSCORE: {'unmeasurable' if s is None else f'{s:.1f}/100'}"
          f"  (raw {card.raw:.1f}/{card.measured_ceiling:.0f})")
    return 0
