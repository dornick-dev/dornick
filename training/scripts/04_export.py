# -*- coding: utf-8 -*-
"""Checkpoint → base.npz + torch/numpy parity check.

The product only ever sees the npz. The parity check is MANDATORY: a silent
matrix bug in the numpy inference would read as "the model is bad" — it is
caught here instead.

Usage:  py scripts/04_export.py [checkpoint.pt]
        (default: checkpoints/best.pt if present, else checkpoints/base.pt)
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

CHECKPOINTS = ROOT / "checkpoints"
NPZ = CHECKPOINTS / "base.npz"


def main() -> None:
    if len(sys.argv) > 1:
        ck = Path(sys.argv[1])
    else:
        best = CHECKPOINTS / "best.pt"
        ck = best if best.exists() else CHECKPOINTS / "base.pt"
    if not ck.is_file():
        raise SystemExit(f"no checkpoint: {ck}  (train first, or fetch base.pt)")

    diff = common.export_npz(ck, NPZ)
    mb = NPZ.stat().st_size / 1e6
    print(f"written: {NPZ} ({mb:.1f} MB) from {ck.name}")
    print(f"torch<->numpy max logit diff: {diff:.4f} (fp16 packing ~0.1 is fine)")
    expander = QueryExpander(NPZ)
    print("sample output:", repr(expander.expand("bitcoin pozisyonum için kural neydi")))


if __name__ == "__main__":
    main()
