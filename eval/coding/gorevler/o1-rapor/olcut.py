"""o1 — orta/Python: CSV → rapor + CLI.

Doğru cevap puanlayıcının kendi hesabı: gerçek, ajanın çıktısından değil
görevin DONMUŞ tohum CSV'sinden türetiliyor. Ajan dosyayı bozduysa sayılar
tutmaz — ve tutmaması doğrudur.

Biçim şart koşulmuyor: "47.553,25" da "47553.25" da kabul. Ölçtüğümüz şey
rakamın doğruluğu; ondalık ayracı tercih meselesi. Şart koştuğumuz tek şey
sıra: en çok ciro yapan üç ürün çoktan aza dizilmiş olmalı.
"""

from __future__ import annotations

import collections
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import puanla  # noqa: E402
from puanla import Eksen, Sayac  # noqa: E402

BASLIK = "CSV satış raporu + CLI"
ZORLUK = "orta"
DIL = "python"
KRITIK = ("rapor", "ciro", "ay")
TOHUM_CSV = Path(__file__).resolve().parent / "tohum" / "satislar.csv"
SECILI_AY = "2026-03"


def gercek() -> dict[str, object]:
    """Donmuş tohumdan hesaplanan doğru cevap."""
    ay_ciro: collections.Counter[str] = collections.Counter()
    urun_ciro: collections.Counter[str] = collections.Counter()
    ay_urun: dict[str, collections.Counter[str]] = collections.defaultdict(
        collections.Counter)
    with TOHUM_CSV.open(encoding="utf-8", newline="") as fh:
        for satir in csv.DictReader(fh):
            tutar = int(satir["adet"]) * float(satir["birim_fiyat"])
            ay = satir["tarih"][:7]
            ay_ciro[ay] += tutar
            urun_ciro[satir["urun"]] += tutar
            ay_urun[ay][satir["urun"]] += tutar
    return {
        "ay_ciro": {a: round(v, 2) for a, v in ay_ciro.items()},
        "top3": [u for u, _ in urun_ciro.most_common(3)],
        "ay_top3": [u for u, _ in ay_urun[SECILI_AY].most_common(3)],
        "ay_toplam": {a: round(v, 2) for a, v in ay_ciro.items()},
    }


def olc(kok: Path) -> list[Eksen]:
    arac = puanla.bul(kok, "rapor.py")
    csv_yol = puanla.bul(kok, "satislar.csv")
    d = gercek()

    c = Sayac()
    tam: puanla.Kosum | None = None
    ayli: puanla.Kosum | None = None
    if arac is None:
        for ad, ag in (("rapor.py var", 8), ("csv ile koşuyor", 16),
                       ("çıktı boş değil", 8), ("--ay koşuyor", 8)):
            c.madde(ad, ag, False, "rapor.py bulunamadı")
    else:
        c.madde("rapor.py var", 8, True, str(arac.relative_to(kok)))
        arg = str(csv_yol) if csv_yol else "satislar.csv"
        tam = puanla.kabuk([sys.executable, arac.name, arg],
                           cwd=arac.parent, zaman_asimi=90)
        c.madde("csv ile koşuyor", 16, tam.tamam,
                f"çıkış {tam.kod}; {tam.ozet(160)}")
        c.madde("çıktı boş değil", 8, len(tam.cikti.strip()) > 20,
                f"{len(tam.cikti.strip())} karakter")
        ayli = puanla.kabuk([sys.executable, arac.name, arg, "--ay", SECILI_AY],
                            cwd=arac.parent, zaman_asimi=90)
        c.madde("--ay koşuyor", 8, ayli.tamam, f"çıkış {ayli.kod}; {ayli.ozet(120)}")
    calisir = c.eksen("calisir", 40)

    k = Sayac()
    tam_metin = tam.hepsi if tam else ""
    ay_ciro: dict[str, float] = d["ay_ciro"]  # type: ignore[assignment]
    tutan = [a for a, v in ay_ciro.items() if puanla.sayi_var(tam_metin, v, 0.02)]
    k.oranli("aylık cirolar doğru", 10, len(tutan) / max(1, len(ay_ciro)),
             f"{len(tutan)}/{len(ay_ciro)} ay tuttu: {', '.join(sorted(tutan)) or 'hiçbiri'}")

    top3: list[str] = d["top3"]  # type: ignore[assignment]
    hepsi_var = all(u.casefold() in tam_metin.casefold() for u in top3)
    sirali = puanla.sira_var(tam_metin, top3)
    k.madde("en çok ciro yapan 3 ürün var", 5, hepsi_var, ", ".join(top3))
    k.madde("üçü çoktan aza sıralı", 5, hepsi_var and sirali,
            "sıra tuttu" if sirali else "sıra tutmadı ya da ürün eksik")

    ay_metin = ayli.hepsi if ayli else ""
    secilen_dogru = puanla.sayi_var(ay_metin, ay_ciro.get(SECILI_AY, -1), 0.02)
    digerleri = [a for a in ay_ciro if a != SECILI_AY]
    sizinti = [a for a in digerleri if puanla.sayi_var(ay_metin, ay_ciro[a], 0.02)]
    k.madde(f"--ay {SECILI_AY} doğru ayı veriyor", 3, secilen_dogru,
            f"beklenen {ay_ciro.get(SECILI_AY)}")
    # Süzme puanı ancak doğru ay GELDİYSE verilir: hiç çıktı üretmeyen bir
    # araç "diğer ayları süzmüş" sayılmaz — bedava puan olurdu.
    k.madde("--ay diğer ayları süzüyor", 2, secilen_dogru and not sizinti,
            "doğru ay hiç gelmedi" if not secilen_dogru
            else (f"sızan ay: {', '.join(sizinti)}" if sizinti else "temiz"))
    kapsam = k.eksen("kapsam", 25)

    return [calisir, kapsam, puanla.saglik_ekseni(kok),
            puanla.test_ekseni(kok, kritik=KRITIK, harici=True)]


if __name__ == "__main__":
    raise SystemExit(puanla.tek_basina(olc, "o1-rapor"))
