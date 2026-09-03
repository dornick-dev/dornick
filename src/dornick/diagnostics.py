"""Code diagnostics: check a written file before anyone runs it.

Why it exists: the agent's most expensive class of error is "I wrote it, I
did not run it, I said done". The file lands on disk, the turn closes, the
error only surfaces when the user opens the page — and by then the model's
context has long scattered. Yet every language already has a checker
(Python's compiler, `php -l`, `node --check`); the only missing piece was to
run it the moment the write finished and put the result INTO THE TOOL'S
REPLY. The model sees the error on the next turn and fixes it.

Three rules are the spine of this module:

  1. **Never invent an error.** Findings come only from a real checker's
     output. No heuristic type analysis of our own — a false alarm is worse
     than not looking at all: it sends the model off to "fix" an error that
     does not exist.
  2. **Never say "all is well".** A clean result means "that checker did not
     see this". Every checker has a class of error it does not see (`php -l`
     does not see type errors) and we write that explicitly into the result.
  3. **No checker, stay quiet, do not suggest installing.** "could not be
     checked" is said in one line; editing the machine is not the model's job.

The checker is chosen by extension. For an extension we do not know
`denetle()` returns None — the caller adds nothing, there is no noise.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from . import environment

# Ceiling on the time given to a checker. If post-write feedback waits this
# long it has already waited too long; past it we honestly say "could not be
# checked".
TIMEOUT = 20.0

# The trimmed form of the raw output that goes to the model.
MAX_RAW = 1500

# At most this many findings are shown in the feedback. The rest is
# summarised as a count: once the first error is fixed most of them vanish.
MAX_FINDINGS = 5

# Huge files (packed bundles, generated data) are not checked: slow, and not
# something the agent wrote by hand anyway.
MAX_SIZE = 2_000_000


@dataclass(slots=True)
class Finding:
    """A single checker finding. `line` is 0 when unknown."""

    line: int
    message: str
    file: str = ""


@dataclass(slots=True)
class Diagnosis:
    """The check result for one file.

    status is one of three values:
      temiz  the checker ran, no findings
      hata   the checker ran, there are findings
      yok    the checker could not be run (not installed, timeout, crashed)
    """

    file: str
    language: str
    checker: str
    status: str
    findings: list[Finding] = field(default_factory=list)
    raw: str = ""
    # The error classes this checker CANNOT see. Written next to a clean
    # result so that the illusion "I checked it, it is solid" does not arise.
    scope: str = ""
    # While status == "yok": why it could not be run.
    reason: str = ""

    @property
    def faulty(self) -> bool:
        return self.status == "hata"

    def metin(self) -> str:
        """The human- (and model-) readable text appended to the tool result."""
        name = Path(self.file).name
        if self.status == "yok":
            return f"tanı: {name} kontrol edilemedi — {self.reason}."

        if self.status == "temiz":
            closing = f"tanı: temiz — {self.checker} bu dosyada hata görmedi."
            if self.scope:
                closing += f" ({self.scope})"
            return closing

        lines = [f"tanı: {self.checker} {len(self.findings)} hata buldu:"]
        for finding in self.findings[:MAX_FINDINGS]:
            place = f"satır {finding.line}" if finding.line else "yer belirsiz"
            lines.append(f"  {place}: {finding.message}")
        remaining = len(self.findings) - MAX_FINDINGS
        if remaining > 0:
            lines.append(f"  ... {remaining} bulgu daha.")
        lines.append(
            f"Bu hatalar senin az önce yazdığın dosyada ({name}). "
            "Düzeltmeden devam etme."
        )
        return "\n".join(lines)

    def detay(self) -> dict:
        """Machine-readable form so the UI can draw a badge."""
        return {
            "dosya": self.file,
            "dil": self.language,
            "denetleyici": self.checker,
            "durum": self.status,
            "bulgular": [
                {"satir": f.line, "mesaj": f.message} for f in self.findings
            ],
        }


# -- finding the checker ------------------------------------------------
#
# On Windows installed tools may not be on PATH: winget packages sit in their
# own folders, XAMPP/Laragon in their own tree. Looking at PATH and saying
# "missing" would ignore an installed checker.

_EXTRA_LOCATIONS: dict[str, tuple[str, ...]] = {
    "php": (
        r"~\AppData\Local\Microsoft\WinGet\Packages\PHP.PHP.*\php.exe",
        r"C:\xampp*\php\php.exe",
        r"C:\laragon\bin\php\*\php.exe",
        r"C:\php*\php.exe",
    ),
}


@lru_cache(maxsize=32)
def checker_path(name: str) -> str | None:
    """Full path of the executable called `name`; None if not found.

    The result is cached — there is no point scanning the disk on every
    write. Tests clear it with `checker_path.cache_clear()`.
    """
    import shutil

    if path := shutil.which(name):
        return path
    for pattern in _EXTRA_LOCATIONS.get(name, ()):
        expanded = Path(pattern).expanduser()
        root = Path(expanded.anchor)
        try:
            candidates = sorted(root.glob(str(expanded.relative_to(root))))
        except (OSError, ValueError):  # pragma: no cover - broken pattern/permission
            continue
        for candidate in candidates:
            if candidate.is_file():
                return str(candidate)
    return None


def _run(command: list[str], timeout: float) -> tuple[int, str] | None:
    """Runs the checker: (exit code, output). None if it does not finish.

    With flags that keep a console window from opening: while dornick runs
    under pythonw every check used to flash a cmd window on the screen.
    """
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            timeout=timeout,
            **environment.quiet_flags(),
        )
    except subprocess.TimeoutExpired:
        return None
    streams = (result.stdout or b"") + b"\n" + (result.stderr or b"")
    # Line endings are unified: Windows' \r used to sit in front of the
    # end-of-line pattern ($) and make the line number unreadable.
    text = streams.decode("utf-8", errors="replace").replace("\r\n", "\n")
    return result.returncode, text.replace("\r", "\n").strip()


def _trim(text: str, limit: int = MAX_RAW) -> str:
    return text if len(text) <= limit else text[:limit] + "\n... [kırpıldı]"


# -- output parsers -----------------------------------------------------
#
# Separate functions: so that parsing can be tested even when the checker is
# not installed on the machine. This is the only way we can prove that we
# read the output of a tool that is not installed correctly.

# ruff/pyflakes: "path:line:column: message" (the column is absent in some versions)
_PY_LINE = re.compile(r"^(?P<file>.+?):(?P<line>\d+)(?::\d+)?: (?P<message>.+)$")

# php -l: "PHP Parse error:  syntax error, ... in FILE on line 4"
# The "PHP " prefix depends on php.ini: the same error can arrive both with
# the prefix (stderr) and without (stdout) — we recognise both and then drop
# the duplicates.
_PHP_LINE = re.compile(
    r"^(?:PHP )?(?:Parse|Fatal) error:\s*(?P<message>.*?) in (?P<file>.*) "
    r"on line (?P<line>\d+)"
)

# node --check: first line "FILE:LINE", then the code, then "SyntaxError: message"
_NODE_LOCATION = re.compile(r"^(?P<file>.+):(?P<line>\d+)$", re.MULTILINE)
_NODE_MESSAGE = re.compile(r"^(?P<message>\w*Error: .+)$", re.MULTILINE)

# tsc: "file(12,5): error TS2322: message"
_TS_LINE = re.compile(
    r"^(?P<file>.+?)\((?P<line>\d+),\d+\): error (?P<message>.+)$", re.MULTILINE
)


def _py_findings(output: str) -> list[Finding]:
    findings = []
    for line in output.splitlines():
        if m := _PY_LINE.match(line.strip()):
            findings.append(
                Finding(int(m["line"]), m["message"].strip(), m["file"].strip())
            )
    return findings


def _php_findings(output: str) -> list[Finding]:
    findings: list[Finding] = []
    seen: set[tuple[str, int, str]] = set()
    for line in output.splitlines():
        if not (m := _PHP_LINE.match(line.strip())):
            continue
        finding = Finding(int(m["line"]), m["message"].strip(), m["file"].strip())
        # The same error arrives twice, with and without the prefix; let it
        # reach the model once.
        signature = (finding.file, finding.line, finding.message)
        if signature in seen:
            continue
        seen.add(signature)
        findings.append(finding)
    return findings


def _node_findings(output: str) -> list[Finding]:
    location = _NODE_LOCATION.search(output)
    message = _NODE_MESSAGE.search(output)
    if not message:
        return []
    return [
        Finding(
            int(location["line"]) if location else 0,
            message["message"].strip(),
            location["file"].strip() if location else "",
        )
    ]


def _ts_findings(output: str) -> list[Finding]:
    return [
        Finding(int(m["line"]), m["message"].strip(), m["file"].strip())
        for m in _TS_LINE.finditer(output)
    ]


# -- languages ----------------------------------------------------------

UZANTILAR: dict[str, str] = {
    ".py": "python",
    ".pyw": "python",
    ".php": "php",
    ".js": "js",
    ".mjs": "js",
    ".cjs": "js",
    ".ts": "ts",
    ".tsx": "ts",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
}
# .jsx is deliberately absent: `node --check` does not understand JSX syntax
# and would invent errors for a perfectly sound file.


def detect_language(path: Path | str) -> str | None:
    """Language from the extension; None if we do not know it (= skip silently)."""
    return UZANTILAR.get(Path(path).suffix.lower())


def supported(path: Path | str) -> bool:
    return detect_language(path) is not None


def _python(path: Path, timeout: float) -> Diagnosis:
    """The compiler first (always there), then ruff/pyflakes if present.

    The compiler sees syntax; ruff/pyflakes go one step further and also
    catch the "blows up when run" class such as undefined names and unused
    imports. Even with neither we still say something — Python's compiler
    ships with the interpreter itself.
    """
    base_scope = "çalışma zamanı hataları bu denetimin dışında"
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return Diagnosis(str(path), "python", "python derleyicisi", "yok",
                         reason=f"dosya okunamadı ({exc.strerror or exc})")

    try:
        compile(source, str(path), "exec")
    except SyntaxError as exc:
        return Diagnosis(
            str(path), "python", "python derleyicisi", "hata",
            findings=[Finding(exc.lineno or 0, exc.msg or "sözdizimi hatası", str(path))],
            raw=f"{type(exc).__name__}: {exc}",
        )
    except ValueError as exc:  # a NUL byte in the source, for instance
        return Diagnosis(
            str(path), "python", "python derleyicisi", "hata",
            findings=[Finding(0, str(exc), str(path))], raw=str(exc),
        )

    # Syntax is sound. Is there a tool that can look deeper?
    for name, arguments in (
        ("ruff", ["check", "--quiet", "--output-format=concise"]),
        ("pyflakes", []),
    ):
        if (exe := checker_path(name)) is None:
            continue
        result = _run([exe, *arguments, str(path)], timeout)
        if result is None:
            break  # timeout: trust the compiler result, stop quietly
        _code, output = result
        findings = _py_findings(output)
        label = f"python derleyicisi + {name}"
        if findings:
            return Diagnosis(str(path), "python", label, "hata",
                             findings=findings, raw=_trim(output))
        return Diagnosis(str(path), "python", label, "temiz", scope=base_scope)

    return Diagnosis(
        str(path), "python", "python derleyicisi", "temiz",
        scope="yalnızca sözdizimi denetlendi; tanımsız isim ve tip hataları "
              "ancak çalıştırınca görünür",
    )


def _php(path: Path, timeout: float) -> Diagnosis:
    """`php -l`: syntax and compile-time fatal errors.

    Being honest about its scope is essential: `php -l` does not see TYPE
    errors. A `return` that disagrees with the declared return type (saying
    `: string` and returning an object) passes it and only becomes a
    TypeError when a request arrives. We write this next to the clean result
    so the model does not relax with "the linter passed".
    """
    exe = checker_path("php")
    if exe is None:
        return Diagnosis(str(path), "php", "php -l", "yok",
                         reason="php bu makinede bulunamadı")
    # -n: do not read php.ini — missing-extension warnings must not mix into
    # the findings.
    result = _run([exe, "-n", "-l", str(path)], timeout)
    if result is None:
        return Diagnosis(str(path), "php", "php -l", "yok",
                         reason=f"php -l {timeout:.0f} sn'de bitmedi")
    code, output = result
    findings = _php_findings(output)
    if findings:
        return Diagnosis(str(path), "php", "php -l", "hata",
                         findings=findings, raw=_trim(output))
    if code != 0:
        # The exit code says error but we could not resolve the line: hand
        # over the raw output as it is, do not invent.
        return Diagnosis(str(path), "php", "php -l", "hata",
                         findings=[Finding(0, output.splitlines()[0] if output else
                                           f"çıkış kodu {code}", str(path))],
                         raw=_trim(output))
    return Diagnosis(str(path), "php", "php -l", "temiz",
                     scope="php -l yalnızca sözdizimini görür; tip hataları "
                           "(bildirilen dönüş tipiyle uyuşmayan return) ve "
                           "bulunamayan sınıflar ancak çalıştırınca ortaya çıkar")


def _js(path: Path, timeout: float) -> Diagnosis:
    exe = checker_path("node")
    if exe is None:
        return Diagnosis(str(path), "js", "node --check", "yok",
                         reason="node bu makinede bulunamadı")
    result = _run([exe, "--check", str(path)], timeout)
    if result is None:
        return Diagnosis(str(path), "js", "node --check", "yok",
                         reason=f"node --check {timeout:.0f} sn'de bitmedi")
    code, output = result
    if code == 0:
        return Diagnosis(str(path), "js", "node --check", "temiz",
                         scope="yalnızca sözdizimi; tanımsız değişken ve tip "
                               "hataları ancak çalıştırınca görünür")
    findings = _node_findings(output) or [
        Finding(0, output.splitlines()[0] if output else f"çıkış kodu {code}", str(path))
    ]
    return Diagnosis(str(path), "js", "node --check", "hata",
                     findings=findings, raw=_trim(output))


def _tsconfig(path: Path) -> Path | None:
    """Is there a tsconfig.json above the file? (the project boundary)"""
    for folder in [path.parent, *path.parent.parents]:
        candidate = folder / "tsconfig.json"
        if candidate.is_file():
            return candidate
        if (folder / ".git").exists():
            break
    return None


def _ts(path: Path, timeout: float) -> Diagnosis:
    """TypeScript is only meaningful in project context: no tsconfig, no attempt.

    Compiling a single file torn from its project would produce "module not
    found" errors that do not really exist — a violation of the first rule.
    """
    if _tsconfig(path) is None:
        return Diagnosis(str(path), "ts", "tsc", "yok",
                         reason="tsconfig.json bulunamadı, proje bağlamı olmadan "
                                "TypeScript denetlenemez")
    exe = checker_path("npx") or checker_path("npx.cmd")
    if exe is None:
        return Diagnosis(str(path), "ts", "tsc", "yok", reason="npx bulunamadı")
    result = _run([exe, "--no-install", "tsc", "--noEmit", str(path)], timeout)
    if result is None:
        return Diagnosis(str(path), "ts", "tsc", "yok",
                         reason=f"tsc {timeout:.0f} sn'de bitmedi")
    code, output = result
    findings = _ts_findings(output)
    if findings:
        return Diagnosis(str(path), "ts", "tsc", "hata",
                         findings=findings, raw=_trim(output))
    if code != 0:
        # If tsc is not installed, npx --no-install blows up here: that is
        # not a code error but the absence of the checker.
        return Diagnosis(str(path), "ts", "tsc", "yok",
                         reason="tsc çalıştırılamadı (projede kurulu olmayabilir)")
    return Diagnosis(str(path), "ts", "tsc", "temiz",
                     scope="tsc çalışma zamanı davranışını değil tipleri denetler")


def _json(path: Path, timeout: float) -> Diagnosis:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return Diagnosis(str(path), "json", "json ayrıştırıcı", "yok",
                         reason=f"dosya okunamadı ({exc})")
    try:
        json.loads(text)
    except json.JSONDecodeError as exc:
        return Diagnosis(str(path), "json", "json ayrıştırıcı", "hata",
                         findings=[Finding(exc.lineno, exc.msg, str(path))], raw=str(exc))
    return Diagnosis(str(path), "json", "json ayrıştırıcı", "temiz",
                     scope="yalnızca biçim; alanların doğruluğu denetlenmedi")


def _yaml(path: Path, timeout: float) -> Diagnosis:
    try:
        import yaml  # type: ignore
    except ImportError:
        return Diagnosis(str(path), "yaml", "yaml ayrıştırıcı", "yok",
                         reason="PyYAML kurulu değil")
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return Diagnosis(str(path), "yaml", "yaml ayrıştırıcı", "yok",
                         reason=f"dosya okunamadı ({exc})")
    try:
        list(yaml.safe_load_all(text))
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        message = getattr(exc, "problem", None) or str(exc).splitlines()[0]
        line = (mark.line + 1) if mark is not None else 0
        return Diagnosis(str(path), "yaml", "yaml ayrıştırıcı", "hata",
                         findings=[Finding(line, message, str(path))], raw=_trim(str(exc)))
    return Diagnosis(str(path), "yaml", "yaml ayrıştırıcı", "temiz",
                     scope="yalnızca biçim; alanların doğruluğu denetlenmedi")


_CHECKERS = {
    "python": _python,
    "php": _php,
    "js": _js,
    "ts": _ts,
    "json": _json,
    "yaml": _yaml,
}


def denetle(path: Path | str, *, timeout: float = TIMEOUT) -> Diagnosis | None:
    """Checks a single file. None if the language is unknown — the caller says nothing.

    Blocking (runs a subprocess); async callers should wrap it in
    `asyncio.to_thread`.
    """
    path = Path(path)
    language = detect_language(path)
    if language is None:
        return None
    try:
        if not path.is_file():
            return None
        if path.stat().st_size > MAX_SIZE:
            return Diagnosis(str(path), language, "-", "yok",
                             reason="dosya denetim için fazla büyük")
    except OSError:
        return None

    try:
        return _CHECKERS[language](path, timeout)
    except Exception as exc:  # the checker crashed: do not produce a fake finding
        return Diagnosis(str(path), language, "-", "yok",
                         reason=f"denetleyici çalıştırılamadı ({type(exc).__name__})",
                         raw=_trim(str(exc)))


def denetle_coklu(
    paths: list[Path], *, timeout: float = TIMEOUT
) -> list[Diagnosis]:
    """Several files; unsupported ones drop out of the list."""
    results = []
    for path in paths:
        if (diagnosis := denetle(path, timeout=timeout)) is not None:
            results.append(diagnosis)
    return results


def ozet(diagnoses: list[Diagnosis], *, kok: Path | None = None) -> str:
    """Summary of a multi-file check — the reply of the `denetle` tool.

    The faulty ones first (they are the real matter), then a one-line count.
    We do not say "all clean": it says which checker looked.
    """
    if not diagnoses:
        return ("Denetlenecek dosya bulunamadı. Tanınan uzantılar: "
                + ", ".join(sorted(UZANTILAR)) + ".")

    def name(d: Diagnosis) -> str:
        if kok is None:
            return Path(d.file).name
        try:
            return str(Path(d.file).relative_to(kok))
        except ValueError:
            return d.file

    faulty = [d for d in diagnoses if d.status == "hata"]
    clean = [d for d in diagnoses if d.status == "temiz"]
    unchecked = [d for d in diagnoses if d.status == "yok"]

    lines: list[str] = []
    for diagnosis in faulty:
        lines.append(f"{name(diagnosis)} — {diagnosis.checker}, {len(diagnosis.findings)} hata:")
        for finding in diagnosis.findings[:MAX_FINDINGS]:
            place = f"satır {finding.line}" if finding.line else "yer belirsiz"
            lines.append(f"  {place}: {finding.message}")
        remaining = len(diagnosis.findings) - MAX_FINDINGS
        if remaining > 0:
            lines.append(f"  ... {remaining} bulgu daha.")

    if clean:
        tools = sorted({d.checker for d in clean})
        lines.append(
            f"{len(clean)} dosyada bulgu yok ({', '.join(tools)} baktı). "
            "Bu, kodun çalıştığı anlamına gelmez — denetleyiciler çoğunlukla "
            "sözdizimine bakar."
        )
    for diagnosis in unchecked:
        lines.append(f"{name(diagnosis)} kontrol edilemedi — {diagnosis.reason}.")

    if faulty:
        lines.append("Hataları düzeltmeden devam etme.")
    return "\n".join(lines)


def batch_paths(kok: Path, *, desen: str | None = None, tavan: int = 60) -> list[Path]:
    """The checkable files under a folder.

    Dependency and generated-output folders are skipped: checking the ten
    thousand files inside `node_modules` is neither what the user asked for
    nor what the agent wrote.
    """
    skip = {"node_modules", "vendor", ".git", "__pycache__", ".venv", "venv",
            "dist", "build", ".next", "writable"}
    found: list[Path] = []
    for base, folders, files in os.walk(kok):
        folders[:] = [f for f in folders if f not in skip and not f.startswith(".")]
        for file_name in sorted(files):
            path = Path(base) / file_name
            if not supported(path):
                continue
            if desen and not path.match(desen):
                continue
            found.append(path)
            if len(found) >= tavan:
                return found
    return found
