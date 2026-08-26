# -*- coding: utf-8 -*-
"""Saf numpy çıkarım — ürünün kullanacağı taraf.

torch YOK: neocp'nin kurulumsuz ilkesi. Ağırlıklar tek .npz dosyasından
yüklenir; açgözlü (greedy) çözümle en fazla 64 baytlık terim listesi üretir.
11M parametrede CPU'da tek sorgu ~10-40 ms.
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


class TabanYazici:
    def __init__(self, yol: str | Path) -> None:
        paket = np.load(Path(yol), allow_pickle=False)
        self.w = {k: paket[k].astype(np.float32) for k in paket.files if k != "_ayar"}
        self.a = json.loads(bytes(paket["_ayar"]).decode("utf-8"))
        self.kafa = self.a["kafa"]

    def _blok(self, x: np.ndarray, i: int, onbellek: list | None = None) -> np.ndarray:
        """Bir transformer bloğu.

        `onbellek` verilirse KV önbelleği kullanılır: x yalnızca YENİ konumları
        taşır, geçmiş konumların anahtar/değerleri önbellekten okunur. Önbelleksiz
        çözümleme her bayt için tüm diziyi baştan hesaplıyordu ve bir genişletme
        saniyeler sürüyordu; önbellekle aynı matematik ~30 kat ucuz.
        """
        w = self.w
        T, d = x.shape
        h = _ln(x, w[f"b{i}.n1.w"], w[f"b{i}.n1.b"])
        # MultiheadAttention: in_proj tek matris (3d, d), out_proj (d, d).
        qkv = h @ w[f"b{i}.att.in_w"].T + w[f"b{i}.att.in_b"]
        q, k, v = np.split(qkv, 3, axis=-1)
        hd = d // self.kafa
        q = q.reshape(T, self.kafa, hd).transpose(1, 0, 2)
        k = k.reshape(T, self.kafa, hd).transpose(1, 0, 2)
        v = v.reshape(T, self.kafa, hd).transpose(1, 0, 2)
        gecmis = 0
        if onbellek is not None and onbellek[i] is not None:
            ek, ev = onbellek[i]
            gecmis = ek.shape[1]
            k = np.concatenate([ek, k], axis=1)
            v = np.concatenate([ev, v], axis=1)
        if onbellek is not None:
            onbellek[i] = (k, v)
        puan = q @ k.transpose(0, 2, 1) / np.sqrt(hd)
        # Nedensellik maskesi: yeni konum j (mutlak gecmis+j), anahtar sütunu
        # ondan sonraysa kapalı. Tek-adım çözümlemede (T=1) maske boş kalır.
        S = k.shape[1]
        maske = np.triu(np.full((T, S), -1e9, dtype=np.float32), 1 + gecmis)
        puan += maske
        puan -= puan.max(-1, keepdims=True)
        agirlik = np.exp(puan)
        agirlik /= agirlik.sum(-1, keepdims=True)
        birlesik = (agirlik @ v).transpose(1, 0, 2).reshape(T, d)
        x = x + birlesik @ w[f"b{i}.att.out_w"].T + w[f"b{i}.att.out_b"]
        h = _ln(x, w[f"b{i}.n2.w"], w[f"b{i}.n2.b"])
        h = _gelu(h @ w[f"b{i}.mlp0.w"].T + w[f"b{i}.mlp0.b"])
        return x + h @ w[f"b{i}.mlp2.w"].T + w[f"b{i}.mlp2.b"]

    def _logits(self, dizin: list[int]) -> np.ndarray:
        w = self.w
        x = w["gomme"][dizin] + w["konum"][: len(dizin)]
        for i in range(self.a["kat"]):
            x = self._blok(x, i)
        x = _ln(x, w["son.w"], w["son.b"])
        return x[-1] @ w["gomme"].T

    def _ilerle(self, dizin: list[int], baslangic: int, onbellek: list) -> np.ndarray:
        """dizin[baslangic:] konumlarını önbellek üzerinden işler, son logits döner."""
        w = self.w
        yeni = dizin[baslangic:]
        x = w["gomme"][yeni] + w["konum"][baslangic: baslangic + len(yeni)]
        for i in range(self.a["kat"]):
            x = self._blok(x, i, onbellek)
        x = _ln(x, w["son.w"], w["son.b"])
        return x[-1] @ w["gomme"].T

    def genislet(self, girdi: str, en_cok_bayt: int = 64) -> str:
        """Sorguya eklenecek terimler; konu yoksa boş dize."""
        dizin = [BOS] + list(girdi.encode("utf-8")[-152:]) + [SEP]
        onbellek: list = [None] * self.a["kat"]
        logits = self._ilerle(dizin, 0, onbellek)
        uretilen: list[int] = []
        for _ in range(en_cok_bayt):
            sonraki = int(np.argmax(logits))
            if sonraki in (EOS, PAD, BOS, SEP):
                break
            uretilen.append(sonraki)
            dizin.append(sonraki)
            if len(dizin) >= self.a["ctx"]:
                break
            logits = self._ilerle(dizin, len(dizin) - 1, onbellek)
        ham = bytes(uretilen).decode("utf-8", "ignore").strip()
        return _temizle(ham)


# Açgözlü çözümleme takılıp aynı kelimeyi tekrarlayabiliyor ("kapı kapı
# kapı…") — sınavda kesinliği ve sessizliği bunlar yiyordu. Tekrarlar
# atılıyor, liste 8 terimle sınırlanıyor; sıra korunuyor çünkü model en
# emin olduğu terimi önce üretiyor.
EN_COK_TERIM = 8


def _temizle(ham: str) -> str:
    gorulen: set[str] = set()
    terimler: list[str] = []
    for parca in ham.split():
        anahtar = parca.casefold()
        if anahtar in gorulen:
            continue
        gorulen.add(anahtar)
        terimler.append(parca)
        if len(terimler) >= EN_COK_TERIM:
            break
    return " ".join(terimler)
