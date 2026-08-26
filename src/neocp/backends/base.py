"""Sağlayıcıdan bağımsız model arayüzü.

Harness'ın geri kalanı hangi modelin konuştuğunu bilmez. Backend'in görevi,
hangi API'yle konuşursa konuşsun, sonucu **Anthropic blok biçiminde**
döndürmektir:

    {"type": "text", "text": ...}
    {"type": "tool_use", "id": ..., "name": ..., "input": {...}}

Bu biçimi ortak payda seçmenin sebebi, oturum günlüğünün tek bir şekli
olması. Zihin, geçmiş oturumları modelden bağımsız okuyabilmeli — bugün
Opus'la konuştuğun bir işi yarın yerel bir modelle sürdürebilesin.
"""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass
from typing import Any, AsyncIterator, Callable, Protocol, runtime_checkable

from ..context import Prepared
from ..session import blocks_to_dicts

TextSink = Callable[[str], None]


class Interrupted(Exception):
    """Kullanıcı akışı kesti — bu bir hata değil, bir karar.

    Backend'ler bunu yakalayıp `TurnResult(interrupted=True)` döndürür;
    genel hata yoluna düşmemeli (hata sayılırsa oto-mod modele kara liste
    puanı yazar, arayüz de "hata" diye gösterir).
    """


async def cancellable(stream: Any, cancel: Any) -> AsyncIterator[Any]:
    """Akışı, kesme bayrağını DA dinleyerek dolaşır.

    `async for` yalnızca parça GELDİĞİNDE kontrol veriyor. İlk token'dan
    önce — istek kuruldu, sunucu istemi işliyor — hiç parça yok ve kesme
    hiç yoklanmıyordu. Önbelleksiz İLK turda istem işleme dakikalar
    sürebiliyor: kullanıcı Durdur'a basıyor ve hiçbir şey olmuyordu
    ("ilk konuşmada durdurma çalışmıyor" yarasının kökü). Sonraki turlarda
    önbellek ilk token'ı hızlandırdığı için hata gizleniyordu.

    Burada her adım kesme bekleyişiyle yarıştırılıyor: hangisi önce
    gelirse o kazanır. Kesildiğinde `Interrupted` yükselir; akışın
    kapatılması çağıranın sorumluluğunda kalır (openai: _aclose,
    anthropic: context manager).
    """
    iterator = stream.__aiter__()
    stop = asyncio.ensure_future(cancel.wait())
    try:
        while True:
            if stop.done():
                raise Interrupted
            step = asyncio.ensure_future(iterator.__anext__())
            done, _ = await asyncio.wait({step, stop}, return_when=asyncio.FIRST_COMPLETED)
            if step not in done:
                # Kesme kazandı: yarım kalan okuma adımını iptal et.
                step.cancel()
                with contextlib.suppress(BaseException):
                    await step
                raise Interrupted
            try:
                chunk = step.result()
            except StopAsyncIteration:
                return
            yield chunk
    finally:
        stop.cancel()
        with contextlib.suppress(BaseException):
            await stop


@dataclass(slots=True)
class TurnResult:
    """Bir model turunun sonucu.

    interrupted=True ise message None'dır ve yarım kalan içerik bilinçli
    olarak atılmıştır: yarım gelen bir tool_use bloğunun input JSON'u
    eksik olur ve onu geçmişe yazmak bir sonraki isteği bozar.
    """

    message: Any | None = None
    interrupted: bool = False
    error: str | None = None
    partial_text: str = ""

    @property
    def stop_reason(self) -> str | None:
        return getattr(self.message, "stop_reason", None)

    @property
    def content(self) -> list[dict[str, Any]]:
        """İçerik bloklarını tek biçimde sözlük olarak verir.

        SDK nesneleriyle sözlükler arasındaki farkı burada bir kez kapatmak,
        döngünün ve oturumun her yerde ikisini de düşünmesini engeller.
        Thinking blokları dahil hiçbir alan atılmaz — API değiştirilmiş
        blokları reddeder.
        """
        return blocks_to_dicts(getattr(self.message, "content", None) or [])

    @property
    def usage(self) -> Any:
        return getattr(self.message, "usage", None)

    def tool_uses(self) -> list[dict[str, Any]]:
        return [b for b in self.content if b.get("type") == "tool_use"]


@dataclass(slots=True)
class Callbacks:
    on_text: TextSink = lambda _: None
    on_thinking: TextSink = lambda _: None
    on_tool_start: Callable[[str], None] = lambda _: None
    on_turn_start: Callable[[], None] = lambda: None


@runtime_checkable
class Backend(Protocol):
    """Her sağlayıcının uyması gereken sözleşme."""

    async def turn(
        self,
        prepared: Prepared,
        tools: list[dict[str, Any]],
        *,
        cancel: Any,
        callbacks: Callbacks | None = None,
    ) -> TurnResult: ...

    async def count_tokens(self, prepared: Prepared, tools: list[dict[str, Any]]) -> int: ...

    async def close(self) -> None: ...


@dataclass(slots=True)
class SimpleMessage:
    """Anthropic yanıt nesnesinin yerine geçen taşıyıcı.

    Yerel sağlayıcılar kendi biçimlerinde cevap verir; backend onu bu
    şekle çevirir ve harness farkı görmez.
    """

    content: list[dict[str, Any]]
    stop_reason: str
    usage: Any = None
    stop_details: Any = None


@dataclass(slots=True)
class SimpleUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0
