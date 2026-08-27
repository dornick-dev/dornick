"""o3 — orta/Node: mevcut projeye özellik ekleme, mevcut testler kırılmadan.

Buradaki asıl ölçüm REGRESYON: ajanın "var olan testler geçiyor" demesi
yetmiyor, testin BOZULMAMIŞ kopyası koşuluyor. Atölye geçici bir klasöre
kopyalanıyor, `kitaplik.test.js`'in tohumdaki hali üstüne yazılıyor ve
takım orada koşturuluyor. Testi gevşeterek yeşil almak bu düzenekte mümkün
değil.

Yeni davranış da ajanın testlerinden değil, puanlayıcının kendi yazdığı
koşum betiğinden ölçülüyor.
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

BASLIK = "Kitaplığa ödünç verme ekle (mevcut testler kırılmasın)"
ZORLUK = "orta"
DIL = "node"
KRITIK = ("oduncVer", "iadeAl")
TOHUM_TEST = Path(__file__).resolve().parent / "tohum" / "kitaplik.test.js"

_KOSUM = """'use strict';
const { Kitaplik } = require(%(modul)s);
const rapor = { yukleniyor: true, adimlar: {} };
function dene(ad, fn) {
  try { rapor.adimlar[ad] = { ok: true, deger: fn() }; }
  catch (e) { rapor.adimlar[ad] = { ok: false, hata: String(e && e.message || e) }; }
}
const k = new Kitaplik();
dene('kur', () => { k.ekle('978-1', 'Kuyu', 'Ahmet'); k.ekle('978-2', 'Zeytin', 'Ayse'); return k.sayi; });
dene('oduncVer', () => k.oduncVer('978-1', 'Fatih'));
dene('listede_gorunuyor', () => JSON.stringify(k.liste()));
dene('ikinci_odunc_patlamali', () => { k.oduncVer('978-1', 'Mehmet'); return 'PATLAMADI'; });
dene('olmayan_isbn_patlamali', () => { k.oduncVer('yok-boyle', 'Fatih'); return 'PATLAMADI'; });
dene('iadeAl', () => k.iadeAl('978-1'));
dene('iadeden_sonra_yeniden', () => { k.oduncVer('978-1', 'Mehmet'); return 'tamam'; });
dene('bos_kitap_listede', () => JSON.stringify(k.liste()));
console.log('###' + JSON.stringify(rapor));
"""


def _koştur(modul: Path) -> dict | None:
    betik = _KOSUM % {"modul": json.dumps(str(modul).replace("\\", "/"))}
    with tempfile.TemporaryDirectory(prefix="neocp-o3-") as tmp:
        yol = Path(tmp) / "kosum.js"
        yol.write_text(betik, encoding="utf-8")
        k = puanla.kabuk(["node", str(yol)], cwd=tmp, zaman_asimi=60)
    for satir in k.hepsi.splitlines():
        if satir.startswith("###"):
            try:
                return json.loads(satir[3:])
            except ValueError:
                return None
    return None


def _regresyon(kok: Path) -> puanla.Kosum | None:
    """Atölyenin kopyasında, tohumdaki BOZULMAMIŞ test takımını koşturur."""
    with tempfile.TemporaryDirectory(prefix="neocp-o3-reg-") as tmp:
        hedef = Path(tmp) / "atolye"
        try:
            shutil.copytree(kok, hedef,
                            ignore=shutil.ignore_patterns(*puanla.ATLA_KLASOR))
        except OSError:
            return None
        modul = puanla.bul(hedef, "kitaplik.js")
        if modul is None:
            return None
        # Ajan testi düzenlemiş olabilir: aslı üstüne yazılıyor.
        shutil.copyfile(TOHUM_TEST, modul.parent / "kitaplik.test.js")
        return puanla.kabuk(["node", "--test"], cwd=modul.parent, zaman_asimi=120)


def olc(kok: Path) -> list[Eksen]:
    if not puanla.node_var():
        sebep = "makinede node yok"
        return [Eksen("calisir", 40, None, [], sebep=sebep),
                Eksen("kapsam", 25, None, [], sebep=sebep),
                puanla.saglik_ekseni(kok),
                Eksen("test", 15, None, [], sebep=sebep, harici=True)]

    modul = puanla.bul(kok, "kitaplik.js")
    c = Sayac()
    rapor: dict | None = None

    if modul is None:
        for ad, ag in (("kitaplik.js duruyor", 8), ("node --check temiz", 6),
                       ("modül yükleniyor", 8), ("bozulmamış testler yeşil", 18)):
            c.madde(ad, ag, False, "kitaplik.js bulunamadı")
    else:
        c.madde("kitaplik.js duruyor", 8, True, str(modul.relative_to(kok)))
        kontrol = puanla.kabuk(["node", "--check", str(modul)], zaman_asimi=40)
        c.madde("node --check temiz", 6, kontrol.tamam, kontrol.ozet(140))
        rapor = _koştur(modul)
        c.madde("modül yükleniyor", 8, rapor is not None,
                "tamam" if rapor else "require patladı")
        reg = _regresyon(kok)
        if reg is None or reg.kod is None:
            c.atla("bozulmamış testler yeşil",
                   reg.patlama if reg else "regresyon kopyası kurulamadı")
        else:
            c.madde("bozulmamış testler yeşil", 18, reg.tamam,
                    reg.ozet(180))
    calisir = c.eksen("calisir", 40)

    k = Sayac()
    adim = (rapor or {}).get("adimlar") or {}

    def gecti(ad: str) -> bool:
        return bool(adim.get(ad, {}).get("ok"))

    def patlamali(ad: str) -> bool:
        """Hata fırlatması BEKLENEN adım: fırlatmışsa geçer.

        Ön şart var ve gerekli: `oduncVer` HİÇ YOKSA çağrı da "is not a
        function" ile patlıyor ve saf bir kontrol bunu "doğru hata fırlattı"
        sanıyordu — hiçbir şey yazmayan ajan iki maddeyi bedava alıyordu.
        Özellik önce çalışmalı, sonra sınırı korumalı.
        """
        if not gecti("oduncVer"):
            return False
        d = adim.get(ad)
        return bool(d) and not d.get("ok")

    k.madde("oduncVer çalışıyor", 6, gecti("oduncVer"),
            str(adim.get("oduncVer", "adım hiç koşmadı"))[:120])
    liste = str(adim.get("listede_gorunuyor", {}).get("deger", ""))
    gorunuyor = gecti("listede_gorunuyor") and "Fatih" in liste
    k.madde("liste ödünçteki kişiyi gösteriyor", 5, gorunuyor,
            liste[:140] or "liste alınamadı")
    k.madde("ikinci ödünç hata fırlatıyor", 6, patlamali("ikinci_odunc_patlamali"),
            str(adim.get("ikinci_odunc_patlamali", "adım hiç koşmadı"))[:120])
    k.madde("olmayan ISBN hata fırlatıyor", 4, patlamali("olmayan_isbn_patlamali"),
            str(adim.get("olmayan_isbn_patlamali", "adım hiç koşmadı"))[:120])
    k.madde("iadeAl kitabı serbest bırakıyor", 4,
            gecti("iadeAl") and gecti("iadeden_sonra_yeniden"),
            str(adim.get("iadeAl", "adım hiç koşmadı"))[:120])
    kapsam = k.eksen("kapsam", 25)

    test_e = puanla.test_ekseni(kok, kritik=KRITIK, harici=True)
    test_e.kanit.insert(0, "! tohumda zaten test takımı var — bu eksen ajanın "
                           "kendi katkısını ayıramaz, o yüzden puana katılmıyor")

    return [calisir, kapsam, puanla.saglik_ekseni(kok), test_e]


if __name__ == "__main__":
    raise SystemExit(puanla.tek_basina(olc, "o3-ozellik"))
