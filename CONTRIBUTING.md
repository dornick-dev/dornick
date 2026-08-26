# Contributing

Thanks for your interest in neo.

## Branches

* `main` is protected — no direct pushes.
* Work on a feature branch (`ozellik/kisa-ad` or `fix/kisa-ad`), open a
  pull request against `main`.

## Running tests

```bash
pip install -e ".[dev]"
py -m pytest tests/ -q
```

All tests must pass before a PR is merged. If you touch the memory/recall
layer, also run the scale benchmark:

```bash
py eval/context_memory/scale_bench.py
```

## Code conventions

* **Identifiers and comments are in Turkish.** This is a deliberate,
  project-wide convention (`hatirla`, `taban_yazici`, `sinav_kapisi` …).
  Please keep new code consistent with it — English identifiers are only
  used where an external API dictates them (tool names, HTTP fields).
  **Exception: `training/`** — the training rig is written in English
  (names and comments) so the ML community can read and retrain it; keep
  new code there English. Its data schema and npz/checkpoint key names
  stay Turkish — they are a frozen wire format (see `training/README.md`).
* Comments explain *why*, not *what*.
* No new runtime dependencies without discussion — the product core runs
  on the standard library plus a handful of small packages.

## Commit messages

English or Turkish, imperative mood, first line under 72 characters.
