"""Model fiyat etiketi — OpenRouter kataloğundan.

Maliyet çipi için: seçili modelin girdi/çıktı fiyatı (USD/token).
OpenRouter'ın /models yanıtı her modelin `pricing` alanını veriyor;
katalog isteği pahalı (yüzlerce model + ağ), o yüzden otomod havuz
önbelleği kalıbıyla hem belleğe hem diske önbellekleniyor (24 saat
taze; ağ yokken bayat tablo hiç yoktan iyi).

İki kural tur hızını koruyor:

  * `etiket(ag=False)` ASLA ağa çıkmaz — bellek + disk. Turun içinde
    çağrılabilir.
  * Ağa çıkan tek yol `etiket(ag=True)`; köprü onu arka plan
    thread'inde, oturumda bir kez çağırıyor.

Fiyat bilinemiyorsa (başka sağlayıcı, katalogda olmayan model, ağ yok)
None dönüyor: arayüz çipi dolar yerine token sayısı gösterir — yanlış
bir rakam basmaktan iyi.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

from .config import OPENROUTER_URL, OTO_MODEL, ModelConfig
from .automode import LIST_TIMEOUT, FRESHNESS_S, _oku, _state_dir, _yaz

# Fiyat tablosu önbelleği: .dornick/fiyat.json
PRICE_FILE = "fiyat.json"

# Süreç içinde ikinci kez diske gitmemek için; anahtar dosya yolu
# (testler ayrı state_dir veriyor ve birbirine karışmamalı).
_KILIT = threading.Lock()
_BELLEK: dict[str, tuple[float, dict[str, dict[str, float]]]] = {}


def suz(entries: list[Any]) -> dict[str, dict[str, float]]:
    """Model listesinden fiyat tablosu: {id: {"girdi": $, "cikti": $}}.

    Fiyatlar USD/token; OpenRouter dize döndürüyor ("0.000003") ve
    sayıya çevrilemeyen kayıt sessizce atlanıyor — tek bozuk giriş
    tabloyu düşürmemeli.
    """
    tablo: dict[str, dict[str, float]] = {}
    for entry in entries:
        if not isinstance(entry, dict) or not entry.get("id"):
            continue
        pricing = entry.get("pricing") or {}
        try:
            girdi = float(pricing.get("prompt"))
            cikti = float(pricing.get("completion"))
        except (TypeError, ValueError):
            continue
        if girdi < 0 or cikti < 0:
            continue   # negatif fiyat: bozuk kayıt
        tablo[str(entry["id"])] = {"girdi": girdi, "cikti": cikti}
    return tablo


def _indir() -> dict[str, dict[str, float]]:
    """Canlı katalogdan fiyat tablosu. Ağ yoksa boş sözlük."""
    try:
        with urllib.request.urlopen(
            OPENROUTER_URL + "/models", timeout=LIST_TIMEOUT
        ) as response:
            payload = json.load(response)
    except (urllib.error.URLError, OSError, ValueError, TimeoutError):
        return {}
    data = payload.get("data") if isinstance(payload, dict) else None
    return suz(data) if isinstance(data, list) else {}


def tablo(
    state_dir: Path | str | None = None,
    *,
    ag: bool = False,
    simdi: Callable[[], float] = time.time,
) -> dict[str, dict[str, float]]:
    """Fiyat tablosu. Sıra: bellek (taze) > disk (taze) > [ağ] > bayat disk.

    `ag=False` hiç ağa çıkmaz — turun içinden güvenle çağrılır.
    """
    yer = Path(state_dir) if state_dir else _state_dir()
    dosya = yer / PRICE_FILE

    with _KILIT:
        ts, eldeki = _BELLEK.get(str(dosya), (0.0, {}))
    if eldeki and simdi() - ts < FRESHNESS_S:
        return dict(eldeki)

    kayit = _oku(dosya)
    if kayit.get("fiyatlar") and simdi() - float(kayit.get("ts") or 0) < FRESHNESS_S:
        with _KILIT:
            _BELLEK[str(dosya)] = (float(kayit["ts"]), dict(kayit["fiyatlar"]))
        return dict(kayit["fiyatlar"])

    if ag:
        taze = _indir()
        if taze:
            kayit.update({"ts": simdi(), "fiyatlar": taze})
            _yaz(dosya, kayit)
            with _KILIT:
                _BELLEK[str(dosya)] = (simdi(), dict(taze))
            return taze

    # Ağ yok ya da yasak: bayat tablo, hiç yoktan iyi.
    return dict(kayit.get("fiyatlar") or {})


def etiket(
    model: ModelConfig,
    state_dir: Path | str | None = None,
    *,
    ag: bool = False,
    simdi: Callable[[], float] = time.time,
) -> dict[str, float] | None:
    """Seçili modelin fiyat etiketi: {"girdi": USD/token, "cikti": USD/token}.

    Yalnız OpenRouter'da anlamlı: başka sağlayıcının (yerel sunucu,
    Anthropic) fiyatı bu katalogda yok → None. "Oto" kipi ücretsiz
    havuzla çalışıyor → sıfır fiyat (gerçek: tek kuruş gitmiyor).
    Katalogda olmayan model → None; çip token sayısına düşer.
    """
    if (model.base_url or "").rstrip("/") != OPENROUTER_URL:
        return None
    ad = (model.name or "").strip()
    if ad.lower() == OTO_MODEL:
        return {"girdi": 0.0, "cikti": 0.0}
    return tablo(state_dir, ag=ag, simdi=simdi).get(ad)
