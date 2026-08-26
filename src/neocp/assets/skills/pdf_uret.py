"""Metinden PDF üretir.

Standart yetenek — paketle geldi. Değiştirebilir, silebilirsin.
"""

NAME = "pdf_uret"
DESCRIPTION = """Verilen başlık ve metinden düzgün biçimli bir PDF üretir
(rapor, tutanak, teklif). Markdown-vari yapı anlar: '# ' ile başlayan satır
bölüm başlığı, '- ' ile başlayan satır madde olur. Kullanıcı "PDF yap",
"rapor çıkar", "yazdırılabilir hale getir" dediğinde kullan. Çıktı atölyeye
yazılır ve yolu söylenir."""

SCHEMA = {
    "type": "object",
    "properties": {
        "path": {"type": "string",
                 "description": "Çıktı dosyası (ör. raporlar/ozet.pdf)."},
        "title": {"type": "string", "description": "Kapak başlığı."},
        "text": {"type": "string",
                 "description": "İçerik. '# başlık' bölüm, '- madde' liste."},
    },
    "required": ["path", "title", "text"],
}


def run(args, ctx):
    from pathlib import Path

    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
    except ImportError:
        return ("PDF üretmek için `reportlab` gerekli. Kabukta "
                "`py -m pip install reportlab` çalıştırıp yeniden dene.")

    out = Path(str(args.get("path") or "rapor.pdf"))
    if not out.is_absolute():
        out = ctx.sandbox.root / out
    out.parent.mkdir(parents=True, exist_ok=True)

    # Türkçe glifler: gömülü Helvetica ğ/ş/ı bilmiyor. Windows'ta Segoe UI
    # her makinede var; bulunamazsa Helvetica'ya düşülür (harf kaybıyla).
    body_font = "Helvetica"
    for label, file in (("Govde", "C:/Windows/Fonts/segoeui.ttf"),):
        try:
            pdfmetrics.registerFont(TTFont(label, file))
            body_font = label
        except Exception:
            pass

    head = ParagraphStyle("h", fontName=body_font, fontSize=16, leading=20,
                          spaceBefore=14, spaceAfter=6)
    normal = ParagraphStyle("n", fontName=body_font, fontSize=10.5,
                            leading=15, spaceAfter=5)
    item = ParagraphStyle("i", parent=normal, leftIndent=12)

    story = [Paragraph(str(args.get("title") or ""), ParagraphStyle(
        "t", fontName=body_font, fontSize=22, leading=27, spaceAfter=14))]
    for line in str(args.get("text") or "").splitlines():
        line = line.rstrip()
        if not line:
            story.append(Spacer(1, 4))
        elif line.startswith("# "):
            story.append(Paragraph(line[2:], head))
        elif line.startswith("- "):
            story.append(Paragraph("•  " + line[2:], item))
        else:
            story.append(Paragraph(line, normal))

    SimpleDocTemplate(str(out), pagesize=A4,
                      leftMargin=18 * mm, rightMargin=18 * mm,
                      topMargin=16 * mm, bottomMargin=16 * mm).build(story)
    return f"PDF yazıldı: {out} ({out.stat().st_size:,} bayt)"
