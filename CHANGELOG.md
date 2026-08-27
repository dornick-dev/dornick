# Changelog

## 0.3.0 — 2026-08-27

The coding release. neo could already write code; this version is about
whether the code it hands you **runs** — and about being able to prove it.

### Working in your own project

* **Project mode.** Point neo at any folder and it works there instead of in
  the sandbox `atolye`. Dangerous roots (drive roots, system folders, the home
  directory itself) are refused with a reason; recent projects are remembered.
* **Post-write diagnostics.** Every file neo writes is checked in its own
  language the moment it is written — `compile()` for Python, `php -l`,
  `node --check`, `tsc`, ruff when present. The coverage table is documented
  honestly, including what is *not* checked.
* **A test runner that doesn't guess.** The `kos` tool detects the project's
  real test command from evidence (`package.json` scripts, `pytest.ini`,
  `composer.json`, a `Makefile` target) and runs it. With no evidence it says
  so rather than inventing a command, and it never claims more than
  "this verifies as much as the tests that ran cover".
* **Symbols.** `semboller` finds definitions and usages — Python via `ast`,
  PHP/JS/TS via careful patterns.
* **Deeper browser.** Form fill and submit, console reads, network errors and
  error-page detection, so "the page opened" and "the page works" stop being
  the same answer.

### Your rules over the model's

* **Hooks.** `.neocp/kancalar.json` runs your shell command before or after a
  tool; a non-zero exit vetoes the tool and its stdout is handed to the model
  as the reason. Two decisions make this safe together: hooks run **outside**
  the permission engine (your own rule shouldn't ask your permission, and must
  work in plan mode), and the hook file is **closed to the model**, so it cannot
  delete the fence built to stop it. Closed on two paths: the write tools refuse
  it by path, and any other *mutating* call whose arguments name the file (a
  shell command, say) is refused before the permission gate — that second path
  was a real hole, since `shell` is not a write tool and in `yolo` mode was not
  even asked about. Reading stays allowed: the model should know the rules it
  works under. The boundary is stated honestly in the code — this stops a model
  that finds a hook inconvenient, not one deliberately obfuscating the filename;
  against that, the fence is the permission engine. A timeout blocks; a hook that
  could not be launched is skipped and *says so*, never silently.

### Eyes

* **`read_file` sees images.** A PNG or JPG comes back to the model as an
  actual image instead of a screenful of replacement characters. PDFs return
  page text with a page range; a scanned PDF says "these pages carry no text
  layer — do not guess" instead of returning empty.

### Chat surface

* `/` command book, `@` file mentions with search, a running-tasks ledger with
  stop and drill-in, a "what changed this turn" list with undo, and a budget
  brake that stops a run at the limit you set instead of after it.
* Model text is always visible: only tool steps and harness notes fold into
  the work strip. File paths and `file:line` references are clickable and open
  the viewer at the right line.
* Backup model, session naming and tagging, and search across past transcripts.

### Measurement

* **`eval/coding/`** — nine tasks (Python/Node/PHP × easy/medium/hard), each in
  its own workspace with an empty mind and its own neo instance, driven through
  the gate. The grader executes the delivered code. Baseline: **92.3/100** on a
  mid-tier model, plus the three weaknesses the behavioural columns exposed —
  including one delivery with 14 passing tests and a CLI that fails on every
  query. See [docs/evaluation.md](docs/evaluation.md).

### Fixes

* The external gate's timeout message no longer claims a permission prompt is
  waiting when it isn't (in `yolo` mode every allowed tool logs a permission
  event; only a real `ask` counts now).
* Background server commands log to `.neocp/surec-loglari/` instead of opening
  a console window, and the shell refuses to launch neo from inside neo.
* Killing a timed-out subprocess now kills its whole tree: a 2-second hook
  timeout used to turn into a 60-second wait because the real command survived
  the shell and held the pipes open.
* Malformed tool arguments are validated centrally and reported as a usable
  error, so the model stops concluding a tool is broken and emitting fake
  `<function_calls>` XML at the user.

## 0.2.1 — 2026-08-27

* **Orphaned helpers.** Subagent helpers cut short by an app shutdown
  are now detected at startup: the user and the model are notified
  once, and the orchestra panel is seeded with their "left unfinished"
  state — no more ghost "running" channels after a restart. A second
  launch does not re-announce the same orphan.

## 0.2.0 — 2026-08-27

The overnight wave: conversation clarity, a new settings design and
four core tool capabilities.

* **Conversation clarity.** Tool steps collapse into cards; diffs and
  shell output render as rich cards; smart scrolling stops yanking the
  view while you read; step summaries draw on a wide vocabulary.
* **New settings design.** The settings page moved to a unified visual
  language (`settings.css`); three UI bugs and the welcome screen fixed.
* **Four core tool capabilities.** A `grep` tool (tools/search.py),
  atomic multi-edit, checkpoint + undo, and resilient web search with
  a fallback provider.
* **Goals panel and plan-approval flow.** The agent's goal list is
  visible in the UI; plans go to the user for approval before work
  starts.
* **Artifact system.** Persistent, addressable, updatable deliverable
  pages (`artifacts.py`).
* **Definition-of-done guide.** The agent's "when does work count as
  finished" bar is now systematic.

## 0.1.1 — 2026-08-27

Fixes from the first real end-user installs, plus two new installer
components.

* Installed apps no longer show developer-style `pip install ...` hints.
  The app now detects the installer layout (embedded Python / setup.json)
  and points to the setup wizard components instead.
* Fixed console windows flashing over the app (e.g. right after
  restoring a minimized window): every hidden helper subprocess
  (powershell, netstat, taskkill, wsl, the agent shell) now runs with
  `CREATE_NO_WINDOW`.
* Speech failures are no longer silent: if audio cannot be generated
  (service unreachable / package missing), the app says so once in the
  chat and in the voice settings pane.
* Mid-turn system notes (goal sync, harness notes) now go to
  OpenAI-compatible endpoints as user notes: Anthropic-family models only
  accept `system` at the start of the conversation and returned HTTP 400.
* New optional installer components: **Listening (microphone)**
  (faster-whisper + sounddevice, local recognition) and **Camera
  watching** (opencv-python-headless). Both follow the training
  component pattern: separate site folders, absent unless selected.
* Installer/build script reads the version from `pyproject.toml`.

## 0.1.0 — 2026-08-26

First public release.

* Agent core: append-only event log, ~60-line agent loop, permission gate,
  Anthropic + OpenAI-compatible (local) backends.
* Living memory: SQLite FTS5 + 256-bit fingerprint index, associative
  links, trace reinforcement — recall stays ~constant time as memory grows.
* Base rewriter: 10.8M-parameter byte-level model (pure numpy inference,
  ships as `src/neocp/assets/taban.npz`) expanding queries with synonyms,
  abbreviations and pronoun resolution.
* "Beni tanı" night school: on-device nightly fine-tuning loop with an
  exam gate — a new model is only deployed if it beats the current one.
* Desktop app (WebView2), web UI, terminal mode; brain scene visualisation.
* Gate API (`POST /api/gate`) for external agents, MCP connectors,
  skills, TR/EN interface.
* Windows installer (Inno Setup) and the full training rig (`training/`)
  with the bilingual teacher corpus and base checkpoint included.
