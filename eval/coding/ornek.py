"""İzole neo örneği: pencere yok, sunucu var.

Koşucu her görevi KENDİ neo'suyla koşturuyor. Sebep tek cümle: ölçüm
kullanıcının gerçek zihnini, atölyesini ve oturumlarını kirletmemeli, görevler
de birbirini kirletmemeli. Bir görevde yazılan `servis.py` bir sonraki görevin
atölyesinde durursa ölçtüğümüz şey ajan değil, artık dosyalar olur.

İzolasyon kalıbı (ürünün kendi açılış yolunu kullanarak):

  * `desktop._boot` doğrudan çağrılıyor — `desktop.run` DEĞİL. `run` pywebview
    penceresi açıyor ve `_kill_ghosts` ile makinedeki diğer neo örneklerini
    öldürüyordu; ölçüm kullanıcının açık uygulamasını kapatamaz.
  * Çalışma alanı `Config.load`'a AÇIK argüman olarak veriliyor. `NEOCP_WORKSPACE`
    ortam değişkeni kullanılmıyor: o değişken `config._pin_home` ile kullanıcının
    EV işaretçisini (`~/.neocp/home`) geçici klasöre sabitlerdi — ölçüm bittiğinde
    neo'nun evi silinmiş bir tmp klasörü olurdu.
  * `NEOCP_STATE_DIR` yalnız bu sürecin ortamında kuruluyor; ev işaretçisine
    dokunmuyor ama `otomod`/`fiyat` gibi ortak önbellekleri de geçici klasöre
    çekiyor.
  * Port her koşuda farklı; tarayıcı kapısı da kaydırılıyor ki kullanıcının
    açık neo'suyla çakışmasın.

Kapanış: stdin'den bir satır (ya da EOF) gelince `_teardown` çağrılıyor —
MCP alt süreçleri ve açık dosyalar arkada kalmasın.

Tek başına kullanım (elle deneme için):
    py eval/coding/ornek.py --alan C:\\tmp\\deneme --port 8790
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import threading
from pathlib import Path

HAZIR_ONEK = "HAZIR "


def main(argv: list[str] | None = None) -> int:
    ayristirici = argparse.ArgumentParser(description="izole neo örneği")
    ayristirici.add_argument("--alan", required=True,
                             help="çalışma alanı (ev) klasörü")
    ayristirici.add_argument("--port", type=int, required=True)
    args = ayristirici.parse_args(argv)

    alan = Path(args.alan).resolve()
    durum = alan / ".neocp"
    durum.mkdir(parents=True, exist_ok=True)

    # Ortak önbellekler de geçici klasöre. Ev işaretçisine DOKUNULMUYOR.
    os.environ["NEOCP_STATE_DIR"] = str(durum)
    os.environ.pop("NEOCP_WORKSPACE", None)

    kaynak = Path(__file__).resolve().parents[2] / "src"
    if kaynak.is_dir():
        sys.path.insert(0, str(kaynak))

    from neocp import desktop
    from neocp.config import Config

    # Açık argüman: `_resolve_workspace` bunu SABİTLEMİYOR (bkz. config.py).
    config = Config.load(alan)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        runtime = loop.run_until_complete(desktop._boot(config, args.port, False))
    except Exception as exc:  # açılış patlarsa koşucu sebebi görmeli
        print(f"PATLADI {type(exc).__name__}: {exc}", flush=True)
        return 1

    print(f"{HAZIR_ONEK}{runtime.url} oturum={runtime.session.id}", flush=True)

    def bekci() -> None:
        """stdin kapanınca ya da bir satır gelince temiz kapanış."""
        try:
            sys.stdin.readline()
        except Exception:
            pass
        try:
            desktop._teardown(loop, runtime)
        except Exception:
            pass
        # `_teardown` döngüyü durdurmayı zaten sıraya koyuyor; yine de
        # asılı bir thread kalırsa süreç kapanmalı.
        threading.Timer(8.0, lambda: os._exit(0)).start()

    threading.Thread(target=bekci, daemon=True, name="neo-eval-bekci").start()

    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
