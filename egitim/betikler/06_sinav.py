# -*- coding: utf-8 -*-
"""Kabul sınavı: taban model, neocp'nin ölçek benchmark'ında yarışır.

Kapılar (ZIHIN raporu §8): isabet ≥ köprülü mevcut (0.87), tuzak/boş
sessizliğinde gerileme yok, CPU çıkarımı p95 < 80 ms. Ayrıca korpusun
susma sınıfından ayrılmış örneklerde modelin gerçekten sustuğu ölçülür.
"""

from __future__ import annotations

import json
import statistics
import sys
import tempfile
import time
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
# neocp kökü: düzenek ürünle aynı depoda yaşıyorsa (egitim/ depo kökünde)
# kök bir üst dizindir; ayrık geliştirici düzeninde eski sabit yol geçerli.
_REPO = KOK.parent
NEOCP = _REPO if (_REPO / "src" / "neocp").is_dir() else Path("D:/Projects/Fatih/neocp")
sys.path.insert(0, str(KOK))
sys.path.insert(0, str(NEOCP / "src"))
sys.path.insert(0, str(NEOCP / "eval" / "context_memory"))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import scale_bench as sb  # noqa: E402
from model.cikarim import TabanYazici  # noqa: E402
from neocp.loop import select_prime, worth_recalling  # noqa: E402

yazici = TabanYazici(KOK / "out" / "taban.npz")


def genis(q: str) -> str:
    ek = yazici.genislet(q)
    return f"{q} {ek}".strip() if ek else q


def main() -> None:
    data = sb.load_dataset()
    with tempfile.TemporaryDirectory() as tmp:
        mind, ids = sb.build_mind(data, Path(tmp))
        soul = mind.soul()
        sb.SOUL_IDS.clear()
        sb.SOUL_IDS.update(m.id for g in (soul.user, soul.preferences,
                                          soul.lessons, soul.voice) for m in g)

        sb.METHODS.clear()
        sb.METHODS.update({
            "mevcut": (lambda m, q: select_prime(m, q), 220),
            "taban": (lambda m, q: select_prime(m, genis(q)), 220),
        })
        rows = [sb.run_method(n, data, mind, ids) for n in sb.METHODS]
        print(f"{'yöntem':<8} {'isabet':>7} {'kesinlik':>9} {'sessizlik':>10} {'tok':>7}")
        for r in rows:
            print(f"{r['name']:<8} {r['recall']:>7.2f} {r['precision']:>9.2f} "
                  f"{r['silence']:>10.2f} {r['tokens']:>7.1f}")
        kinds = sorted({k for r in rows for k in r["by_type"]})
        print(f"\n{'yöntem':<8} " + " ".join(f"{k:>12}" for k in kinds))
        for r in rows:
            print(f"{r['name']:<8} " + " ".join(
                f"{r['by_type'].get(k, 0):>12.2f}" for k in kinds))
        mind.store.close()

    # Susma ve hız: korpusun kendisinden örneklerle.
    korpus = [json.loads(l) for l in
              (KOK / "veri" / "korpus.jsonl").read_text(encoding="utf-8").splitlines()]
    susma = [r["girdi"] for r in korpus if r["tur"] == "susma"][:40]
    sessiz = sum(1 for s in susma if not yazici.genislet(s))
    print(f"\nsusma: {sessiz}/{len(susma)} örnekte model sustu")

    sureler = []
    for r in korpus[:60]:
        t0 = time.perf_counter()
        yazici.genislet(r["girdi"])
        sureler.append((time.perf_counter() - t0) * 1000)
    sureler.sort()
    print(f"çıkarım: ortanca {statistics.median(sureler):.0f} ms · "
          f"p95 {sureler[int(len(sureler)*0.95)-1]:.0f} ms (kapı: <80)")

    print("\nörnek genişletmeler:")
    for r in [x for x in korpus if x['cikti']][:6]:
        print(f"  {r['girdi'][:52]!r} → {yazici.genislet(r['girdi'])!r}")


if __name__ == "__main__":
    main()
