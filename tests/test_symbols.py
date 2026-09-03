"""Symbol search: a structural answer instead of `grep` noise.

The promise under test: "where is this function defined, where is it called
from?" must be answered with DEFINITION and USAGE separately. `grep kaydet`
dumped the definition, the calls, the comments, the strings and other names
like `kaydetme_hatasi` into one pile.

The second promise is honesty: Python exact via `ast`, PHP/JS/TS "most
probably" via regex, other languages not at all — and which one applies is
written at the bottom of the result.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from dornick import symbols
from dornick.config import Config
from dornick.events import EventLog
from dornick.session import Session
from dornick.tools import ToolContext, ToolRegistry
from dornick.tools import kod as code_tools

PY_SOURCE = '''\
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

PHP_SOURCE = """\
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

JS_SOURCE = """\
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
def project(tmp_path: Path) -> Path:
    (tmp_path / "depo.py").write_text(PY_SOURCE, encoding="utf-8")
    return tmp_path


# -- Python: exact with ast --------------------------------------------


def test_python_definitions_are_exact(project: Path) -> None:
    result = symbols.ara(project, "kaydet")
    names = [(s.kind, s.scope, s.line) for s in result.tanimlar]
    assert ("fonksiyon", "", 6) in names       # module-level def kaydet
    assert ("metot", "Depo", 12) in names      # Depo.kaydet
    assert result.kesin


def test_python_signature_carries_arguments_and_return(project: Path) -> None:
    result = symbols.ara(project, "kaydet", tur="tanim")
    signature = next(s.signature for s in result.tanimlar if s.scope == "")
    assert signature.startswith("def kaydet(")
    assert "yol: str" in signature
    assert "-> bool" in signature


def test_a_method_names_its_class(project: Path) -> None:
    result = symbols.ara(project, "kaydet", tur="tanim")
    text = result.metin(tur="tanim")
    assert "Depo sınıfının metodu" in text


def test_async_definitions_are_found(project: Path) -> None:
    result = symbols.ara(project, "toplu_kaydet", tur="tanim")
    assert len(result.tanimlar) == 1
    assert result.tanimlar[0].signature.startswith("async def toplu_kaydet(")


def test_classes_are_found(project: Path) -> None:
    result = symbols.ara(project, "Depo", tur="tanim")
    assert [s.kind for s in result.tanimlar] == ["sinif"]
    assert result.tanimlar[0].signature == "class Depo"


def test_python_ignores_comments_and_strings(project: Path) -> None:
    """The real value of `ast`: a name in a comment or a string is NOT IN THE TREE."""
    result = symbols.ara(project, "kaydet")
    lines = {u.line for u in result.use_log}
    # 1: "kaydet" in the module docstring, 18: comment, 19: string return
    assert 1 not in lines
    assert 18 not in lines
    assert 19 not in lines


def test_python_usages_are_classified(project: Path) -> None:
    result = symbols.ara(project, "kaydet")
    kinds = {u.kind for u in result.use_log}
    assert "cagri" in kinds
    # Definition lines are not counted as usages.
    definition_lines = {s.line for s in result.tanimlar}
    assert not (definition_lines & {u.line for u in result.use_log})


def test_imports_count_as_usage(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("def kaydet():\n    pass\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("from a import kaydet\n", encoding="utf-8")
    result = symbols.ara(tmp_path, "kaydet")
    assert any(u.kind == "ice_aktarma" for u in result.use_log)


def test_a_broken_python_file_is_reported_not_silently_skipped(tmp_path: Path) -> None:
    """Silently counting a broken file as 'undefined' sends the model to the wrong place."""
    (tmp_path / "bozuk.py").write_text("def kaydet(:\n", encoding="utf-8")
    result = symbols.ara(tmp_path, "kaydet")
    assert result.unparsable
    assert "ayrıştırılamadı" in result.metin()


# -- PHP ----------------------------------------------------------------


def test_php_definitions(tmp_path: Path) -> None:
    (tmp_path / "Home.php").write_text(PHP_SOURCE, encoding="utf-8")
    result = symbols.ara(tmp_path, "kaydet", tur="tanim")
    lines = sorted(s.line for s in result.tanimlar)
    assert 13 in lines             # private static function kaydet
    assert 19 in lines             # free function kaydet
    assert not result.kesin        # regex: we do not say "exact"


def test_php_class_definition(tmp_path: Path) -> None:
    (tmp_path / "Home.php").write_text(PHP_SOURCE, encoding="utf-8")
    result = symbols.ara(tmp_path, "Home", tur="tanim")
    assert [s.kind for s in result.tanimlar] == ["sinif"]


def test_php_usages_cover_arrow_and_static_calls(tmp_path: Path) -> None:
    (tmp_path / "Home.php").write_text(PHP_SOURCE, encoding="utf-8")
    result = symbols.ara(tmp_path, "kaydet")
    texts = " ".join(u.text for u in result.use_log)
    assert "$depo->kaydet" in texts        # object method
    assert "Kayit::kaydet" in texts        # static call


def test_php_comment_lines_are_dropped(tmp_path: Path) -> None:
    (tmp_path / "Home.php").write_text(PHP_SOURCE, encoding="utf-8")
    result = symbols.ara(tmp_path, "kaydet")
    assert all("yalnızca yorumda" not in u.text for u in result.use_log)


def test_php_new_is_an_instantiation(tmp_path: Path) -> None:
    (tmp_path / "Home.php").write_text(PHP_SOURCE, encoding="utf-8")
    result = symbols.ara(tmp_path, "Depo")
    assert any(u.kind == "kurulum" for u in result.use_log)


# -- JS -----------------------------------------------------------------


def test_js_function_class_and_arrow(tmp_path: Path) -> None:
    (tmp_path / "depo.js").write_text(JS_SOURCE, encoding="utf-8")
    everything = symbols.ara(tmp_path, "kaydet", tur="tanim")
    assert any(s.line == 2 for s in everything.tanimlar)     # export function

    arrow = symbols.ara(tmp_path, "yukle", tur="tanim")   # const yukle = async () =>
    assert arrow.tanimlar and arrow.tanimlar[0].kind == "fonksiyon"

    klass = symbols.ara(tmp_path, "Depo", tur="tanim")
    assert klass.tanimlar and klass.tanimlar[0].kind == "sinif"


def test_js_control_keywords_are_not_symbols(tmp_path: Path) -> None:
    """`if (x) {` is not a method definition."""
    (tmp_path / "a.js").write_text(
        "class A {\n  metot() {\n    if (x) {\n      return 1;\n    }\n  }\n}\n",
        encoding="utf-8")
    result = symbols.ara(tmp_path, "if", tur="tanim")
    assert result.tanimlar == []
    method = symbols.ara(tmp_path, "metot", tur="tanim")
    assert method.tanimlar and method.tanimlar[0].kind == "metot"


# -- scope and limits ---------------------------------------------------


def test_unsupported_language_says_so_and_points_at_grep(tmp_path: Path) -> None:
    """For a language we cannot measure: not a half answer but an honest redirection."""
    (tmp_path / "ana.go").write_text("func Kaydet() {}\n", encoding="utf-8")
    (tmp_path / "notlar.md").write_text("# kaydet\n", encoding="utf-8")
    result = symbols.ara(tmp_path, "Kaydet")
    text = result.metin()
    assert "yapısal arama YOK" in text
    assert "`grep`" in text


def test_dependency_folders_are_skipped(tmp_path: Path) -> None:
    (tmp_path / "kod.py").write_text("def kaydet(): pass\n", encoding="utf-8")
    inside = tmp_path / "node_modules" / "paket"
    inside.mkdir(parents=True)
    (inside / "kaydet.js").write_text("function kaydet() {}\n", encoding="utf-8")
    result = symbols.ara(tmp_path, "kaydet")
    assert result.taranan == 1
    assert all("node_modules" not in s.file for s in result.tanimlar)


def test_depth_is_limited(tmp_path: Path) -> None:
    deep = tmp_path / "a" / "b" / "c" / "d"
    deep.mkdir(parents=True)
    (deep / "gizli.py").write_text("def kaydet(): pass\n", encoding="utf-8")
    (tmp_path / "yuzey.py").write_text("def kaydet(): pass\n", encoding="utf-8")
    result = symbols.ara(tmp_path, "kaydet", depth=3)
    assert all("gizli" not in s.file for s in result.tanimlar)


def test_binary_files_are_skipped(tmp_path: Path) -> None:
    (tmp_path / "veri.py").write_bytes(b"def kaydet():\x00\x00 pass")
    result = symbols.ara(tmp_path, "kaydet")
    assert result.taranan == 0


def test_the_file_ceiling_is_announced(tmp_path: Path) -> None:
    """An incomplete result must not stay quiet."""
    for i in range(6):
        (tmp_path / f"m{i}.py").write_text("def kaydet(): pass\n", encoding="utf-8")
    result = symbols.ara(tmp_path, "kaydet", limit=3)
    assert result.hit_ceiling
    assert "tavanına çarptı" in result.metin()


def test_language_filter(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("def kaydet(): pass\n", encoding="utf-8")
    (tmp_path / "a.js").write_text("function kaydet() {}\n", encoding="utf-8")
    result = symbols.ara(tmp_path, "kaydet", dil="python")
    assert result.languages == {"python"}
    assert len(result.tanimlar) == 1


def test_a_loose_match_says_it_is_loose(tmp_path: Path) -> None:
    """Without an exact name, containing names are shown — but this is NOT HIDDEN."""
    (tmp_path / "a.py").write_text(
        "def kaydet_hepsini(): pass\n", encoding="utf-8")
    result = symbols.ara(tmp_path, "kaydet")
    assert result.loose
    assert "adı içerenler" in result.metin()


def test_a_defined_but_unused_symbol_is_called_out(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("def kaydet(): pass\n", encoding="utf-8")
    result = symbols.ara(tmp_path, "kaydet")
    assert "ölü kod olabilir" in result.metin()


def test_nothing_found_is_not_an_invention(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("def baska(): pass\n", encoding="utf-8")
    result = symbols.ara(tmp_path, "kaydet")
    assert result.tanimlar == [] and result.use_log == []
    assert "bulunamadı" in result.metin()


# -- tool surface -------------------------------------------------------


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
    code_tools.register(reg)
    return reg


async def call(registry: ToolRegistry, ctx: ToolContext, **args):
    return await registry.get("semboller").handler(args, ctx)


def test_the_tool_is_registered_and_read_only() -> None:
    from dornick.tools import build_registry

    registry = build_registry(subagents=False)
    spec = registry.get("semboller")
    assert spec is not None
    # Runs nothing, writes nothing: must not get stuck at the gate.
    assert spec.mutates is False


async def test_the_tool_finds_a_definition(
    registry: ToolRegistry, ctx: ToolContext, project: Path
) -> None:
    result = await call(registry, ctx, sorgu="kaydet", path=str(project))
    assert "def kaydet(" in result.content
    assert result.detail["tanim"] >= 2
    assert result.detail["kesin"] is True


async def test_the_tool_refuses_free_text(
    registry: ToolRegistry, ctx: ToolContext, project: Path
) -> None:
    """A query with spaces is not a symbol name; the right tool is `grep`."""
    result = await call(registry, ctx, sorgu="veri kaydedilemedi", path=str(project))
    assert result.is_error
    assert "`grep`" in result.content


async def test_the_tool_accepts_a_file_path(
    registry: ToolRegistry, ctx: ToolContext, project: Path
) -> None:
    """The model gives the only thing it has: the path of the file."""
    result = await call(registry, ctx, sorgu="Depo", path=str(project / "depo.py"))
    assert "class Depo" in result.content


async def test_the_tool_can_show_definitions_only(
    registry: ToolRegistry, ctx: ToolContext, project: Path
) -> None:
    result = await call(registry, ctx, sorgu="kaydet", path=str(project), tur="tanim")
    assert "tanım" in result.content
    assert "kullanım" not in result.content


async def test_the_tool_rejects_a_missing_folder(
    registry: ToolRegistry, ctx: ToolContext, tmp_path: Path
) -> None:
    result = await call(registry, ctx, sorgu="x", path=str(tmp_path / "yok" / "yok"))
    assert result.is_error


def test_the_description_admits_its_limits(registry: ToolRegistry) -> None:
    description = registry.get("semboller").description
    assert "kesin" in description
    assert "yapısal arama YOKTUR" in description
    assert "`grep`" in description
