# -*- coding: utf-8 -*-
"""English probe: API-free, hand-labeled mini exam (core lives in common.py).

The real Turkish benchmark is the product's scale bench (05_exam.py). There
is no equivalent frozen corpus for English yet; this script stands in as a
holdable signal.  Usage: py scripts/06_en_probe.py [model.npz]
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import common  # noqa: E402
from model.inference import QueryExpander  # noqa: E402


def main() -> None:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "checkpoints" / "base.npz"
    r = common.en_probe(QueryExpander(path), verbose=True)
    print()
    print(f"topic hit  : {r['topic']:.2f}")
    print(f"silence    : {r['silence']:.2f}")
    print(f"latency    : median {r['median_ms']:.0f} ms, p95 {r['p95_ms']:.0f} ms")


if __name__ == "__main__":
    main()
