"""Görseli yeniden boyutlandırır / biçim değiştirir.

Standart yetenek — paketle geldi. Değiştirebilir, silebilirsin.
"""

NAME = "resim_boyutlandir"
DESCRIPTION = """Bir görseli yeniden boyutlandırır ve istenirse biçimini
değiştirir (png/jpg/webp). Kullanıcı "küçült", "boyutlandır", "jpg yap",
"web için hafiflet" dediğinde kullan. En-boy oranı korunur."""

SCHEMA = {
    "type": "object",
    "properties": {
        "path": {"type": "string", "description": "Kaynak görsel."},
        "out": {"type": "string",
                "description": "Çıktı yolu; uzantısı biçimi belirler (boşsa üstüne _kucuk eklenir)."},
        "max_edge": {"type": "integer",
                     "description": "Uzun kenarın azami pikseli (varsayılan 1280)."},
        "quality": {"type": "integer",
                    "description": "JPEG/WebP kalitesi 1-100 (varsayılan 82)."},
    },
    "required": ["path"],
}


def run(args, ctx):
    from pathlib import Path

    try:
        from PIL import Image
    except ImportError:
        return ("Görsel işlemek için `Pillow` gerekli. Kabukta "
                "`py -m pip install Pillow` çalıştırıp yeniden dene.")

    src = Path(str(args.get("path") or ""))
    if not src.is_absolute():
        src = ctx.sandbox.root / src
    if not src.is_file():
        return f"Görsel bulunamadı: {src}"

    out_raw = str(args.get("out") or "")
    out = Path(out_raw) if out_raw else src.with_stem(src.stem + "_kucuk")
    if not out.is_absolute():
        out = ctx.sandbox.root / out
    out.parent.mkdir(parents=True, exist_ok=True)

    edge = max(16, min(int(args.get("max_edge") or 1280), 8000))
    quality = max(1, min(int(args.get("quality") or 82), 100))

    with Image.open(src) as picture:
        picture.thumbnail((edge, edge))
        # JPEG şeffaflık taşıyamaz; RGBA'yı beyaz zemine indiriyoruz.
        if out.suffix.lower() in (".jpg", ".jpeg") and picture.mode in ("RGBA", "P"):
            from PIL import Image as I
            flat = I.new("RGB", picture.size, (255, 255, 255))
            flat.paste(picture.convert("RGBA"), mask=picture.convert("RGBA").split()[-1])
            picture = flat
        picture.save(out, quality=quality)
        size = picture.size

    return f"Yazıldı: {out} ({size[0]}×{size[1]}, {out.stat().st_size:,} bayt)"
