"""Location: where we are.

The answer to "what's the weather tomorrow?" depends on where to look,
and the model had no way to learn it — it assumed Istanbul and answered.

There are three sources and their reliability differs wildly:

    typed by hand  certain. If the user said it, it is true.
    timezone       gives the country, not the city. No network, no permission.
    IP             **claims** a city, but it may not hold.

The third was measured: two services were asked at the same moment, one
said "Manisa", the other "Kayseri". On mobile connections and with big
carriers the exit point is not where the user is. That is why the city
coming from the IP is marked here as a **hint**, not as fact: the model
must not bake it into an answer without verifying it.

The IP query sends the user's address to a third-party service. That is
why it ships disabled and asks for a separate permission.
"""

from __future__ import annotations

import json
import locale
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

# Services that resolve location from the IP. Both are asked: if they say
# the same thing confidence grows, if they diverge that is information too.
SOURCES = (
    ("ip-api", "http://ip-api.com/json/?fields=status,country,regionName,city"),
    ("ipinfo", "https://ipinfo.io/json"),
)

TIMEOUT = 6.0


@dataclass(slots=True)
class PlaceConfig:
    """Location settings.

    enabled: location lookup from the IP. Ships disabled — sending the
        user's address to a third-party service is not something to do
        silently.
    manual: the place the user typed themselves. If set it comes before
        everything: the only certain source.
    """

    enabled: bool = False
    manual: str = ""


@dataclass(slots=True)
class Place:
    # The best answer to where we are.
    where: str = ""
    # How trustworthy this answer is: "kesin" | "ülke" | "ipucu" | "yok"
    trust: str = "yok"
    # Where it came from — for the model to state in its answer.
    source: str = ""
    detail: dict[str, Any] = field(default_factory=dict)


def from_machine() -> Place:
    """Country from the timezone. No network, no permission needed.

    It does not give the city and says so: the difference between "you
    are in Türkiye" and "you are in Istanbul" is the entire answer to a
    weather question.
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
    """City from the IP. A **hint**, not fact.

    Both services are asked. If they name the same city confidence grows
    a little; if they diverge both are written — exactly this happened
    in the measurement ("Manisa" and "Kayseri") and reducing it to a
    single answer would be wrong.
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
    """The best answer to where we are, together with its trust level."""
    if manual := (config.manual or "").strip():
        return Place(where=manual, trust="kesin", source="kullanıcı söyledi")

    machine = from_machine()
    if not config.enabled:
        return machine

    network = from_network()
    if not network.where:
        return machine

    # Country from the machine, city from the network. Together they say
    # more, but the trust is still the network's trust.
    detail = {**machine.detail, **network.detail}
    where = network.where
    if machine.where and machine.where not in where:
        where = f"{where} ({machine.where})"
    return Place(where=where, trust="ipucu", source=network.source, detail=detail)


def describe(place: Place) -> str:
    """The text that goes to the model.

    The trust level is inside the sentence: if the model bakes a "hint"
    city into an answer as fact, that is exactly the mistake we are
    trying to fix.
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
