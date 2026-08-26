# -*- coding: utf-8 -*-
"""Taban model mimarisi: bayt düzeyi, decoder-only, ~11M parametre.

Bayt düzeyi bilinçli: Türkçe sondan eklemeli — tokenizer'sız model ekleri
kendiliğinden görür ("etiketleri" içinde "etiket" bayt bayt duruyor).
Sözlük 260: 256 bayt + BOS/SEP/EOS/PAD.

Dizi biçimi:  [BOS] girdi-baytları [SEP] terim-baytları [EOS]
Kayıp yalnız SEP sonrasında: model soruyu üretmeyi değil, cevaplamayı öğrenir.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import torch
import torch.nn as nn
import torch.nn.functional as F

BOS, SEP, EOS, PAD = 256, 257, 258, 259
VOCAB = 260


@dataclass
class Ayar:
    ctx: int = 224          # girdi ≤152 bayt + terimler ≤64 bayt + işaretler
    d: int = 384
    kat: int = 6
    kafa: int = 6
    dropout: float = 0.1


class Blok(nn.Module):
    def __init__(self, a: Ayar) -> None:
        super().__init__()
        self.n1 = nn.LayerNorm(a.d)
        self.att = nn.MultiheadAttention(a.d, a.kafa, dropout=a.dropout,
                                         batch_first=True)
        self.n2 = nn.LayerNorm(a.d)
        self.mlp = nn.Sequential(
            nn.Linear(a.d, 4 * a.d), nn.GELU(),
            nn.Linear(4 * a.d, a.d), nn.Dropout(a.dropout))

    def forward(self, x: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
        h = self.n1(x)
        h, _ = self.att(h, h, h, attn_mask=mask, need_weights=False)
        x = x + h
        return x + self.mlp(self.n2(x))


class TabanModel(nn.Module):
    def __init__(self, a: Ayar | None = None) -> None:
        super().__init__()
        self.a = a or Ayar()
        self.gomme = nn.Embedding(VOCAB, self.a.d)
        self.konum = nn.Embedding(self.a.ctx, self.a.d)
        self.bloklar = nn.ModuleList(Blok(self.a) for _ in range(self.a.kat))
        self.son = nn.LayerNorm(self.a.d)
        self.bas = nn.Linear(self.a.d, VOCAB, bias=False)
        self.bas.weight = self.gomme.weight  # ağırlık bağlama
        mask = torch.triu(torch.full((self.a.ctx, self.a.ctx), float("-inf")), 1)
        self.register_buffer("mask", mask, persistent=False)

    def forward(self, dizin: torch.Tensor) -> torch.Tensor:
        T = dizin.shape[1]
        x = self.gomme(dizin) + self.konum(torch.arange(T, device=dizin.device))
        m = self.mask[:T, :T]
        for blok in self.bloklar:
            x = blok(x, m)
        return self.bas(self.son(x))

    def kayip(self, dizin: torch.Tensor, hedef: torch.Tensor) -> torch.Tensor:
        logits = self.forward(dizin)
        return F.cross_entropy(logits.reshape(-1, VOCAB), hedef.reshape(-1),
                               ignore_index=PAD)


def kodla(girdi: str, cikti: str | None = None, ctx: int = 224
          ) -> tuple[list[int], list[int] | None]:
    """Metni dizine çevirir. Eğitimde (dizin, hedef); çıkarımda (dizin, None).

    Girdinin SONU korunur: soru en sonda, bağlam başta — sığmazsa bağlamın
    başı gider, soru asla gitmez.
    """
    g = girdi.encode("utf-8")[-152:]
    seq = [BOS] + list(g) + [SEP]
    if cikti is None:
        return seq, None
    c = cikti.encode("utf-8")[: ctx - len(seq) - 1]
    tam = seq + list(c) + [EOS]
    # Hedef bir kaydırılmış dizi; girdi kısmı PAD ile maskeli.
    hedef = [PAD] * (len(seq) - 1) + list(c) + [EOS]
    return tam[:-1][:ctx], hedef[:ctx]


def parametre_sayisi(model: nn.Module) -> int:
    return sum(p.numel() for p in model.parameters())
