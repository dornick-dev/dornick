# -*- coding: utf-8 -*-
"""GPU training. Checkpointed, resumable, with throughput readout.

  py scripts/03_train.py --steps 1500              (pilot)
  py scripts/03_train.py --steps 20000             (full)
  py scripts/03_train.py --steps 20000 --resume    (continue)
  py scripts/03_train.py ... --extra corpus_en.jsonl   (bilingual training)
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
import time
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from model.architecture import PAD, BaseModel, Config, count_parameters, encode  # noqa: E402

CORPUS = ROOT / "data" / "corpus.jsonl"
CHECKPOINTS = ROOT / "checkpoints"
LAST, BEST = CHECKPOINTS / "last.pt", CHECKPOINTS / "best.pt"


def load_data(ctx: int, extra: list[str] | None = None) -> tuple[list, list]:
    """corpus.jsonl + optional extra corpora (bilingual training: corpus_en)."""
    rows = []
    files = [CORPUS] + [CORPUS.parent / name for name in (extra or [])]
    for file in files:
        if not file.exists():
            print(f"warning: {file.name} missing, skipped")
            continue
        for line in file.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except Exception:
                continue
            rows.append(encode(r["girdi"], r["cikti"], ctx))
    rng = random.Random(41)
    rng.shuffle(rows)
    cut = max(64, len(rows) // 50)
    return rows[cut:], rows[:cut]


def batch(rows: list, bs: int, ctx: int, device) -> tuple[torch.Tensor, torch.Tensor]:
    picked = random.sample(rows, min(bs, len(rows)))
    width = max(len(d) for d, _ in picked)
    X = torch.full((len(picked), width), PAD, dtype=torch.long)
    Y = torch.full((len(picked), width), PAD, dtype=torch.long)
    for i, (d, t) in enumerate(picked):
        X[i, :len(d)] = torch.tensor(d)
        Y[i, :len(t)] = torch.tensor(t)
    return X.to(device), Y.to(device)


def validate(model, rows, ctx, device, bs=96) -> float:
    model.eval()
    total, n = 0.0, 0
    with torch.no_grad(), torch.autocast("cuda", dtype=torch.bfloat16):
        for i in range(0, min(len(rows), 12 * bs), bs):
            group = rows[i:i + bs]
            width = max(len(d) for d, _ in group)
            X = torch.full((len(group), width), PAD, dtype=torch.long)
            Y = torch.full((len(group), width), PAD, dtype=torch.long)
            for j, (d, t) in enumerate(group):
                X[j, :len(d)] = torch.tensor(d)
                Y[j, :len(t)] = torch.tensor(t)
            total += model.loss(X.to(device), Y.to(device)).item() * len(group)
            n += len(group)
    model.train()
    return total / max(1, n)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--steps", type=int, default=1500)
    p.add_argument("--bs", type=int, default=96)
    p.add_argument("--lr", type=float, default=3e-4)
    p.add_argument("--resume", action="store_true")
    p.add_argument("--extra", nargs="*", default=[],
                   help="extra corpus files (e.g. corpus_en.jsonl)")
    a = p.parse_args()

    device = "cuda" if torch.cuda.is_available() else "cpu"
    cfg = Config()
    model = BaseModel(cfg).to(device)
    print(f"device: {device} | parameters: {count_parameters(model)/1e6:.1f}M")

    train_rows, val_rows = load_data(cfg.ctx, a.extra)
    print(f"data: {len(train_rows)} train + {len(val_rows)} validation")

    opt = torch.optim.AdamW(model.parameters(), lr=a.lr, weight_decay=0.05,
                            betas=(0.9, 0.95))
    step0, best = 0, float("inf")
    if a.resume and LAST.exists():
        ck = torch.load(LAST, map_location=device)
        model.load_state_dict(ck["model"])
        opt.load_state_dict(ck["opt"])
        step0, best = ck["adim"], ck.get("eniyi", best)
        print(f"resuming: step {step0}, best val {best:.4f}")

    WARMUP = 200

    def lr_scale(step: int) -> float:
        if step < WARMUP:
            return step / WARMUP
        progress = (step - WARMUP) / max(1, a.steps - WARMUP)
        return 0.1 + 0.9 * 0.5 * (1 + math.cos(math.pi * min(1.0, progress)))

    CHECKPOINTS.mkdir(exist_ok=True)
    model.train()
    started = time.time()
    for step in range(step0 + 1, a.steps + 1):
        for g in opt.param_groups:
            g["lr"] = a.lr * lr_scale(step)
        X, Y = batch(train_rows, a.bs, cfg.ctx, device)
        with torch.autocast("cuda", dtype=torch.bfloat16, enabled=device == "cuda"):
            loss = model.loss(X, Y)
        opt.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        opt.step()

        if step % 100 == 0 or step == a.steps:
            speed = (step - step0) / (time.time() - started)
            print(f"step {step}/{a.steps} · loss {loss.item():.4f} · "
                  f"{speed:.1f} steps/s · lr {opt.param_groups[0]['lr']:.2e}")
        if step % 500 == 0 or step == a.steps:
            val = validate(model, val_rows, cfg.ctx, device)
            note = ""
            if val < best:
                best = val
                # Checkpoint dict keys ("ayar"/"adim"/"eniyi") are frozen:
                # existing checkpoints and the loaders in export/personal
                # loop read them.
                torch.save({"model": model.state_dict(), "ayar": vars(cfg),
                            "adim": step, "val": val}, BEST)
                note = "  <- best, saved"
            torch.save({"model": model.state_dict(), "opt": opt.state_dict(),
                        "adim": step, "eniyi": best, "ayar": vars(cfg)}, LAST)
            print(f"   validation {val:.4f}{note}")

    print(f"done: {a.steps} steps, best validation {best:.4f} -> {BEST}")


if __name__ == "__main__":
    main()
