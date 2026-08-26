# -*- coding: utf-8 -*-
"""İnteraktif deneme: soru yaz → genişletme terimleri.

Model sohbet cevabı üretmez; aramaya eklenecek terimleri (veya susma)
döndürür. Zamir/bağlam için tek satırda \\n yazılabilir veya satır sonuna
\\ koyup bir sonraki satırla birleştirilebilir.

Kullanım:  py betikler/08_dene.py
Çıkış:     boş satır / q / exit
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

KOK = Path(__file__).parent.parent
sys.path.insert(0, str(KOK))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from model.cikarim import TabanYazici  # noqa: E402

NPZ = KOK / "out" / "taban.npz"


def _oku_girdi() -> str | None:
    """Bir sorgu satırı oku; çıkışta None.

    Satır `\\` ile biterse devam satırı birleştirilir.
    Metindeki `\\n` (iki karakter) gerçek satır kırılmasına çevrilir.
    """
    parcalar: list[str] = []
    while True:
        try:
            satir = input("soru> " if not parcalar else "    > ")
        except (EOFError, KeyboardInterrupt):
            print()
            return None
        if not parcalar and satir.strip().casefold() in ("", "q", "quit", "exit"):
            return None
        if satir.endswith("\\") and not satir.endswith("\\\\"):
            parcalar.append(satir[:-1])
            continue
        parcalar.append(satir)
        break
    ham = "\n".join(parcalar).replace("\\n", "\n").strip()
    return ham or None


def main() -> None:
    if not NPZ.is_file():
        raise SystemExit(f"ağırlık yok: {NPZ}  (önce 05_disari_aktar.py)")
    print(f"yükleniyor: {NPZ.name}")
    y = TabanYazici(NPZ)
    y.genislet("warmup")
    print("hazır — soru yaz (çıkış: q / boş satır). Bağlam için: bağlam\\n soru\n")
    while True:
        girdi = _oku_girdi()
        if girdi is None:
            break
        t0 = time.perf_counter()
        cikti = y.genislet(girdi)
        ms = (time.perf_counter() - t0) * 1000
        if cikti:
            print(f"  → {cikti!r}  ({ms:.0f} ms)")
        else:
            print(f"  → (susma)  ({ms:.0f} ms)")


if __name__ == "__main__":
    main()
