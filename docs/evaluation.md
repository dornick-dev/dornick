# neo coding evaluation (2026-08-26/27)

**Questions:** what happens when you hand neo a coding task? How much of the
result is the model, and how much is neo's harness (tools + running tests +
fixing its own mistakes)?

## Setup

neo received three tasks through the **external gate** (`POST /api/gate` —
the API that writes into the chat like a user and returns the full output).
For each task neo worked in its own workshop: wrote the files, ran the tests
itself, fixed what was red, and reported back. Everything was audited
independently: every test suite re-run by the grader, CSVs counted row by
row, CLIs executed by hand.

| Task | Contents |
|---|---|
| Easy | Turkish-aware text statistics + tests |
| Medium | CSV expense report generator + CLI + tests |
| Hard | TF-IDF search engine + SQLite persistence + CLI + 10+ tests |

The full design is a **2×2 matrix plus a reference point**: two models
(`openai/gpt-5.6-luna` and `anthropic/claude-fable-5`), each run twice —
inside neo's harness, and bare over the raw API in a single shot (no tools,
no test runs, no second chances). The grader (Claude, running on
claude-fable-5 with its own harness) also solved the tasks as a reference.

Rubric per task: Works 40 · Coverage 25 · Code quality 20 · Test quality 15.

## Results — the matrix

| | inside neo's harness | bare one-shot API |
|---|---|---|
| **gpt-5.6-luna** | **294**/300 | 280/300 |
| **claude-fable-5** | **294**/300 | 261/300 |

Reference: the grader (claude-fable-5 + its own harness) scored 289/300.

Per-task detail:

| Run | Easy | Medium | Hard | Notes |
|---|---|---|---|---|
| neo + luna | 97 | 98 | 99 | `Decimal` for money; cosine TF-IDF |
| neo + fable | 98 | 97 | 99 | 33 tests total; "no results" UX; smoothed IDF |
| bare luna | 85 | 96 | 99 | **shipped the Turkish-casing bug** (`casefold()`) |
| bare fable | 98 | 97 | **66** | **shipped an `UnboundLocalError`** that broke 10 tests + the CLI |
| grader | 96 | 96 | 97 | two first-pass test-expectation bugs, fixed after running |

## What the matrix says

1. **The harness equalizes the models.** Inside neo, both models landed on
   exactly 294/300 — different strengths, same ceiling. Bare, they diverged
   by 19 points and *each shipped broken code in one task*: luna fell into
   the Turkish I/İ trap, fable typo'd a variable in a five-file project and
   took 10 tests plus the CLI down with it. Neither could see its own bug,
   because neither could run anything.
2. **The write-run-catch-fix loop is the product.** Both models made
   first-pass mistakes inside neo too — then ran the tests, caught them,
   and fixed them before reporting. Bare, the same class of mistake went
   straight to the user. So did the grader's own two test-expectation
   mistakes, for symmetry — caught the same way, by running.
3. **At this task scale, harness choice mattered more than model choice.**
   Model swap changed the bare score by 19 points; harness on/off changed
   fable's score by 33.

## A bug this evaluation caught

The first fable-in-neo attempt failed instantly: the Anthropic API only
accepts `system` roles at the start of the message array, while neo injects
mid-conversation system notes (goal sync, harness notes). Every request
returned HTTP 400 — a real hole in the "model-agnostic" claim, invisible
until a Claude-family model was actually selected. Fixed in
`backends/translate.py` (mid-conversation system notes now travel as tagged
user notes, valid for every provider) with a regression test. Evaluations
that exercise real paths find real bugs.

## Part two: the automated rig (2026-08-27)

The matrix above was graded by hand, which does not scale and cannot be
re-run after a change. So it was turned into a rig that lives in the repo:
[`eval/coding/`](../eval/coding/README.md). Nine tasks across easy/medium/hard
in Python, Node and PHP; each runs in its own temp workspace with **an empty
mind** and its own neo instance, driven through the gate. The grader then
enters the workshop and **executes the code** — imports the module, starts the
server, POSTs to the endpoint, logs in to the panel.

Two rules keep the number honest:

- **An axis that could not be measured leaves the denominator** — otherwise
  "I couldn't measure it" and "it failed" collapse to the same score.
- **No `works` axis, no score at all.** This rule came from a bug: a task
  scored 100.0 while both load-bearing axes were unmeasured.

### Baseline — `minimax/minimax-m2.7`, all 9 tasks

| Task | Difficulty | Works (40) | Coverage (25) | Health (20) | Tests (15) | **Score** |
|---|---|---|---|---|---|---|
| k1-modul | easy/py | 40.0 | 15.0 | 20.0 | 9.0 | **84.0** |
| k2-cli | easy/node | 40.0 | 25.0 | 20.0 | — | **100.0** |
| k3-tamir | easy/php | 40.0 | 25.0 | 20.0 | — | **100.0** |
| o1-rapor | med/py | 40.0 | 25.0 | 20.0 | — | **100.0** |
| o2-servis | med/py | 40.0 | 25.0 | 18.7 | 9.0 | **92.7** |
| o3-ozellik | med/node | 40.0 | 25.0 | 20.0 | — | **100.0** |
| z1-arama | hard/py | 25.0 | 7.0 | 20.0 | 15.0 | **67.0** |
| z2-panel | hard/php | 40.0 | 20.0 | 14.0 | — | **87.1** |
| z3-gizli-hata | hard/py | 40.0 | 25.0 | 20.0 | — | **100.0** |

**Average 92.3/100.** (`—` = the prompt didn't ask for tests: measured,
reported, excluded from the score.)

### What the behavioural columns say — and they say more than the score

The rig also records non-scoring behaviour, and this is where the real gaps are.

**1. Green tests are not a working product.** `z1-arama` is the sharpest result
in the whole set. The agent shipped 14 tests, all passing, 18 assertions, none
of them free — and code health 20/20. And the CLI the prompt actually asked
for does not work: `py ara.py bul "salmastra"` prints its own usage line and
exits 1, for every query. The tests covered the internal functions; nothing
ever exercised the entry point a user would type. The agent verified itself
and was satisfied.

This one matters because it survives the obvious fix. A gate that refuses to
finish on a red suite does nothing here — the suite was green. The only thing
that catches it is running the delivered thing the way the user will run it,
which is exactly what the grader does and the agent didn't.

**2. Three of nine turns never finished.** `o2-servis`, `z1-arama` and
`z3-gizli-hata` all hit the 900-second ceiling; their scores measure whatever
was lying in the workshop when the clock ran out, so they are biased downward.
All three are the medium/hard end — the agent does not converge on hard work
inside fifteen minutes.

**3. Red tests shipped twice, and a plan never once.** `k1-modul` delivered a
module rejecting all five valid inputs while its own suite showed `FFFFF`;
`o2-servis` delivered with one of eight failing. In both, the agent ran the
suite, saw red, and said done. And across all nine tasks, a plan was written
**zero** times — the system prompt asks for one on multi-file work, and
prompt-level advice did not survive contact with a single task.

Also worth naming: `z2-panel` shipped 31% duplicated lines across 38 repeated
blocks, and one of its four pages silently falls back to the login form after a
*successful* login — a "does it return 200?" check would have called it green.
And 39 malformed tool calls across the nine tasks, roughly a tenth of all calls.

Finding 3 is why the following wave converted prompt advice into harness
reflexes: a plan step the loop performs rather than requests, and a done-gate
that refuses to close a turn on a red suite. The table above is the **before**
measurement, kept deliberately so the after has something to be compared
against. Finding 1 is not yet addressed and is the most valuable open problem
in this file.

### Honesty about this rig

Single run per task, so ±5 points is noise; only a >15-point move means
anything. Each run starts from an empty mind, so this measures the coding
pipeline — **not** what memory contributes to coding. Rows are marked `†` in
the generated report when they were inherited from an earlier run the same day;
all rows come from the same build.

## Honesty notes

- Single run per cell, single grader; treat ±2 points as noise. Bare-fable's
  66 is one unlucky variable name — another sample might land elsewhere,
  which is precisely the point about one-shot fragility.
- The fable-in-neo run happened after the luna runs; neo's memory contained
  episodes about the earlier exam. The earlier solution folders were removed
  before the run so nothing could be copied, and tool traces show the work
  was done from scratch, but mild familiarity priming cannot be excluded.
- Bare runs used bounded reasoning (fable requires reasoning; capped at
  3,000 tokens) and an output format the model was told to follow; the
  grader extracted files mechanically.
- Task prompts and grading were written the same day as the runs; the tasks
  are local enough (Turkish requirements, workshop layout) not to appear
  verbatim in any training set.
