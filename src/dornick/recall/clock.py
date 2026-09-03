"""Enjekte edilebilir saat.

Hafıza zamanla çalışıyor: bir kaydın ne kadar hatırlanacağı, ne zaman
yazıldığına ve en son ne zaman kullanıldığına bakıyor. Bu, ölçülemez bir
tasarım tuzağı taşır — `datetime.now()` doğrudan çağrılırsa "otuz gün sonra
ne olur" sorusu ancak otuz gün beklenerek yanıtlanabilir.

Bu yüzden zamanı okuyan tek bir yer var ve orası dışarıdan verilebiliyor.
Ürün varsayılanı duvar saati; yaşam benchmark'ı (eval/context_memory/
yasam_bench.py) yerine sanal bir takvim koyup doksan günü saniyeler içinde
oynatıyor. Ürün davranışı değişmiyor, ölçülebilirlik açılıyor.

Kural: `recall/store.py` ve `mind/store.py` içinde `datetime.now()` doğrudan
çağrılmaz — `tests/test_saat.py` bunu zorluyor.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

# Saat: argümansız çağrılıp "şu an"ı veren şey. Zaman dilimi bilgisi taşıması
# şart — naif bir damga ile UTC damgasını çıkarmak sessizce yanlış aralık
# üretir.
Clock = Callable[[], datetime]


def wall_clock() -> datetime:
    """Ürünün varsayılan saati: gerçek zaman, UTC."""
    return datetime.now(timezone.utc)


def stamp(clock: Clock) -> str:
    """Diske yazılan biçim.

    Milisaniye çözünürlük: aynı saniye içinde yazılan iki kaydın sırası
    kaybolmasın (tazelik sıralaması buna bakıyor).
    """
    return clock().isoformat(timespec="milliseconds")


def parse(metin: str | None) -> datetime | None:
    """Diskteki damgayı geri okur; tanınmayan biçimde None.

    Zaman dilimi olmadan yazılmış eski damgalar (bu sürümden önceki bir
    hatanın kalıntısı ya da elle düzenlenmiş bir db) UTC sayılıyor —
    aksi halde naif ve bilinçli damgaların karşılaştırması patlar.
    """
    if not metin:
        return None
    try:
        an = datetime.fromisoformat(metin)
    except ValueError:
        return None
    return an if an.tzinfo else an.replace(tzinfo=timezone.utc)
