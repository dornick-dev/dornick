# -*- coding: utf-8 -*-
"""GPU eğitimi (4070). Checkpoint'li, sürdürülebilir, hız ölçümlü.

  py betikler/04_egit.py --adim 1500              (pilot)
  py betikler/04_egit.py --adim 20000             (tam)
  py betikler/04_egit.py --adim 20000 --surdur    (kaldığı yerden)
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

KOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from model.mimari import PAD, Ayar, TabanModel, kodla, parametre_sayisi  # noqa: E402

VERI = KOK / "veri" / "korpus.jsonl"
OUT = KOK / "out"
SON, ENIYI = OUT / "son.pt", OUT / "eniyi.pt"


def veri_yukle(ctx: int, ek: list[str] | None = None) -> tuple[list, list]:
    """korpus.jsonl + istenirse ek korpuslar (iki-dilli eğitim: korpus_en)."""
    rows = []
    dosyalar = [VERI] + [VERI.parent / d for d in (ek or [])]
    for dosya in dosyalar:
        if not dosya.exists():
            print(f"uyarı: {dosya.name} yok, atlandı")
            continue
        for line in dosya.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except Exception:
                continue
            rows.append(kodla(r["girdi"], r["cikti"], ctx))
    rng = random.Random(41)
    rng.shuffle(rows)
    kes = max(64, len(rows) // 50)
    return rows[kes:], rows[:kes]


def toplu(rows: list, bs: int, ctx: int, device) -> tuple[torch.Tensor, torch.Tensor]:
    secim = random.sample(rows, min(bs, len(rows)))
    en = max(len(d) for d, _ in secim)
    X = torch.full((len(secim), en), PAD, dtype=torch.long)
    Y = torch.full((len(secim), en), PAD, dtype=torch.long)
    for i, (d, h) in enumerate(secim):
        X[i, :len(d)] = torch.tensor(d)
        Y[i, :len(h)] = torch.tensor(h)
    return X.to(device), Y.to(device)


def dogrulama(model, rows, ctx, device, bs=96) -> float:
    model.eval()
    toplam, n = 0.0, 0
    with torch.no_grad(), torch.autocast("cuda", dtype=torch.bfloat16):
        for i in range(0, min(len(rows), 12 * bs), bs):
            grup = rows[i:i + bs]
            en = max(len(d) for d, _ in grup)
            X = torch.full((len(grup), en), PAD, dtype=torch.long)
            Y = torch.full((len(grup), en), PAD, dtype=torch.long)
            for j, (d, h) in enumerate(grup):
                X[j, :len(d)] = torch.tensor(d)
                Y[j, :len(h)] = torch.tensor(h)
            toplam += model.kayip(X.to(device), Y.to(device)).item() * len(grup)
            n += len(grup)
    model.train()
    return toplam / max(1, n)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--adim", type=int, default=1500)
    p.add_argument("--bs", type=int, default=96)
    p.add_argument("--lr", type=float, default=3e-4)
    p.add_argument("--surdur", action="store_true")
    p.add_argument("--ek", nargs="*", default=[],
                   help="ek korpus dosyaları (ör. korpus_en.jsonl)")
    a = p.parse_args()

    device = "cuda" if torch.cuda.is_available() else "cpu"
    ayar = Ayar()
    model = TabanModel(ayar).to(device)
    print(f"cihaz: {device} | parametre: {parametre_sayisi(model)/1e6:.1f}M")

    egitim, dogru = veri_yukle(ayar.ctx, a.ek)
    print(f"veri: {len(egitim)} eğitim + {len(dogru)} doğrulama")

    opt = torch.optim.AdamW(model.parameters(), lr=a.lr, weight_decay=0.05,
                            betas=(0.9, 0.95))
    adim0, eniyi = 0, float("inf")
    if a.surdur and SON.exists():
        ck = torch.load(SON, map_location=device)
        model.load_state_dict(ck["model"])
        opt.load_state_dict(ck["opt"])
        adim0, eniyi = ck["adim"], ck.get("eniyi", eniyi)
        print(f"sürdürülüyor: adım {adim0}, en iyi val {eniyi:.4f}")

    ISINMA = 200

    def lr_carpani(adim: int) -> float:
        if adim < ISINMA:
            return adim / ISINMA
        ilerleme = (adim - ISINMA) / max(1, a.adim - ISINMA)
        return 0.1 + 0.9 * 0.5 * (1 + math.cos(math.pi * min(1.0, ilerleme)))

    OUT.mkdir(exist_ok=True)
    model.train()
    basla = time.time()
    for adim in range(adim0 + 1, a.adim + 1):
        for g in opt.param_groups:
            g["lr"] = a.lr * lr_carpani(adim)
        X, Y = toplu(egitim, a.bs, ayar.ctx, device)
        with torch.autocast("cuda", dtype=torch.bfloat16, enabled=device == "cuda"):
            kayip = model.kayip(X, Y)
        opt.zero_grad(set_to_none=True)
        kayip.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        opt.step()

        if adim % 100 == 0 or adim == a.adim:
            hiz = (adim - adim0) / (time.time() - basla)
            print(f"adım {adim}/{a.adim} · kayıp {kayip.item():.4f} · "
                  f"{hiz:.1f} adım/sn · lr {opt.param_groups[0]['lr']:.2e}")
        if adim % 500 == 0 or adim == a.adim:
            val = dogrulama(model, dogru, ayar.ctx, device)
            isaret = ""
            if val < eniyi:
                eniyi = val
                torch.save({"model": model.state_dict(), "ayar": vars(ayar),
                            "adim": adim, "val": val}, ENIYI)
                isaret = "  ← en iyi, kaydedildi"
            torch.save({"model": model.state_dict(), "opt": opt.state_dict(),
                        "adim": adim, "eniyi": eniyi, "ayar": vars(ayar)}, SON)
            print(f"   doğrulama {val:.4f}{isaret}")

    print(f"bitti: {a.adim} adım, en iyi doğrulama {eniyi:.4f} → {ENIYI}")


if __name__ == "__main__":
    main()
