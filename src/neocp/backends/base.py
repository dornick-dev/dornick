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

from dataclasses import dataclass
from typing import Any, Callable, Protocol, runtime_checkable

from ..context import Prepared
from ..session import blocks_to_dicts

TextSink = Callable[[str], None]


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
