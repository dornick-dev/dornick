# Coding benchmark

The question is not *how smart is the model* — it is **does a model
running inside dornick deliver working software?**

Fully automatic: every task runs in its own temp workspace, with an
**empty mind**, on its own isolated dornick instance. When the agent says it
is done, the grader walks into the workspace and **executes** the
delivery — runs the CLI, probes the HTTP endpoints, checks the auth
redirects, runs the test suites. Files merely existing scores nothing.

## Run it

```bash
py eval/coding/runner.py --task all --model z-ai/glm-5.3-flash --repeat 2
```

Useful flags: `--task k2-cli,z1-search` (subset), `--difficulty hard`,
`--state <dir>` (config/keys source), `--keep`
(keep workspaces), `--previous <json>` (merge with a previous result and
re-run only the selected tasks).

## Layout

| Path | Purpose |
|---|---|
| `runner.py` | runner: builds the isolated workspace, boots dornick, asks through the gate, grades |
| `grading.py` | scoring axes (works / scope / health / tests); executes the delivery |
| `behavior.py` | behaviour columns from the session log: model calls, tool errors, prompt & cache tokens, cost |
| `tasks/<task>/` | one folder per task: `task.md` (the brief, exactly what the agent sees) + `grader.py` + optional `seed/` files |
| `results/` | raw per-run JSON cited by the public benchmark report |

## Honesty rules baked in

* The *works* axis is the carrier: if it cannot be measured, the task
  scores `None`, never a flattering number.
* A run that leaves a server holding the port is detected and reported
  instead of silently scoring zero.
* Scores are per-repetition; the report uses means, never best-of.
