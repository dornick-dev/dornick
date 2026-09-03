"""`read_file`: non-text files.

Proven wound: opening a PNG with `read_file` sent the model a screenful of
"��". The model read that as "the file is corrupt" and told the user so —
yet the file was perfectly fine, we were looking with the wrong eye. The
same for PDF: a contract, an invoice, a report were closed to `read_file`.

The promise tested: an image goes to the model as an IMAGE, a PDF's text
is extracted, and the limits of both are stated honestly — an unreadable
PDF is not called "empty", it is called "carries no text layer".
"""

from __future__ import annotations

import asyncio
import base64
import struct
import zlib
from pathlib import Path

import pytest

from dornick.config import Config
from dornick.events import EventLog
from dornick.session import Session
from dornick.tools import ToolContext, ToolRegistry
from dornick.tools import files as file_tools


# -- small but REAL files ----------------------------------------------
#
# Not a fake byte string: a real PNG and a real PDF are produced. A test
# that "a byte string was base64-encoded" proves nothing; the real
# question is whether these files come out in a form that can go to the
# model.


def write_png(path: Path, width: int = 2, height: int = 2) -> Path:
    """A hand-built, valid PNG (without asking for a dependency)."""
    def chunk(kind: bytes, body: bytes) -> bytes:
        return (struct.pack(">I", len(body)) + kind + body
                + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    rows = b"".join(b"\x00" + b"\xff\x00\x00" * width for _ in range(height))
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
                     + chunk(b"IDAT", zlib.compress(rows))
                     + chunk(b"IEND", b""))
    return path


def write_pdf(path: Path, pages: list[str]) -> Path:
    """A real, valid PDF — one with a text layer.

    Built by hand without dependencies: the content stream has a real `Tj`
    text operator, so `extract_text` actually does work. Using a ready-made
    generator would tie the test to that generator's version.
    """
    path.write_bytes(_handmade_pdf(pages))
    return path


def _handmade_pdf(pages: list[str]) -> bytes:
    """A minimal but valid PDF: one Tj text operator per page."""
    objects: list[bytes] = []
    page_ids = [4 + 2 * i for i in range(len(pages))]

    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    kids = " ".join(f"{n} 0 R" for n in page_ids).encode()
    objects.append(b"<< /Type /Pages /Kids [" + kids + b"] /Count "
                   + str(len(pages)).encode() + b" >>")
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    for i, text in enumerate(pages):
        content = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
        objects.append(
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 3 0 R >> >> /Contents "
            + str(5 + 2 * i).encode() + b" 0 R >>")
        objects.append(b"<< /Length " + str(len(content)).encode() + b" >>\n"
                       b"stream\n" + content + b"\nendstream")

    body = b"%PDF-1.4\n"
    offsets: list[int] = []
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(body))
        body += str(i).encode() + b" 0 obj\n" + obj + b"\nendobj\n"

    xref = len(body)
    body += b"xref\n0 " + str(len(objects) + 1).encode() + b"\n"
    body += b"0000000000 65535 f \n"
    for offset in offsets:
        body += f"{offset:010d} 00000 n \n".encode()
    body += (b"trailer\n<< /Size " + str(len(objects) + 1).encode()
             + b" /Root 1 0 R >>\nstartxref\n" + str(xref).encode()
             + b"\n%%EOF\n")
    return body


@pytest.fixture()
def ctx(tmp_path: Path) -> ToolContext:
    config = Config.load(tmp_path)
    config.ensure_dirs()
    return ToolContext(
        config=config,
        session=Session(EventLog(tmp_path / ".dornick" / "s.jsonl"), "test-oku"),
        cancel=asyncio.Event(),
    )


@pytest.fixture()
def registry() -> ToolRegistry:
    reg = ToolRegistry()
    file_tools.register(reg)
    return reg


async def read(registry: ToolRegistry, ctx: ToolContext, **args):
    return await registry.get("read_file").handler(args, ctx)


# -- images ------------------------------------------------------------


async def test_a_png_comes_back_as_an_image(
    registry: ToolRegistry, ctx: ToolContext, tmp_path: Path
) -> None:
    """The core promise: the model SEES the file, it does not read its bytes."""
    path = write_png(tmp_path / "ekran.png")
    result = await read(registry, ctx, path=str(path))

    assert not result.is_error
    data = result.detail["image"]
    assert data.startswith("data:image/png;base64,")
    # What is carried is really the file itself.
    assert base64.b64decode(data.split(",", 1)[1]) == path.read_bytes()
    # The text side tells the model what happened.
    assert "ekran.png" in result.content and "görüyorsun" in result.content


async def test_the_image_reaches_the_model_through_the_executor(
    ctx: ToolContext, tmp_path: Path
) -> None:
    """The transport was ready and unused: the executor attaches
    `detail["image"]` to the block as `_image`, and the loop turns it into
    an image block. Here we verify the connection is really made."""
    from dornick.permissions import PermissionEngine
    from dornick.session import PendingToolUse
    from dornick.tools import execute

    registry = ToolRegistry()
    file_tools.register(registry)
    path = write_png(tmp_path / "kare.png")

    blocks = await execute(
        [PendingToolUse(id="c1", name="read_file", input={"path": str(path)})],
        registry=registry,
        permissions=PermissionEngine("yolo", [], []),
        ctx=ctx,
        approve=lambda *_: asyncio.sleep(0, result=True),
    )
    assert blocks[0]["_image"].startswith("data:image/png;base64,")


@pytest.mark.parametrize("name,kind", [
    ("a.png", "image/png"), ("b.jpg", "image/jpeg"), ("c.jpeg", "image/jpeg"),
    ("d.gif", "image/gif"), ("e.webp", "image/webp"),
])
def test_supported_image_types(name: str, kind: str) -> None:
    assert file_tools.IMAGE_TYPES[Path(name).suffix] == kind


def test_unsupported_image_types_stay_out(tmp_path: Path) -> None:
    """Sending a type the API does not accept returns 400; it must never enter."""
    for name in ("resim.bmp", "vektor.svg", "foto.tiff", "ham.heic"):
        assert not file_tools._is_image(tmp_path / name)


async def test_an_oversized_image_says_so_instead_of_guessing(
    registry: ToolRegistry, ctx: ToolContext, tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(file_tools, "MAX_IMAGE_BYTES", 10)
    path = write_png(tmp_path / "buyuk.png")
    result = await read(registry, ctx, path=str(path))
    assert result.is_error
    assert "gönderilemeyecek kadar büyük" in result.content
    assert "İçeriğini göremiyorum" in result.content
    assert "image" not in result.detail        # no half image is sent


async def test_a_text_file_is_unaffected(
    registry: ToolRegistry, ctx: ToolContext, tmp_path: Path
) -> None:
    """The text path must not change by a single letter."""
    path = tmp_path / "not.txt"
    path.write_text("bir\niki\n", encoding="utf-8")
    result = await read(registry, ctx, path=str(path))
    assert "bir" in result.content and "iki" in result.content
    assert "image" not in result.detail


# -- PDF ---------------------------------------------------------------


async def test_a_pdf_yields_its_text(
    registry: ToolRegistry, ctx: ToolContext, tmp_path: Path
) -> None:
    path = write_pdf(tmp_path / "sozlesme.pdf",
                     ["Birinci sayfa metni", "Ikinci sayfa metni"])
    result = await read(registry, ctx, path=str(path))

    assert not result.is_error
    assert "Birinci sayfa metni" in result.content
    assert "Ikinci sayfa metni" in result.content
    assert "--- sayfa 1 ---" in result.content
    assert result.detail["sayfa"] == 2


async def test_a_pdf_always_says_how_much_it_read(
    registry: ToolRegistry, ctx: ToolContext, tmp_path: Path
) -> None:
    """The model must not read 3 pages and think it summarised a 200-page report."""
    path = write_pdf(tmp_path / "rapor.pdf", [f"sayfa {i}" for i in range(1, 8)])
    result = await read(registry, ctx, path=str(path), limit=2)
    assert "7 sayfa, 1-2 arası okundu" in result.content
    assert "offset=3" in result.content
    assert "sayfa 3" not in result.content


async def test_a_pdf_page_range(
    registry: ToolRegistry, ctx: ToolContext, tmp_path: Path
) -> None:
    path = write_pdf(tmp_path / "r.pdf", [f"benzersiz{i}" for i in range(1, 6)])
    result = await read(registry, ctx, path=str(path), offset=4, limit=2)
    assert "benzersiz4" in result.content and "benzersiz5" in result.content
    assert "benzersiz1" not in result.content


async def test_a_page_beyond_the_end_is_refused_clearly(
    registry: ToolRegistry, ctx: ToolContext, tmp_path: Path
) -> None:
    path = write_pdf(tmp_path / "kisa.pdf", ["tek sayfa"])
    result = await read(registry, ctx, path=str(path), offset=9)
    assert result.is_error
    assert "1 sayfa" in result.content
    assert "1 ile 1 arasında" in result.content


async def test_a_scanned_pdf_is_honest_about_having_no_text(
    registry: ToolRegistry, ctx: ToolContext, tmp_path: Path
) -> None:
    """The most important PDF test: saying 'empty' makes the model think the file has no content."""
    path = write_pdf(tmp_path / "taranmis.pdf", [""])
    result = await read(registry, ctx, path=str(path))
    assert "METİN KATMANI TAŞIMIYOR" in result.content
    assert "uydurma" in result.content
    assert result.detail["metinsiz"] is True


async def test_a_broken_pdf_does_not_pretend(
    registry: ToolRegistry, ctx: ToolContext, tmp_path: Path
) -> None:
    path = tmp_path / "bozuk.pdf"
    path.write_bytes(b"%PDF-1.4\nbu bir PDF degil")
    result = await read(registry, ctx, path=str(path))
    assert result.is_error
    assert "açılamadı" in result.content or "sayfa içermiyor" in result.content


async def test_a_missing_pypdf_is_reported_not_faked(
    registry: ToolRegistry, ctx: ToolContext, tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch
) -> None:
    """If the library is missing we do not guess about the content."""
    import builtins

    path = write_pdf(tmp_path / "x.pdf", ["metin"])   # the file, BEFORE the patch
    real_import = builtins.__import__

    def block(name, *a, **k):
        if name == "pypdf":
            raise ImportError("yok")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", block)
    result = await read(registry, ctx, path=str(path))
    assert result.is_error
    assert "pypdf" in result.content
    assert "tahminde bulunmayacağım" in result.content


async def test_long_pdf_text_is_clipped(
    registry: ToolRegistry, ctx: ToolContext, tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(file_tools, "MAX_PDF_CHARS", 200)
    path = write_pdf(tmp_path / "uzun.pdf", ["x" * 400])
    result = await read(registry, ctx, path=str(path))
    assert "(kırpıldı)" in result.content


def test_the_description_tells_the_model_it_can_see(registry: ToolRegistry) -> None:
    """The tool schema is the only document the model sees: it must not say 'I cannot read'."""
    description = registry.get("read_file").description
    assert "GERÇEKTEN GÖRÜRSÜN" in description
    assert "PDF" in description
    assert "uydurma" in description
