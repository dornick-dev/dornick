# Raw results

Per-run JSON produced by `kosucu.py`. Files cited by the public
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
