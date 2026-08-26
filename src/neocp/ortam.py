"""Çalışma ortamı: kurulu düzen mi, geliştirici deposu mu?

Kurulum sihirbazıyla kurulan ağaçta Python gömülüdür (<kök>\\python\\...)
ve sihirbaz köke setup.json (eski adıyla kurulum.json) bırakır. Geliştirici
deposunda ise pip ile kurulmuş sıradan bir Python vardır.

Bu ayrım kullanıcıya görünen metinleri değiştirir: eksik bir özellik için
geliştiriciye "pip install ..." demek doğru, kurulum sihirbazından geçmiş
birine demekse anlamsız — ona sihirbazı yeniden çalıştırması söylenir.

Bir de konsol meselesi var: kurulu uygulama pythonw altında (konsolsuz)
koşar. Konsolsuz bir süreçten bayraksız başlatılan her konsol alt süreci
(powershell, netstat, taskkill...) ekranda bir cmd penceresi parlatır.
`sessiz_bayraklar()` bu pencereyi bastıran subprocess anahtarlarını verir.
"""

from __future__ import annotations

import subprocess
import sys
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def kurulu_mu() -> bool:
    """Kurulum sihirbazıyla kurulan düzende miyiz?

    İki bağımsız iz yeter: gömülü Python'un ._pth dosyası (sihirbaz paketi
    hep onunla kurar) ve sihirbazın kuruluma bıraktığı setup.json /
    kurulum.json. Geliştirici deposunda ikisi de yoktur.
    """
    try:
        exe = Path(sys.executable).resolve()
    except OSError:  # pragma: no cover - bozuk sys.executable
        return False
    if next(exe.parent.glob("python3*._pth"), None) is not None:
        return True
    kok = exe.parent.parent
    return (kok / "setup.json").exists() or (kok / "kurulum.json").exists()


def sessiz_bayraklar() -> dict:
    """Windows'ta konsol penceresi açtırmayan subprocess anahtarları.

    Çıktısı borulanan ya da hiç gösterilmeyen her konsol alt süreci bu
    bayrakla açılmalı; aksi halde pythonw altında her çağrı ekranda bir
    cmd penceresi parlatıyor. Kendi penceresi İSTENEN başlatmalar
    (kullanıcının uygulamasını yeni konsolda açmak gibi) bilinçli olarak
    CREATE_NEW_CONSOLE kullanır — onlara dokunma.
    """
    if sys.platform == "win32":
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    return {}
