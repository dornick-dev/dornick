"""Oto model kipi — yalnızca OpenRouter.

Kullanıcı model adı olarak "oto" seçtiğinde istekler OpenRouter'ın ücretsiz
modellerinden oluşan küçük bir havuzla atılıyor: ilk model asıl, sıradaki
birkaçı OpenRouter'ın kendi yedek zinciri (`models` alanı). Böylece anahtar
girilir girilmez, tek kuruş harcamadan çalışan bir kurulum var.

Havuz canlı listeden geliyor ve diske önbellekleniyor (24 saat taze; ağ
yokken bayat önbellek de iş görür). Süzgeç üç katlı:

  * ücretsiz: pricing.prompt == 0 VE pricing.completion == 0,
  * araç destekli: supported_parameters "tools" içeriyor — araçsız bir
    modelle bu harness'ın yapabileceği bir şey yok,
  * popülerlik sırası: liste `order=top-weekly` ile isteniyor; parametre
    canlı yanıtla doğrulandı (max_price=0 19 model döndürdü, ücretli
    sızıntı yok) ama körü körüne güvenilmiyor — dönen liste yerelde bir
    kez daha süzülüyor, uç bir gün bozulursa tam liste çekilip süzülüyor.

Ücretsiz uçların huyu belli: yavaşlayabilir, boş dönebilir, kaybolabilir.
`Saglik` model başına son birkaç çağrıyı sayıyor; arka arkaya hata veren
model bir süreliğine havuzun sonuna itiliyor — kullanıcı "neden hep aynı
hatayı alıyorum" yaşamıyor. Bellek-içi yeter: süreç yeniden başlayınca
herkes temiz sayfayla döner.

Buradaki hiçbir alan başka sağlayıcının isteğine DOKUNMUYOR: istek
şekillendirme yalnız `oto_mu` doğruyken devreye giriyor.
"""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from pathlib import Path
from typing import Any, Callable

from .config import OPENROUTER_URL, OTO_MODEL, ModelConfig

# Havuz önbelleği: .dornick/oto_havuz.json
HAVUZ_DOSYA = "oto_havuz.json"
HAVUZ_BOY = 6
TAZELIK_SN = 24 * 3600

# Liste isteği kısa kesilmeli: model listesi için yarım dakika beklemek,
# ilk cevabı yarım dakika bekletmek demek.
LISTE_ZAMAN_ASIMI = 20.0
ANAHTAR_ZAMAN_ASIMI = 10.0

# Sağlık: son PENCERE çağrılık kayan pencere; HATA_ESIGI hata modeli
# CEZA_SN boyunca havuzun sonuna itiyor.
PENCERE = 5
HATA_ESIGI = 2
CEZA_SN = 15 * 60


def oto_mu(model: ModelConfig) -> bool:
    """Bu yapılandırma oto kipi mi?

    İki şart birden: adres OpenRouter VE ad "oto". Başka bir sağlayıcıda
    "oto" adında gerçek bir model olabilir; ona dokunulmaz.
    """
    return (
        (model.base_url or "").rstrip("/") == OPENROUTER_URL
        and (model.name or "").strip().lower() == OTO_MODEL
    )


# -- havuz -------------------------------------------------------------


def suz(entries: list[Any]) -> list[str]:
    """Model listesinden ücretsiz + araç destekli ilk HAVUZ_BOY kimlik.

    Sıra korunuyor: liste popülerlik sırasıyla istendiyse havuz da öyle.
    Fiyat karşılaştırması sayıyla yapılıyor — OpenRouter "0" da "0.000000"
    da döndürebiliyor, dize karşılaştırması ikisinden birini kaçırır.
    """
    havuz: list[str] = []
    for entry in entries:
        if not isinstance(entry, dict) or not entry.get("id"):
            continue
        pricing = entry.get("pricing") or {}
        try:
            bedava = (
                float(pricing.get("prompt") or "1") == 0.0
                and float(pricing.get("completion") or "1") == 0.0
            )
        except (TypeError, ValueError):
            continue
        if not bedava:
            continue
        if "tools" not in (entry.get("supported_parameters") or []):
            continue
        ident = str(entry["id"])
        # Batch-only kimlikler canlı sohbette 404 — havuza sokma.
        if ident.rsplit(":", 1)[-1].lower() == "batch" and ":" in ident:
            continue
        havuz.append(ident)
        if len(havuz) >= HAVUZ_BOY:
            break
    return havuz


def _indir() -> list[str]:
    """Canlı listeden havuzu kurar. Ağ yoksa boş liste.

    Önce süzülmüş + popülerlik sıralı uç; parametreler bir gün bozulursa
    tam liste çekilip yerelde süzülüyor. Her iki yanıt da `suz`dan geçiyor:
    sunucunun süzgecine güvenmek, ücretli bir modelin sızması demek olur.
    """
    for url in (
        OPENROUTER_URL + "/models?max_price=0&order=top-weekly",
        OPENROUTER_URL + "/models",
    ):
        try:
            with urllib.request.urlopen(url, timeout=LISTE_ZAMAN_ASIMI) as response:
                payload = json.load(response)
        except (urllib.error.URLError, OSError, ValueError, TimeoutError):
            continue
        data = payload.get("data") if isinstance(payload, dict) else None
        if isinstance(data, list) and (havuz := suz(data)):
            return havuz
    return []


def _state_dir() -> Path:
    """Önbelleğin evi. Ortam değişkeni > sabitlenmiş ev."""
    env = os.getenv("DORNICK_STATE_DIR")
    if env:
        return Path(env)
    from .config import _resolve_workspace

    return _resolve_workspace(None) / ".dornick"


# Süreç içinde ikinci kez diske/ağa gitmemek için. Anahtar dosya yolu:
# testler ayrı state_dir veriyor ve birbirine karışmamalı.
_KILIT = threading.Lock()
_BELLEK: dict[str, tuple[float, list[str]]] = {}


def havuz(state_dir: Path | str | None = None, *, simdi: Callable[[], float] = time.time) -> list[str]:
    """Ücretsiz model havuzu (en çok HAVUZ_BOY kimlik).

    Sıra: bellek-içi (taze) > diskteki önbellek (taze) > canlı liste >
    bayat önbellek (ağ yokken hiç yoktan iyi) > boş liste.
    """
    yer = Path(state_dir) if state_dir else _state_dir()
    dosya = yer / HAVUZ_DOSYA

    with _KILIT:
        ts, eldeki = _BELLEK.get(str(dosya), (0.0, []))
    if eldeki and simdi() - ts < TAZELIK_SN:
        return list(eldeki)

    kayit = _oku(dosya)
    if kayit.get("havuz") and simdi() - float(kayit.get("ts") or 0) < TAZELIK_SN:
        with _KILIT:
            _BELLEK[str(dosya)] = (float(kayit["ts"]), list(kayit["havuz"]))
        return list(kayit["havuz"])

    taze = _indir()
    if taze:
        kayit.update({"ts": simdi(), "havuz": taze})
        _yaz(dosya, kayit)
        with _KILIT:
            _BELLEK[str(dosya)] = (simdi(), list(taze))
        return taze

    # Ağ yok: bayat önbellek, çalışmayan bir kurulumdan iyidir.
    return list(kayit.get("havuz") or [])


def son_yaz(model: str, state_dir: Path | str | None = None) -> None:
    """Son seçilen modeli önbellek dosyasına not eder.

    Teşhis için: oto kipinde "hangi modelle konuştum" sorusunun cevabı
    burada. Yazamamak bir turu asla düşürmemeli.
    """
    try:
        yer = Path(state_dir) if state_dir else _state_dir()
        dosya = yer / HAVUZ_DOSYA
        kayit = _oku(dosya)
        kayit["son"] = {"model": model, "ts": time.time()}
        _yaz(dosya, kayit)
    except Exception:
        pass


def _oku(dosya: Path) -> dict[str, Any]:
    try:
        data = json.loads(dosya.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _yaz(dosya: Path, kayit: dict[str, Any]) -> None:
    try:
        dosya.parent.mkdir(parents=True, exist_ok=True)
        temp = dosya.with_suffix(dosya.suffix + ".tmp")
        temp.write_text(json.dumps(kayit, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(dosya)
    except OSError:
        pass  # önbellek yazılamazsa bir sonraki açılışta yeniden denenir


# -- sağlık ------------------------------------------------------------


class Saglik:
    """Model başına sağlık puanı: son PENCERE çağrının kaydı.

    Zaman aşımı, boş yanıt ve hata aynı kefede: çağrı başarısız. Pencerede
    HATA_ESIGI başarısızlık biriken model CEZA_SN boyunca havuzun sonuna
    itiliyor; süre dolunca temiz sayfayla dönüyor.

    `saat` enjekte edilebilir — testler 15 dakikayı beklemesin.
    """

    def __init__(self, saat: Callable[[], float] = time.monotonic) -> None:
        self.saat = saat
        self._kayit: dict[str, deque[bool]] = {}
        self._ceza: dict[str, float] = {}

    def kaydet(self, model: str, ok: bool) -> None:
        pencere = self._kayit.setdefault(model, deque(maxlen=PENCERE))
        pencere.append(bool(ok))
        if sum(1 for basarili in pencere if not basarili) >= HATA_ESIGI:
            self._ceza[model] = self.saat() + CEZA_SN
            # Ceza yazıldı; pencere sıfırlanıyor ki model döndüğünde eski
            # hataları sırtında taşımasın.
            pencere.clear()

    def cezali(self, model: str) -> bool:
        return self._ceza.get(model, 0.0) > self.saat()

    def sirala(self, havuz: list[str]) -> list[str]:
        """Cezalı modelleri sona iter; gerisinin sırasına dokunmaz."""
        saglam = [m for m in havuz if not self.cezali(m)]
        hasta = [m for m in havuz if self.cezali(m)]
        return saglam + hasta


# -- anahtar doğrulama --------------------------------------------------


def dogrula_anahtar(anahtar: str) -> str:
    """OpenRouter anahtarını GET /key ile yoklar.

    Dönen değer üç durumdan biri:
        "ok"        anahtar geçerli
        "gecersiz"  401 — anahtar yanlış, kaydedilmemeli
        "belirsiz"  ağ yok ya da beklenmedik cevap — doğrulama atlanabilir
    """
    istek = urllib.request.Request(
        OPENROUTER_URL + "/key",
        headers={"Authorization": f"Bearer {anahtar}"},
    )
    try:
        with urllib.request.urlopen(istek, timeout=ANAHTAR_ZAMAN_ASIMI):
            return "ok"
    except urllib.error.HTTPError as exc:
        return "gecersiz" if exc.code == 401 else "belirsiz"
    except (urllib.error.URLError, OSError, TimeoutError):
        return "belirsiz"
