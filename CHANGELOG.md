# Changelog

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
