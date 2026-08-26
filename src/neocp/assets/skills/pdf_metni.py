"""PDF'ten metin çıkarır.

Standart yetenek — paketle geldi. Değiştirebilir, silebilirsin.
"""

NAME = "pdf_metni"
DESCRIPTION = """Bir PDF dosyasının metnini çıkarır. Kullanıcı bir PDF'ten
bahsettiğinde ya da bir rapor/şartname okunacaksa bunu kullan. Sayfa aralığı
verilebilir; uzun belgelerde önce ilk sayfalara bak."""

SCHEMA = {
    "type": "object",
    "properties": {
        "path": {"type": "string", "description": "PDF dosyasının yolu."},
        "first": {"type": "integer", "description": "Başlangıç sayfası (1'den, varsayılan 1)."},
        "last": {"type": "integer", "description": "Son sayfa (varsayılan: ilk 10 sayfa)."},
    },
    "required": ["path"],
}


def run(args, ctx):
    from pathlib import Path

    try:
        from pypdf import PdfReader
    except ImportError:
        return (
            "PDF okumak için `pypdf` gerekli. Kabukta `py -m pip install pypdf` "
            "çalıştırıp yeniden dene."
        )

    path = Path(str(args.get("path") or "")).expanduser()
    if not path.is_absolute():
        path = ctx.sandbox.root / path
    if not path.is_file():
        return f"Dosya yok: {path}"

    reader = PdfReader(str(path))
    total = len(reader.pages)
    first = max(1, int(args.get("first") or 1))
    last = min(total, int(args.get("last") or min(total, first + 9)))
    if first > total:
        return f"Belge {total} sayfa; {first}. sayfa yok."

    parts = [f"{path.name}: {total} sayfa. Gösterilen: {first}-{last}."]
    for number in range(first, last + 1):
        text = (reader.pages[number - 1].extract_text() or "").strip()
        parts.append(f"--- sayfa {number} ---\n{text or '(metin çıkarılamadı)'}")
    return "\n".join(parts)
