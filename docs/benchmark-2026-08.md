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

**Three methodological caveats, before anything else** (raised in external
review, and correct):

1. **The benchmark is saturated.** All three harnesses score 100 on seven
   of the nine tasks. A suite this easy cannot rank the harnesses; it can
   only say all three clear this difficulty. A harder task band
   (target scores 60–90) is the roadmap's next item.
2. **neo's number is in-sample.** Several of neo's harness rules
   (the negative-requirement gate, the reasoning-effort cap) were written
   while looking at failures *on these very tasks*. OpenCode and Claude
   Code received no such tuning round. Until a held-out task set exists,
   896.7 is an in-sample figure and should be read as such.
3. **~1 point of the 2.4-point spread was a grader artifact.** The
   assertion counter missed the whole unittest family
   (`assertTrue`, `assertIn`, …), so unittest-style suites lost test
   points for style, not quality. The ruler is fixed
   ([`grading.py`](../eval/coding/grading.py)); published numbers were
   left as measured, with this note.

Given all that, the sentence this data actually supports is narrower and
still worth having: **on nine tasks that all three harnesses handle, neo
delivers the same quality as OpenCode on the same ~free model at half the
wall time and half the cost, and never burns a run on a reasoning
spiral.**

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

The only fair speed comparison is between the same-model lanes: **neo is
~2× faster and ~2× cheaper than OpenCode**, with an 85% prompt-cache hit
rate (65–92% per task). Claude Code's 316 s is a different model's token
rate — shown for context, not compared.

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
* neo's numbers trace to run JSONs in
  [`eval/coding/results/`](../eval/coding/results/) with per-run
  behaviour columns (model calls, tool errors, cache tokens, cost).
  The competitor lanes' raw data — OpenCode's own JSON event streams and
  the Claude-lane deliverables scored by this repo's grader — are in
  [`results/competitors/`](../eval/coding/results/competitors/), and the
  memory experiments' raw outputs in
  [`results/memory-experiments/`](../eval/coding/results/memory-experiments/).
  One honest gap remains: the Claude lane's token/cost cannot be metered
  (different billing), and its wall time was stopwatch-measured.

## Addendum — 29 Aug harness iteration, measured honestly

After an external review of the speed gap, three levers were built and a
fresh ×2 sweep was run (same model, same 9 tasks): a `read_many` tool
(array-schema batch reads), a frozen first-turn workspace briefing, and
per-call time/prime/error metrics in the behaviour extractor.

| sweep (mean of 2 reps) | 29 Aug morning | 29 Aug after changes |
|---|---|---|
| quality (sum, 9 tasks) | 897.3 | **887.2** (best-rep sum 900.0 — first all-100 sweep) |
| wall time (best reps) | 577 s | 935 s |
| model calls | 63 | 109 |
| tools per call | 0.98 | 0.99 |
| cache hit | 89.8% | 89.9% |
| cost | $0.083 | $0.149 |

**The honest negative first:** `read_many` was never called — zero uses
across 20 runs. The schema-beats-instruction bet did not move this flash
model on its own; a cross-reference hint was added to `read_file` after
the sweep and remains unmeasured. Calls and wall time went **up**, driven
by two tasks (z2 spent 19 browser calls on form verification, o2 took
three reruns — below); flash-class variance still dominates single-sweep
deltas, so none of this is read as a regression caused by the changes —
but it is certainly not the hoped ~2.0 tools/call either.

**What the new metrics bought immediately:**

* **Time split:** 833 s of the 935 s wall (89%) is model latency; tool
  execution is 102 s. The speed lever is round-trips and per-call
  generation time, not tool speed — now measured, not assumed.
* **Error patterns:** the top recurring tool error ("working directory
  does not exist: atolye\X", 3× per sweep) was a workshop-prefix trap in
  the shell's cwd — fixed and regression-tested the same day.
* **A grading bug found and killed:** o2-service graded "port held —
  cannot measure" three times. Root cause chain: the agent's own detached
  service outlived the instance, the leftover sweep ran *after* grading,
  matched only absolute paths, and then only top-level filenames. All
  three links fixed (sweep before grading, relative launches matched,
  recursive names), each verified live with a planted survivor; o2 then
  measured 100.0.

**B5 — discovery downshift, built and measured the same day.** For
small/fast models, a call that follows a purely read-only tool batch now
runs at `reasoning: low` with a 4096-token output cap; a call that hits
the cap (`finish=length`) is retried once at full budget, so quality is
never traded for the cap. Measured on the two slowest tasks (z1, z2, x2
reps each, plus a second z1 pair): **per-call model time fell ~28%**
(z1 11.9 -> 8.5 s/call, z2 6.1 -> 4.4) with quality held (z2 99.9,
z1 means 92.5/96.4). Total wall time did *not* improve in this sample —
call counts swung 16/51 in one pair and 8 in the next, and z1 shows a
pre-existing slow mode (a provider-side call hanging into the 900 s
ceiling) in both arms. Honest verdict: the per-call gain is real, the
totals are still owned by flash-class variance; the next lever is a
per-call (not per-turn) timeout fed by the new time-split metrics.

The prime-injection gate also changed after the memory review: the
unconditional-top exemption in spontaneous recall now applies only to
young minds (<30 records) — the source of the +9% prompt-token cost on
unrelated work — mirrored in the scale bench with a guard that asserts
the copy equals the product.

*Screenshots of the product: [gallery](gallery/README.md) · Drive neo from
your own harness: [the gate](gate.md).*
