# -*- coding: utf-8 -*-
"""eniyi.pt → taban.npz + torch/numpy eşitlik denetimi.

Ürün yalnız npz'i görür. Eşitlik denetimi ŞART: numpy çıkarımdaki sessiz
bir matris hatası "model kötü" sanılır — burada yakalanır.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import torch

KOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from model.cikarim import TabanYazici  # noqa: E402
from model.mimari import BOS, SEP, Ayar, TabanModel  # noqa: E402

CK = KOK / "out" / "eniyi.pt"
NPZ = KOK / "out" / "taban.npz"


def aktar() -> None:
    ck = torch.load(CK, map_location="cpu")
    ayar = Ayar(**ck["ayar"])
    model = TabanModel(ayar)
    model.load_state_dict(ck["model"])
    model.eval()

    sd = model.state_dict()
    paket: dict[str, np.ndarray] = {
        "gomme": sd["gomme.weight"].numpy(),
        "konum": sd["konum.weight"].numpy(),
        "son.w": sd["son.weight"].numpy(),
        "son.b": sd["son.bias"].numpy(),
    }
    for i in range(ayar.kat):
        on = f"bloklar.{i}."
        paket[f"b{i}.n1.w"] = sd[on + "n1.weight"].numpy()
        paket[f"b{i}.n1.b"] = sd[on + "n1.bias"].numpy()
        paket[f"b{i}.att.in_w"] = sd[on + "att.in_proj_weight"].numpy()
        paket[f"b{i}.att.in_b"] = sd[on + "att.in_proj_bias"].numpy()
        paket[f"b{i}.att.out_w"] = sd[on + "att.out_proj.weight"].numpy()
        paket[f"b{i}.att.out_b"] = sd[on + "att.out_proj.bias"].numpy()
        paket[f"b{i}.n2.w"] = sd[on + "n2.weight"].numpy()
        paket[f"b{i}.n2.b"] = sd[on + "n2.bias"].numpy()
        paket[f"b{i}.mlp0.w"] = sd[on + "mlp.0.weight"].numpy()
        paket[f"b{i}.mlp0.b"] = sd[on + "mlp.0.bias"].numpy()
        paket[f"b{i}.mlp2.w"] = sd[on + "mlp.2.weight"].numpy()
        paket[f"b{i}.mlp2.b"] = sd[on + "mlp.2.bias"].numpy()

    ayar_json = json.dumps({"ctx": ayar.ctx, "d": ayar.d, "kat": ayar.kat,
                            "kafa": ayar.kafa}).encode("utf-8")
    np.savez_compressed(NPZ, _ayar=np.frombuffer(ayar_json, dtype=np.uint8),
                        **{k: v.astype(np.float16) for k, v in paket.items()})
    mb = NPZ.stat().st_size / 1e6
    print(f"yazıldı: {NPZ} ({mb:.1f} MB)")

    # Eşitlik: aynı girdi, torch vs numpy logit'leri.
    yazici = TabanYazici(NPZ)
    deneme = "bitcoin pozisyonum için kural neydi"
    dizin = [BOS] + list(deneme.encode("utf-8")) + [SEP]
    with torch.no_grad():
        ref = model(torch.tensor([dizin]))[0, -1].numpy()
    fark = float(np.max(np.abs(ref - yazici._logits(dizin))))
    print(f"torch↔numpy azami logit farkı: {fark:.4f} (fp16 paket ~0.1 kabul)")
    if fark > 0.25:
        raise SystemExit("EŞİTLİK BOZUK — numpy çıkarımda hata var")
    print("örnek çıktı:", repr(yazici.genislet(deneme)))


if __name__ == "__main__":
    aktar()
