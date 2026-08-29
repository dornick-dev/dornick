# Coding Benchmark Report

**Run:** 20260829T100220Z · **Model:** `z-ai/glm-5.3-flash` · **Repetitions:** 2 · **Rig:** `eval/coding/` (external gate + isolated instance)

The score has four axes: **works** 40 · **requested scope** 25 · **code health** 20 · **test quality** 15. An unmeasurable axis also leaves the denominator; if the brief did not ask for the work (*not requested*) it is measured but not scored. The score column is normalised to 100.

## Score breakdown

| task | difficulty | language | works (40) | scope (25) | health (20) | tests (15) | **score** |
|---|---|---|---|---|---|---|---|
| z1-search | hard | python | 40.0 | 25.0 | 20.0 | 9.0 | **94.0** ±2.3 |

`*` = the brief did not ask for this; measured, reported, not scored.

## Behaviour metrics (never scored)

| task | turn finished | tool calls | tool errors | duration s | tokens (in/out) | cost $ | self-verified | wrote plan | broken deliveries |
|---|---|---|---|---|---|---|---|---|---|
| z1-search | **NO** | 9 | 0 | 900.0 | 131875/3316 | 0.0107 | no | no | 0/2 |

**Tasks graded before their turn finished:** z1-search. Their scores measure whatever was in the workshop when time ran out, not the agent's FINISHED work — biased downward.

**Mean score:** 94.0/100 (1 tasks measured)

**Not run:** k1-module, k2-cli, k3-repair, o1-report, o2-service, o3-feature, z2-panel, z3-hidden-bug

## How solid are these numbers?

Every task ran 2 times; the ± in the score column is the between-run spread (half of min–max). Differences smaller than the spread are not improvements.

Isolation: every run happened in its own temp workspace, with an **empty mind**, on its own neo instance. The user's memories do not ride along — this rig measures the coding pipeline, not memory's contribution to coding.

## Evidence

### z1-search — Note search tool with SQLite persistence

- **works: 40.0/40**
  - `+ ara.py exists (5p) — ara.py`
  - `+ ekle runs (12p) — exit 0; 6 dosya indekslendi (C:\Users\user\AppData\Local\Temp\neocp-eval-z1-search-g98wk2_l\atolye\indeks.db).`
  - `+ SQLite file created (8p) — indeks.db`
  - `+ bul runs in a separate process (15p) — exit 0; 1 not eslesti (tum kelimeleri icerenler ustte): pompa-katalog.txt: ...edek parca: rulman, salmastra, motor mili.`
- **requested scope: 25.0/25**
  - `+ single word finds the right note (8p) — «salmastra» → expected pompa-katalog; output: '1 not eslesti (tum kelimeleri icerenler ustte):\n  pompa-katalog.txt: ...edek parca: rulman, salmastra, motor mili.\n\n'`
  - `+ multi-word: full match ranks first (10p) — «rulman titresim» → kuyu-bakim at 50, pompa-katalog at -1`
  - `+ missing word invents nothing (7p) — «helikopter» → output: 'Hicbir notta bulunamadi: helikopter\n\n'`
- **code health: 20.0/20**
  - `~ clean syntax (8.0/8p) — 2/2 files`
  - `~ size/complexity (6.0/6p) — clean`
  - `~ no duplication (6.0/6p) — repeated lines 0%, 0 recurring blocks`
- **test quality: 9.0/15**
  - `- tests green (6p) — F.F... [100%] ================================== FAILURES =================================== _________________________ `
  - `~ test count (4.0/4p) — 6 tests found`
  - `~ critical path covered (3.0/3p) — 2/2: ekle, bul`
  - `~ assertions substantive (2.0/2p) — 14 assertions, 0 freebies`
- tools: list_dir×2, read_file×2, write_file×2, edit_file×2, kos×1
- ! gate: tur zaman aşımına uğradı
- ! excluded from grading (untouched pre-turn files): 13
- ! 1 leftover processes killed before grading
