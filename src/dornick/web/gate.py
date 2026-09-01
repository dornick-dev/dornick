"""Dış kapı: başka ajanların Dornick'i programatik kullanabildiği HTTP ucu.

Amaç değerlendirme: harici bir araç (test koşucusu, puanlayıcı ajan, betik)
sohbete kullanıcı gibi yazar, turun bitmesini bekler ve TÜM çıktıyı alır —
yanıt metni, kullanılan araçlar, atölyede o tur içinde değişen dosyalar.

Kapı varsayılan KAPALI ve yalnızca ayarlardan açılır; durum `gate.json`'da
saklanır ki yeniden başlatınca hatırlansın. Sunucu zaten sadece 127.0.0.1'i
dinliyor — kapı açıkken bile makine dışına yüzey yok.

Yanıt toplama iki kanaldan yürür ve ikisi de zaten var olan altyapı:
  * Olay günlüğü (EventLog.subscribe) — asistan mesajlarının TAM metni ve
    araç çağrıları buradan gelir. Hub'daki "message" olayı 400 karakterde
    kırpıldığı için hub'dan metin toplamak yetmezdi.
  * Hub — tur sınırı ("turn_end") yalnızca hub'a yayınlanır, günlüğe
    yazılmaz; o yüzden bitişi hub'dan dinliyoruz.

Eşleştirme: gönderdiğimiz metin günlüğe kullanıcı mesajı olarak düşer;
o düştükten SONRAKİ ilk "turn_end" bizim turumuzdur (kuyruk FIFO, turlar
seri). Öncesinde gelen turn_end'ler başka turlarındır ve yok sayılır.
"""

from __future__ import annotations

import json
import os
import queue
import threading
import time
from pathlib import Path
from typing import Any

DOSYA = "gate.json"

# Değişen-dosya taramasında atlanan dizinler: araç artıkları, sürüm kontrolü.
_ATLA = frozenset({".git", "__pycache__", "node_modules", ".venv", ".geri-donusum"})

# Bir turun bekleneceği azami süre. Uzun araştırma turları dakikalar sürer;
# ama sonsuz bekleyen bir HTTP isteği de thread sızdırır.
VARSAYILAN_BEKLE_SN = 600.0
AZAMI_BEKLE_SN = 1800.0

# Yanıttaki dosya listesi tavanı: bir derleme çıktısını sayıp dökmenin alemi yok.
DOSYA_TAVANI = 200


def durum(state_dir: Path) -> bool:
    try:
        return bool(json.loads((state_dir / DOSYA).read_text(encoding="utf-8")).get("on"))
    except (OSError, ValueError):
        return False


def ayarla(state_dir: Path, on: bool) -> None:
    (state_dir / DOSYA).write_text(json.dumps({"on": bool(on)}), encoding="utf-8")


def _metinler(content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    return "\n".join(
        str(b.get("text", "")) for b in content
        if isinstance(b, dict) and b.get("type") == "text"
    )


def _degisen_dosyalar(kok: Path, esik: float) -> list[str]:
    """Turdan beri atölyede yazılan dosyalar (göreli yol, en yeni önce)."""
    bulunan: list[tuple[float, str]] = []
    try:
        for dirpath, dirnames, filenames in os.walk(kok):
            dirnames[:] = [d for d in dirnames if d not in _ATLA and not d.startswith(".")]
            for ad in filenames:
                yol = Path(dirpath) / ad
                try:
                    mt = yol.stat().st_mtime
                except OSError:
                    continue
                if mt >= esik:
                    bulunan.append((mt, yol.relative_to(kok).as_posix()))
                    if len(bulunan) >= DOSYA_TAVANI:
                        raise StopIteration
    except StopIteration:
        pass
    bulunan.sort(reverse=True)
    return [yol for _, yol in bulunan]


def sor(
    *,
    controller: Any,
    hub: Any,
    text: str,
    image: str = "",
    bekle_sn: float = VARSAYILAN_BEKLE_SN,
    sandbox_root: Path | None = None,
) -> dict[str, Any]:
    """Mesajı ajana verir, turun bitmesini bekler, tüm çıktıyı döndürür.

    HTTP thread'inde bloklar; ThreadingHTTPServer her isteğe kendi thread'ini
    verdiği için diğer istekler etkilenmez.
    """
    agent = getattr(controller, "agent", None)
    log = getattr(getattr(agent, "session", None), "log", None)
    if log is None:
        return {"ok": False, "error": "ajan hazır değil"}

    bekle_sn = max(5.0, min(float(bekle_sn or VARSAYILAN_BEKLE_SN), AZAMI_BEKLE_SN))
    baslangic = time.time()
    # `busy` desktop'ta property, başka bir controller'da metot olabilir.
    mesgul = getattr(controller, "busy", False)
    kuyruktaydi = bool(mesgul() if callable(mesgul) else mesgul)

    mesaj_gorüldu = threading.Event()
    onay_bekliyor = threading.Event()
    parcalar: list[str] = []
    araclar: list[str] = []

    def dinle(ev: Any) -> None:
        if not mesaj_gorüldu.is_set():
            if (
                ev.is_message
                and ev.role == "user"
                and not ev.meta.get("tool_results")
                and not ev.meta.get("continuation")
                and not ev.meta.get("internal")
                and _metinler(ev.content).strip() == text.strip()
            ):
                mesaj_gorüldu.set()
            return
        if ev.is_message and ev.role == "assistant" and isinstance(ev.content, list):
            for blok in ev.content:
                if not isinstance(blok, dict):
                    continue
                if blok.get("type") == "text" and str(blok.get("text", "")).strip():
                    parcalar.append(str(blok["text"]))
                elif blok.get("type") == "tool_use":
                    araclar.append(str(blok.get("name", "")))
        elif ev.kind == "meta" and ev.content == "permission":
            # Yalnız GERÇEKTEN kullanıcıya sorulan izin sayılır. `yolo`
            # kipinde her araç da bir permission olayı bırakıyor; hepsini
            # "onay bekliyor" saymak, zaman aşımı mesajının her seferinde
            # yanlış yere ("izin onayla") işaret etmesine yol açıyordu.
            if str((ev.meta or {}).get("decision") or "") == "ask":
                onay_bekliyor.set()

    abonelik_iptal = log.subscribe(dinle)
    kanal: queue.Queue[str] = hub.register()
    try:
        # `siraya`: dış kapının mesajı koşan bir turun ortasına KARIŞMAZ,
        # kendi turunu bekler — eşleştirme (kullanıcı mesajı → turn_end)
        # ancak böyle çalışır. Eski imzalı köprüler için geri düşüş var.
        try:
            controller.submit(str(text), str(image or ""), siraya=True)
        except TypeError:
            controller.submit(str(text), str(image or ""))
        son_tarih = baslangic + bekle_sn
        bitti = False
        while time.time() < son_tarih:
            try:
                satir = kanal.get(timeout=min(2.0, max(0.1, son_tarih - time.time())))
            except queue.Empty:
                continue
            try:
                olay = json.loads(satir)
            except ValueError:
                continue
            if olay.get("type") == "turn_end" and mesaj_gorüldu.is_set():
                bitti = True
                break
    finally:
        abonelik_iptal()
        hub.unregister(kanal)

    if not bitti:
        sebep = "tur zaman aşımına uğradı"
        if onay_bekliyor.is_set():
            sebep += " — bir araç izni onay bekliyor (yetki kipini gevşetin ya da onaylayın)"
        return {"ok": False, "error": sebep, "gecen_sn": round(time.time() - baslangic, 1)}

    dosyalar: list[str] = []
    if sandbox_root is not None:
        dosyalar = _degisen_dosyalar(Path(sandbox_root), baslangic)

    return {
        "ok": True,
        "yanit": "\n\n".join(parcalar).strip(),
        "araclar": araclar,
        "dosyalar": dosyalar,
        "kuyrukta_bekledi": kuyruktaydi,
        "gecen_sn": round(time.time() - baslangic, 1),
        "oturum": getattr(getattr(agent, "session", None), "id", ""),
    }
