# Coding Benchmark Report

**Run:** 20260829T085844Z · **Model:** `z-ai/glm-5.3-flash` · **Repetitions:** 2 · **Rig:** `eval/coding/` (external gate + isolated instance)

The score has four axes: **works** 40 · **requested scope** 25 · **code health** 20 · **test quality** 15. An unmeasurable axis also leaves the denominator; if the brief did not ask for the work (*not requested*) it is measured but not scored. The score column is normalised to 100.

## Score breakdown

| task | difficulty | language | works (40) | scope (25) | health (20) | tests (15) | **score** |
|---|---|---|---|---|---|---|---|
| k1-module† | easy | python | 40.0 | 25.0 | 20.0 | 15.0 | **100.0** ±0.3 |
| k2-cli† | easy | node | 40.0 | 25.0 | 20.0 | 0.0* | **100.0** ±0.0 |
| k3-repair† | easy | php | 40.0 | 25.0 | 20.0 | 0.0* | **100.0** ±0.0 |
| o1-report† | medium | python | 40.0 | 25.0 | 20.0 | 0.0* | **100.0** ±0.0 |
| o2-service | medium | python | 40.0 | 25.0 | 20.0 | 15.0 | **100.0** ±7.5 |
| o3-feature† | medium | node | 40.0 | 25.0 | 20.0 | 15.0* | **100.0** ±0.0 |
| z1-search† | hard | python | 40.0 | 25.0 | 20.0 | 15.0 | **100.0** ±5.0 |
| z2-panel† | hard | php | 40.0 | 25.0 | 20.0 | 0.0* | **100.0** ±0.0 |
| z3-hidden-bug† | hard | python | 40.0 | 25.0 | 20.0 | 0.0* | **100.0** ±0.0 |

`*` = the brief did not ask for this; measured, reported, not scored.
`†` = this row is carried over from a previous run: k1-module (20260829T085237Z), k2-cli (20260829T085237Z), k3-repair (20260829T085237Z), o1-report (20260829T085237Z), o3-feature (20260829T085237Z), z1-search (20260829T085237Z), z2-panel (20260829T085237Z), z3-hidden-bug (20260829T085237Z).

## Behaviour metrics (never scored)

| task | turn finished | tool calls | tool errors | duration s | tokens (in/out) | cost $ | self-verified | wrote plan | broken deliveries |
|---|---|---|---|---|---|---|---|---|---|
| k1-module | yes | 6 | 1 | 55.0 | 97409/842 | 0.0075 | yes | no | 0/2 |
| k2-cli | yes | 3 | 1 | 47.7 | 63194/1006 | 0.0050 | no | no | 0/2 |
| k3-repair | yes | 7 | 2 | 96.1 | 129090/883 | 0.0099 | no | no | 0/2 |
| o1-report | yes | 4 | 1 | 42.7 | 79722/894 | 0.0062 | no | no | 0/2 |
| o2-service | yes | 24 | 5 | 210.8 | 465632/3490 | 0.0358 | yes | no | 0/2 |
| o3-feature | yes | 12 | 3 | 97.5 | 211525/1745 | 0.0163 | yes | no | 0/2 |
| z1-search | yes | 10 | 1 | 134.7 | 180890/3336 | 0.0144 | yes | no | 0/2 |
| z2-panel | yes | 36 | 3 | 212.1 | 609754/3911 | 0.0467 | yes | no | 0/2 |
| z3-hidden-bug | yes | 6 | 1 | 38.6 | 96488/596 | 0.0074 | yes | no | 0/2 |

**Mean score:** 100.0/100 (9 tasks measured)

## How solid are these numbers?

Every task ran 2 times; the ± in the score column is the between-run spread (half of min–max). Differences smaller than the spread are not improvements.

Isolation: every run happened in its own temp workspace, with an **empty mind**, on its own neo instance. The user's memories do not ride along — this rig measures the coding pipeline, not memory's contribution to coding.

## Evidence

### k1-module — TCKN validation module + tests

- **works: 40.0/40**
  - `+ tckn.py exists (10p) — tckn.py`
  - `+ module imports (15p) — ok`
  - `+ dogrula() is callable (15p) — ok`
- **requested scope: 25.0/25**
  - `~ valid numbers → True (10.0/10p) — 5/5`
  - `~ invalid numbers → False (10.0/10p) — 6/6`
  - `~ survives garbage input (2.0/2p) — 4/4 inputs raised nothing`
  - `~ garbage input → False (3.0/3p) — 4/4`
- **code health: 20.0/20**
  - `~ clean syntax (8.0/8p) — 2/2 files`
  - `~ size/complexity (6.0/6p) — clean`
  - `~ no duplication (6.0/6p) — repeated lines 0%, 0 recurring blocks`
- **test quality: 15.0/15**
  - `+ tests green (6p) — ...... [100%] 6 passed in 0.01s`
  - `~ test count (4.0/4p) — 6 tests found`
  - `~ critical path covered (3.0/3p) — 1/1: dogrula`
  - `~ assertions substantive (2.0/2p) — 14 assertions, 0 freebies`
- verification trail: `shell: py -m pytest test_tckn.py -q`; `shell: py -m pytest test_tckn.py -q`
- tools: shell×3, write_file×2, kos×1
- ! excluded from grading (untouched pre-turn files): 7

### k2-cli — Node todo-list CLI

- **works: 40.0/40**
  - `+ gorev.js exists (10p) — gorev\gorev.js`
  - `! the agent's leftover gorevler.json was deleted before measuring (clean slate)`
  - `+ ekle works (10p) — exit 0/0`
  - `+ liste works (10p) — 1. [ ] süt al 2. [ ] faturayı öde`
  - `+ unknown command errors (10p) — exit code 1`
- **requested scope: 25.0/25**
  - `+ added items are listed (10p) — «süt al»: True, «faturayı öde»: True`
  - `+ bitir changes the list (the other item stays) (8p) — bitir exit 0; list changed`
  - `+ persists in gorevler.json (7p) — gorevler.json, 109 chars`
- **code health: 20.0/20**
  - `~ clean syntax (8.0/8p) — 1/1 files`
  - `~ size/complexity (6.0/6p) — clean`
  - `~ no duplication (6.0/6p) — repeated lines 0%, 0 recurring blocks`
- **test quality: 0.0/15** *(not requested)*
  - `- no test file (0p)`
- tools: shell×2, write_file×1
- ! excluded from grading (untouched pre-turn files): 7

### k3-repair — Find and fix the PHP invoice bug

- **works: 40.0/40**
  - `+ fatura.php still there (10p) — fatura.php`
  - `+ php -l clean (10p) — No syntax errors detected in C:\Users\user\AppData\Local\Temp\neocp-eval-k3-repair-4sg9xot1\atolye\fatura.php`
  - `+ function callable from outside (20p) — ok`
- **requested scope: 25.0/25**
  - `+ case: three lines 18% (10p) — expected 82.60, got 82.60`
  - `+ case: single line 20% (7p) — expected 27.00, got 27.00`
  - `+ case: two lines 0% (5p) — expected 50.00, got 50.00`
  - `+ case: empty order (3p) — expected 0.00, got 0.00`
- **code health: 20.0/20**
  - `~ clean syntax (8.0/8p) — 1/1 files`
  - `~ size/complexity (6.0/6p) — clean`
  - `~ no duplication (6.0/6p) — repeated lines 0%, 0 recurring blocks`
- **test quality: 0.0/15** *(not requested)*
  - `- no test file (0p)`
- tools: shell×4, read_file×1, edit_file×1, list_dir×1
- ! excluded from grading (untouched pre-turn files): 7

### o1-report — CSV sales report + CLI

- **works: 40.0/40**
  - `+ rapor.py exists (8p) — rapor.py`
  - `+ runs on the csv (16p) — exit 0; 2026-01 | Toplam ciro: 47553.25 Pompa 25197.00 Sensor 12159.05 PLC 8249.70 2026-02 | Toplam ciro: 33938.45 Sensor 17278.65 Pompa 8399.00 PLC 5499.80 2026-03 | T`
  - `+ output not empty (8p) — 316 chars`
  - `+ --ay runs (8p) — exit 0; 2026-03 | Toplam ciro: 99286.90 Pompa 54593.50 PLC 30248.90 Sensor 12799.00`
- **requested scope: 25.0/25**
  - `~ monthly totals right (10.0/10p) — 3/3 months matched: 2026-01, 2026-02, 2026-03`
  - `+ top 3 products present (5p) — Pompa, PLC, Sensor`
  - `+ the three sorted high to low (5p) — order held`
  - `+ --ay 2026-03 gives the right month (3p) — expected 99286.9`
  - `+ --ay filters the other months (2p) — clean`
- **code health: 20.0/20**
  - `~ clean syntax (8.0/8p) — 1/1 files`
  - `~ size/complexity (6.0/6p) — clean`
  - `~ no duplication (6.0/6p) — repeated lines 0%, 0 recurring blocks`
- **test quality: 0.0/15** *(not requested)*
  - `- no test file (0p)`
- tools: shell×2, read_file×1, write_file×1
- ! excluded from grading (untouched pre-turn files): 8

### o2-service — Short-link HTTP service + tests

- **works: 40.0/40**
  - `+ servis.py exists (8p) — kisa-baglanti\servis.py`
  - `+ process boots (12p) — up`
  - `+ port opens (10p) — 127.0.0.1:8099 opened`
  - `+ /saglik 200 (10p) — HTTP 200`
- **requested scope: 25.0/25**
  - `+ POST /kisalt returns a code (10p) — HTTP 200, code «dspgjt»; body '{"kod": "dspgjt"}'`
  - `+ GET /<kod> redirects 302 (10p) — HTTP 302, Location «https://ornek.gov.tr/ihale/2026/sondaj»`
  - `+ unknown code 404 (5p) — HTTP 404`
- **code health: 20.0/20**
  - `~ clean syntax (8.0/8p) — 2/2 files`
  - `~ size/complexity (6.0/6p) — clean`
  - `~ no duplication (6.0/6p) — repeated lines 0%, 0 recurring blocks`
- **test quality: 15.0/15**
  - `+ tests green (6p) — ...... [100%] 6 passed in 12.68s`
  - `~ test count (4.0/4p) — 6 tests found`
  - `~ critical path covered (3.0/3p) — 2/2: kisalt, saglik`
  - `~ assertions substantive (2.0/2p) — 11 assertions, 0 freebies`
- verification trail: `shell: cd C:\Users\user\AppData\Local\Temp\neocp-eval-o2-service-ml72vtlv\atolye\kisa-baglanti; p`; `shell: cd C:\Users\user\AppData\Local\Temp\neocp-eval-o2-service-ml72vtlv\atolye\kisa-baglanti; p`; `shell: cd C:\Users\user\AppData\Local\Temp\neocp-eval-o2-service-ml72vtlv\atolye\kisa-baglanti; p`; `shell: $w = Invoke-WebRequest -Uri http://localhost:8099/saglik -UseBasicParsing; "$($w.StatusCod`
- tools: shell×9, read_file×7, write_file×3, kos×3, edit_file×2
- ! excluded from grading (untouched pre-turn files): 7
- ! 1 leftover processes killed before grading

### o3-feature — Add lending to the library (existing tests must not break)

- **works: 40.0/40**
  - `+ kitaplik.js still there (8p) — kitaplik.js`
  - `+ node --check clean (6p)`
  - `+ module loads (8p) — ok`
  - `+ pristine tests green (18p) — TAP version 13 # Subtest: kitap eklenebiliyor ok 1 - kitap eklenebiliyor --- duration_ms: 0.5057 type: 'test' ... # Subtest: aynı ISBN iki kez eklenemiyor ok 2 - aynı ISBN iki kez `
- **requested scope: 25.0/25**
  - `+ oduncVer works (6p) — {'ok': True, 'value': {'isbn': '978-1', 'baslik': 'Kuyu', 'yazar': 'Ahmet', 'odunc': 'Mehmet'}}`
  - `+ liste shows who has the book (5p) — [{"isbn":"978-1","baslik":"Kuyu","yazar":"Ahmet","oduncVerildi":true,"kimde":"Fatih"},{"isbn":"978-2","baslik":"Zeytin","yazar":"Ayse","odun`
  - `+ second lend throws (6p) — {'ok': False, 'error': 'Kitap zaten dışarıda: 978-1 (Fatih)'}`
  - `+ missing ISBN throws (4p) — {'ok': False, 'error': 'Böyle bir kitap yok: no-such'}`
  - `+ iadeAl frees the book (4p) — {'ok': True, 'value': {'isbn': '978-1', 'baslik': 'Kuyu', 'yazar': 'Ahmet', 'odunc': 'Mehmet'}}`
- **code health: 20.0/20**
  - `~ clean syntax (8.0/8p) — 2/2 files`
  - `~ size/complexity (6.0/6p) — clean`
  - `~ no duplication (6.0/6p) — repeated lines 0%, 0 recurring blocks`
- **test quality: 15.0/15** *(not requested)*
  - `! the seed already ships a test suite — this axis cannot isolate the agent's own contribution, so it is not scored`
  - `+ tests green (6p) — TAP version 13 # Subtest: kitap eklenebiliyor ok 1 - kitap eklenebiliyor --- duration_ms: 0.5747 type: 'test' ... # Subt`
  - `~ test count (4.0/4p) — 10 tests found`
  - `~ critical path covered (3.0/3p) — 2/2: oduncVer, iadeAl`
  - `~ assertions substantive (2.0/2p) — 28 assertions, 0 freebies`
- verification trail: `shell: node --test atolye/kitaplik.test.js`; `shell: node --test kitaplik.test.js`; `shell: node --test kitaplik.test.js 2>&1 | Select-String -Pattern '# (pass|fail)|not ok'`
- tools: edit_file×5, read_file×3, shell×3, kos×1
- ! excluded from grading (untouched pre-turn files): 7

### z1-search — Note search tool with SQLite persistence

- **works: 40.0/40**
  - `+ ara.py exists (5p) — ara.py`
  - `+ ekle runs (12p) — exit 0; 6 dosya dizine eklendi: C:\Users\user\AppData\Local\Temp\neocp-eval-z1-search-ig2halg1\atolye\notlar`
  - `+ SQLite file created (8p) — ara.index.db`
  - `+ bul runs in a separate process (15p) — exit 0; pompa-katalog.txt:4 Yedek parca: rulman, salmastra, motor mili. pompa-katalog.txt:4 Yedek parca: rulman, salmastra, motor mili.`
- **requested scope: 25.0/25**
  - `+ single word finds the right note (8p) — «salmastra» → expected pompa-katalog; output: 'pompa-katalog.txt:4\n  Yedek parca: rulman, salmastra, motor mili.\npompa-katalog.txt:4\n  Yedek parca: rulman, salmastra, '`
  - `+ multi-word: full match ranks first (10p) — «rulman titresim» → kuyu-bakim at 0, pompa-katalog at 178`
  - `+ missing word invents nothing (7p) — «helikopter» → output: "Eşleşme yok: 'helikopter' için hiçbir notta sonuç bulunamadı.\n\n"`
- **code health: 20.0/20**
  - `~ clean syntax (8.0/8p) — 2/2 files`
  - `~ size/complexity (6.0/6p) — clean`
  - `~ no duplication (6.0/6p) — repeated lines 0%, 0 recurring blocks`
- **test quality: 15.0/15**
  - `+ tests green (6p) — ......... [100%] 9 passed in 0.28s`
  - `~ test count (4.0/4p) — 9 tests found`
  - `~ critical path covered (3.0/3p) — 2/2: ekle, bul`
  - `~ assertions substantive (2.0/2p) — 14 assertions, 0 freebies`
- verification trail: `shell: py -m pytest test_ara.py -q`; `shell: py ara.py bul "titresim"; echo ---; py -m pytest test_ara.py -q`
- tools: shell×5, list_dir×2, write_file×2, kos×1
- ! excluded from grading (untouched pre-turn files): 13

### z2-panel — Login-guarded mini admin panel

- **works: 40.0/40**
  - `+ index.php exists (8p) — admin-panel`
  - `! 8098 was held (the agent may have left its own server running); measured on port 8100`
  - `+ server boots (10p) — port opened`
  - `+ login page renders (10p) — 200, 1123 chars; password field: True`
  - `+ correct password gets in (12p) — login POST → HTTP 200; ozet.php → HTTP 200`
- **requested scope: 25.0/25**
  - `~ unauthenticated access blocked (7.0/7p) — ozet.php: blocked; kullanicilar.php: blocked; ayarlar.php: blocked`
  - `+ wrong password rejected (3p) — after a wrong password ozet.php → HTTP 302`
  - `+ ozet.php works after login (5p) — 200, 1962 chars`
  - `+ kullanicilar.php works after login (5p) — 200, 2199 chars`
  - `+ ayarlar.php works after login (5p) — 200, 1949 chars`
- **code health: 20.0/20**
  - `~ clean syntax (8.0/8p) — 6/6 files`
  - `~ size/complexity (6.0/6p) — clean`
  - `~ no duplication (6.0/6p) — repeated lines 0%, 0 recurring blocks`
- **test quality: 0.0/15** *(not requested)*
  - `- no test file (0p)`
- verification trail: `browser: `; `shell: try { (Invoke-WebRequest -Uri http://localhost:8090/index.php -MaximumRedirection 0 -Error`; `browser: `; `browser: `
- tools: browser×19, shell×9, write_file×7, list_dir×1
- ! excluded from grading (untouched pre-turn files): 7

### z3-hidden-bug — Find and fix the 3 hidden bugs in the cart module

- **works: 40.0/40**
  - `+ sepet.py still there (6p) — sepet\sepet.py`
  - `+ module imports (10p) — ok`
  - `+ pristine regression suite runs (8p) — ........ [100%] 8 passed in 0.01s`
  - `+ regression suite fully green (16p) — ........ [100%] 8 passed in 0.01s`
- **requested scope: 25.0/25**
  - `+ bug 1: re-adding a product accumulates (8p) — expected [7, 21.0], got [7, 21.0]`
  - `+ bug 2: discount boundaries inclusive (8p) — 500→0.05 (0.05), 1000→0.1 (0.10), 499.99→0.0 (0.0)`
  - `+ bug 3: total keeps the cents (6p) — 7 × 14.29 → expected 100.03, got 100.03`
  - `+ hidden case: 1500 → 10%, 500 → 5% (2p) — 1500→1350.0 (1350.0), 500→475.0 (475.0)`
  - `+ existing guard survived (quantity 0 → ValueError) (1p) — {'ok': True, 'value': 'ValueError'}`
- **code health: 20.0/20**
  - `~ clean syntax (8.0/8p) — 1/1 files`
  - `~ size/complexity (6.0/6p) — clean`
  - `~ no duplication (6.0/6p) — repeated lines 0%, 0 recurring blocks`
- **test quality: 0.0/15** *(not requested)*
  - `! the regression suite ships with the seed — this axis cannot isolate the agent's own contribution, so it is not scored`
  - `- no test file (0p)`
- verification trail: `shell: py -m pytest -q`; `shell: cd C:\Users\user\AppData\Local\Temp\neocp-eval-z3-hidden-bug-ayv91spf\atolye\sepet; py -m `
- tools: read_file×2, shell×2, list_dir×1, edit_file×1
- ! excluded from grading (untouched pre-turn files): 8
