# Coding benchmark

The question is not *how smart is the model* — it is **does a model
running inside neo deliver working software?**

Fully automatic: every task runs in its own temp workspace, with an
**empty mind**, on its own isolated neo instance. When the agent says it
is done, the grader walks into the workspace and **executes** the
delivery — runs the CLI, probes the HTTP endpoints, checks the auth
redirects, runs the test suites. Files merely existing scores nothing.

## Run it

```bash
py eval/coding/kosucu.py --gorev hepsi --model z-ai/glm-5.3-flash --tekrar 2
```

Useful flags: `--gorev k2-cli,z1-arama` (subset), `--zorluk zor`
(by difficulty), `--durum <dir>` (config/keys source), `--sakla`
(keep workspaces), `--onceki <json>` (merge with a previous result and
re-run only the selected tasks).

## Layout

| Path | Purpose |
|---|---|
| `kosucu.py` | runner: builds the isolated workspace, boots neo, asks through the gate, grades |
| `puanla.py` | scoring axes (works / scope / health / tests); executes the delivery |
| `davranis.py` | behaviour columns from the session log: model calls, tool errors, prompt & cache tokens, cost |
| `gorevler/<task>/` | one folder per task: `gorev.md` (the brief, exactly what the agent sees) + `olcut.py` (grader) + optional `tohum/` (seed files) |
| `sonuclar/` | raw per-run JSON cited by the public benchmark report |

## Honesty rules baked in

* The *works* axis is the carrier: if it cannot be measured, the task
  scores `None`, never a flattering number.
* A run that leaves a server holding the port is detected and reported
  instead of silently scoring zero.
* Scores are per-repetition; the report uses means, never best-of.
