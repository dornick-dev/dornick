"""z3 — zor/Python: tohum projede 3 gizli hatayı bulup düzeltme.

Tohumdaki üç hata:
  1. `ekle` var olan ürünün adedini TOPLAMAK yerine üstüne yazıyor.
  2. `indirim_orani` sınırı dışlıyor (`>` yerine `>=` olmalı) — tam 1000 TL
     harcayan %5 alıyor.
  3. `toplam` kuruşu yuvarlıyor (`round(net)` yerine `round(net, 2)`).

Puanlayıcı iki ayrı iş yapıyor ve ikisi de kaçamağa kapalı:

  * **Regresyon:** atölyenin kopyasında `test_regresyon.py`'nin TOHUMDAKİ
    hali üstüne yazılıp koşuluyor. Testi gevşetmek burada işe yaramaz.
  * **Gizli vakalar:** her hata, testte HİÇ GEÇMEYEN sayılarla ayrıca
    sınanıyor. Görünen testin beklediği değeri koda gömerek geçmek de işe
    yaramaz.
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import puanla  # noqa: E402
from puanla import Eksen, Sayac  # noqa: E402

BASLIK = "Sepet modülündeki 3 gizli hatayı bul ve düzelt"
ZORLUK = "zor"
DIL = "python"
KRITIK = ("ekle", "indirim_orani", "toplam")
TOHUM_TEST = (Path(__file__).resolve().parent / "tohum" / "sepet"
              / "test_regresyon.py")

# Gizli vakalar: görünen testte geçmeyen sayılar.
_KOSUM = r"""
import json, sys
sys.path.insert(0, {klasor!r})
import sepet as m
r = {{}}
def dene(ad, fn):
    try: r[ad] = {{"ok": True, "deger": fn()}}
    except Exception as e: r[ad] = {{"ok": False, "hata": repr(e)}}

def uc_kez():
    s = {{}}
    m.ekle(s, "conta", 3.0, 1); m.ekle(s, "conta", 3.0, 2); m.ekle(s, "conta", 3.0, 4)
    return [m.kalem_sayisi(s), m.ara_toplam(s)]
dene("ekle_birikiyor", uc_kez)

dene("sinir_500", lambda: m.indirim_orani(500.0))
dene("sinir_1000", lambda: m.indirim_orani(1000.0))
dene("sinir_499", lambda: m.indirim_orani(499.99))

def bin_bes_yuz():
    s = {{}}; m.ekle(s, "pompa", 750.0, 2); return m.toplam(s)
dene("indirim_yuzde_on", bin_bes_yuz)

def kurus():
    s = {{}}; m.ekle(s, "vida", 14.29, 7); return m.toplam(s)
dene("kurus_korunuyor", kurus)

def tam_500():
    s = {{}}; m.ekle(s, "role", 250.0, 2); return m.toplam(s)
dene("tam_500_indirimli", tam_500)

def negatif():
    try:
        m.ekle({{}}, "x", 5.0, 0); return "PATLAMADI"
    except ValueError:
        return "ValueError"
dene("koruma_duruyor", negatif)

print("###" + json.dumps(r))
"""


def _gizli(klasor: Path) -> dict | None:
    k = puanla.kabuk([sys.executable, "-c", _KOSUM.format(klasor=str(klasor))],
                     cwd=klasor, zaman_asimi=60)
    for satir in k.hepsi.splitlines():
        if satir.startswith("###"):
            try:
                return json.loads(satir[3:])
            except ValueError:
                return None
    return None


def _regresyon(kok: Path) -> puanla.Kosum | None:
    """Atölyenin kopyasında, tohumdaki BOZULMAMIŞ regresyon takımını koşturur."""
    with tempfile.TemporaryDirectory(prefix="neocp-z3-reg-") as tmp:
        hedef = Path(tmp) / "atolye"
        try:
            shutil.copytree(kok, hedef,
                            ignore=shutil.ignore_patterns(*puanla.ATLA_KLASOR))
        except OSError:
            return None
        kopya = puanla.bul(hedef, "sepet.py")
        if kopya is None:
            return None
        shutil.copyfile(TOHUM_TEST, kopya.parent / "test_regresyon.py")
        return puanla.kabuk(
            [sys.executable, "-m", "pytest", "-q", "--no-header",
             "-p", "no:cacheprovider", "test_regresyon.py"],
            cwd=kopya.parent, zaman_asimi=180)


def olc(kok: Path) -> list[Eksen]:
    modul = puanla.bul(kok, "sepet.py")

    c = Sayac()
    gizli: dict | None = None
    if modul is None:
        for ad, ag in (("sepet.py duruyor", 6), ("modül import ediliyor", 10),
                       ("bozulmamış regresyon takımı koşuyor", 8),
                       ("regresyon takımı tamamen yeşil", 16)):
            c.madde(ad, ag, False, "sepet.py bulunamadı")
    else:
        c.madde("sepet.py duruyor", 6, True, str(modul.relative_to(kok)))
        gizli = _gizli(modul.parent)
        c.madde("modül import ediliyor", 10, gizli is not None,
                "tamam" if gizli else "import patladı")
        reg = _regresyon(kok)
        if reg is None or reg.kod is None:
            c.atla("bozulmamış regresyon takımı koşuyor",
                   reg.patlama if reg else "regresyon kopyası kurulamadı")
            c.atla("regresyon takımı tamamen yeşil", "takım koşturulamadı")
        else:
            c.madde("bozulmamış regresyon takımı koşuyor", 8,
                    "passed" in reg.hepsi or "failed" in reg.hepsi,
                    reg.ozet(120))
            c.madde("regresyon takımı tamamen yeşil", 16, reg.tamam,
                    reg.ozet(200))
    calisir = c.eksen("calisir", 40)

    # -- gizli vakalar: her hata ayrı ayrı ---------------------------
    k = Sayac()
    a = gizli or {}

    def deger(ad: str):
        d = a.get(ad)
        return d.get("deger") if d and d.get("ok") else None

    birikim = deger("ekle_birikiyor")
    k.madde("hata 1: aynı ürün eklenince adet birikiyor", 8,
            birikim == [7, 21.0],
            f"beklenen [7, 21.0], çıkan {birikim!r}")

    sinirlar = (deger("sinir_500"), deger("sinir_1000"), deger("sinir_499"))
    dogru_sinir = (sinirlar[0] == 0.05 and sinirlar[1] == 0.10
                   and sinirlar[2] == 0.0)
    k.madde("hata 2: indirim sınırları dahil", 8, dogru_sinir,
            f"500→{sinirlar[0]!r} (0.05), 1000→{sinirlar[1]!r} (0.10), "
            f"499.99→{sinirlar[2]!r} (0.0)")

    kurus = deger("kurus_korunuyor")
    k.madde("hata 3: toplam kuruşu koruyor", 6,
            kurus is not None and abs(float(kurus) - 100.03) < 0.005,
            f"7 × 14.29 → beklenen 100.03, çıkan {kurus!r}")

    on = deger("indirim_yuzde_on")
    tam = deger("tam_500_indirimli")
    k.madde("gizli vaka: 1500 → %10, 500 → %5", 2,
            on is not None and abs(float(on) - 1350.0) < 0.005
            and tam is not None and abs(float(tam) - 475.0) < 0.005,
            f"1500→{on!r} (1350.0), 500→{tam!r} (475.0)")

    k.madde("var olan koruma sökülmemiş (adet 0 → ValueError)", 1,
            deger("koruma_duruyor") == "ValueError",
            str(a.get("koruma_duruyor", "adım koşmadı"))[:100])
    kapsam = k.eksen("kapsam", 25)

    test_e = puanla.test_ekseni(kok, kritik=KRITIK, harici=True)
    test_e.kanit.insert(0, "! regresyon takımı tohumla geliyor — bu eksen "
                           "ajanın kendi katkısını ayıramaz, puana katılmıyor")

    return [calisir, kapsam, puanla.saglik_ekseni(kok), test_e]


if __name__ == "__main__":
    raise SystemExit(puanla.tek_basina(olc, "z3-gizli-hata"))
