"""k3 — kolay/PHP: verilen bozuk dosyada hatayı bulup düzeltme.

Tohumda iki hata var ve ikisi de kullanıcının gördüğü tek yanlış sayıya
katkı veriyor:
  * `kdv_ekle` oranı ÇARPMAK yerine TOPLUYOR (70 + 18 = 88 yerine 70 × 1.18)
  * `fatura_toplami` döngüsü `count($satirlar) - 1` ile SON KALEMİ atlıyor

İkincisi sinsi: ilk hatayı düzeltip "82.60'a yaklaştım" diyerek durmak
mümkün. O yüzden puanlayıcının vakaları ikisini AYRI AYRI yakalıyor —
tek kalemli vaka yalnız döngü hatasına, farklı oranlı vaka yalnız KDV
hatasına duyarlı.

Puanlayıcı ajanın yazdığı hiçbir dosyayı çağırmıyor: kendi koşum betiğini
kendi geçici klasörüne yazıp `fatura.php`'yi require ediyor.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import puanla  # noqa: E402
from puanla import Eksen, Sayac  # noqa: E402

BASLIK = "PHP fatura hesabındaki hatayı bul ve düzelt"
ZORLUK = "kolay"
DIL = "php"
KRITIK = ("fatura_toplami", "kdv_ekle")

# (ad, kalemler, oran, beklenen)
VAKALAR = [
    ("üç kalem %18", [(2, 10.0), (1, 30.0), (4, 5.0)], 18.0, 82.60),
    ("tek kalem %20", [(3, 7.5)], 20.0, 27.00),
    ("iki kalem %0", [(2, 12.5), (2, 12.5)], 0.0, 50.00),
    ("boş sipariş", [], 18.0, 0.00),
]

_KOSUM = """<?php
require_once %(dosya)s;
// Vakalar JSON metni olarak gömülüyor: PHP dizi sözdizimi JSON nesne
// literalini kabul etmiyor, json_decode tek doğru yol.
$vakalar = json_decode(%(vakalar)s, true);
$cikan = [];
foreach ($vakalar as $v) {
    $satirlar = [];
    foreach ($v['kalemler'] as $k) {
        $satirlar[] = ['adet' => $k[0], 'fiyat' => $k[1]];
    }
    try {
        $cikan[] = fatura_toplami($satirlar, $v['oran']);
    } catch (Throwable $e) {
        $cikan[] = null;
    }
}
echo "###" . json_encode($cikan) . PHP_EOL;
"""


def _koştur(dosya: Path) -> list[float | None] | None:
    vakalar = [{"kalemler": [list(k) for k in kalemler], "oran": oran}
               for _, kalemler, oran, _ in VAKALAR]
    betik = _KOSUM % {
        "dosya": json.dumps(str(dosya)),
        "vakalar": json.dumps(json.dumps(vakalar)),
    }
    with tempfile.TemporaryDirectory(prefix="neocp-k3-") as tmp:
        yol = Path(tmp) / "kosum.php"
        yol.write_text(betik, encoding="utf-8")
        k = puanla.kabuk(["php", str(yol)], cwd=tmp, zaman_asimi=60)
    for satir in k.hepsi.splitlines():
        if satir.startswith("###"):
            try:
                ham = json.loads(satir[3:])
            except ValueError:
                return None
            return [None if v is None else float(v) for v in ham]
    return None


def olc(kok: Path) -> list[Eksen]:
    if not puanla.php_var():
        sebep = "makinede php yok"
        return [Eksen("calisir", 40, None, [], sebep=sebep),
                Eksen("kapsam", 25, None, [], sebep=sebep),
                puanla.saglik_ekseni(kok),
                Eksen("test", 15, None, [], sebep=sebep, harici=True)]

    dosya = puanla.bul(kok, "fatura.php")

    c = Sayac()
    sonuc: list[float | None] | None = None
    if dosya is None:
        c.madde("fatura.php duruyor", 10, False, "atölyede bulunamadı")
        c.madde("php -l temiz", 10, False, "dosya yok")
        c.madde("fonksiyon dışarıdan çağrılabiliyor", 20, False, "dosya yok")
    else:
        c.madde("fatura.php duruyor", 10, True, str(dosya.relative_to(kok)))
        lint = puanla.kabuk(["php", "-l", str(dosya)], zaman_asimi=40)
        c.madde("php -l temiz", 10, lint.tamam, lint.ozet(140))
        sonuc = _koştur(dosya)
        c.madde("fonksiyon dışarıdan çağrılabiliyor", 20,
                sonuc is not None and any(v is not None for v in sonuc),
                "tamam" if sonuc else "require/çağrı başarısız")
    calisir = c.eksen("calisir", 40)

    k = Sayac()
    agirlik = {0: 10.0, 1: 7.0, 2: 5.0, 3: 3.0}
    for i, (ad, _kalemler, _oran, beklenen) in enumerate(VAKALAR):
        alinan = sonuc[i] if sonuc and i < len(sonuc) else None
        dogru = alinan is not None and abs(alinan - beklenen) < 0.005
        k.madde(f"vaka: {ad}", agirlik[i], dogru,
                f"beklenen {beklenen:.2f}, çıkan "
                f"{'hata' if alinan is None else f'{alinan:.2f}'}")
    kapsam = k.eksen("kapsam", 25)

    return [calisir, kapsam, puanla.saglik_ekseni(kok),
            # İstem test istemedi. Yine de ölçülüyor: kendi düzeltmesini
            # doğrulayan bir test yazmak, istenmese de kalitedir.
            puanla.test_ekseni(kok, kritik=KRITIK, harici=True)]


if __name__ == "__main__":
    raise SystemExit(puanla.tek_basina(olc, "k3-tamir"))
