"""The `kos` tool: finds the project's own test harness and runs it.

This tool starts where `denetle` ends. `denetle` looks at the language's
syntax; `kos` ACTUALLY runs the code. The difference is an entire user
complaint:

    public function index(): string { return redirect(); }

`php -l` finds this clean, the browser throws a TypeError. An agent that
runs the tests sees it before the turn closes.

Permission-mode decision — `mutates=True`, the reasoning:

    Running tests starts as "does not change files" but that is not true.
    A test suite runs migrations, cleans `writable/`, writes caches, drops
    and recreates databases, goes out to the network, sends e-mail. And the
    code it runs is not OURS but the project's — i.e. third-party code
    running on the user's machine with the user's privileges. `shell` is
    `mutates=True` for exactly this reason; `kos` is also a shell that runs
    a discovered command. `mutates=False` would have meant an agent in plan
    mode could silently trigger the user's test suite (and its side
    effects). Friction is solved by a permission rule: the user says
    "kos:*" once.

`parallel_safe=False`: two test runs at the same time enter the same
database, the same `writable/` folder.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .. import testrun
from .base import ToolContext, ToolRegistry, ToolResult, object_schema


def _find_root(args: dict[str, Any], ctx: ToolContext) -> Path:
    """Which project are we going to run in?

    Order: (1) the path the model gave, (2) the project a file was most
    recently written to in this session, (3) the workshop, (4) the
    workspace. In every case the full path of the root is in the result
    text — even if guessed wrong, the model corrects it the moment it sees
    it.
    """
    if raw := (args.get("path") or "").strip():
        path = Path(raw).expanduser()
        if not path.is_absolute():
            base = ctx.sandbox.root if ctx.sandbox.enabled else ctx.workspace
            path = base / path
        return testrun.project_root(path)
    if (last := testrun.son_proje()) is not None:
        return last
    return ctx.sandbox.root if ctx.sandbox.enabled else ctx.workspace


def _harness_summary(root: Path) -> str:
    """The list of harnesses found in the folder — without running, for free."""
    found = testrun.tespit_hepsi(root)
    if not found:
        return testrun.tespit_metni(root)

    lines = [f"{root} altında bulunan düzenekler:"]
    for d in found:
        label = "test" if d.tur == "test" else "sağlık denetimi"
        lines.append(f"  `{d.etiket}` — {label}, kanıt: {d.kanit}")
        for note in d.notlar:
            lines.append(f"      {note}")
        if d.engel:
            lines.append(f"      koşulamaz: {d.engel}")
    lines.append("")
    lines.append("Bunlar tespit; hiçbiri koşturulmadı. Koşturmak için "
                 "`kos` aracını `sadece_tespit` olmadan çağır.")
    return "\n".join(lines)


def register(registry: ToolRegistry) -> None:
    @registry.tool(
        name="kos",
        description="""
Projenin KENDİ test düzeneğini bulur ve çalıştırır; sonucu geçen/kalan
sayısı, başarısız testlerin adı ve dosya:satır bilgisiyle özetler.

Ne zaman kullan: kod yazdıktan ya da düzelttikten sonra, "bitti" demeden
önce. `denetle` yalnızca sözdizimine bakar — tip hataları, yanlış dönüş
değerleri ve bozuk davranış ancak kod ÇALIŞINCA ortaya çıkar.

Komut uydurulmaz: pytest yapılandırması, package.json'daki `scripts.test`,
phpunit, go.mod gibi gerçek dosya kanıtları aranır. Hiçbiri yoksa araç
"test düzeneği bulunamadı" der ve sana uydurma bir komut vermez.

`path` vermezsen bu oturumda en son dosya yazdığın proje kullanılır.
`komut` verirsen tespit atlanır ve o komut koşar (dar bir dilim koşturmak
için: `py -m pytest -q tests/test_x.py`).
`sadece_tespit: true` hiçbir şey çalıştırmadan yalnızca ne bulunduğunu söyler.

Bir koşumun geçmesi "her şey çalışıyor" demek DEĞİLDİR; yalnızca koşulan
testlerin kapsadığı kadarını doğrular. Sonuç metni bunu her seferinde
yazıyor — kullanıcıya aktarırken de aynı sınırı koru.
        """,
        input_schema=object_schema(
            {
                "path": {
                    "type": "string",
                    "description": "Proje klasörü ya da içindeki bir dosya. "
                                   "Verilmezse en son dokunulan proje kullanılır.",
                },
                "komut": {
                    "type": "string",
                    "description": "Tespiti geçersiz kılan komut. Yalnızca "
                                   "gerçekten bildiğin bir komutu ver.",
                },
                "zaman_asimi": {
                    "type": "integer",
                    "description": "Saniye cinsinden süre tavanı "
                                   f"(varsayılan {int(testrun.DEFAULT_TIMEOUT)}, "
                                   f"en fazla {int(testrun.MAX_TIMEOUT)}).",
                },
                "sadece_tespit": {
                    "type": "boolean",
                    "description": "Hiçbir şey çalıştırma; yalnızca bu projede "
                                   "hangi düzeneğin bulunduğunu söyle.",
                },
            },
        ),
        mutates=True,
        parallel_safe=False,
    )
    async def kos(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        root = _find_root(args, ctx)
        if not root.is_dir():
            return ToolResult.error(
                f"Klasör yok: {root}. `path` ile var olan bir proje klasörü ver."
            )

        if args.get("sadece_tespit"):
            return ToolResult(content=_harness_summary(root),
                              detail={"kok": str(root), "tespit": True})

        timeout = float(args.get("zaman_asimi") or testrun.DEFAULT_TIMEOUT)

        if command := (args.get("komut") or "").strip():
            result = await testrun.kos_komut(
                command, root, zaman_asimi=timeout, cancel=ctx.cancel)
            return _reply(result)

        harness = testrun.tespit(root)
        if harness is None:
            # No evidence. Instead of inventing a command, say what to do.
            return ToolResult(content=testrun.tespit_metni(root),
                              detail={"kok": str(root), "duzenek": None})

        if not harness.kosulabilir:
            return ToolResult(
                content=(
                    f"{root} altında `{harness.etiket}` düzeneği var "
                    f"(kanıt: {harness.kanit}) ama koşturulamıyor: "
                    f"{harness.engel}\n\nBu bir kod hatası değil, makinenin "
                    "durumu. Kullanıcıya bildir; kurulum kararı onun."
                ),
                detail={"kok": str(root), "engel": harness.engel},
            )

        result = await testrun.kos(harness, zaman_asimi=timeout, cancel=ctx.cancel)
        return _reply(result)


def _reply(result: testrun.Result) -> ToolResult:
    """Turns the result into a tool reply.

    `is_error` only when things really went wrong: a failed test, a
    non-zero exit code, a timeout. "No harness" is not an error — it is
    information; counted as an error, the model would assume a flaw in what
    it wrote.
    """
    faulty = (
        result.status in ("zaman_asimi", "baslatilamadi", "kesildi")
        or result.cikis_kodu != 0
        or result.sayim.kalan > 0
    )
    return ToolResult(content=result.metin(), is_error=faulty, detail=result.detay())
