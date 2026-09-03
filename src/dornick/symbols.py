"""Symbol search — structural code navigation without an LSP or a heavy language server.

Why it exists: the agent's only answer to "where is this function defined,
where is it called from?" was `grep`. `grep` sees text, not structure.
Searching for `kaydet` dumps the definition, the calls, the comments, the
strings and other names like `kaydetme_hatasi` into one pile — the model
reads that pile and fixes the wrong place, or never finds the right one.

The tool here separates the two: DEFINITION apart, USAGE apart, each in the
form `file:line: signature`.

Two layers, two different levels of honesty — and the difference is not hidden:

  * **Python: exact.** Parsed with `ast`. A name inside a comment or a string
    is never counted as a usage; a `def` really is a `def`. If a file cannot
    be parsed (syntax error) that is said, we do not fall back to guessing.
  * **PHP / JS / TS: careful regular expressions.** There is no language
    parser, so the result is "most probably" rather than "exact". Comment
    lines are dropped, but a name inside a string can still slip in. The
    footer of the result says so.
  * **Other languages: none.** We do not invent — it says "no structural
    search for this language, use `grep`". A half answer is worse than an
    honest redirection.
"""

from __future__ import annotations

import ast
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

# At most this many files are looked at in one go. Scanning a repository is
# not what is wanted; "this symbol in this project" is.
MAX_FILES = 400

# Bundles and generated files are not scanned: a single-line 3 MB
# `app.min.js` is both slow and meaningless.
MAX_SIZE = 400_000

# How many folder levels to descend. The third level is `src/dornick/tools/`;
# in real projects the source ends there.
MAX_DEPTH = 3

# At most this many definitions and usages shown in the result.
MAX_DEFINITIONS = 25
MAX_USAGES = 40

# Dependency and generated-output folders. The same list as
# `diagnostics.batch_paths` — same rationale: the ten thousand files inside
# `node_modules` are neither what the user wrote nor what the agent is
# looking for.
SKIP = {
    "node_modules", "vendor", ".git", "__pycache__", ".venv", "venv",
    "dist", "build", ".next", "writable", "site-packages", ".mypy_cache",
    ".pytest_cache", "coverage", "target", "bin", "obj",
}

LANGUAGES: dict[str, str] = {
    ".py": "python", ".pyw": "python",
    ".php": "php",
    ".js": "js", ".mjs": "js", ".cjs": "js", ".jsx": "js",
    ".ts": "ts", ".tsx": "ts",
}

# Languages with an exact parser. The rest goes by regex, and says so.
EXACT = {"python"}


def detect_language(path: Path | str) -> str | None:
    return LANGUAGES.get(Path(path).suffix.lower())


@dataclass(slots=True)
class Symbol:
    """A definition: function, class or method."""

    name: str
    kind: str           # fonksiyon | sinif | metot | sabit
    file: str
    line: int
    signature: str
    scope: str = ""     # the class name for a method

    def format(self, root: Path | None = None) -> str:
        """"tools/files.py:180: async def write_file(args, ctx) -> ToolResult"

        For a method the class is written too: among ten `handle`s of the
        same name only the owner says which one it is.
        """
        place = f"{_short(self.file, root)}:{self.line}"
        tail = f"   [{self.scope} sınıfının metodu]" if self.scope else ""
        return f"{place}: {self.signature}{tail}"


@dataclass(slots=True)
class Use:
    """A usage site and how it is used."""

    file: str
    line: int
    text: str
    kind: str = "anma"   # cagri | kurulum | ice_aktarma | anma

    def format(self, root: Path | None = None) -> str:
        return f"{_short(self.file, root)}:{self.line}: {self.text}"


@dataclass(slots=True)
class Result:
    query: str
    tanimlar: list[Symbol] = field(default_factory=list)
    use_log: list[Use] = field(default_factory=list)
    taranan: int = 0
    languages: set[str] = field(default_factory=set)
    # Files that could not be parsed: not skipped silently, counted.
    unparsable: list[str] = field(default_factory=list)
    # Did we fall back to substring matches because no exact name matched?
    loose: bool = False
    root: Path | None = None
    # Whether the scan hit the ceiling: an incomplete result must not stay quiet.
    hit_ceiling: bool = False

    @property
    def kesin(self) -> bool:
        """Only a result coming from a real parser is exact."""
        return bool(self.languages) and self.languages <= EXACT

    def metin(self, *, tur: str = "hepsi") -> str:
        if not self.languages:
            return (
                f"{self.root} altında yapısal arama yapabildiğim bir dosya yok. "
                "Python, PHP, JS ve TS için sembol araması var; başka diller "
                "için yapısal arama YOK — `grep` aracını kullan."
            )

        lines: list[str] = []
        if tur in ("tanim", "hepsi"):
            lines += self._definition_section()
        if tur in ("kullanim", "hepsi"):
            if lines:
                lines.append("")
            lines += self._usage_section()

        lines.append("")
        lines.append(self._footer())
        return "\n".join(lines)

    def _definition_section(self) -> list[str]:
        if not self.tanimlar:
            return [f"'{self.query}' adında bir tanım bulunamadı "
                    f"({self.taranan} dosya tarandı)."]
        head = f"{len(self.tanimlar)} tanım"
        if self.loose:
            head += f" (tam '{self.query}' yok; adı içerenler)"
        lines = [head + ":"]
        for s in self.tanimlar[:MAX_DEFINITIONS]:
            lines.append(f"  {s.format(self.root)}")
        if len(self.tanimlar) > MAX_DEFINITIONS:
            lines.append(f"  ... {len(self.tanimlar) - MAX_DEFINITIONS} tanım daha.")
        return lines

    def _usage_section(self) -> list[str]:
        if not self.use_log:
            if self.tanimlar:
                return [f"Kullanım bulunamadı. '{self.query}' tanımlı ama bu "
                        "kapsamda hiçbir yerden çağrılmıyor — ölü kod olabilir, "
                        "ya da çağrı bu klasörün dışında."]
            return ["Kullanım da bulunamadı."]
        counts: dict[str, int] = {}
        for u in self.use_log:
            counts[u.kind] = counts.get(u.kind, 0) + 1
        summary = ", ".join(f"{n} {kind.replace('_', ' ')}"
                            for kind, n in sorted(counts.items()))
        lines = [f"{len(self.use_log)} kullanım ({summary}):"]
        for u in self.use_log[:MAX_USAGES]:
            lines.append(f"  {u.format(self.root)}")
        if len(self.use_log) > MAX_USAGES:
            lines.append(f"  ... {len(self.use_log) - MAX_USAGES} kullanım daha.")
        return lines

    def _footer(self) -> str:
        """The line that says how reliable the result is."""
        parts = [f"{self.taranan} dosya tarandı "
                 f"({', '.join(sorted(self.languages))})."]
        if "python" in self.languages:
            parts.append("Python dosyaları `ast` ile ayrıştırıldı: yorum ve "
                         "dize içindeki isimler sayılmadı.")
        if self.languages - EXACT:
            parts.append("PHP/JS/TS için düzenli ifade kullanıldı — yorum "
                         "satırları elendi ama dize içindeki bir isim "
                         "kullanım gibi görünebilir; şüphelenirsen dosyayı aç.")
        if self.unparsable:
            parts.append(f"{len(self.unparsable)} dosya ayrıştırılamadı "
                         f"(ilki: {self.unparsable[0]}).")
        if self.hit_ceiling:
            parts.append(f"Tarama {MAX_FILES} dosya tavanına çarptı; sonuç "
                         "eksik olabilir — `path` ile daralt.")
        return " ".join(parts)


def _short(file: str, root: Path | None) -> str:
    if root is None:
        return Path(file).name
    try:
        return str(Path(file).relative_to(root))
    except ValueError:
        return file


# -- collecting files ---------------------------------------------------


def files(
    root: Path,
    *,
    language: str | None = None,
    limit: int = MAX_FILES,
    depth: int = MAX_DEPTH,
) -> tuple[list[Path], bool]:
    """The files to scan, and whether the ceiling was hit.

    Binary files are skipped: even with a `.py` extension, a file holding a
    NUL byte is not source, and trying to parse it is wasted work.
    """
    found: list[Path] = []
    root = Path(root)
    for base, folders, names in os.walk(root):
        level = len(Path(base).relative_to(root).parts)
        if level >= depth:
            folders[:] = []
        else:
            folders[:] = [f for f in folders
                          if f not in SKIP and not f.startswith(".")]
        for name in sorted(names):
            path = Path(base) / name
            found_language = detect_language(path)
            if found_language is None or (language and found_language != language):
                continue
            try:
                if path.stat().st_size > MAX_SIZE:
                    continue
            except OSError:  # pragma: no cover
                continue
            found.append(path)
            if len(found) >= limit:
                return found, True
    return found, False


def _read(path: Path) -> str | None:
    """Reads the source; None if binary or unreadable."""
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    if b"\x00" in raw[:4096]:
        return None
    return raw.decode("utf-8", errors="replace")


# -- Python: exact with ast --------------------------------------------


def _python_signature(node: ast.AST) -> str:
    if isinstance(node, ast.ClassDef):
        bases = ", ".join(_source(b) for b in node.bases)
        return f"class {node.name}({bases})" if bases else f"class {node.name}"
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
        try:
            arguments = ast.unparse(node.args)
        except Exception:  # pragma: no cover - old version / odd tree
            arguments = ", ".join(a.arg for a in node.args.args)
        tail = ""
        if node.returns is not None:
            tail = f" -> {_source(node.returns)}"
        return f"{prefix} {node.name}({arguments}){tail}"
    return getattr(node, "name", "?")  # pragma: no cover


def _source(node: ast.AST) -> str:
    try:
        return ast.unparse(node)
    except Exception:  # pragma: no cover
        return "?"


def python_definitions(path: Path, source: str) -> list[Symbol] | None:
    """All definitions in the file; None if it cannot be parsed.

    Returning None matters: silently counting a broken file as "no
    definitions" would send a model looking for exactly what is there to the
    wrong place.
    """
    try:
        tree = ast.parse(source, filename=str(path))
    except (SyntaxError, ValueError):
        return None

    found: list[Symbol] = []

    def walk(node: ast.AST, scope: str) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef):
                found.append(Symbol(child.name, "sinif", str(path),
                                    child.lineno, _python_signature(child), scope))
                walk(child, child.name)
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                kind = "metot" if scope else "fonksiyon"
                found.append(Symbol(child.name, kind, str(path), child.lineno,
                                    _python_signature(child), scope))
                # Nested functions are definitions too; the scope name is kept.
                walk(child, scope)
            else:
                walk(child, scope)

    walk(tree, "")
    return found


def python_usages(
    path: Path, source: str, name: str, definition_lines: set[int]
) -> list[Use] | None:
    """Usages of `name` in this file — via `ast`, hence exact.

    Names inside comments and strings are NOT IN THE TREE; that is why they
    never show up here. This is precision a regex can never reach.
    """
    try:
        tree = ast.parse(source, filename=str(path))
    except (SyntaxError, ValueError):
        return None

    lines = source.splitlines()
    found: dict[int, Use] = {}

    def add(line: int, kind: str) -> None:
        if line in definition_lines or line in found:
            return
        raw = lines[line - 1].strip() if 0 < line <= len(lines) else ""
        found[line] = Use(str(path), line, raw[:120], kind)

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            target = node.func
            ident = (getattr(target, "id", None) if isinstance(target, ast.Name)
                     else getattr(target, "attr", None))
            if ident == name:
                add(node.lineno, "cagri")
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                if alias.name.rsplit(".", 1)[-1] == name or alias.asname == name:
                    add(node.lineno, "ice_aktarma")
        elif isinstance(node, ast.Name) and node.id == name:
            add(node.lineno, "anma")
        elif isinstance(node, ast.Attribute) and node.attr == name:
            add(node.lineno, "anma")
    return list(found.values())


# -- PHP / JS / TS: careful regular expressions ------------------------
#
# Every pattern targets a specific signature; a generic "does this word
# occur" scan is deliberately absent. The captured name is always group 1.

_PHP_PATTERNS: tuple[tuple[str, str], ...] = (
    ("fonksiyon", r"^\s*(?:(?:public|private|protected|static|final|abstract)\s+)*"
                  r"function\s+&?(\w+)\s*\("),
    ("sinif", r"^\s*(?:abstract\s+|final\s+)?(?:class|interface|trait|enum)\s+(\w+)"),
    ("sabit", r"^\s*(?:public\s+|private\s+|protected\s+)?const\s+(\w+)\s*="),
)

_JS_PATTERNS: tuple[tuple[str, str], ...] = (
    ("fonksiyon", r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*\*?\s*(\w+)\s*\("),
    ("sinif", r"^\s*(?:export\s+)?(?:default\s+)?(?:abstract\s+)?class\s+(\w+)"),
    # const name = (…) => …   /   const name = function …
    ("fonksiyon", r"^\s*(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*"
                  r"(?:async\s*)?(?:function\b|\([^)]*\)\s*=>|\w+\s*=>)"),
    # a method in a class body:  name(arg) {   —  if/for/while/switch are filtered out
    ("metot", r"^\s{2,}(?:static\s+|async\s+|get\s+|set\s+)*(\w+)\s*\([^;]*\)\s*\{"),
    # TypeScript interface/type
    ("sinif", r"^\s*(?:export\s+)?(?:interface|type|enum)\s+(\w+)\b"),
)

# Control structures the method pattern would catch by mistake.
_KEYWORDS = {"if", "for", "while", "switch", "catch", "function", "return",
             "else", "do", "try", "with", "case", "typeof", "new", "await"}

# Comment lines: not counted as usage. Inside strings it can still slip in
# and the result footer says so explicitly.
_COMMENT = re.compile(r"^\s*(//|#|\*|/\*|<!--)")


def pattern_definitions(path: Path, source: str, language: str) -> list[Symbol]:
    patterns = _PHP_PATTERNS if language == "php" else _JS_PATTERNS
    compiled = [(kind, re.compile(pattern)) for kind, pattern in patterns]
    found: list[Symbol] = []
    seen: set[tuple[str, int]] = set()
    for i, line in enumerate(source.splitlines(), start=1):
        if _COMMENT.match(line):
            continue
        for kind, pattern in compiled:
            if not (m := pattern.match(line)):
                continue
            name = m.group(1)
            if name in _KEYWORDS:
                continue
            if (name, i) in seen:
                continue
            seen.add((name, i))
            found.append(Symbol(name, kind, str(path), i, line.strip()[:160]))
    return found


def _usage_pattern(name: str) -> re.Pattern[str]:
    """The pattern that catches lines where `name` is used.

    The look-behind for `$` and `.` is deliberate: in PHP `$kaydet` is
    something else, whereas in JS `nesne.kaydet(` IS what we are looking for
    — so the dot is not a blocker but gets its own branch.
    """
    k = re.escape(name)
    return re.compile(
        rf"(?:(?<![\w$]){k}\s*\()"          # call: kaydet(
        rf"|(?:->\s*{k}\s*\()"              # PHP method: $o->kaydet(
        rf"|(?:(?<![\w$]){k}::)"            # PHP static: Kayit::
        rf"|(?:\bnew\s+{k}(?![\w$]))"       # instantiation: new Kayit
        rf"|(?:\b(?:extends|implements|instanceof)\s+{k}(?![\w$]))"
        rf"|(?:\b(?:use|import|require|from)\b[^\n]*(?<![\w$]){k}(?![\w$]))"
    )


def _usage_kind(line: str, name: str) -> str:
    flat = line.strip()
    if re.search(rf"\bnew\s+{re.escape(name)}\b", flat):
        return "kurulum"
    if re.match(r"^\s*(use|import|require|from|include)\b", flat):
        return "ice_aktarma"
    if re.search(rf"(?<![\w$]){re.escape(name)}\s*\(", flat) or \
       re.search(rf"->\s*{re.escape(name)}\s*\(", flat):
        return "cagri"
    return "anma"


def pattern_usages(
    path: Path, source: str, name: str, definition_lines: set[int]
) -> list[Use]:
    pattern = _usage_pattern(name)
    found: list[Use] = []
    for i, line in enumerate(source.splitlines(), start=1):
        if i in definition_lines or _COMMENT.match(line):
            continue
        if not pattern.search(line):
            continue
        found.append(Use(str(path), i, line.strip()[:120],
                         _usage_kind(line, name)))
    return found


# -- search -------------------------------------------------------------


def ara(
    root: Path | str,
    query: str,
    *,
    tur: str = "hepsi",
    dil: str | None = None,
    limit: int = MAX_FILES,
    depth: int = MAX_DEPTH,
) -> Result:
    """Finds the definitions and usages of the symbol named `query`.

    An exact name match is looked for first; if there is no definition at
    all we fall back to names CONTAINING it, and the result says so — the
    model must not mistakenly think "I found exactly this".
    """
    root = Path(root).expanduser()
    result = Result(query=query, root=root)
    if not root.is_dir():
        return result

    paths, hit = files(root, language=dil, limit=limit, depth=depth)
    result.hit_ceiling = hit

    # Per file: source + language + definitions. Kept so we do not read twice.
    loaded: list[tuple[Path, str, str, list[Symbol]]] = []
    for path in paths:
        file_language = detect_language(path)
        if file_language is None:
            continue  # pragma: no cover
        source = _read(path)
        if source is None:
            continue
        result.taranan += 1
        result.languages.add(file_language)
        if file_language == "python":
            definitions = python_definitions(path, source)
            if definitions is None:
                result.unparsable.append(_short(str(path), root))
                definitions = []
        else:
            definitions = pattern_definitions(path, source, file_language)
        loaded.append((path, source, file_language, definitions))

    if not result.languages:
        return result

    exact = [s for _p, _s, _l, definitions in loaded for s in definitions if s.name == query]
    if exact:
        result.tanimlar = exact
    else:
        needle = query.lower()
        result.tanimlar = [s for _p, _s, _l, definitions in loaded for s in definitions
                           if needle in s.name.lower()]
        result.loose = bool(result.tanimlar)

    if tur == "tanim":
        return result

    # Usages always go by the EXACT name: while searching "kaydet" in loose
    # mode, showing the calls of "kaydetme_hatasi" is noise.
    target = query if exact or not result.tanimlar else result.tanimlar[0].name
    for path, source, file_language, definitions in loaded:
        lines = {s.line for s in definitions if s.name == target}
        if file_language == "python":
            found = python_usages(path, source, target, lines)
            if found is None:
                continue
        else:
            found = pattern_usages(path, source, target, lines)
        result.use_log.extend(found)

    # Sorted by file and line: `ast.walk` walks in tree order and line 203 of
    # the same file could come out before line 137. If the list is to be
    # read it should follow the order in the source.
    result.use_log.sort(key=lambda u: (u.file, u.line))
    result.tanimlar.sort(key=lambda s: (s.file, s.line))
    return result
