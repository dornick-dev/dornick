"""Dosyaları zip arşivine paketler.

Standart yetenek — paketle geldi. Değiştirebilir, silebilirsin.
"""

NAME = "arsivle"
DESCRIPTION = """Verilen dosya ve klasörleri tek bir .zip arşivine paketler.
Kullanıcı "sıkıştır", "arşivle", "tek dosya yap", "paylaşılabilir hale
getir" dediğinde kullan. Klasör verilirse içi özyinelemeli girer."""

SCHEMA = {
    "type": "object",
    "properties": {
        "paths": {"type": "array", "items": {"type": "string"},
                  "description": "Paketlenecek dosya/klasör yolları."},
        "out": {"type": "string",
                "description": "Çıktı arşivi (ör. paket.zip)."},
    },
    "required": ["paths", "out"],
}


def run(args, ctx):
    import zipfile
    from pathlib import Path

    out = Path(str(args.get("out") or "paket.zip"))
    if not out.is_absolute():
        out = ctx.sandbox.root / out
    out.parent.mkdir(parents=True, exist_ok=True)

    count = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as pack:
        for raw in args.get("paths") or []:
            spot = Path(str(raw))
            if not spot.is_absolute():
                spot = ctx.sandbox.root / spot
            if spot.is_file():
                pack.write(spot, spot.name)
                count += 1
            elif spot.is_dir():
                for inner in sorted(spot.rglob("*")):
                    if inner.is_file():
                        pack.write(inner, str(inner.relative_to(spot.parent)))
                        count += 1
            else:
                return f"Yol bulunamadı: {spot}"
    return f"Arşiv yazıldı: {out} ({count} dosya, {out.stat().st_size:,} bayt)"
