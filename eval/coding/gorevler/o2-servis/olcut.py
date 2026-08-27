"""o2 — orta/Python: küçük HTTP servisi + testleri.

Bir servisin "çalıştığı" ancak dışarıdan istek atılarak bilinir. Bu yüzden
puanlayıcı süreci gerçekten başlatıyor, porta bağlanmayı bekliyor ve
uçlara HTTP isteği atıyor. Ajanın kendi testlerinin yeşil olması bu eksene
girmiyor — o ayrı eksen.

Süreç ölçüm bitince öldürülüyor; hiçbir koşu arkasında dinleyen bir sunucu
bırakmıyor.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import puanla  # noqa: E402
from puanla import Eksen, Sayac  # noqa: E402

BASLIK = "Kısa-link HTTP servisi + testleri"
ZORLUK = "orta"
DIL = "python"
KRITIK = ("kisalt", "saglik")
PORT = 8099
HEDEF = "https://ornek.gov.tr/ihale/2026/sondaj"


def _kod_cikar(y: puanla.Yanit) -> str:
    """Yanıttan kısa kodu çıkarır: JSON bekleniyor, düz metne de düşülüyor."""
    import json
    import re

    try:
        veri = json.loads(y.govde)
    except ValueError:
        veri = None
    if isinstance(veri, dict):
        for anahtar in ("kod", "code", "kisa", "short", "id", "slug"):
            if isinstance(veri.get(anahtar), str) and veri[anahtar].strip():
                return veri[anahtar].strip().rsplit("/", 1)[-1]
        for deger in veri.values():
            if isinstance(deger, str) and re.fullmatch(r"[\w-]{3,32}", deger.strip()):
                return deger.strip()
    m = re.search(r"[\w-]{4,32}", y.govde.strip())
    return m.group(0) if m else ""


def olc(kok: Path) -> list[Eksen]:
    servis = puanla.bul(kok, "servis.py")
    saglik_e = puanla.saglik_ekseni(kok)
    test_e = puanla.test_ekseni(kok, kritik=KRITIK)

    if servis is None:
        c = Sayac()
        for ad, ag in (("servis.py var", 8), ("süreç ayağa kalkıyor", 12),
                       ("port açılıyor", 10), ("/saglik 200", 10)):
            c.madde(ad, ag, False, "servis.py bulunamadı")
        k = Sayac()
        for ad, ag in (("POST /kisalt kod dönüyor", 10),
                       ("GET /<kod> 302 yönlendiriyor", 10),
                       ("olmayan kod 404", 5)):
            k.madde(ad, ag, False, "servis.py bulunamadı")
        return [c.eksen("calisir", 40), k.eksen("kapsam", 25), saglik_e, test_e]

    if not puanla.port_bos_mu(PORT):
        sebep = f"{PORT} portu başkası tarafından tutuluyor — ölçüm yapılamaz"
        return [Eksen("calisir", 40, None, [], sebep=sebep),
                Eksen("kapsam", 25, None, [], sebep=sebep), saglik_e, test_e]

    c = Sayac()
    k = Sayac()
    c.madde("servis.py var", 8, True, str(servis.relative_to(kok)))

    with puanla.Sunucu([sys.executable, servis.name], cwd=servis.parent,
                       port=PORT, hazir_sn=30.0) as s:
        c.madde("süreç ayağa kalkıyor", 12, not s.olu or s.acildi,
                s.patlama or ("süreç hemen öldü" if s.olu and not s.acildi else "ayakta"))
        c.madde("port açılıyor", 10, s.acildi,
                f"127.0.0.1:{PORT} " + ("açıldı" if s.acildi else "30 sn'de açılmadı"))

        tarayici = puanla.Tarayici()
        taban = f"http://127.0.0.1:{PORT}"
        if not s.acildi:
            c.madde("/saglik 200", 10, False, "port açılmadı")
            for ad, ag in (("POST /kisalt kod dönüyor", 10),
                           ("GET /<kod> 302 yönlendiriyor", 10),
                           ("olmayan kod 404", 5)):
                k.madde(ad, ag, False, "port açılmadı")
        else:
            saglik = tarayici.iste(f"{taban}/saglik")
            c.madde("/saglik 200", 10, saglik.kod == 200,
                    f"HTTP {saglik.kod}{(' ' + saglik.hata) if saglik.hata else ''}")

            kisalt = tarayici.iste(f"{taban}/kisalt", json_govde={"url": HEDEF})
            kod = _kod_cikar(kisalt) if kisalt.kod in (200, 201) else ""
            k.madde("POST /kisalt kod dönüyor", 10, bool(kod),
                    f"HTTP {kisalt.kod}, kod «{kod}»; gövde {kisalt.govde[:80]!r}")

            if kod:
                gidis = tarayici.iste(f"{taban}/{kod}", takip=False)
                yer = gidis.basliklar.get("Location", "") or gidis.basliklar.get("location", "")
                k.madde("GET /<kod> 302 yönlendiriyor", 10,
                        gidis.kod in (301, 302, 303, 307, 308) and HEDEF in yer,
                        f"HTTP {gidis.kod}, Location «{yer[:80]}»")
            else:
                k.madde("GET /<kod> 302 yönlendiriyor", 10, False, "kod alınamadı")

            yok = tarayici.iste(f"{taban}/kesinlikle-yok-4242", takip=False)
            k.madde("olmayan kod 404", 5, yok.kod == 404, f"HTTP {yok.kod}")

    return [c.eksen("calisir", 40), k.eksen("kapsam", 25), saglik_e, test_e]


if __name__ == "__main__":
    raise SystemExit(puanla.tek_basina(olc, "o2-servis"))
