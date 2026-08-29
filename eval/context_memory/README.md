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
