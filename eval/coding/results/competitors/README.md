# Competitor lanes — raw data

The three-harness benchmark's non-neo columns, so the comparison is
auditable rather than taken on faith.

| File | Lane | What it is |
|---|---|---|
| `result-opencode-9.json` | OpenCode | per-task scores, wall time, token/cost sums (9-task sweep) |
| `oc-<task>-events.jsonl` | OpenCode | raw `opencode run --format json` event streams — every step's tokens and cost, per task |
| `result-claude-9.json` | Claude Code | the reference lane's deliverables scored by this repo's grader (9 tasks; per-axis evidence included) |
| `result-opencode.json`, `result-claude.json` | both | the earlier three-task sweep |

Caveats, honestly: the OpenCode event streams are the harness's own
telemetry (we did not instrument it); the Claude Code lane's wall times
were measured with a stopwatch around its tool calls and its token/cost
columns are not comparable (different meter). Task ids in these files use
the pre-port Turkish names (`k1-modul`, `o1-rapor`, …).
