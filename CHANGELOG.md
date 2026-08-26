# Changelog

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
