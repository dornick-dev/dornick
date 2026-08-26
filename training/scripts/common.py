# -*- coding: utf-8 -*-
"""Pieces shared between scripts: npz export, EN probe, TR bench wrapper.

Kept in one place so export/probe/loop do not carry their own copies;
duplicated logic drifts silently and then the thing being measured is no
longer the same thing.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]          # training/
# Product root: the rig lives inside the product repo (training/ at the
# repo root), so the parent directory is the product. The installed layout
# is identical (<app>/training next to <app>/src). personal_loop.py can
# still override this with --neocp.
PRODUCT = ROOT.parent
sys.path.insert(0, str(ROOT))

from model.inference import QueryExpander  # noqa: E402


# -- npz export (same mapping as 04_export.py) --------------------------------

def export_npz(ck_path: Path, npz_path: Path) -> float:
    """Checkpoint → fp16 npz + torch/numpy parity check. Returns the max diff.

    The npz key names ("gomme", "konum", "b{i}. ...") are the frozen wire
    format the shipped product inference reads — see model/inference.py.
    """
    import numpy as np
    import torch

    from model.architecture import BOS, SEP, BaseModel, Config

    ck = torch.load(ck_path, map_location="cpu")
    cfg = Config(**ck["ayar"])
    model = BaseModel(cfg)
    model.load_state_dict(ck["model"])
    model.eval()

    sd = model.state_dict()
    pack = {
        "gomme": sd["gomme.weight"].numpy(),
        "konum": sd["konum.weight"].numpy(),
        "son.w": sd["son.weight"].numpy(),
        "son.b": sd["son.bias"].numpy(),
    }
    for i in range(cfg.kat):
        p = f"bloklar.{i}."
        pack[f"b{i}.n1.w"] = sd[p + "n1.weight"].numpy()
        pack[f"b{i}.n1.b"] = sd[p + "n1.bias"].numpy()
        pack[f"b{i}.att.in_w"] = sd[p + "att.in_proj_weight"].numpy()
        pack[f"b{i}.att.in_b"] = sd[p + "att.in_proj_bias"].numpy()
        pack[f"b{i}.att.out_w"] = sd[p + "att.out_proj.weight"].numpy()
        pack[f"b{i}.att.out_b"] = sd[p + "att.out_proj.bias"].numpy()
        pack[f"b{i}.n2.w"] = sd[p + "n2.weight"].numpy()
        pack[f"b{i}.n2.b"] = sd[p + "n2.bias"].numpy()
        pack[f"b{i}.mlp0.w"] = sd[p + "mlp.0.weight"].numpy()
        pack[f"b{i}.mlp0.b"] = sd[p + "mlp.0.bias"].numpy()
        pack[f"b{i}.mlp2.w"] = sd[p + "mlp.2.weight"].numpy()
        pack[f"b{i}.mlp2.b"] = sd[p + "mlp.2.bias"].numpy()

    cfg_json = json.dumps({"ctx": cfg.ctx, "d": cfg.d, "kat": cfg.kat,
                           "kafa": cfg.kafa}).encode("utf-8")
    np.savez_compressed(npz_path, _ayar=np.frombuffer(cfg_json, dtype=np.uint8),
                        **{k: v.astype(np.float16) for k, v in pack.items()})

    expander = QueryExpander(npz_path)
    probe = "bitcoin pozisyonum için kural neydi"
    seq = [BOS] + list(probe.encode("utf-8")) + [SEP]
    with torch.no_grad():
        ref = model(torch.tensor([seq]))[0, -1].numpy()
    diff = float(np.max(np.abs(ref - expander._logits(seq))))
    if diff > 0.25:
        raise SystemExit("PARITY BROKEN — the numpy inference has a bug")
    return diff


# -- English probe ------------------------------------------------------------

# (query, expected stems) — empty list = the model must stay silent (chatter).
# Stems are deliberately short: prefix matching. The expansion must CONTAIN one.
EN_PROBE = [
    ("Can you check whether the living room thermostat is still set to 23 degrees?",
     ["thermo", "temperat", "heat", "climat", "degre"]),
    ("Is the garage door locked right now?",
     ["lock", "door", "garage", "secur"]),
    ("Did my crypto portfolio drop below the limit we talked about?",
     ["crypto", "portfolio", "bitcoin", "invest", "coin", "market"]),
    ("Remind me what the doctor said about my blood pressure medication.",
     ["doctor", "medic", "health", "pressure", "blood", "pill", "prescri"]),
    ("What was the wifi password for the guest network?",
     ["wifi", "network", "password", "internet", "connect"]),
    ("When is my dentist appointment next week?",
     ["dent", "appoint", "schedul", "calend"]),
    ("How much did we spend on groceries last month?",
     ["grocer", "spend", "budget", "expense", "shop", "money", "food"]),
    ("Did the backup job on the server finish overnight?",
     ["backup", "server", "job", "data"]),
    ("Turn off the irrigation system in the garden this afternoon.",
     ["irrigat", "water", "garden", "sprink"]),
    ("What did my boss say about the deadline for the automation project?",
     ["deadlin", "project", "boss", "automat", "work", "task"]),
    ("Is the security camera at the front door still recording?",
     ["camera", "record", "secur", "video", "surveil"]),
    ("What was the license plate of the rental car?",
     ["plate", "car", "vehic", "rental", "licens"]),
    ("Did I already pay the electricity bill this month?",
     ["electric", "bill", "pay", "invoice", "utilit"]),
    ("Where did I park the car at the airport?",
     ["park", "car", "airport", "locat"]),
    ("What is the flight number for the trip to Berlin?",
     ["flight", "trip", "travel", "berlin", "plane"]),
    ("Remind me of the kids' school pickup time on Fridays.",
     ["school", "pickup", "kid", "child", "time", "schedul"]),
    # chatter — must stay silent:
    ("How are you doing today?", []),
    ("thanks, that was helpful", []),
    ("ok great", []),
    ("good morning!", []),
    ("haha nice one", []),
    ("see you tomorrow", []),
]


def en_probe(expander: QueryExpander, verbose: bool = False) -> dict:
    expander.expand("warmup")
    topic_hit = topic_total = silent_hit = silent_total = 0
    timings = []
    for query, stems in EN_PROBE:
        t0 = time.perf_counter()
        out = expander.expand(query).casefold()
        timings.append((time.perf_counter() - t0) * 1000)
        if stems:
            topic_total += 1
            ok = any(s in out for s in stems)
            topic_hit += ok
        else:
            silent_total += 1
            ok = not out
            silent_hit += ok
        if verbose:
            print(f"  {'+' if ok else '-'} {query[:52]:<52} -> {out[:60]!r}")
    timings.sort()
    return {
        "topic": topic_hit / topic_total,
        "silence": silent_hit / silent_total,
        "median_ms": timings[len(timings) // 2],
        "p95_ms": timings[int(len(timings) * 0.95)],
    }


# -- TR bench wrapper (same rig as 05_exam.py) --------------------------------

def tr_exam(expanders: dict[str, QueryExpander | None]) -> dict[str, dict]:
    """Runs the product's scale bench with the given expanders.
    None = no expansion (the current/baseline system).

    Returns: {name: {"recall": .., "silence": .., "precision": ..}}
    """
    import tempfile

    sys.path.insert(0, str(PRODUCT / "src"))
    sys.path.insert(0, str(PRODUCT / "eval" / "context_memory"))
    import scale_bench as sb
    from neocp.loop import select_prime

    def method(x):
        if x is None:
            return lambda m, q: select_prime(m, q)
        def runner(m, q, x=x):
            extra = x.expand(q)
            return select_prime(m, f"{q} {extra}".strip() if extra else q)
        return runner

    data = sb.load_dataset()
    result: dict[str, dict] = {}
    with tempfile.TemporaryDirectory() as tmp:
        mind, ids = sb.build_mind(data, Path(tmp))
        soul = mind.soul()
        sb.SOUL_IDS.clear()
        sb.SOUL_IDS.update(m.id for g in (soul.user, soul.preferences,
                                          soul.lessons, soul.voice) for m in g)
        sb.METHODS.clear()
        sb.METHODS.update({name: (method(x), 220) for name, x in expanders.items()})
        for name in sb.METHODS:
            r = sb.run_method(name, data, mind, ids)
            result[name] = {"recall": r["recall"], "silence": r["silence"],
                            "precision": r["precision"]}
        mind.store.close()
    return result
