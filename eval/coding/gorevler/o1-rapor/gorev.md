Atölyede `satislar.csv` var: `tarih, urun, adet, birim_fiyat` sütunları.

Bundan rapor çıkaran bir araç istiyorum, adı `rapor.py` olsun:

    py rapor.py satislar.csv

deyince her ayın toplam cirosunu ve en çok ciro yapan 3 ürünü (çoktan aza
sıralı) yazsın.

    py rapor.py satislar.csv --ay 2026-03

deyince sadece o ayı göstersin.

Ciro = adet × birim_fiyat. Para değerleri iki ondalıklı olsun.
