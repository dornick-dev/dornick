Python ile küçük bir kısa-link servisi istiyorum. `servis.py` olsun, `py servis.py`
deyince 8099 portunda ayağa kalksın.

Uçlar:

- `GET /saglik` → 200 dönsün, ayakta olduğunu anlayayım.
- `POST /kisalt` → gövdesinde `{"url": "https://..."}` alsın, `{"kod": "ab12cd"}`
  gibi bir kod dönsün.
- `GET /<kod>` → o kodun adresine yönlendirsin (302).
- Olmayan bir kod istenirse 404 dönsün.

Testlerini de yaz.
