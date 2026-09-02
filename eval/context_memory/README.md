# Memory recall benchmark

Measures the recall stack at scale: 100 memories + 60 conversation
episodes, 70 queries across seven types (exact, paraphrase, synonym,
numeric, continuation, empty, trap). Reported: hit-rate, coverage,
precision, silence-on-trap, tokens per query, latency.

```bash
py eval/context_memory/scale_bench.py
```

The bench's parametric copy of the selection logic is asserted equal to
the product's `select_prime` on every query — if the product drifts, the
bench fails instead of measuring the wrong thing.

## Life benchmark (yasam_bench.py)

The scale bench above measures a single turn. The life bench measures the
memory **over days**: a frozen 90-virtual-day scenario (`yasam_dataset.json`,
333 events) replayed with an injected virtual clock, so decay, reinforcement
and correction become observable.

```bash
py eval/context_memory/yasam_bench.py --etiket taban
py eval/context_memory/yasam_bench.py --etiket f1 --taban taban
py eval/context_memory/yasam_bench.py --kapat aktivasyon --etiket f1-ablasyon
py eval/context_memory/yasam_bench.py --tablo
```

Event sets: A stable facts · B correction chains · C one-off noise ·
D reused procedures · E context clash (same words, different project) ·
F traps (nothing should surface) · G long silence · H conversation dumps.

Reported: prime precision/recall, forbidden-record leakage, silence on
traps, stale/fresh records in the soul, tokens per turn and per session,
return-after-silence recall, and p95 latency at 50k nodes. Reports land in
`docs/charts/yasam-<label>.{json,md}`; the running phase ledger is
`docs/hafiza-fazlar.md`.

Like the scale bench, the measured path is the product's own
(`loop.select_prime`, `Mind.soul`) — no copied selection logic.
