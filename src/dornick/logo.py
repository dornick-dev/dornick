"""Dornick'in logosu — tek kaynak.

Ocak kimliği: koyu kömür yuvarlak kare üstünde "ağdan örülmüş n" — dört
tebeşir düğüm, kehribar tepe düğümü. Üst şeritteki marka SVG'siyle aynı
işaret; pencere simgesi, görev çubuğu, tepsi ve sekme hepsinde AYNI çizim.

Vektör dosyası yerine kodla çiziliyor: paketlenmiş uygulamada en sık kırılan
şey varlık yolu — çizim koddaysa simge asla boş kalmaz. PIL tepsi için zaten
gerekli; yoksa çağıran taraf sessizce vazgeçiyor.
"""

from __future__ import annotations

from pathlib import Path

# Ocak renkleri (app.css'teki token ailesiyle aynı).
_ZEMIN = (27, 24, 20)          # --panel: koyu kömür
_KENAR = (62, 55, 44)          # ince kenar — koyu görev çubuğunda da seçilsin
_CIZGI = (239, 232, 220)       # tebeşir: n'nin ipliği ve alt düğümler
_TEPE = (240, 160, 32)         # kehribar: tepe düğümü (--cyan)

# İşaretin geometrisi 32'lik ızgarada — index.html'deki marka SVG'siyle
# birebir: ağ örgüsünden bir "d" (düğüm-d). Sap + kase, üç tebeşir boğum
# karesi, tepede kehribar düğüm.
_SAP = ((21.5, 7.0), (21.5, 23.5))
_KASE = (9.7, 13.3, 21.5, 26.3)          # yuvarlak köşeli çerçeve
_KASE_R = 2.8
_BOGUMLAR = [(7.4, 11.2), (7.4, 21.9), (19.3, 24.1)]   # 4.4'lük kareler
_TEPE_NOKTA = (21.5, 5.6, 3.3)           # cx, cy, r

# Çizim değişince paketlerdeki .ico kendini tazelesin: sürüm bekçisi.
_SURUM = "dugum-1"


def draw(size: int):
    """size×size logo (PIL Image): koyu yuvarlak kare + örülmüş n.

    4× süperörnekleyip küçültüyoruz: 16px'te bile kenarlar temiz kalsın.
    """
    from PIL import Image, ImageDraw

    s = size * 4
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    u = s / 32.0                 # 32'lik ızgara → piksel

    # Zemin: yuvarlak kare karo. Şeffaf zemin yerine karo: açık görev
    # çubuğunda da koyu temada da aynı okunur kimlik.
    pay = s * 0.02
    d.rounded_rectangle((pay, pay, s - pay, s - pay), radius=s * 0.21,
                        fill=(*_ZEMIN, 255), outline=(*_KENAR, 255),
                        width=max(1, int(s * 0.012)))

    # d ipliği: sap + yuvarlak köşeli kase (SVG yoluyla aynı ağırlık).
    w = max(2, int(3.6 * u))
    (x1, y1), (x2, y2) = _SAP
    d.line([(x1 * u, y1 * u), (x2 * u, y2 * u)], fill=(*_CIZGI, 255), width=w)
    r = w / 2
    for x, y in _SAP:
        d.ellipse((x * u - r, y * u - r, x * u + r, y * u + r), fill=(*_CIZGI, 255))
    kx1, ky1, kx2, ky2 = (v * u for v in _KASE)
    d.rounded_rectangle((kx1, ky1, kx2, ky2), radius=_KASE_R * u,
                        outline=(*_CIZGI, 255), width=w)

    # Boğum kareleri: tebeşir, yuvarlatılmış.
    for x, y in _BOGUMLAR:
        d.rounded_rectangle((x * u, y * u, (x + 4.4) * u, (y + 4.4) * u),
                            radius=1.2 * u, fill=(*_CIZGI, 255))

    # Tepe düğümü: kehribar.
    cx, cy, cr = _TEPE_NOKTA
    d.ellipse(((cx - cr) * u, (cy - cr) * u, (cx + cr) * u, (cy + cr) * u),
              fill=(*_TEPE, 255))

    return img.resize((size, size), Image.LANCZOS)


def ensure_ico(path: Path) -> bool:
    """Çok boyutlu .ico dosyasını (yoksa) üretir. Başarı durumunu döndürür."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        # Sürüm bekçisi: çizim değiştiyse (ocak göçü gibi) eski .ico
        # sessizce kalmasın — yeniden üret. Yan dosya .ico'nun yanında.
        bekci = path.with_suffix(".ico.surum")
        if path.exists():
            try:
                if bekci.read_text(encoding="utf-8").strip() == _SURUM:
                    return True
            except OSError:
                pass
        base = draw(256)
        base.save(path, format="ICO",
                  sizes=[(16, 16), (20, 20), (24, 24), (32, 32),
                         (40, 40), (48, 48), (64, 64), (128, 128), (256, 256)])
        try:
            bekci.write_text(_SURUM, encoding="utf-8")
        except OSError:
            pass
        return True
    except Exception:
        return False


def ico_path() -> Path:
    """Paket içindeki simge yolu (gerekiyorsa üretir)."""
    path = Path(__file__).parent / "assets" / "dornick.ico"
    ensure_ico(path)
    return path


def ensure_png(path: Path, size: int = 256) -> bool:
    """Windows toast ve sekme için PNG. ICO WinRT src olarak tutulmuyor."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        bekci = path.with_suffix(".png.surum")
        if path.exists():
            try:
                if bekci.read_text(encoding="utf-8").strip() == _SURUM:
                    return True
            except OSError:
                pass
        draw(size).save(path, format="PNG")
        try:
            bekci.write_text(_SURUM, encoding="utf-8")
        except OSError:
            pass
        return True
    except Exception:
        return False


def png_path(size: int = 256) -> Path:
    """Paket içindeki PNG yolu (gerekiyorsa üretir)."""
    path = Path(__file__).parent / "assets" / "dornick.png"
    ensure_png(path, size)
    return path
