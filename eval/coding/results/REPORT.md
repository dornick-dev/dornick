# Coding Benchmark Report

**Run:** 20260829T121113Z · **Model:** `z-ai/glm-5.3-flash` · **Repetitions:** 2 · **Rig:** `eval/coding/` (external gate + isolated instance)

The score has four axes: **works** 40 · **requested scope** 25 · **code health** 20 · **test quality** 15. An unmeasurable axis also leaves the denominator; if the brief did not ask for the work (*not requested*) it is measured but not scored. The score column is normalised to 100.

## Score breakdown

| task | difficulty | language | works (40) | scope (25) | health (20) | tests (15) | **score** |
|---|---|---|---|---|---|---|---|
| k3-repair | easy | php | 40.0 | 25.0 | 20.0 | 0.0* | **100.0** ±0.0 |
| o3-feature | medium | node | 40.0 | 25.0 | 20.0 | 0.0* | **100.0** ±0.0 |
| z1-search | hard | python | 40.0 | 25.0 | 20.0 | 15.0 | **100.0** ±1.5 |

`*` = the brief did not ask for this; measured, reported, not scored.

## Behaviour metrics (never scored)

| task | turn finished | tool calls | tool errors | duration s | tokens (in/out) | cost $ | self-verified | wrote plan | broken deliveries |
|---|---|---|---|---|---|---|---|---|---|
| k3-repair | yes | 4 | 1 | 42.9 | 79351/906 | 0.0062 | no | no | 0/2 |
| o3-feature | yes | 9 | 1 | 60.1 | 134930/923 | 0.0104 | yes | no | 0/2 |
| z1-search | yes | 12 | 3 | 127.6 | 206337/3489 | 0.0163 | yes | no | 0/2 |

**Mean score:** 100.0/100 (3 tasks measured)

**Not run:** k1-module, k2-cli, o1-report, o2-service, z2-panel, z3-hidden-bug

## How solid are these numbers?

Every task ran 2 times; the ± in the score column is the between-run spread (half of min–max). Differences smaller than the spread are not improvements.

Isolation: every run happened in its own temp workspace, with an **empty mind**, on its own neo instance. The user's memories do not ride along — this rig measures the coding pipeline, not memory's contribution to coding.

## Evidence

### k3-repair — Find and fix the PHP invoice bug

- **works: 40.0/40**
  - `+ fatura.php still there (10p) — fatura.php`
  - `+ php -l clean (10p) — No syntax errors detected in C:\Users\user\AppData\Local\Temp\neocp-eval-k3-repair-spbgg_i3\atolye\fatura.php`
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
- tools: shell×2, read_file×1, edit_file×1
- ! excluded from grading (untouched pre-turn files): 7

### o3-feature — Add lending to the library (existing tests must not break)

- **works: 40.0/40**
  - `+ kitaplik.js still there (8p) — kitaplik.js`
  - `+ node --check clean (6p)`
  - `+ module loads (8p) — ok`
  - `+ pristine tests green (18p) — TAP version 13 # Subtest: kitap eklenebiliyor ok 1 - kitap eklenebiliyor --- duration_ms: 0.9385 type: 'test' ... # Subtest: aynı ISBN iki kez eklenemiyor ok 2 - aynı ISBN iki kez `
- **requested scope: 25.0/25**
  - `+ oduncVer works (6p) — {'ok': True, 'value': {'isbn': '978-1', 'baslik': 'Kuyu', 'yazar': 'Ahmet', 'odunc': 'Mehmet'}}`
  - `+ liste shows who has the book (5p) — [{"isbn":"978-1","baslik":"Kuyu","yazar":"Ahmet","odunc":"Fatih"},{"isbn":"978-2","baslik":"Zeytin","yazar":"Ayse","odunc":null}]`
  - `+ second lend throws (6p) — {'ok': False, 'error': 'Kitap zaten Fatih kişisinde: 978-1'}`
  - `+ missing ISBN throws (4p) — {'ok': False, 'error': 'Bu ISBN kayıtlı değil: no-such'}`
  - `+ iadeAl frees the book (4p) — {'ok': True, 'value': {'isbn': '978-1', 'baslik': 'Kuyu', 'yazar': 'Ahmet', 'odunc': 'Mehmet'}}`
- **code health: 20.0/20**
  - `~ clean syntax (8.0/8p) — 1/1 files`
  - `~ size/complexity (6.0/6p) — clean`
  - `~ no duplication (6.0/6p) — repeated lines 0%, 0 recurring blocks`
- **test quality: 0.0/15** *(not requested)*
  - `! the seed already ships a test suite — this axis cannot isolate the agent's own contribution, so it is not scored`
  - `- no test file (0p)`
- verification trail: `shell: node --test`; `shell: node --test kitaplik.test.js`; `shell: node --test .\kitaplik.test.js`; `shell: node -e "const {Kitaplik}=require('./kitaplik');const k=new Kitaplik();k.ekle('a','A');k.o`
- tools: shell×4, read_file×2, edit_file×2, kos×1
- ! excluded from grading (untouched pre-turn files): 8

### z1-search — Note search tool with SQLite persistence

- **works: 40.0/40**
  - `+ ara.py exists (5p) — ara.py`
  - `+ ekle runs (12p) — exit 0; İndeks güncel, değişiklik yok.`
  - `+ SQLite file created (8p) — indeks.db`
  - `+ bul runs in a separate process (15p) — exit 0; pompa-katalog.txt (skor 10.7) …m3/saat. Yedek parca: rulman, salmastra, motor mili.`
- **requested scope: 25.0/25**
  - `+ single word finds the right note (8p) — «salmastra» → expected pompa-katalog; output: 'pompa-katalog.txt  (skor 10.7)\n    …m3/saat. Yedek parca: rulman, salmastra, motor mili.\n\n'`
  - `+ multi-word: full match ranks first (10p) — «rulman titresim» → kuyu-bakim at 0, pompa-katalog at 155`
  - `+ missing word invents nothing (7p) — «helikopter» → output: 'Eşleşme bulunamadı: "helikopter"\n\n'`
- **code health: 20.0/20**
  - `~ clean syntax (8.0/8p) — 2/2 files`
  - `~ size/complexity (6.0/6p) — clean`
  - `~ no duplication (6.0/6p) — repeated lines 0%, 0 recurring blocks`
- **test quality: 15.0/15**
  - `+ tests green (6p) — ....... [100%] 7 passed in 0.19s`
  - `~ test count (4.0/4p) — 7 tests found`
  - `~ critical path covered (3.0/3p) — 2/2: ekle, bul`
  - `~ assertions substantive (2.0/2p) — 13 assertions, 0 freebies`
- verification trail: `shell: py -m pytest test_ara.py -q`; `shell: py -m pytest test_ara.py -q`; `shell: py -m pytest test_ara.py -q; if (-not (Test-Path notlar)) { New-Item -ItemType Directory n`
- tools: read_file×3, shell×3, write_file×2, grep×2, kos×1, edit_file×1
- ! excluded from grading (untouched pre-turn files): 13
