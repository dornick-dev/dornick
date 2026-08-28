# Changelog

## Unreleased

* **The model names your sessions.** After the first exchange, an unnamed
  session gets a short model-written title instead of the first 30
  characters of your message. A hand-given name is never overwritten.
* **Per-chat model selection.** The model chip under the composer now opens
  a searchable picker whose choice applies to *this chat* and takes effect
  immediately; a new chat inherits the last chat's pinned model, and the
  global default (Settings → Model) stays untouched — a plumbing bug that
  silently wrote the per-chat pin over the global default on disk is fixed.
* **Shell children no longer inherit stdin, and timeouts kill the whole
  process tree.** Caught live in a benchmark: an agent-written script that
  read stdin hung the turn for minutes, and the "stopped" wrapper's
  grandchild lived on for 7½ more. Children now get a closed stdin
  (`input()` fails instantly with a visible error) and Windows timeouts use
  `taskkill /T`.
* **Edit tool tolerates whitespace drift.** When the exact `old` text is
  not found, the editor tries line-ending normalization, trailing-space
  tolerance, and a uniform indentation shift (re-indenting `new` by the
  same amount) — each only when the match is unique; content differences
  still fail loudly.
* **Reasoning effort is capped at `medium` for small/fast model families.**
  Measured on the same model and task: uncapped high-effort thinking blew an
  11-call task into a 900-second timeout, and a sibling harness burned a
  full 32k-token reasoning spiral delivering nothing. Quality comes from
  the delivery gates, not the thinking budget.
* **Prompt-cache markers pay off on OpenRouter.** Cache hit rates measured
  at 65–92% across a three-task benchmark; the behavior report now carries
  a cache-read column.
* **Viewer tabs.** Opening a second file no longer closes the first — a tab
  strip appears and either can be closed or revisited.
* **Connectors directory.** The MCP settings pane now has search,
  connected/not-connected filters, and a popular-connectors catalog
  (GitHub, Notion, Linear, Sentry, Stripe, Playwright, filesystem, memory)
  that pre-fills the add form.
* **Task-list panel is editable in place** (complete/remove/add/clear), the
  plan nudge stays silent mid-work instead of proposing a from-scratch plan
  over a half-built project, and the plan card's confusing "save as
  automation" button is gone.
* **Links render as real anchors** — the URL shows in the status bar and
  right-click → copy works; sidebar, settings-modal sizing, and light-theme
  panel tones were reworked to match.
* New seed skill `olcum`: time a command N times, A/B compare, write a
  small report — for "it's faster now" claims that should be measured.

* **Gemini works again.** Gemini requires every `array` property in a tool
  schema to declare `items`; without it, it rejects **the entire tool list**,
  not just that tool — so one tool's omission made neo unusable on every
  Gemini model. Three properties were missing it. The schemas are fixed, and
  the OpenAI-compatible converter now fills in a permissive `items` for any
  array that lacks one, so the next tool written the same way cannot break a
  provider. A test walks every registered tool's schema.
* **Provider-specific fields on tool calls are no longer dropped.** Gemini
  attaches a `thought_signature` to function calls from thinking models and
  requires it back on the next turn; our translation kept only id, name and
  input, so such a field was lost. Unknown fields are now carried through the
  round trip verbatim — not modelled, just not lost — and stripped on the
  Anthropic path, which rejects fields it does not know.

## 0.4.1 — 2026-08-28

Two things that landed right after 0.4.0 was cut, now in the installer.

* **The flow diagram is a real diagram now.** Layout is computed from the
  graph — layer by longest path, columns centred vertically — so the flow
  reads left to right without lines crossing under cards. Edges leave and
  enter at the card's edge, curve, and carry **arrowheads**; a hand-dragged
  node keeps its own position. An `on: error` branch used to look identical
  to a normal one, which was a loss of information: it is now red, dashed
  and labelled **ON ERROR**. Node colour classifies rather than decorates —
  steps that reach the network, touch the system, ask the model, call a
  skill or read the inbox are told apart at a glance. A five-step flow no
  longer overflows the panel: a **Fit** control scales it down (never up)
  and steps aside the moment you drag a node.

* **A written entry point must actually be run.** The sharpest result in our
  own benchmark was a task delivered with 14 passing tests, 18 real
  assertions and 20/20 code health — whose command line did not work at all:
  every query printed the usage line and exited 1. The tests called the
  internal functions; nothing ever ran the command a user would type. That
  case slips past the red-test gate, because the suite was *green*.

  Now, when a file written this turn declares itself runnable from the
  command line (`__main__`, `sys.argv`, `argparse`, `process.argv`, PHP
  `$argv`) and its name never appears in any command that ran, a "done"
  answer is turned back once. The gate is deliberately narrow — a library
  module, a class file or a JSON file never triggers it — and it carries the
  same three brakes as the red-test gate: only this turn's writes, only a
  tool-less answer that claims completion, and at most once per turn. An
  answer that admits it hasn't run the thing is left alone.

## 0.4.0 — 2026-08-27

Automations: a repeated job becomes a graph of steps you can watch run.

* **Automation tasks.** Tasks now come in two kinds. A *simple* task is one
  instruction on a schedule (as before). An *automation* is a graph of nodes
  and edges stored in `.neocp/workflows/<id>.json` — `mail_read` → `agent` →
  `http` → `skill`, or whatever the job needs. Node types are open strings,
  so adding one does not break the format. There is still only **one**
  scheduler: `schedule.Task` gained `kind_ui` and `workflow_id`, and a
  triggered automation runs the graph instead of a prompt. Skills were not
  duplicated into a second script engine — a `skill` node calls the existing
  one.
* **Watch it run.** The flow lights up while it works: each node shows
  *running / done / failed* in colour **and in words**, the active edge is
  highlighted, and the panel refreshes every 1.5 s then stops on its own when
  the run ends. The output stays on the same screen — an automation that
  produces an app does not send you off to the Apps panel.
* **Self-repair, bounded.** When a step fails, neo asks the model to fix that
  step's config, writes it to disk and retries — once per step, at most three
  steps per run, config and skill only. What changed is written into the
  report; a silent repair is not a repair, it's a surprise. A step you edited
  by hand is marked ✎ and is **never** rewritten: that would be a quiet
  revert, not a fix. If the model answers with prose instead of JSON, nothing
  changes.
* **Automations live in memory.** A saved flow is remembered as a
  `procedure`, a broken step as a `lesson`, in a fixed shape from every path
  (tool or UI). The shape matters: these records also feed the nightly
  on-device fine-tune, and an event written differently every time has no
  pattern to learn. `workflow action=list` now prints each flow's steps, so
  "do I already have something that does this?" is answerable in one call —
  and both the tool and its output say the same thing: use what fits, don't
  bend what doesn't.
* **Local model optimisation.** With `local_optimize` on (off by default,
  localhost only), neo unloads other LM Studio models, *then* measures free
  VRAM, and fits the context window to what is left — without double-counting
  a model that is already resident. Without a GPU reading it only applies the
  model's own context ceiling. NVIDIA (`nvidia-smi`) only for now.

### Installer

* Installing over an existing copy is now **tested** for all three choices:
  update (data kept), clean install (code rewritten, data kept), and reset
  data too (backup written *before* deletion, then data genuinely removed).
  Eight scenarios, all passing, including backup rotation, running-copy
  detection and uninstall leaving `.neocp` in place.

### Fixes

* Automations could not be created at all: the scheduler, the runner and the
  UI all understood `kind_ui`/`workflow_id`, but nothing could write them —
  the API dropped them silently and the tool had no such field.
* Run history was filed under an id derived from the workflow while the UI
  asked by task id, so history looked empty and live progress never arrived.
* Progress was only recorded when a step *finished*, so nothing appeared to
  be running during a long step.
* The English interface was half Turkish: `<html lang>` was pinned to `tr`,
  which made CSS `text-transform: uppercase` render "SIMPLE" as "SİMPLE";
  several toolbar tooltips had no translation at all and `aria-label` was
  never translated, so screen readers heard Turkish in English mode.

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
