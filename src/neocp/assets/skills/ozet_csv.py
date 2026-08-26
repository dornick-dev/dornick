"""CSV/TSV dosyasının hızlı profili.

Standart yetenek — paketle geldi. Değiştirebilir, silebilirsin.
"""

NAME = "ozet_csv"
DESCRIPTION = """Bir CSV ya da TSV dosyasının hızlı özeti: satır ve sütun
sayısı, sütun adları, sayısal sütunların en küçük / en büyük / ortalama
değerleri ve ilk birkaç satır. Kullanıcı bir veri dosyasından bahsettiğinde
dosyayı satır satır okumadan önce buna bak."""

SCHEMA = {
    "type": "object",
    "properties": {
        "path": {"type": "string", "description": "Dosyanın yolu."},
        "rows": {
            "type": "integer",
            "description": "Örnek olarak gösterilecek satır sayısı (varsayılan 5).",
        },
    },
    "required": ["path"],
}


def run(args, ctx):
    import csv
    import statistics
    from pathlib import Path

    path = Path(str(args.get("path") or "")).expanduser()
    if not path.is_absolute():
        path = ctx.sandbox.root / path
    if not path.is_file():
        return f"Dosya yok: {path}"

    sample = max(1, min(int(args.get("rows") or 5), 20))
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    delimiter = "\t" if path.suffix.lower() == ".tsv" or "\t" in text[:2000] else ","

    reader = csv.reader(text.splitlines(), delimiter=delimiter)
    rows = [row for row in reader if row]
    if not rows:
        return "Dosya boş."

    header, body = rows[0], rows[1:]
    lines = [
        f"{path.name}: {len(body)} satır, {len(header)} sütun.",
        "Sütunlar: " + ", ".join(header),
    ]

    for index, name in enumerate(header):
        values = []
        for row in body:
            if index >= len(row):
                continue
            try:
                values.append(float(row[index].replace(",", ".")))
            except ValueError:
                break
        # Sütunun tamamı sayı değilse özetlenmez; yarım özet yanıltıcı.
        if values and len(values) == sum(1 for r in body if index < len(r) and r[index].strip()):
            lines.append(
                f"  {name}: min {min(values):g}, max {max(values):g}, "
                f"ort {statistics.fmean(values):g}"
            )

    lines.append(f"İlk {min(sample, len(body))} satır:")
    for row in body[:sample]:
        lines.append("  " + " | ".join(row))
    return "\n".join(lines)
