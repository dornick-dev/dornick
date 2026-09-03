# -*- coding: utf-8 -*-
"""Base writer: the layer that expands a query with the small local model.

A 10.8M-parameter, byte-level, bilingual (TR/EN) GPT opens the topic in the
query into a few synonymous/neighbouring terms; the terms are appended to the
query and handed to the recall search. Whatever the dictionary bridge's
(bridge.py) ~50 hand-written groups miss, this model closes with learned
generalisation — measured difference: synonym class 0.50 → 1.00, overall
hit rate 0.87 → 0.93 (eval/context_memory/scale_bench.py, frozen set).

Pure numpy: no torch, no install. The weights are a single .npz file; the
user's own trained .dornick/taban.npz is looked for first (the personal
fine-tuning vision), otherwise the assets/taban.npz shipped with the product.
If neither exists, or numpy is not installed, the layer silently stays out
and the query passes through as is: recall works WITHOUT this model, the
model only improves it.

The training rig lives in a separate repo: D:\\Projects\\ai\\neocp-base-model
(teacher-student distillation, 138k examples labelled by gemini flash-lite).
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

BOS, SEP, EOS, PAD = 256, 257, 258, 259

# Greedy decoding can get stuck repeating the same word; repeats are dropped
# and the list is capped at 8 terms (the model emits what it is surest of
# first).
MAX_TERMS = 8

# Maximum bytes the expansion may generate. The benchmark was measured with
# this value; whoever changes it must re-run the benchmark first.
MAX_BYTES = 64

_lock = threading.Lock()
_writer: "BaseWriter | None" = None
_attempted = False
_loaded_trace: tuple[str, float] | None = None  # (path, mtime) — for hot refresh
_last_check = 0.0

# When the night loop drops a new model into .dornick/taban.npz it should take
# effect without restarting the app, so the file is re-probed at most this
# often.
REFRESH_INTERVAL_S = 300.0


def enrich(query: str, state_dir: Path | None = None) -> str:
    """Query + model terms; if there is no model, or it says nothing, the query as is.

    Produces the text that goes to select_prime. The method in the benchmark
    is exactly this: `select_prime(m, q + " " + expand(q))` — the joining
    here is the product of that measurement; changing the format means
    moving to an unmeasured product.
    """
    query = (query or "").strip()
    if not query:
        return query
    writer = _load(state_dir)
    if writer is None:
        return query
    try:
        terms = writer.expand(query)
    except Exception:
        # Expansion must never, under any condition, make recall worse.
        return query
    return f"{query} {terms}" if terms else query


def ready(state_dir: Path | None = None) -> bool:
    return _load(state_dir) is not None


def reset() -> None:
    """Drops the cache: the next query re-probes the candidates on disk.

    When the personal model is deleted (or replaced by an import), waiting
    out the five-minute refresh interval means "I reset it but the old model
    is still talking"; the reset/restore endpoints call this and make the
    switch immediate.
    """
    global _writer, _attempted, _loaded_trace, _last_check
    with _lock:
        _writer = None
        _attempted = False
        _loaded_trace = None
        _last_check = 0.0


def _candidates(state_dir: Path | None) -> list[Path]:
    candidates = []
    if state_dir is not None:
        candidates.append(Path(state_dir) / "taban.npz")
    candidates.append(Path(__file__).parent.parent / "assets" / "taban.npz")
    return candidates


def _load(state_dir: Path | None) -> "BaseWriter | None":
    global _writer, _attempted, _loaded_trace, _last_check
    import time
    now = time.monotonic()
    refresh_due = now - _last_check >= REFRESH_INTERVAL_S
    if (_writer is not None or _attempted) and not refresh_due:
        return _writer
    with _lock:
        now = time.monotonic()
        if (_writer is not None or _attempted) and now - _last_check < REFRESH_INTERVAL_S:
            return _writer
        _last_check = now
        _attempted = True
        for path in _candidates(state_dir):
            try:
                trace = (str(path), path.stat().st_mtime)
            except OSError:
                continue
            # Same file, same stamp: what is loaded is still valid.
            if _writer is not None and trace == _loaded_trace:
                return _writer
            try:
                _writer = BaseWriter(path)
                _loaded_trace = trace
            except Exception:
                continue
            return _writer
        return _writer


def _np():
    import numpy as np
    return np


def _clean(raw: str) -> str:
    seen: set[str] = set()
    terms: list[str] = []
    for piece in raw.split():
        key = piece.casefold()
        if key in seen:
            continue
        seen.add(key)
        terms.append(piece)
        if len(terms) >= MAX_TERMS:
            break
    return " ".join(terms)


class BaseWriter:
    """Greedy decoder with a KV cache, loaded from a single .npz."""

    def __init__(self, path: str | Path) -> None:
        np = _np()
        bundle = np.load(Path(path), allow_pickle=False)
        self.w = {k: bundle[k].astype(np.float32) for k in bundle.files if k != "_ayar"}
        self.a = json.loads(bytes(bundle["_ayar"]).decode("utf-8"))
        self.heads = self.a["kafa"]

    def _ln(self, x, w, b, eps=1e-5):
        mu = x.mean(-1, keepdims=True)
        var = x.var(-1, keepdims=True)
        return (x - mu) / _np().sqrt(var + eps) * w + b

    def _gelu(self, x):
        np = _np()
        return 0.5 * x * (1 + np.tanh(np.sqrt(2 / np.pi) * (x + 0.044715 * x ** 3)))

    def _block(self, x, i: int, cache: list):
        np = _np()
        w = self.w
        T, d = x.shape
        h = self._ln(x, w[f"b{i}.n1.w"], w[f"b{i}.n1.b"])
        # MultiheadAttention: in_proj is a single (3d, d) matrix, out_proj (d, d).
        qkv = h @ w[f"b{i}.att.in_w"].T + w[f"b{i}.att.in_b"]
        q, k, v = np.split(qkv, 3, axis=-1)
        hd = d // self.heads
        q = q.reshape(T, self.heads, hd).transpose(1, 0, 2)
        k = k.reshape(T, self.heads, hd).transpose(1, 0, 2)
        v = v.reshape(T, self.heads, hd).transpose(1, 0, 2)
        past = 0
        if cache[i] is not None:
            ck, cv = cache[i]
            past = ck.shape[1]
            k = np.concatenate([ck, k], axis=1)
            v = np.concatenate([cv, v], axis=1)
        cache[i] = (k, v)
        score = q @ k.transpose(0, 2, 1) / np.sqrt(hd)
        # Causality: a new position does not see the keys after itself.
        S = k.shape[1]
        score += np.triu(np.full((T, S), -1e9, dtype=np.float32), 1 + past)
        score -= score.max(-1, keepdims=True)
        weight = np.exp(score)
        weight /= weight.sum(-1, keepdims=True)
        merged = (weight @ v).transpose(1, 0, 2).reshape(T, d)
        x = x + merged @ w[f"b{i}.att.out_w"].T + w[f"b{i}.att.out_b"]
        h = self._ln(x, w[f"b{i}.n2.w"], w[f"b{i}.n2.b"])
        h = self._gelu(h @ w[f"b{i}.mlp0.w"].T + w[f"b{i}.mlp0.b"])
        return x + h @ w[f"b{i}.mlp2.w"].T + w[f"b{i}.mlp2.b"]

    def _forward(self, sequence: list[int], start: int, cache: list):
        w = self.w
        fresh = sequence[start:]
        x = w["gomme"][fresh] + w["konum"][start: start + len(fresh)]
        for i in range(self.a["kat"]):
            x = self._block(x, i, cache)
        x = self._ln(x, w["son.w"], w["son.b"])
        return x[-1] @ w["gomme"].T

    def expand(self, text: str, max_bytes: int = MAX_BYTES) -> str:
        """Terms to append to the query; an empty string if there is no topic."""
        np = _np()
        sequence = [BOS] + list(text.encode("utf-8")[-152:]) + [SEP]
        cache: list = [None] * self.a["kat"]
        logits = self._forward(sequence, 0, cache)
        generated: list[int] = []
        for _ in range(max_bytes):
            nxt = int(np.argmax(logits))
            if nxt in (EOS, PAD, BOS, SEP):
                break
            generated.append(nxt)
            sequence.append(nxt)
            if len(sequence) >= self.a["ctx"]:
                break
            logits = self._forward(sequence, len(sequence) - 1, cache)
        return _clean(bytes(generated).decode("utf-8", "ignore").strip())
