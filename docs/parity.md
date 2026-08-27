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
| Artifacts | local artifact pages: publish/update-in-place/gallery, chat cards *(landing in v0.2.0)* |
| External automation | the gate API — outside agents drive a full turn and receive the complete output |

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

## Deliberately deferred (roadmap)

- **Deeper browser control** — accessibility-tree refs, forms, console/network
  reads (today: text-targeted clicking on a CDP-driven real profile).
- **Hooks** — pre/post tool-use user commands.
- **OS-level shell sandboxing** — today the permission engine is the fence;
  the shell itself is not jailed (documented honestly in `sandbox.py`).
- **Cross-platform screen/hands** — currently Windows (ctypes/user32).
- **Nested subagents / typed agents** — depth is capped at 1 by design for now.
- **Transcript search** across past sessions.
- **LSP integration** for structural code understanding.

## Method

Inventory: file:line-referenced sweep of this repository (tools, loop,
permissions, context, UX). Market scan: official docs and changelogs of
Claude Code, Claude Agent SDK, opencode, Cursor, Gemini CLI and Codex CLI,
August 2026. Scores and claims about our own features come from the
measured benchmarks in [evaluation.md](evaluation.md) and the training
pipeline in [../training/README.md](../training/README.md).
