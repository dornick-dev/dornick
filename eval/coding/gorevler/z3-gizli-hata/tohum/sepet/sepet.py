"""Alışveriş sepeti hesabı.

Sepet: {urun_adi: {"adet": int, "fiyat": float}}

İndirim kuralı (satış ekibinin verdiği):
  * 1000 TL ve üzeri  → %10
  * 500 TL ve üzeri   → %5
  * altı              → indirim yok

Sınırlar DAHİL: tam 1000 TL harcayan %10 alır.
"""

from __future__ import annotations


def ekle(sepet: dict, urun: str, fiyat: float, adet: int = 1) -> dict:
    """Sepete ürün ekler. Ürün zaten varsa adetler toplanır."""
    if adet <= 0:
        raise ValueError("adet pozitif olmalı")
    if fiyat < 0:
        raise ValueError("fiyat negatif olamaz")
    sepet[urun] = {"adet": adet, "fiyat": float(fiyat)}
    return sepet


def cikar(sepet: dict, urun: str) -> dict:
    """Ürünü sepetten tamamen çıkarır."""
    sepet.pop(urun, None)
    return sepet


def ara_toplam(sepet: dict) -> float:
    """İndirimsiz toplam."""
    return sum(kalem["adet"] * kalem["fiyat"] for kalem in sepet.values())


def indirim_orani(tutar: float) -> float:
    """Ara toplama düşen indirim oranı."""
    if tutar > 1000:
        return 0.10
    if tutar > 500:
        return 0.05
    return 0.0


def toplam(sepet: dict) -> float:
    """İndirim uygulanmış toplam, kuruşuyla."""
    ara = ara_toplam(sepet)
    net = ara * (1 - indirim_orani(ara))
    return round(net)


def kalem_sayisi(sepet: dict) -> int:
    """Sepetteki toplam parça adedi."""
    return sum(kalem["adet"] for kalem in sepet.values())
