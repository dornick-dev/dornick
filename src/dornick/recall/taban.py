# -*- coding: utf-8 -*-
"""Taban yazıcı: sorguyu yerel küçük modelle genişleten katman.

10.8M parametrelik, bayt seviyesinde, iki dilli (TR/EN) bir GPT sorgudaki
konuyu birkaç eşanlamlı/komşu terime açar; terimler sorguya eklenip
hatırlama aramasına verilir. Sözlük köprüsünün (bridge.py) elle yazılmış
~50 grubu neyi kaçırıyorsa bu model onu öğrenilmiş genellemeyle kapatır —
ölçülen fark: eşanlam sınıfı 0.50 → 1.00, genel isabet 0.87 → 0.93
(eval/context_memory/scale_bench.py, dondurulmuş set).

Saf numpy: torch yok, kurulum yok. Ağırlıklar tek .npz dosyası; önce
kullanıcının kendi eğittiği .dornick/taban.npz aranır (kişisel ince ayar
vizyonu), yoksa ürünle gelen assets/taban.npz. İkisi de yoksa ya da numpy
yüklü değilse katman sessizce devre dışı kalır ve sorgu olduğu gibi geçer:
hatırlama bu model OLMADAN da çalışır, model yalnızca iyileştirir.

Eğitim düzeneği ayrı depoda: D:\\Projects\\ai\\neocp-base-model
(öğretmen-öğrenci damıtma, gemini flash-lite etiketli 138k örnek).
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

BOS, SEP, EOS, PAD = 256, 257, 258, 259

# Açgözlü çözümleme takılıp aynı kelimeyi tekrarlayabiliyor; tekrarlar
# atılır, liste 8 terimle sınırlanır (model en emin olduğunu önce üretir).
EN_COK_TERIM = 8

# Genişletmenin üreteceği azami bayt. Sınav bu değerle ölçüldü; değiştiren
# önce benchmark'ı yeniden koşmalı.
EN_COK_BAYT = 64

_kilit = threading.Lock()
_yazici: "TabanYazici | None" = None
_denendi = False
_yuklu_iz: tuple[str, float] | None = None  # (yol, mtime) — sıcak yenileme için
_son_bakis = 0.0

# Gece döngüsü .dornick/taban.npz'ye yeni model koyunca uygulama yeniden
# başlamadan devreye girsin diye dosya en fazla bu aralıkla yeniden yoklanır.
YENILEME_ARALIGI_SN = 300.0


def zenginlestir(sorgu: str, state_dir: Path | None = None) -> str:
    """Sorgu + model terimleri; model yoksa/susarsa sorgu olduğu gibi.

    select_prime'a giden metni üretir. Benchmark'taki yöntem birebir bu:
    `select_prime(m, q + " " + genislet(q))` — buradaki birleştirme o
    ölçümün ürünü; biçimi değiştirmek ölçülmemiş bir ürüne geçmektir.
    """
    sorgu = (sorgu or "").strip()
    if not sorgu:
        return sorgu
    yazici = _yukle(state_dir)
    if yazici is None:
        return sorgu
    try:
        terimler = yazici.genislet(sorgu)
    except Exception:
        # Genişletme hiçbir koşulda hatırlamayı düşürmemeli.
        return sorgu
    return f"{sorgu} {terimler}" if terimler else sorgu


def hazir(state_dir: Path | None = None) -> bool:
    return _yukle(state_dir) is not None


def sifirla() -> None:
    """Önbelleği düşürür: bir sonraki sorgu adayları diskten yeniden yoklar.

    Kişisel model silindiğinde (ya da içe aktarımla değiştiğinde) beş
    dakikalık yenileme aralığını beklemek "sıfırladım ama hâlâ eski model
    konuşuyor" demek; sıfırlama/geri yükleme uçları bunu çağırıp geçişi
    anında yapıyor.
    """
    global _yazici, _denendi, _yuklu_iz, _son_bakis
    with _kilit:
        _yazici = None
        _denendi = False
        _yuklu_iz = None
        _son_bakis = 0.0


def _adaylar(state_dir: Path | None) -> list[Path]:
    adaylar = []
    if state_dir is not None:
        adaylar.append(Path(state_dir) / "taban.npz")
    adaylar.append(Path(__file__).parent.parent / "assets" / "taban.npz")
    return adaylar


def _yukle(state_dir: Path | None) -> "TabanYazici | None":
    global _yazici, _denendi, _yuklu_iz, _son_bakis
    import time
    simdi = time.monotonic()
    taze_gerek = simdi - _son_bakis >= YENILEME_ARALIGI_SN
    if (_yazici is not None or _denendi) and not taze_gerek:
        return _yazici
    with _kilit:
        simdi = time.monotonic()
        if (_yazici is not None or _denendi) and simdi - _son_bakis < YENILEME_ARALIGI_SN:
            return _yazici
        _son_bakis = simdi
        _denendi = True
        for yol in _adaylar(state_dir):
            try:
                iz = (str(yol), yol.stat().st_mtime)
            except OSError:
                continue
            # Aynı dosya, aynı damga: yüklü olan geçerli.
            if _yazici is not None and iz == _yuklu_iz:
                return _yazici
            try:
                _yazici = TabanYazici(yol)
                _yuklu_iz = iz
            except Exception:
                continue
            return _yazici
        return _yazici


def _np():
    import numpy as np
    return np


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


class TabanYazici:
    """Tek .npz'den yüklenen, KV önbellekli açgözlü çözümleyici."""

    def __init__(self, yol: str | Path) -> None:
        np = _np()
        paket = np.load(Path(yol), allow_pickle=False)
        self.w = {k: paket[k].astype(np.float32) for k in paket.files if k != "_ayar"}
        self.a = json.loads(bytes(paket["_ayar"]).decode("utf-8"))
        self.kafa = self.a["kafa"]

    def _ln(self, x, w, b, eps=1e-5):
        mu = x.mean(-1, keepdims=True)
        var = x.var(-1, keepdims=True)
        return (x - mu) / _np().sqrt(var + eps) * w + b

    def _gelu(self, x):
        np = _np()
        return 0.5 * x * (1 + np.tanh(np.sqrt(2 / np.pi) * (x + 0.044715 * x ** 3)))

    def _blok(self, x, i: int, onbellek: list):
        np = _np()
        w = self.w
        T, d = x.shape
        h = self._ln(x, w[f"b{i}.n1.w"], w[f"b{i}.n1.b"])
        # MultiheadAttention: in_proj tek matris (3d, d), out_proj (d, d).
        qkv = h @ w[f"b{i}.att.in_w"].T + w[f"b{i}.att.in_b"]
        q, k, v = np.split(qkv, 3, axis=-1)
        hd = d // self.kafa
        q = q.reshape(T, self.kafa, hd).transpose(1, 0, 2)
        k = k.reshape(T, self.kafa, hd).transpose(1, 0, 2)
        v = v.reshape(T, self.kafa, hd).transpose(1, 0, 2)
        gecmis = 0
        if onbellek[i] is not None:
            ek, ev = onbellek[i]
            gecmis = ek.shape[1]
            k = np.concatenate([ek, k], axis=1)
            v = np.concatenate([ev, v], axis=1)
        onbellek[i] = (k, v)
        puan = q @ k.transpose(0, 2, 1) / np.sqrt(hd)
        # Nedensellik: yeni konum, kendinden sonraki anahtarı görmez.
        S = k.shape[1]
        puan += np.triu(np.full((T, S), -1e9, dtype=np.float32), 1 + gecmis)
        puan -= puan.max(-1, keepdims=True)
        agirlik = np.exp(puan)
        agirlik /= agirlik.sum(-1, keepdims=True)
        birlesik = (agirlik @ v).transpose(1, 0, 2).reshape(T, d)
        x = x + birlesik @ w[f"b{i}.att.out_w"].T + w[f"b{i}.att.out_b"]
        h = self._ln(x, w[f"b{i}.n2.w"], w[f"b{i}.n2.b"])
        h = self._gelu(h @ w[f"b{i}.mlp0.w"].T + w[f"b{i}.mlp0.b"])
        return x + h @ w[f"b{i}.mlp2.w"].T + w[f"b{i}.mlp2.b"]

    def _ilerle(self, dizin: list[int], baslangic: int, onbellek: list):
        w = self.w
        yeni = dizin[baslangic:]
        x = w["gomme"][yeni] + w["konum"][baslangic: baslangic + len(yeni)]
        for i in range(self.a["kat"]):
            x = self._blok(x, i, onbellek)
        x = self._ln(x, w["son.w"], w["son.b"])
        return x[-1] @ w["gomme"].T

    def genislet(self, girdi: str, en_cok_bayt: int = EN_COK_BAYT) -> str:
        """Sorguya eklenecek terimler; konu yoksa boş dize."""
        np = _np()
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
        return _temizle(bytes(uretilen).decode("utf-8", "ignore").strip())
