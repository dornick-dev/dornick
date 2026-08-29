# Evaluation rigs

Two measurement rigs live here. Everything the benchmark report
([docs/benchmark-2026-08.md](../docs/benchmark-2026-08.md)) claims comes
out of these — you can re-run all of it.

| Folder | What it measures | Entry point |
|---|---|---|
| [`coding/`](coding/) | Does an agent inside neo **deliver working software**? Nine tasks (easy→hard, Python/Node/PHP); the grader executes the delivered code. | `py eval/coding/kosucu.py --gorev hepsi --tekrar 2` |
| [`context_memory/`](context_memory/) | Recall quality of the memory system at scale (100 memories / 70 queries): hit-rate, precision, silence on trap questions. Guards that the benchmarked path **is** the product path. | `py eval/context_memory/scale_bench.py` |

Notes:

* Each coding task runs in its own temp workspace with an **empty mind**
  and its own isolated neo instance — nothing touches your data.
* Source identifiers are Turkish (the project's working language);
  behaviour columns in the result JSON are documented in
  [`coding/README.md`](coding/README.md).
* `coding/sonuclar/` holds the raw per-run JSON the report cites.
