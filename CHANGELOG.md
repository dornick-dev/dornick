# Changelog

## 1.1.0 — 2026-08-29

Review hardening. Night-school privacy gate (hosted labeling now behind an
explicit consent switch; local models unchanged), held-out personal exam +
stock-anchored drift floor, young-mind gate on spontaneous recall. Speed
work measured honestly: per-call time/prime/error metrics, discovery
downshift (**per-call model time −28%** on the slowest tasks), per-call
silence window for hanging provider calls, `read_many` batch reads +
workspace briefing (not yet adopted by the flash model — stated plainly).
First sweep with every task's best repetition at 100/100; a grading
port-poisoning chain and a shell working-directory trap fixed. Full
detail: [the benchmark page](docs/benchmark-2026-08.md).

## 1.0.0 — 2026-08-29

The benchmark release. neo's harness now measures as a statistical tie with
Claude Code in delivery quality on a nine-task suite (897.3 vs **896.7** vs
OpenCode's 894.9 out of 900) — on a ~free flash model, ahead of the
same-model competitor. Full method, raw data and honest caveats:
[docs/benchmark-2026-08.md](docs/benchmark-2026-08.md).

* **Memory that measurably pays.** Seeded true facts cut a task's prompt
  tokens 24% and rescued a failing rep to 100; a mechanical end-of-run
  capsule made a warm continuation **twice as fast** (−38% tokens) with
  equal correctness. A 50-junk-memory pollution attack that leaked into
  the prompt through a single-stem overlap is sealed — hit-rate unchanged,
  precision and trap-silence up.
* **Tool errors become lessons.** A repeated error pattern is written to
  memory once and attached to the same error in future sessions
  ("[Memory] …"); known PowerShell traps are taught in the tool
  description *before* the first failure.
* **Two new delivery gates.** A written test file that was never run
  blocks the "done" claim (a red suite got shipped exactly this way), and
  negative requirements ("must reject", "must redirect") must be proven
  with a command — the PHP auth panel went 55.9 → 100 on this rule alone.
* Screenshot gallery: [docs/gallery](docs/gallery/README.md).

## 0.x — 2026-08-26 → 28 (pre-1.0, condensed)

Nine releases in three days, kept here as a digest; the git history has
every detail. Highlights in order: first public cut (memory graph, soul,
tools); automations as node graphs with live-lit steps and limited
self-repair; the local base rewriter (10.8M, byte-level TR/EN) shipping
in-product with the nightly fine-tune loop and its exam gate; session
titles written by the model; per-chat model pinning; viewer tabs; the
connectors directory; shell hardening (stdin, process-tree kill,
taught-first traps); whitespace-tolerant edits; the reasoning-effort cap
that took the hard tasks off the 900-second ceiling; and the release gate
that requires all benchmark tasks green on the build.
