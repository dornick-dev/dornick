# The Gate — driving dornick from other agents and harnesses

dornick has a single programmatic chat endpoint, the *gate*. It is how the
[benchmark rig](benchmark-2026-08.md) drives isolated dornick instances, and it
is the intended way to plug dornick into **another agent** — Claude Code,
OpenCode, a CI job, a cron script — as a callable worker.

## Enabling it

The gate is **off by default**. Turn it on either in the app
(*Settings → Machine → External gate*) or programmatically:

```bash
curl -s -X POST http://127.0.0.1:8765/api/gate \
  -H "Content-Type: application/json" -d '{"on": true}'
```

The switch is persisted in `.dornick/gate.json`. The server only ever binds
to `127.0.0.1` — the gate is local by design; anything on your machine can
speak to it, nothing off it can.

## Asking

`POST /api/gate` with a `text` body sends one message to the agent and
**blocks until the turn finishes**, then returns everything at once:

```bash
curl -s -X POST http://127.0.0.1:8765/api/gate \
  -H "Content-Type: application/json" \
  -d '{"text": "Read satislar.csv and write rapor.py that prints monthly revenue.",
       "bekle_sn": 600}'
```

```json
{
  "ok": true,
  "yanit": "…the agent's full text answer…",
  "araclar": ["read_file", "write_file", "shell"],
  "dosyalar": ["rapor.py"],
  "kuyrukta_bekledi": false,
  "gecen_sn": 41.7,
  "oturum": "20260829T012345Z"
}
```

| field | meaning |
|---|---|
| `yanit` | the agent's complete text output for the turn |
| `araclar` | tools it called, in order |
| `dosyalar` | files that changed in the workspace during the turn |
| `kuyrukta_bekledi` | `true` if your request queued behind a running turn |
| `gecen_sn` | wall time |
| `oturum` | session id — the raw event log is `.dornick/sessions/<oturum>.jsonl` |
| `bekle_sn` (request) | timeout, default 600 s; on timeout you get `ok:false` + `error` |

An optional `image` field takes a base64 data URL. Errors never drop the
connection — you always get JSON with `ok:false` and a reason.

## Driving dornick from Claude Code (or any agent)

Tell your agent the endpoint exists and let it call the gate with its own
HTTP tooling. A prompt that works verbatim in Claude Code:

> There is a local agent listening at `http://127.0.0.1:8765/api/gate`.
> POST JSON `{"text": "..."}` to give it a task; the response contains its
> answer (`yanit`) and the files it changed (`dosyalar`). Delegate the
> following task to it and review the result: …

That is the whole integration — no SDK. The same shape works from OpenCode,
LangChain, a Makefile, or a scheduled job. For a benchmark-grade setup
(fresh home, empty memory, pinned model, own API key per instance), do what
the rig does: create a temp home with a `config.json` + `keys.json`, start
dornick against it, then speak through the gate — the complete recipe is
[`eval/coding/runner.py`](../eval/coding/runner.py) (`build_workspace` + `Instance`).

## Auditing what it did

Every turn is an append-only JSONL event log under `.dornick/sessions/`.
The behaviour extractor [`eval/coding/behavior.py`](../eval/coding/behavior.py)
turns one into counters — model calls, tool errors, prompt/cache tokens,
cost — which is exactly how the numbers in the benchmark report were
produced. Nothing about the gate is special-cased: it is the same agent
loop the UI uses, minus the pixels.
