"""z1 — zor/Python: SQLite kalıcılıklı arama/indeks.

Zorluğun üç ayrı yeri var ve üçü de ayrı ölçülüyor:

  * **Kalıcılık.** `bul` AYRI bir süreçte koşuyor. Aynı süreçte bellekte
    tutmak bu isteği karşılamıyor; kapanıp açılınca indeksin durması
    gerekiyor. Ayrıca diskte gerçekten bir SQLite dosyası olmalı — başlığı
    okunarak doğrulanıyor ("SQLite format 3"), uzantıya bakılmıyor.
  * **Sıralama.** İki kelimelik sorguda ikisini de içeren not, yalnız birini
    içerenin ÜSTÜNDE olmalı. Donmuş korpus buna göre kuruldu: "rulman
    titresim" yalnız kuyu-bakim'da birlikte geçiyor.
  * **Sessizlik.** Olmayan kelimede uydurma sonuç dönmemeli. Hafıza
    tarafındaki "sessizlik" metriğinin kod tarafındaki karşılığı.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import puanla  # noqa: E402
from puanla import Eksen, Sayac  # noqa: E402

BASLIK = "SQLite kalıcılıklı not arama aracı"
ZORLUK = "zor"
DIL = "python"
KRITIK = ("ekle", "bul")

TEK_KELIME = "salmastra"            # yalnız pompa-katalog.txt'de
TEK_BEKLENEN = "pompa-katalog"
CIFT = "rulman titresim"            # ikisi birlikte yalnız kuyu-bakim'da
CIFT_UST = "kuyu-bakim"
CIFT_ALT = "pompa-katalog"          # yalnız "rulman" var: altta olmalı
YOK = "helikopter"


def _sqlite_dosyasi(kok: Path) -> Path | None:
    """Diskteki gerçek SQLite dosyasını başlığından bulur (uzantıya güvenmeden)."""
    import os

    for dirpath, dirnames, filenames in os.walk(kok):
        dirnames[:] = [d for d in dirnames if d not in puanla.ATLA_KLASOR]
        for ad in sorted(filenames):
            yol = Path(dirpath) / ad
            try:
                if yol.stat().st_size < 16:
                    continue
                with yol.open("rb") as fh:
                    if fh.read(16) == b"SQLite format 3\x00":
                        return yol
            except OSError:
                continue
    return None


def olc(kok: Path) -> list[Eksen]:
    arac = puanla.bul(kok, "ara.py")
    notlar = None
    for aday in ("notlar", "Notlar"):
        yer = kok / aday
        if yer.is_dir():
            notlar = yer
            break
    if notlar is None:
        for p in kok.rglob("kuyu-bakim.txt"):
            notlar = p.parent
            break

    c = Sayac()
    ekle = tekli = ciftli = bos = None
    if arac is None:
        for ad, ag in (("ara.py var", 5), ("ekle koşuyor", 12),
                       ("SQLite dosyası oluştu", 8),
                       ("bul ayrı süreçte koşuyor", 15)):
            c.madde(ad, ag, False, "ara.py bulunamadı")
    else:
        c.madde("ara.py var", 5, True, str(arac.relative_to(kok)))
        yer = arac.parent
        hedef = str(notlar) if notlar else "notlar"
        ekle = puanla.kabuk([sys.executable, arac.name, "ekle", hedef],
                            cwd=yer, zaman_asimi=120)
        c.madde("ekle koşuyor", 12, ekle.tamam, f"çıkış {ekle.kod}; {ekle.ozet(160)}")

        db = _sqlite_dosyasi(kok)
        c.madde("SQLite dosyası oluştu", 8, db is not None,
                str(db.relative_to(kok)) if db else "diskte SQLite başlıklı dosya yok")

        # AYRI süreç: kalıcılığın tek dürüst kanıtı.
        tekli = puanla.kabuk([sys.executable, arac.name, "bul", TEK_KELIME],
                             cwd=yer, zaman_asimi=90)
        c.madde("bul ayrı süreçte koşuyor", 15, tekli.tamam,
                f"çıkış {tekli.kod}; {tekli.ozet(160)}")
        ciftli = puanla.kabuk([sys.executable, arac.name, "bul", CIFT],
                              cwd=yer, zaman_asimi=90)
        bos = puanla.kabuk([sys.executable, arac.name, "bul", YOK],
                           cwd=yer, zaman_asimi=90)
    calisir = c.eksen("calisir", 40)

    k = Sayac()
    tek_metin = tekli.hepsi if tekli else ""
    k.madde("tek kelime doğru notu buluyor", 8,
            TEK_BEKLENEN in tek_metin,
            f"«{TEK_KELIME}» → {TEK_BEKLENEN} bekleniyordu; çıktı: {tek_metin[:120]!r}")

    cift_metin = ciftli.hepsi if ciftli else ""
    ust = cift_metin.find(CIFT_UST)
    alt = cift_metin.find(CIFT_ALT)
    sirali = ust >= 0 and (alt < 0 or ust < alt)
    k.madde("çok kelimede hepsi geçen not üstte", 10, sirali,
            f"«{CIFT}» → {CIFT_UST} yeri {ust}, {CIFT_ALT} yeri {alt}")

    bos_metin = bos.hepsi if bos else ""
    temiz = bool(bos) and not any(
        ad in bos_metin for ad in
        ("kuyu-bakim", "pompa-katalog", "teklif-kayseri", "sensor-arizasi",
         "toplanti-2mart", "egitim-plani"))
    k.madde("olmayan kelimede sonuç uydurmuyor", 7, temiz,
            f"«{YOK}» → çıktı: {bos_metin[:120]!r}")
    kapsam = k.eksen("kapsam", 25)

    return [calisir, kapsam, puanla.saglik_ekseni(kok),
            puanla.test_ekseni(kok, kritik=KRITIK)]


if __name__ == "__main__":
    raise SystemExit(puanla.tek_basina(olc, "z1-arama"))
