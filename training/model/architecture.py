# -*- coding: utf-8 -*-
"""Base model architecture: byte-level, decoder-only, ~10.8M parameters.

Byte-level on purpose: Turkish is agglutinative — a tokenizer-free model
sees suffixes for free ("etiketleri" literally contains "etiket" byte by
byte), and the same vocabulary covers English without a second tokenizer.
Vocabulary is 260: 256 bytes + BOS/SEP/EOS/PAD.

Sequence format:  [BOS] input-bytes [SEP] term-bytes [EOS]
Loss is applied only after SEP: the model learns to answer, not to
reproduce the question.
"""

from __future__ import annotations

from dataclasses import dataclass

import torch
import torch.nn as nn
import torch.nn.functional as F

BOS, SEP, EOS, PAD = 256, 257, 258, 259
VOCAB = 260


@dataclass
class Config:
    ctx: int = 224          # input ≤152 bytes + terms ≤64 bytes + markers
    d: int = 384
    kat: int = 6            # layers  (field name frozen: stored in checkpoints)
    kafa: int = 6           # heads   (field name frozen: stored in checkpoints)
    dropout: float = 0.1


class Block(nn.Module):
    def __init__(self, cfg: Config) -> None:
        super().__init__()
        self.n1 = nn.LayerNorm(cfg.d)
        self.att = nn.MultiheadAttention(cfg.d, cfg.kafa, dropout=cfg.dropout,
                                         batch_first=True)
        self.n2 = nn.LayerNorm(cfg.d)
        self.mlp = nn.Sequential(
            nn.Linear(cfg.d, 4 * cfg.d), nn.GELU(),
            nn.Linear(4 * cfg.d, cfg.d), nn.Dropout(cfg.dropout))

    def forward(self, x: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
        h = self.n1(x)
        h, _ = self.att(h, h, h, attn_mask=mask, need_weights=False)
        x = x + h
        return x + self.mlp(self.n2(x))


class BaseModel(nn.Module):
    # NOTE on state-dict names: submodules are named `gomme` (embedding),
    # `konum` (positions), `bloklar` (blocks), `son` (final norm), `bas`
    # (head). These Turkish names are a FROZEN wire format: existing
    # checkpoints (checkpoints/base.pt) and the .npz files consumed by the
    # shipped product inference (src/neocp/recall/taban.py) use them.
    # Renaming them would break every deployed model.
    def __init__(self, cfg: Config | None = None) -> None:
        super().__init__()
        self.a = cfg or Config()
        self.gomme = nn.Embedding(VOCAB, self.a.d)
        self.konum = nn.Embedding(self.a.ctx, self.a.d)
        self.bloklar = nn.ModuleList(Block(self.a) for _ in range(self.a.kat))
        self.son = nn.LayerNorm(self.a.d)
        self.bas = nn.Linear(self.a.d, VOCAB, bias=False)
        self.bas.weight = self.gomme.weight  # weight tying
        mask = torch.triu(torch.full((self.a.ctx, self.a.ctx), float("-inf")), 1)
        self.register_buffer("mask", mask, persistent=False)

    def forward(self, seq: torch.Tensor) -> torch.Tensor:
        T = seq.shape[1]
        x = self.gomme(seq) + self.konum(torch.arange(T, device=seq.device))
        m = self.mask[:T, :T]
        for block in self.bloklar:
            x = block(x, m)
        return self.bas(self.son(x))

    def loss(self, seq: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
        logits = self.forward(seq)
        return F.cross_entropy(logits.reshape(-1, VOCAB), target.reshape(-1),
                               ignore_index=PAD)


def encode(text: str, output: str | None = None, ctx: int = 224
           ) -> tuple[list[int], list[int] | None]:
    """Turn text into a sequence. Training: (seq, target); inference: (seq, None).

    The END of the input is preserved: the question sits last, context
    first — if it does not fit, the head of the context is dropped, never
    the question.
    """
    g = text.encode("utf-8")[-152:]
    seq = [BOS] + list(g) + [SEP]
    if output is None:
        return seq, None
    c = output.encode("utf-8")[: ctx - len(seq) - 1]
    full = seq + list(c) + [EOS]
    # Target is the sequence shifted by one; the input part is masked with PAD.
    target = [PAD] * (len(seq) - 1) + list(c) + [EOS]
    return full[:-1][:ctx], target[:ctx]


def count_parameters(model: nn.Module) -> int:
    return sum(p.numel() for p in model.parameters())
