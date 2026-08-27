"""k2 — kolay/Node: bir CLI aracı.

Bir CLI'ın "çalışıyor" olması dört şey demek ve dördü de dışarıdan ölçülebilir:
komut kabul ediyor, çıkış kodu doğru, durumu diske yazıyor, bilmediği komutta
sessizce başarı raporlamıyor. Son madde önemli: `exit 0` dönen bir hata,
betikte kullanılan her aracı zehirler.

Kalıcılık AYRI süreçlerle ölçülüyor — aynı süreç içinde bellekte tutmak
"kaybolmasın" isteğini karşılamıyor.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import puanla  # noqa: E402
from puanla import Eksen, Sayac  # noqa: E402

BASLIK = "Node görev listesi CLI"
ZORLUK = "kolay"
DIL = "node"
KRITIK = ("ekle", "liste", "bitir")

BIR = "süt al"
IKI = "faturayı öde"


def olc(kok: Path) -> list[Eksen]:
    betik = puanla.bul(kok, "gorev.js", "gorev.mjs")
    if not puanla.node_var():
        yok = Eksen("calisir", 40, None, [], sebep="makinede node yok")
        return [yok,
                Eksen("kapsam", 25, None, [], sebep="makinede node yok"),
                puanla.saglik_ekseni(kok),
                Eksen("test", 15, None, [], sebep="makinede node yok")]

    c = Sayac()
    if betik is None:
        for ad, ag in (("gorev.js var", 10), ("ekle çalışıyor", 10),
                       ("liste çalışıyor", 10), ("bilinmeyen komut hata veriyor", 10)):
            c.madde(ad, ag, False, "gorev.js bulunamadı")
        kapsam = Sayac()
        for ad, ag in (("eklenenler listede", 10), ("bitir listeyi değiştiriyor", 8),
                       ("gorevler.json'da kalıcı", 7)):
            kapsam.madde(ad, ag, False, "gorev.js bulunamadı")
        return [c.eksen("calisir", 40), kapsam.eksen("kapsam", 25),
                puanla.saglik_ekseni(kok),
                puanla.test_ekseni(kok, kritik=KRITIK, harici=True)]

    yer = betik.parent
    ad = betik.name
    c.madde("gorev.js var", 10, True, str(betik.relative_to(kok)))

    # Temiz sayfa: ajan kendi denemesi için görev eklemiş olabilir ve o
    # artıklar ölçümü okunamaz hale getiriyor. Ölçülen yara: ajanın bıraktığı
    # listede 1. görev ZATEN bitmişti; `bitir 1` hiçbir şeyi değiştirmedi ve
    # çalışan bir özellik "değişmedi" diye puan kaybetti. Kalıcılık bundan
    # sonra bizim eklediklerimizle ölçülüyor — silmek ölçümü zayıflatmıyor.
    onceki_kayit = puanla.bul(kok, "gorevler.json")
    if onceki_kayit is not None:
        try:
            onceki_kayit.unlink()
            c.kanit.append("! ajanın bıraktığı gorevler.json ölçümden önce "
                           "silindi (temiz sayfa)")
        except OSError:
            pass

    ekle1 = puanla.kabuk(["node", ad, "ekle", BIR], cwd=yer, zaman_asimi=45)
    ekle2 = puanla.kabuk(["node", ad, "ekle", IKI], cwd=yer, zaman_asimi=45)
    c.madde("ekle çalışıyor", 10, ekle1.tamam and ekle2.tamam,
            ekle1.ozet(140) if not ekle1.tamam else f"çıkış {ekle1.kod}/{ekle2.kod}")

    liste1 = puanla.kabuk(["node", ad, "liste"], cwd=yer, zaman_asimi=45)
    c.madde("liste çalışıyor", 10, liste1.tamam, liste1.ozet(140))

    sacma = puanla.kabuk(["node", ad, "zıpla"], cwd=yer, zaman_asimi=45)
    c.madde("bilinmeyen komut hata veriyor", 10,
            sacma.kod is not None and sacma.kod != 0,
            f"çıkış kodu {sacma.kod}")
    calisir = c.eksen("calisir", 40)

    # -- kapsam -------------------------------------------------------
    k = Sayac()
    ilk_ciktisi = liste1.hepsi
    k.madde("eklenenler listede görünüyor", 10,
            BIR in ilk_ciktisi and IKI in ilk_ciktisi,
            f"«{BIR}»: {BIR in ilk_ciktisi}, «{IKI}»: {IKI in ilk_ciktisi}")

    bitir = puanla.kabuk(["node", ad, "bitir", "1"], cwd=yer, zaman_asimi=45)
    liste2 = puanla.kabuk(["node", ad, "liste"], cwd=yer, zaman_asimi=45)
    degisti = (bitir.tamam and liste2.tamam
               and liste2.hepsi.strip() != ilk_ciktisi.strip()
               and IKI in liste2.hepsi)
    k.madde("bitir listeyi değiştiriyor (kalan görev duruyor)", 8, degisti,
            "bitir çıkışı " + str(bitir.kod) +
            ("; liste aynı kaldı" if liste2.hepsi.strip() == ilk_ciktisi.strip()
             else "; liste değişti"))

    kayit = puanla.bul(kok, "gorevler.json")
    kalici = False
    detay = "gorevler.json yok"
    if kayit is not None:
        icerik = puanla.oku(kayit)
        kalici = BIR in icerik and IKI in icerik
        detay = f"{kayit.name}, {len(icerik)} karakter"
        try:
            json.loads(icerik)
        except ValueError:
            detay += " (geçerli JSON değil)"
            kalici = False
    k.madde("gorevler.json'da kalıcı", 7, kalici, detay)
    kapsam = k.eksen("kapsam", 25)

    return [calisir, kapsam, puanla.saglik_ekseni(kok),
            # İstem test istemedi: ölçülür, raporlanır, puana katılmaz.
            puanla.test_ekseni(kok, kritik=KRITIK, harici=True)]


if __name__ == "__main__":
    raise SystemExit(puanla.tek_basina(olc, "k2-cli"))
