# -*- coding: utf-8 -*-
"""Pure-numpy inference — the side the product actually ships.

NO torch here: neo's zero-install principle. Weights load from a single
.npz file; greedy decoding produces at most 64 bytes of search terms.
At ~10.8M parameters a single query takes ~10-40 ms on CPU.

The .npz key names ("gomme", "konum", "son.w", "b{i}.att.in_w", ...) are a
FROZEN wire format shared with the product's own copy of this decoder
(src/neocp/recall/taban.py) and with every already-deployed model file.
Do not rename them.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

BOS, SEP, EOS, PAD = 256, 257, 258, 259


def _ln(x, w, b, eps=1e-5):
    mu = x.mean(-1, keepdims=True)
    var = x.var(-1, keepdims=True)
    return (x - mu) / np.sqrt(var + eps) * w + b


def _gelu(x):
    return 0.5 * x * (1 + np.tanh(np.sqrt(2 / np.pi) * (x + 0.044715 * x ** 3)))


class QueryExpander:
    def __init__(self, path: str | Path) -> None:
        pack = np.load(Path(path), allow_pickle=False)
        self.w = {k: pack[k].astype(np.float32) for k in pack.files if k != "_ayar"}
        # "_ayar" carries the architecture hyperparameters as JSON bytes
        # (ctx / d / kat=layers / kafa=heads) — part of the frozen format.
        self.a = json.loads(bytes(pack["_ayar"]).decode("utf-8"))
        self.heads = self.a["kafa"]

    def _block(self, x: np.ndarray, i: int, cache: list | None = None) -> np.ndarray:
        """One transformer block.

        With `cache`, the KV cache is used: x carries only the NEW
        positions, past keys/values come from the cache. Cacheless decoding
        recomputed the whole sequence for every byte and a single expansion
        took seconds; with the cache the same math is ~30x cheaper.
        """
        w = self.w
        T, d = x.shape
        h = _ln(x, w[f"b{i}.n1.w"], w[f"b{i}.n1.b"])
        # MultiheadAttention: in_proj is one (3d, d) matrix, out_proj (d, d).
        qkv = h @ w[f"b{i}.att.in_w"].T + w[f"b{i}.att.in_b"]
        q, k, v = np.split(qkv, 3, axis=-1)
        hd = d // self.heads
        q = q.reshape(T, self.heads, hd).transpose(1, 0, 2)
        k = k.reshape(T, self.heads, hd).transpose(1, 0, 2)
        v = v.reshape(T, self.heads, hd).transpose(1, 0, 2)
        past = 0
        if cache is not None and cache[i] is not None:
            pk, pv = cache[i]
            past = pk.shape[1]
            k = np.concatenate([pk, k], axis=1)
            v = np.concatenate([pv, v], axis=1)
        if cache is not None:
            cache[i] = (k, v)
        score = q @ k.transpose(0, 2, 1) / np.sqrt(hd)
        # Causal mask: new position j (absolute past+j) may not attend to a
        # key column after it. In single-step decoding (T=1) the mask is empty.
        S = k.shape[1]
        mask = np.triu(np.full((T, S), -1e9, dtype=np.float32), 1 + past)
        score += mask
        score -= score.max(-1, keepdims=True)
        att = np.exp(score)
        att /= att.sum(-1, keepdims=True)
        merged = (att @ v).transpose(1, 0, 2).reshape(T, d)
        x = x + merged @ w[f"b{i}.att.out_w"].T + w[f"b{i}.att.out_b"]
        h = _ln(x, w[f"b{i}.n2.w"], w[f"b{i}.n2.b"])
        h = _gelu(h @ w[f"b{i}.mlp0.w"].T + w[f"b{i}.mlp0.b"])
        return x + h @ w[f"b{i}.mlp2.w"].T + w[f"b{i}.mlp2.b"]

    def _logits(self, seq: list[int]) -> np.ndarray:
        w = self.w
        x = w["gomme"][seq] + w["konum"][: len(seq)]
        for i in range(self.a["kat"]):
            x = self._block(x, i)
        x = _ln(x, w["son.w"], w["son.b"])
        return x[-1] @ w["gomme"].T

    def _advance(self, seq: list[int], start: int, cache: list) -> np.ndarray:
        """Process seq[start:] through the cache, return logits for the last position."""
        w = self.w
        new = seq[start:]
        x = w["gomme"][new] + w["konum"][start: start + len(new)]
        for i in range(self.a["kat"]):
            x = self._block(x, i, cache)
        x = _ln(x, w["son.w"], w["son.b"])
        return x[-1] @ w["gomme"].T

    def expand(self, text: str, max_bytes: int = 64) -> str:
        """Terms to add to the query; empty string when there is no topic."""
        seq = [BOS] + list(text.encode("utf-8")[-152:]) + [SEP]
        cache: list = [None] * self.a["kat"]
        logits = self._advance(seq, 0, cache)
        produced: list[int] = []
        for _ in range(max_bytes):
            nxt = int(np.argmax(logits))
            if nxt in (EOS, PAD, BOS, SEP):
                break
            produced.append(nxt)
            seq.append(nxt)
            if len(seq) >= self.a["ctx"]:
                break
            logits = self._advance(seq, len(seq) - 1, cache)
        raw = bytes(produced).decode("utf-8", "ignore").strip()
        return _dedupe(raw)


# Greedy decoding can get stuck repeating a word ("door door door…") —
# in the exam this was eating precision and silence. Repeats are dropped
# and the list is capped at 8 terms; order is preserved because the model
# emits its most confident term first.
MAX_TERMS = 8


def _dedupe(raw: str) -> str:
    seen: set[str] = set()
    terms: list[str] = []
    for part in raw.split():
        key = part.casefold()
        if key in seen:
            continue
        seen.add(key)
        terms.append(part)
        if len(terms) >= MAX_TERMS:
            break
    return " ".join(terms)
