The workshop has `satislar.csv` with columns `tarih, urun, adet,
birim_fiyat`.

I want a reporting tool named `rapor.py`:

    py rapor.py satislar.csv

must print each month's total revenue and the top 3 products by revenue
(sorted high to low).

    py rapor.py satislar.csv --ay 2026-03

must show only that month.

Revenue = adet × birim_fiyat. Money values with two decimals.
