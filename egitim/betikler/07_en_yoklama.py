# -*- coding: utf-8 -*-
"""İngilizce yoklama: API'siz, elle etiketli mini sınav (çekirdek ortak.py'de).

Türkçe için gerçek benchmark ürün deposunda (scale_bench). İngilizce için
eşdeğer bir donmuş korpus yok; bu betik onun yerine tutulabilir bir sinyal
verir. Kullanım: py betikler/07_en_yoklama.py [model.npz]
"""

from __future__ import annotations

import sys
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK))
sys.path.insert(0, str(KOK / "betikler"))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import ortak  # noqa: E402
from model.cikarim import TabanYazici  # noqa: E402


def main() -> None:
    yol = Path(sys.argv[1]) if len(sys.argv) > 1 else KOK / "out" / "taban.npz"
    r = ortak.en_yoklama(TabanYazici(yol), yazdir=True)
    print()
    print(f"konu isabeti : {r['konu']:.2f}")
    print(f"susma        : {r['susma']:.2f}")
    print(f"gecikme      : ortanca {r['ortanca_ms']:.0f} ms, p95 {r['p95_ms']:.0f} ms")


if __name__ == "__main__":
    main()
