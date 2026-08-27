"""k1 — kolay/Python: bir modül + testleri.

Ölçmesi kolay olsun diye seçildi: TCKN doğrulaması kapalı formda, tek doğru
cevabı var ve puanlayıcı doğruyu KENDİ hesaplıyor — ajanın çıktısına bakıp
"herhalde doğrudur" demiyor.

Ajanın modülü nereye koyduğunu aramakla buluyoruz (kök ya da bir alt klasör);
yer disiplini bu görevin ölçtüğü şey değil.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import puanla  # noqa: E402
from puanla import Eksen, Sayac  # noqa: E402

BASLIK = "TCKN doğrulama modülü + testleri"
ZORLUK = "kolay"
DIL = "python"
KRITIK = ("dogrula",)


def _tckn(dokuz: str) -> str:
    """Puanlayıcının kendi doğrusu: dokuz haneden geçerli bir TCKN üretir."""
    d = [int(c) for c in dokuz]
    tek = d[0] + d[2] + d[4] + d[6] + d[8]
    cift = d[1] + d[3] + d[5] + d[7]
    onuncu = (tek * 7 - cift) % 10
    onbirinci = (sum(d) + onuncu) % 10
    return dokuz + str(onuncu) + str(onbirinci)


# Donmuş örnekler: sayılar burada üretiliyor ama üreteç sabit, sonuç sabit.
GECERLI = [_tckn(s) for s in ("123456789", "987654321", "100000001",
                              "555555555", "246813579")]
GECERSIZ = [
    "12345678901",     # sağlama tutmuyor
    "01234567890",     # sıfırla başlıyor
    "1234567890",      # 10 hane
    "123456789012",    # 12 hane
    "1234567890a",     # harf var
    "",                # boş
]
# Fonksiyonun patlamaması gereken çöp girdiler.
COP = ["None", "12 34 567 8901", "  ", "abcdefghijk"]


_KOSUM = r"""
import json, sys
sys.path.insert(0, {klasor!r})
import tckn
gecerli = {gecerli!r}
gecersiz = {gecersiz!r}
cop = {cop!r}
rapor = {{"import": True, "gecerli": [], "gecersiz": [], "cop": [], "patlak": []}}
for no in gecerli:
    try:
        rapor["gecerli"].append(bool(tckn.dogrula(no)))
    except Exception as e:
        rapor["gecerli"].append(None); rapor["patlak"].append(f"{{no}}: {{e!r}}")
for no in gecersiz:
    try:
        rapor["gecersiz"].append(bool(tckn.dogrula(no)))
    except Exception as e:
        rapor["gecersiz"].append(None); rapor["patlak"].append(f"{{no}}: {{e!r}}")
for ham in cop:
    deger = None if ham == "None" else ham
    try:
        rapor["cop"].append(bool(tckn.dogrula(deger)))
    except Exception as e:
        rapor["cop"].append(None); rapor["patlak"].append(f"{{ham}}: {{e!r}}")
print("###" + json.dumps(rapor))
"""


def _kosum_yap(klasor: Path) -> puanla.Kosum:
    betik = _KOSUM.format(klasor=str(klasor), gecerli=GECERLI,
                          gecersiz=GECERSIZ, cop=COP)
    return puanla.kabuk([sys.executable, "-c", betik], cwd=klasor, zaman_asimi=60)


def _rapor(k: puanla.Kosum) -> dict | None:
    for satir in k.hepsi.splitlines():
        if satir.startswith("###"):
            try:
                return json.loads(satir[3:])
            except ValueError:
                return None
    return None


def olc(kok: Path) -> list[Eksen]:
    modul = puanla.bul(kok, "tckn.py")

    # -- ÇALIŞIR MI --------------------------------------------------
    c = Sayac()
    rapor = None
    if modul is None:
        c.madde("tckn.py var", 10, False, "atölyede bulunamadı")
        c.madde("modül import ediliyor", 15, False, "dosya yok")
        c.madde("dogrula() çağrılabiliyor", 15, False, "dosya yok")
    else:
        c.madde("tckn.py var", 10, True, str(modul.relative_to(kok)))
        kosum = _kosum_yap(modul.parent)
        rapor = _rapor(kosum)
        c.madde("modül import ediliyor", 15, rapor is not None,
                "tamam" if rapor else kosum.ozet(160))
        if rapor is None:
            c.madde("dogrula() çağrılabiliyor", 15, False, "import olmadı")
        else:
            hic_patlamadi = not rapor["patlak"]
            calisti = any(v is not None for v in rapor["gecerli"])
            c.madde("dogrula() çağrılabiliyor", 15, calisti and hic_patlamadi,
                    "; ".join(rapor["patlak"][:2]) if rapor["patlak"] else "tamam")
    calisir = c.eksen("calisir", 40)

    # -- İSTENEN KAPSAM ----------------------------------------------
    k = Sayac()
    if rapor is None:
        k.madde("geçerli numaralara True", 10, False, "modül koşmadı")
        k.madde("geçersiz numaralara False", 10, False, "modül koşmadı")
        k.madde("çöp girdide patlamıyor", 5, False, "modül koşmadı")
    else:
        dogru_g = sum(1 for v in rapor["gecerli"] if v is True)
        k.oranli("geçerli numaralara True", 10, dogru_g / len(GECERLI),
                 f"{dogru_g}/{len(GECERLI)}")
        dogru_h = sum(1 for v in rapor["gecersiz"] if v is False)
        k.oranli("geçersiz numaralara False", 10, dogru_h / len(GECERSIZ),
                 f"{dogru_h}/{len(GECERSIZ)}")
        # İki ayrı şey iki ayrı madde: patlamamak yetmiyor, çöp girdinin
        # doğru cevabı False. (Yoksa `return True` diyen bir kabuk bu
        # maddeyi tam alıyordu.)
        patlamadi = sum(1 for v in rapor["cop"] if v is not None)
        k.oranli("çöp girdide patlamıyor", 2, patlamadi / len(COP),
                 f"{patlamadi}/{len(COP)} girdi istisna atmadı")
        cop_dogru = sum(1 for v in rapor["cop"] if v is False)
        k.oranli("çöp girdiye False diyor", 3, cop_dogru / len(COP),
                 f"{cop_dogru}/{len(COP)}")
    kapsam = k.eksen("kapsam", 25)

    return [calisir, kapsam, puanla.saglik_ekseni(kok),
            puanla.test_ekseni(kok, kritik=KRITIK)]


if __name__ == "__main__":
    raise SystemExit(puanla.tek_basina(olc, "k1-modul"))
