# Agentic parity map (2026-08-27)

How neo's agentic surface compares to the current harness landscape
(Claude Code, Agent SDK, opencode, Cursor, Codex CLI), what was closed in
the overnight parity push, and what is deliberately deferred. Compiled from
a file-referenced inventory of this codebase plus a sourced market scan.

## At parity (or equivalent)

| Capability | neo's shape |
|---|---|
| Core file tools | read / write (staleness-guarded) / edit — now with **atomic multi-edit** |
| Code search | **`grep` tool** (pure-Python content search: regex, glob, context lines) + glob listing |
| Shell | foreground / long-background with completion notes / detached servers; auto-detects server-type commands |
| Subagents | parallel, background-capable, per-agent model override, steerable (`task_say`), inspectable (`task_status`) |
| Long-horizon runs | soft turn checkpoints (hard fuse at 600), **mid-run compaction** with pinned work-state, outage retry → park → auto-resume |
| Mid-turn steering | user messages inject into the running turn (no queue-and-wait) |
| Interrupts | pre-first-token cancellation; stops helpers too |
| Checkpoints / undo | **automatic pre-write snapshots + `undo` tool** (list/restore, redo-safe, 14-day retention) |
| Plan mode | read-only mode + **plan-approval loop** ("▶ Apply plan" hands authority back and executes) |
| Visible todos | live goals panel (event-driven, strikethrough-on-done, reload-safe) |
| Context economy | 75% auto-compaction, deterministic tool-payload pruning, cache breakpoints, deferred MCP schemas (measured: 27k → ~250 tokens for a 28-tool server) |
| Permissions | four modes (auto/ask/plan/yolo), rule engine (allow/deny, deny wins), per-helper approval attribution |
| Skills / commands | self-written Python skills, hot-reloaded, shipped seed set |
| MCP | client (stdio+HTTP+OAuth, Claude Code `mcpServers` format) **and server** (the memory itself is an MCP server) |
| Sessions | resume, history browser, transcript restore on reload, selective export/import with automatic backups |
| Scheduled work | in-app scheduler (every/daily) + nightly personal-training loop |
| Artifacts | local artifact pages: publish/update-in-place/gallery, chat cards |
| External automation | the gate API — outside agents drive a full turn and receive the complete output |
| **Working in your own repo** | project mode: point neo at any folder and it works there, not in a sandbox `atolye` (dangerous roots refused, recents remembered) |
| **Post-write diagnostics** | every write is compiled/linted in its own language before the model moves on (`compile()`, `php -l`, `node --check`, `tsc`, ruff) — with an honest coverage table for what is *not* checked |
| **Running the tests** | the `kos` tool detects the project's real test command from evidence (never invents one) and runs it |
| **Symbols** | `semboller` — definitions and usages across Python (`ast`) and PHP/JS/TS |
| **Hooks** | `.neocp/kancalar.json` — user shell commands before/after tool use; a non-zero exit **vetoes** the tool. Deliberately outside the permission engine (your own rule shouldn't ask your permission), and the hook file is closed to the model on two paths — write tools refuse it by path, other mutating calls that name it are refused before the permission gate — so it cannot disarm its own fence by casually reaching for the shell |
| **Eyes on files** | `read_file` on a PNG/JPG returns an actual image to the model; on a PDF, page text with an explicit "these pages carry no text layer — do not guess" when scanned |
| **Chat surface** | `/` command book, `@` file mentions, running-tasks ledger with stop and drill-in, "what changed this turn" with undo, budget brake |
| **Deeper browser** | console reads, network errors, form fill/submit, error-page detection — not just clicking text |
| **Transcript search** | search across past sessions by name, tag, or transcript contents |

## Ahead of the market

Confirmed against the scan — none of the surveyed harnesses have these:

1. **A model that learns its user.** Nightly on-device fine-tuning of the
   on-board query-expansion model, gated by an exam that rejects any
   candidate that regresses. Everyone else's "memory" is an appended
   markdown file.
2. **A living memory, not a notes file.** FTS + fingerprint recall with
   spreading activation, ~constant-time at 50k memories, visualized live.
3. **Memory as an MCP server.** Other tools (Claude Code included) can
   mount neo's memory.
4. **The gate.** Scriptable full-turn access for external evaluators —
   this repo's own benchmark used it.

## Measured, not asserted

The claims above are inventory. What the coding work actually *delivers* is
measured by a rig in this repo ([`eval/coding/`](../eval/coding/README.md)):
nine tasks, each in its own workspace with an empty mind, graded by executing
the code. Baseline and the three weaknesses it exposed are in
[the benchmark](benchmark-2026-08.md). Reading that page is the honest version of
reading this one.

## Deliberately deferred (roadmap)

- **OS-level shell sandboxing** — today the permission engine is the fence;
  the shell itself is not jailed (documented honestly in `sandbox.py`).
- **Cross-platform screen/hands** — currently Windows (ctypes/user32).
- **Nested subagents / typed agents** — depth is capped at 1 by design for now;
  typed agent definitions (per-agent tools and prompt) are the next step.
- **Real LSP** — `semboller` is an `ast`/regex approximation, good enough for
  "where is this defined", not for rename-safe refactoring.
- **MCP OAuth** — client-side OAuth for remote MCP servers is not wired.
- **Memory-informed coding** — the coding pipeline currently runs with an
  empty mind; wiring recall into coding work is unmeasured and undone.

## Method

Inventory: file:line-referenced sweep of this repository (tools, loop,
permissions, context, UX). Market scan: official docs and changelogs of
Claude Code, Claude Agent SDK, opencode, Cursor, Gemini CLI and Codex CLI,
August 2026. Scores and claims about our own features come from the
measured benchmarks in [the benchmark](benchmark-2026-08.md) and the training
pipeline in [../training/README.md](../training/README.md).
