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

Sürüm de buranın işi: hangi kopyanın çalıştığı sahada görünmüyordu.
Tek gerçek kaynak pyproject.toml — kurulu ağaç depo düzenini birebir
taklit ettiği ve build.ps1 pyproject'i paket köküne koyduğu için iki
düzende de aynı yerden okunur.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
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


def _kok() -> Path:
    """Uygulama ağacının kökü: src/Dornick'in iki üstü.

    Geliştirici deposunda depo kökü, kurulu düzende {app} — ikisi de
    pyproject.toml'u bu seviyede taşır (kuruluda build.ps1 koyar).
    """
    return Path(__file__).resolve().parents[2]


@lru_cache(maxsize=1)
def surum() -> str:
    """Çalışan kopyanın sürümü — tek gerçek kaynak pyproject.toml.

    pyproject okunamıyorsa (elle bozulmuş bir ağaç) pip metadata'sına
    düşülür; o da yoksa "0.0.0" — arayüz hiç değilse boş kalmaz.
    """
    try:
        import tomllib

        with open(_kok() / "pyproject.toml", "rb") as f:
            deger = tomllib.load(f).get("project", {}).get("version")
        if deger:
            return str(deger)
    except (OSError, ValueError):
        pass
    try:
        from importlib.metadata import PackageNotFoundError, version

        return version("dornick")
    except Exception:  # pragma: no cover - metadata da yoksa
        return "0.0.0"


# Güncelleme denetimi ELLE tetiklenir (Ayarlar › Makine); arka planda
# kendiliğinden ağa çıkan bir denetim bilerek yok — gizlilik ve sadelik.
GUNCELLEME_API = "https://api.github.com/repos/fatihkutuk/dornick/releases/latest"
GUNCELLEME_ZAMANASIMI = 6.0


def _surum_parcala(metin: str) -> tuple[int, ...]:
    """"v0.2.10" → (0, 2, 10). Sayı bulunamazsa boş demet — karşılaştırma
    yeni-sürüm-yok tarafına düşer, asla patlamaz."""
    return tuple(int(p) for p in re.findall(r"\d+", metin)[:4])


def guncelleme_denetle(*, _ac=urllib.request.urlopen) -> dict:
    """GitHub'daki son yayını sorar ve mevcutla karşılaştırır.

    Dönen sözlük arayüzün çizdiği her şey:
      ok     istek yerine ulaştı mı
      mevcut çalışan sürüm
      yeni   daha yeni bir yayın varsa onun sürümü, yoksa ""
      url    yeni sürümün indirme sayfası (tarayıcıda açılır)
      hata   kibar, insan diliyle hata metni (ok=False iken)
    """
    mevcut = surum()
    istek = urllib.request.Request(
        GUNCELLEME_API, headers={"Accept": "application/vnd.github+json",
                                 "User-Agent": f"dornick/{mevcut}"})
    try:
        with _ac(istek, timeout=GUNCELLEME_ZAMANASIMI) as cevap:
            veri = json.loads(cevap.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            # Depo/yayın görünmüyor: yayın hiç yapılmamış olabilir.
            return {"ok": False, "mevcut": mevcut, "yeni": "", "url": "",
                    "hata": "Yayınlanmış sürüm bulunamadı"}
        return {"ok": False, "mevcut": mevcut, "yeni": "", "url": "",
                "hata": f"Sürüm servisi cevap vermedi (HTTP {exc.code})"}
    except Exception:
        return {"ok": False, "mevcut": mevcut, "yeni": "", "url": "",
                "hata": "Ağa ulaşılamadı — internet bağlantısını denetle"}

    uzak = str(veri.get("tag_name") or veri.get("name") or "").strip()
    url = str(veri.get("html_url") or "")
    if _surum_parcala(uzak) > _surum_parcala(mevcut):
        return {"ok": True, "mevcut": mevcut,
                "yeni": uzak.lstrip("vV"), "url": url, "hata": ""}
    return {"ok": True, "mevcut": mevcut, "yeni": "", "url": "", "hata": ""}


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


async def agaci_oldur(proc) -> None:
    """Bir alt süreci ve ONUN ALTINDAKİLERİ sonlandırır.

    Yalnızca `proc.kill()` demek yetmiyor ve bu iki ayrı yerde ölçülerek
    görüldü (test koşucusu ve kancalar). Kabuk üzerinden başlatılan bir
    komutta `proc` powershell/cmd/bash'tir; asıl iş onun ÇOCUĞUdur.
    Kabuğu öldürmek gerçek süreci (npm, pytest, kullanıcının kancası)
    makinede çalışır halde bırakıyor — üstelik boruları da açık tuttuğu
    için çağıran taraf onun bitmesini beklemeye devam ediyor. Ölçüm:
    2 saniyelik bir zaman aşımı, 60 saniyelik bir bekleyişe dönüştü.

    Windows'ta süreç grubu yok; ağacın tamamı `taskkill /T` ile
    iniliyor. POSIX'te çağıran taraf süreci kendi oturumunda başlatıyor
    (`start_new_session`) ve grup tek sinyalle düşüyor.
    """
    import asyncio

    if proc.returncode is not None:
        return
    if sys.platform == "win32":
        try:
            agac = await asyncio.create_subprocess_exec(
                "taskkill", "/T", "/F", "/PID", str(proc.pid),
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                **sessiz_bayraklar(),
            )
            await asyncio.wait_for(agac.wait(), 10)
        except (OSError, ValueError, asyncio.TimeoutError):  # pragma: no cover
            pass
    else:  # pragma: no cover - POSIX yolu Windows'ta koşmuyor
        import os
        import signal

        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (OSError, ProcessLookupError):
            pass
    try:
        proc.kill()
    except (ProcessLookupError, OSError):
        pass
    try:
        await asyncio.wait_for(proc.wait(), 10)
    except (asyncio.TimeoutError, ProcessLookupError):  # pragma: no cover
        pass
