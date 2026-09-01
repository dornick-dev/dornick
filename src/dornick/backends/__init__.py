"""Model sağlayıcıları.

Harness tek bir sözleşme görür (`Backend`); hangi modelin konuştuğu
yapılandırma meselesidir. Aynı zihin ve aynı oturum günlüğü, bugün Opus'la
yarın yerel bir modelle sürdürülebilir.
"""

from __future__ import annotations

from ..config import ModelConfig
from .base import (
    Backend,
    Callbacks,
    Interrupted,
    SimpleMessage,
    SimpleUsage,
    TurnResult,
    cancellable,
)

__all__ = [
    "Backend",
    "Callbacks",
    "Interrupted",
    "SimpleMessage",
    "SimpleUsage",
    "TurnResult",
    "build_client",
    "cancellable",
]

PROVIDERS = ("anthropic", "openai")


def build_client(model: ModelConfig) -> Backend:
    """Yapılandırmaya göre istemci kurar.

    Yedek model tanımlıysa asıl istemci bir sarmalayıcının içine giriyor:
    asıl model kalıcı olarak susarsa (kredi bitti, kimlik geçersiz) tur
    ölmek yerine yedekle sürüyor. Döngü farkı görmüyor — gördüğü şey yine
    tek bir `Backend`.
    """
    if (model.fallback_model or "").strip() and model.fallback_model != model.name:
        from .fallback import FallbackBackend

        return FallbackBackend(model, _plain_client)

    return _plain_client(model)


def _plain_client(model: ModelConfig) -> Backend:
    if model.provider == "anthropic":
        from .anthropic_backend import AnthropicBackend

        return AnthropicBackend(model)

    if model.provider == "openai":
        from .openai_backend import OpenAIBackend

        return OpenAIBackend(model)

    raise ValueError(
        f"Bilinmeyen sağlayıcı: {model.provider}. Geçerli olanlar: {', '.join(PROVIDERS)}"
    )
