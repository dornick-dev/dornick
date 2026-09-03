"""Hafıza mekaniklerinin açma/kapama anahtarları.

Tek amacı ölçüm: yaşam benchmark'ı (eval/context_memory/yasam_bench.py) her
mekaniği tek tek kapatıp Pareto tablosu üretebilmeli. Bir mekaniğin
kapatılması hiçbir metriği bozmuyorsa o mekanik karmaşıklığı hak etmemiştir
ve kaldırılır — bu dosya o kararın ölçülebilir olmasını sağlıyor.

Anahtarlar **süreç geneli** ve varsayılanları açık: ürün davranışı bu modül
eklenmeden öncekiyle birebir aynı. Ayarları yalnızca benchmark değiştirir;
ürün kodunda `ayarla()` çağrısı yoktur.

Neden ürün kodunda duruyor da bench'te değil: ölçülen yol ürünün kendi yolu
olmalı. Bench'e kopyalanmış bir "aktivasyonsuz sürüm" sessizce ayrışır ve
ölçülen şey ürün olmaz (bkz. scale_bench.py'nin parametrik kopya-eşitlik
kontrolü, aynı gerekçe).
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, fields, replace
from typing import Iterator


@dataclass(frozen=True, slots=True)
class Switches:
    """Hangi mekanik açık. Hepsi varsayılan olarak açık."""

    # Faz 1 — zaman bazlı aktivasyon (ACT-R taban seviyesi).
    activation: bool = True
    # Faz 2 — supersede: güncellenen kaydın eskisini tohumlamadan düşürme.
    supersede: bool = True
    # Faz 3 — gece konsolidasyonu: yeniden örgü ve damıtma.
    weave: bool = True
    distillation: bool = True
    # Faz 4 — kodlama gücü (sürpriz).
    encoding: bool = True
    # Faz 5 — bağlam bonusu.
    context: bool = True


ACTIVE = Switches()

# Bench'in `--kapat` bayrağına yazacağı isimler. Bilinmeyen isim sessizce
# yutulmasın diye tek kaynaktan okunuyor.
NAMES: tuple[str, ...] = tuple(f.name for f in fields(Switches))


def configure(**disabled: bool) -> None:
    """Anahtarları süreç genelinde değiştirir. Yalnızca ölçüm içindir."""
    global ACTIVE
    bilinmeyen = set(disabled) - set(NAMES)
    if bilinmeyen:
        raise ValueError(f"Bilinmeyen mekanik: {', '.join(sorted(bilinmeyen))}")
    ACTIVE = replace(ACTIVE, **disabled)


def reset() -> None:
    """Hepsini varsayılana (açık) döndürür."""
    global ACTIVE
    ACTIVE = Switches()


@contextmanager
def disabled(*adlar: str) -> Iterator[Switches]:
    """Verilen mekanikleri blok boyunca kapatır, çıkışta geri açar."""
    global ACTIVE
    onceki = ACTIVE
    try:
        configure(**{ad: False for ad in adlar})
        yield ACTIVE
    finally:
        ACTIVE = onceki
