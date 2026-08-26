"""Ekrana çizme.

Bazı cevaplar yazıyla anlatılınca kaybolur. "Depo seviyesi %62" bir sayı;
depo silueti üzerinde duran bir çizgi ise bir bakışta okunuyor. Harita,
yerleşim, karşılaştırma, zaman çizelgesi — hepsi böyle.

Sayfayı ajan kendi yazıyor. Bu bir şablon kütüphanesi değil: elli hazır
grafik türü tanımlayıp "şunlardan birini seç" demek, tam da istenen şeyi
—- o işe özel bir çizim— engelliyor. Ajan HTML/SVG yazabiliyor; burada
yapılan şey ona bir yüzey ve bir çerçeve vermek.

Güvenlik iki katmanlı:

    burada    sayfa katı bir CSP ile sarılıyor: hiçbir ağ isteği yok, dış
              kaynak yok. Yalnızca satır içi biçem, satır içi betik ve
              gömülü (data:) görsel.
    arayüzde  yalıtılmış çerçevede açılıyor (`sandbox="allow-scripts"`,
              `allow-same-origin` yok): sayfa programın DOM'una, çerezine
              ve `/api` uçlarına erişemiyor.

İkisi de gerekli. Ajanın yazdığı bir betiğin kendi izin kapısını atlaması,
bu programda en pahalı hata olurdu.
"""

from __future__ import annotations

import re
from pathlib import Path

# Atölye içinde çizimlerin durduğu klasör.
FOLDER = "gorseller"

# Dosya adı: başlıktan türetiliyor ama başlık serbest metin, dosya adı değil.
_SLUG = re.compile(r"[^a-z0-9]+")

_TR = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")

# Sayfanın çerçevesi. `default-src 'none'` her şeyi kapatıyor; sonra tek
# tek yalnızca gerekenler açılıyor. Dış bir yazı tipi, bir CDN betiği ya
# da bir izleyici piksel hiçbir koşulda yüklenmiyor.
SHELL = """<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; \
style-src 'unsafe-inline'; script-src 'unsafe-inline'; img-src data:; font-src data:">
<title>{title}</title>
<style>
  /* Programın kendi paleti: çizim arayüzün içinde duruyor, üstünde
     yüzen yabancı bir beyaz sayfa gibi değil. */
  :root {{
    --bg: #050a0f; --ink: #dceefc; --dim: #7fa0c0; --faint: #4b6684;
    --cyan: #4fe3ff; --mint: #5ce6a4; --amber: #ffc857; --rose: #ff7a90;
    --violet: #b39cff; --line: #4fe3ff22;
  }}
  * {{ box-sizing: border-box; }}
  html, body {{ margin: 0; height: 100%; }}
  body {{
    background: var(--bg); color: var(--ink);
    font: 14px/1.6 "Segoe UI Variable Text", -apple-system, system-ui, sans-serif;
    padding: 18px;
  }}
  h1, h2, h3 {{ font-weight: 300; letter-spacing: .01em; margin: 0 0 12px; }}
  h1 {{ font-size: 20px; }}
  svg {{ max-width: 100%; height: auto; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th, td {{ padding: 6px 10px; text-align: left; border-bottom: 1px solid var(--line); }}
  th {{ font: 10.5px "Cascadia Code", ui-monospace, monospace;
        letter-spacing: .16em; text-transform: uppercase; color: var(--cyan); }}
  .dim {{ color: var(--dim); }}
  .faint {{ color: var(--faint); }}
</style>
</head>
<body>
{body}
</body>
</html>
"""


def folder(sandbox_root: Path) -> Path:
    return Path(sandbox_root) / FOLDER


def slug(title: str, fallback: str = "cizim") -> str:
    """Başlıktan dosya adı. Türkçe harfler sadeleşiyor, gerisi tireleniyor."""
    plain = (title or "").translate(_TR).lower()
    name = _SLUG.sub("-", plain).strip("-")
    return (name or fallback)[:48]


def wrap(title: str, body: str) -> str:
    """Ajanın yazdığı gövdeyi çerçeveye oturtur.

    Ajan tam bir belge yazdıysa (`<!DOCTYPE` ya da `<html` ile başlıyorsa)
    dokunulmuyor: kendi çerçevesini kurmuş demektir. O durumda CSP'yi de
    kendi yazmadıysa eklenmiyor — bunu zorlamak, çalışan bir sayfayı
    sessizce bozar. Yalıtılmış çerçeve zaten ikinci katman.
    """
    text = (body or "").strip()
    if text[:200].lstrip().lower().startswith(("<!doctype", "<html")):
        return text
    return SHELL.format(title=_escape(title or "çizim"), body=text)


def _escape(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;")
                .replace(">", "&gt;").replace('"', "&quot;"))


def save(sandbox_root: Path, title: str, body: str) -> Path:
    """Çizimi atölyeye yazar ve yolunu döndürür."""
    root = folder(sandbox_root)
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{slug(title)}.html"
    path.write_text(wrap(title, body), encoding="utf-8")
    return path
