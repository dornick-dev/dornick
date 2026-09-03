"""`read_file`: metin olmayan dosyalar.

Kanıtlanmış yara: bir PNG'yi `read_file` ile açmak modele bir ekran dolusu
"��" gönderiyordu. Model bunu "dosya bozuk" diye okuyup kullanıcıya öyle
söylüyordu — oysa dosya sapasağlamdı, biz yanlış gözle bakıyorduk. Aynısı
PDF için: bir sözleşme, bir fatura, bir rapor `read_file`a kapalıydı.

Sınanan vaat: görsel modele GÖRÜNTÜ olarak gider, PDF'in metni çıkarılır,
ve ikisinin de sınırları dürüstçe söylenir — okunamayan bir PDF'te "boş"
denmez, "metin katmanı taşımıyor" denir.
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


# -- küçük ama GERÇEK dosyalar -----------------------------------------
#
# Sahte bayt dizisi değil: gerçek bir PNG ve gerçek bir PDF üretiliyor.
# "Bir bayt dizisi base64'e çevrildi" testi hiçbir şey kanıtlamaz; asıl
# soru bu dosyaların modele gidebilecek biçimde çıkıp çıkmadığı.


def png_yaz(yol: Path, en: int = 2, boy: int = 2) -> Path:
    """Elle kurulmuş, geçerli bir PNG (bağımlılık istemeden)."""
    def parca(tur: bytes, govde: bytes) -> bytes:
        return (struct.pack(">I", len(govde)) + tur + govde
                + struct.pack(">I", zlib.crc32(tur + govde) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBBBBB", en, boy, 8, 2, 0, 0, 0)
    satirlar = b"".join(b"\x00" + b"\xff\x00\x00" * en for _ in range(boy))
    yol.write_bytes(b"\x89PNG\r\n\x1a\n" + parca(b"IHDR", ihdr)
                    + parca(b"IDAT", zlib.compress(satirlar))
                    + parca(b"IEND", b""))
    return yol


def pdf_yaz(yol: Path, sayfalar: list[str]) -> Path:
    """Gerçek, geçerli bir PDF — metin katmanı olan.

    Bağımlılıksız elle kuruluyor: içerik akışında gerçek bir `Tj` metin
    operatörü var, yani `extract_text` gerçekten iş yapıyor. Hazır bir
    üretici kullanmak testi o üreticinin sürümüne bağlardı.
    """
    yol.write_bytes(_elle_pdf(sayfalar))
    return yol


def _elle_pdf(sayfalar: list[str]) -> bytes:
    """Asgari ama geçerli bir PDF: her sayfada bir Tj metin operatörü."""
    nesneler: list[bytes] = []
    sayfa_ids = [4 + 2 * i for i in range(len(sayfalar))]

    nesneler.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    kids = " ".join(f"{n} 0 R" for n in sayfa_ids).encode()
    nesneler.append(b"<< /Type /Pages /Kids [" + kids + b"] /Count "
                    + str(len(sayfalar)).encode() + b" >>")
    nesneler.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    for i, metin in enumerate(sayfalar):
        icerik = f"BT /F1 12 Tf 72 720 Td ({metin}) Tj ET".encode()
        nesneler.append(
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 3 0 R >> >> /Contents "
            + str(5 + 2 * i).encode() + b" 0 R >>")
        nesneler.append(b"<< /Length " + str(len(icerik)).encode() + b" >>\n"
                        b"stream\n" + icerik + b"\nendstream")

    govde = b"%PDF-1.4\n"
    yerler: list[int] = []
    for i, nesne in enumerate(nesneler, start=1):
        yerler.append(len(govde))
        govde += str(i).encode() + b" 0 obj\n" + nesne + b"\nendobj\n"

    xref = len(govde)
    govde += b"xref\n0 " + str(len(nesneler) + 1).encode() + b"\n"
    govde += b"0000000000 65535 f \n"
    for yer in yerler:
        govde += f"{yer:010d} 00000 n \n".encode()
    govde += (b"trailer\n<< /Size " + str(len(nesneler) + 1).encode()
              + b" /Root 1 0 R >>\nstartxref\n" + str(xref).encode()
              + b"\n%%EOF\n")
    return govde


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


async def oku(registry: ToolRegistry, ctx: ToolContext, **args):
    return await registry.get("read_file").handler(args, ctx)


# -- görseller ----------------------------------------------------------


async def test_a_png_comes_back_as_an_image(
    registry: ToolRegistry, ctx: ToolContext, tmp_path: Path
) -> None:
    """Asıl vaat: model dosyayı GÖRÜYOR, baytlarını okumuyor."""
    yol = png_yaz(tmp_path / "ekran.png")
    sonuc = await oku(registry, ctx, path=str(yol))

    assert not sonuc.is_error
    veri = sonuc.detail["image"]
    assert veri.startswith("data:image/png;base64,")
    # Taşınan şey gerçekten dosyanın kendisi.
    assert base64.b64decode(veri.split(",", 1)[1]) == yol.read_bytes()
    # Metin tarafı modele ne olduğunu söylüyor.
    assert "ekran.png" in sonuc.content and "görüyorsun" in sonuc.content


async def test_the_image_reaches_the_model_through_the_executor(
    ctx: ToolContext, tmp_path: Path
) -> None:
    """Taşıma yolu hazırdı ve kullanılmıyordu: yürütücü `detail["image"]`ı
    bloğa `_image` olarak iliştiriyor, döngü de onu görüntü bloğuna
    çeviriyor. Bağlantının gerçekten kurulduğunu burada doğruluyoruz."""
    from dornick.permissions import PermissionEngine
    from dornick.session import PendingToolUse
    from dornick.tools import execute

    registry = ToolRegistry()
    file_tools.register(registry)
    yol = png_yaz(tmp_path / "kare.png")

    bloklar = await execute(
        [PendingToolUse(id="c1", name="read_file", input={"path": str(yol)})],
        registry=registry,
        permissions=PermissionEngine("yolo", [], []),
        ctx=ctx,
        approve=lambda *_: asyncio.sleep(0, result=True),
    )
    assert bloklar[0]["_image"].startswith("data:image/png;base64,")


@pytest.mark.parametrize("ad,tur", [
    ("a.png", "image/png"), ("b.jpg", "image/jpeg"), ("c.jpeg", "image/jpeg"),
    ("d.gif", "image/gif"), ("e.webp", "image/webp"),
])
def test_supported_image_types(ad: str, tur: str) -> None:
    assert file_tools.IMAGE_TYPES[Path(ad).suffix] == tur


def test_unsupported_image_types_stay_out(tmp_path: Path) -> None:
    """API kabul etmeyen bir tür göndermek 400 döner; hiç girmesin."""
    for ad in ("resim.bmp", "vektor.svg", "foto.tiff", "ham.heic"):
        assert not file_tools._is_image(tmp_path / ad)


async def test_an_oversized_image_says_so_instead_of_guessing(
    registry: ToolRegistry, ctx: ToolContext, tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(file_tools, "MAX_GORSEL", 10)
    yol = png_yaz(tmp_path / "buyuk.png")
    sonuc = await oku(registry, ctx, path=str(yol))
    assert sonuc.is_error
    assert "gönderilemeyecek kadar büyük" in sonuc.content
    assert "İçeriğini göremiyorum" in sonuc.content
    assert "image" not in sonuc.detail        # yarım bir görüntü gönderilmiyor


async def test_a_text_file_is_unaffected(
    registry: ToolRegistry, ctx: ToolContext, tmp_path: Path
) -> None:
    """Metin yolu bir harf bile değişmemeli."""
    yol = tmp_path / "not.txt"
    yol.write_text("bir\niki\n", encoding="utf-8")
    sonuc = await oku(registry, ctx, path=str(yol))
    assert "bir" in sonuc.content and "iki" in sonuc.content
    assert "image" not in sonuc.detail


# -- PDF ----------------------------------------------------------------


async def test_a_pdf_yields_its_text(
    registry: ToolRegistry, ctx: ToolContext, tmp_path: Path
) -> None:
    yol = pdf_yaz(tmp_path / "sozlesme.pdf",
                  ["Birinci sayfa metni", "Ikinci sayfa metni"])
    sonuc = await oku(registry, ctx, path=str(yol))

    assert not sonuc.is_error
    assert "Birinci sayfa metni" in sonuc.content
    assert "Ikinci sayfa metni" in sonuc.content
    assert "--- sayfa 1 ---" in sonuc.content
    assert sonuc.detail["sayfa"] == 2


async def test_a_pdf_always_says_how_much_it_read(
    registry: ToolRegistry, ctx: ToolContext, tmp_path: Path
) -> None:
    """Model 3 sayfayı okuyup 200 sayfalık raporu özetlediğini sanmasın."""
    yol = pdf_yaz(tmp_path / "rapor.pdf", [f"sayfa {i}" for i in range(1, 8)])
    sonuc = await oku(registry, ctx, path=str(yol), limit=2)
    assert "7 sayfa, 1-2 arası okundu" in sonuc.content
    assert "offset=3" in sonuc.content
    assert "sayfa 3" not in sonuc.content


async def test_a_pdf_page_range(
    registry: ToolRegistry, ctx: ToolContext, tmp_path: Path
) -> None:
    yol = pdf_yaz(tmp_path / "r.pdf", [f"benzersiz{i}" for i in range(1, 6)])
    sonuc = await oku(registry, ctx, path=str(yol), offset=4, limit=2)
    assert "benzersiz4" in sonuc.content and "benzersiz5" in sonuc.content
    assert "benzersiz1" not in sonuc.content


async def test_a_page_beyond_the_end_is_refused_clearly(
    registry: ToolRegistry, ctx: ToolContext, tmp_path: Path
) -> None:
    yol = pdf_yaz(tmp_path / "kisa.pdf", ["tek sayfa"])
    sonuc = await oku(registry, ctx, path=str(yol), offset=9)
    assert sonuc.is_error
    assert "1 sayfa" in sonuc.content
    assert "1 ile 1 arasında" in sonuc.content


async def test_a_scanned_pdf_is_honest_about_having_no_text(
    registry: ToolRegistry, ctx: ToolContext, tmp_path: Path
) -> None:
    """En önemli PDF testi: 'boş' demek modele dosyayı içeriksiz sandırır."""
    yol = pdf_yaz(tmp_path / "taranmis.pdf", [""])
    sonuc = await oku(registry, ctx, path=str(yol))
    assert "METİN KATMANI TAŞIMIYOR" in sonuc.content
    assert "uydurma" in sonuc.content
    assert sonuc.detail["metinsiz"] is True


async def test_a_broken_pdf_does_not_pretend(
    registry: ToolRegistry, ctx: ToolContext, tmp_path: Path
) -> None:
    yol = tmp_path / "bozuk.pdf"
    yol.write_bytes(b"%PDF-1.4\nbu bir PDF degil")
    sonuc = await oku(registry, ctx, path=str(yol))
    assert sonuc.is_error
    assert "açılamadı" in sonuc.content or "sayfa içermiyor" in sonuc.content


async def test_a_missing_pypdf_is_reported_not_faked(
    registry: ToolRegistry, ctx: ToolContext, tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch
) -> None:
    """Kütüphane yoksa içerik hakkında tahmin yürütmüyoruz."""
    import builtins

    yol = pdf_yaz(tmp_path / "x.pdf", ["metin"])   # dosya, yama'dan ÖNCE
    gercek = builtins.__import__

    def engelle(ad, *a, **k):
        if ad == "pypdf":
            raise ImportError("yok")
        return gercek(ad, *a, **k)

    monkeypatch.setattr(builtins, "__import__", engelle)
    sonuc = await oku(registry, ctx, path=str(yol))
    assert sonuc.is_error
    assert "pypdf" in sonuc.content
    assert "tahminde bulunmayacağım" in sonuc.content


async def test_long_pdf_text_is_clipped(
    registry: ToolRegistry, ctx: ToolContext, tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(file_tools, "MAX_PDF_KARAKTER", 200)
    yol = pdf_yaz(tmp_path / "uzun.pdf", ["x" * 400])
    sonuc = await oku(registry, ctx, path=str(yol))
    assert "(kırpıldı)" in sonuc.content


def test_the_description_tells_the_model_it_can_see(registry: ToolRegistry) -> None:
    """Araç şeması modelin gördüğü tek belge: 'okuyamıyorum' dememeli."""
    aciklama = registry.get("read_file").description
    assert "GERÇEKTEN GÖRÜRSÜN" in aciklama
    assert "PDF" in aciklama
    assert "uydurma" in aciklama
