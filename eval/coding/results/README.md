# Raw results

Per-run JSON produced by the runner. Files cited by the public
benchmark report (docs/benchmark-2026-08.md in the release repo):

| File | What it is |
|---|---|
| `20260828T155549Z…` | first three-task comparison sweep |
| `20260828T163730Z…` | three-task sweep after the harness repairs |
| `20260828T192350Z…` | release gate: the two remaining hard tasks |
| `20260828T224624Z…` | nine-task sweep, first full pass |
| `20260828T230330Z…` | nine-task ×2 sweep (the report's neo column) |
| `20260829T050710Z…` + `20260829T053256Z…` | confirmation sweep after the test-coverage rule (o2 re-run merged) |

Each task entry carries `tum_puanlar` (all repetition scores) and a
`davranis` block: model calls, tool errors, prompt/cache tokens, cost.

Note: runs up to 2026-08-29 predate the rig's English port — their task ids
(`k1-modul`, `o1-rapor`, …) and field names (`davranis`, `tum_puanlar`) are
the original Turkish schema. Newer runs use the English schema
(`behavior`, `all_scores`, task ids like `k1-module`).
