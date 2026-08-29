# Three-harness benchmark — Claude Code · OpenCode · neo (Aug 28–29, 2026)

Nine coding tasks (3 easy, 3 medium, 3 hard — Python, Node, PHP), three
harnesses, one grader. Everything here is measured; nothing is mocked.
The task set, grader and per-run behaviour data live in this repo under
[`eval/coding/`](../eval/coding/) — you can re-run all of it.

## Method — and its honest limits

- **neo** and **OpenCode** ran the *same model* (`z-ai/glm-5.3-flash` via
  OpenRouter) with separate API keys, one fresh workspace and an **empty
  memory** per task. neo ran from source. OpenCode ran its installed CLI
  (1.2.27) with default settings.
- **Claude Code** is the evaluating agent itself, on its own model
  (Anthropic Fable). It cannot run on OpenRouter, so this lane is a
  *reference line*, not a same-model comparison. Its lane was worked
  honestly: same briefs, no peeking at graders, deliverables scored by the
  same rubric.
- The grader **executes** the delivered code (CLI runs, HTTP endpoints,
  auth redirects, test suites) rather than checking files exist. Scores
  are 0–100 per task.
- neo's score is the **mean of 2 repetitions** per task; the other lanes
  ran once. Flash-class models have real run-to-run variance (we measured
  a 32k-token reasoning spiral one day and a clean 97 the next on the same
  task) — single-run numbers deserve suspicion, including these.

## Scores

Each task is scored 0–100 by the same grader; **higher is better**. Bold
marks the best score in the row.

| Task | difficulty | Claude Code | OpenCode | neo (mean of 2) |
|---|---|---|---|---|
| k1 TCKN validator + tests | easy | 100.0 | 98.0 | 99.0 |
| k2 todo CLI (Node) | easy | 100.0 | 100.0 | 100.0 |
| k3 invoice repair (PHP) | easy | 100.0 | 100.0 | 100.0 |
| o1 CSV sales report | medium | 100.0 | 100.0 | 100.0 |
| o2 short-link HTTP service | medium | 98.7 | 100.0 | 99.3 |
| o3 lending feature (Node) | medium | 100.0 | 100.0 | 100.0 |
| z1 SQLite note search | hard | 98.7 | 97.0 | 98.3 |
| z2 PHP admin panel + auth | hard | 100.0 | 99.9 | 100.0 |
| z3 hidden-bug repair | hard | 100.0 | 100.0 | 100.0 |
| **Total** | | **897.3** | 894.9 | **896.7** |

**Read this as a statistical tie at the top.** The gap between the three
lanes (2.4 points out of 900) is smaller than the run-to-run variance of a
single hard task (z1 swung ±1.7 between neo's two reps). The honest claims
are narrower and more interesting:

- A ~free flash model inside a disciplined harness delivers the same
  *quality* as the reference agent on these tasks. The difference that
  remains is **efficiency**, not correctness.
- neo beat OpenCode on the same model — and did it after OpenCode's
  strongest run of the night.

**Post-release confirmation sweep.** After the test-coverage delivery rule
landed, the full 9-task ×2 sweep was repeated: **896.8** — the tie holds
(and an amusing lesson surfaced: the first attempt scored o2 as
unmeasurable because a zombie process from a *previous* run still held the
service port; the fix was the same process-tree hygiene this report
preaches). We do not claim a pass we did not measure.

## Efficiency (same-model lanes)

| | OpenCode | neo |
|---|---|---|
| Wall time, 9 tasks | 1428 s | ~690 s |
| Prompt tokens | 1,817,032 (1,447,680 cached) | 1,342,058 (~85% cached) |
| Real spend (provider billing) | $0.097 for the 9-task sweep | $0.105 for the 9-task ×2 = 18 runs |
| Worst single behaviour seen | 32,000-token reasoning spiral, 0 files written (previous sweep, z1) | stdin-inheriting child hung a turn 7.5 min (previous sweep, o1 — root-caused and fixed same night) |

Claude Code's lane: 316 s of wall time across the 9 tasks, ~40 model calls;
its token/dollar cost runs on a different meter and is not comparable.

## What the harness does that the raw model doesn't

Every mechanism below exists because a measured failure demanded it, and
each has a regression test:

1. **Delivery gates.** "Done" claims are bounced once when: a written CLI
   was never executed; a written *test file* was never run (a red test
   suite got shipped exactly this way); the task list still has open
   items; the last run was red. z2 went 55.9 → 100 the night the negative-
   requirement rule ("prove the *forbidden* paths too") landed.
2. **Reasoning-effort cap for flash-class models.** Uncapped high-effort
   thinking turned an 11-call task into a 900-second timeout, and burned a
   full 32k-token reasoning spiral in a sibling harness. Quality came from
   the gates, not the thinking budget.
3. **Prompt-cache markers** (first system block + last two messages):
   65–92% cache-read rates measured on OpenRouter.
4. **Teach-first tool errors.** Known shell traps are written into the
   tool description; unknown ones that repeat become persistent *lessons*
   and get attached to the error next time ("[Memory] …").
5. **Whitespace-tolerant edits.** 7 of 18 tool errors in one hard run were
   anchor mismatches on correct content; the editor now tolerates CRLF,
   trailing-space and uniform indent drift — uniqueness still required.

## Memory: measured, not vibes

The claim to test: *recall should cut cost without hurting quality.*

**Seeded-memory experiment** (same task, 2 reps each): an agent whose mind
held four true facts about the workspace skipped a discovery call —
**−24% prompt tokens**, and in one rep the memory carried it from 82 to
100 points. An agent whose mind held **50 irrelevant memories** leaked
junk into its context through a single-stem overlap ("ayın" ↔ "ayında"),
**+28–110% tokens**. That leak is now sealed: on rich queries a record
grounded by only one prefix-deduplicated stem no longer primes. Re-run
after the fix: zero junk injected, recall of true positives unchanged
(hit-rate 0.78 = ungated, precision 0.54 → 0.64, silence-on-trap 0.38 →
0.62 on the 100-memory / 70-query bench in
[`eval/context_memory/`](../eval/context_memory/)).

**Warm-start experiment** (capsule): after finishing a task, neo writes a
mechanical capsule (what was asked, files produced, commands verified)
into memory. A *new session* continuing that work: rep 1 no difference
(edit-type follow-ups must read the file anyway), rep 2 **5 calls / 26 s
vs 8 calls / 62 s** cold (−38% tokens, half the time), correctness equal.
Honest summary: memory pays when it substitutes for *discovery*; it cannot
and should not substitute for reading code you're about to edit.

## Reproduce it

```bash
py eval/coding/kosucu.py --gorev hepsi --model z-ai/glm-5.3-flash --tekrar 2
```

Raw per-run JSON (scores, behaviour columns, cache rates) is committed
under [`eval/coding/sonuclar/`](../eval/coding/sonuclar/). Screenshots of
the product taken during this work: [the gallery](gallery/README.md).
