"""neo'nun logosu — tek kaynak.

Minimalist bir işaret: parlayan çekirdek + ince yörünge yayı. Sahnedeki
holografik çekirdeğin ve üst şeritteki marka noktasının damıtılmış hali;
pencere simgesi, görev çubuğu, tepsi ve sekme hepsinde AYNI çizim kullanılır.

Vektör dosyası yerine kodla çiziliyor: paketlenmiş uygulamada en sık kırılan
şey varlık yolu — çizim koddaysa simge asla boş kalmaz. PIL tepsi için zaten
gerekli; yoksa çağıran taraf sessizce vazgeçiyor.
"""

from __future__ import annotations

from pathlib import Path

# Marka renkleri (app.css'teki --cyan ailesiyle aynı).
_CORE_IN = (234, 252, 255)     # merkez: buza yakın beyaz
_CORE_MID = (79, 227, 255)     # cyan
_CORE_OUT = (18, 116, 156)     # derin petrol — açık zeminde de okunsun
_RING = (79, 227, 255)


def draw(size: int):
    """size×size şeffaf zeminde logo (PIL Image).

    4× süperörnekleyip küçültüyoruz: 16px'te bile kenarlar temiz kalsın.
    """
    from PIL import Image, ImageDraw

    s = size * 4
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c = s / 2

    # Yörünge yayı: 300°'lik ince halka, boşluğu sağ üstte — sahnedeki
    # halkaların "hep dönen, hiç kapanmayan" hissi.
    ring_r = s * 0.435
    ring_w = max(2, int(s * 0.055))
    box = (c - ring_r, c - ring_r, c + ring_r, c + ring_r)
    d.arc(box, start=-40, end=230, fill=(*_RING, 255), width=ring_w)

    # Çekirdek: radyal gradyan disk (eşmerkezli halkalarla).
    core_r = s * 0.26
    steps = 120
    for i in range(steps, 0, -1):
        t = i / steps            # 1 = dış kenar, 0 = merkez
        r = core_r * t
        if t > 0.55:             # dış: cyan → petrol
            k = (t - 0.55) / 0.45
            col = tuple(int(_CORE_MID[j] + (_CORE_OUT[j] - _CORE_MID[j]) * k) for j in range(3))
        else:                    # iç: beyaz → cyan
            k = t / 0.55
            col = tuple(int(_CORE_IN[j] + (_CORE_MID[j] - _CORE_IN[j]) * k) for j in range(3))
        d.ellipse((c - r, c - r, c + r, c + r), fill=(*col, 255))

    return img.resize((size, size), Image.LANCZOS)


def ensure_ico(path: Path) -> bool:
    """Çok boyutlu .ico dosyasını (yoksa) üretir. Başarı durumunu döndürür."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            return True
        base = draw(256)
        base.save(path, format="ICO",
                  sizes=[(16, 16), (20, 20), (24, 24), (32, 32),
                         (40, 40), (48, 48), (64, 64), (128, 128), (256, 256)])
        return True
    except Exception:
        return False


def ico_path() -> Path:
    """Paket içindeki simge yolu (gerekiyorsa üretir)."""
    path = Path(__file__).parent / "assets" / "neo.ico"
    ensure_ico(path)
    return path
