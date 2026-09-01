"""Anthropic backend.

Streaming varsayılan: max_tokens 16k'nın üstünde streaming olmadan istek
atmak SDK'da HTTP timeout riski taşır, ayrıca kullanıcıya ilerleme
göstermenin ve turu ortasında kesebilmenin tek yolu bu.
"""

from __future__ import annotations

from typing import Any

import anthropic

from ..config import ModelConfig
from ..context import Prepared
from .base import Callbacks, Interrupted, TurnResult, cancellable


class AnthropicBackend:
    name = "anthropic"

    def __init__(self, model: ModelConfig, client: Any | None = None) -> None:
        self.model = model
        kwargs: dict[str, Any] = {}
        if model.base_url:
            kwargs["base_url"] = model.base_url
        # SDK varsayılanı 10 dakikalık zaman aşımı: ölü bir bağlantı turu
        # dakikalarca asıyordu (OpenAI backend'iyle aynı sınırlar).
        kwargs.setdefault("timeout", 90.0)
        kwargs.setdefault("max_retries", 2)
        self._client = client or anthropic.AsyncAnthropic(**kwargs)

    async def close(self) -> None:
        await self._client.close()

    def _stream_api(self, prepared: Prepared) -> Any:
        # Beta özellikleri (bağlam düzenleme, compaction) beta ad alanını
        # gerektirir. Gerekmedikçe GA yolunda kal.
        namespace = (
            self._client.beta.messages if prepared.needs_beta_client else self._client.messages
        )
        return namespace.stream

    async def turn(
        self,
        prepared: Prepared,
        tools: list[dict[str, Any]],
        *,
        cancel: Any,
        callbacks: Callbacks | None = None,
    ) -> TurnResult:
        callbacks = callbacks or Callbacks()
        kwargs = prepared.request_kwargs(self.model, tools)
        stream_fn = self._stream_api(prepared)
        buffer: list[str] = []

        callbacks.on_turn_start()

        try:
            async with stream_fn(**kwargs) as stream:
                # `cancellable`: kesme, parça BEKLERKEN de yoklanıyor — ilk
                # token'dan önce Durdur'un işlememesi burada düzeltildi.
                async for event in cancellable(stream, cancel):
                    _dispatch(event, callbacks, buffer)

                message = await stream.get_final_message()

        except Interrupted:
            return TurnResult(interrupted=True, partial_text="".join(buffer))
        except anthropic.APIStatusError as exc:
            return TurnResult(error=_explain_status_error(exc), partial_text="".join(buffer))
        except anthropic.APIConnectionError as exc:
            return TurnResult(error=f"Bağlantı kurulamadı: {exc}", partial_text="".join(buffer))

        return TurnResult(message=message, partial_text="".join(buffer))

    async def count_tokens(self, prepared: Prepared, tools: list[dict[str, Any]]) -> int:
        """Gerçek token sayısı. Tahmin kütüphanesi kullanma — hepsi yanlış sayar."""
        result = await self._client.messages.count_tokens(
            model=self.model.name,
            system=prepared.system,
            messages=prepared.messages,
            tools=tools,
        )
        return result.input_tokens


def _dispatch(event: Any, cb: Callbacks, buffer: list[str]) -> None:
    kind = getattr(event, "type", "")

    if kind == "content_block_delta":
        delta = event.delta
        dtype = getattr(delta, "type", "")
        if dtype == "text_delta":
            buffer.append(delta.text)
            cb.on_text(delta.text)
        elif dtype == "thinking_delta":
            cb.on_thinking(delta.thinking)

    elif kind == "content_block_start":
        block = event.content_block
        if getattr(block, "type", None) == "tool_use":
            cb.on_tool_start(block.name)


def _explain_status_error(exc: anthropic.APIStatusError) -> str:
    """Sık görülen 400'leri okunur hale getirir."""
    text = str(getattr(exc, "message", "") or exc)
    hints = {
        "budget_tokens": "Opus 4.7+ üzerinde budget_tokens kaldırıldı; adaptif düşünme kullan.",
        "temperature": "Opus 4.7+ üzerinde temperature/top_p/top_k kabul edilmiyor.",
        "tool_result": "Her tool_use için tam olarak bir tool_result dönmeli.",
        "assistant": "Son turda asistan prefill'i desteklenmiyor.",
    }
    for needle, hint in hints.items():
        if needle in text:
            return f"API {exc.status_code}: {text}\n-> {hint}"
    return f"API {exc.status_code}: {text}"
