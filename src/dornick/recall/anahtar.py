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
class Anahtarlar:
    """Hangi mekanik açık. Hepsi varsayılan olarak açık."""

    # Faz 1 — zaman bazlı aktivasyon (ACT-R taban seviyesi).
    aktivasyon: bool = True
    # Faz 2 — supersede: güncellenen kaydın eskisini tohumlamadan düşürme.
    supersede: bool = True
    # Faz 3 — gece konsolidasyonu: yeniden örgü ve damıtma.
    orgu: bool = True
    damitma: bool = True
    # Faz 4 — kodlama gücü (sürpriz).
    kodlama: bool = True
    # Faz 5 — bağlam bonusu.
    baglam: bool = True


AKTIF = Anahtarlar()

# Bench'in `--kapat` bayrağına yazacağı isimler. Bilinmeyen isim sessizce
# yutulmasın diye tek kaynaktan okunuyor.
ADLAR: tuple[str, ...] = tuple(f.name for f in fields(Anahtarlar))


def ayarla(**kapali: bool) -> None:
    """Anahtarları süreç genelinde değiştirir. Yalnızca ölçüm içindir."""
    global AKTIF
    bilinmeyen = set(kapali) - set(ADLAR)
    if bilinmeyen:
        raise ValueError(f"Bilinmeyen mekanik: {', '.join(sorted(bilinmeyen))}")
    AKTIF = replace(AKTIF, **kapali)


def sifirla() -> None:
    """Hepsini varsayılana (açık) döndürür."""
    global AKTIF
    AKTIF = Anahtarlar()


@contextmanager
def kapali(*adlar: str) -> Iterator[Anahtarlar]:
    """Verilen mekanikleri blok boyunca kapatır, çıkışta geri açar."""
    global AKTIF
    onceki = AKTIF
    try:
        ayarla(**{ad: False for ad in adlar})
        yield AKTIF
    finally:
        AKTIF = onceki
