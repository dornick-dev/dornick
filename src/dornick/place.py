"""Konum: nerede olunduğu.

"Yarın hava nasıl?" sorusunun cevabı nereye bakılacağına bağlı ve model
bunu hiçbir yerden öğrenemiyordu — İstanbul varsayıp cevap veriyordu.

Üç kaynak var ve güvenilirlikleri çok farklı:

    elle yazılan   kesin. Kullanıcı söylediyse doğrudur.
    saat dilimi    ülkeyi verir, şehri vermez. Ağa çıkmaz, izin gerektirmez.
    IP             şehir **iddia eder** ama tutmayabilir.

Üçüncüsü ölçüldü: aynı anda iki servise soruldu, biri "Manisa" dedi diğeri
"Kayseri". Mobil bağlantıda ve büyük operatörlerde çıkış noktası kullanıcının
bulunduğu yer değil. O yüzden IP'den gelen şehir burada bir **ipucu** olarak
işaretleniyor, gerçek olarak değil: modelin onu doğrulamadan cevaba
gömmemesi gerekiyor.

IP sorgusu kullanıcının adresini üçüncü bir servise gönderiyor. Bu yüzden
kapalı geliyor ve ayrı bir izin istiyor.
"""

from __future__ import annotations

import json
import locale
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

# IP'den konum soran servisler. İkisi birden soruluyor: aynı şeyi
# söylüyorlarsa güven artıyor, ayrılıyorlarsa bu da bir bilgi.
SOURCES = (
    ("ip-api", "http://ip-api.com/json/?fields=status,country,regionName,city"),
    ("ipinfo", "https://ipinfo.io/json"),
)

TIMEOUT = 6.0


@dataclass(slots=True)
class PlaceConfig:
    """Konum ayarları.

    enabled: IP'den konum sorgusu. Kapalı geliyor — kullanıcının adresini
        üçüncü bir servise göndermek sessizce yapılacak bir şey değil.
    manual: kullanıcının kendi yazdığı yer. Yazılmışsa her şeyin önünde
        gelir: kesin olan tek kaynak bu.
    """

    enabled: bool = False
    manual: str = ""


@dataclass(slots=True)
class Place:
    # Nerede olunduğuna dair en iyi cevap.
    where: str = ""
    # Bu cevaba ne kadar güvenilir: "kesin" | "ülke" | "ipucu" | "yok"
    trust: str = "yok"
    # Nereden geldiği — modelin cevaba yazması için.
    source: str = ""
    detail: dict[str, Any] = field(default_factory=dict)


def from_machine() -> Place:
    """Saat diliminden ülke. Ağa çıkmıyor, izin gerektirmiyor.

    Şehri vermiyor ve vermediğini söylüyor: "Türkiye'desin" ile
    "İstanbul'dasın" arasındaki fark, hava durumu sorusunda cevabın
    tamamı demek.
    """
    now = datetime.now().astimezone()
    region = (locale.getdefaultlocale()[0] or "").split("_")
    country = region[1] if len(region) > 1 else ""
    zone = now.tzname() or ""
    if not (country or zone):
        return Place()
    return Place(
        where=country or zone,
        trust="ülke",
        source="makinenin saat dilimi",
        detail={"timezone": zone, "utc_offset": now.strftime("%z"), "region": country},
    )


def _ask(url: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": "dornick"})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return json.loads(response.read().decode("utf-8"))


def from_network() -> Place:
    """IP'den şehir. **İpucu**, gerçek değil.

    İki servise birden soruluyor. Aynı şehri söylüyorlarsa güven biraz
    artıyor; ayrılıyorlarsa ikisi de yazılıyor — ölçümde tam olarak bu
    oldu ("Manisa" ve "Kayseri") ve tek bir cevaba indirgemek yanlış
    olurdu.
    """
    found: dict[str, str] = {}
    for name, url in SOURCES:
        try:
            data = _ask(url)
        except Exception:
            continue
        city = str(data.get("city") or "").strip()
        if city:
            found[name] = city

    if not found:
        return Place()

    cities = set(found.values())
    if len(cities) == 1:
        city = cities.pop()
        return Place(
            where=city,
            trust="ipucu",
            source="IP (" + ", ".join(found) + " aynı şeyi söyledi)",
            detail=dict(found),
        )

    return Place(
        where=" ya da ".join(found.values()),
        trust="ipucu",
        source="IP (servisler ayrıldı: " +
               ", ".join(f"{k}={v}" for k, v in found.items()) + ")",
        detail=dict(found),
    )


def locate(config: PlaceConfig) -> Place:
    """Nerede olunduğuna dair en iyi cevap, güveniyle birlikte."""
    if manual := (config.manual or "").strip():
        return Place(where=manual, trust="kesin", source="kullanıcı söyledi")

    machine = from_machine()
    if not config.enabled:
        return machine

    network = from_network()
    if not network.where:
        return machine

    # Ülke bilgisi makineden, şehir ağdan. İkisi birlikte daha çok şey
    # söylüyor ama güven yine ağdakinin güveni.
    detail = {**machine.detail, **network.detail}
    where = network.where
    if machine.where and machine.where not in where:
        where = f"{where} ({machine.where})"
    return Place(where=where, trust="ipucu", source=network.source, detail=detail)


def describe(place: Place) -> str:
    """Modele giden metin.

    Güven derecesi cümlenin içinde: "ipucu" olan bir şehri model cevaba
    gerçek gibi gömerse, düzeltmeye çalıştığımız hatanın aynısı olur.
    """
    if not place.where:
        return (
            "Konum bilinmiyor. Ayarlar › konum kapalı ya da sonuç alınamadı. "
            "Kullanıcıya nerede olduğunu sor ve öğrendiğini zihnine yaz."
        )

    if place.trust == "kesin":
        return f"Konum: {place.where} ({place.source}). Bunu kullanabilirsin."

    if place.trust == "ülke":
        return (
            f"Ülke: {place.where} ({place.source}). Şehir bilinmiyor — saat "
            "dilimi şehir vermiyor. Şehre bağlı bir cevap vereceksen "
            "(hava durumu gibi) önce şehri sor."
        )

    return (
        f"Konum ipucu: {place.where} ({place.source}). **Kesin değil** — "
        "IP çıkış noktası kullanıcının bulunduğu yer olmayabilir. Cevaba "
        "gömme; \"IP'ye göre X gibi görünüyorsun, doğru mu?\" diye teyit et "
        "ve doğrulanan yeri zihnine yaz."
    )
