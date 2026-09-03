"""File tools.

The reason to promote these over `cat`/`echo` from the shell: they give
the harness typed arguments. So a staleness check can be made before a
write, permission rules can be written per path, the UI can show a diff.
None of that is possible in an opaque shell string.
"""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path
from typing import Any

from .. import hooks, testrun, diagnostics
from ..sandbox import OutsideSandbox
from . import checkpoint
from .base import ToolContext, ToolRegistry, ToolResult, object_schema

MAX_READ_CHARS = 60_000
MAX_LIST_ENTRIES = 400

# The most files looked at in one turn of a manual audit. Auditing a folder
# is what is wanted; not scanning the whole repository.
MAX_AUDIT_FILES = 60


def _resolve(raw: str, ctx: ToolContext) -> Path:
    """Resolves relative paths against the workshop, absolute paths as they are.

    A relative path landing in the workshop is deliberate: most of the time
    the agent is doing its own work and when it writes "site/index.html" it
    expects that to be in its own folder. A file outside is reached with an
    absolute path — reading is free everywhere anyway.
    """
    path = Path(raw).expanduser()
    if path.is_absolute():
        return path
    if not ctx.sandbox.enabled:
        return ctx.workspace / path

    root = ctx.sandbox.root
    # The model adds the workshop's name to the path itself
    # ("atolye/site/index.html"): the full path of the folder is in the
    # system prompt and it infers from there. Joining as-is produced
    # `atolye/atolye/...` — the file lands in a subfolder rather than the
    # right place and the user cannot find what they are looking for.
    parts = path.parts
    if parts and parts[0] == root.name:
        path = Path(*parts[1:]) if len(parts) > 1 else Path()
    return root / path


def _guard(path: Path, ctx: ToolContext) -> ToolResult | None:
    """The write boundary. Returns the error if violated, else None.

    The error text also says what to do: for the model to turn to
    `copy_in` on the next turn, "no permission" is not enough.
    """
    # The hook file before everything: even inside the workshop it cannot
    # be written.
    #
    # Hooks are the user's own commands running OUTSIDE the permission
    # engine. That is only safe if the model cannot touch that file:
    # otherwise it would bypass the permission gate entirely by deleting
    # the hook that blocks it or writing its own command there. The rule is
    # in one place and every write tool passes through here.
    if hooks.is_protected(path):
        return ToolResult.error(
            f"{path} kanca dosyasıdır ve yazmaya kapalıdır. Kancalar "
            "kullanıcının senin üzerinde kurduğu kurallardır; onay "
            "penceresi olmadan çalışırlar ve tam bu yüzden senin "
            "değiştirebileceğin bir yerde durmazlar. Bir kancanın "
            "değişmesi gerekiyorsa kullanıcıya söyle, kendin düzenleme."
        )
    try:
        ctx.sandbox.check(path)
    except OutsideSandbox as exc:
        return ToolResult.error(str(exc))
    return None


def _snapshot(path: Path, ctx: ToolContext, tool: str) -> None:
    """Pre-change snapshot for a file inside the workshop.

    Failing to take the snapshot does NOT stop the write: stopping the car
    because the seat belt would not buckle locks the model up. `undo`
    honestly reports a record without a snapshot as "cannot be reverted".
    """
    try:
        if ctx.sandbox.contains(path):
            checkpoint.defter(ctx).save(path, tool)
    except OSError:
        pass


# -- non-text files ----------------------------------------------------
#
# Proven wound: opening a PNG with `read_file` sent the model a screenful
# of "��". The model read that as "the file is corrupt" and told the user
# so — yet the file was perfectly fine, we were looking with the wrong
# eye.

# The image types the API accepts. Sending anything else returns 400; so
# an extension not in the list never enters the image path.
IMAGE_TYPES = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".gif": "image/gif", ".webp": "image/webp",
}

# Image cap. The API rejects ~5 MB in the base64 body; since base64 grows
# the raw size by 4/3, the raw cap is a bit under three quarters of that.
MAX_IMAGE_BYTES = 3_500_000

# Default and maximum pages extracted from a PDF in one turn. Dumping a
# whole contract into the context does not make the wanted paragraph
# easier to find.
PDF_PAGE = 10
PDF_MAX_PAGES = 40
MAX_PDF_CHARS = 40_000


def _is_image(path: Path) -> bool:
    return path.suffix.lower() in IMAGE_TYPES


def _size(count: int) -> str:
    if count >= 1_048_576:
        return f"{count / 1_048_576:.1f} MB"
    # Writing "0 KB" for small files is wrong information: the file is not empty.
    return f"{count / 1024:.0f} KB" if count >= 1024 else f"{count} bayt"


def _read_image(path: Path) -> ToolResult:
    """Hands the image to the model as an IMAGE.

    The transport was ready and unused: a tool result cannot carry an
    image (the API wants `tool_result` content to be a string), but the
    executor sees `detail["image"]` and attaches it to the block as
    `_image`, and the loop puts it into the next user turn as an image
    block — the path the `look`/`screen` tools have used for years. Wiring
    it here is a one-line job; only the connection was missing.
    """
    import base64

    try:
        size = path.stat().st_size
    except OSError as exc:
        return ToolResult.error(f"Okunamadı: {exc}")

    if size > MAX_IMAGE_BYTES:
        # No invention: if we cannot send the image we say so.
        return ToolResult(
            f"{path.name} bir görsel ({_size(size)}) ama modele "
            f"gönderilemeyecek kadar büyük (tavan {_size(MAX_IMAGE_BYTES)}). "
            "İçeriğini göremiyorum; küçültülmüş bir kopyası verilirse "
            "bakabilirim.",
            is_error=True,
        )
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return ToolResult.error(f"Okunamadı: {exc}")

    kind = IMAGE_TYPES[path.suffix.lower()]
    data = base64.b64encode(raw).decode("ascii")
    return ToolResult(
        content=f"{path.name} ({kind}, {_size(size)}) açıldı. Aşağıda görüyorsun.",
        detail={"path": str(path), "image": f"data:{kind};base64,{data}"},
    )


def _read_pdf(path: Path, offset: Any, limit: Any) -> ToolResult:
    """Extracts the TEXT of the PDF's first pages.

    Two honesty rules:
      * For a text-less (scanned) PDF we do not say "empty" — we say the
        pages are images and carry no text layer. Saying "empty" would
        make the model think the file has no content.
      * How many pages were read and how many there are is always
        written; the model must not read page 3 and think it summarised a
        200-page report.
    """
    try:
        from pypdf import PdfReader
    except ImportError:
        return ToolResult(
            f"{path.name} bir PDF ama okuyamıyorum: `pypdf` bu makinede "
            "kurulu değil. İçeriği hakkında tahminde bulunmayacağım — "
            "kullanıcıya bildir.",
            is_error=True,
        )

    try:
        reader = PdfReader(str(path))
        total = len(reader.pages)
    except Exception as exc:
        return ToolResult(
            f"{path.name} açılamadı ({type(exc).__name__}: {exc}). Dosya "
            "bozuk ya da parola korumalı olabilir.",
            is_error=True,
        )

    if total == 0:
        return ToolResult(f"{path.name} sayfa içermiyor.", is_error=True)

    first = max(1, int(offset or 1))
    count = max(1, min(int(limit or PDF_PAGE), PDF_MAX_PAGES))
    last = min(total, first + count - 1)
    if first > total:
        return ToolResult.error(
            f"{path.name} {total} sayfa; {first}. sayfa yok. `offset` değerini "
            f"1 ile {total} arasında ver."
        )

    parts: list[str] = []
    filled = 0
    for no in range(first, last + 1):
        try:
            text = (reader.pages[no - 1].extract_text() or "").strip()
        except Exception:  # one broken page must not bring the whole file down
            text = ""
        if text:
            filled += 1
        parts.append(f"--- sayfa {no} ---\n{text or '(bu sayfada metin yok)'}")

    body = "\n\n".join(parts)
    if len(body) > MAX_PDF_CHARS:
        body = body[:MAX_PDF_CHARS] + "\n… (kırpıldı)"

    heading = f"{path.name} — {total} sayfa, {first}-{last} arası okundu."
    if filled == 0:
        return ToolResult(
            f"{heading}\n\nBu sayfalar METİN KATMANI TAŞIMIYOR — büyük "
            "olasılıkla taranmış görüntüler. İçeriğini okuyamadım; ne "
            "yazdığını uydurma. Sayfayı görsel olarak incelemek gerekirse "
            "kullanıcıdan bir ekran görüntüsü iste.",
            detail={"path": str(path), "sayfa": total, "metinsiz": True},
        )

    tail = ""
    if last < total:
        tail = (f"\n\n[{total} sayfanın {first}-{last} arası. Devamı için "
                f"offset={last + 1}.]")
    return ToolResult(
        content=f"{heading}\n\n{body}{tail}",
        detail={"path": str(path), "sayfa": total, "okunan": [first, last]},
    )


async def _testrun_suffix(path: Path, writes: int) -> str:
    """One-line test-run reminder after a write (empty string if none).

    Diagnosis took a step but its ceiling is syntax: `php -l` does not see
    a `return` that disagrees with the declared return type; a type error
    only blows up when the code runs. The only thing that sees it is
    RUNNING the tests — and in most projects that harness already exists,
    the agent did not know about it.

    We do not run the tests here on our own: a run takes seconds,
    sometimes minutes, and the agent writes the same file back to back —
    every run in between would be wasted. Instead we report that the
    harness EXISTS. Information is free, the run is expensive, the
    decision is the model's.
    """
    try:
        return await asyncio.to_thread(testrun.reminder, path, writes=writes)
    except Exception:  # pragma: no cover - the reminder never gets in the way
        return ""


async def _diagnosis_suffix(path: Path) -> tuple[str, dict[str, Any]]:
    """The written file's diagnosis: (text to append to the tool result, detail).

    This is the most important place in the module. The agent's most
    expensive error class is "I wrote it, didn't run it, said done" — the
    error sits in the file, the turn closes, the user opens the page and
    it blows up. Running the language's own checker the moment the write
    ends and putting the result INTO THE TOOL'S REPLY breaks that chain:
    the model sees the error on the next turn and fixes it before anyone
    notices.

    Diagnosis never overrides the write: the file is on disk, the result
    is a success. Diagnosis only adds a NOTE. If the checker crashed
    nothing is added — the diagnosis's own failure must not break a
    working tool.
    """
    try:
        diagnosis = await asyncio.to_thread(diagnostics.check, path)
    except Exception:  # pragma: no cover - the diagnosis layer never gets in the way
        return "", {}
    if diagnosis is None:
        return "", {}
    return "\n\n" + diagnosis.text(), {"tani": diagnosis.detail()}


def _esnek_esle(text: str, old: str, new: str):
    """Tolerant search when there is no exact match. (start, end, new, note)
    or ("coklu", N) or None.

    Measured wound (28.08 three-way benchmark, z1): 7 of 18 failed tool
    calls were "the searched text is not in the file" and all of them were
    whitespace/indent/line-ending differences — the content was right. The
    model re-read the file and burned the turn. Order: line-ending
    normalisation → trailing whitespace → uniform indent shift. At every
    step the match must be UNIQUE; more than one is an ambiguity error
    (always better than silently changing the wrong place).
    """
    o2 = old.replace("\r\n", "\n").replace("\r", "\n")
    n2 = new.replace("\r\n", "\n").replace("\r", "\n")
    if o2 != old:
        count = text.count(o2)
        if count == 1:
            i = text.index(o2)
            return i, i + len(o2), n2, "satır sonları normalize edildi"
        if count > 1:
            return ("coklu", count)

    old_lines = o2.split("\n")
    fl = text.split("\n")
    n = len(old_lines)
    if not n or len(fl) < n:
        return None
    offs = [0]
    for ln in fl[:-1]:
        offs.append(offs[-1] + len(ln) + 1)

    def span(i):
        return offs[i], offs[i + n - 1] + len(fl[i + n - 1])

    # Trailing whitespace: the line content is the same, the whitespace at
    # the end of the line differs.
    target = [l.rstrip() for l in old_lines]
    candidates = [i for i in range(len(fl) - n + 1)
                  if [l.rstrip() for l in fl[i:i + n]] == target]
    if len(candidates) == 1:
        b, e = span(candidates[0])
        return b, e, n2, "kuyruk boşlukları göz ardı edildi"
    if len(candidates) > 1:
        return ("coklu", len(candidates))

    # Uniform indent shift: the content is the same, the indent difference
    # is CONSTANT across all non-empty lines. `new` is re-indented by the
    # same shift — if the model's old is mis-indented, its new is
    # mis-indented the same way.
    content = [l.strip() for l in old_lines]

    def indent(l):
        return l[: len(l) - len(l.lstrip())]

    matches = []
    for i in range(len(fl) - n + 1):
        window = fl[i:i + n]
        if [l.strip() for l in window] != content:
            continue
        delta = None
        extra = ""
        fits = True
        for a, b in zip(old_lines, window):
            if not a.strip():
                continue
            d = len(indent(b)) - len(indent(a))
            if delta is None:
                delta = d
                if d > 0:
                    extra = indent(b)[: d]
            elif d != delta:
                fits = False
                break
        if fits and delta is not None and delta != 0:
            matches.append((i, delta, extra))
    if len(matches) > 1:
        return ("coklu", len(matches))
    if len(matches) == 1:
        i, delta, extra = matches[0]
        b, e = span(i)
        new_lines = []
        for l in n2.split("\n"):
            if not l.strip():
                new_lines.append(l)
            elif delta > 0:
                new_lines.append(extra + l)
            else:
                cut = min(-delta, len(indent(l)))
                new_lines.append(l[cut:])
        return b, e, "\n".join(new_lines), f"girinti {delta:+d} kaydırılarak eşleşti"
    return None


def register(registry: ToolRegistry) -> None:
    # For the pre-write staleness check: path -> mtime_ns at last read.
    seen: dict[Path, int] = {}
    # The file most recently changed in this session: where `denetle`
    # looks when called without a path. So the model can say "I wrote the
    # code, let me check it".
    last_written: list[Path] = []
    # Write count per file. Writing the same file a third time means "I'm
    # trying to fix it by eye and cannot see"; the test-run reminder gets
    # firmer there.
    write_counter: dict[Path, int] = {}

    @registry.tool(
        name="read_file",
        description="""
Bir dosyayı okur. Metin dosyalarında uzun içerik için `offset` ve `limit`
ile satır aralığı verilebilir; çıktı satır numaralı gelir.

Birden çok dosyaya bakacaksan tek tek çağırma: `read_many` hepsini tek
turda okur — keşif için her zaman onu tercih et.

Görsel dosyaları (png, jpg, gif, webp) GERÇEKTEN GÖRÜRSÜN: dosya sana
görüntü olarak gelir. Ekran görüntüsü, tasarım dosyası, hata fotoğrafı —
"okuyamıyorum" deme, aç ve bak.

PDF'lerde ilk sayfaların metni çıkarılır. Taranmış (metinsiz) bir PDF'te
bunu açıkça söyler; o durumda içeriği uydurma.
        """,
        input_schema=object_schema(
            {
                "path": {"type": "string", "description": "Dosya yolu (göreli ya da mutlak)."},
                "offset": {"type": "integer", "description": "Başlangıç satırı (1'den başlar). PDF'te başlangıç sayfası."},
                "limit": {"type": "integer", "description": "Okunacak satır sayısı. PDF'te sayfa sayısı."},
            },
            required=["path"],
        ),
    )
    async def read_file(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        path = _resolve(args["path"], ctx)
        if not path.exists():
            return ToolResult.error(f"Dosya yok: {path}")
        if path.is_dir():
            return ToolResult.error(f"{path} bir dizin. İçeriği için list_dir kullan.")

        # Non-text formats take their own paths: reading a PNG as utf-8
        # sent the model a screenful of junk ("��…"), and the model looked
        # at that junk and thought the file was corrupt.
        if _is_image(path):
            return await asyncio.to_thread(_read_image, path)
        if path.suffix.lower() == ".pdf":
            return await asyncio.to_thread(
                _read_pdf, path, args.get("offset"), args.get("limit"))

        def _read() -> tuple[str, int]:
            data = path.read_text(encoding="utf-8", errors="replace")
            return data, path.stat().st_mtime_ns

        try:
            text, mtime = await asyncio.to_thread(_read)
        except OSError as exc:
            return ToolResult.error(f"Okunamadı: {exc}")

        seen[path] = mtime

        lines = text.splitlines()
        offset = max(1, int(args.get("offset") or 1))
        limit = int(args.get("limit") or len(lines))
        window = lines[offset - 1 : offset - 1 + limit]

        numbered = "\n".join(f"{offset + i:>6}\t{line}" for i, line in enumerate(window))
        if len(numbered) > MAX_READ_CHARS:
            numbered = (
                numbered[:MAX_READ_CHARS]
                + f"\n\n... kırpıldı. Devamı için offset={offset + len(window) // 2} kullan."
            )

        footer = ""
        if offset > 1 or offset - 1 + limit < len(lines):
            footer = f"\n\n[{len(lines)} satırın {offset}-{offset + len(window) - 1} arası]"

        # read_many's announcement through the RESULT channel. Schema +
        # tool description were not enough: 0 calls in 20 runs (29.08
        # sweep). The channel the model reads most carefully is the tool
        # result; while there are unread sibling files in the folder, the
        # address of the next exploration turn is written here, BY NAME. A
        # model that keeps reading one by one is now ignoring not an
        # instruction but the concrete list in front of it. Only code/text
        # extensions and at least 2 candidates: no point producing noise in
        # a one-file folder.
        try:
            unread = sorted(
                k.name for k in path.parent.iterdir()
                if k.is_file() and k != path and k not in seen
                and k.suffix.lower() in (".py", ".js", ".mjs", ".php", ".html",
                                         ".css", ".json", ".md", ".txt"))
            if len(unread) >= 2:
                listing = ", ".join(unread[:6])
                footer += (f"\n\n[Bu klasörde okunmamış {len(unread)} dosya "
                           f"daha var: {listing}. Hepsine bakacaksan read_many "
                           f"tek turda okur — tek tek read_file çağırma.]")
        except OSError:
            pass

        return ToolResult(content=(numbered or "(dosya boş)") + footer)

    # Why a separate tool: the advice "call independent reads in parallel
    # in one turn" did not hold in measurement (0.97 tools/call in the
    # 9-task run — the infrastructure is ready, the small model ignores the
    # instruction). Schema is stronger than instruction: a single tool with
    # an array argument reduces N exploration turns to one round trip.
    @registry.tool(
        name="read_many",
        description="""
Birden çok dosyayı TEK çağrıda okur. Bir görevin başında yapıyı anlamak
için 2-8 dosyaya bakacaksan bunları tek tek read_file ile isteme; hepsini
buraya ver — her dosya için ayrı bir tur harcamazsın.

Yalnız metin dosyaları içindir; görsel ve PDF için read_file kullan.
Uzun dosyalar baştan kırpılır — derinlemesine okuma gerekiyorsa o dosyayı
read_file ile aralık vererek aç.
        """,
        input_schema=object_schema(
            {
                "paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 2,
                    "maxItems": 8,
                    "description": "Okunacak dosya yolları (2-8 adet).",
                },
            },
            required=["paths"],
        ),
    )
    async def read_many(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        raw_paths = args.get("paths") or []
        if not isinstance(raw_paths, list) or not raw_paths:
            return ToolResult.error("paths bir dosya yolu listesi olmalı.")
        raw_paths = [str(p) for p in raw_paths][:8]
        # The total budget is the same as one read_file; the share per file is equal.
        share = max(4_000, MAX_READ_CHARS // len(raw_paths))

        def _one(raw: str) -> str:
            path = _resolve(raw, ctx)
            if not path.exists():
                return f"== {raw} ==\n(hata: dosya yok)"
            if path.is_dir():
                return f"== {raw} ==\n(hata: bu bir dizin — list_dir kullan)"
            if _is_image(path) or path.suffix.lower() == ".pdf":
                return f"== {raw} ==\n(görsel/PDF — read_file ile aç)"
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
                seen[path] = path.stat().st_mtime_ns
            except OSError as exc:
                return f"== {raw} ==\n(hata: {exc})"
            lines = text.splitlines()
            body = "\n".join(f"{i + 1:>6}\t{l}" for i, l in enumerate(lines))
            if len(body) > share:
                body = body[:share] + (
                    f"\n... kırpıldı ({len(lines)} satır). Devamı için "
                    f"read_file(path={raw!r}, offset=...) kullan.")
            return f"== {raw} ==\n{body or '(dosya boş)'}"

        blocks = await asyncio.to_thread(lambda: [_one(p) for p in raw_paths])
        return ToolResult(content="\n\n".join(blocks))

    @registry.tool(
        name="write_file",
        description="""
Dosyayı verilen içerikle yazar; yoksa oluşturur, varsa üzerine yazar.

Var olan bir dosyanın üzerine yazmadan önce onu read_file ile okumuş olman
gerekir. Bu, senin görmediğin değişiklikleri sessizce ezmeni engeller.
Küçük değişiklikler için write_file yerine edit_file kullan.
        """,
        input_schema=object_schema(
            {
                "path": {"type": "string", "description": "Dosya yolu."},
                "content": {"type": "string", "description": "Dosyanın tam yeni içeriği."},
            },
            required=["path", "content"],
        ),
        mutates=True,
        parallel_safe=False,
    )
    async def write_file(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        path = _resolve(args["path"], ctx)
        if refused := _guard(path, ctx):
            return refused
        content = args.get("content", "")

        if path.exists():
            if path not in seen:
                return ToolResult.error(
                    f"{path} zaten var ve bu oturumda okunmadı. "
                    "Üzerine yazmadan önce read_file ile oku."
                )
            if path.stat().st_mtime_ns != seen[path]:
                return ToolResult.error(
                    f"{path} sen okuduktan sonra değişti. Tekrar oku, sonra yaz."
                )

        def _write() -> int:
            # Snapshot right before writing: `undo` is only possible this way.
            _snapshot(path, ctx, "write_file")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            return path.stat().st_mtime_ns

        try:
            seen[path] = await asyncio.to_thread(_write)
        except OSError as exc:
            return ToolResult.error(f"Yazılamadı: {exc}")

        last_written[:] = [path]
        write_counter[path] = write_counter.get(path, 0) + 1
        testrun.touched(path)
        diagnosis_text, diagnosis_detail = await _diagnosis_suffix(path)
        testrun_text = await _testrun_suffix(path, write_counter[path])
        return ToolResult(
            content=f"{path} yazıldı ({len(content.splitlines())} satır)."
                    + diagnosis_text + (f"\n{testrun_text}" if testrun_text else ""),
            detail={"path": str(path), "bytes": len(content.encode("utf-8")),
                    **diagnosis_detail},
        )

    @registry.tool(
        name="edit_file",
        description="""
Bir dosyada tam metin değişimi yapar. `old` metni dosyada tam olarak bir kez
geçmelidir — sıfır ya da birden fazla eşleşmede işlem yapılmaz ve hata döner.
Boşluk farkları hoş görülür: satır sonu (CRLF/LF), satır sonundaki boşluk ve
TEK-TİP girinti kayması eşleşmeyi bozmaz (yine tek eşleşme şartıyla; kayma
`new`e de uygulanır). İçerik farkı hoş görülmez.
Benzersiz kılmak için etrafından yeterince bağlam al.

Aynı dosyada birden fazla değişiklik için `edits` ver: [{old, new}, ...].
Uygulama ATOMİKTİR — önce hepsi doğrulanır, biri bile tutmazsa hiçbiri
uygulanmaz ve hangi maddenin neden tutmadığı söylenir.

Dosyayı önce read_file ile okumuş olman gerekir.
        """,
        input_schema=object_schema(
            {
                "path": {"type": "string", "description": "Dosya yolu."},
                "old": {"type": "string", "description": "Değiştirilecek tam metin (tekli kullanım)."},
                "new": {"type": "string", "description": "Yerine yazılacak metin (tekli kullanım)."},
                "edits": {
                    "type": "array",
                    "description": "Çoklu değişiklik: [{old, new}, ...]. Hepsi ya da hiçbiri.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "old": {"type": "string"},
                            "new": {"type": "string"},
                        },
                        "required": ["old", "new"],
                    },
                },
            },
            required=["path"],
        ),
        mutates=True,
        parallel_safe=False,
    )
    async def edit_file(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        path = _resolve(args["path"], ctx)
        if refused := _guard(path, ctx):
            return refused

        edits = args.get("edits")
        if edits:
            pairs = [(e.get("old"), e.get("new")) for e in edits if isinstance(e, dict)]
            if len(pairs) != len(edits):
                return ToolResult.error("`edits` maddeleri {old, new} nesneleri olmalı.")
        elif "old" in args and "new" in args:
            pairs = [(args["old"], args["new"])]
        else:
            return ToolResult.error(
                "Ya `old`+`new` (tek değişiklik) ya da `edits` (çoklu) vermelisin."
            )

        if not path.exists():
            return ToolResult.error(f"Dosya yok: {path}")
        if path not in seen:
            return ToolResult.error(f"{path} bu oturumda okunmadı. Önce read_file ile oku.")

        text = await asyncio.to_thread(path.read_text, encoding="utf-8")

        # ALL are validated first; the error text shows the item with its
        # number so the model knows what to fix. Nothing has been written yet.
        spans: list[tuple[int, int, str, int]] = []  # (start, end, new, item no)
        notes: list[str] = []   # explanation of tolerant matches — goes into the message
        multiple = len(pairs) > 1
        for no, (old, new) in enumerate(pairs, 1):
            which = f"{no}. madde: " if multiple else ""
            nothing = " Hiçbir değişiklik uygulanmadı." if multiple else ""
            if not isinstance(old, str) or not isinstance(new, str) or not old:
                return ToolResult.error(
                    f"{which}`old` ve `new` dolu birer metin olmalı.{nothing}"
                )
            count = text.count(old)
            if count == 0:
                # Whitespace/indent/line-ending tolerance: if the content is
                # right the turn is not burned. The match must still be UNIQUE.
                loose = _esnek_esle(text, old, new)
                if isinstance(loose, tuple) and loose and loose[0] == "coklu":
                    return ToolResult.error(
                        f"{which}Aranan metin (boşluk toleransıyla) {loose[1]} kez "
                        f"geçiyor, hangisi olduğu belirsiz. Bağlam ekleyerek "
                        f"benzersizleştir.{nothing}"
                    )
                if loose is None:
                    return ToolResult.error(
                        f"{which}Aranan metin dosyada yok. Girintiyi ve satır sonlarını "
                        f"birebir eşleştir; emin değilsen dosyayı tekrar oku.{nothing}"
                    )
                b, e, new_text, note = loose
                spans.append((b, e, new_text, no))
                notes.append(f"{which}{note}")
                continue
            if count > 1:
                return ToolResult.error(
                    f"{which}Aranan metin {count} kez geçiyor, hangisi olduğu belirsiz. "
                    f"Öncesinden/sonrasından bağlam ekleyerek benzersizleştir.{nothing}"
                )
            start = text.index(old)
            spans.append((start, start + len(old), new, no))

        # Order-independent overlap check: if two items touch the same
        # region the result would depend on the items' order — that is an
        # ambiguity, an error.
        spans.sort()
        for (b1, s1, _, n1), (b2, _, _, n2) in zip(spans, spans[1:]):
            if b2 < s1:
                return ToolResult.error(
                    f"{n1}. ve {n2}. maddeler çakışıyor (aynı metin bölgesini "
                    "değiştiriyorlar). Maddeleri birleştir. Hiçbir değişiklik uygulanmadı."
                )

        def _apply() -> int:
            # Snapshot right before writing: `undo` is only possible this way.
            _snapshot(path, ctx, "edit_file")
            updated = text
            # From the end to the start: earlier replacements must not
            # shift the positions of later ones.
            for start, end, new, _ in reversed(spans):
                updated = updated[:start] + new + updated[end:]
            path.write_text(updated, encoding="utf-8")
            return path.stat().st_mtime_ns

        seen[path] = await asyncio.to_thread(_apply)
        # The line where the change starts: so the step card in the UI can
        # draw the diff with real line numbers. For multiple edits the line
        # of the FIRST change (UI contract).
        line = text[: spans[0][0]].count("\n") + 1
        message = (
            f"{path} güncellendi ({len(spans)} değişiklik)."
            if len(spans) > 1
            else f"{path} güncellendi."
        )
        if notes:
            # If tolerance kicked in the model should know: a sign that it
            # should take the next old from the real form in the file.
            message += " (" + "; ".join(notes) + ")"
        last_written[:] = [path]
        write_counter[path] = write_counter.get(path, 0) + 1
        testrun.touched(path)
        diagnosis_text, diagnosis_detail = await _diagnosis_suffix(path)
        testrun_text = await _testrun_suffix(path, write_counter[path])
        return ToolResult(
            content=message + diagnosis_text + (f"\n{testrun_text}" if testrun_text else ""),
            detail={"path": str(path), "line": line, **diagnosis_detail},
        )

    @registry.tool(
        name="copy_in",
        description="""
Dışarıdaki bir dosyayı ya da klasörü atölyene kopyalar. Orijinaline
dokunulmaz. Atölye dışına yazamadığın için, üzerinde çalışman gereken bir
dosya varsa yolu budur.

`to` verilmezse dosya atölyenin köküne kendi adıyla düşer.
        """,
        input_schema=object_schema(
            {
                "path": {"type": "string", "description": "Kopyalanacak kaynak yolu."},
                "to": {
                    "type": "string",
                    "description": "Atölye içinde hedef yol (göreli).",
                },
            },
            required=["path"],
        ),
        mutates=True,
        parallel_safe=False,
    )
    async def copy_in(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        source = Path(args["path"]).expanduser()
        if not source.is_absolute():
            source = ctx.workspace / source
        if not source.exists():
            return ToolResult.error(f"Kaynak yok: {source}")

        target = _resolve(args.get("to") or source.name, ctx)
        if refused := _guard(target, ctx):
            return refused
        if target.exists():
            return ToolResult.error(
                f"{target} zaten var. Üzerine yazmak istiyorsan başka bir ad ver "
                "ya da önce sil."
            )

        def _copy() -> int:
            target.parent.mkdir(parents=True, exist_ok=True)
            if source.is_dir():
                # A directory copy is not kept in the ledger: squeezing
                # dozens of files into one "yoktu" record would make undo
                # a liar.
                shutil.copytree(source, target)
                return sum(1 for _ in target.rglob("*") if _.is_file())
            # The target does not exist yet (a "yoktu" record is written);
            # if overwriting is ever allowed the same call also stores the
            # current state.
            _snapshot(target, ctx, "copy_in")
            shutil.copy2(source, target)
            return 1

        try:
            count = await asyncio.to_thread(_copy)
        except OSError as exc:
            return ToolResult.error(f"Kopyalanamadı: {exc}")

        # The copy counts as read: this process wrote it a moment ago, the
        # staleness check would force the model into a needless read_file
        # turn here.
        if target.is_file():
            seen[target] = target.stat().st_mtime_ns

        return ToolResult(
            content=f"{source} → {target} ({count} dosya).",
            detail={"path": str(target), "files": count},
        )

    @registry.tool(
        name="list_dir",
        description="""
Bir dizinin içeriğini listeler. `pattern` verilirse glob deseniyle özyinelemeli
arar (örn. "**/*.py"). Dizinler sonunda / ile gösterilir.
        """,
        input_schema=object_schema(
            {
                "path": {"type": "string", "description": "Dizin yolu."},
                "pattern": {"type": "string", "description": "Özyinelemeli glob deseni."},
            },
            required=["path"],
        ),
    )
    async def list_dir(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        root = _resolve(args["path"], ctx)
        if not root.is_dir():
            return ToolResult.error(f"Dizin yok: {root}")

        pattern = args.get("pattern")

        def _scan() -> list[str]:
            entries = sorted(root.glob(pattern)) if pattern else sorted(root.iterdir())
            return [
                f"{p.relative_to(root)}{'/' if p.is_dir() else ''}"
                for p in entries[:MAX_LIST_ENTRIES]
            ]

        try:
            names = await asyncio.to_thread(_scan)
        except OSError as exc:
            return ToolResult.error(f"Listelenemedi: {exc}")

        if not names:
            return ToolResult(content="(boş)")

        body = "\n".join(names)
        if len(names) == MAX_LIST_ENTRIES:
            body += f"\n\n... ilk {MAX_LIST_ENTRIES} girdi gösterildi, daha var."
        return ToolResult(content=f"{root}\n{body}")

    @registry.tool(
        name="denetle",
        description="""
Kodu, dilinin kendi denetleyicisiyle sınar ve bulduğu hataları satır
numaralarıyla döndürür (Python derleyicisi/ruff, `php -l`, `node --check`,
tsc, JSON/YAML ayrıştırıcıları).

`path` bir dosya ya da klasör olabilir; verilmezse en son yazdığın dosyaya
bakar. Klasörde `pattern` ile daraltabilirsin (örn. "*.php").

Ne zaman kullan: bir dosyayı düzenledikten sonra — yazma araçları tanıyı
zaten kendiliğinden ekler, ama elle yazdığın ya da kabuktan ürettiğin
kodu buradan sınarsın.

Dikkat: temiz sonuç "kod çalışıyor" demek DEĞİLDİR. Denetleyiciler
çoğunlukla sözdizimine bakar; tip hataları ve çalışma zamanı davranışı
ancak kodu gerçekten koşturunca ortaya çıkar. Hangi denetleyicinin baktığı
cevapta yazar.
        """,
        input_schema=object_schema(
            {
                "path": {
                    "type": "string",
                    "description": "Denetlenecek dosya ya da klasör. "
                                   "Boş bırakılırsa en son yazılan dosya.",
                },
                "pattern": {
                    "type": "string",
                    "description": "Klasör denetiminde ad deseni (örn. \"*.py\").",
                },
            },
        ),
    )
    async def denetle(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        raw = (args.get("path") or "").strip()
        if raw:
            target = _resolve(raw, ctx)
        elif last_written:
            target = last_written[0]
        else:
            return ToolResult.error(
                "Bu oturumda henüz bir dosya yazmadın, denetlenecek bir şey yok. "
                "Denetlemek istediğin dosyayı `path` ile ver."
            )

        if not target.exists():
            return ToolResult.error(f"Yol yok: {target}")

        pattern = args.get("pattern") or None
        if target.is_dir():
            paths = await asyncio.to_thread(
                diagnostics.batch_paths, target, pattern=pattern, limit=MAX_AUDIT_FILES
            )
            root: Path | None = target
        else:
            paths, root = [target], target.parent

        if not paths:
            return ToolResult(
                content=f"{target} altında denetlenebilir dosya yok. "
                        "Tanınan uzantılar: " + ", ".join(sorted(diagnostics.EXTENSIONS)) + "."
            )

        diagnoses = await asyncio.to_thread(diagnostics.check_many, paths)
        if not diagnoses:
            # A single file with an unrecognised extension: no invention,
            # say so honestly.
            return ToolResult(
                content=f"{target} için bir denetleyici tanımıyorum "
                        f"({target.suffix or 'uzantısız'}). Kontrol edilmedi."
            )

        faulty = sum(1 for t in diagnoses if t.status == "hata")
        return ToolResult(
            content=diagnostics.summary(diagnoses, root=root),
            detail={
                "path": str(target),
                "hatali": faulty,
                "taniler": [t.detail() for t in diagnoses],
            },
        )
