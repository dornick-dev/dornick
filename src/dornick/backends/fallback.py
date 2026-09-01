"""Yedek model: asıl model kalıcı olarak susunca iş ölmesin.

Sorun sahada şöyle görünüyor: uzun bir iş koşuyor, kredi bitiyor (402) ya
da ayarlardaki model kimliği artık geçersiz oluyor. Sağlayıcı her istekte
aynı cevabı veriyor, yani beklemek işe yaramıyor; döngü hatayı yüzeye
çıkarıp duruyor ve saatlerdir süren iş yarıda kalıyor.

Bu sarmalayıcı araya giriyor: asıl model KALICI bir hatayla dönerse aynı
tur, yedek modelle bir kez daha deneniyor. Başarılıysa iş sürüyor ve
kullanıcı sohbette tek satır görüyor. O andan sonra tur yedek modelle
devam ediyor — her turda asıl modeli yeniden denemek, her turu iki isteğe
çıkarır ve kredi bittiyse hiçbir zaman düzelmez.

Neden BACKEND katmanında: döngü (`loop.py`) hangi modelin konuştuğunu
bilmiyor, yalnızca bir `Backend` görüyor. Geçişi buraya koymak döngüyü,
oturum günlüğünü ve arayüzü değiştirmeden çalışıyor — `build_client`
yedek tanımlıysa asıl istemci yerine bunu döndürüyor.

Sınır: GEÇİCİ hatalar buraya hiç uğramıyor. Bağlantı kopması, 429 ve 5xx
zaten döngünün yeniden deneme merdiveninde (RETRY_DELAYS) ve orada
kalmalı — bir sağlayıcı hıçkırığında kalıcı olarak zayıf bir modele
geçmek, sessizce kalitesi düşmüş bir iş demek.
"""

from __future__ import annotations

import re
from dataclasses import replace
from typing import Any

from ..config import ModelConfig
from .base import Backend, Callbacks, TurnResult

# Kalıcı sayılan haller. Ölçü tek soru: AYNI istek birazdan tekrar
# gönderilse sonuç değişir mi? Değişmeyecekse yedeğe geçmek doğru.
#
#   402  ödeme / kredi — para yatana kadar her istek aynı
#   401  anahtar geçersiz — döngü bunu geçici sayıyor (anahtar sonradan
#        düzelebilir) ve yeniden deniyor; oraya dokunmuyoruz
#   404  model yok / kaldırılmış
#   400  çoğu zaman geçersiz model kimliği ya da desteklenmeyen alan
#   403  erişim yok (bölge, plan)
_PERMANENT_STATUS = ("400", "402", "403", "404", "405", "422")

# Durum kodu gelmeyen sağlayıcılar aynı şeyi düz metinle söylüyor.
_PERMANENT_TEXT = re.compile(
    r"is not a valid model|model_not_found|modeli bulunamadı|"
    r"insufficient|credit|quota|billing|payment required|"
    r"unsupported_country|not permitted",
    re.I,
)


def is_permanent(error: str | None) -> bool:
    """Yeniden denemenin sonucu değiştirmeyeceği bir hata mı?

    Kararı METİN üzerinden veriyoruz çünkü backend'ler hatayı zaten
    okunur bir cümleye çeviriyor (`_explain`) ve özgün istisna nesnesi
    o noktada kayboluyor.
    """
    text = (error or "").strip()
    if not text:
        return False
    if re.search(r"\b(" + "|".join(_PERMANENT_STATUS) + r")\b", text):
        return True
    return bool(_PERMANENT_TEXT.search(text))


class FallbackBackend:
    """Asıl backend'i sarar; kalıcı hatada yedeğe geçer ve orada kalır."""

    def __init__(self, model: ModelConfig, build: Any) -> None:
        self._build = build
        self._model = model
        self._primary: Backend | None = build(model)
        self._fallback: Backend | None = None
        # Geçiş yapıldı mı: yapıldıysa artık asıl model hiç denenmiyor.
        self.switched = False

    # -- yardımcılar ---------------------------------------------------

    @property
    def fallback_name(self) -> str:
        return (self._model.fallback_model or "").strip()

    def _fallback_client(self) -> Backend:
        """Yedek istemci ilk gerektiğinde kuruluyor.

        Sağlayıcı ve adres aynı kalıyor, yalnızca model adı değişiyor:
        yedek "aynı kapıdaki başka model" demek. Farklı bir sağlayıcıya
        düşmek ayarların işi — burada sessizce yapılması, hangi anahtarla
        konuşulduğunu görünmez kılardı.
        """
        if self._fallback is None:
            self._fallback = self._build(
                replace(self._model, name=self.fallback_name, fallback_model="")
            )
        return self._fallback

    # -- Backend sözleşmesi --------------------------------------------

    async def turn(
        self,
        prepared: Any,
        tools: list[dict[str, Any]],
        *,
        cancel: Any,
        callbacks: Callbacks | None = None,
    ) -> TurnResult:
        if self.switched:
            return await self._fallback_client().turn(
                prepared, tools, cancel=cancel, callbacks=callbacks)

        assert self._primary is not None
        result = await self._primary.turn(
            prepared, tools, cancel=cancel, callbacks=callbacks)

        # Kesme bir hata değil bir karar: yedeğe geçmek yanlış olurdu.
        if result.interrupted or not is_permanent(result.error):
            return result

        self.switched = True
        # Tek satırlık haber. `on_text` gösterim kanalı: satır sohbette
        # görünüyor ama cevabın içeriğine ve oturum günlüğüne girmiyor —
        # geçmişe modelin söylemediği bir cümleyi yazmak, sonraki turlarda
        # modelin kendi sözü sanılırdı.
        if callbacks is not None:
            callbacks.on_text(
                f"\n_Asıl model yanıt vermedi — yedek modelle sürüyorum "
                f"({self.fallback_name})._\n\n"
            )

        return await self._fallback_client().turn(
            prepared, tools, cancel=cancel, callbacks=callbacks)

    async def count_tokens(self, prepared: Any, tools: list[dict[str, Any]]) -> int:
        client = self._fallback_client() if self.switched else self._primary
        assert client is not None
        return await client.count_tokens(prepared, tools)

    async def close(self) -> None:
        for client in (self._primary, self._fallback):
            if client is not None:
                await client.close()
