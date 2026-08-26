# neo coding evaluation (2026-08-26)

**Question:** what happens when you hand neo a coding task — and does neo's
harness (tools + running tests + fixing its own mistakes) actually matter?

## Setup

neo received three tasks through the **external gate** (`POST /api/gate` —
the API that writes into the chat like a user and returns the full output).
For each task neo worked in its own workshop: wrote the files, ran the tests
itself, fixed what was red, and reported back. Everything was audited
independently: all 30 tests re-run, the CSV counted row by row, the CLIs
executed by hand.

| Task | Contents | neo's time |
|---|---|---|
| Easy | Turkish-aware text statistics + tests | 76 s |
| Medium | CSV expense report generator + CLI + tests | 90 s |
| Hard | TF-IDF search engine + SQLite persistence + CLI + 10+ tests | 99 s |

Two comparisons were run:

1. **System comparison:** the evaluator (Claude, on its own model) solved the
   same tasks. Different models — a comparison of two systems.
2. **Fair experiment (same model):** neo's configured model that day
   (`openrouter/gpt-5.6-luna`) was also prompted **bare, one-shot, over the
   raw API** — no tools, no test runs, no second chances. Any gap is the
   harness, not the model.

Rubric: Works 40 · Coverage 25 · Code quality 20 · Test quality 15 = 100.

## Results

| | Easy | Medium | Hard | Total |
|---|---|---|---|---|
| **neo** (luna, inside the harness) | 97 | 98 | 99 | **294/300** |
| Claude (evaluator, own model) | 96 | 96 | 97 | 289/300 |
| Same model, bare one-shot | 85 | 96 | 99 | 280/300 |

Highlights:

- **neo's code quality matched its evaluator** — and led in places: `Decimal`
  for money, cosine-normalized smoothed TF-IDF for search were neo's calls.
- **The harness proof lives in the easy task:** the bare model reached for
  `casefold()`, fell into the Turkish I/İ trap, and **shipped broken code**
  (its own test suite had 1 red — the test was right, it just couldn't run
  it). The same model inside neo made the same first-pass mistake — then ran
  the tests, caught it, and fixed it. Same model: +14 points inside the
  harness, and zero broken deliveries.
- **A symmetric human note:** the evaluator also got two first-pass test
  expectations wrong (Turkish collation) and fixed them after running.
  The write-run-catch-fix loop worked on every side; that loop's value is
  exactly what this measured.

## Honesty notes

- Single run, single grader; treat ±2 point differences as noise.
- The first comparison uses different models by design ("neo the system vs
  the evaluator's system"); the same-model experiment was added to close
  that gap.
- Task prompts and grading were written the same day as the run; the tasks
  are local enough (Turkish requirements, workshop layout) not to appear
  verbatim in any training set.
