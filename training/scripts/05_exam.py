# -*- coding: utf-8 -*-
"""Acceptance exam: the base model competes on neo's scale benchmark.

Gates (must hold to ship with the product): recall >= the current system,
no regression on trap/empty silence, CPU inference fast enough. The
model's silence is additionally measured on held-out 'susma' examples
from its own corpus.

Usage:  py scripts/05_exam.py [model.npz]      (default: checkpoints/base.npz)
"""

from __future__ import annotations

import json
import statistics
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Product root: the rig lives inside the product repo (training/ next to src/).
PRODUCT = ROOT.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(PRODUCT / "src"))
sys.path.insert(0, str(PRODUCT / "eval" / "context_memory"))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import scale_bench as sb  # noqa: E402
from model.inference import QueryExpander  # noqa: E402
from neocp.loop import select_prime  # noqa: E402

NPZ = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "checkpoints" / "base.npz"
expander = QueryExpander(NPZ)


def expanded(q: str) -> str:
    extra = expander.expand(q)
    return f"{q} {extra}".strip() if extra else q


def main() -> None:
    data = sb.load_dataset()
    with tempfile.TemporaryDirectory() as tmp:
        mind, ids = sb.build_mind(data, Path(tmp))
        soul = mind.soul()
        sb.SOUL_IDS.clear()
        sb.SOUL_IDS.update(m.id for g in (soul.user, soul.preferences,
                                          soul.lessons, soul.voice) for m in g)

        sb.METHODS.clear()
        sb.METHODS.update({
            "current": (lambda m, q: select_prime(m, q), 220),
            "base": (lambda m, q: select_prime(m, expanded(q)), 220),
        })
        rows = [sb.run_method(n, data, mind, ids) for n in sb.METHODS]
        print(f"{'method':<8} {'recall':>7} {'precision':>10} {'silence':>8} {'tok':>7}")
        for r in rows:
            print(f"{r['name']:<8} {r['recall']:>7.2f} {r['precision']:>10.2f} "
                  f"{r['silence']:>8.2f} {r['tokens']:>7.1f}")
        kinds = sorted({k for r in rows for k in r["by_type"]})
        print(f"\n{'method':<8} " + " ".join(f"{k:>12}" for k in kinds))
        for r in rows:
            print(f"{r['name']:<8} " + " ".join(
                f"{r['by_type'].get(k, 0):>12.2f}" for k in kinds))
        mind.store.close()

    # Silence and speed: on examples from the corpus itself.
    corpus = [json.loads(l) for l in
              (ROOT / "data" / "corpus.jsonl").read_text(encoding="utf-8").splitlines()]
    silence_rows = [r["girdi"] for r in corpus if r["tur"] == "susma"][:40]
    silent = sum(1 for s in silence_rows if not expander.expand(s))
    print(f"\nsilence: model stayed silent on {silent}/{len(silence_rows)} examples")

    timings = []
    for r in corpus[:60]:
        t0 = time.perf_counter()
        expander.expand(r["girdi"])
        timings.append((time.perf_counter() - t0) * 1000)
    timings.sort()
    print(f"inference: median {statistics.median(timings):.0f} ms · "
          f"p95 {timings[int(len(timings)*0.95)-1]:.0f} ms")

    print("\nsample expansions:")
    for r in [x for x in corpus if x['cikti']][:6]:
        print(f"  {r['girdi'][:52]!r} -> {expander.expand(r['girdi'])!r}")


if __name__ == "__main__":
    main()
