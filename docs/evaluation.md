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
