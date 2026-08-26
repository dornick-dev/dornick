"""neocp taban modeli — ortak ayarlar ve bütçe bekçisi.

Öğretmen: Gemini flash-lite (OpenRouter, Fatih'in $15 limitli anahtarı).
Bekçi HER isteğin usage'ını sayar ve SERT_SINIR'da durur — anahtarın
sağlayıcı limiti son savunma hattıdır, ilk değil.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

KOK = Path(__file__).resolve().parent
VERI = KOK / "veri"
OUT = KOK / "out"

# Sırayla denenir: ilki 404 verirse ikincisine düşülür.
OGRETMENLER = ("google/gemini-3.1-flash-lite", "google/gemini-2.5-flash-lite")

# $/1M token — Fatih'in verdiği fiyatlar (3.1 flash-lite).
GIRIS_USD = 0.25
CIKIS_USD = 1.50

# Bütçe: anahtarın limiti 15; biz 12'de dururuz.
SERT_SINIR_USD = 12.0
HARCAMA_DOSYASI = VERI / "harcama.json"

_kilit = threading.Lock()


def _anahtar() -> str:
    for line in (KOK / "anahtar.env").read_text(encoding="utf-8").splitlines():
        if line.startswith("OPENROUTER_API_KEY="):
            return line.split("=", 1)[1].strip()
    raise RuntimeError("anahtar.env içinde OPENROUTER_API_KEY yok")


def harcama() -> dict:
    try:
        return json.loads(HARCAMA_DOSYASI.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"giris": 0, "cikis": 0, "usd": 0.0, "istek": 0}


def _harcama_ekle(giris: int, cikis: int) -> float:
    with _kilit:
        h = harcama()
        h["giris"] += giris
        h["cikis"] += cikis
        h["istek"] += 1
        h["usd"] = h["giris"] / 1e6 * GIRIS_USD + h["cikis"] / 1e6 * CIKIS_USD
        VERI.mkdir(parents=True, exist_ok=True)
        HARCAMA_DOSYASI.write_text(json.dumps(h, indent=1), encoding="utf-8")
        return h["usd"]


class ButceDoldu(RuntimeError):
    pass


_secilen_ogretmen: list[str] = []


def ogretmen_sor(messages: list[dict], *, max_tokens: int = 400,
                 temperature: float = 0.0, deneme: int = 3) -> str:
    """Tek öğretmen çağrısı: bütçe bekçili, yeniden denemeli."""
    if harcama()["usd"] >= SERT_SINIR_USD:
        raise ButceDoldu(f"Bütçe sınırı: ${SERT_SINIR_USD}")

    adaylar = _secilen_ogretmen or list(OGRETMENLER)
    son_hata: Exception | None = None
    for model in adaylar:
        for tur in range(deneme):
            body = json.dumps({
                "model": model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
            }).encode()
            req = urllib.request.Request(
                "https://openrouter.ai/api/v1/chat/completions", data=body,
                headers={"Authorization": f"Bearer {_anahtar()}",
                         "Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=120) as r:
                    out = json.load(r)
                usage = out.get("usage") or {}
                _harcama_ekle(int(usage.get("prompt_tokens") or 0),
                              int(usage.get("completion_tokens") or 0))
                if not _secilen_ogretmen:
                    _secilen_ogretmen.append(model)
                return (out["choices"][0]["message"]["content"] or "").strip()
            except urllib.error.HTTPError as exc:
                if exc.code == 404:
                    son_hata = exc
                    break  # bu model yok; sıradakine geç
                son_hata = exc
                time.sleep(1.5 * (tur + 1))
            except Exception as exc:  # ağ dalgalanması
                son_hata = exc
                time.sleep(1.5 * (tur + 1))
    raise RuntimeError(f"Öğretmen cevap vermedi: {son_hata}")
