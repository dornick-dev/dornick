# -*- coding: utf-8 -*-
"""Interactive demo: type a question -> expansion terms.

The model does not chat; it returns the terms to add to the memory search
(or silence). For pronoun/context examples you can write \\n inside one
line, or end a line with \\ to continue on the next.

Usage:  py scripts/try_it.py [model.npz]
Quit:   empty line / q / exit
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from model.inference import QueryExpander  # noqa: E402

NPZ = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "checkpoints" / "base.npz"


def read_query() -> str | None:
    """Read one query line; None on quit.

    A line ending in `\\` is joined with the next. A literal `\\n` (two
    characters) becomes a real line break.
    """
    parts: list[str] = []
    while True:
        try:
            line = input("query> " if not parts else "     > ")
        except (EOFError, KeyboardInterrupt):
            print()
            return None
        if not parts and line.strip().casefold() in ("", "q", "quit", "exit"):
            return None
        if line.endswith("\\") and not line.endswith("\\\\"):
            parts.append(line[:-1])
            continue
        parts.append(line)
        break
    raw = "\n".join(parts).replace("\\n", "\n").strip()
    return raw or None


def main() -> None:
    if not NPZ.is_file():
        raise SystemExit(f"no weights: {NPZ}  (run scripts/04_export.py first)")
    print(f"loading: {NPZ.name}")
    expander = QueryExpander(NPZ)
    expander.expand("warmup")
    print("ready — type a question (quit: q / empty line). "
          "For context: context\\n question\n")
    while True:
        query = read_query()
        if query is None:
            break
        t0 = time.perf_counter()
        out = expander.expand(query)
        ms = (time.perf_counter() - t0) * 1000
        if out:
            print(f"  -> {out!r}  ({ms:.0f} ms)")
        else:
            print(f"  -> (silence)  ({ms:.0f} ms)")


if __name__ == "__main__":
    main()
