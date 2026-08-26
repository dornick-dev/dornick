# -*- coding: utf-8 -*-
"""Betikler arası ortak parçalar: npz aktarımı, EN yoklama, TR bench sarmalı.

05/07/08 aynı işi kendi kopyalarıyla yapmasın diye; kopya mantık sessizce
ayrışır ve ölçülen şey aynı şey olmaktan çıkar.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
# neocp kökü: düzenek ürünle aynı depoda yaşıyorsa (egitim/ depo kökünde)
# kök bir üst dizindir; ayrık geliştirici düzeninde eski sabit yol geçerli.
_REPO = KOK.parent
NEOCP = _REPO if (_REPO / "src" / "neocp").is_dir() else Path("D:/Projects/Fatih/neocp")
sys.path.insert(0, str(KOK))

from model.cikarim import TabanYazici  # noqa: E402


# -- npz aktarımı (05 ile aynı eşleme) ---------------------------------------

def npz_aktar(ck_yolu: Path, npz_yolu: Path) -> float:
    """Checkpoint → fp16 npz + torch/numpy eşitlik denetimi. Farkı döndürür."""
    import numpy as np
    import torch

    from model.mimari import BOS, SEP, Ayar, TabanModel

    ck = torch.load(ck_yolu, map_location="cpu")
    ayar = Ayar(**ck["ayar"])
    model = TabanModel(ayar)
    model.load_state_dict(ck["model"])
    model.eval()

    sd = model.state_dict()
    paket = {
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
    np.savez_compressed(npz_yolu, _ayar=np.frombuffer(ayar_json, dtype=np.uint8),
                        **{k: v.astype(np.float16) for k, v in paket.items()})

    yazici = TabanYazici(npz_yolu)
    deneme = "bitcoin pozisyonum için kural neydi"
    dizin = [BOS] + list(deneme.encode("utf-8")) + [SEP]
    with torch.no_grad():
        ref = model(torch.tensor([dizin]))[0, -1].numpy()
    fark = float(np.max(np.abs(ref - yazici._logits(dizin))))
    if fark > 0.25:
        raise SystemExit("EŞİTLİK BOZUK — numpy çıkarımda hata var")
    return fark


# -- İngilizce yoklama --------------------------------------------------------

# (sorgu, beklenen kök listesi) — boş liste = susmalı (gevezelik).
# Kökler kasıtlı kısa: prefix eşleşir. Genişletme İÇERMELİ.
YOKLAMA = [
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
    # gevezelik — susmalı:
    ("How are you doing today?", []),
    ("thanks, that was helpful", []),
    ("ok great", []),
    ("good morning!", []),
    ("haha nice one", []),
    ("see you tomorrow", []),
]


def en_yoklama(yazici: TabanYazici, yazdir: bool = False) -> dict:
    yazici.genislet("warmup")
    konu_d = konu_t = sus_d = sus_t = 0
    sureler = []
    for sorgu, kokler in YOKLAMA:
        b = time.perf_counter()
        cikti = yazici.genislet(sorgu).casefold()
        sureler.append((time.perf_counter() - b) * 1000)
        if kokler:
            konu_t += 1
            tutan = any(k in cikti for k in kokler)
            konu_d += tutan
        else:
            sus_t += 1
            tutan = not cikti
            sus_d += tutan
        if yazdir:
            print(f"  {'+' if tutan else '-'} {sorgu[:52]:<52} -> {cikti[:60]!r}")
    sureler.sort()
    return {
        "konu": konu_d / konu_t,
        "susma": sus_d / sus_t,
        "ortanca_ms": sureler[len(sureler) // 2],
        "p95_ms": sureler[int(len(sureler) * 0.95)],
    }


# -- TR bench sarmalı (06 ile aynı düzenek) -----------------------------------

def tr_sinav(yazicilar: dict[str, TabanYazici | None]) -> dict[str, dict]:
    """scale_bench'i verilen yazıcılarla koşar. None = genişletmesiz (mevcut).

    Dönen: {ad: {"isabet": .., "sessizlik": .., "kesinlik": ..}}
    """
    import tempfile

    sys.path.insert(0, str(NEOCP / "src"))
    sys.path.insert(0, str(NEOCP / "eval" / "context_memory"))
    import scale_bench as sb
    from neocp.loop import select_prime

    def yontem(y):
        if y is None:
            return lambda m, q: select_prime(m, q)
        def kosucu(m, q, y=y):
            ek = y.genislet(q)
            return select_prime(m, f"{q} {ek}".strip() if ek else q)
        return kosucu

    data = sb.load_dataset()
    sonuc: dict[str, dict] = {}
    with tempfile.TemporaryDirectory() as tmp:
        mind, ids = sb.build_mind(data, Path(tmp))
        soul = mind.soul()
        sb.SOUL_IDS.clear()
        sb.SOUL_IDS.update(m.id for g in (soul.user, soul.preferences,
                                          soul.lessons, soul.voice) for m in g)
        sb.METHODS.clear()
        sb.METHODS.update({ad: (yontem(y), 220) for ad, y in yazicilar.items()})
        for ad in sb.METHODS:
            r = sb.run_method(ad, data, mind, ids)
            sonuc[ad] = {"isabet": r["recall"], "sessizlik": r["silence"],
                         "kesinlik": r["precision"]}
        mind.store.close()
    return sonuc
