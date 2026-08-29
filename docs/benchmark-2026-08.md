# The Benchmark — August 2026

One page, everything measured, nothing mocked. Three harnesses, nine
coding tasks, one grader that **executes the delivered code**. Raw data:
[`eval/coding/results/`](../eval/coding/results/). Re-run it yourself:
[`eval/`](../eval/README.md).

## 1 · Quality

![Total scores: Claude Code 897.3, neo 896.7, OpenCode 894.9 out of 900](charts/scores.png)

| Harness | Model | Total /900 |
|---|---|---|
| Claude Code (reference) | Anthropic frontier | 897.3 |
| **neo** | `z-ai/glm-5.3-flash` (~free) | **896.7** |
| OpenCode 1.2.27 | `z-ai/glm-5.3-flash` (same) | 894.9 |

**Verdict: a three-way tie in quality.** The 2.4-point spread is smaller
than the run-to-run variance of one hard task (±1.7 between neo's two
repetitions of the same task). Two narrower claims *are* supported:

* A ~free flash model inside neo's harness matches the frontier reference
  on delivery quality.
* neo beats the same-model competitor — on OpenCode's best run (its worst
  burned a 32,000-token reasoning spiral and scored 0 on a hard task; neo
  caps that failure mode).

A confirmation sweep after the last harness rule landed scored 896.8 —
the tie holds. We do not claim a pass we did not measure.

<details><summary>Per-task scores (0–100, higher is better; neo = mean of 2 reps)</summary>

| Task | difficulty | Claude Code | OpenCode | neo |
|---|---|---|---|---|
| k1 TCKN validator + tests | easy | **100.0** | 98.0 | 99.0 |
| k2 todo CLI (Node) | easy | 100.0 | 100.0 | 100.0 |
| k3 invoice repair (PHP) | easy | 100.0 | 100.0 | 100.0 |
| o1 CSV sales report | medium | 100.0 | 100.0 | 100.0 |
| o2 short-link HTTP service | medium | 98.7 | **100.0** | 99.3 |
| o3 lending feature (Node) | medium | 100.0 | 100.0 | 100.0 |
| z1 SQLite note search | hard | **98.7** | 97.0 | 98.3 |
| z2 PHP admin panel + auth | hard | **100.0** | 99.9 | **100.0** |
| z3 hidden-bug repair | hard | 100.0 | 100.0 | 100.0 |

</details>

## 2 · Efficiency

![Wall time and real cost: Claude 316s, neo ~690s ($0.05), OpenCode 1428s ($0.10)](charts/efficiency.png)

The remaining gap to the reference is **speed, not correctness** — and it
is mostly the model's token rate. Between the same-model lanes, neo is
~2× faster and ~2× cheaper than OpenCode, with an 85% prompt-cache hit
rate (65–92% per task).

## 3 · Memory

![Memory experiments: seeded facts −24%, warm continuation −38%, junk pollution +69% before the seal and 0% after](charts/memory.png)

Claim under test: *recall should cut cost without hurting quality.*
Quality was unchanged in **all four** experiments; only cost moved.

* **Seeded true facts** (4 real workspace facts vs empty mind, same task
  ×2): the agent skipped a discovery call — **−24% prompt tokens**, and in
  one repetition memory carried the score from 82 to 100.
* **Warm continuation** (the end-of-run capsule neo writes automatically):
  a new session continuing the work ran **5 calls / 26 s vs 8 calls /
  62 s** cold — −38% tokens. Boundary: this pays on *discovery*, not on
  edits — a file you are about to edit must be read regardless.
* **Pollution attack** (50 irrelevant memories): junk used to leak into
  the prompt through a single-stem overlap (+69% tokens on the worst
  rep). The gate is sealed; the same attack now injects **zero** blocks,
  with recall of true positives unchanged (hit-rate 0.78 = ungated;
  precision 0.54 → 0.64; silence-on-trap 0.38 → 0.62 on the
  [100-memory/70-query bench](../eval/context_memory/README.md)).
* **Memory ON across the whole 9-task suite** (one persistent mind, tasks
  unrelated to each other): quality parity with the empty-mind run
  (99.6% vs 99.7% on the 8 comparable tasks) at ~+9% tokens — accumulated
  memory of *unrelated* work neither helps nor hurts delivery. Memory
  earns its keep on **related** work, which is what the two green bars
  measure.

## 4 · What the harness adds over the raw model

Each mechanism exists because a measured failure demanded it; each has a
regression test in [`tests/`](../tests/):

1. **Delivery gates** — "done" is bounced once when a written CLI was
   never executed, a written test file was never run (a red suite got
   shipped exactly this way), the task list has open items, or the last
   run was red. The negative-requirement rule ("prove the *forbidden*
   paths too") took the auth-panel task from 55.9 to 100.
2. **Reasoning-effort cap for flash-class models** — uncapped thinking
   turned an 11-call task into a 900-second timeout and, in the
   competitor, a 32k-token spiral delivering nothing.
3. **Prompt-cache markers** — 65–92% cache-read measured on OpenRouter.
4. **Teach-first tool errors** — known shell traps are documented in the
   tool description *before* the first failure; repeated unknown errors
   become persistent lessons attached to the next occurrence.
5. **Whitespace-tolerant edits** — CRLF/trailing-space/uniform-indent
   drift no longer wastes turns; uniqueness is still required.

## Method, honestly

* neo and OpenCode: same model, separate API keys, one fresh workspace and
  an **empty mind** per task (except the memory-ON sweep above), default
  settings, neo from source.
* Claude Code is the evaluating agent itself on its own model — a
  reference line, not a same-model comparison. Its lane was worked
  honestly: same briefs, no peeking at graders, scored by the same rubric.
* neo's headline is a **mean of 2 repetitions**; no best-of anywhere.
  Flash-class variance is real — treat any single run (including these)
  with suspicion.
* Every number traces to a JSON in
  [`eval/coding/results/`](../eval/coding/results/) with per-run
  behaviour columns (model calls, tool errors, cache tokens, cost).

*Screenshots of the product: [gallery](gallery/README.md) · Drive neo from
your own harness: [the gate](gate.md).*
